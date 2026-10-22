# GPU Host Mode Patch for Castlevania GOS Emulator

**Status: APPLIED.** As of 2026-10-22, host GPU is already the default in both
`runtime/android-emulator/Dockerfile` (line 74: `hw.gpu.mode=host`) and
`runtime/android-emulator/entrypoint.sh` (line 39: `GPU_MODE="${GPU_MODE:-host}"`).
The diff below is retained as the change record only; it is not a pending task.

## Problem
Game crashes at Unity initialization with:
- `EGL_BAD_CONFIG: no ES 3.1 support`
- SIGSEGV in `libunity.so` (ARM64 via libnative_bridge)

SwiftShader indirect rendering lacks ES 3.1 support required by Unity 2019+ IL2CPP.

## Solution
Switch emulator GPU mode from `swiftshader_indirect` to `host` to use Steam Deck's Mesa drivers (supports GLES 3.1).

## Changes Required

### 1. Update entrypoint.sh
Change default GPU mode:
```diff
- log "starting AVD ${AVD} (gpu=${GPU_MODE:-swiftshader_indirect}, ...)"
+ log "starting AVD ${AVD} (gpu=${GPU_MODE:-host}, ...)"
  exec emulator \
      -avd "${AVD}" \
-     -gpu "${GPU_MODE:-swiftshader_indirect}" \
+     -gpu "${GPU_MODE:-host}" \
```

### 2. Update AVD config.ini
```bash
sed -i 's/^hw.gpu.mode=.*/hw.gpu.mode=host/' /root/.android/avd/cvgos.avd/config.ini
```

### 3. Rebuild container
```bash
podman build -t localhost/cvgos-android-emu:gpu-host runtime/android-emulator/
podman run --device /dev/kvm --device /dev/dri:/dev/dri ...
```

## Verification Criteria
- `adb logcat | grep EGL` shows no EGL_BAD_CONFIG
- Game reaches title screen without SIGSEGV
- Vending process `com.android.vending` spawns within 10s of launch
- Frida can attach to vending PID and hooks `NetworkSecurityPolicy.isCleartextTrafficPermitted`

## Risks
- Host GPU requires /dev/dri access (already in Dockerfile)
- May increase GPU memory usage
- If host GPU fails, fallback to swiftshader_indirect remains available via env var

## Alternative
If host GPU fails, try `hw.gpu.mode=guest` with `-gpu mesa` or switch to Android 11 x86_64 system image with updated libndk_translation.
