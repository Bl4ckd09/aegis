"""Ripple — causal cascade engine.

A disruption point ripples outward through London's road graph (BFS); we quantify
what the ripple touches: road junctions, bus stops, bus routes, and (equity layer)
the population + deprivation of the LSOAs it reaches.

Compute is dual-path (mirrors geo.py): cuGraph/cuDF on a GPU box, networkx/pandas
CPU fallback elsewhere — so it builds on a laptop and accelerates on the DGX Spark.

Heavy data (road graph, bus stops, LSOA table) is built once at startup and cached
to data/ripple/ so restarts are fast.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Optional

import httpx
import networkx as nx
import osmnx as ox

from . import config

# RAPIDS cuGraph/cuDF for GPU BFS (on the DGX Spark or a cloud RAPIDS GPU); the
# engine falls back to networkx on CPU when these aren't present.
try:
    import cudf
    import cugraph
    _HAS_CUGRAPH = True
except Exception:
    _HAS_CUGRAPH = False

RIPPLE_DIR = config.DATA_DIR / "ripple"
RIPPLE_DIR.mkdir(parents=True, exist_ok=True)
GRAPH_PATH = RIPPLE_DIR / "graph.graphml"
STOPS_PATH = RIPPLE_DIR / "stops.json"
POIS_PATH = RIPPLE_DIR / "pois.json"
CENT_PATH = RIPPLE_DIR / "centrality.json"
IMD_PATH = RIPPLE_DIR / "imd_london.xlsx"
IMD_URL = ("https://data.london.gov.uk/download/2l15g/"
           "9ee0cf66-e6f9-4e38-8eec-79c1d897e248/ID%202019%20for%20London.xlsx")

# Demo area: centre + radius of the road graph (env-overridable).
CENTER_LAT = float(os.environ.get("AEGIS_RIPPLE_LAT", "51.5074"))
CENTER_LON = float(os.environ.get("AEGIS_RIPPLE_LON", "-0.1278"))
RADIUS_M = int(os.environ.get("AEGIS_RIPPLE_RADIUS", "6000"))
DEFAULT_HOPS = int(os.environ.get("AEGIS_RIPPLE_HOPS", "15"))

# Average daily boardings per stop — proxy when per-stop counts aren't loaded.
BOARDINGS_PER_STOP = float(os.environ.get("AEGIS_BOARDINGS_PER_STOP", "600"))


class RippleEngine:
    def __init__(self) -> None:
        self.G: Optional[nx.MultiDiGraph] = None
        self.UG: Optional[nx.Graph] = None          # undirected, for reachability BFS
        self.stops: list[dict] = []                 # {lat, lon, name, routes:[...], node, lsoa}
        self.lsoa: dict[str, dict] = {}             # LSOA code -> {decile, pop, name}
        self.pois: list[dict] = []                  # high-street businesses {lat,lon,name,node,lsoa}
        self.centrality: dict[int, float] = {}      # node -> betweenness percentile (0-1)
        self.lifelines: list[dict] = []             # top chokepoints by businesses depending on them
        self.G_cu = None                            # cuGraph graph (GPU BFS) when available
        self.engine_backend = "networkx (CPU)"      # how the graph/betweenness was built
        self.bfs_backend = "networkx (CPU)"         # how per-query BFS (_reach) runs
        self.ready = False

    # --- one-time load (called at startup) ----------------------------------
    def load(self) -> None:
        self._load_graph()
        self._load_stops()
        self._attach_stops_to_nodes()
        self._load_lsoa()
        self._attach_stops_to_lsoa()
        self._load_pois()
        self._build_cugraph()
        self._build_centrality()        # heavy global analytic — GPU if available
        self._select_bfs_backend()      # decide per-query BFS path (frees GPU graph if CPU)
        self._build_lifelines()         # one-time _reach×40 — now on the chosen backend
        self.ready = True
        print(f"[ripple] ready: {self.G.number_of_nodes()} nodes, "
              f"{self.G.number_of_edges()} edges, {len(self.stops)} stops, "
              f"{len(self.lsoa)} LSOAs | build: {self.engine_backend} | "
              f"per-query BFS: {self.bfs_backend}")

    def _select_bfs_backend(self) -> None:
        """Choose the per-query BFS backend (config-driven, keyed on graph size).

        cuGraph wins only on large graphs; below RIPPLE_GPU_BFS_MIN_NODES, networkx is
        far faster per query and avoids GPU oversubscription. When CPU is chosen we drop
        the cuGraph graph reference to free GPU memory (betweenness is already built);
        `_reach` then takes its networkx path via `self.G_cu is None`."""
        n = self.G.number_of_nodes()
        gpu_built = self.G_cu is not None
        mode = config.RIPPLE_BFS_BACKEND
        if mode == "gpu":
            use_gpu = gpu_built
        elif mode == "cpu":
            use_gpu = False
        else:  # auto
            use_gpu = gpu_built and n >= config.RIPPLE_GPU_BFS_MIN_NODES
        if not use_gpu and gpu_built:
            self.G_cu = None  # release GPU graph → per-query BFS runs on CPU networkx
            print(f"[ripple] per-query BFS → CPU networkx (n={n} < "
                  f"{config.RIPPLE_GPU_BFS_MIN_NODES}, mode={mode}); cuGraph BFS graph freed")
        self.bfs_backend = "cuGraph (GPU)" if (use_gpu and self.G_cu is not None) else "networkx (CPU)"

    def _build_cugraph(self) -> None:
        """Build the cuGraph graph for GPU BFS (no-op without RAPIDS → networkx CPU)."""
        if not _HAS_CUGRAPH:
            return
        try:
            edges = list(self.UG.edges())
            df = cudf.DataFrame({"src": [int(u) for u, v in edges],
                                 "dst": [int(v) for u, v in edges]})
            gc = cugraph.Graph(directed=False)
            gc.from_cudf_edgelist(df, source="src", destination="dst", renumber=True)
            self.G_cu = gc
            self.engine_backend = "cuGraph (GPU)"
            print(f"[ripple] cuGraph built — GPU BFS enabled ({len(edges)} edges)")
        except Exception as e:
            print(f"[ripple] cuGraph build failed ({e}); using networkx CPU")
            self.G_cu = None

    def _build_centrality(self) -> None:
        """Betweenness centrality → the road network's structural chokepoints (junctions
        most shortest-paths funnel through). Heavy graph analytic: cuGraph on GPU, networkx
        k-sample CPU fallback. Computed once and cached (it's a property of the graph)."""
        import bisect
        if CENT_PATH.exists():
            self.centrality = {int(k): v for k, v in json.loads(CENT_PATH.read_text()).items()}
            print(f"[ripple] centrality from cache ({len(self.centrality)} nodes)")
            return
        try:
            n = self.G.number_of_nodes()
            if self.G_cu is not None:
                df = cugraph.betweenness_centrality(self.G_cu, k=min(500, n), normalized=True)
                cent = dict(zip(df["vertex"].to_arrow().to_pylist(),
                                df["betweenness_centrality"].to_arrow().to_pylist()))
                where = "GPU (cuGraph)"
            else:
                cent = nx.betweenness_centrality(self.UG, k=min(150, n), normalized=True)
                where = "CPU (networkx, sampled)"
            vals = sorted(cent.values())
            m = len(vals) or 1
            self.centrality = {int(node): bisect.bisect_left(vals, c) / m for node, c in cent.items()}
            CENT_PATH.write_text(json.dumps({str(k): round(v, 4) for k, v in self.centrality.items()}))
            print(f"[ripple] betweenness centrality computed on {where} ({len(self.centrality)} nodes)")
        except Exception as e:
            print(f"[ripple] centrality failed ({e}) — chokepoint weighting disabled")
            self.centrality = {}

    def _build_lifelines(self) -> None:
        """Rank the network's top chokepoints by how many high-street businesses depend
        on them — combines betweenness + BFS reach + POIs. Proactive insight (which
        junctions to protect), independent of today's disruptions."""
        if not self.centrality or not self.pois:
            self.lifelines = []
            return
        top = sorted(self.centrality, key=self.centrality.get, reverse=True)[:40]
        poi_nodes = [p.get("node") for p in self.pois]
        out = []
        for nd in top:
            reach = self._reach(nd, 6)
            cnt = sum(1 for pn in poi_nodes if pn in reach)
            out.append({"lat": self.G.nodes[nd]["y"], "lon": self.G.nodes[nd]["x"],
                        "businesses": cnt, "centrality": round(self.centrality[nd], 3)})
        out.sort(key=lambda z: -z["businesses"])
        self.lifelines = out[:8]
        print(f"[ripple] lifelines: top chokepoint serves {self.lifelines[0]['businesses'] if self.lifelines else 0} businesses")

    def _load_graph(self) -> None:
        if GRAPH_PATH.exists():
            self.G = ox.load_graphml(GRAPH_PATH)
            print(f"[ripple] graph from cache ({self.G.number_of_nodes()} nodes)")
        else:
            print(f"[ripple] building road graph (r={RADIUS_M}m) — one-time...")
            self.G = ox.graph_from_point((CENTER_LAT, CENTER_LON), dist=RADIUS_M,
                                         network_type="drive")
            ox.save_graphml(self.G, GRAPH_PATH)
        self.UG = self.G.to_undirected()

    def _load_stops(self) -> None:
        if STOPS_PATH.exists():
            self.stops = json.loads(STOPS_PATH.read_text())
            return
        # The tiled grid trips TfL's unauthenticated rate limit; only run it when an
        # app_key is set (500/min). Without one, skip — cascades still work on the
        # road graph; stops/routes light up once a key is provided.
        if not config.TFL_APP_KEY:
            print("[ripple] no TFL_APP_KEY — skipping bus-stop grid (set the key to enable)")
            self.stops = []
            return
        # TfL's StopPoint radius query is capped (~1.5km) AND unauthenticated calls are
        # rate-limited (~50/min), so tile the area with overlapping 1.5km queries spaced
        # 2.5km apart, throttled, and dedupe by stop id.
        step_m = 2500
        dlat = step_m / 111_000.0
        dlon = step_m / (111_000.0 * math.cos(math.radians(CENTER_LAT)))
        span = RADIUS_M // step_m
        seen: dict[str, dict] = {}
        # NOTE: app_key must be IN the URL — passing httpx params= with a query-string
        # URL replaces the query (drops stopTypes/lat/lon → 404).
        keyq = f"&app_key={config.TFL_APP_KEY}" if config.TFL_APP_KEY else ""
        with httpx.Client(timeout=30, headers={"User-Agent": "Ripple/1.0"}) as cl:
            for iy in range(-span, span + 1):
                for ix in range(-span, span + 1):
                    la, lo = CENTER_LAT + iy * dlat, CENTER_LON + ix * dlon
                    url = (f"https://api.tfl.gov.uk/StopPoint?stopTypes=NaptanPublicBusCoachTram"
                           f"&lat={la}&lon={lo}&radius=1500{keyq}")
                    try:
                        resp = cl.get(url)
                        if resp.status_code != 200:   # rate-limited → back off and skip
                            time.sleep(5.0)
                            continue
                        sp = resp.json().get("stopPoints", [])
                    except Exception:
                        continue
                    time.sleep(0.2 if config.TFL_APP_KEY else 1.5)  # fast with a key (500/min)
                    for s in sp:
                        sid = s.get("id") or s.get("naptanId")
                        if sid and sid not in seen and s.get("lat") and s.get("lon"):
                            seen[sid] = {
                                "lat": s["lat"], "lon": s["lon"], "name": s.get("commonName"),
                                "routes": sorted({ln.get("name") for ln in (s.get("lines") or [])
                                                  if ln.get("name")})}
        self.stops = list(seen.values())
        STOPS_PATH.write_text(json.dumps(self.stops))
        print(f"[ripple] fetched {len(self.stops)} bus stops via {(2*span+1)**2}-tile grid")

    def _attach_stops_to_nodes(self) -> None:
        if not self.stops:
            return
        nodes = ox.distance.nearest_nodes(
            self.G, [s["lon"] for s in self.stops], [s["lat"] for s in self.stops])
        for s, n in zip(self.stops, nodes):
            s["node"] = int(n)

    def _load_lsoa(self) -> None:
        """LSOA deprivation decile + population from the London IoD2019 workbook."""
        try:
            import pandas as pd
            if not IMD_PATH.exists():
                r = httpx.get(IMD_URL, timeout=90, headers={"User-Agent": "Mozilla/5.0"},
                              follow_redirects=True)
                IMD_PATH.write_bytes(r.content)
            xl = pd.ExcelFile(IMD_PATH)
            imd = xl.parse("IMD 2019")
            pop = xl.parse("Population figures")
            code_c, name_c = "LSOA code (2011)", "LSOA name (2011)"
            dec_c = next(c for c in imd.columns if "(IMD) Decile" in str(c))
            popc = next(c for c in pop.columns if str(c).startswith("Total population"))
            popmap = dict(zip(pop[code_c], pop[popc]))
            for _, row in imd.iterrows():
                code = row[code_c]
                self.lsoa[code] = {"decile": int(row[dec_c]), "name": str(row[name_c]),
                                   "pop": int(popmap.get(code, 0) or 0)}
            print(f"[ripple] loaded {len(self.lsoa)} LSOAs (decile + population)")
        except Exception as e:
            print(f"[ripple] LSOA load failed ({e}) — equity layer disabled")
            self.lsoa = {}

    def _attach_stops_to_lsoa(self) -> None:
        """Reverse-geocode each stop to its LSOA via postcodes.io (cached on the stop)."""
        if not self.stops or not self.lsoa:
            return
        todo = [s for s in self.stops if "lsoa" not in s]
        if not todo:
            return
        with httpx.Client(timeout=30) as cl:
            for i in range(0, len(todo), 100):
                batch = todo[i:i + 100]
                body = {"geolocations": [{"longitude": s["lon"], "latitude": s["lat"],
                                          "limit": 1, "radius": 2000} for s in batch]}
                try:
                    res = cl.post("https://api.postcodes.io/postcodes", json=body).json().get("result", [])
                except Exception:
                    res = []
                for s, g in zip(batch, res):
                    hits = (g or {}).get("result") or []
                    s["lsoa"] = hits[0]["codes"]["lsoa"] if hits else None
        STOPS_PATH.write_text(json.dumps(self.stops))
        matched = sum(1 for s in self.stops if s.get("lsoa") in self.lsoa)
        print(f"[ripple] attached LSOA to stops ({matched} matched)")

    def _load_pois(self) -> None:
        """High-street businesses (OSM shops + hospitality) → nearest road node + LSOA."""
        if POIS_PATH.exists():
            self.pois = json.loads(POIS_PATH.read_text())
            return
        try:
            tags = {"shop": True,
                    "amenity": ["restaurant", "cafe", "pub", "bar", "fast_food", "bakery"]}
            gdf = ox.features_from_point((CENTER_LAT, CENTER_LON), tags, dist=RADIUS_M)
            pois = []
            for _, row in gdf.iterrows():
                geom = row.get("geometry")
                if geom is None:
                    continue
                c = geom.centroid
                nm = row.get("name")
                pois.append({"lat": float(c.y), "lon": float(c.x),
                             "name": nm if isinstance(nm, str) else None})
            self.pois = pois
        except Exception as e:
            print(f"[ripple] POI load failed ({e}) — high-street layer disabled")
            self.pois = []
            return
        if self.pois:
            nn = ox.distance.nearest_nodes(self.G, [p["lon"] for p in self.pois],
                                           [p["lat"] for p in self.pois])
            for p, n in zip(self.pois, nn):
                p["node"] = int(n)
            stops_with = [s for s in self.stops if s.get("lsoa")]
            if stops_with:
                from scipy.spatial import cKDTree
                tree = cKDTree([(s["lat"], s["lon"]) for s in stops_with])
                _, idx = tree.query([(p["lat"], p["lon"]) for p in self.pois])
                for p, i in zip(self.pois, idx):
                    p["lsoa"] = stops_with[int(i)]["lsoa"]
        POIS_PATH.write_text(json.dumps(self.pois))
        print(f"[ripple] loaded {len(self.pois)} high-street businesses (POIs)")

    # --- the cascade ---------------------------------------------------------
    def nearest_node(self, lat: float, lon: float) -> int:
        return int(ox.distance.nearest_nodes(self.G, lon, lat))

    def _reach(self, src: int, hops: int) -> set:
        """BFS reachable set within `hops` — cuGraph on GPU, networkx CPU fallback."""
        if self.G_cu is not None:
            res = cugraph.bfs(self.G_cu, start=src)
            res = res[res["distance"] <= hops]
            return set(int(v) for v in res["vertex"].to_arrow().to_pylist())
        return set(nx.single_source_shortest_path_length(self.UG, src, cutoff=hops).keys())

    def cascade(self, lat: float, lon: float, hops: int = DEFAULT_HOPS) -> dict:
        """Ripple out from a disruption point; return the impact footprint."""
        if not self.ready:
            return {"error": "engine not ready"}
        src = self.nearest_node(lat, lon)
        reach = self._reach(src, hops)

        affected = [s for s in self.stops if s.get("node") in reach]
        routes = sorted({r for s in affected for r in s["routes"]})
        # affected node coordinates (for drawing the ripple on the map)
        pts = [{"lat": self.G.nodes[n]["y"], "lon": self.G.nodes[n]["x"]} for n in reach]

        # equity: LSOAs served by the affected bus stops → population + deprivation
        lsoa_codes = {s["lsoa"] for s in affected if s.get("lsoa") in self.lsoa}
        population = sum(self.lsoa[c]["pop"] for c in lsoa_codes)
        deprived = [c for c in lsoa_codes if self.lsoa[c]["decile"] <= 2]   # most-deprived 20%
        most_deprived = [{"name": self.lsoa[c]["name"], "decile": self.lsoa[c]["decile"]}
                         for c in sorted(deprived, key=lambda c: self.lsoa[c]["decile"])][:5]

        return {
            "disruption": {"lat": lat, "lon": lon},
            "hops": hops,
            "engine": self.bfs_backend,
            "affected_nodes": len(reach),
            "affected_stops": len(affected),
            "affected_routes": len(routes),
            "routes": routes[:40],
            "est_daily_journeys": int(len(affected) * BOARDINGS_PER_STOP),
            "affected_population": population,
            "affected_lsoas": len(lsoa_codes),
            "deprived_lsoas": len(deprived),
            "most_deprived": most_deprived,
            "stops": [{"lat": s["lat"], "lon": s["lon"], "name": s["name"]} for s in affected],
            "ripple_points": pts,
        }


    def highstreets(self, road_seeds: list[dict], transit_seeds: list[dict] | None = None,
                    hops_base: int = 8) -> dict:
        """City-scale collective view, multi-modal + severity-weighted:
          • road disruptions → full BFS cascade (GPU), radius scaled by severity
          • tube/bus disruptions → mark the affected station/stop node + 1-hop nbrs (local)
        Aggregate severity-weighted access health per LSOA high street, deprivation-weighted.
        This is where the graph BFS + GPU genuinely earn their keep."""
        from collections import defaultdict
        transit_seeds = transit_seeds or []
        if not self.ready or not self.pois:
            return {"areas": [], "ranked": [], "totals": {}, "engine": self.bfs_backend}

        # batch the nearest-node lookups (one KDTree query, not one per seed)
        seeds = [(s, "road") for s in road_seeds if s.get("lat") and s.get("lon")] \
            + [(s, "transit") for s in transit_seeds if s.get("lat") and s.get("lon")]
        node_weight: dict[int, float] = {}
        chokepoints: list[dict] = []
        if seeds:
            nodes = ox.distance.nearest_nodes(self.G, [s["lon"] for s, _ in seeds],
                                              [s["lat"] for s, _ in seeds])
            for (s, kind), n in zip(seeds, nodes):
                w = float(s.get("weight", 0.5))
                if kind == "road":   # network ripple; WIDER on chokepoints (high betweenness)
                    cent = self.centrality.get(int(n), 0.0)
                    hit = self._reach(int(n), max(4, round(hops_base * (0.5 + w) + 5 * cent)))
                    if cent >= 0.9:  # disruption sitting on a top-10% network chokepoint
                        chokepoints.append({"lat": s["lat"], "lon": s["lon"],
                                            "centrality": round(cent, 3), "weight": round(w, 2)})
                else:                # transit: local impairment around the stop/station
                    hit = [int(n), *self.UG.neighbors(int(n))]
                for m in hit:
                    if node_weight.get(m, 0) < w:
                        node_weight[m] = w
            chokepoints.sort(key=lambda x: -x["centrality"])

        agg = defaultdict(lambda: {"total": 0, "affected": 0, "wsum": 0.0, "slat": 0.0, "slon": 0.0})
        for p in self.pois:
            code = p.get("lsoa")
            if code not in self.lsoa:
                continue
            a = agg[code]
            a["total"] += 1; a["slat"] += p["lat"]; a["slon"] += p["lon"]
            w = node_weight.get(p.get("node"), 0)
            if w > 0:
                a["affected"] += 1; a["wsum"] += w
        areas = []
        for code, a in agg.items():
            L = self.lsoa[code]
            areas.append({"code": code, "name": L["name"], "decile": L["decile"], "pop": L["pop"],
                          "lat": a["slat"] / a["total"], "lon": a["slon"] / a["total"],
                          "total": a["total"], "affected": a["affected"],
                          "health": round(100 * (1 - min(1.0, a["wsum"] / a["total"])))})
        ranked = sorted([x for x in areas if x["affected"] > 0],
                        key=lambda x: (x["affected"], -x["decile"]), reverse=True)[:12]
        return {
            "areas": areas,
            "ranked": ranked,
            "chokepoints": chokepoints[:8],
            "lifelines": self.lifelines,
            "totals": {"businesses": sum(x["total"] for x in areas),
                       "affected": sum(x["affected"] for x in areas),
                       "deprived_affected": sum(x["affected"] for x in areas if x["decile"] <= 2),
                       "road_disruptions": len([s for s in road_seeds if s.get("lat")]),
                       "transit_points": len(transit_seeds),
                       "chokepoint_disruptions": len(chokepoints)},
            "engine": self.bfs_backend,
        }


engine = RippleEngine()
