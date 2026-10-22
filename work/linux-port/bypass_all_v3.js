// bypass_all_v3.js — licence bypass (v5) + skip UnityDownloaderActivity (drop Intent).
console.log("=== bypass_all_v3 ===");
Java.perform(function () {
    // --- Part 1: Licence bypass (v5) ---
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

    // --- Part 2: Skip UnityDownloaderActivity (drop the Intent) ---
    var Activity = Java.use("android.app.Activity");
    Activity.startActivity.overload("android.content.Intent").implementation = function (intent) {
        var cmpStr = null;
        try { var c = intent.getComponent(); if (c) cmpStr = c.flattenToString(); } catch (e) {}
        if (cmpStr && cmpStr.indexOf("UnityDownloaderActivity") >= 0) {
            console.log("[uda] startActivity -> UnityDownloaderActivity DROPPED");
            return;
        }
        return this.startActivity(intent);
    };
    try {
        Activity.startActivity.overload("android.content.Intent", "android.os.Bundle").implementation = function (intent, opts) {
            var cmpStr = null;
            try { var c = intent.getComponent(); if (c) cmpStr = c.flattenToString(); } catch (e) {}
            if (cmpStr && cmpStr.indexOf("UnityDownloaderActivity") >= 0) {
                console.log("[uda] startActivity(Bundle) -> UnityDownloaderActivity DROPPED");
                return;
            }
            return this.startActivity(intent, opts);
        };
    } catch (e) {}
    try {
        Activity.startActivityForResult.overload("android.content.Intent", "int").implementation = function (intent, code) {
            var cmpStr = null;
            try { var c = intent.getComponent(); if (c) cmpStr = c.flattenToString(); } catch (e) {}
            if (cmpStr && cmpStr.indexOf("UnityDownloaderActivity") >= 0) {
                console.log("[uda] startActivityForResult -> UnityDownloaderActivity DROPPED");
                return;
            }
            return this.startActivityForResult(intent, code);
        };
    } catch (e) {}
    console.log("[uda] startActivity hooks installed");

    console.log("=== bypass_all_v3 loaded ===");
});