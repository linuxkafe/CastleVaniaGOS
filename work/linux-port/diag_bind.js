// diag_bind.js — find who binds to the licensing service and how the callback fires.
console.log("=== diag_bind START ===");
Java.perform(function () {
    // Hook ContextWrapper.bindService to log the Intent action
    try {
        var CW = Java.use("android.content.ContextWrapper");
        CW.bindService.overload("android.content.Intent", "android.content.ServiceConnection", "int").implementation = function (intent, conn, flags) {
            console.log("[bindService] action=" + (intent ? intent.getAction() : null) + " conn=" + conn + " flags=" + flags);
            return this.bindService(intent, conn, flags);
        };
        console.log("[+] Hooked ContextWrapper.bindService");
    } catch (e) { console.log("[-] bindService: " + e); }

    // Hook ServiceConnection.onServiceConnected on all implementations via the interface
    // (Frida allows hooking interface methods; applies to all impls)
    try {
        var SC = Java.use("android.content.ServiceConnection");
        SC.onServiceConnected.implementation = function (name, binder) {
            console.log("[onServiceConnected] name=" + name + " binder=" + binder);
            return this.onServiceConnected(name, binder);
        };
        console.log("[+] Hooked ServiceConnection.onServiceConnected");
    } catch (e) { console.log("[-] ServiceConnection: " + e); }

    // Hook e.onServiceConnected and e.a(f) explicitly (already tried, but log entry)
    try {
        var eCls = Java.use("com.google.android.vending.licensing.e");
        eCls.onServiceConnected.implementation = function (name, binder) {
            console.log("[e.onServiceConnected] name=" + name);
            return this.onServiceConnected(name, binder);
        };
        eCls["a"].overload("com.google.android.vending.licensing.f").implementation = function (cb) {
            console.log("[e.a(checkLicense)] called with cb=" + cb);
            return this.a(cb);
        };
        console.log("[+] Hooked e.onServiceConnected + e.a(f)");
    } catch (e) { console.log("[-] e hooks: " + e); }

    console.log("=== diag_bind loaded ===");
});