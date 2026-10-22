// probe_ea.js — probe e$a nested class methods
console.log("=== probe_ea START ===");
Java.perform(function () {
    try {
        var ea = Java.use("com.google.android.vending.licensing.e$a");
        console.log("### FOUND: com.google.android.vending.licensing.e$a");
        var ms = ea.class.getDeclaredMethods();
        console.log("methods (" + ms.length + "):");
        for (var i = 0; i < ms.length; i++) console.log("  " + ms[i].toString());
        var fs = ea.class.getDeclaredFields();
        console.log("fields (" + fs.length + "):");
        for (var i = 0; i < fs.length; i++) console.log("  " + fs[i].toString());
        // also check deeper nesting
        var nested = ea.class.getDeclaredClasses();
        console.log("nested (" + nested.length + "):");
        for (var i = 0; i < nested.length; i++) console.log("  " + nested[i].getName());
    } catch (e) {
        console.log("e$a absent: " + e);
    }
    console.log("=== probe_ea END ===");
});