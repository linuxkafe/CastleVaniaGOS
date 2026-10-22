// probe_uda.js — probe UnityDownloaderActivity methods
console.log("=== probe_uda START ===");
Java.perform(function () {
    var uda = Java.use("com.unity3d.plugin.downloader.UnityDownloaderActivity");
    console.log("### FOUND: UnityDownloaderActivity");
    var ms = uda.class.getDeclaredMethods();
    console.log("methods (" + ms.length + "):");
    for (var i = 0; i < ms.length; i++) console.log("  " + ms[i].toString());
    // inner classes
    var nested = uda.class.getDeclaredClasses();
    console.log("nested (" + nested.length + "):");
    for (var i = 0; i < nested.length; i++) {
        console.log("  " + nested[i].getName());
        var nms = nested[i].getDeclaredMethods();
        for (var j = 0; j < nms.length; j++) console.log("    " + nms[j].toString());
    }
    console.log("=== probe_uda END ===");
});