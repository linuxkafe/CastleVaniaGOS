"""backends.py — Reservoir backend implementations (Strategy pattern).

Each backend implements the same interface so FlyBrainReservoir can delegate
build/simulate without knowing hardware details.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

try:
    import brian2 as b2  # type: ignore[import-not-found]
    _BRIAN2_OK = True
except ImportError:  # pragma: no cover
    b2 = None
    _BRIAN2_OK = False

from lib.epistemic.flybrainpoc.hardware import BackendType

b2: Any = b2  # type: ignore[assignment]

# Constants shared with reservoir.py
READOUT_POOLS = {"mbons": 16, "central_complex": 12, "giant_fiber": 4}
N_SENSORY = 128
SENSORY_SLICES = {"mbons": (0, 43), "central_complex": (43, 86), "giant_fiber": (86, 128)}


class ReservoirBackend(ABC):
    """Abstract interface for a reservoir backend.

    Subclasses must declare whether they actually execute work on the device
    they name, via `executes_on_device` / `device_note`. This exists because
    "the hardware was detected" and "this backend runs on it" are different
    questions, and conflating them is how a CPU run gets reported as a GPU run
    (T320). A backend that is a stub must say so declaratively instead of
    swallowing the error that would reveal it.
    """

    #: True only if simulation actually runs on the named device.
    executes_on_device: bool = False

    #: Human-readable justification for `executes_on_device`, surfaced when a
    #: backend is skipped. Specific enough to distinguish "no hardware" from
    #: "hardware present, backend cannot use it".
    device_note: str = "unspecified"

    @abstractmethod
    def build_trivial(self) -> Any:
        """Build and return a trivial (CPU) LIF network."""
        pass

    @abstractmethod
    def build_full(self, connectome_path: Path) -> Any:
        """Build and return the full connectome network."""
        pass

    @abstractmethod
    def simulate(self, net: Any, duration_ms: float) -> Dict[str, np.ndarray]:
        """Run the network and return per-pool spike counts."""
        pass


class CPUBackend(ReservoirBackend):
    """Brian2 numpy/cython backend — always available, reference implementation."""

    executes_on_device = True
    device_note = "reference backend; runs on the host CPU"

    def __init__(self):
        if not _BRIAN2_OK:
            raise RuntimeError("brian2 is required for CPUBackend (pip install brian2)")

    def build_trivial(self) -> Any:
        """Build the trivial 3-pool LIF network using explicit object list."""
        N_IN = N_SENSORY
        mbon = READOUT_POOLS["mbons"]
        cc = READOUT_POOLS["central_complex"]
        gf = READOUT_POOLS["giant_fiber"]

        S_raw = b2.SpikeGeneratorGroup(
            N_IN, np.zeros(0, dtype=int), np.zeros(0) * b2.ms, name="spikegen"
        )
        S = S_raw

        pool_groups: Dict[str, Any] = {}
        pool_monitors: Dict[str, Any] = {}
        pool_synapses: Dict[str, Any] = {}

        w_map = {"mbons": 0.5, "central_complex": 0.45, "giant_fiber": 0.55}

        for name, N in (("mbons", mbon), ("central_complex", cc), ("giant_fiber", gf)):
            g = b2.NeuronGroup(
                N,
                "dv/dt = -v/tau_m : 1\n tau_m : second (constant)",
                threshold="v > 1.0",
                reset="v = 0.0",
                refractory=5.0 * b2.ms,
                name=f"out_{name}",
            )
            g.tau_m = 15.0 * b2.ms
            pool_groups[name] = g
            pool_monitors[name] = b2.SpikeMonitor(g, name=f"mon_{name}")
            syn = b2.Synapses(S, g, model="w : 1", on_pre="v += w", name=f"syn_{name}")
            slice_start, slice_end = SENSORY_SLICES[name]
            pre = np.arange(slice_start, slice_end)
            post = np.arange(N)
            syn.connect(
                i=np.repeat(pre, len(post)),
                j=np.tile(post, len(pre)),
            )
            syn.w = w_map[name]
            pool_synapses[name] = syn

        objs = [S_raw]
        for name in READOUT_POOLS:
            objs.append(pool_groups[name])
            objs.append(pool_monitors[name])
            objs.append(pool_synapses[name])

        net = b2.Network(objs)
        net.S_raw = S_raw
        net.pools = pool_monitors
        net.pool_groups = pool_groups
        net.pool_synapses = pool_synapses
        net.n_input_neurons = N_IN
        net.S = S
        return net

    def build_full(self, connectome_path: Path) -> Any:
        """REAL_AES_FULL on the CPU reference backend (T326).

        The old NotImplementedError said this "requires a GPU backend". That
        was never true: T325 measured the real 15M-synapse connectome running
        on this CPU in 449 ms at ~1 spike/neuron. The blocker was that nobody
        had written the loader.

        The network is built by `real_connectome.build_full_network`, whose
        model parameters come from the fly-brain reference implementation
        rather than being invented here.
        """
        if not _BRIAN2_OK:
            raise RuntimeError("brian2 is required for REAL_AES_FULL")
        from lib.epistemic.flybrainpoc.real_connectome import (
            build_full_network,
            resolve_checkout,
        )

        checkout = resolve_checkout(Path(connectome_path))
        return build_full_network(checkout)

    def simulate(self, net: Any, duration_ms: float) -> Dict[str, np.ndarray]:
        """Run the network and return per-pool binned spike counts."""
        if not hasattr(net, "pools"):
            raise RuntimeError("Invalid network: missing pools attribute")

        duration = duration_ms * b2.ms
        net.run(duration, report=None)

        bin_ms = 10.0
        n_bins = int(np.ceil(duration_ms / bin_ms))
        out = {}

        for name, mon in net.pools.items():
            src = getattr(mon, "source", None)
            n_neurons = src.N if src is not None else 0
            counts = np.zeros((n_neurons, n_bins), dtype=int)
            if n_neurons == 0:
                out[name] = counts
                continue
            t = np.asarray(mon.t / b2.ms, dtype=float)
            idx = np.asarray(mon.i, dtype=int)
            for tt, ii in zip(t, idx):
                b = min(int(tt // bin_ms), n_bins - 1)
                counts[ii, b] += 1
            out[name] = counts
        return out


def _brian2_cuda_probe() -> Tuple[bool, str]:
    """Report whether the installed brian2 actually exposes a CUDA backend.

    Returns (usable, reason).

    T320: this probe used to be a `try: b2.prefs...cuda_backend = True
    except Exception: pass`, which swallowed a `PreferenceError` and made a CPU
    run indistinguishable from a GPU run. The distinction matters on hosts where
    the GPU is present but the simulator cannot use it — which is *this* host:
    a working RTX 5090 and a brian2 with no CUDA support at all.
    """
    if not _BRIAN2_OK:
        return False, "brian2 not importable"
    prefs = b2.prefs.devices.get("cpp_standalone")
    if prefs is None or "cuda_backend" not in prefs:
        return False, (
            f"brian2 {getattr(b2, '__version__', '?')} has no CUDA backend "
            f"(no 'cpp_standalone.cuda_backend' preference); CUDA support was "
            f"moved out of brian2 — use geobrian/brian2cuda, which are not "
            f"installed"
        )
    return True, f"brian2 {getattr(b2, '__version__', '?')} exposes cpp_standalone.cuda_backend"


class CUDABackend(ReservoirBackend):
    """NVIDIA CUDA backend for brian2.

    NOTE (T320): as of brian2 2.10.1 this is a **stub**. brian2 no longer ships
    a CUDA backend (no `.cu` kernels, no `cuda_backend` preference), so this
    class cannot run anything on the GPU; it delegates to the CPU backend for
    the trivial unit. It is kept constructible on purpose: the T270 requirement is
    that the AES runs on *any* hardware, so auto-detection must degrade
    gracefully rather than fail. What T320 fixes is not the degradation but the
    silence — `executes_on_device` is False and `device_note` says why, so
    auto-detection can skip this backend and report the real reason.

    A real CUDA path means geobrian or brian2cuda (neither installed). That is
    deliberately out of scope here: it is engine choice plus measurement, not a
    correctness fix.
    """

    # Class-level values are pessimistic: an unprobed backend must not claim it
    # runs on the GPU. `__init__` refines this per instance from the probe.
    executes_on_device = False
    device_note = "unprobed: construct the backend to learn whether CUDA is usable"

    def __init__(self):
        if not _BRIAN2_OK:
            raise RuntimeError("brian2 is required for CUDABackend")
        self._cuda_usable, self._cuda_reason = _brian2_cuda_probe()
        self.executes_on_device = self._cuda_usable
        self.device_note = self._cuda_reason

    def build_trivial(self) -> Any:
        # Not a CUDA run: brian2 has no CUDA backend. Delegates to the CPU
        # backend, and says so via executes_on_device/device_note rather than
        # pretending a preference was set (T320).
        if self._cuda_usable:
            # Would enable the CUDA target here, once brian2 has one.
            pass
        cpu = CPUBackend()
        return cpu.build_trivial()

    def build_full(self, connectome_path: Path) -> Any:
        raise NotImplementedError(
            "REAL_AES_FULL connectome loading is not implemented for the CUDA "
            "backend (T326). The CPU reference backend does implement it — see "
            "CPUBackend.build_full. The blocker here is the backend, not the "
            "data: the FlyWire checkout is public and this is not a hardware "
            "problem (T325 measured it on CPU). Uses geobrain/brian2cuda for "
            "the GPU path; neither is installed."
        )

    def simulate(self, net: Any, duration_ms: float) -> Dict[str, np.ndarray]:
        cpu = CPUBackend()
        return cpu.simulate(net, duration_ms)


class ROCmBackend(ReservoirBackend):
    """AMD ROCm/HIP backend via Brian2 cpp_standalone (stub until hardware available)."""

    executes_on_device = False
    device_note = (
        "stub: brian2 has no ROCm/HIP backend, so nothing runs on the AMD GPU"
    )

    def __init__(self):
        if not _BRIAN2_OK:
            raise RuntimeError("brian2 is required for ROCmBackend")

    def build_trivial(self) -> Any:
        # Stub: delegate to CPU backend
        cpu = CPUBackend()
        return cpu.build_trivial()

    def build_full(self, connectome_path: Path) -> Any:
        raise NotImplementedError(
            "ROCM backend not yet implemented — requires AMD GPU with ROCm 5.x+ "
            "and Brian2 cpp_standalone HIP support."
        )

    def simulate(self, net: Any, duration_ms: float) -> Dict[str, np.ndarray]:
        cpu = CPUBackend()
        return cpu.simulate(net, duration_ms)


class MetalBackend(ReservoirBackend):
    """Apple Metal/MPS backend (stub until validated on Apple Silicon)."""

    executes_on_device = False
    device_note = (
        "stub: brian2 has no Metal/MPS backend, so nothing runs on the Apple GPU"
    )

    def __init__(self):
        if not _BRIAN2_OK:
            raise RuntimeError("brian2 is required for MetalBackend")

    def build_trivial(self) -> Any:
        cpu = CPUBackend()
        return cpu.build_trivial()

    def build_full(self, connectome_path: Path) -> Any:
        raise NotImplementedError(
            "Metal backend not yet implemented — requires Apple Silicon M1+ "
            "with MPS or Brian2 Metal support."
        )

    def simulate(self, net: Any, duration_ms: float) -> Dict[str, np.ndarray]:
        cpu = CPUBackend()
        return cpu.simulate(net, duration_ms)


BACKEND_REGISTRY = {
    BackendType.CPU: CPUBackend,
    BackendType.CUDA: CUDABackend,
    BackendType.ROCM: ROCmBackend,
    BackendType.METAL: MetalBackend,
}


def get_backend_instance(backend_type: BackendType) -> ReservoirBackend:
    """Factory function to get a backend instance."""
    cls = BACKEND_REGISTRY.get(backend_type)
    if cls is None:
        raise ValueError(f"No backend registered for {backend_type}")
    return cls()