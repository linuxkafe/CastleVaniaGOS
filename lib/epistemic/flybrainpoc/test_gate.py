"""test_gate.py — T269 async gate + validator wiring (T-5/T-7/T-8).

Covers: verdict JSON contract, divergence flag logic, divergence append
semantics, and readout-checkpoint loading used by scripts/gmif-check-flybrain.sh.
Simulation-path tests use the cheap naive readout to keep runtime small; the
fitted-readout path is exercised by scripts/gmif-check-flybrain.sh --self-check.
"""


from pathlib import Path

import numpy as np
import yaml

from lib.epistemic.flybrainpoc.readout import ReadoutClassifier
from lib.epistemic.flybrainpoc.validator import (
    _read_z3_result,
    FlyBrainResult,
    FlyBrainValidator,
    load_readout_checkpoint,
    validate_island,
)


MINI_SAT = {
    "artifact": "mini-sat",
    "label": "SAT",
    "nodes": [
        {"id": "C-1", "kind": "claim", "validation_type": "logical",
         "logical_form": "G(C-1)", "validation_confidence": 0.8},
        {"id": "C-2", "kind": "claim", "validation_type": "logical",
         "logical_form": "G(C-2)", "validation_confidence": 0.8},
    ],
    "edges": [{"from": "C-1", "to": "C-2", "type": "implies", "strength": "strong"}],
}

MINI_UNSAT = {
    "artifact": "mini-unsat",
    "label": "UNSAT",
    "nodes": [
        {"id": "C-1", "kind": "claim", "validation_type": "logical",
         "logical_form": "G(C-1)", "validation_confidence": 0.8},
        {"id": "C-2", "kind": "claim", "validation_type": "logical",
         "logical_form": "NOT G(C-1)", "validation_confidence": 0.8},
    ],
    "edges": [{"from": "C-1", "to": "C-2", "type": "contradicts", "strength": "strong"}],
}


def _write(where: Path, isl: dict) -> Path:
    p = where / f"{isl['artifact']}.yaml"
    p.write_text(yaml.safe_dump(isl))
    return p


def test_read_z3_result_dispatches(tmp_path):
    d = tmp_path / "z3tmp"
    d.mkdir(exist_ok=True)
    (d / "sat").write_text("SATISFIABLE\nwith model...")
    (d / "unsat").write_text("unsat")
    (d / "to").write_text("TIMEOUT")
    (d / "missing").unlink(missing_ok=True)
    assert _read_z3_result(d / "sat") == "SAT"
    assert _read_z3_result(d / "unsat") == "UNSAT"
    assert _read_z3_result(d / "to") == "TIMEOUT"
    assert _read_z3_result(d / "missing") is None


def test_compare_sets_divergence_flag():
    v = FlyBrainValidator()
    ok = v.compare(FlyBrainResult(island="i", label="SAT", confidence=0.9), "SAT")
    assert ok.divergence is False
    bad = v.compare(FlyBrainResult(island="i", label="SAT", confidence=0.9), "UNSAT")
    assert bad.divergence is True
    gone = v.compare(FlyBrainResult(island="i", label="UNSAT", confidence=0.9), None)
    assert gone.divergence is False


def test_validate_island_writes_verdict_and_divergences(tmp_path):
    island_path = _write(tmp_path, MINI_SAT)
    z3 = tmp_path / "z3.txt"
    z3.write_text("SAT")
    out = tmp_path / "flybrain" / "result.json"
    divs = tmp_path / "divergences.json"
    res = validate_island(island_path, z3, out, divs, timeout=300)
    assert res.label in ("SAT", "UNSAT")
    assert res.z3_result == "SAT"
    payload = __import__("json").loads(out.read_text())
    for key in ("ticket", "island", "label", "confidence", "z3_result",
                "divergence", "elapsed_ms", "raw_scores"):
        assert key in payload
    assert payload["ticket"] == "T269"
    # no fabricated divergence for matching verdicts on this naive path
    assert payload["divergence"] is False
    assert divs.exists() is False or __import__("json").loads(divs.read_text()) == []


def test_validate_island_appends_divergence(tmp_path):
    island_path = _write(tmp_path, MINI_UNSAT)
    # Predict the naive-path verdict, then feed Z3 the OPPOSITE verdict so a
    # divergence is guaranteed and we exercise the append path.
    probe = FlyBrainValidator(timeout=300).run_island(MINI_UNSAT, "mini-unsat")
    z3 = tmp_path / "z3.txt"
    z3.write_text("UNSAT" if probe.label == "SAT" else "SAT")  # opposite
    out = tmp_path / "result.json"
    divs = tmp_path / "divergences.json"
    res = validate_island(island_path, z3, out, divs, timeout=300)
    assert res.divergence is True
    entries = __import__("json").loads(divs.read_text())
    assert len(entries) == 1
    assert entries[0]["divergence"] is True
    assert entries[0]["z3_result"] == z3.read_text().strip()


def test_load_readout_checkpoint_missing_is_none():
    assert load_readout_checkpoint(None) is None
    assert load_readout_checkpoint(Path("/nonexistent/readout.joblib")) is None


def test_load_readout_checkpoint_roundtrip(tmp_path):
    import joblib
    clf = ReadoutClassifier(method="logistic", calibrate=False)
    clf.fit(
        np.array([[0.0, 1.0], [1.0, 0.0], [0.2, 0.8], [0.9, 0.1], [0.3, 0.9], [0.8, 0.2]]),
        np.array(["SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT"]),
    )
    ckpt = tmp_path / "readout.joblib"
    joblib.dump(clf, ckpt)
    loaded = load_readout_checkpoint(ckpt)
    assert isinstance(loaded, ReadoutClassifier)
    assert loaded.predict(np.array([0.9, 0.1])) is not None


def test_load_readout_checkpoint_legacy_model(tmp_path):
    import joblib
    clf = ReadoutClassifier(method="logistic", calibrate=False)
    clf.fit(
        np.array([[0.0, 1.0], [1.0, 0.0], [0.2, 0.8], [0.9, 0.1], [0.3, 0.9], [0.8, 0.2]]),
        np.array(["SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT"]),
    )
    ckpt = tmp_path / "legacy.joblib"
    joblib.dump(clf._model, ckpt)  # old format: bare estimator only
    loaded = load_readout_checkpoint(ckpt)
    assert isinstance(loaded, ReadoutClassifier)
    assert loaded._classes == ["SAT", "UNSAT"]

# ── T321: the identity of the MODEL behind a confidence ──
#
# These assert the property that was missing, not the implementation. Each
# names the failure it prevents: T321 recorded `confidence` with nothing
# about which fitted model produced it, so a refit silently rewrote the
# apparent meaning of numbers already written to aes/verification/.


def _fit_readout(features, labels):
    """A fitted readout, calibrated.

    The calibration step is 3-fold, so each class needs >= 3 examples. The
    first draft of these tests used 2 per class and failed with sklearn's
    "Requesting 3-fold cross-validation but provided less than 3 examples" —
    a defect in the fixture, not in the code under test.
    """
    clf = ReadoutClassifier(method="logistic", calibrate=True)
    clf.fit(np.asarray(features, dtype=float), np.asarray(labels))
    return clf


def test_describe_readout_records_fitted_and_hash(tmp_path):
    import hashlib
    import joblib
    from lib.epistemic.flybrainpoc.validator import describe_readout

    X = [[0.0, 1.0], [1.0, 0.0], [0.2, 0.8], [0.9, 0.1],
         [0.1, 0.95], [0.85, 0.15], [0.05, 0.6], [0.95, 0.4]]
    clf = _fit_readout(X, ["SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT"])
    ckpt = tmp_path / "readout.joblib"
    joblib.dump(clf, ckpt)

    d = describe_readout(ckpt, fitted=True)
    assert d["fitted"] is True
    assert d["source"] == "fitted-checkpoint"
    # The hash must be the file's real identity, computable independently.
    expected = hashlib.sha256(ckpt.read_bytes()).hexdigest()
    assert d["sha256"] == expected
    assert d["bytes"] == ckpt.stat().st_size


def test_describe_readout_never_claims_a_hash_for_an_unused_model(tmp_path):
    """The load-bearing case: a hash of a file that was NOT used is a lie.

    A reader comparing two artefacts would see two different hashes and
    conclude the models differ — when the truth is that one of the numbers
    came from the mean-activity fallback and no model was involved at all.
    """
    import joblib
    from lib.epistemic.flybrainpoc.validator import describe_readout

    clf = _fit_readout(
        [[0.0, 1.0], [1.0, 0.0], [0.2, 0.8], [0.9, 0.1],
         [0.1, 0.95], [0.85, 0.15], [0.05, 0.6], [0.95, 0.4]],
        ["SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT"],
    )
    ckpt = tmp_path / "readout.joblib"
    joblib.dump(clf, ckpt)

    d = describe_readout(ckpt, fitted=False)
    assert d["fitted"] is False
    assert d["source"] == "mean-activity-fallback"
    assert d["sha256"] is None, "a hash implies the model produced the number"


def test_describe_readout_marks_absent_checkpoint_rather_than_guessing(tmp_path):
    from lib.epistemic.flybrainpoc.validator import describe_readout

    missing = tmp_path / "nope.joblib"
    d = describe_readout(missing, fitted=False)
    assert d["fitted"] is False
    assert d["sha256"] is None
    assert d["checkpoint"] == str(missing), "must name what it looked for"


def test_describe_readout_handles_no_checkpoint_argument():
    from lib.epistemic.flybrainpoc.validator import describe_readout

    d = describe_readout(None, fitted=False)
    assert d["fitted"] is False
    assert d["checkpoint"] is None
    assert d["sha256"] is None


def test_two_checkpoints_produce_different_identities(tmp_path):
    """The property the whole ticket exists for: a refit is DETECTABLE.

    Not "the function returns a hash" — that a change in model is visible in
    the recorded provenance, which is what makes a stale confidence
    attributable instead of mysterious.
    """
    import joblib
    from lib.epistemic.flybrainpoc.validator import describe_readout

    def _fit(a, b, name):
        clf = _fit_readout(
            [[0.0, 1.0], [1.0, 0.0], [a, b], [b, a], [a, 0.5], [b, 0.5],
             [0.5, a], [0.5, b]],
            ["SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT", "SAT", "UNSAT"],
        )
        p = tmp_path / name
        joblib.dump(clf, p)
        return describe_readout(p, fitted=True)

    first = _fit(0.2, 0.8, "a.joblib")
    second = _fit(0.3, 0.7, "b.joblib")
    assert first["sha256"] != second["sha256"], (
        "a refit must change the recorded identity, otherwise two "
        "confidences from different models look comparable"
    )
