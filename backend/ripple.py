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
        self.G_cu = None                            # cuGraph graph (GPU BFS) when available
        self.engine_backend = "networkx (CPU)"
        self.ready = False

    # --- one-time load (called at startup) ----------------------------------
    def load(self) -> None:
        self._load_graph()
        self._load_stops()
        self._attach_stops_to_nodes()
        self._load_lsoa()
        self._attach_stops_to_lsoa()
        self._build_cugraph()
        self.ready = True
        print(f"[ripple] ready: {self.G.number_of_nodes()} nodes, "
              f"{self.G.number_of_edges()} edges, {len(self.stops)} stops, "
              f"{len(self.lsoa)} LSOAs | BFS backend: {self.engine_backend}")

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

    # --- the cascade ---------------------------------------------------------
    def nearest_node(self, lat: float, lon: float) -> int:
        return int(ox.distance.nearest_nodes(self.G, lon, lat))

    def cascade(self, lat: float, lon: float, hops: int = DEFAULT_HOPS) -> dict:
        """Ripple out from a disruption point; return the impact footprint."""
        if not self.ready:
            return {"error": "engine not ready"}
        src = self.nearest_node(lat, lon)
        if self.G_cu is not None:  # GPU BFS via cuGraph
            res = cugraph.bfs(self.G_cu, start=src)
            res = res[res["distance"] <= hops]
            reach = set(int(v) for v in res["vertex"].to_arrow().to_pylist())
        else:                      # CPU BFS via networkx
            reach = set(nx.single_source_shortest_path_length(self.UG, src, cutoff=hops).keys())

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
            "engine": self.engine_backend,
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


engine = RippleEngine()
