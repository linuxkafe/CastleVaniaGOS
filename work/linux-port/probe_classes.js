// probe_classes.js — enumerate loaded classes containing "license"/"licensing"/"vending"
// Uses Java.enumerateClassesLoadedBy (NOT enumerateLoadedClasses, which crashes).
console.log("===== PROBE2 START =====");
Java.perform(function () {
    var loader = Java.classFactory.loader;
    console.log("loader: " + loader);
    var matches = [];
    Java.enumerateClassesLoadedBy(loader, {
        onMatch: function (name) {
            var low = name.toLowerCase();
            if (low.indexOf("licens") >= 0 || low.indexOf("vending") >= 0) {
                matches.push(name);
            }
        },
        onComplete: function () {
            console.log("matched classes (" + matches.length + "):");
            matches.sort();
            for (var i = 0; i < matches.length; i++) console.log("  " + matches[i]);
            console.log("===== PROBE2 END =====");
        }
    });
});