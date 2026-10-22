// diag_bind2.js — identify the ServiceConnection class and the caller of bindService
console.log("=== diag_bind2 START ===");
Java.perform(function () {
    var CW = Java.use("android.content.ContextWrapper");
    CW.bindService.overload("android.content.Intent", "android.content.ServiceConnection", "int").implementation = function (intent, conn, flags) {
        var action = (intent ? intent.getAction() : null);
        var connClass = (conn ? conn.getClass().getName() : null);
        console.log("[bindService] action=" + action + " connClass=" + connClass + " flags=" + flags);
        if (action && action.indexOf("licensing") >= 0) {
            console.log("[bindService] STACK: " + Java.use("android.util.Log").getStackTraceString(Java.use("java.lang.Throwable").$new()));
        }
        return this.bindService(intent, conn, flags);
    };
    console.log("[+] Hooked bindService");
    console.log("=== diag_bind2 loaded ===");
});