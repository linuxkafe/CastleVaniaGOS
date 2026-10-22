// diag_e2.js — hook e.onServiceConnected with stack trace; also hook all e.a overloads
console.log("=== diag_e2 START ===");
Java.perform(function () {
    var eCls = Java.use("com.google.android.vending.licensing.e");
    // Hook onServiceConnected
    eCls.onServiceConnected.implementation = function (name, binder) {
        console.log("[e.onServiceConnected] name=" + name);
        try {
            console.log("[e.onServiceConnected] stack:\n" + Java.use("android.util.Log").getStackTraceString(Java.use("java.lang.Throwable").$new()));
        } catch (ex) {}
        return this.onServiceConnected(name, binder);
    };
    // Hook every overload of a()
    var overloads = eCls.a.overloads;
    console.log("e.a has " + overloads.length + " overloads");
    for (var i = 0; i < overloads.length; i++) {
        (function (ov, idx) {
            ov.implementation = function () {
                console.log("[e.a overload " + idx + "] called, args=" + arguments.length);
                return ov.apply(this, arguments);
            };
        })(overloads[i], i);
    }
    console.log("[+] hooked all e.a overloads + onServiceConnected");
    console.log("=== diag_e2 loaded ===");
});