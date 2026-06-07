"""Unit tests for the per-query BFS backend routing (CPU vs GPU).

At the current graph size (~22k nodes) a cuGraph kernel launch + device->host
transfer (~27 ms) is far slower than networkx with an early cutoff (~0.1 ms), so
per-query BFS should route to CPU; GPU is reserved for the one-time betweenness
build and only used for per-query BFS on very large graphs. See PERFORMANCE.md.
"""
import networkx as nx
import pytest

from backend import ripple as R
from backend import config


class _FakeG:
    def __init__(self, n):
        self._n = n

    def number_of_nodes(self):
        return self._n


def _engine(n_nodes, gpu_built):
    e = R.RippleEngine()
    e.G = _FakeG(n_nodes)
    e.G_cu = object() if gpu_built else None  # sentinel for "cuGraph graph present"
    return e


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr(config, "RIPPLE_BFS_BACKEND", "auto", raising=False)
    monkeypatch.setattr(config, "RIPPLE_GPU_BFS_MIN_NODES", 200_000, raising=False)
    return config


def test_auto_small_graph_routes_cpu_and_frees_gpu(cfg):
    e = _engine(21_908, gpu_built=True)
    e._select_bfs_backend()
    assert e.G_cu is None                 # GPU graph released -> _reach uses CPU
    assert "CPU" in e.bfs_backend


def test_auto_large_graph_keeps_gpu(cfg):
    e = _engine(500_000, gpu_built=True)
    e._select_bfs_backend()
    assert e.G_cu is not None
    assert "GPU" in e.bfs_backend


def test_force_cpu_overrides_large_graph(monkeypatch, cfg):
    monkeypatch.setattr(config, "RIPPLE_BFS_BACKEND", "cpu", raising=False)
    e = _engine(500_000, gpu_built=True)
    e._select_bfs_backend()
    assert e.G_cu is None
    assert "CPU" in e.bfs_backend


def test_force_gpu_overrides_small_graph(monkeypatch, cfg):
    monkeypatch.setattr(config, "RIPPLE_BFS_BACKEND", "gpu", raising=False)
    e = _engine(100, gpu_built=True)
    e._select_bfs_backend()
    assert e.G_cu is not None
    assert "GPU" in e.bfs_backend


def test_no_gpu_available_is_cpu(cfg):
    e = _engine(500_000, gpu_built=False)
    e._select_bfs_backend()
    assert e.G_cu is None
    assert "CPU" in e.bfs_backend


def test_reach_cpu_correct():
    """The CPU path returns the correct hop-bounded reachable set."""
    e = R.RippleEngine()
    e.UG = nx.path_graph(6)   # 0-1-2-3-4-5
    e.G_cu = None
    assert e._reach(0, 2) == {0, 1, 2}
    assert e._reach(0, 10) == {0, 1, 2, 3, 4, 5}
    assert e._reach(3, 1) == {2, 3, 4}
