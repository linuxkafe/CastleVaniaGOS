// bypass_all_v2.js — licence bypass (v5) + skip UnityDownloaderActivity (skip download).
// Licence part: probe-verified (e, g, e$a). Downloader part: probe-verified (UnityDownloaderActivity).
console.log("=== bypass_all_v2 ===");

Java.perform(function () {
    // --- Part 1: Licence bypass (from bypass_license_v5.js) ---
    var eCls = null, gCls = null, eaCls = null;
    try { eCls = Java.use("com.google.android.vending.licensing.e"); } catch (e) {}
    try { gCls = Java.use("com.google.android.vending.licensing.g"); } catch (e) {}
    try { eaCls = Java.use("com.google.android.vending.licensing.e$a"); } catch (e) {}

    if (eCls) {
        eCls.onServiceConnected.implementation = function (name, binder) {
            console.log("[lic] onServiceConnected: " + name);
            var delivered = 0;
            try {
                var field = this.getClass().getDeclaredField("j");
                field.setAccessible(true);
                var raw = field.get(this);
                var LinkedList = Java.use("java.util.LinkedList");
                var queue = Java.cast(raw, LinkedList);
                var it = queue.iterator();
                while (it.hasNext()) {
                    var rawG = it.next();
                    try {
                        var Gcls = Java.use("com.google.android.vending.licensing.g");
                        var g = Java.cast(rawG, Gcls);
                        var cb = g.a();
                        if (cb) { cb.a(0); console.log("[lic] delivered f.a(0) LICENSED"); delivered++; }
                    } catch (ex) { console.log("[lic] deliver failed: " + ex); }
                }
                queue.clear();
            } catch (ex) { console.log("[lic] queue access failed: " + ex); }
            console.log("[lic] delivered=" + delivered + " (original skipped)");
        };
        console.log("[lic] Hooked e.onServiceConnected");
    }
    if (gCls) {
        try {
            gCls["a"].overload("java.security.PublicKey", "int", "java.lang.String", "java.lang.String").implementation = function (pk, nonce, signedData, signature) {
                console.log("[lic] g.a(verify) — forcing LICENSED");
                try { var cb = this.a(); if (cb) cb.a(0); } catch (e) {}
            };
            console.log("[lic] Hooked g.a");
        } catch (e) { console.log("[lic] g.a hook failed: " + e); }
    }
    if (eaCls) {
        try {
            eaCls["a"].overload("int", "java.lang.String", "java.lang.String").implementation = function (rc, sd, sig) {
                console.log("[lic] e$a.a(IPC) rc=" + rc + " — forcing LICENSED");
                try {
                    var cb = this.b.a();
                    if (cb) { cb.a(0); console.log("[lic] delivered f.a(0)"); }
                } catch (e) { console.log("[lic] e$a deliver: " + e); }
            };
            console.log("[lic] Hooked e$a.a");
        } catch (e) { console.log("[lic] e$a.a hook failed: " + e); }
    }

    // --- Part 2: Skip UnityDownloaderActivity (skip OBB download) ---
    try {
        var UDA = Java.use("com.unity3d.plugin.downloader.UnityDownloaderActivity");
        console.log("[uda] Found UnityDownloaderActivity");
        // Finish the activity in onCreate so the download check is skipped.
        UDA.onCreate.implementation = function (bundle) {
            console.log("[uda] onCreate — finishing activity (skip download)");
            this.onCreate(bundle);
            this.finish();
        };
        console.log("[uda] Hooked onCreate -> finish()");
    } catch (e) {
        console.log("[uda] UnityDownloaderActivity hook failed: " + e);
    }

    console.log("=== bypass_all_v2 loaded ===");
});