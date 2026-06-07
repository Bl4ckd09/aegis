"""Ripple cascade engine on a Modal RAPIDS GPU (cuGraph + cuDF).

Runs the SAME backend/ripple.py engine as hp-15 will — here on a cloud L4 with
RAPIDS so cuGraph BFS executes on the GPU. The Aegis backend proxies /api/cascade
to this endpoint (set AEGIS_RIPPLE_URL). On the DGX Spark you instead run the
engine locally (cuGraph installed there) — no Modal needed; identical code.

Deploy:   modal deploy modal_ripple.py
Endpoints (per workspace):
  POST https://<ws>--aegis-ripple-ripple-cascade.modal.run   {lat,lon,hops}
  GET  https://<ws>--aegis-ripple-ripple-status.modal.run
"""
import modal

# CUDA 12 base + RAPIDS (cudf/cugraph) + the Ripple engine's deps. Same code as hp-15.
image = (
    modal.Image.from_registry("nvidia/cuda:12.5.1-runtime-ubuntu22.04", add_python="3.12")
    .pip_install("cudf-cu12", "cugraph-cu12", extra_index_url="https://pypi.nvidia.com")
    .pip_install("osmnx", "networkx", "pandas", "scikit-learn", "openpyxl",
                 "httpx", "fastapi", "uvicorn", "pydantic")
    .add_local_dir("backend", remote_path="/root/backend")  # the identical ripple engine
)

app = modal.App("aegis-ripple")
vol = modal.Volume.from_name("aegis-ripple-data", create_if_missing=True)  # graph/stops/imd cache


@app.cls(
    image=image,
    gpu="L4",                       # cheap GPU; cuGraph/cuDF run here
    volumes={"/root/data": vol},
    secrets=[modal.Secret.from_dict({"TFL_APP_KEY": "27a7ec2b298549a98f5a3d0e07b344ce"})],
    scaledown_window=600,
    timeout=3600,
    min_containers=0,
)
class Ripple:
    @modal.enter()
    def boot(self):
        import sys
        sys.path.insert(0, "/root")
        from backend.ripple import engine, _HAS_CUGRAPH
        print(f"[modal_ripple] RAPIDS cuGraph available: {_HAS_CUGRAPH}")
        self.engine = engine
        self.engine.load()  # builds/loads graph + stops + IMD (cached to the Volume)

    @modal.fastapi_endpoint(method="POST")
    def cascade(self, data: dict):
        return self.engine.cascade(data["lat"], data["lon"], data.get("hops", 15))

    @modal.fastapi_endpoint(method="GET")
    def status(self):
        e = self.engine
        return {"ready": e.ready, "backend": e.engine_backend,
                "nodes": e.G.number_of_nodes() if e.G else 0, "stops": len(e.stops)}
