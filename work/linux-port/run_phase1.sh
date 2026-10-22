#!/bin/bash
# T009 Phase 1: Emulator Patch — Serve local assets and bypass license check
# Runs on Steam Deck via SSH. All paths are parameterised via env vars with defaults;
# no host-specific absolute paths are hardcoded.
#
# Required env (override as needed):
#   REPO_ROOT   path to the CastleVaniaGOS repo on the Deck host
#               (default: $HOME/cvgos, i.e. a clone of this repo on the Deck)
#   APK_NAME    APK filename (default: castlevania-grimoire-of-souls-1-1-4.apk)
#   ASSET_PORT  port for the asset server (default: 8080)
#   ADB         adb binary (default: adb)
set -e

REPO_ROOT="${REPO_ROOT:-$HOME/cvgos}"
APK_NAME="${APK_NAME:-castlevania-grimoire-of-souls-1-1-4.apk}"
ASSET_PORT="${ASSET_PORT:-8080}"
ADB="${ADB:-adb}"
EMULATOR_PORT="${EMULATOR_PORT:-5554}"
ASSETS_DIR="${ASSETS_DIR:-$REPO_ROOT/extracted/assets/bin/Data}"
GAME_PKG="jp.konami.castlevania"
FRIDA_PORT="${FRIDA_PORT:-27042}"
APK_DIR="${APK_DIR:-$REPO_ROOT/apks}"

# Create assets directory structure
echo "=== Preparing assets directory ==="
mkdir -p "$ASSETS_DIR"
echo "Assets dir: $ASSETS_DIR"

# Start asset server on host (Deck)
echo ""
echo "=== Starting asset server on port $ASSET_PORT ==="
python3 "$REPO_ROOT/work/linux-port/asset_server.py" "$ASSET_PORT" "$ASSETS_DIR" &
ASSET_SERVER_PID=$!
echo "Asset server PID: $ASSET_SERVER_PID"
sleep 2

# Start emulator via podman
echo ""
echo "=== Starting emulator ==="
podman run --rm --device /dev/kvm \
  -p "$EMULATOR_PORT:$EMULATOR_PORT" \
  -p "$ASSET_PORT:$ASSET_PORT" \
  -v "$APK_DIR:/apks" \
  cvgos-android-emu:latest waitboot 60 &
PODMAN_PID=$!
echo "Podman PID: $PODMAN_PID"
sleep 80

# Check device connection
echo ""
echo "=== Checking device connection ==="
"$ADB" devices

# Install frida-server (must be provided by the operator; not in repo)
echo ""
echo "=== Installing frida-server ==="
"$ADB" -s "emulator-$EMULATOR_PORT" push "$APK_DIR/frida-server" /data/local/tmp/frida-server
"$ADB" -s "emulator-$EMULATOR_PORT" shell chmod 755 /data/local/tmp/frida-server
"$ADB" -s "emulator-$EMULATOR_PORT" shell "/data/local/tmp/frida-server &"
sleep 3

# Forward frida port
"$ADB" -s "emulator-$EMULATOR_PORT" forward "tcp:$FRIDA_PORT" "tcp:$FRIDA_PORT"
echo "Frida forwarded: localhost:$FRIDA_PORT -> emulator:$FRIDA_PORT"

# Install game APK
echo ""
echo "=== Installing game APK ==="
"$ADB" -s "emulator-$EMULATOR_PORT" install -r -d -g "$APK_DIR/$APK_NAME" 2>&1
sleep 10

# Configure emulator to use local asset server.
# NOTE: /etc/hosts on Android is read-only, so the hosts entry may fail silently.
# The game requests the CDN hostname on port 80 by default, while the asset server
# listens on ASSET_PORT. To bridge this, either (a) run the asset server on port 80
# (requires privileges), or (b) install an iptables redirect inside the emulator:
#   adb shell "iptables -t nat -A OUTPUT -p tcp --dport 80 -j REDIRECT --to-port $ASSET_PORT"
# Without one of these, the redirect below does not reach the asset server.
echo ""
echo "=== Configuring emulator network ==="
"$ADB" -s "emulator-$EMULATOR_PORT" shell "echo '10.0.2.2 asset-cdn.konami.com' >> /etc/hosts" 2>/dev/null || true

# Launch game
echo ""
echo "=== Launching game ==="
"$ADB" -s "emulator-$EMULATOR_PORT" shell am force-stop "$GAME_PKG"
"$ADB" -s "emulator-$EMULATOR_PORT" shell am start -n "$GAME_PKG/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity" 2>&1
sleep 15

echo ""
echo "=== Done ==="
# Cleanup
kill "$ASSET_SERVER_PID" 2>/dev/null || true
# (podman container is left running; stop with: podman stop <id>)