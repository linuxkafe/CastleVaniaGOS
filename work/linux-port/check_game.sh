#!/bin/bash
# Launch game and check logs
# All paths are parameterised via env vars; no host-specific absolute paths.
ADB="${ADB:-adb}"
export PATH="${ANDROID_SDK:-/opt/android-sdk}/platform-tools:$PATH"
"$ADB" logcat -c
"$ADB" shell am force-stop jp.konami.castlevania
sleep 2
"$ADB" shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity
sleep 15
"$ADB" logcat -d 2>&1 | grep -iE "Licensing|cleartext|NetworkSecurity|download|asset|IAB|purchase|error" | tail -30