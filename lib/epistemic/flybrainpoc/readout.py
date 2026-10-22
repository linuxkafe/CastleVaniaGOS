"""readout.py — trained classifier over reservoir activity (T-6).

The reservoir is fixed; the readout is the only trained component. It maps
per-pool spike counts (10ms bins) to a {SAT, UNSAT, AMBIGUOUS} verdict plus
a calibrated confidence. Methods: logistic regression (L2) as the baseline
and XGBoost as the stronger baseline. Platt scaling for calibration.

Design constraints:
  - xgboost import is optional (not guaranteed in every env); logistic is
    always available through sklearn.
  - The 3-class problem is collapsed into {SAT, UNSAT} for the core binary
    accuracy; AMBIGUOUS is a rejection class kept out of the binary score.
"""


import math

import numpy as np

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV

try:
    from xgboost import XGBClassifier
    _XGBOOST_OK = True
except ImportError:  # pragma: no cover
    _XGBOOST_OK = False


@dataclass
class ClassificationResult:
    label: str  # "SAT" | "UNSAT" | "AMBIGUOUS"
    confidence: float  # calibrated, 0..1
    raw_scores: Dict[str, float] = field(default_factory=dict)


def _featurize(pool_counts: Dict[str, np.ndarray]) -> np.ndarray:
    """Flatten per-pool 2D spike-count matrices into one feature vector.

    pool_counts: {pool: array (n_neurons, n_bins)}.
    Returns a 1D numpy array of ints; shape is (sum of n_neurons*n_bins).
    """
    parts = []
    for name in sorted(pool_counts.keys()):
        parts.append(np.asarray(pool_counts[name], dtype=float).ravel())
    if not parts:
        return np.zeros(0, dtype=float)
    return np.concatenate(parts)


class ReadoutClassifier:
    """Train on reservoir features, predict {SAT, UNSAT, AMBIGUOUS}."""

    def __init__(self, method: str = "logistic", calibrate: bool = True,
                 threshold_ambiguous: float = 0.35, standardize: bool = False):
        if method not in ("logistic", "xgboost"):
            raise ValueError(f"Unknown method: {method!r}")
        self.method = method
        self.calibrate = calibrate
        self.threshold_ambiguous = threshold_ambiguous
        # T306 arm 2: in-fold StandardScaler (Pipeline) — T305 measured
        # +0.085 balanced (0.622 -> 0.707) with scaling. The scaler is part of
        # the estimator so it is fit inside each CV fold (no leakage) and the
        # fitted checkpoint applies the same transform at predict time.
        self.standardize = standardize
        self._model = None
        self._classes = None

    def _make_model(self):
        if self.method == "logistic":
            clf = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
        elif not _XGBOOST_OK:
            raise ImportError("xgboost is optional; fall back to method='logistic'")
        else:
            clf = XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.1,
                subsample=0.9, colsample_bytree=0.8, use_label_encoder=False,
                eval_metric="logloss", verbosity=0,
            )
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        if self.standardize:
            return Pipeline([("scaler", StandardScaler()), ("clf", clf)])
        return clf

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ReadoutClassifier":
        labels = sorted(np.unique(np.asarray(y, dtype=str)).tolist())
        self._label_map = {lab: i for i, lab in enumerate(labels)}
        y_int = np.array([self._label_map[lab] for lab in y], dtype=int)
        model = self._make_model()
        model.fit(X, y_int)
        if self.calibrate and len(labels) == 2:
            model = CalibratedClassifierCV(model, method="sigmoid", cv=3)
            model.fit(X, y_int)
        self._model = model
        self._classes = labels
        return self

    def predict(self, X: np.ndarray) -> ClassificationResult:
        if self._model is None:
            raise RuntimeError("readout not fitted — call fit() first")
        probs = self._model.predict_proba(X[np.newaxis, :])[0]
        int_to_label = {i: lab for i, lab in enumerate(self._classes)}
        raw = {int_to_label[i]: float(p) for i, p in enumerate(probs)}
        label = max(raw, key=raw.get)
        conf = raw[label]
        # Ambiguity rejection: if the top-2 probability gap is small, mark
        # the verdict as ambiguous rather than confident.
        sort = sorted(raw.values(), reverse=True)
        if len(sort) >= 2 and (sort[0] - sort[1]) < self.threshold_ambiguous:
            label = "AMBIGUOUS"
            conf = sort[0]
        out = ClassificationResult(label=label, confidence=conf, raw_scores=raw)
        return out

    def fit_and_predict(self, X_train, y_train, X_test) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Convenience wrapper returning (preds, probs, confidence)."""
        self.fit(X_train, y_train)
        probs = self._model.predict_proba(X_test)
        int_to_label = {i: lab for i, lab in enumerate(self._classes)}
        preds = [int_to_label[int(np.argmax(probs[i]))] for i in range(len(X_test))]
        conf = [max(probs[i]) for i in range(len(X_test))]
        return np.asarray(preds), probs, np.asarray(conf)


def balanced_cv(X: np.ndarray, y: np.ndarray, cv: int = 5, method: str = "logistic",
                groups: Optional[np.ndarray] = None, scale: bool = False) -> Tuple[float, float]:
    """Stratified 5-fold balanced accuracy + UNSAT recall (macro).

    Returns (balanced_accuracy, recall_unsat). recall_unsat is computed
    over the union of cross-validated predictions so each fold's true
    positives/total are consistent with the fold's own labels.

    T289: when `groups` (island ids) are supplied, folds split by GROUP, never
    by sample — GroupKFold guarantees every sample of an island stays in one
    fold, so the reported accuracy measures generalization to unseen islands,
    not memorization (finding T277 §5.7). With one sample per island this equals
    sample CV by construction; the enforced invariant protects future
    multi-sample datasets.

    scale (T306 arm 2): StandardScaler wrapped into the estimator (via
    ReadoutClassifier.standardize) so it is fit inside each fold — zero
    leakage — and the transform is part of the model at predict time.
    """
    from sklearn.model_selection import GroupKFold, StratifiedKFold
    model = ReadoutClassifier(method=method, calibrate=False, standardize=scale)
    base = model._make_model()
    if groups is not None:
        gkf = GroupKFold(n_splits=cv)
        splits = gkf.split(X, y, groups)
    else:
        skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)
        splits = skf.split(X, y)
    conf = np.zeros((2, 2), dtype=int)  # rows true, cols pred, order [UNSAT, SAT]
    label_to_idx = {"UNSAT": 0, "SAT": 1}
    for train_idx, test_idx in splits:
        base.fit(X[train_idx], y[train_idx])
        pred = base.predict(X[test_idx])
        for t, p in zip(y[test_idx], pred):
            conf[label_to_idx[t], label_to_idx[p]] += 1
    balanced = 0.5 * (
        conf[0, 0] / max(conf[0].sum(), 1) + conf[1, 1] / max(conf[1].sum(), 1)
    )
    recall_unsat = conf[0, 0] / max(conf[0].sum(), 1)
    return float(balanced), float(recall_unsat)


def logistic_features(pool_counts: Dict[str, np.ndarray]) -> np.ndarray:
    return _featurize(pool_counts)


# ── T305: position-invariant temporal statistics (real-island separability) ──
# The raw per-pool bin features (0..1280) scatter the anti-phase signature of a
# `contradicts` pair across whichever sensory slots the pair members occupy,
# which differs between islands. A linear readout cannot align the signature
# across islands. These statistics collapse the neuron axis (order/position
# invariant) and the time axis into ~18 scalars per pool plus a cross-pool
# block, making the contradiction signature usable by the logistic readout.
# Empirical result (T305): balanced CV on 202 real islands 0.502 -> 0.707,
# UNSAT recall 0.1875 -> 0.688 with StandardScaler + this representation.


def _pool_temporal_stats(pool: np.ndarray) -> np.ndarray:
    """~18 position-invariant temporal statistics for one pool's counts.

    pool: (n_neurons, n_bins) spike counts. All quantities are invariant to
    neuron-slot ordering (they aggregate/sort over neurons), so a contradicts
    pair landing on different slots across islands still produces the same
    signature. Deterministic.
    """
    n_neurons, n_bins = pool.shape
    total = float(pool.sum())
    colsum = pool.sum(axis=0)                  # (n_bins,) firing profile
    rowsum = pool.sum(axis=1)                  # per-neuron totals
    w = np.arange(n_bins) + 0.5
    if total > 0:
        centroid = float((colsum * w).sum() / total)
        spread = float(np.sqrt((colsum * (w - centroid) ** 2).sum() / total))
        sel = colsum[colsum > 0]
        probs = sel / total
        entropy = float(-np.sum(probs * np.log(probs + 1e-12)) / np.log(n_bins))
        early = float(colsum[:20].sum() / total)
        late = float(colsum[20:].sum() / total)
        third1 = float(colsum[:14].sum() / total)
        third2 = float(colsum[14:27].sum() / total)
        third3 = float(colsum[27:].sum() / total)
        tail = float(colsum[22:].sum() / total)
    else:
        centroid = spread = entropy = 0.0
        early = late = third1 = third2 = third3 = tail = 0.0
    c = np.cov(colsum[:-1], colsum[1:])
    autocorr = float(c[0, 1] / (np.sqrt(c[0, 0] * c[1, 1]) + 1e-9)) if (
        c[0, 0] > 0 and c[1, 1] > 0) else 0.0
    participation = float(rowsum.max() / total) if total > 0 else 0.0
    s = np.sort(rowsum)
    if total > 0 and n_neurons > 1:
        gini = float((n_neurons + 1 - 2 * (s.cumsum() / total).sum()) / n_neurons)
    else:
        gini = 0.0
    no_early = float(colsum[:20].sum() == 0)
    no_late = float(colsum[20:].sum() == 0)
    return np.array([
        total, centroid, spread, early, late, early - late,
        third1, third2, third3, tail, autocorr, entropy,
        participation, gini, no_early, no_late,
        float((rowsum > 0).mean()),
        float(rowsum.std() / (rowsum.mean() + 1e-9)),
    ], dtype=float)


def temporal_stats_features(pool_counts: Dict[str, np.ndarray]) -> np.ndarray:
    """Position-invariant stats representation (T305).

    For each pool: `_pool_temporal_stats` (18 scalars). Across pools: firing
    composition, pooled centroid, centroid differences and pairwise time-profile
    correlations. Overlapping-pool aggregates make the vector order-independent
    over pool names. Returns all-zeros for empty input; degrades gracefully to
    per-pool stats only when fewer than 2 pools exist.
    """
    if not pool_counts:
        return np.zeros(0, dtype=float)
    names = sorted(pool_counts.keys())
    per_pool = np.concatenate([_pool_temporal_stats(np.asarray(pool_counts[n], dtype=float))
                               for n in names])
    if len(names) < 2:
        return per_pool
    totals = np.array([float(np.asarray(pool_counts[n]).sum()) for n in names])
    gt = totals.sum() + 1e-9
    comp = totals / gt
    cents = []
    profiles = []
    half = 1.0
    for n in names:
        col = np.asarray(pool_counts[n], dtype=float).sum(axis=0)
        profiles.append(col)
        tot = col.sum()
        if tot > 0:
            cents.append(float((col * (np.arange(len(col)) + 0.5)).sum() / tot))
        else:
            cents.append(0.0)
    cents = np.asarray(cents)
    cents_c = cents - cents.mean()
    cdiff = [cents_c[i] - cents_c[j] for i in range(len(names))
             for j in range(i + 1, len(names))]
    corrs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = profiles[i], profiles[j]
            ca = a - a.mean()
            cb = b - b.mean()
            den = math.sqrt(float((ca ** 2).sum()) * float((cb ** 2).sum())) + 1e-9
            corrs.append(float((ca * cb).sum()) / den)
    global_block = np.concatenate([comp, [float((totals * cents).sum() / gt)],
                                   cdiff, corrs])
    return np.concatenate([per_pool, global_block])


# ── T306: sensory-layer anti-phase statistics (v3) ─────────────────────────
# T305 root-cause #1 (unfinished): real-island UNSAT separability is capped
# because pool-level features monitor only the 32 readout neurons, which wash
# out the per-slot signature of a contradicts pair. The anti-phase signal lives
# on the 128-neuron sensory layer (the encoder output): for a contradicts edge
# the 'from' claim fires in an early window, the 'to' claim in a late window,
# scattered across whichever sensory slots the pair members occupy.
#
# v3 = v2 pool stats (backbone) ⊕ sensory anti-phase block computed at CLAIM
# RESOLUTION: the encoder meta maps claim ids to sensory slots, so every
# aggregate is pooled over the whole 128-channel layer (or computed directly on
# the pair's slots) and is position-invariant by construction — the pair
# landing on different slots or slices across islands yields the same stats.
# Empirical corpus rule (202 real islands): a contradicts edge is present in
# every UNSAT island (16/16) and in no SAT island (0/186), so these features
# make the Z3-UNSAT mechanism directly visible to the logistic readout.

# Anti-phase windows (ms), consistent with encoder.ANTI_PHASE_WINDOWS_MS
# (from=(0,220), to=(180,400)) binned at 10ms over a 400ms horizon (40 bins).
_EARLY_BINS = slice(0, 22)    # 0..220 ms
_LATE_BINS = slice(18, 40)    # 180..400 ms
_OVERLAP_BINS = slice(18, 22)  # 180..220 ms (windows overlap)
_V3_SENSORY_BLOCK = 30  # documented feature count in the sensory block


def _corr(a, b) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size < 2:
        return 0.0
    ca = a - a.mean()
    cb = b - b.mean()
    den = math.sqrt(float((ca ** 2).sum()) * float((cb ** 2).sum())) + 1e-12
    return float((ca * cb).sum() / den)


def _gini(x) -> float:
    x = np.asarray(x, dtype=float)
    s = np.sort(x)
    n = s.size
    if n < 2 or s.sum() <= 0:
        return 0.0
    return float((n + 1 - 2 * (s.cumsum() / s.sum()).sum()) / n)


def sensory_antiphase_features(
    pool_counts: Dict[str, np.ndarray],
    sensory_counts: "np.ndarray",
    sensory_meta: Dict[int, dict],
    edges: Optional[list] = None,
) -> np.ndarray:
    """Position-invariant sensory-layer anti-phase statistics (T306 v3).

    sensory_counts: (n_slots, n_bins) binned sensory-layer spike counts (the
        encoder output — the reservoir input group reproduces these trains, so
        no extra monitoring is needed; deterministic per island seed).
    sensory_meta:   {slot: {"claim", "is_contradiction", "operator",
        "confidence"}} — the encoder meta (overwrites collapse to final state).
    edges:          island "edges" list; contradicting from/to roles resolved
        against the meta so pair statistics are computed at claim resolution.

    Returns v2 pool backbone concatenated with the 30-scalar sensory block
    (documented below). All sensory aggregates are pooled over the full
    128-channel layer or computed at claim resolution -> invariant to which
    slots/slices the pair occupies. Deterministic.
    """
    backbone = temporal_stats_features(pool_counts)
    sensory_counts = np.asarray(sensory_counts, dtype=float)
    n_slots, n_bins = sensory_counts.shape
    if sensory_meta is None:
        sensory_meta = {}
    if n_slots == 0 or n_bins == 0:
        return np.concatenate([backbone, np.zeros(_V3_SENSORY_BLOCK, dtype=float)])

    rowsum = sensory_counts.sum(axis=1)                    # (n_slots,)
    colsum = sensory_counts.sum(axis=0)                    # (n_bins,)
    total = float(sensory_counts.sum())
    active = rowsum > 0
    n_active = int(active.sum())

    # ── head/tail composition (pooled, position-invariant) ──
    early = sensory_counts[:, _EARLY_BINS].sum(axis=1)
    late = sensory_counts[:, _LATE_BINS].sum(axis=1)
    head_only = (early > 0) & (late == 0)
    tail_only = (late > 0) & (early == 0)
    both = (early > 0) & (late > 0)
    n_head = int(head_only.sum())
    n_tail = int(tail_only.sum())
    n_both = int(both.sum())
    n_neither = int((~active).sum())
    denom_active = max(n_active, 1)
    head_frac = n_head / denom_active
    tail_frac = n_tail / denom_active
    both_frac = n_both / denom_active
    neither_frac = n_neither / max(n_slots, 1)

    # pooled anti-phase correlation: early-vs-late mass across active slots
    antiphase_corr = _corr(early[active] + 1e-9, late[active] + 1e-9)
    # template correlation: mean profile of head-only vs tail-only slots
    tpl_head = sensory_counts[head_only].mean(axis=0) if n_head else np.full(n_bins, 0.0)
    tpl_tail = sensory_counts[tail_only].mean(axis=0) if n_tail else np.full(n_bins, 0.0)
    template_corr = _corr(tpl_head, tpl_tail)
    mean_slot_mass = total / max(n_slots * n_bins, 1)
    gini_slots = _gini(rowsum)

    # ── role-aware, at claim resolution ──
    claim_to_slot = {}
    for slot, m in sensory_meta.items():
        cid = m.get("claim")
        if cid:
            claim_to_slot[cid] = int(slot)
    pairs = []
    for e in (edges or []):
        etype = str(e.get("type", "")).lower()
        if etype in ("contradicts", "negates", "contradiction"):
            frm, to = e.get("from"), e.get("to")
            if frm in claim_to_slot and to in claim_to_slot:
                pairs.append((claim_to_slot[frm], claim_to_slot[to], frm, to))
    from_early_frac = from_late_frac = to_early_frac = to_late_frac = 0.0
    overlap_frac = complementarity = 0.0
    flip_count = 0
    pair_from_conf = pair_to_conf = 0.0
    for fs, ts, fcid, tcid in pairs:
        frow, trow = sensory_counts[fs], sensory_counts[ts]
        ftot, ttot = max(float(frow.sum()), 1e-9), max(float(trow.sum()), 1e-9)
        fE = float(frow[_EARLY_BINS].sum()) / ftot
        fL = float(frow[_LATE_BINS].sum()) / ftot
        tE = float(trow[_EARLY_BINS].sum()) / ttot
        tL = float(trow[_LATE_BINS].sum()) / ttot
        from_early_frac += fE
        from_late_frac += fL
        to_early_frac += tE
        to_late_frac += tL
        overlap_frac += float(frow[_OVERLAP_BINS].sum()) / ftot
        # anti-phase: 'from' early-dominant AND 'to' late-dominant -> positive
        complementarity += max(0.0, (fE - fL)) * max(0.0, (tL - tE))
        flip_count += int(fL > fE) + int(tE > tL)
        pair_from_conf += float(sensory_meta.get(fs, {}).get("confidence", 0.0))
        pair_to_conf += float(sensory_meta.get(ts, {}).get("confidence", 0.0))
    n_pairs = len(pairs)
    if n_pairs:
        from_early_frac /= n_pairs
        from_late_frac /= n_pairs
        to_early_frac /= n_pairs
        to_late_frac /= n_pairs
        overlap_frac /= n_pairs
        complementarity /= n_pairs
        pair_from_conf /= n_pairs
        pair_to_conf /= n_pairs

    # ── operator composition + contradiction mass/confidence ──
    ops = [str(m.get("operator", "DEFAULT")) for m in sensory_meta.values()]
    n_meta = max(len(ops), 1)
    op_G = sum(1 for o in ops if o == "G") / n_meta
    op_F = sum(1 for o in ops if o == "F") / n_meta
    op_P = sum(1 for o in ops if o == "P") / n_meta
    op_D = sum(1 for o in ops if o == "DEFAULT") / n_meta
    contra_slots = [s for s, m in sensory_meta.items() if m.get("is_contradiction")]
    contra_mass = float(sum(rowsum[s] for s in contra_slots)) if contra_slots else 0.0
    contra_mass_frac = contra_mass / max(total, 1e-9)
    confs = [float(m.get("confidence", 0.0)) for m in sensory_meta.values()]
    contra_conf = [float(sensory_meta[s].get("confidence", 0.0)) for s in contra_slots]
    non_conf = [float(sensory_meta[s].get("confidence", 0.0))
                for s in sensory_meta if not sensory_meta[s].get("is_contradiction")]
    mean_contra_conf = float(np.mean(contra_conf)) if contra_conf else 0.0
    mean_non_conf = float(np.mean(non_conf)) if non_conf else 0.0
    conf_gap = mean_contra_conf - mean_non_conf

    sensory_block = np.array([
        n_active / max(n_slots, 1),          # 0 active-slot fraction
        head_frac,                           # 1 head-only fraction (active)
        tail_frac,                           # 2 tail-only fraction (active)
        both_frac,                           # 3 both-windows fraction (active)
        neither_frac,                        # 4 silent-slot fraction (all)
        float(n_head),                       # 5 head-only count
        float(n_tail),                       # 6 tail-only count
        head_frac * tail_frac,               # 7 complementary pair fraction
        antiphase_corr,                      # 8 pooled early/late anti-corr
        template_corr,                       # 9 head-template vs tail-template corr
        mean_slot_mass,                      # 10 mean mass per slot-bin
        gini_slots,                          # 11 slot-mass concentration
        float(n_pairs),                      # 12 contradicts pair count
        from_early_frac,                     # 13 'from' early-window mass frac
        from_late_frac,                      # 14 'from' late-window mass frac
        to_early_frac,                       # 15 'to' early-window mass frac
        to_late_frac,                        # 16 'to' late-window mass frac
        overlap_frac,                        # 17 'from' mass in overlap window
        complementarity,                     # 18 anti-phase complementarity
        float(flip_count),                   # 19 role-flip count
        pair_from_conf,                      # 20 pair 'from' validation conf
        pair_to_conf,                        # 21 pair 'to' validation conf
        op_G, op_F, op_P, op_D,              # 22-25 operator composition
        contra_mass_frac,                    # 26 contradiction mass fraction
        mean_contra_conf,                    # 27 contradiction claims' conf
        mean_non_conf,                       # 28 non-contradiction claims' conf
        conf_gap,                            # 29 confidence gap (contra - non)
    ], dtype=float)
    return np.concatenate([backbone, sensory_block])