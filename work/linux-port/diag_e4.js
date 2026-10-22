// diag_e4.js — hook e.a(g), e$a static dispatchers, e.onServiceConnected post-state
console.log("=== diag_e4 START ===");
Java.perform(function () {
    var eCls = Java.use("com.google.android.vending.licensing.e");
    var eaCls = Java.use("com.google.android.vending.licensing.e$a");

    // Hook e.a(g) (checkAccess with validator) — likely the real entry point
    try {
        eCls["a"].overload("com.google.android.vending.licensing.g").implementation = function (g) {
            console.log("[e.a(g)] called — queued validator " + g);
            return this.a(g);
        };
        console.log("[+] Hooked e.a(g)");
    } catch (e) { console.log("[-] e.a(g): " + e); }

    // Hook e.onServiceConnected to log post-state
    eCls.onServiceConnected.implementation = function (name, binder) {
        console.log("[e.onServiceConnected] name=" + name);
        var r = this.onServiceConnected(name, binder);
        // log after
        try { console.log("[e.onServiceConnected] post: b(service)=" + this.b.value); } catch (ex) { console.log("[e.onServiceConnected] post b err: " + ex); }
        try { console.log("[e.onServiceConnected] post: j(queue)=" + this.j.value); } catch (ex) {}
        return r;
    };

    // Hook e$a static dispatchers
    try {
        eaCls["a"].overload("com.google.android.vending.licensing.e$a").implementation = function (ea) {
            console.log("[e$a.a(static)] called with " + ea);
            return eaCls["a"].call(null, ea);
        };
        console.log("[+] Hooked e$a.a(e$a) static");
    } catch (e) { console.log("[-] e$a.a(e$a): " + e); }
    try {
        eaCls["b"].overload("com.google.android.vending.licensing.e$a").implementation = function (ea) {
            console.log("[e$a.b(static)] called with " + ea);
            return eaCls["b"].call(null, ea);
        };
        console.log("[+] Hooked e$a.b(e$a) static");
    } catch (e) { console.log("[-] e$a.b(e$a): " + e); }

    // Hook e$a.a(int,String,String) IPC callback
    try {
        eaCls["a"].overload("int", "java.lang.String", "java.lang.String").implementation = function (rc, sd, sig) {
            console.log("[e$a.a(IPC)] called rc=" + rc);
            return;
        };
        console.log("[+] Hooked e$a.a(int,String,String)");
    } catch (e) { console.log("[-] e$a.a(int,S,S): " + e); }

    console.log("=== diag_e4 loaded ===");
});