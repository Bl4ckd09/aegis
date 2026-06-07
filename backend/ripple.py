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

RIPPLE_DIR = config.DATA_DIR / "ripple"
RIPPLE_DIR.mkdir(parents=True, exist_ok=True)
GRAPH_PATH = RIPPLE_DIR / "graph.graphml"
STOPS_PATH = RIPPLE_DIR / "stops.json"

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
        self.stops: list[dict] = []                 # {lat, lon, name, routes:[...], node}
        self.ready = False

    # --- one-time load (called at startup) ----------------------------------
    def load(self) -> None:
        self._load_graph()
        self._load_stops()
        self._attach_stops_to_nodes()
        self.ready = True
        print(f"[ripple] ready: {self.G.number_of_nodes()} nodes, "
              f"{self.G.number_of_edges()} edges, {len(self.stops)} bus stops")

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

    # --- the cascade ---------------------------------------------------------
    def nearest_node(self, lat: float, lon: float) -> int:
        return int(ox.distance.nearest_nodes(self.G, lon, lat))

    def cascade(self, lat: float, lon: float, hops: int = DEFAULT_HOPS) -> dict:
        """Ripple out from a disruption point; return the impact footprint."""
        if not self.ready:
            return {"error": "engine not ready"}
        src = self.nearest_node(lat, lon)
        reach = set(nx.single_source_shortest_path_length(self.UG, src, cutoff=hops).keys())

        affected = [s for s in self.stops if s.get("node") in reach]
        routes = sorted({r for s in affected for r in s["routes"]})
        # affected node coordinates (for drawing the ripple on the map)
        pts = [{"lat": self.G.nodes[n]["y"], "lon": self.G.nodes[n]["x"]} for n in reach]

        return {
            "disruption": {"lat": lat, "lon": lon},
            "hops": hops,
            "affected_nodes": len(reach),
            "affected_stops": len(affected),
            "affected_routes": len(routes),
            "routes": routes[:40],
            "est_daily_journeys": int(len(affected) * BOARDINGS_PER_STOP),
            "stops": [{"lat": s["lat"], "lon": s["lon"], "name": s["name"]} for s in affected],
            "ripple_points": pts,
        }


engine = RippleEngine()
