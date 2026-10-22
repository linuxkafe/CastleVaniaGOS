#!/bin/bash
set -e

# All paths are parameterised via env vars; no host-specific absolute paths.
# GPU mode defaults to 'host' (see runtime/android-emulator/entrypoint.sh).
export PATH="${ANDROID_SDK:-/opt/android-sdk}/platform-tools:${ANDROID_SDK:-/opt/android-sdk}/emulator:$PATH"

APK_DIR="${APK_DIR:-./apks}"
APK_NAME="${APK_NAME:-castlevania-grimoire-of-souls-1-1-4.apk}"
GPU_MODE="${GPU_MODE:-host}"

echo "=== Starting emulator ==="
adb start-server
sleep 2

emulator -avd cvgos -gpu "$GPU_MODE" -no-window -no-boot-anim -no-snapshot \
  -netdelay none -netspeed full -no-audio -no-metrics &
EMU_PID=$!
echo "Emulator PID: $EMU_PID"

# Wait for emulator to boot
echo "Waiting for emulator..."
for i in $(seq 1 90); do
  if adb devices | grep -q "emulator.*device"; then
    echo "Emulator ready after ${i}s"
    break
  fi
  sleep 2
done

echo "=== Installing APK ==="
adb install -r -d -g "$APK_DIR/$APK_NAME"

echo "=== Starting frida-server ==="
# frida-server binary must be supplied by the operator (not in repo); place it in APK_DIR.
adb push "$APK_DIR/frida-server" /data/local/tmp/frida-server
adb shell "chmod 755 /data/local/tmp/frida-server"
adb shell "/data/local/tmp/frida-server &"
sleep 2

echo "=== Forwarding frida port ==="
adb forward tcp:27042 tcp:27042

echo "=== Launching game ==="
adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity
sleep 5

echo "=== Getting game PID ==="
GAME_PID=$(adb shell "ps | grep jp.konami.castlevania | awk '{print \$2}' | head -1")
echo "Game PID: $GAME_PID"

echo "=== Frida server running, port 27042 forwarded ==="
echo "=== Use: frida -H 127.0.0.1:27042 -p \$GAME_PID -l work/linux-port/bypass_license.js ==="