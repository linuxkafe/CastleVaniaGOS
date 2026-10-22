"""validator.py — orchestrator: encode -> simulate -> classify -> compare (T-5/T-7).

Primary entry point: validate_island(). It mirrors gmif-check.sh's contract:
reads the same island YAML, produces a verdict file alongside Z3's result,
and writes divergences.json for the async gate.
"""

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import yaml

from lib.epistemic.flybrainpoc.encoder import Encoder
from lib.epistemic.flybrainpoc.readout import ClassificationResult, ReadoutClassifier
from lib.epistemic.flybrainpoc.reservoir import (
    FlyBrainReservoir,
    get_backend_fallback_reason,
)


class FlyBrainTimeout(RuntimeError):
    """Raised when the whole encode->simulate->classify pipeline exceeds budget."""


def _effective_backend_name(validator) -> str:
    """Name the backend that actually executed the run (T320).

    Read from the run itself, not from what was requested: `backend="cuda"` on
    this host resolves to CPU, and an artefact that says "cuda" is a false
    provenance claim. In isolation mode the reservoir that ran is a local
    instance, so `run_island` stashes it here.
    """
    used = getattr(validator, "last_backend_used", None)
    if used is not None:
        return getattr(used, "value", str(used))
    cap = getattr(getattr(validator, "reservoir", None), "backend_capability", None)
    if cap is None:
        return "unknown"
    return getattr(cap.backend, "value", str(cap.backend))


@dataclass
class FlyBrainResult:
    island: str
    label: str  # SAT | UNSAT | AMBIGUOUS
    confidence: float
    z3_result: Optional[str] = None
    divergence: bool = False
    elapsed_ms: float = 0.0
    raw_scores: Dict[str, float] = field(default_factory=dict)
    out_path: Optional[Path] = None


def compute_divergence_score(result: FlyBrainResult) -> float:
    """Compute a divergence score based on confidence and verdict mismatch.
    
    Returns a score between 0.0 and 1.0 where higher means more divergent.
    """
    if not result.divergence:
        return 0.0
    # Higher confidence in disagreement = higher divergence score
    # If fly-brain is very confident but disagrees with Z3, that's significant
    base_score = result.confidence
    # If Z3 result is missing, lower the score
    if result.z3_result not in ("SAT", "UNSAT"):
        base_score *= 0.5
    return round(base_score, 2)


def create_shadow_doc(result: FlyBrainResult, island_path: Path, 
                      z3_result_path: Path, shadow_dir: Optional[Path] = None) -> Path:
    """Create shadow doc for fly-brain/Z3 divergence.

    Args:
        result: FlyBrainResult with divergence=True
        island_path: Path to the island YAML file
        z3_result_path: Path to the Z3 result file
        shadow_dir: override for the shadow-doc directory (default: <repo>/aes/shadow)

    Returns:
        Path to the created shadow doc
    """
    if result.out_path is None:
        raise ValueError("cannot create shadow doc: result.out_path is not set")
    # A shadow doc binds its content_hash to the fly-brain result artifact.
    # If that artifact lives in an ephemeral location (e.g. /tmp during
    # tests), the doc would reference a file that disappears — reject it
    # rather than pollute aes/shadow with broken evidence.
    if str(result.out_path).startswith("/tmp"):
        raise ValueError(
            f"refusing to bind shadow doc to ephemeral out path: {result.out_path}"
        )
    # Compute content hash of result.json
    result_json = Path(result.out_path).read_bytes()
    content_hash = hashlib.sha256(result_json).hexdigest()

    # Build frontmatter (single timestamp so id/created/filename agree)
    now = datetime.now()
    doc_id = f"SD-GMIF-FLY-{now.strftime('%Y%m%d%H%M%S')}"
    frontmatter = {
        "id": doc_id,
        "type": "lesson",
        "okf_version": "0.2",
        "title": f"Fly-brain Divergence: island {result.island}",
        "synthesis": f"Z3={result.z3_result}, fly-brain={result.label} (confidence {result.confidence:.2f}); divergence detected",
        "epistemic_state": "SUPORTADA",
        "pointer": {"path": str(result.out_path), "content_hash": content_hash},
        "provenance": {
            "generated_by": "gmif-check-flybrain.sh",
            "generated_at": now.isoformat(),
            "source_ticket": "T269",
            "source_conversation": f"gmif-check-flybrain.sh divergence detection: island {result.island}, Z3={result.z3_result}, fly-brain={result.label}",
            "island_id": result.island,
            "z3_verdict": result.z3_result,
            "fly_verdict": result.label,
            "fly_confidence": round(result.confidence, 2),
            "divergence_score": compute_divergence_score(result),
        },
        "content_hash": content_hash,
        "generated": {"by": "gmif-check-flybrain.sh", "at": now.isoformat()},
        "score": {"activation": round(result.confidence, 2), "pinned": False, "centrality": 0.0},
        "last_accessed": now.isoformat(),
        "created": now.isoformat(),
    }
    
    # Build markdown body
    body = f"""# Fly-brain Divergence Report

## Island
- **ID**: {result.island}
- **Path**: {island_path}

## Verdicts
- **Z3**: {result.z3_result}
- **Fly-brain**: {result.label} (confidence: {result.confidence:.2f})

## Divergence
- **Detected**: Yes
- **Score**: {compute_divergence_score(result)}

## Raw Scores
```json
{json.dumps(result.raw_scores, indent=2)}
```

## Evidence
- Fly-brain result: aes/verification/flybrain/result.json
- Z3 result: {z3_result_path}
- Divergence log: aes/graph/flybrain-divergences.json
"""
    
    # Build frontmatter YAML
    import yaml
    frontmatter_yaml = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)
    
    # Write shadow doc (frontmatter delimited per repo convention: ---\n<yaml>\n---)
    aes_root = Path(__file__).resolve().parents[3]
    shadow_path = (Path(shadow_dir) if shadow_dir else aes_root / "aes" / "shadow") / f"{doc_id}.md"
    shadow_path.parent.mkdir(parents=True, exist_ok=True)
    shadow_path.write_text("---\n" + frontmatter_yaml + "---\n\n" + body)
    
    return shadow_path


class FlyBrainTimeout(RuntimeError):
    """Raised when the whole encode->simulate->classify pipeline exceeds budget."""


@dataclass
class FlyBrainResult:
    island: str
    label: str  # SAT | UNSAT | AMBIGUOUS
    confidence: float
    z3_result: Optional[str] = None
    divergence: bool = False
    elapsed_ms: float = 0.0
    raw_scores: Dict[str, float] = field(default_factory=dict)
    out_path: Optional[Path] = None


def _flatten_counts(pool_counts: Dict[str, "np.ndarray"]) -> Dict[str, list]:
    return {name: arr.tolist() for name, arr in pool_counts.items()}


def _seed_for(island_id: str) -> int:
    """Stable per-island RNG seed (independent of processing order)."""
    import zlib
    return zlib.crc32(island_id.encode("utf-8"))


def _read_z3_result(result_path: Path) -> Optional[str]:
    if not result_path.exists():
        return None
    txt = result_path.read_text().strip()
    # Handle JSON format (cache hit)
    if txt.startswith("{"):
        try:
            import json
            data = json.loads(txt)
            return data.get("result", "ERROR")
        except json.JSONDecodeError:
            pass
    # Plain text format (cache miss)
    txt = txt.strip().upper()
    if txt.startswith("SAT"):
        return "SAT"
    if txt.startswith("UNSAT"):
        return "UNSAT"
    if txt.startswith("TIMEOUT"):
        return "TIMEOUT"
    return txt


def describe_readout(
    checkpoint: Optional[Path], fitted: bool
) -> Dict[str, object]:
    """Identity of the MODEL that produced a confidence, for the artefact.

    T321. T320 recorded the provenance of the RUN (`backend_used`,
    `backend_fallback_reason`) because a CPU run chosen through the "cuda"
    backend was indistinguishable from a real GPU run. This is the same defect
    one level up: the ARTEFACT records `confidence` but nothing about which
    fitted model produced it, so a number from a classifier and a number from
    the unfitted fallback are written identically.

    The fallback in `FlyBrainValidator.run_island` returns confidence exactly
    0.5. So before this change, "0.5" was a silently different measurement
    wearing the same field name as "0.8549".

    A hash of a file that was NOT used would be worse than no hash, so
    `fitted` is recorded alongside it: a sha256 with `fitted: false` means the
    artefact is honestly labelled and the number came from the fallback.
    """
    out: Dict[str, object] = {
        "fitted": bool(fitted),
        "source": "fitted-checkpoint" if fitted else "mean-activity-fallback",
        "checkpoint": None,
        "sha256": None,
        "bytes": None,
    }
    if checkpoint is None:
        return out
    ckpt = Path(checkpoint)
    out["checkpoint"] = str(ckpt)
    if not ckpt.exists():
        return out
    if not fitted:
        # The file is there but no model came from it — joblib missing, or the
        # object was not a usable readout. Record that fact WITHOUT a sha256.
        #
        # The first version of this function hashed whenever the file existed,
        # and the test written for it caught that immediately. A hash here is
        # not merely redundant, it is misleading: it puts a model identity
        # next to a number that no model produced, and a reader comparing two
        # artefacts would infer the models differed when the truth is that one
        # of them has no model at all. `fitted` already carries that truth.
        out["present_but_unused"] = True
        return out
    h = hashlib.sha256()
    with ckpt.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    out["sha256"] = h.hexdigest()
    out["bytes"] = ckpt.stat().st_size
    return out


def load_readout_checkpoint(path: Optional[Path]) -> Optional[ReadoutClassifier]:
    """Load a fitted readout from a benchmark checkpoint (or None if absent).
    
    Accepts either the full :class:`ReadoutClassifier` object (current
    format) or a legacy dump of just the wrapped estimator with the
    synthetic label order [UNSAT, SAT] (pre-T269 revert format).
    """
    try:
        import joblib
    except ImportError:
        return None
    if path is None or not Path(path).exists():
        return None
    obj = joblib.load(path)
    if isinstance(obj, ReadoutClassifier):
        return obj
    clf = ReadoutClassifier(method="logistic", calibrate=True)
    clf._model = obj
    clf._classes = ["SAT", "UNSAT"]
    return clf


class FlyBrainValidator:
    """Reusable validator; loads the reservoir once and processes many islands."""

    def __init__(
        self,
        encoder: Optional[Encoder] = None,
        reservoir: Optional[FlyBrainReservoir] = None,
        readout: Optional[ReadoutClassifier] = None,
        duration_ms: float = 400.0,
        timeout: int = 120,
        isolate_reservoir: bool = True,
        encoder_mode: str = "rate+timing",
        encoder_layout: str = "positional",
    ):
        self.encoder = encoder or Encoder(mode=encoder_mode, layout=encoder_layout)
        self.reservoir = reservoir or FlyBrainReservoir(model="TRIVIAL_UNIT")
        self.readout = readout or ReadoutClassifier(method="logistic", calibrate=True)
        self.duration_ms = duration_ms
        self.timeout = timeout
        self._isolate_reservoir = isolate_reservoir
        self._reservoir_loaded = False
        self._readout_fitted = False
        #: Backend that executed the most recent run (T320 provenance).
        self.last_backend_used = None
        self.last_features: Optional["np.ndarray"] = None
        # Stashed per-pool 40-bin spike counts from the last run_island, for
        # consumers that need pool-level temporal detail (T402 anomaly
        # detection / hybrid_loop OBSERVAÇÃO context).
        self.last_pool_counts: Optional[dict] = None
        # T306 v3: stashed sensory-layer context — (128, n_bins) binned input
        # counts plus the encoder meta (slot -> {claim, is_contradiction, ...})
        # and the island edges, consumed by the v3 featurizer at claim
        # resolution. Deterministic: derives from the encoder output, which the
        # reservoir's input group reproduces exactly (no extra monitoring).
        self.last_sensory_counts: Optional["np.ndarray"] = None
        self.last_sensory_meta: Optional[dict] = None

    def _ensure_loaded(self):
        if not self._reservoir_loaded:
            self.reservoir.load()
            self._reservoir_loaded = True

    def _ensure_readout(self, fit_data: Optional[tuple] = None):
        """Train the readout on reservoir features.
        
        fit_data: (X, y) used for the balanced-accuracy benchmark; when
        absent, the readout defaults are used for `predict` only after a
        call to fit() elsewhere. In the gate path, the readout is loaded
        from a checkpoint on disk (see validate_island).
        """
        if fit_data is not None and not self._readout_fitted:
            X, y = fit_data
            self.readout.fit(X, y)
            self._readout_fitted = True

    def run_island(self, island: Dict, island_id: str, trial: int = 0) -> FlyBrainResult:
        t0 = time.perf_counter()
        if (time.perf_counter() - t0) > self.timeout:
            raise FlyBrainTimeout(
                f"timeout before processing {island_id} (budget {self.timeout}s)"
            )
        # Deterministic per-island Poisson draws: seed the encoder RNG with a
        # stable hash of the island id so benchmark runs are reproducible
        # regardless of order (RFC §7.2 T-4 seeded-n_run reproducibility).
        # T303 ensemble: trial>0 derives a distinct seed from the same island
        # id, giving independent trials per island (trial=0 keeps the exact
        # historical single-run behavior/seed).
        if trial == 0:
            seed = _seed_for(island_id)
        else:
            seed = _seed_for(f"{island_id}#{trial}")
        np.random.seed(seed)
        st = self.encoder.encode_island(island)
        if len(st.spike_trains) == 0:
            raise ValueError(f"island {island_id} encoded to zero spike trains")
        # Isolation protocol: each island is an independent experiment.
        # Brian2 SpikeMonitors accumulate across runs, so reusing one
        # reservoir across islands mixes spike counts and destroys the
        # discriminating signal (observed as flat 0.500 benchmarks).
        if self._isolate_reservoir:
            res = FlyBrainReservoir(model="TRIVIAL_UNIT")
            res.load()
        else:
            self._ensure_loaded()
            res = self.reservoir
        # T320: record the backend that actually ran THIS run. The reservoir in
        # isolation mode is a local instance, so reading `self.reservoir` at
        # report time would report a reservoir that never ran (it reported
        # "unknown", which is at least honest but useless).
        self.last_backend_used = getattr(
            getattr(res, "backend_capability", None), "backend", None
        )
        res.inject(st.spike_trains)
        pool_counts = res.simulate(duration_ms=self.duration_ms)
        self.last_pool_counts = pool_counts
        # T306 v3: bin the sensory encoder output into (128, n_bins) counts and
        # pass the full sensory context to the featurizer (claim resolution).
        n_bins = int(self.duration_ms / self.encoder.bin_ms)
        self.last_sensory_counts = _bin_sensory(
            st.spike_trains, n_bins, self.duration_ms, self.encoder.bin_ms
        )
        self.last_sensory_meta = dict(st.meta)
        self.last_features = _featurize_single(
            pool_counts,
            sensory_counts=self.last_sensory_counts,
            sensory_meta=self.last_sensory_meta,
            edges=island.get("edges", []),
        )
        try:
            res = self.readout.predict(self.last_features)
        except RuntimeError:
            # Readout not fitted — fall back to a naive mean-activity guess.
            total = int(np.sum([np.sum(arr) for arr in pool_counts.values()]))
            res = ClassificationResult(
                label="UNSAT" if total < 10 else "SAT",
                confidence=0.5,
                raw_scores={},
            )
        elapsed = (time.perf_counter() - t0) * 1000.0
        return FlyBrainResult(
            island=island_id,
            label=res.label,
            confidence=res.confidence,
            elapsed_ms=elapsed,
            raw_scores=res.raw_scores,
        )

    def compare(self, fb: FlyBrainResult, z3_result: Optional[str]) -> FlyBrainResult:
        """Attach the Z3 verdict and set the divergence flag."""
        fb.z3_result = z3_result
        if z3_result in ("SAT", "UNSAT"):
            fb.divergence = fb.label == "AMBIGUOUS" or fb.label != z3_result
        else:
            fb.divergence = False
        return fb


def _bin_sensory(spike_trains: Dict[int, "np.ndarray"], n_bins: int,
                 duration_ms: float, bin_ms: float) -> "np.ndarray":
    """Bin encoder spike trains into (128, n_bins) sensory-layer counts.

    The reservoir input group reproduces these trains exactly, so the v3
    sensory features can be computed directly from the encoder output — no
    extra SpikeMonitor. Slots outside 0..127 are folded modulo 128 (defensive;
    encoder layout already bounds to 128)."""
    counts = np.zeros((128, n_bins), dtype=float)
    for slot, times in spike_trains.items():
        if times is None or len(times) == 0:
            continue
        idx = np.clip((np.asarray(times, dtype=float) / bin_ms).astype(int),
                      0, n_bins - 1)
        np.add.at(counts[int(slot) % 128, :], idx, 1.0)
    return counts


def _featurize_single(pool_counts: Dict[str, "np.ndarray"],
                      sensory_counts: "np.ndarray" = None,
                      sensory_meta: dict = None,
                      edges: list = None) -> "np.ndarray":
    """Map per-pool spike counts to a feature vector.

    The featurizer is a per-run, explicit choice (T305): the default "raw"
    preserves the historical logistic_features contract used by the synthetic
    benchmarks and the flybrain gate; "v2" selects the position-invariant
    temporal statistics added for real-island separability; "v3" (T306) adds
    the sensory-layer anti-phase statistics computed at claim resolution
    (v3 = v2 backbone + 30-scalar sensory block). Select via the
    AES_FEATURIZER environment variable; any value other than "v2"/"v3" keeps
    the raw representation so every existing caller is bit-for-bit unchanged.

    v3 requires the sensory context (binned input counts + encoder meta +
    island edges); callers without it (old unit tests, pool-only consumers)
    degrade gracefully to the v2 backbone instead of crashing.
    """
    from lib.epistemic.flybrainpoc.readout import (
        logistic_features, sensory_antiphase_features, temporal_stats_features,
    )
    mode = os.environ.get("AES_FEATURIZER", "raw")
    if mode == "v3":
        if sensory_counts is None or sensory_counts.size == 0:
            return temporal_stats_features(pool_counts)
        return sensory_antiphase_features(pool_counts, sensory_counts, sensory_meta, edges)
    if mode == "v2":
        return temporal_stats_features(pool_counts)
    return logistic_features(pool_counts)


class GateBudget:
    """Simple wall-clock budget for the async gate subprocess."""

    def __init__(self, deadline_s: float):
        self.start = time.perf_counter()
        self.deadline_s = deadline_s

    def remaining(self) -> float:
        return self.deadline_s - (time.perf_counter() - self.start)

    def expired(self) -> bool:
        return self.remaining() <= 0.0


def validate_island(
    island_path: Path,
    z3_result_path: Path,
    flybrain_result_path: Path,
    divergences_path: Optional[Path] = None,
    timeout: int = 120,
    checkpoint: Optional[Path] = None,
) -> FlyBrainResult:
    """Top-level CLI per island. Mirrors the Z3 gate's per-file flow.
    
    If `checkpoint` (a fitted-readout state) is provided, load it. Otherwise
    a naive mean-activity fallback is used so the gate never crashes on an
    unfitted readout, while SC-1's benchmark path uses its own fitted model.
    """
    island = yaml.safe_load(island_path.read_text())
    island_id = island.get("artifact") or island_path.stem

    validator = FlyBrainValidator(timeout=timeout)
    fitted = None
    if checkpoint is not None:
        fitted = load_readout_checkpoint(checkpoint)
        if fitted is not None:
            validator.readout = fitted
    result = validator.run_island(island, island_id)
    result = validator.compare(result, _read_z3_result(z3_result_path))
    result.out_path = flybrain_result_path

    flybrain_result_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ticket": "T269",
        "island": island_id,
        "label": result.label,
        "confidence": round(result.confidence, 4),
        "z3_result": result.z3_result,
        "divergence": result.divergence,
        "elapsed_ms": round(result.elapsed_ms, 2),
        "raw_scores": result.raw_scores,
        # T287/ADR-012: explicit arbitration state on every divergence.
        #   arbiter: z3 (mechanical decision for logical claims),
        #            human (recorded human verdict), human-pending (open)
        #   arbiter_verdict: SAT/UNSAT/UNKNOWN (z3) or accept-z3 /
        #                    favor-flybrain / undecidable (human) or "" (open)
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arbiter": "z3" if result.z3_result in ("SAT", "UNSAT") else "human-pending",
        "arbiter_verdict": result.z3_result if result.z3_result in ("SAT", "UNSAT") else "",
        "state": "open",
        # T320: provenance of the run. Without this, a CPU run selected through
        # the "cuda" backend was indistinguishable from a real GPU run in the
        # artefact, which is exactly why the misdetection survived for months.
        # `backend_used` is what actually executed; `backend_fallback_reason`
        # is set only when a higher-priority backend was skipped.
        "backend_used": _effective_backend_name(validator),
        "backend_fallback_reason": get_backend_fallback_reason(),
        # T321: identity of the MODEL behind `confidence`, the model-level
        # counterpart to T320's run-level provenance. Without it, the
        # `confidence` above is an unlabelled number: the same field carries a
        # fitted classifier's output and the unfitted fallback's flat 0.5, and
        # a refit silently rewrites past artefacts' apparent meaning. With
        # `fitted` and `sha256`, a reader can tell whether two confidences
        # came from the same model — and tell when they did not.
        "readout": describe_readout(checkpoint, fitted is not None),
    }
    flybrain_result_path.write_text(json.dumps(payload, indent=2))

    if divergences_path is not None and result.divergence:
        divergences_path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if divergences_path.exists():
            existing = json.loads(divergences_path.read_text())
        existing.append(payload)
        divergences_path.write_text(json.dumps(existing, indent=2))
        
        # Create shadow doc for divergence
        try:
            shadow_path = create_shadow_doc(result, island_path, z3_result_path)
            print(f"[flybrain] divergence shadow doc created: {shadow_path}")
        except Exception as e:
            print(f"[flybrain] WARNING: failed to create shadow doc: {e}", file=sys.stderr)

    return result


def benchmark_fit(X: "np.ndarray", y: "np.ndarray", cv: int = 5) -> Dict[str, float]:
    """Balanced CV accuracy used for SC-1. Returns {'balanced_acc':..., 'recall_unsat':...}."""
    from lib.epistemic.flybrainpoc.readout import balanced_cv
    acc, recall = balanced_cv(X, y, cv=cv, method="logistic")
    return {"balanced_acc": acc, "recall_unsat": recall}


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="T269 fly-brain GMIF validator (per island)")
    parser.add_argument("island", type=Path, help="path to the island YAML")
    parser.add_argument("--z3-result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--divergences", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--checkpoint", type=Path, default=None)
    args = parser.parse_args()
    try:
        validate_island(args.island, args.z3_result, args.out, args.divergences,
                        args.timeout, args.checkpoint)
    except (FlyBrainTimeout, ValueError) as exc:
        print(f"[flybrain] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"[flybrain] validated {args.island.stem} -> {args.out}")