#!/system/bin/bash
export PATH=/opt/android-sdk/platform-tools:$PATH

# Kill everything
adb shell killall -9 frida-server-17 2>/dev/null
adb shell killall -9 frida-server 2>/dev/null
adb shell killall -9 frida-server-full 2>/dev/null
sleep 3

# Start full frida-server
adb shell /data/local/tmp/frida-server-full &
sleep 5

# Verify
adb shell ps | grep frida

# Clear and start
adb shell am force-stop jp.konami.castlevania 2>/dev/null
adb shell am force-stop com.android.vending 2>/dev/null
adb shell pm clear jp.konami.castlevania 2>/dev/null
sleep 3

# Clear logs
adb logcat -c

# Start game
adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity
sleep 5

# Find vending PID
VENDING_PID=$(adb shell ps | grep frida | awk '{print $2}' | head -1)
echo "Checking frida server PID: $VENDING_PID"

VENDING_PID=$(adb shell ps | grep "com.android.vending" | grep -v root | awk '{print $2}' | head -1)
echo "Vending PID: $VENDING_PID"

if [ -z "$VENDING_PID" ]; then
    echo "Waiting for vending..."
    for i in $(seq 1 10); do
        sleep 3
        VENDING_PID=$(adb shell ps | grep vending | awk '{print $2}' | head -1)
        if [ ! -z "$VENDING_PID" ]; then
            echo "Found vending: PID $VENDING_PID"
            break
        fi
        echo "  Waiting... ($i)"
    done
fi

if [ -z "$VENDING_PID" ]; then
    echo "ERROR: Vending process not found!"
    adb logcat -d | tail -50
    exit 1
fi

# Attach Frida
echo "Attaching Frida to PID $VENDING_PID..."
timeout 60 frida -U -l /tmp/test_final.js -p $VENDING_PID --runtime=v8 2>&1 || true

# Check logs
echo ""
echo "=== LOGS ==="
adb logcat -d | grep -E "License|cleartext|konami|Error contacting|licensing|CLEARTEXT|HOOKED|LicenseValidator" | tail -40