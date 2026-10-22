// diag_e_methods.js — hook every method of com.google.android.vending.licensing.e to find the entry point.
console.log("=== diag_e_methods START ===");
Java.perform(function () {
    var eCls = Java.use("com.google.android.vending.licensing.e");
    var methods = eCls.class.getDeclaredMethods();
    console.log("e has " + methods.length + " methods");
    for (var i = 0; i < methods.length; i++) {
        var m = methods[i];
        var name = m.getName();
        var params = m.getParameterTypes();
        var sig = name + "(" + params.map(function(p){return p.getName();}).join(",") + ")";
        // build overload signature
        var overloadSig = params.map(function(p){return p.getName();});
        try {
            var hook = function (sig) {
                return function () {
                    console.log("[e CALL] " + sig + " args=" + arguments.length);
                    // call original
                    return this[sig.split("(")[0]].apply(this, arguments);
                };
            };
            // Frida needs overload; use apply with the method name
            eCls[name].implementation = function () {
                console.log("[e CALL] " + sig);
                return eCls[name].apply(this, arguments);
            };
            console.log("[hooked] " + sig);
        } catch (e) {
            console.log("[skip] " + sig + " : " + e);
        }
    }
    console.log("=== diag_e_methods loaded ===");
});