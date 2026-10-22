"""Tests for REAL_AES_FULL loading (T326).

Every test here that needs the connectome is SKIPPED when the parquet is
absent. A skipped test is honest; a test that silently passes against a
synthetic stand-in is the failure mode this repo keeps running into (T320's
CUDA backend, T324's decorative edges).

The tests that always run — the id mapping, the parameter table, the checkout
resolution — are the ones where the bugs actually were.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from lib.epistemic.flybrainpoc import real_connectome as rc

CHECKOUT_ENV = "AES_FLYBRAIN_PATH"


def _checkout():
    try:
        return rc.resolve_checkout(Path("eonsystemspbc/fly-brain"))
    except FileNotFoundError:
        return None


def _data_usable():
    """Can THIS interpreter actually read the data, not merely find it?

    T328: this guard used to ask only whether the parquet file existed. Once
    the connectome became durable at /opt/fly-brain, a machine whose
    `python3` lacks pyarrow had the file present, the guard passed, and every
    test below died with `ModuleNotFoundError: No module named 'pyarrow'`.

    Same mistake as the rest of this ticket: the condition asked was not the
    condition that mattered. Presence of a file is not the capability to read
    it. The PoC runs under two interpreters here — the system `python3` that
    `make test-check` uses, and the project venv — and only one can open a
    parquet.
    """
    if _checkout() is None:
        return False
    try:
        import pyarrow.parquet  # noqa: F401
    except ImportError:
        return False
    return True


CHECKOUT = _checkout()
needs_data = pytest.mark.skipif(
    not _data_usable(),
    reason=(
        "FlyWire data not readable here — either the parquet is absent "
        "(set AES_FLYBRAIN_PATH, see T325) or this interpreter lacks pyarrow"
    ),
)


class TestCheckoutResolution:
    def test_missing_parquet_raises_with_actionable_message(self):
        """A missing data file must say where to get it, not just fail."""
        if CHECKOUT is not None:
            pytest.skip("parquet present; the missing-data path is untestable here")
        with pytest.raises(FileNotFoundError) as e:
            rc.resolve_checkout(Path("/nonexistent/nowhere"))
        msg = str(e.value)
        assert "fly-brain" in msg, "must name the repository to clone"
        assert "AES_FLYBRAIN_PATH" in msg, "must name the env override"


class TestIdMapping:
    """The mapping is POSITIONAL, and getting that wrong broke every lookup.

    An earlier version read the completeness CSV's second column as the index.
    That column is a `Completed` boolean; the parquet is keyed by row
    position. The failure was a KeyError on 21 of 21 IDs.
    """

    @staticmethod
    def _csv_fixture(tmp_path, body):
        """The reader looks under <checkout>/data/, not <checkout>/."""
        d = tmp_path / rc.COMPLETENESS_RELPATH.parent
        d.mkdir(parents=True, exist_ok=True)
        (d / rc.COMPLETENESS_RELPATH.name).write_text(body)
        return tmp_path

    def test_flyid_maps_to_row_position_not_column_value(self, tmp_path):
        co = self._csv_fixture(tmp_path, ",Completed\n111,True\n222,True\n333,False\n")
        assert rc.flyid_to_index(co, [111, 222, 333]) == [0, 1, 2]

    def test_missing_id_raises_rather_than_defaulting(self, tmp_path):
        co = self._csv_fixture(tmp_path, ",Completed\n111,True\n")
        with pytest.raises(KeyError) as e:
            rc.flyid_to_index(co, [999])
        assert "999" in str(e.value)


class TestLIFParameters:
    """Taken from fly-brain's params dict, not invented here."""

    def test_parameters_match_the_reference(self):
        # code/run_brian2_cuda.py
        assert rc.REAL_LIF_PARAMS["v_0"] == -52e-3
        assert rc.REAL_LIF_PARAMS["v_rst"] == -52e-3
        assert rc.REAL_LIF_PARAMS["v_th"] == -45e-3
        assert rc.REAL_LIF_PARAMS["t_mbr"] == 20e-3
        assert rc.REAL_LIF_PARAMS["tau"] == 5e-3
        assert rc.REAL_LIF_PARAMS["t_rfc"] == 2.2e-3
        assert rc.REAL_LIF_PARAMS["t_dly"] == 1.8e-3
        assert rc.REAL_LIF_PARAMS["w_syn"] == 0.275e-3
        assert rc.REAL_LIF_PARAMS["f_poi"] == 250

    def test_equations_declare_the_constants_they_reference(self):
        # The threshold/reset strings say `v > v_th` and `v = v_rst`, so those
        # names must exist as state variables or brian2 raises on assignment.
        for name in ("v_0", "v_rst", "v_th", "t_mbr", "tau"):
            assert name in rc.REAL_EQS, f"{name} is referenced but not declared"

    def test_default_experiment_is_the_sugar_set(self):
        # code/benchmark.py 'sugar': 21 sugar GRNs at 200 Hz.
        assert len(rc.DEFAULT_EXPERIMENT_FLYIDS) == 21
        assert rc.DEFAULT_STIM_RATE_HZ == 200.0


@needs_data
class TestRealConnectome:
    def test_loads_the_real_graph(self):
        pre, post, w, n = rc.load_connectome(CHECKOUT)
        assert n == 138639, "FlyWire v783 neuron count"
        assert len(pre) == 15091983, "real synapse count (T325: NOT ~5M)"
        assert len(pre) == len(post) == len(w)
        assert pre.max() < n and post.max() < n

    def test_weights_are_signed_and_non_trivial(self):
        """40% of the real synapses are INHIBITORY (T326).

        A test asserting `w.min() > 0` was wrong and the data corrected it:
        `Excitatory x Connectivity` ranges -2405 .. 1897. T325's probe clamped
        negatives to a positive floor and so measured an excitatory-only
        network — the cost figure holds, the dynamics did not. This test now
        pins the sign structure so the clamp cannot come back unnoticed.
        """
        _, _, w, _ = rc.load_connectome(CHECKOUT)
        assert w.min() < 0, "inhibitory weights must be negative, not clamped away"
        assert w.max() > 1.0, "real weights span a range; all-equal means a stub"
        frac_inh = float((w < 0).mean())
        assert 0.3 < frac_inh < 0.5, f"expected ~40% inhibitory, got {frac_inh:.2f}"

    @pytest.mark.slow
    def test_builds_and_runs(self):
        import brian2 as b2

        net = rc.build_full_network(CHECKOUT)
        assert net.n_neurons == 138639
        assert net.n_synapses == 15091983
        assert net.n_input_neurons == 21
        # REAL has Poisson drive, not a spike generator: inject() cannot feed it.
        assert net.has_injection_input is False
        net.run(2 * b2.ms, report=None)
        mon = list(net.pools.values())[0]
        assert len(mon.t) > 0, "the real network must actually spike"

    def test_simulation_does_not_raise(self):
        """A 5 ms window is drive-only. It must spike, and that is all it shows.

        T328: this asserted `> 100 spikes in 5 ms`. That threshold was
        calibrated against the BUGGY drive of T327, which fired ~66x too
        much, and it never could have tested what its docstring claimed. At
        200 Hz the 21 driven neurons receive about ONE Poisson spike each in
        the first 5 ms, and the 1.8 ms synaptic delay plus the membrane
        timescale mean no recurrent propagation has happened yet. Measured:
        16 spikes at 5 ms, converging to ~16,858/s by 500 ms.

        So a 5 ms window can only show the drive reached the network. Whether
        the edges are decorative is a different question, asked properly in
        test_recurrent_edges_recruit_beyond_the_driven_set below.
        """
        import brian2 as b2

        net = rc.build_full_network(CHECKOUT)
        net.run(5 * b2.ms, report=None)
        mon = list(net.pools.values())[0]
        total = len(mon.t)
        # ~21 driven neurons x ~1 Poisson spike each in 5 ms at 200 Hz.
        assert 5 <= total <= 60, (
            f"{total} spikes in 5 ms; expected the ~21 drive spikes, got a "
            f"number that means the drive is wrong in a new way"
        )

    @pytest.mark.slow
    def test_recurrent_edges_recruit_beyond_the_driven_set(self):
        """The real test that the 15M edges are not decorative (T328).

        If the recurrent edges did nothing, the only neurons that could ever
        spike are the 21 driven ones. The reference's published run reaches
        388 active neurons at t_run=1.0s (T327). So: run long enough for
        propagation and assert the active population EXCEEDS the driven set.
        That is a direct measurement of the requirement, not a magic spike
        count, and it fails if the connectivity breaks in either direction.
        """
        import brian2 as b2
        import numpy as np

        net = rc.build_full_network(CHECKOUT)
        net.run(0.2 * b2.second, report=None)
        mon = list(net.pools.values())[0]
        active = set(np.unique(mon.i).tolist())
        driven = set(net.drive_indices.tolist())

        assert len(active) > len(driven), (
            f"only {len(active)} active neurons, all within the {len(driven)} "
            f"driven: the recurrent edges are decorative"
        )
        recruited = active - driven
        assert len(recruited) > 50, (
            f"only {len(recruited)} neurons recruited beyond the drive; "
            f"expected the published ~388 active at 1.0s"
        )


@needs_data
@pytest.mark.slow
class TestAgainstPublishedReference:
    """Compare against fly-brain's OWN published output, not against plausibility.

    T326's loader passed 30 quality gates while driving the wrong 20 neurons:
    `PoissonInput(N=len(drive_idx))` drives the FIRST N neurons of a group, not
    the scattered indices of the 21 sugar GRNs. It ran, it spiked, and it was
    wrong. Only a comparison with the world catches that — the gates cannot,
    because they test the code against itself.

    Comparison notes, both learned the hard way:
      * Compare against the `n_run=1` row. The mean over n_run=1..32 is ~10x
        higher because multi-run rows ACCUMULATE spikes; comparing to the mean
        makes a correct implementation look 10x wrong.
      * Compare against the `Brian2 (CPU)` rows, not GeNN/PyTorch. In the
        reference's own data the GPU backends produce ~10x more spikes than
        brian2 on the same network — a real divergence, and not the
        configuration this loader reproduces.
    """

    @staticmethod
    def _reference_rows(checkout):
        import pandas as pd

        f = checkout / "data" / "benchmark-results.csv"
        if not f.exists():
            return None
        df = pd.read_csv(f)
        return df[
            (df.status == "success")
            & (df.experiment_key == "sugar")
            & (df.framework == "Brian2 (CPU)")
            & (df.t_run == 1.0)
            & (df.n_run == 1)
            & (df.run_label == "nature_2026_07")
        ]

    def test_matches_published_spike_count_and_active_neurons(self):
        import brian2 as b2
        import numpy as np

        ref = self._reference_rows(CHECKOUT)
        if ref is None or ref.empty:
            pytest.skip("benchmark-results.csv absent or has no comparable row")

        expected_spikes = float(ref.spikes.iloc[0])
        expected_active = float(ref.active_neurons.iloc[0])
        assert expected_spikes > 0, "reference row must have activity to compare against"

        net = rc.build_full_network(CHECKOUT)
        net.run(1.0 * b2.second, report=None)
        mon = list(net.pools.values())[0]
        spikes = len(mon.t)
        active = len(np.unique(mon.i))

        assert 0.5 <= spikes / expected_spikes <= 2.0, (
            f"spikes {spikes} vs published {expected_spikes:.0f} "
            f"({spikes / expected_spikes:.3f}x) — drive, weights or index "
            f"mapping has drifted"
        )
        assert 0.8 <= active / expected_active <= 1.25, (
            f"active_neurons {active} vs published {expected_active:.0f} "
            f"({active / expected_active:.3f}x)"
        )
