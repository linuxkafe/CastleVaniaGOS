# FlyBrainPoc — fly-brain GMIF co-processor (T269 + T270, RFC 002)

A fixed reservoir-computing pipeline (encoder → LIF reservoir → linear readout)
that gives AES a **second, structurally independent verdict** on island
graphs, alongside LLM formalization + Z3 SAT. It is *not* a logic solver: it
is a fast, trainable pre-filter that surfaces **divergences** — cases where
the fly-brain and Z3 disagree on a non-trivial graph — as adversarial flags
for human/LLM root-cause review.

## Pipeline

```
island YAML ──▶ Encoder ──▶ Spike trains ──▶ LIF reservoir ──▶ binned counts ──▶ readout ──▶ SAT/UNSAT
                  │            (128 input            (TRIVIAL_UNIT / GPU:                 (logistic/      + confidence
                  │             sensory neurons)       REAL_AES_FULL)                XGBoost)        + divergence
                  ▼                                   mbons / central_complex /                              vs Z3
               rate+timing:                     giant_fiber pools)              fixed weights (no learning)
               anti-phase contradiction,        w = 0.45…0.55, τ=15ms, v_thr=1.0
               causal echo (implies/supports)
```

- **Encoder** (`encoder.py`): maps claims to positional sensory slots
  (`index % 128`, not hash — the contradiction pair must land in the same
  readout channels on every island). Contradiction claims drive **anti-phase**
  windows (mutual-exclusivity signature, binocular-rivalry rationale);
  implies/supports targets get a delayed **echo** burst encoding edge strength.
  `rate_only` mode disables all timing → all-SAT ablation baseline.
- **Reservoir** (`reservoir.py`): 128-neuron input `SpikeGeneratorGroup` → 3
  LIF pools (`mbons` 16, `central_complex` 12, `giant_fiber` 4) with
  slice-specific afferents. Weights tuned **sub-threshold** so a single
  sustained claim sits below threshold and only 2+ overlapping claims fire —
  otherwise pools pin at their refractory ceiling and SAT/UNSAT become
  indistinguishable.
  - **Hardware-agnostic backend** (T270): auto-detects CUDA / ROCm / Metal / CPU
    via `hardware.py`; strategy pattern in `backends.py` (`CPUBackend`,
    `CUDABackend`, `ROCmBackend`, `MetalBackend`).
  - `TRIVIAL_UNIT` (brian2 CPU, this PoC); `REAL_AES_FULL` (138k-neuron
    fly-brain connectome, needs GPU backend).
  - Graceful fallback: `REAL_AES_FULL` on CPU warns + falls back to
    `TRIVIAL_UNIT` (no exception).
- **Readout** (`readout.py`): LogisticRegression (+ XGBoost alternative),
  calibrated; 5-fold CV balanced accuracy. Only trainable component.
- **Validator** (`validator.py`): orchestrates encode→simulate→classify→compare.
  Isolation protocol: a **fresh reservoir per island** (brian2 SpikeMonitors
  accumulate across runs; reuse destroys the signal).
- **Gate** (`scripts/gmif-check-flybrain.sh`, `make gmif-check-flybrain`):
  async, non-blocking (SC-4). Not a dependency of `make check`. A divergence
  exits 1 and appends to `aes/graph/flybrain-divergences.json` for
  self-ticket/learning hooks.

## Hardware-Agnostic Backend (T270)

| Backend | Detection | Priority (default) |
|---------|-----------|-------------------|
| **CUDA** | `nvidia-smi` + driver | 1 |
| **ROCm** | `rocm-smi` + HIP toolchain | 2 |
| **Metal/MPS** | macOS 12.3+ on arm64 | 3 |
| **CPU** | Brian2 numpy/cython | 4 (always available) |

**Config** (`.aes/config.mk`):
```makefile
AES_FLYBRAIN_BACKEND_PRIORITY = cuda,rocm,metal,cpu
AES_FLYBRAIN_FORCE_CPU = 0
```
**Env override:** `AES_FLYBRAIN_BACKEND_PRIORITY=metal,cpu,rocm,cuda`  
**Force CPU:** `AES_FLYBRAIN_FORCE_CPU=1` or `backend="cpu"` in code.  
**Strict mode:** `FlyBrainReservoir(backend="cuda", strict=True)` → fails fast.

## Usage

```bash
# generate the synthetic benchmark set (1000 islands, 500 SAT + 500 UNSAT)
python3 scripts/generate-synthetic-islands.py --count 1000 --seed 42

# SC-1 / SC-2 benchmark (fits + checkpoints the readout)
python3 scripts/flybrain-benchmark.py            # full run (~9 min on CPU)
python3 scripts/flybrain-benchmark.py --limit 60 # quick de-risk

# async gate on a real island (needs Z3 result sidecar)
make gmif-check-flybrain ISLAND=aes/graph/<id>.yaml Z3_RESULT=<z3-out>
make gmif-check-flybrain                          # synthetic self-check
```

## Results (synthetic benchmark, seed 42, reproducible per-island seeding)

| Metric | Value |
|---|---|
| Balanced accuracy (5-fold CV, 1000 islands) | **0.965** |
| UNSAT recall (contradiction detection) | **0.968** |
| SC-1 threshold | ≥ 0.80 ✅ |
| Mean per-island latency (brian2 CPU) | 0.55 s |

**Key Findings:**

1. **Temporal structure is the primary signal carrier** — Even with hash layout (randomized positions), `rate+timing` achieves 0.80–0.86 accuracy. The anti-phase/echo temporal structure carries the signal.

2. **Positional encoding provides ~15% boost** — Positional layout adds ~0.15 accuracy on top of the temporal structure (0.95 vs 0.80–0.86).

3. **Rate-only ablation confirms temporal structure is necessary** — Both layouts drop to chance (~0.50) when timing is removed.

4. **Hash layout is NOT chance level** — 0.80–0.86 accuracy proves the temporal structure itself is the primary signal carrier, not positional alignment.

- This is a **stand-in** reservoir, not the fly-brain. The scientific claim of
  RFC 002 is that temporal-recurrent neural processing can *separate*
  contradiction graphs from implication chains in a fixed non-learned medium —
  demonstrated here. The full-connectome version (`REAL_AES_FULL`) remains the
  scaled-up validation and requires a GPU box (CUDA/ROCm/Metal).
- The positional encoding is a deliberately chosen inductive bias; ablation
  against a hash-based layout (not linear-detectable) is an open test.
- `n_run=1` per island (seeded); RFC's `n_run=8` ensemble is deferred to the
  GPU backend where cost is acceptable.
- GPU backends (CUDA/ROCm/Metal) currently stub to CPUBackend; ready for
  GPU implementation when hardware available.