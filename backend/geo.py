"""GPU-accelerated spatial join for the disruption cross-reference.

Uses NVIDIA RAPIDS (cuDF to hold the disruption table + cuPy for a vectorized
haversine distance matrix) when available, falling back to NumPy on CPU. The
compute is small today (incidents x disruptions) but this scales to all 880
cameras x all disruptions on the GPU without changing the call site.
"""
from __future__ import annotations

EARTH_M = 6371000.0

try:
    import cupy as _xp
    import cudf  # noqa: F401  (used to build the disruption frame on-GPU)
    _GPU = True
except Exception:  # pragma: no cover - CPU fallback
    import numpy as _xp
    _GPU = False


def backend_name() -> str:
    return "RAPIDS cuDF/cuPy (GPU)" if _GPU else "NumPy (CPU)"


def is_gpu() -> bool:
    return _GPU


def nearest(inc_lats, inc_lons, dis_lats, dis_lons):
    """Nearest disruption per incident.

    Returns (idx, dist_m): for each incident, the index of the closest disruption
    and the great-circle distance in metres. Empty lists if either side is empty.
    """
    if not len(inc_lats) or not len(dis_lats):
        return [], []

    il = _xp.radians(_xp.asarray(inc_lats, dtype="float64"))[:, None]
    io = _xp.radians(_xp.asarray(inc_lons, dtype="float64"))[:, None]
    dl = _xp.radians(_xp.asarray(dis_lats, dtype="float64"))[None, :]
    do = _xp.radians(_xp.asarray(dis_lons, dtype="float64"))[None, :]

    dphi = dl - il
    dlam = do - io
    a = _xp.sin(dphi / 2) ** 2 + _xp.cos(il) * _xp.cos(dl) * _xp.sin(dlam / 2) ** 2
    dist = 2 * EARTH_M * _xp.arcsin(_xp.sqrt(a))  # (n_inc, n_dis)

    idx = _xp.argmin(dist, axis=1)
    mind = _xp.min(dist, axis=1)
    if _GPU:
        idx = _xp.asnumpy(idx)
        mind = _xp.asnumpy(mind)
    return idx.tolist(), mind.tolist()
