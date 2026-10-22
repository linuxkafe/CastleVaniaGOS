"""test_reservoir.py — integration tests for the Brian2 LIF reservoir (T-4).

These tests exercise the TRIVIAL_UNIT model (deterministic, fast). The
REAL_AES_FULL connectome path is opt-in and benchmarked on a CUDA box
(T-8 in RFC-002) — never part of the default test suite.
"""

import numpy as np
import pytest

brian2 = pytest.importorskip("brian2")

from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir, READOUT_POOLS, is_available  # noqa: E402


def _noop_trains():
    return {1: np.array([0.0, 10.0, 20.0]), 2: np.array([5.0, 15.0])}


class TestLoad:
    def test_brian2_importable(self):
        assert is_available()

    def test_brian2_loads_without_crash(self):
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.load()
        assert r._loaded
        assert r.n_input_neurons == 128

    def test_cold_start_ms_positive(self):
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.load()
        assert r.cold_start_ms > 0.0

    def test_load_is_idempotent(self):
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.load()
        first = r.cold_start_ms
        r.load()  # no rebuild
        assert r._loaded
        assert r.cold_start_ms == first


class TestSimulate:
    def test_simulate_returns_nonempty(self):
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.inject(_noop_trains())
        out = r.simulate(duration_ms=200.0)
        assert set(out.keys()) == set(READOUT_POOLS.keys())
        for pool, counts in out.items():
            assert counts.shape == (READOUT_POOLS[pool], 20)

    def test_simulate_shape_matches_bins(self):
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.inject(_noop_trains())
        out = r.simulate(duration_ms=400.0)
        mbon = out["mbons"]
        assert mbon.shape == (READOUT_POOLS["mbons"], 40)

    def test_unloaded_inject_loads_first(self):
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.inject(_noop_trains())
        assert r._loaded

    def test_real_full_fallbacks_gracefully(self, monkeypatch):
        """When the connectome is ABSENT, warn and fall back instead of raising.

        T328: this test used to *assume* the connectome was absent — its
        docstring said "not loadable without the flybrain checkout" and it
        simply called load(). It passed for months, but it was not testing
        the fallback; it was testing the state of whichever machine ran it.
        On a host that has the FlyWire parquet (this one, since T327 moved it
        to /opt/fly-brain), REAL_AES_FULL is genuinely available, no fallback
        occurs, and the test failed on `0 == 1` warnings.

        A test whose result depends on whether optional data happens to be
        installed is a test that will lie in both directions. The failure is
        now FORCED, so the assertion is about the fallback logic and nothing
        else.
        """
        from lib.epistemic.flybrainpoc.backends import CPUBackend

        def _no_data(self, connectome_path):
            raise FileNotFoundError("forced: no FlyWire parquet on this host")

        monkeypatch.setattr(CPUBackend, "build_full", _no_data)

        r = FlyBrainReservoir(model="REAL_AES_FULL")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r.load()
            # Filter for our specific fallback warning
            fallback_warnings = [x for x in w if "REAL_AES_FULL not available" in str(x.message)]
            assert len(fallback_warnings) == 1
            assert "Falling back to TRIVIAL_UNIT" in str(fallback_warnings[0].message)
        assert r._loaded
        assert r.model == "TRIVIAL_UNIT"