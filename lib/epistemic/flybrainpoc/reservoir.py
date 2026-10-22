"""reservoir.py — Hardware-agnostic Brian2 LIF reservoir wrapper (T-4/T270).

Two tiers:
  - REAL_AES_FULL: drop-in path for the eonsystemspbc/fly-brain connectome
    (138k neurons, 15.1M synapses, Brian2 backends, CUDA/ROCm/Metal on GPU).

    T325: the "~5M synapses" figure that lived here was wrong by 3x. Measured
    from the actual FlyWire v783 parquet (eonsystemspbc/fly-brain): 15,091,983
    synapses over 138,639 neurons, mean in-degree 110, max 10,356.
  - TRIVIAL_UNIT: a minimal LIF network used for the integration test and
    for running late-stage experiments without pulling the full connectome.

The reservoir is FIXED (no learning). It turns structured input spike
trains into high-dimensional temporally-structured population activity.

Backend selection:
  - backend="auto" (default): pick the highest-priority backend that actually
    EXECUTES on its own device (CUDA > ROCm > Metal > CPU by default). As of
    brian2 2.10.1 only CPU qualifies — the GPU backends are stubs (T320), so
    auto-detection returns CPU even on a host with a working GPU.
  - backend="cpu"/"cuda"/"rocm"/"metal": explicit backend (strict=False falls back)
  - backend="cuda" with strict=True: fails if CUDA cannot run the simulation.
    This covers BOTH "no CUDA hardware" and "hardware present, but the
    installed simulator has no CUDA backend" — the second case used to pass
    silently and run on the CPU.
  - The reason for any fallback is recorded in BACKEND_FALLBACK_REASON and
    propagated into the result by validator.py, so a run's provenance does not
    depend on a log line someone has to remember to read.
  - Env var AES_FLYBRAIN_BACKEND overrides
  - Config .aes/config.mk AES_FLYBRAIN_BACKEND_PRIORITY sets priority order

"Hardware detection" and "can run here" are deliberately separate questions:
hardware.py answers the first, and as of T320 nothing treats the second as
implied by the first.
"""

import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import brian2 as b2  # type: ignore[import-not-found]
    _BRIAN2_OK = True
except ImportError:  # pragma: no cover — CI without optional dep
    b2 = None
    _BRIAN2_OK = False

from lib.epistemic.flybrainpoc.hardware import (
    BackendCapability,
    BackendType,
    detect_all_backends,
    get_best_backend,
)
from lib.epistemic.flybrainpoc.backends import (
    ReservoirBackend,
    get_backend_instance,
)

b2: Any = b2  # type: ignore[assignment]

logger = logging.getLogger(__name__)


READOUT_POOLS = {
    "mbons": 16,
    "central_complex": 12,
    "giant_fiber": 4,
}

N_SENSORY = 128

SENSORY_SLICES = {
    "mbons": (0, 43),
    "central_complex": (43, 86),
    "giant_fiber": (86, 128),
}


def _parse_backend_priority() -> List[BackendType]:
    """Parse backend priority from env or config.mk."""
    # Env var takes precedence
    env_prio = os.environ.get("AES_FLYBRAIN_BACKEND_PRIORITY")
    if env_prio:
        try:
            return [BackendType(p.strip().lower()) for p in env_prio.split(",")]
        except ValueError:
            pass
    # Fallback to config.mk (simple grep)
    config_path = Path(".aes/config.mk")
    if config_path.exists():
        try:
            for line in config_path.read_text().splitlines():
                if line.strip().startswith("AES_FLYBRAIN_BACKEND_PRIORITY"):
                    val = line.split("=", 1)[1].strip()
                    return [BackendType(p.strip().lower()) for p in val.split(",")]
        except Exception:
            pass
    # Default priority
    return [BackendType.CUDA, BackendType.ROCM, BackendType.METAL, BackendType.CPU]


def _force_cpu() -> bool:
    """Check if CPU-only mode is forced via env or config."""
    if os.environ.get("AES_FLYBRAIN_FORCE_CPU", "0") == "1":
        return True
    config_path = Path(".aes/config.mk")
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if line.strip().startswith("AES_FLYBRAIN_FORCE_CPU"):
                val = line.split("=", 1)[1].strip()
                if val == "1":
                    return True
    return False


def _resolve_backend(backend: str, strict: bool) -> BackendCapability:
    """Resolve backend string to BackendCapability.

    T320: hardware detection answers "is the device there?", which is not the
    same question as "can this simulator run on it?". `detect_cuda()` reports a
    working RTX 5090 while the installed brian2 has no CUDA backend at all, so
    resolving on hardware alone selected CUDA and produced a CPU run wearing
    CUDA's name. Selection now asks the backend class whether it executes on its
    own device, and a skipped candidate is reported through
    `BACKEND_FALLBACK_REASON` so the reason survives into the result.
    """
    if backend == "auto":
        priority = _parse_backend_priority()
        force = _force_cpu()
        return _select_runnable(get_best_backend(priority=priority, force_cpu=force), strict)

    # Explicit backend requested
    try:
        bt = BackendType(backend.lower())
    except ValueError:
        raise ValueError(f"Unknown backend: {backend}. Choose from: auto, cpu, cuda, rocm, metal")

    all_caps = {cap.backend: cap for cap in detect_all_backends()}
    cap = all_caps.get(bt)
    if cap is None:
        raise ValueError(f"Backend {backend} not recognised")

    if not cap.available:
        if strict:
            raise RuntimeError(
                f"Explicit backend '{backend}' requested but not available: {cap.reason}. "
                f"Use backend='auto' for graceful fallback or strict=False."
            )
        # Graceful fallback to best available
        priority = _parse_backend_priority()
        return _select_runnable(get_best_backend(priority=priority, force_cpu=False), strict)

    # Hardware is present — but is the requested backend able to use it? This is
    # the branch that had no test and no behaviour: on a host with a working
    # GPU and a simulator without a GPU backend, the old code returned the CUDA
    # capability and ran on the CPU (T320).
    impl = get_backend_instance(bt)
    if not getattr(impl, "executes_on_device", False):
        reason = f"hardware present ({cap.reason}) yet unusable: {impl.device_note}"
        if strict:
            raise RuntimeError(
                f"Explicit backend '{backend}' requested with strict=True, and it is "
                f"{reason}. Strict mode refuses to run on a device other than the one "
                f"requested — it will not silently fall back."
            )
        logger.warning(
            "flybrain: backend '%s' is not runnable (%s) — falling back.",
            backend, reason,
        )
        _note_fallback(bt, reason)
        return _select_runnable(
            get_best_backend(priority=_parse_backend_priority(), force_cpu=False), strict
        )

    return cap


#: Why the requested backend was skipped, if it was. Read via
#: `get_backend_fallback_reason()` (not by importing this name) so consumers see
#: the value at call time — importing the global binds it once, which silently
#: pins None. T320 learned that the hard way.
BACKEND_FALLBACK_REASON: Optional[str] = None


def get_backend_fallback_reason() -> Optional[str]:
    """Why the requested backend was skipped, or None if none was."""
    return BACKEND_FALLBACK_REASON


def _note_fallback(backend_type: BackendType, reason: str) -> None:
    global BACKEND_FALLBACK_REASON
    BACKEND_FALLBACK_REASON = f"{backend_type.value}: {reason}"


def _select_runnable(cap: BackendCapability, strict: bool) -> BackendCapability:
    """Return `cap` if its backend runs on its own device, else the next that does.

    CPU always qualifies (it is the reference backend), so this terminates.
    """
    impl = get_backend_instance(cap.backend)
    if getattr(impl, "executes_on_device", False):
        return cap

    reason = f"backend '{cap.backend.value}' cannot execute on its own device: {impl.device_note}"
    if strict:
        raise RuntimeError(f"strict mode: {reason}")
    logger.warning("flybrain: %s — falling back to CPU.", reason)
    _note_fallback(cap.backend, reason)
    return BackendCapability(BackendType.CPU, True, f"fallback: {reason}")


class FlyBrainReservoir:
    """Reservoir computing host around a LIF network with hardware-agnostic backend."""

    def __init__(
        self,
        backend: str = "auto",
        model: str = "TRIVIAL_UNIT",
        strict: bool = False,
    ):
        """
        Args:
            backend: "auto" (default), "cpu", "cuda", "rocm", "metal"
            model: "TRIVIAL_UNIT" or "REAL_AES_FULL"
            strict: if True, explicit backend must be available; if False, falls back gracefully
        """
        self.backend_str = backend
        self.model = model
        self.strict = strict
        self.backend_capability: Optional[BackendCapability] = None
        self.backend_impl: Optional[ReservoirBackend] = None
        self.net: Optional[Any] = None
        self.cold_start_ms: float = 0.0
        self._loaded = False

    def load(self) -> None:
        if not _BRIAN2_OK:
            raise ImportError("brian2 is required for the reservoir (pip install brian2)")
        if self._loaded:
            return

        t0 = time.perf_counter()
        b2.start_scope()

        # Resolve backend
        self.backend_capability = _resolve_backend(self.backend_str, self.strict)
        self.backend_impl = get_backend_instance(self.backend_capability.backend)

        # Build the network
        if self.model == "TRIVIAL_UNIT":
            self.net = self.backend_impl.build_trivial()
            self.n_input_neurons = self.net.n_input_neurons
        elif self.model == "REAL_AES_FULL":
            # Try to build full connectome; on failure, log warning and fall back
            connectome_path = Path("eonsystemspbc/fly-brain")  # convention
            try:
                self.net = self.backend_impl.build_full(connectome_path)
            except (NotImplementedError, FileNotFoundError, RuntimeError, ImportError) as e:
                # Graceful fallback: warn and use trivial unit.
                #
                # T326: the set of caught errors grew, and that is a correction
                # rather than a convenience. `build_full` used to raise
                # NotImplementedError on every backend, so that was the only
                # thing that could go wrong. Now the loader is real, and the
                # likeliest failure is not an unsupported backend at all — it
                # is the FlyWire parquet not being on this machine, which is
                # FileNotFoundError. Catching only NotImplementedError would
                # have turned "no optional data" into a hard crash, breaking
                # the T270 guarantee that the PoC runs anywhere.
                import warnings
                warnings.warn(
                    f"REAL_AES_FULL not available on {self.backend_capability.backend.value} "
                    f"({self.backend_capability.reason}): {type(e).__name__}: {e}. "
                    f"Falling back to TRIVIAL_UNIT.",
                    UserWarning,
                    stacklevel=2,
                )
                self.net = self.backend_impl.build_trivial()
                self.n_input_neurons = self.net.n_input_neurons
                self.model = "TRIVIAL_UNIT"  # record actual model used
        else:
            raise ValueError(f"Unknown model: {self.model}")

        self.cold_start_ms = (time.perf_counter() - t0) * 1000.0
        self._loaded = True

    def inject(self, spike_trains: Dict[int, "np.ndarray"]) -> None:
        """Replace the spike generator's events with the encoded claim trains."""
        if not self._loaded:
            self.load()

        if not hasattr(self.net, "S_raw"):
            raise RuntimeError("Network missing S_raw (spike generator)")

        neuron_idx = np.array(sorted(spike_trains.keys()), dtype=np.int32)
        times = (
            np.concatenate(
                [np.asarray(t, dtype=float) for t in spike_trains.values()]
            )
            if spike_trains
            else np.zeros(0)
        )
        if len(neuron_idx) == 0:
            neuron_idx = np.zeros(0, dtype=np.int32)
            times = np.zeros(0)

        dt_ms = 0.1
        pairs = []
        for n_int, t in zip(
            neuron_idx.tolist(),
            [np.asarray(spike_trains[int(n)], dtype=float) for n in neuron_idx],
        ):
            for tt in t:
                pairs.append((n_int, round(float(tt) / dt_ms) * dt_ms))
        if pairs:
            arr = np.array(pairs, dtype=[("n", np.int32), ("t", np.float64)])
            arr = np.unique(arr)
            neuron_idx = arr["n"]
            times = arr["t"] * b2.ms
        else:
            neuron_idx = np.zeros(0, dtype=np.int32)
            times = np.zeros(0) * b2.ms
        self.net.S_raw.set_spikes(neuron_idx, times)

    def simulate(self, duration_ms: float) -> Dict[str, "np.ndarray"]:
        """Run the reservoir and return per-pool spike counts."""
        if not self._loaded:
            self.load()

        if self.backend_impl is None:
            raise RuntimeError("Backend not initialised — call load() first")

        return self.backend_impl.simulate(self.net, duration_ms)

    def backend_summary(self) -> str:
        """Return a human-readable summary of the selected backend."""
        if self.backend_capability is None:
            return "Backend not yet resolved (call load() first)"
        cap = self.backend_capability
        status = "✓" if cap.available else "✗"
        fallback = ""
        if self.backend_str != "auto":
            try:
                requested = BackendType(self.backend_str.lower())
                if cap.backend != requested:
                    fallback = " [FALLBACK]"
            except ValueError:
                pass
        return (
            f"FlyBrainReservoir backend: {cap.backend.value.upper()} "
            f"({status}) — {cap.reason}"
            f"{fallback}"
        )


def is_available() -> bool:
    return _BRIAN2_OK


def platform_summary() -> str:
    return f"{platform.python_implementation()} {platform.python_version()} on {platform.machine()}"