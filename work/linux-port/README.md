# T009 Phase 1: Emulator Patch — Asset Server Bypass

## Objective
Serve local Unity assets via HTTP server to bypass dead CDN endpoints in Castlevania: Grimoire of Souls.

## Files Created
```
work/linux-port/
├── asset_server.py      # HTTP server serving Unity assets
└── run_phase1.sh        # Deployment script for Steam Deck
```

## How It Works
1. Extract `sharedassets0.*` and `globalgamemanagers` from APK
2. Start Python HTTP server on Deck (port 8080)
3. Forward port to emulator via podman `-p 8080:8080`
4. Game loads assets from local HTTP instead of dead CDN
5. License check bypass attempted via Frida (if available)

## Prerequisites
- Docker/podman image: `localhost/cvgos-android-emu:latest`
- APK: `castlevania-grimoire-of-souls-1-1-4.apk`
- Assets: `extracted/assets/bin/Data/`
- Frida server: `frida-server` (x86_64 Android binary)

## Run on Deck
```bash
ssh deck@steamdeck
cd /home/deck/cvgos-emulator
bash /path/to/run_phase1.sh
```

## Verification
- Game launches without SSL errors
- Assets load from local server
- Title screen displays

## Rollback
All changes are temporary (container is ephemeral). Kill scripts to stop.
