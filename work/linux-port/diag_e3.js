// diag_e3.js — inside e.onServiceConnected, dump fields + service class
console.log("=== diag_e3 START ===");
Java.perform(function () {
    var eCls = Java.use("com.google.android.vending.licensing.e");
    eCls.onServiceConnected.implementation = function (name, binder) {
        console.log("[e.onServiceConnected] name=" + name);
        // dump fields
        var fields = this.getClass().getDeclaredFields();
        for (var i = 0; i < fields.length; i++) {
            fields[i].setAccessible(true);
            try {
                var v = fields[i].get(this);
                console.log("  field " + fields[i].getName() + " = " + v + " (" + (v ? v.getClass().getName() : "null") + ")");
            } catch (ex) { console.log("  field " + fields[i].getName() + " = <err " + ex + ">"); }
        }
        return this.onServiceConnected(name, binder);
    };
    console.log("[+] hooked");
    console.log("=== diag_e3 loaded ===");
});