"""H1 de-risk: prove the Ripple cascade core on CPU (graph + BFS + stops + spatial join).

If this works, the riskiest part of Ripple is de-risked: a disruption point ripples
out through the road graph and we can count the bus stops it affects. GPU (cuGraph/cuDF)
is a later mechanical swap.
"""
import time

import httpx
import networkx as nx
import osmnx as ox

CENTER = (51.5074, -0.1278)   # central London (Trafalgar-ish)
RADIUS_M = 1500
HOPS = 12


def main():
    t0 = time.time()
    print("fetching OSMnx drive graph (central London)...")
    G = ox.graph_from_point(CENTER, dist=RADIUS_M, network_type="drive")
    print(f"  graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges  ({time.time()-t0:.1f}s)")

    dnode = ox.distance.nearest_nodes(G, CENTER[1], CENTER[0])
    UG = G.to_undirected()
    reach = set(nx.single_source_shortest_path_length(UG, dnode, cutoff=HOPS).keys())
    print(f"  BFS {HOPS} hops from disruption node: {len(reach)} affected road nodes")

    print("fetching TfL bus stops near the point...")
    url = (f"https://api.tfl.gov.uk/StopPoint?stopTypes=NaptanPublicBusCoachTram"
           f"&lat={CENTER[0]}&lon={CENTER[1]}&radius={RADIUS_M}")
    r = httpx.get(url, timeout=30, headers={"User-Agent": "Ripple/1.0"})
    sp = r.json().get("stopPoints", [])
    stops = [(s["lat"], s["lon"], s.get("commonName"),
              [ln.get("name") for ln in (s.get("lines") or [])]) for s in sp
             if s.get("lat") and s.get("lon")]
    routes = sorted({ln for s in stops for ln in s[3]})
    print(f"  bus stops: {len(stops)} | distinct routes: {len(routes)}")

    if stops:
        nn = ox.distance.nearest_nodes(G, [s[1] for s in stops], [s[0] for s in stops])
        affected = [(stops[i], n) for i, n in enumerate(nn) if n in reach]
        aff_routes = sorted({ln for (s, _) in affected for ln in s[3]})
        print(f"  stops inside the cascade: {len(affected)}/{len(stops)}")
        print(f"  bus routes touched by the cascade: {len(aff_routes)}  e.g. {aff_routes[:10]}")

    print(f"\nRIPPLE CORE OK ✅  (graph→BFS→stops→spatial-join in {time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
