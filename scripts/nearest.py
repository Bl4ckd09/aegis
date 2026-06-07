"""Diagnostic: nearest official disruption to each current incident.

Run on hp15:  .venv/bin/python -m scripts.nearest
"""
import httpx

from backend.disruptions import haversine_m

BASE = "http://localhost:8000"
inc = httpx.get(f"{BASE}/api/incidents").json()
dis = httpx.get(f"{BASE}/api/disruptions").json()
print(f"{len(inc)} incidents vs {len(dis)} located disruptions\n")
for i in inc:
    ranked = sorted(
        (haversine_m(i["lat"], i["lon"], d["lat"], d["lon"]), d) for d in dis
    )
    if not ranked:
        continue
    dist, d = ranked[0]
    name = i["common_name"][:34]
    print(f"  {name:34s} nearest: {dist:6.0f} m  [{d['category']}/{d['sub_category']}] {d['id']}")
