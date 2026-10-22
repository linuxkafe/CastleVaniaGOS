#!/system/bin/bash
export PATH=/opt/android-sdk/platform-tools:$PATH

# Kill old frida
adb shell killall -9 frida-server-17 2>/dev/null
adb shell killall -9 frida-server-full 2>/dev/null
sleep 3

# Start full frida-server
adb shell /data/local/tmp/frida-server-full &
sleep 5

# Clear and start game
adb shell am force-stop jp.konami.castlavania 2>/dev/null || adb shell am force-stop jp.konami.castlevania 2>/dev/null
adb shell am force-stop com.android.vending 2>/dev/null
adb shell pm clear jp.konami.castlevania 2>/dev/null
sleep 3

# Clear logs
adb logcat -c

# Start game
echo "Starting game..."
adb shell am start -n jp.konami.castlavania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity 2>/dev/null || \
adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity
sleep 10

# Check if game is running
echo "Checking processes..."
adb shell ps | grep -E "konami|vending" || echo "No processes found"

# Wait for vending to appear (it might take a while)
echo "Waiting for vending process..."
VENDING_PID=""
for i in $(seq 1 30); do
    sleep 3
    VENDING_PID=$(adb shell ps | grep "com.android.vending" | grep -v root | awk '{print $2}' | head -1)
    if [ ! -z "$VENDING_PID" ]; then
        echo "Found vending: PID $VENDING_PID"
        break
    fi
    # Also check for the game
    GAME_PID=$(adb shell ps | grep "konami" | grep -v root | awk '{print $2}' | head -1)
    if [ ! -z "$GAME_PID" ]; then
        echo "Game running: PID $GAME_PID, but no vending yet..."
    fi
    echo "  Waiting... ($i)"
done

if [ -z "$VENDING_PID" ]; then
    echo "ERROR: Vending not found!"
    echo "=== Full process list ==="
    adb shell ps | grep -E "u0_a|system|root" | head -30
    exit 1
fi

# Create JS script directly
cat > /tmp/bytehook.js << 'JS'
Java.perform(function() {
    console.log("[+] Java hook started");

    // Hook NetworkSecurityPolicy
    try {
        var NSP = Java.use("android.security.NetworkSecurityPolicy");
        console.log("[+] Found NetworkSecurityPolicy");

        NSP.isCleartextTrafficPermitted.overload("java.lang.String").implementation = function(host) {
            console.log("[+] NSP.isCleartextTrafficPermitted(" + host + ") -> true");
            return true;
        };
        console.log("[+] Hooked isCleartextTrafficPermitted(String)");

        NSP.isCleartextTrafficPermitted.overload().implementation = function() {
            console.log("[+] NSP.isCleartextTrafficPermitted() -> true");
            return true;
        };
        console.log("[+] Hooked isCleartextTrafficPermitted()");
    } catch(e) {
        console.log("[-] NSP hook failed: " + e);
    }

    // Hook Apache HttpClient DefaultRequestDirector
    try {
        var DRD = Java.use("org.apache.http.impl.client.DefaultRequestDirector");
        console.log("[+] Found DefaultRequestDirector");

        DRD.execute.overload(
            "org.apache.http.HttpHost",
            "org.apache.http.HttpRequest",
            "org.apache.http.protocol.HttpContext"
        ).implementation = function(host, request, context) {
            console.log("[+] DRD.execute: " + host);

            if (host && host.toString && host.toString().indexOf("android.clients.google.com") >= 0) {
                console.log("[+] Intercepting license server request!");

                var BasicHttpResponse = Java.use("org.apache.http.message.BasicHttpResponse");
                var BasicStatusLine = Java.use("org.apache.http.message.BasicStatusLine");
                var ProtocolVersion = Java.use("org.apache.http.ProtocolVersion");
                var StringEntity = Java.use("org.apache.http.entity.StringEntity");

                var pv = ProtocolVersion.$new("HTTP", 1, 1);
                var sl = BasicStatusLine.$new(pv, 200, "OK");
                var resp = BasicHttpResponse.$new(sl);
                var entity = StringEntity.$new("0|123456789|jp.konami.castlavania|1|user1|0");
                resp.setEntity(entity);

                console.log("[+] Returning mock LICENSED response");
                return resp;
            }

            try {
                return this.execute(host, request, context);
            } catch(e) {
                var msg = e.getMessage ? e.getMessage() : "";
                console.log("[+] Exception: " + msg);
                if (msg.indexOf("Cleartext") >= 0) {
                    console.log("[+] Cleartext exception! Bypassing...");
                    var BHR = Java.use("org.apache.http.message.BasicHttpResponse");
                    var BSL = Java.use("org.apache.http.message.BasicStatusLine");
                    var PV = Java.use("org.apache.http.ProtocolVersion");
                    var pv2 = PV.$new("HTTP", 1, 1);
                    var sl2 = BSL.$new(pv2, 200, "OK");
                    var resp2 = BHR.$new(sl2);
                    var SE = Java.use("org.apache.http.entity.StringEntity");
                    var entity2 = SE.$new("0|123456789|jp.konami.castlavania|1|user1|0");
                    resp2.setEntity(entity2);
                    return resp2;
                }
                throw e;
            }
        };
        console.log("[+] Hooked DefaultRequestDirector.execute");
    } catch(e) {
        console.log("[-] DRD hook failed: " + e);
    }

    // Hook callback interface d$a (IPC callback from vending)
    try {
        var dStub = Java.use("com.google.android.vending.licensing.d$a");
        console.log("[+] Found callback d$a");

        dStub.a.overload("int", "java.lang.String", "java.lang.String").implementation = function(responseCode, signedResponse, signature) {
            console.log("[+] License callback: responseCode=" + responseCode);
            console.log("[+] signedResponse: " + signedResponse);

            if (responseCode != 0) {
                console.log("[+] Forcing LICENSED (changed " + responseCode + " to 0)");
                return this.a(0, "0|123456789|jp.konami.castlavania|1|user1|0", "mock_sig");
            }
            return this.a(responseCode, signedResponse, signature);
        };
        console.log("[+] Hooked d$a.a(int, String, String)");
    } catch(e) {
        console.log("[-] d$a hook failed: " + e);
    }

    // Hook callback interface f
    try {
        var f = Java.use("com.google.android.vending.licensing.f");
        console.log("[+] Found callback interface f");

        f.b.implementation = function(errorCode) {
            console.log("[+] f.b(" + errorCode + ") -> converting to LICENSED");
            return this.a(0);
        };
        console.log("[+] Hooked f.b -> f.a(0)");
    } catch(e) {
        console.log("[-] f hook failed: " + e);
    }

    console.log("[+] All hooks installed!");
});
console.log("[*] Script loaded, waiting...");
JS

# Attach Frida
echo ""
echo "=== Attaching Frida to vending PID $VENDING_PID ==="
timeout 60 frida -U -l /tmp/bytehook.js -p $VENDING_PID --runtime=v8 2>&1 || true

# Check logs
echo ""
echo "=== LOG OUTPUT ==="
adb logcat -d | grep -iE "license|cleartext|konami|error contacting|vending|licensing" | tail -40