// STATUS: NON-FUNCTIONAL (as of 2026-10-22, round-1 peer review F1/F2).
// The classes and methods hooked below are ABSENT from the game's classes.dex
// (verified: strings -a extracted/classes.dex | grep -F -c <name> == 0 for each).
// The licensing client exists only under obfuscated names (com.google.android.vending.licensing.a..m).
// This script is retained for reference only and cannot bypass the licence check as written.
// See aes/peer-reviews/castlevania-t009-r1/final-synthesis.md (F1, F2).

// Simple cleartext bypass script
console.log("Hooking NetworkSecurityPolicy...");

// Hook the NetworkSecurityPolicy class
Java.perform(function() {
    var NetworkSecurityPolicy = Java.use("android.security.net.config.NetworkSecurityPolicy");
    
    // Get the cleartext traffic permitted method
    var getInstance = NetworkSecurityPolicy.getInstance.overload();
    getInstance.implementation = function() {
        var result = getInstance.call(this);
        console.log("Got NetworkSecurityPolicy instance");
        return result;
    };
    
    // Hook isCleartextTrafficPermitted
    var isCleartext = NetworkSecurityPolicy.isCleartextTrafficPermitted.overload("java.net.URI");
    isCleartext.implementation = function(uri) {
        console.log("isCleartextTrafficPermitted called for: " + uri);
        return true; // Force return true
    };
    
    // Also hook the string version
    var isCleartextStr = NetworkSecurityPolicy.isCleartextTrafficPermitted.overload("java.lang.String");
    isCleartextStr.implementation = function(host) {
        console.log("isCleartextTrafficPermitted called for: " + host);
        return true; // Force return true
    };
    
    console.log("NetworkSecurityPolicy hooks installed");
});

// Also hook OkHttp if present
console.log("Hooking OkHttp...");
Java.perform(function() {
    try {
        var OkHttp = Java.use("okhttp3.OkHttpClient");
        if (OkHttp) {
            console.log("Found OkHttpClient");
        }
    } catch(e) {
        console.log("OkHttp not found: " + e);
    }
});

console.log("Script loaded");
setInterval(function() {
    // Keep the script alive
}, 1000);