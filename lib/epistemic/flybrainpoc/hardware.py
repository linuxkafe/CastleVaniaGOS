"""hardware.py — Auto-detection of available compute backends.

Detects CUDA (NVIDIA), ROCm (AMD), Metal (Apple Silicon), and CPU availability.
Returns a prioritised list of BackendCapability objects for the reservoir to use.
"""

import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class BackendType(Enum):
    CPU = "cpu"
    CUDA = "cuda"
    ROCM = "rocm"
    METAL = "metal"


@dataclass(frozen=True)
class BackendCapability:
    backend: BackendType
    available: bool
    reason: str = ""
    version: str = ""

    def __bool__(self) -> bool:
        return self.available


def _run(cmd: List[str], timeout: float = 2.0) -> Optional[str]:
    """Run a command, return stdout stripped, or None on failure."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0:
            return res.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _run_status(cmd: List[str], timeout: float = 2.0) -> Optional[subprocess.CompletedProcess]:
    """Run a command and return the full CompletedProcess, or None if absent.

    Unlike ``_run``, this distinguishes "tool not installed" (returns None)
    from "tool present but failed" (returns the process with a non-zero
    returncode). Collapsing those two cases is what let detect_cuda() claim
    a GPU was available just because a toolkit directory existed (T281).
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None


def detect_cuda() -> BackendCapability:
    """Detect NVIDIA CUDA availability via nvidia-smi and driver version."""
    res = _run_status(
        ["nvidia-smi", "--query-gpu=driver_version,name", "--format=csv,noheader"]
    )
    if res is not None and res.returncode == 0:
        out = res.stdout.strip()
        lines = out.split("\n")
        driver = lines[0].split(",")[0].strip() if lines else "unknown"
        gpus = "; ".join(line.split(",")[1].strip() for line in lines if "," in line)
        return BackendCapability(
            BackendType.CUDA,
            available=True,
            reason=f"nvidia-smi OK: {gpus}",
            version=driver,
        )

    cuda_path = os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME")

    if res is not None:
        # nvidia-smi is installed but failed (e.g. driver/library mismatch).
        # A failing nvidia-smi is a NEGATIVE signal — surface the real error
        # instead of falling back to a toolkit-path guess.
        err_lines = ((res.stderr or "") + "\n" + (res.stdout or "")).strip().splitlines()
        detail = err_lines[0] if err_lines else f"exit {res.returncode}"
        return BackendCapability(
            BackendType.CUDA,
            available=False,
            reason=f"nvidia-smi present but failed: {detail}",
            version="broken",
        )

    # nvidia-smi not installed. A CUDA toolkit directory on disk is not a
    # usable GPU runtime — path-only never claims availability.
    if cuda_path and os.path.exists(cuda_path):
        return BackendCapability(
            BackendType.CUDA,
            available=False,
            reason=f"nvidia-smi not found; CUDA_PATH={cuda_path} is path-only (no verified runtime)",
            version="path-only",
        )

    return BackendCapability(
        BackendType.CUDA,
        available=False,
        reason="nvidia-smi not found and no CUDA_PATH",
    )


def detect_rocm() -> BackendCapability:
    """Detect AMD ROCm availability via rocm-smi and HIP runtime."""
    out = _run(["rocm-smi", "--showproductname"])
    if out:
        lines = [line for line in out.split("\n") if "GPU" in line or "Card" in line]
        gpus = "; ".join(lines[:4]) if lines else "detected"
        return BackendCapability(
            BackendType.ROCM,
            available=True,
            reason=f"rocm-smi OK: {gpus}",
            version="rocm",
        )

    # Check HIP runtime library
    hip_paths = [
        "/opt/rocm",
        "/usr/lib/x86_64-linux-gnu/rocm",
        os.environ.get("HIP_PATH", ""),
    ]
    for p in hip_paths:
        if p and os.path.exists(os.path.join(p, "bin", "hipcc")):
            return BackendCapability(
                BackendType.ROCM,
                available=True,
                reason=f"HIP toolchain at {p}",
                version="hip",
            )

    return BackendCapability(
        BackendType.ROCM,
        available=False,
        reason="rocm-smi not found and no HIP toolchain",
    )


def detect_metal() -> BackendCapability:
    """Detect Apple Metal/MPS availability on macOS (Apple Silicon)."""
    if platform.system() != "Darwin":
        return BackendCapability(
            BackendType.METAL,
            available=False,
            reason="not macOS",
        )

    # Check for Apple Silicon (arm64) — Metal Performance Shaders requires M1+
    if platform.machine() != "arm64":
        return BackendCapability(
            BackendType.METAL,
            available=False,
            reason=f"Intel Mac ({platform.machine()}), MPS requires Apple Silicon",
        )

    # macOS version must support MPS (12.3+)
    try:
        macos_ver = tuple(map(int, platform.mac_ver()[0].split(".")))
        if macos_ver < (12, 3):
            return BackendCapability(
                BackendType.METAL,
                available=False,
                reason=f"macOS {platform.mac_ver()[0]} < 12.3, MPS unavailable",
            )
    except Exception:
        pass

    return BackendCapability(
        BackendType.METAL,
        available=True,
        reason="Apple Silicon + macOS 12.3+, MPS available",
        version="mps",
    )


def detect_cpu() -> BackendCapability:
    """CPU backend is always available (Brian2 numpy/cython)."""
    return BackendCapability(
        BackendType.CPU,
        available=True,
        reason="Brian2 numpy/cython backend",
        version="cpu",
    )


def detect_all_backends() -> List[BackendCapability]:
    """Return all backends with availability, ordered by default priority."""
    return [
        detect_cuda(),
        detect_rocm(),
        detect_metal(),
        detect_cpu(),
    ]


def _parse_backend_priority_from_env() -> Optional[List[BackendType]]:
    """Parse backend priority from env var AES_FLYBRAIN_BACKEND_PRIORITY."""
    env_prio = os.environ.get("AES_FLYBRAIN_BACKEND_PRIORITY")
    if env_prio:
        try:
            return [BackendType(p.strip().lower()) for p in env_prio.split(",")]
        except ValueError:
            pass
    return None


def get_best_backend(
    priority: Optional[List[BackendType]] = None,
    force_cpu: bool = False,
) -> BackendCapability:
    """
    Return the best available backend according to priority.

    Args:
        priority: Ordered list of BackendType (default: CUDA > ROCm > Metal > CPU).
                  If None, reads from env var AES_FLYBRAIN_BACKEND_PRIORITY,
                  then defaults to [CUDA, ROCM, METAL, CPU].
        force_cpu: If True, always return CPU backend

    Returns:
        The first available backend in priority order, or CPU as last resort.
    """
    if force_cpu:
        return detect_cpu()

    if priority is None:
        priority = _parse_backend_priority_from_env()
        if priority is None:
            priority = [BackendType.CUDA, BackendType.ROCM, BackendType.METAL, BackendType.CPU]

    all_caps = {cap.backend: cap for cap in detect_all_backends()}

    for bt in priority:
        cap = all_caps.get(bt)
        if cap and cap.available:
            return cap

    # Should never reach here (CPU is always available), but be safe
    return detect_cpu()


def backend_summary() -> str:
    """Human-readable summary of all detected backends."""
    lines = ["Hardware backend detection:"]
    for cap in detect_all_backends():
        status = "✓" if cap.available else "✗"
        lines.append(f"  {status} {cap.backend.value.upper():5} — {cap.reason}")
    return "\n".join(lines)