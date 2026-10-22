"""Backend runnability and honest reporting — T320.

The gap these tests cover is the one T270's AC-4 claimed to cover but did not:
"hardware present, but the installed simulator cannot use it". Every existing
test mocks the device as *absent*, so the branch that actually misbehaves —
GPU detected, brian2 without a CUDA backend, run proceeds on the CPU wearing
CUDA's name — had no test at all.

Note the distinction these tests insist on. A test asserting "the chosen
backend is not CUDA" would also pass in a world where CUDA quietly vanished
from the registry. That is the wrong world to pass in. So the assertions check
the REASON: the fallback must be attributable to the simulator lacking a
backend, not to missing hardware. The difference between those two strings is
the whole content of the fix.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lib.epistemic.flybrainpoc.backends import (  # noqa: E402
    BACKEND_REGISTRY,
    CPUBackend,
    CUDABackend,
    _brian2_cuda_probe,
    get_backend_instance,
)
from lib.epistemic.flybrainpoc.hardware import BackendCapability, BackendType  # noqa: E402


class TestBrian2CudaProbe:
    """The probe is the thing that used to be a swallowed exception."""

    def test_probe_reports_a_reason_never_raises(self):
        usable, reason = _brian2_cuda_probe()
        assert isinstance(usable, bool)
        # Whether or not brian2 gains CUDA support, a reason must exist and
        # must name brian2. A silent probe is the defect this replaces.
        assert "brian2" in reason.lower()

    def test_probe_does_not_swallow_by_assigning(self):
        """A usable probe must be a real check, not 'we tried and passed'.

        The original code assigned a preference inside try/except and ignored
        the result. Here we assert that when the preference is missing, the
        probe says so — the failure has to be legible.
        """
        b2 = pytest.importorskip("brian2")
        prefs = b2.prefs.devices.get("cpp_standalone")
        has_pref = prefs is not None and "cuda_backend" in prefs
        usable, reason = _brian2_cuda_probe()
        assert usable == has_pref
        if not has_pref:
            assert "no CUDA backend" in reason


class TestExecutesOnDevice:
    def test_cpu_backend_executes_on_device(self):
        assert CPUBackend.executes_on_device is True

    def test_cuda_backend_declares_honestly(self):
        b = CUDABackend()
        usable, reason = _brian2_cuda_probe()
        # Whatever brian2 does, the declaration must match the probe.
        assert b.executes_on_device == usable
        assert b.device_note == reason

    def test_every_registered_backend_declares_itself(self):
        """No backend may inherit the abstract default silently."""
        for name, cls in BACKEND_REGISTRY.items():
            assert "executes_on_device" in vars(cls), (
                f"{cls.__name__} does not declare executes_on_device — "
                f"selection cannot tell a real backend from a stub"
            )
            assert vars(cls).get("device_note", "unspecified") != "unspecified", (
                f"{cls.__name__} must explain why it does or does not run on device"
            )


class TestSelectionPrefersRunnableBackends:
    """The branch T270 never tested: hardware present, backend unusable."""

    def test_auto_skips_cuda_when_brian2_cannot_use_it(self):
        from lib.epistemic.flybrainpoc import reservoir as R

        usable, _ = _brian2_cuda_probe()
        if usable:
            pytest.skip("brian2 has a CUDA backend; this host is not the case under test")

        fake_cuda = BackendCapability(BackendType.CUDA, True, "nvidia-smi OK: NVIDIA GeForce RTX 5090")
        with patch.object(R, "get_best_backend", return_value=fake_cuda):
            cap = R._select_runnable(fake_cuda, strict=False)

        assert cap.backend is BackendType.CPU
        # The reason must name the simulator, not missing hardware. A fallback
        # attributed to "no GPU" on a host that has one is a second false
        # provenance claim.
        assert R.BACKEND_FALLBACK_REASON is not None
        assert "brian2" in R.BACKEND_FALLBACK_REASON

    def test_strict_refuses_instead_of_silently_falling_back(self):
        from lib.epistemic.flybrainpoc import reservoir as R

        usable, _ = _brian2_cuda_probe()
        if usable:
            pytest.skip("brian2 has a CUDA backend; nothing to refuse")

        fake_cuda = BackendCapability(BackendType.CUDA, True, "nvidia-smi OK: NVIDIA GeForce RTX 5090")
        with patch.object(R, "get_best_backend", return_value=fake_cuda):
            with pytest.raises(RuntimeError, match="cannot execute on its own device"):
                R._select_runnable(fake_cuda, strict=True)

    def test_explicit_cuda_strict_true_fails_on_unusable_backend(self):
        """AC-4 of T270, for the branch that was never verified."""
        from lib.epistemic.flybrainpoc import reservoir as R

        usable, _ = _brian2_cuda_probe()
        if usable:
            pytest.skip("brian2 has a CUDA backend; nothing to fail")

        caps = [
            BackendCapability(BackendType.CUDA, True, "nvidia-smi OK: NVIDIA GeForce RTX 5090"),
            BackendCapability(BackendType.CPU, True, "always"),
        ]
        with patch.object(R, "detect_all_backends", return_value=caps):
            with pytest.raises(RuntimeError, match="yet unusable"):
                R._resolve_backend("cuda", strict=True)

    def test_explicit_cuda_non_strict_falls_back_and_records_reason(self):
        from lib.epistemic.flybrainpoc import reservoir as R

        usable, _ = _brian2_cuda_probe()
        if usable:
            pytest.skip("brian2 has a CUDA backend; nothing to fall back from")

        R.BACKEND_FALLBACK_REASON = None
        caps = [
            BackendCapability(BackendType.CUDA, True, "nvidia-smi OK: NVIDIA GeForce RTX 5090"),
            BackendCapability(BackendType.CPU, True, "always"),
        ]
        with patch.object(R, "detect_all_backends", return_value=caps):
            cap = R._resolve_backend("cuda", strict=False)

        assert cap.backend is BackendType.CPU
        assert R.BACKEND_FALLBACK_REASON is not None

    def test_fallback_reason_is_read_at_call_time(self):
        """Regression on a bug this ticket introduced and then fixed.

        The first cut of the fix had `validator.py` do
        `from ...reservoir import BACKEND_FALLBACK_REASON`, which binds the
        value at import time and pins None forever. The symptom looked exactly
        like the original defect: a run that fell back, reporting no reason.
        Consumers must go through the accessor.
        """
        from lib.epistemic.flybrainpoc import reservoir as R

        assert R.get_backend_fallback_reason() == R.BACKEND_FALLBACK_REASON

        usable, _ = _brian2_cuda_probe()
        if usable:
            pytest.skip("brian2 has a CUDA backend; nothing to fall back from")

        R.BACKEND_FALLBACK_REASON = None
        fake_cuda = BackendCapability(BackendType.CUDA, True, "nvidia-smi OK: NVIDIA GeForce RTX 5090")
        with patch.object(R, "get_best_backend", return_value=fake_cuda):
            R._select_runnable(fake_cuda, strict=False)

        # The accessor must see the update; a stale import binding would not.
        assert R.get_backend_fallback_reason() is not None
        assert "brian2" in R.get_backend_fallback_reason()

    def test_cpu_is_always_accepted(self):
        """Termination: the reference backend qualifies, so selection ends."""
        from lib.epistemic.flybrainpoc import reservoir as R

        cpu_cap = BackendCapability(BackendType.CPU, True, "always")
        assert R._select_runnable(cpu_cap, strict=False) is cpu_cap


class TestFactoryDoesNotHideStubs:
    def test_get_backend_instance_returns_declared_backend(self):
        b = get_backend_instance(BackendType.CUDA)
        assert isinstance(b, CUDABackend)
        # Constructing must not be a lie: if it cannot run on the GPU it has to
        # say so on the instance, not only in a module docstring.
        assert isinstance(b.executes_on_device, bool)
