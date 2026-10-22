// diag_bind3.js — identify the ServiceConnection class and caller of bindService (no recursion)
console.log("=== diag_bind3 START ===");
Java.perform(function () {
    var CW = Java.use("android.content.ContextWrapper");
    var origBind = CW.bindService.overload("android.content.Intent", "android.content.ServiceConnection", "int");
    origBind.implementation = function (intent, conn, flags) {
        var action = null;
        var connClass = "null";
        try { action = (intent ? intent.getAction() : null); } catch (e) {}
        try { if (conn) connClass = conn.getClass().getName(); } catch (e) { connClass = "n/a"; }
        if (action && String(action).indexOf("licensing") >= 0) {
            console.log("[bindService] action=" + action + " connClass=" + connClass + " flags=" + flags);
        }
        try { return origBind.call(this, intent, conn, flags); } catch (e) { console.log("[bindService] err: " + e); return true; }
    };
    console.log("[+] Hooked bindService (no recursion)");
    console.log("=== diag_bind3 loaded ===");
});