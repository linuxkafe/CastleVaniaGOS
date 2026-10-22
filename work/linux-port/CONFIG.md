# Canonical configuration — T009 Linux port work

This document is the single source of truth for values that were previously scattered
across `STATUS-ATUAL.md`, `FASE1-RESUMO.md`, `IMPLEMENTACAO.md`, `GPU_HOST_PATCH.md`,
`run_phase1.sh`, `run_frida.sh`, `asset_server.py`, and the shadow docs. All other
artefacts should reference or derive from the values here.

## Asset server

- Canonical port: **8080** (`ASSET_PORT` default in `run_phase1.sh` and `asset_server.py`)
- Bind host: **127.0.0.1** by default (override with `BIND_HOST` env var; document any
  non-loopback exposure — see F9)
- Canonical asset byte counts (from `extracted/assets/bin/Data/`):
  - `globalgamemanagers`: 551,616 bytes (539 KiB)
  - `globalgamemanagers.assets`: 638,892 bytes
  - `level0`: 85,184 bytes
  - `sharedassets0.assets.split0..2`: 1,048,576 bytes each
  - `sharedassets0.assets.split3`: 625,872 bytes
  - `unity default resources`: 3,605,916 bytes
  - `boot.config`: 181 bytes

## GPU mode

- Canonical mode: **host** (Steam Deck Mesa drivers, supports GLES 3.1).
- `runtime/android-emulator/Dockerfile` line 74: `hw.gpu.mode=host`
- `runtime/android-emulator/entrypoint.sh` line 39: `GPU_MODE="${GPU_MODE:-host}"`
- Software fallback: `GPU_MODE=swiftshader_indirect` (env override) — lacks ES 3.1, Unity crashes.
- `run_frida.sh` defaults `GPU_MODE=host`.

## Frida

- Container image installs `frida-tools` (unpinned, currently resolves to 17.x).
- Container image installs frida-server 16.2.1 (android-x86_64) at `/usr/local/bin/frida-server`
  — this binary cannot execute inside the Ubuntu container (Android ELF); it must be pushed
  into the emulator via `adb push`. Version skew: client 17.x vs server 16.2.1 are
  incompatible (Frida requires matching major versions). The working setup used 17.24.3 on
  both sides (HOST-ONLY evidence). See `runtime/android-emulator/Dockerfile:39,59-64`.

## Ports summary

| Service | Port | Bind |
|---|---|---|
| ADB / emulator | 5554, 5555 | localhost |
| Asset server | 8080 (canonical) | 127.0.0.1 (default) |
| Frida | 27042 | localhost (forwarded) |
| Mock licence server | 9999 (operator-chosen) | 127.0.0.1 (default) |

## Paths

- No host-specific absolute paths in tracked scripts; use `REPO_ROOT`, `APK_DIR`, `APK_NAME`,
  `ASSETS_DIR`, `ADB`, `ANDROID_SDK` env vars (defaults documented in each script).
- `frida-server` binary is NOT in the repository; the operator must supply it (see Dockerfile).