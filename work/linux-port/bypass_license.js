// STATUS: NON-FUNCTIONAL (as of 2026-10-22, round-1 peer review F1/F2).
// The classes and methods hooked below are ABSENT from the game's classes.dex
// (verified: strings -a extracted/classes.dex | grep -F -c <name> == 0 for each).
// The licensing client exists only under obfuscated names (com.google.android.vending.licensing.a..m).
// This script is retained for reference only and cannot bypass the licence check as written.
// See aes/peer-reviews/castlevania-t009-r1/final-synthesis.md (F1, F2).

// Frida script to bypass Google Play License check
// Hooks LicenseChecker.checkLicense to return LICENSE_OK (0)

Java.perform(function() {
    console.log("[*] Starting license bypass...");
    
    // Try to find and hook the license checker
    try {
        var LicenseChecker = Java.use("com.android.vending.licensing.LicenseChecker");
        console.log("[*] Found LicenseChecker");
        
        LicenseChecker.checkLicense.implementation = function(callback, data, signature) {
            console.log("[*] Hooking LicenseChecker.checkLicense");
            
            // Call the callback with LICENSE_OK (0)
            setTimeout(function() {
                try {
                    callback.onLicenseChecked(null, 0);
                    console.log("[*] License check bypassed - returning LICENSE_OK");
                } catch(e) {
                    console.log("[*] Error in callback: " + e);
                }
            }, 100);
        };
        
        console.log("[*] LicenseChecker hooked successfully");
    } catch(e) {
        console.log("[*] LicenseChecker not found: " + e);
    }
    
    // Also hook the IabHelper if it exists
    try {
        var IabHelper = Java.use("com.android.vending.billing.IabHelper");
        console.log("[*] Found IabHelper");
        
        IabHelper.startup.implementation = function(requests) {
            console.log("[*] Hooking IabHelper.startup");
            var result = startup.call(this, requests);
            console.log("[*] IabHelper.startup result: " + result);
            return result;
        };
        
        console.log("[*] IabHelper hooked");
    } catch(e) {
        console.log("[*] IabHelper not found: " + e);
    }
    
    // Hook mvpToken to return valid token
    try {
        var Security = Java.use("com.android.vending.licensing.Security");
        console.log("[*] Found Security");
        
        Security.verifyLicense.implementation = function(packageName, nonce, signedData, signature) {
            console.log("[*] Hooking Security.verifyLicense");
            return true;
        };
        
        console.log("[*] Security hooked");
    } catch(e) {
        console.log("[*] Security not found: " + e);
    }
    
    console.log("[*] License bypass setup complete");
});