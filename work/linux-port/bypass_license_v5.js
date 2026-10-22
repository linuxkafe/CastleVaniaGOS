// bypass_license_v5.js — hook e.onServiceConnected to deliver LICENSED from the queued validators.
// Obfuscation map: work/linux-port/LICENSE_OBFUSCATION_MAP.md
// Key insight from diag_e3/e4: e.onServiceConnected fires; e.j (queue) holds g (LicenseValidator)
// instances. We deliver LICENSED by calling g.a().a(0) for each queued g, without
// calling the original (which would make the network request).
console.log("=== bypass_license_v5 (onServiceConnected + queue) ===");

Java.perform(function () {
    var eCls = null, gCls = null, eaCls = null;
    try { eCls = Java.use("com.google.android.vending.licensing.e"); console.log("[+] Found e"); } catch (e) { console.log("[-] e: " + e); }
    try { gCls = Java.use("com.google.android.vending.licensing.g"); console.log("[+] Found g"); } catch (e) { console.log("[-] g: " + e); }
    try { eaCls = Java.use("com.google.android.vending.licensing.e$a"); console.log("[+] Found e$a"); } catch (e) { console.log("[-] e$a: " + e); }

    // 1. Hook e.onServiceConnected: deliver LICENSED for each queued validator, skip original.
    if (eCls) {
        eCls.onServiceConnected.implementation = function (name, binder) {
            console.log("[+] e.onServiceConnected fired: " + name);
            var delivered = 0;
            try {
                var field = this.getClass().getDeclaredField("j");
                field.setAccessible(true);
                var raw = field.get(this);
                console.log("[+] raw queue: " + raw + " (" + (raw ? raw.getClass().getName() : "null") + ")");
                // Use the concrete LinkedList type directly (cast to interface failed in Frida).
                var LinkedList = Java.use("java.util.LinkedList");
                var queue = Java.cast(raw, LinkedList);
                console.log("[+] queue size: " + queue.size());
                if (queue.size() > 0) {
                    var it = queue.iterator();
                    while (it.hasNext()) {
                        var rawG = it.next();
                        console.log("[+] queued validator: " + rawG);
                        try {
                            var Gcls = Java.use("com.google.android.vending.licensing.g");
                            var g = Java.cast(rawG, Gcls);
                            var cb = g.a(); // returns f (app callback)
                            console.log("[+] got callback f: " + cb);
                            if (cb) { cb.a(0); console.log("[+] delivered f.a(0) LICENSED"); delivered++; }
                        } catch (ex) { console.log("[!] deliver failed: " + ex); }
                    }
                    queue.clear();
                }
            } catch (ex) { console.log("[!] queue access failed: " + ex); }
            // also try e$a if present (defence)
            console.log("[+] delivered=" + delivered + " (original onServiceConnected skipped)");
            // do NOT call original
        };
        console.log("[+] Hooked e.onServiceConnected");
    }

    // 2. Hook g.a(PublicKey,int,String,String) (verify) -> skip RSA, deliver 0.
    if (gCls) {
        try {
            gCls["a"].overload("java.security.PublicKey", "int", "java.lang.String", "java.lang.String").implementation = function (pk, nonce, signedData, signature) {
                console.log("[+] g.a(verify) called — forcing LICENSED");
                try {
                    var cb = this.a();
                    if (cb) cb.a(0);
                } catch (e) { console.log("[!] g.a cb: " + e); }
            };
            console.log("[+] Hooked g.a(PublicKey,int,String,String)");
        } catch (e) { console.log("[-] g.a hook: " + e); }
    }

    // 3. Hook e$a.a(int,String,String) (IPC callback) -> force 0 + deliver.
    if (eaCls) {
        try {
            eaCls["a"].overload("int", "java.lang.String", "java.lang.String").implementation = function (responseCode, signedData, signature) {
                console.log("[+] e$a.a(IPC) called rc=" + responseCode + " — forcing LICENSED");
                try {
                    var cb = this.b.a(); // g.a() -> f
                    if (cb) { cb.a(0); console.log("[+] delivered f.a(0)"); }
                } catch (e) { console.log("[!] e$a deliver: " + e); }
            };
            console.log("[+] Hooked e$a.a(int,String,String)");
        } catch (e) { console.log("[-] e$a.a hook: " + e); }
    }

    console.log("=== bypass_license_v5 loaded ===");
});