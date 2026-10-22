"""test_hardware.py — Tests for hardware auto-detection and backend selection (T270)."""

import os
from unittest.mock import patch

import pytest

from lib.epistemic.flybrainpoc.hardware import (
    BackendType,
    BackendCapability,
    detect_cuda,
    detect_rocm,
    detect_metal,
    detect_cpu,
    detect_all_backends,
    get_best_backend,
    backend_summary,
)


class TestHardwareDetection:
    """Test hardware backend detection with mocked subprocess."""

    def test_detect_cpu_always_available(self):
        cap = detect_cpu()
        assert cap.backend == BackendType.CPU
        assert cap.available is True
        assert "Brian2" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware._run_status")
    def test_detect_cuda_with_nvidia_smi(self, mock_run):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(
            [],
            0,
            stdout="535.154.05, NVIDIA GeForce RTX 4090\n535.154.05, NVIDIA A100",
            stderr="",
        )
        cap = detect_cuda()
        assert cap.backend == BackendType.CUDA
        assert cap.available is True
        assert "RTX 4090" in cap.reason
        assert cap.version == "535.154.05"

    @patch("lib.epistemic.flybrainpoc.hardware._run_status")
    def test_detect_cuda_not_found(self, mock_run):
        mock_run.return_value = None
        # Also mock CUDA_PATH to be unset
        with patch.dict(os.environ, {"CUDA_PATH": "", "CUDA_HOME": ""}, clear=False):
            cap = detect_cuda()
        assert cap.backend == BackendType.CUDA
        assert cap.available is False
        assert "nvidia-smi not found" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware._run_status")
    def test_detect_cuda_present_but_broken_driver(self, mock_run):
        # nvidia-smi installed but errors (driver/library mismatch) → NOT
        # available, even when CUDA_PATH exists: a toolkit dir is not a GPU.
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(
            [],
            1,
            stdout="",
            stderr="Failed to initialize NVML: Driver/library version mismatch",
        )
        with patch.dict(os.environ, {"CUDA_PATH": "/usr/local/cuda-13", "CUDA_HOME": ""}, clear=False):
            cap = detect_cuda()
        assert cap.backend == BackendType.CUDA
        assert cap.available is False
        assert cap.version == "broken"
        assert "Driver/library" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware._run_status")
    def test_detect_cuda_path_only_not_available(self, mock_run, tmp_path):
        # nvidia-smi absent but toolkit dir on disk → path-only is NOT
        # executable availability (regression for T281).
        #
        # The toolkit dir must actually be created. This test used to point
        # CUDA_PATH at the literal "/usr/local/cuda-13" and rely on it existing
        # on the developer's machine — it passed here and failed on CI with
        # `assert '' == 'path-only'`, because detect_cuda() requires
        # os.path.exists(cuda_path). A test that only exercises its branch on
        # machines that happen to have CUDA 13 installed is not testing the
        # branch at all (T309).
        mock_run.return_value = None
        cuda_dir = tmp_path / "cuda-13"
        cuda_dir.mkdir()
        with patch.dict(os.environ, {"CUDA_PATH": str(cuda_dir), "CUDA_HOME": ""}, clear=False):
            cap = detect_cuda()
        assert cap.backend == BackendType.CUDA
        assert cap.available is False
        assert cap.version == "path-only"
        assert "path-only" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware._run")
    def test_detect_rocm_with_rocm_smi(self, mock_run):
        mock_run.return_value = "GPU 0: AMD Radeon RX 7900 XTX\nGPU 1: AMD Radeon Pro W7900"
        cap = detect_rocm()
        assert cap.backend == BackendType.ROCM
        assert cap.available is True
        assert "RX 7900" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware._run")
    def test_detect_rocm_not_found(self, mock_run):
        mock_run.return_value = None
        with patch.dict(os.environ, {"HIP_PATH": ""}, clear=False):
            cap = detect_rocm()
        assert cap.backend == BackendType.ROCM
        assert cap.available is False

    @patch("lib.epistemic.flybrainpoc.hardware.platform.system", return_value="Darwin")
    @patch("lib.epistemic.flybrainpoc.hardware.platform.machine", return_value="arm64")
    @patch("lib.epistemic.flybrainpoc.hardware.platform.mac_ver", return_value=("13.5", "", ""))
    def test_detect_metal_apple_silicon(self, mock_machine, mock_system, mock_mac_ver):
        cap = detect_metal()
        assert cap.backend == BackendType.METAL
        assert cap.available is True
        assert "Apple Silicon" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware.platform.system", return_value="Darwin")
    @patch("lib.epistemic.flybrainpoc.hardware.platform.machine", return_value="x86_64")
    def test_detect_metal_intel_mac(self, mock_machine, mock_system):
        cap = detect_metal()
        assert cap.backend == BackendType.METAL
        assert cap.available is False
        assert "Intel Mac" in cap.reason

    @patch("lib.epistemic.flybrainpoc.hardware.platform.system", return_value="Linux")
    def test_detect_metal_non_macos(self, mock_system):
        cap = detect_metal()
        assert cap.backend == BackendType.METAL
        assert cap.available is False
        assert "not macOS" in cap.reason

    def test_detect_all_backends_returns_list(self):
        backends = detect_all_backends()
        assert len(backends) == 4
        types = {b.backend for b in backends}
        assert types == {BackendType.CUDA, BackendType.ROCM, BackendType.METAL, BackendType.CPU}
        # CPU must always be available
        cpu = next(b for b in backends if b.backend == BackendType.CPU)
        assert cpu.available is True


class TestBackendSelection:
    """Test get_best_backend priority logic."""

    def test_force_cpu_returns_cpu(self):
        cap = get_best_backend(force_cpu=True)
        assert cap.backend == BackendType.CPU

    def test_priority_first_available(self):
        # Mock: CUDA unavailable, ROCm available, Metal unavailable, CPU available
        mock_caps = {
            BackendType.CUDA: BackendCapability(BackendType.CUDA, False, "no nvidia-smi"),
            BackendType.ROCM: BackendCapability(BackendType.ROCM, True, "rocm-smi OK"),
            BackendType.METAL: BackendCapability(BackendType.METAL, False, "not macOS"),
            BackendType.CPU: BackendCapability(BackendType.CPU, True, "always"),
        }

        with patch("lib.epistemic.flybrainpoc.hardware.detect_all_backends", return_value=list(mock_caps.values())):
            cap = get_best_backend(priority=[BackendType.CUDA, BackendType.ROCM, BackendType.METAL, BackendType.CPU])
            assert cap.backend == BackendType.ROCM

    def test_priority_cuda_first_when_available(self):
        mock_caps = {
            BackendType.CUDA: BackendCapability(BackendType.CUDA, True, "nvidia-smi OK"),
            BackendType.ROCM: BackendCapability(BackendType.ROCM, True, "rocm-smi OK"),
            BackendType.METAL: BackendCapability(BackendType.METAL, True, "MPS OK"),
            BackendType.CPU: BackendCapability(BackendType.CPU, True, "always"),
        }
        with patch("lib.epistemic.flybrainpoc.hardware.detect_all_backends", return_value=list(mock_caps.values())):
            cap = get_best_backend(priority=[BackendType.CUDA, BackendType.ROCM, BackendType.METAL, BackendType.CPU])
            assert cap.backend == BackendType.CUDA

    def test_custom_priority_order(self):
        mock_caps = {
            BackendType.CUDA: BackendCapability(BackendType.CUDA, True, ""),
            BackendType.ROCM: BackendCapability(BackendType.ROCM, True, ""),
            BackendType.METAL: BackendCapability(BackendType.METAL, True, ""),
            BackendType.CPU: BackendCapability(BackendType.CPU, True, ""),
        }
        with patch("lib.epistemic.flybrainpoc.hardware.detect_all_backends", return_value=list(mock_caps.values())):
            # Metal preferred over CUDA
            cap = get_best_backend(priority=[BackendType.METAL, BackendType.CUDA, BackendType.ROCM, BackendType.CPU])
            assert cap.backend == BackendType.METAL

    def test_env_var_override(self):
        mock_caps = {
            BackendType.CUDA: BackendCapability(BackendType.CUDA, True, ""),
            BackendType.ROCM: BackendCapability(BackendType.ROCM, True, ""),
            BackendType.METAL: BackendCapability(BackendType.METAL, True, ""),
            BackendType.CPU: BackendCapability(BackendType.CPU, True, ""),
        }
        with patch("lib.epistemic.flybrainpoc.hardware.detect_all_backends", return_value=list(mock_caps.values())):
            with patch.dict(os.environ, {"AES_FLYBRAIN_BACKEND_PRIORITY": "metal,cpu,rocm,cuda"}, clear=False):
                cap = get_best_backend()
                assert cap.backend == BackendType.METAL


class TestBackendCapability:
    def test_bool_conversion(self):
        assert bool(BackendCapability(BackendType.CPU, True, "")) is True
        assert bool(BackendCapability(BackendType.CUDA, False, "")) is False

    def test_backend_summary_contains_all(self):
        summary = backend_summary()
        assert "CUDA" in summary
        assert "ROCM" in summary
        assert "METAL" in summary
        assert "CPU" in summary
        assert "✓" in summary or "✗" in summary


class TestReservoirBackendIntegration:
    """Integration tests for FlyBrainReservoir with different backends."""

    def test_default_auto_backend_loads(self):
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.load()
        assert r._loaded
        assert r.backend_capability is not None
        assert r.backend_capability.available is True

    def test_explicit_cpu_backend(self):
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        r = FlyBrainReservoir(backend="cpu", model="TRIVIAL_UNIT")
        r.load()
        assert r.backend_capability.backend == BackendType.CPU

    @patch("lib.epistemic.flybrainpoc.reservoir.detect_all_backends")
    def test_strict_mode_fails_on_unavailable(self, mock_detect):
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        # Mock the hardware detection: CUDA explicitly NOT available, CPU available.
        # Host-independent — tests the strict-mode LOGIC (request CUDA + strict=True
        # on a machine where CUDA is unavailable → must raise), not the host's GPU.
        mock_detect.return_value = [
            BackendCapability(BackendType.CUDA, False, "nvidia-smi not found"),
            BackendCapability(BackendType.CPU, True, "always"),
        ]
        r = FlyBrainReservoir(backend="cuda", model="TRIVIAL_UNIT", strict=True)
        with pytest.raises(RuntimeError, match="Explicit backend 'cuda' requested but not available"):
            r.load()

    @patch("lib.epistemic.flybrainpoc.reservoir.detect_all_backends")
    @patch("lib.epistemic.flybrainpoc.reservoir.get_best_backend")
    def test_non_strict_falls_back(self, mock_best_backend, mock_detect):
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        # Mock the hardware detection: CUDA NOT available, CPU available.
        # Host-independent — tests the non-strict fallback LOGIC (request CUDA +
        # strict=False on a machine where CUDA is unavailable → falls back to CPU),
        # not the host's GPU.
        mock_detect.return_value = [
            BackendCapability(BackendType.CUDA, False, "nvidia-smi not found"),
            BackendCapability(BackendType.CPU, True, "always"),
        ]
        mock_best_backend.return_value = BackendCapability(BackendType.CPU, True, "fallback")
        r = FlyBrainReservoir(backend="cuda", model="TRIVIAL_UNIT", strict=False)
        r.load()
        assert r._loaded
        # Should have fallen back to CPU
        assert r.backend_capability.backend == BackendType.CPU

    def test_real_full_fallbacks_on_cpu(self, monkeypatch):
        """Same correction as test_reservoir: the absence is forced, not assumed.

        T328 — this asserted a fallback that only happened because the
        FlyWire parquet was not on the machine. With the connectome now
        durable at /opt/fly-brain it did not happen, and the test failed.
        """
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        from lib.epistemic.flybrainpoc.backends import CPUBackend

        def _no_data(self, connectome_path):
            raise FileNotFoundError("forced: no FlyWire parquet on this host")

        monkeypatch.setattr(CPUBackend, "build_full", _no_data)

        import warnings
        r = FlyBrainReservoir(model="REAL_AES_FULL", backend="auto")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r.load()
            fallback_warnings = [x for x in w if "REAL_AES_FULL not available" in str(x.message)]
            assert len(fallback_warnings) == 1
            assert "Falling back to TRIVIAL_UNIT" in str(fallback_warnings[0].message)
        assert r.model == "TRIVIAL_UNIT"
        assert r._loaded

    def test_real_full_is_used_not_skipped_when_connectome_present(self):
        """T328: the other half of the pair, and the reason it was missed.

        Once the FlyWire parquet is durable, REAL_AES_FULL must actually load
        as REAL_AES_FULL — no fallback, and the model string must survive.
        The fallback tests above all proved the path that runs when the data
        is missing; nothing proved the path that runs when it is present, so
        a loader that always fell back would have passed every one of them.
        """
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        from lib.epistemic.flybrainpoc.real_connectome import resolve_checkout
        from pathlib import Path

        try:
            resolve_checkout(Path("eonsystemspbc/fly-brain"))
        except FileNotFoundError:
            pytest.skip("no FlyWire connectome on this host")
        # T328: finding the connectome is not the same as being able to read
        # it. The system python3 that `make test-check` uses has no pyarrow, so
        # this test needs the capability, not the path.
        try:
            import pyarrow.parquet  # noqa: F401
        except ImportError:
            pytest.skip("this interpreter cannot read the FlyWire parquet (no pyarrow)")

        import warnings
        r = FlyBrainReservoir(model="REAL_AES_FULL", backend="auto")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r.load()
            fallback_warnings = [x for x in w if "REAL_AES_FULL not available" in str(x.message)]
        assert not fallback_warnings, (
            "connectome is present, so REAL_AES_FULL must not fall back: "
            f"{[str(x.message) for x in fallback_warnings]}"
        )
        assert r.model == "REAL_AES_FULL", "model must not be rewritten to TRIVIAL_UNIT"
        assert r.net.n_neurons == 138639
        assert r.net.n_synapses == 15091983

    def test_backend_summary(self):
        from lib.epistemic.flybrainpoc.reservoir import FlyBrainReservoir
        r = FlyBrainReservoir(model="TRIVIAL_UNIT")
        r.load()
        summary = r.backend_summary()
        assert "CPU" in summary or "cuda" in summary.lower() or "rocm" in summary.lower() or "metal" in summary.lower()