// probe_licensing.js — read-only probe of obfuscated licensing classes in the game process.
// Usage (on the Deck, inside the container):
//   frida -U -n jp.konami.castlevania -l probe_licensing.js --runtime=v8 > probe_output.txt 2>&1
// Do NOT use Java.enumerateLoadedClasses() (crashes Frida). Probe explicit names only.
//
// Output: for each class in com.google.android.vending.licensing.<a..z> that resolves,
// prints the class name, superclass, declared methods (name + signature) and fields.
// Also probes the shared AIDL interfaces (not obfuscated).

console.log("===== PROBE START =====");
console.log("target: com.google.android.vending.licensing.*");

Java.perform(function () {
    var pkg = "com.google.android.vending.licensing.";

    // Probe single-letter classes a..z
    for (var i = 0; i < 26; i++) {
        var letter = String.fromCharCode(97 + i);
        var name = pkg + letter;
        try {
            var cls = Java.use(name);
            console.log("");
            console.log("### CLASS FOUND: " + name);
            try {
                console.log("  superclass: " + cls.class.getSuperclass());
            } catch (e) { console.log("  superclass: (err) " + e); }
            // declared methods
            try {
                var methods = cls.class.getDeclaredMethods();
                console.log("  methods (" + methods.length + "):");
                for (var m = 0; m < methods.length; m++) {
                    console.log("    " + methods[m].toString());
                }
            } catch (e) { console.log("  methods: (err) " + e); }
            // declared fields
            try {
                var fields = cls.class.getDeclaredFields();
                console.log("  fields (" + fields.length + "):");
                for (var f = 0; f < fields.length; f++) {
                    console.log("    " + fields[f].toString());
                }
            } catch (e) { console.log("  fields: (err) " + e); }
            // nested classes
            try {
                var nested = cls.class.getDeclaredClasses();
                if (nested.length > 0) {
                    console.log("  nested (" + nested.length + "):");
                    for (var n = 0; n < nested.length; n++) {
                        console.log("    " + nested[n].getName());
                    }
                }
            } catch (e) {}
        } catch (e) {
            // class absent — expected for most letters
        }
    }

    // Probe shared AIDL interfaces (not obfuscated)
    var aidl = [
        "com.android.vending.licensing.ILicensingService",
        "com.android.vending.licensing.ILicenseResultListener",
    ];
    for (var a = 0; a < aidl.length; a++) {
        try {
            var c = Java.use(aidl[a]);
            console.log("");
            console.log("### AIDL FOUND: " + aidl[a]);
            var ms = c.class.getDeclaredMethods();
            console.log("  methods (" + ms.length + "):");
            for (var m = 0; m < ms.length; m++) {
                console.log("    " + ms[m].toString());
            }
        } catch (e) {
            console.log("### AIDL ABSENT: " + aidl[a] + " (" + e + ")");
        }
    }

    console.log("");
    console.log("===== PROBE END =====");
});