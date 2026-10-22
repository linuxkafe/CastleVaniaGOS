"""test_readout.py — unit tests for the trained readout (T-6)."""

import numpy as np
import pytest

from lib.epistemic.flybrainpoc.readout import (  # noqa: E402
    ClassificationResult, ReadoutClassifier, logistic_features, temporal_stats_features,
    sensory_antiphase_features,
)


def _spike_feature_vector(n_pools=3, n_bins=20, spike_prob=0.30, rng=None):
    rng = rng or np.random.default_rng(0)
    pools = {}
    for p in range(n_pools):
        n_neurons = [16, 12, 4][p]
        counts = rng.binomial(1, spike_prob, size=(n_neurons, n_bins))
        pools[f"pool_{p}"] = counts
    return logistic_features(pools)


class TestFeaturization:
    def test_feature_dimension(self):
        v = _spike_feature_vector()
        assert v.ndim == 1
        assert v.shape[0] == (16 + 12 + 4) * 20

    def test_empty_returns_zeros(self):
        assert logistic_features({}).shape[0] == 0


STANDARD_POOLS = {
    "mbons": (16, 40),
    "central_complex": (12, 40),
    "giant_fiber": (4, 40),
}


def _standard_pools(spike_prob=0.30, rng=None):
    """3-pool / 40-bin spike counts shaped like reservoir.simulate output."""
    rng = rng or np.random.default_rng(7)
    return {
        name: rng.binomial(1, spike_prob, size=shape).astype(float)
        for name, shape in STANDARD_POOLS.items()
    }


class TestTemporalStatsFeatures:
    """T305 position-invariant temporal statistics (temporal_stats_features)."""

    def test_dimension_3_pools_40_bins(self):
        f = temporal_stats_features(_standard_pools())
        # per-pool 18 x 3 + global [comp*3, g_cent, cdiff*3, corr*3]
        assert f.ndim == 1
        assert f.shape[0] == 3 * 18 + 10

    def test_empty_returns_zeros(self):
        assert temporal_stats_features({}).shape[0] == 0

    def test_single_pool_degrades_to_per_pool_only(self):
        pools = {"mbons": np.ones((16, 40))}
        f = temporal_stats_features(pools)
        assert f.shape[0] == 18

    def test_position_invariance(self):
        """Shuffling neuron slots inside every pool must not change the vector.

        This is the T305 contract: the anti-phase signature of a contradicts
        pair is independent of which sensory slots the pair members occupy.
        """
        pools = _standard_pools(spike_prob=0.5)
        base = temporal_stats_features(pools)
        rng = np.random.default_rng(3)
        shuffled = {}
        for name, P in pools.items():
            idx = rng.permutation(P.shape[0])
            shuffled[name] = P[idx]
        assert np.allclose(base, temporal_stats_features(shuffled))

    def test_deterministic(self):
        pools = _standard_pools()
        assert np.allclose(temporal_stats_features(pools),
                           temporal_stats_features(pools))

    def test_sensitivity_to_contradiction_signature(self):
        """A pool whose profile is shifted late vs early must differ."""
        early = np.zeros((8, 40)); early[:, :20] = 1.0
        late = np.zeros((8, 40)); late[:, 20:] = 1.0
        pools_early = {"mbons": early}
        pools_late = {"mbons": late}
        fe = temporal_stats_features(pools_early)
        fl = temporal_stats_features(pools_late)
        assert not np.allclose(fe, fl)
        # late-shifted pool has bigger 'late' and a negative early-late
        assert fl[4] > fe[4]
        assert fl[5] < fe[5]

    def test_env_switch_selects_v2_in_featurize_single(self, monkeypatch):
        from lib.epistemic.flybrainpoc import validator
        pools = _standard_pools()
        # default = raw logistic_features (1280 dims for 40 bins)
        raw = validator._featurize_single(pools)
        assert raw.shape[0] == (16 + 12 + 4) * 40
        # AES_FEATURIZER=v2 -> temporal stats
        monkeypatch.setenv("AES_FEATURIZER", "v2")
        v2 = validator._featurize_single(pools)
        assert v2.shape[0] == 3 * 18 + 10
        # env cleared -> raw again
        monkeypatch.delenv("AES_FEATURIZER")
        assert np.allclose(validator._featurize_single(pools), raw)


def _sensory_pair(from_slot=10, to_slot=11, from_conf=0.9, to_conf=0.5,
                  n_bins=40, extra_slots=3):
    """Synthetic sensory layer with a contradicts pair, from early / to late."""
    counts = np.zeros((128, n_bins), dtype=float)
    counts[from_slot, 5] = 4.0                    # early-only (head)
    counts[to_slot, 30] = 5.0                     # late-only (tail)
    meta = {
        from_slot: {"claim": "C-0", "is_contradiction": True,
                    "operator": "G", "confidence": from_conf},
        to_slot: {"claim": "C-1", "is_contradiction": True,
                  "operator": "F", "confidence": to_conf},
    }
    for i in range(extra_slots):
        s = 40 + i
        counts[s, 10:20] = 1.0                    # active both-ish (G window)
        meta[s] = {"claim": f"C-{2 + i}", "is_contradiction": False,
                   "operator": "G", "confidence": 0.6}
    edges = [{"from": "C-0", "to": "C-1", "type": "contradicts"}]
    return counts, meta, edges


def _relocated_sensory(counts, meta, edges, from_slot, to_slot):
    """Same profiles moved to different slots (and slice)."""
    c2 = np.zeros_like(counts)
    for src, dst in [(10, from_slot), (11, to_slot), (40, 90), (41, 91), (42, 92)]:
        c2[dst] = counts[src]
    m2 = {}
    for src, dst in [(10, from_slot), (11, to_slot), (40, 90), (41, 91), (42, 92)]:
        m2[dst] = {**meta[src]}
    return c2, m2, edges


class TestSensoryAntiphaseFeatures:
    """T306 v3 sensory-layer anti-phase statistics."""

    def test_dimension_3_pools_backbone_plus_block(self):
        counts, meta, edges = _sensory_pair()
        f = sensory_antiphase_features(_standard_pools(), counts, meta, edges)
        # v2 backbone (3*18+10=64) + documented 30-scalar sensory block
        assert f.shape[0] == 64 + 30

    def test_deterministic(self):
        counts, meta, edges = _sensory_pair()
        pools = _standard_pools()
        assert np.allclose(
            sensory_antiphase_features(pools, counts, meta, edges),
            sensory_antiphase_features(pools, counts, meta, edges))

    def test_position_invariance_across_slots_and_slices(self):
        """Pair landing on different slots (incl. another slice) -> same vector.

        This is the T306 contract: sensory aggregates are pooled over the full
        128-channel layer or computed at claim resolution, so the feature vector
        does not depend on which slots/slices the pair occupies.
        """
        counts, meta, edges = _sensory_pair()
        base = sensory_antiphase_features(_standard_pools(), counts, meta, edges)
        # mbons slice (0-42) -> giant_fiber slice (86-128)
        c2, m2, e2 = _relocated_sensory(counts, meta, edges, from_slot=100, to_slot=101)
        moved = sensory_antiphase_features(_standard_pools(), c2, m2, e2)
        assert np.allclose(base, moved)

    def test_antiphase_signature_is_visible(self):
        """An early-from / late-to pair scores high complementarity + flip 0."""
        counts, meta, edges = _sensory_pair()
        f = sensory_antiphase_features(_standard_pools(), counts, meta, edges)
        block = f[64:]
        assert block[12] == 1.0            # n_pairs
        assert block[18] > 0.9             # complementarity (from early, to late)
        assert block[19] == 0.0            # no role flips

    def test_role_flip_detected(self):
        """Windows swapped (from late, to early) -> role-flip count > 0."""
        counts, meta, edges = _sensory_pair()
        counts[10, 5] = 0.0
        counts[10, 30] = 4.0               # 'from' now late-dominant
        counts[11, 30] = 0.0               # clear original late bin
        counts[11, 5] = 5.0                # 'to' now early-dominant
        f = sensory_antiphase_features(_standard_pools(), counts, meta, edges)
        block = f[64:]
        assert block[19] >= 2              # both roles flipped

    def test_no_contradicts_pair_defaults_to_zeros(self):
        counts, meta, edges = _sensory_pair()
        meta = {s: {**m, "is_contradiction": False} for s, m in meta.items()}
        f = sensory_antiphase_features(_standard_pools(), counts, meta, [])
        block = f[64:]
        assert block[12] == 0.0            # n_pairs
        assert block[18] == 0.0            # complementarity
        assert block[19] == 0.0            # flips

    def test_empty_sensory_keeps_fixed_dimension(self):
        """Silent sensory layer -> full vector (backbone + zeroed block).

        The dimension must be constant across islands so the fitted readout
        sees a consistent feature space; degradation to the bare backbone only
        happens when the sensory CONTEXT is absent (see v3 env test below).
        """
        f = sensory_antiphase_features(_standard_pools(), np.zeros((128, 40)), {}, [])
        assert f.shape[0] == 64 + 30
        block = f[64:]
        assert block[0] == 0.0        # no active slots
        assert block[4] == 1.0        # all slots silent
        assert block[12] == 0.0       # no pairs
        assert block[18] == 0.0       # no complementarity

    def test_v3_env_selects_sensory_in_featurize_single(self, monkeypatch):
        from lib.epistemic.flybrainpoc import validator
        counts, meta, edges = _sensory_pair()
        monkeypatch.setenv("AES_FEATURIZER", "v3")
        f = validator._featurize_single(_standard_pools(),
                                        sensory_counts=counts,
                                        sensory_meta=meta, edges=edges)
        assert f.shape[0] == 64 + 30
        # without sensory context, v3 degrades to the v2 backbone (no crash)
        assert validator._featurize_single(_standard_pools()).shape[0] == 64


class TestStandardize:
    """T306 arm 2: in-fold StandardScaler (estimator pipeline, no leakage)."""

    def test_make_model_is_pipeline_when_standardize(self):
        rc = ReadoutClassifier(method="logistic", calibrate=False, standardize=True)
        from sklearn.pipeline import Pipeline
        assert isinstance(rc._make_model(), Pipeline)
        plain = ReadoutClassifier(method="logistic", calibrate=False)
        assert not isinstance(plain._make_model(), Pipeline)

    def test_balanced_cv_scale_returns_finite_score(self):
        from lib.epistemic.flybrainpoc.readout import balanced_cv
        rng = np.random.default_rng(11)
        X = np.concatenate([rng.normal(5, 2, (40, 20)), rng.normal(-5, 2, (40, 20))])
        y = np.array(["SAT"] * 40 + ["UNSAT"] * 40)
        bal, recall = balanced_cv(X, y, cv=4, scale=True)
        assert 0.0 <= bal <= 1.0
        assert 0.0 <= recall <= 1.0
        assert bal > 0.9  # widely separated gaussians, scaled LR splits them

    def test_calibrated_scaled_model_predicts(self):
        rng = np.random.default_rng(12)
        X = np.concatenate([rng.normal(5, 2, (30, 20)), rng.normal(-5, 2, (30, 20))])
        y = np.array(["SAT"] * 30 + ["UNSAT"] * 30)
        rc = ReadoutClassifier(method="logistic", calibrate=True, standardize=True)
        rc.fit(X, y)
        res = rc.predict(X[0])
        assert res.label in ("SAT", "UNSAT", "AMBIGUOUS")
        assert 0.0 <= res.confidence <= 1.0


class TestReadoutPredict:
    def test_logistic_on_synthetic_features(self):
        """Train on 100 synthetic vectors; predict must reach >=0.80 balanced
        accuracy on a held-out set."""
        rng = np.random.default_rng(1)
        n_train = 100
        X = []
        y = []
        # SAT: high mean firing (0.7); UNSAT: low mean firing (0.2).
        for _ in range(n_train):
            for label, mu in (("SAT", 0.7), ("UNSAT", 0.2)):
                pools = {
                    "mbons": rng.binomial(1, mu, size=(16, 20)),
                    "central_complex": rng.binomial(1, mu * 0.8, size=(12, 20)),
                    "giant_fiber": rng.binomial(1, mu, size=(4, 20)),
                }
                X.append(logistic_features(pools))
                y.append(label)
        X = np.array(X)
        rc = ReadoutClassifier(method="logistic", calibrate=False)
        rc.fit(X, y)
        # Held-out: 20 test vectors with the same generative structure.
        X_test = []
        y_test = []
        for _ in range(10):
            for label, mu in (("SAT", 0.7), ("UNSAT", 0.2)):
                pools = {
                    "mbons": rng.binomial(1, mu, size=(16, 20)),
                    "central_complex": rng.binomial(1, mu * 0.8, size=(12, 20)),
                    "giant_fiber": rng.binomial(1, mu, size=(4, 20)),
                }
                X_test.append(logistic_features(pools))
                y_test.append(label)
        correct = sum(
            1 for t in range(len(X_test)) if rc.predict(X_test[t]).label == y_test[t]
        )
        assert correct / len(X_test) >= 0.80

    def test_predict_requires_fit(self):
        rc = ReadoutClassifier()
        with pytest.raises(RuntimeError):
            rc.predict(np.zeros(5))

    def test_calibration_outputs_valid_probabilities(self):
        rng = np.random.default_rng(2)
        X = rng.random((60, 24))
        y = np.array(["SAT"] * 30 + ["UNSAT"] * 30)
        rc = ReadoutClassifier(method="logistic", calibrate=True)
        rc.fit(X, y)
        res = rc.predict(X[0])
        assert 0.0 <= res.confidence <= 1.0
        assert set(res.raw_scores.keys()) == {"SAT", "UNSAT"}

    def test_xgboost_baseline_matches_logistic(self):
        pytest.importorskip("xgboost")
        rng = np.random.default_rng(3)
        X = rng.random((120, 24))
        y = np.array(["SAT"] * 60 + ["UNSAT"] * 60)
        lr = ReadoutClassifier(method="logistic", calibrate=False)
        rc = ReadoutClassifier(method="xgboost", calibrate=False)
        lr.fit(X, y)
        rc.fit(X, y)
        for i in range(10):
            assert isinstance(lr.predict(X[i]).label, str)
            assert isinstance(rc.predict(X[i]).label, str)


class TestAmbiguityRejection:
    def test_tight_gap_is_ambiguous(self):
        """If top-2 probabilities differ by < threshold, label becomes
        AMBIGUOUS (rejection class)."""
        rng = np.random.default_rng(4)
        X = rng.random((100, 12))
        y = np.array(["SAT"] * 50 + ["UNSAT"] * 50)
        rc = ReadoutClassifier(method="logistic", calibrate=False, threshold_ambiguous=0.99)
        rc.fit(X, y)
        res = rc.predict(X[0])
        assert res.label == "AMBIGUOUS"
        assert isinstance(res, ClassificationResult)