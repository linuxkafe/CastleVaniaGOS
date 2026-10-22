// STATUS: NON-FUNCTIONAL (as of 2026-10-22, round-1 peer review F1/F2).
// The classes and methods hooked below are ABSENT from the game's classes.dex
// (verified: strings -a extracted/classes.dex | grep -F -c <name> == 0 for each).
// The licensing client exists only under obfuscated names (com.google.android.vending.licensing.a..m).
// This script is retained for reference only and cannot bypass the licence check as written.
// See aes/peer-reviews/castlevania-t009-r1/final-synthesis.md (F1, F2).

// Frida script to bypass cleartext and license checks in all processes
setTimeout(function() {
    Java.perform(function() {
        console.log("[*] Bypassing network security restrictions...");
        
        // Hook NetworkSecurityPolicy in ALL processes
        try {
            var NSP = Java.use("android.security.net.config.NetworkSecurityPolicy");
            console.log("[*] Found NetworkSecurityPolicy");
            
            NSP.isCleartextTrafficPermitted.overload().implementation = function() {
                return true;
            };
            
            NSP.isCleartextTrafficPermitted.overload('java.lang.String').implementation = function(host) {
                console.log("[*] Allowing cleartext for: " + host);
                return true;
            };
            
            console.log("[*] NetworkSecurityPolicy hooked - cleartext allowed");
        } catch(e) {
            console.log("[*] NetworkSecurityPolicy hook failed: " + e);
        }
        
        // Also hook the internal method
        try {
            var Policy = Java.use("android.security.net.config.NetworkSecurityPolicyImpl");
            console.log("[*] Found NetworkSecurityPolicyImpl");
            
            Policy.isCleartextTrafficPermitted.overload().implementation = function() {
                return true;
            };
            
            Policy.isCleartextTrafficPermitted.overload('java.lang.String').implementation = function(host) {
                return true;
            };
            
            console.log("[*] NetworkSecurityPolicyImpl hooked");
        } catch(e) {
            console.log("[*] NetworkSecurityPolicyImpl not found: " + e);
        }
        
        // Hook LicenseChecker if present
        try {
            var LicenseChecker = Java.use("com.google.android.vending.licensing.LicenseChecker");
            console.log("[*] Found LicenseChecker");
            
            LicenseChecker.checkLicense.implementation = function(callback, data, signature) {
                console.log("[*] checkLicense called - returning LICENSED");
                setTimeout(function() {
                    try {
                        callback.onLicenseChecked(null, 0);
                    } catch(e) {}
                }, 50);
            };
            console.log("[*] LicenseChecker hooked");
        } catch(e) {
            console.log("[*] LicenseChecker not found: " + e);
        }
        
        // Hook IAB to prevent purchase loops
        try {
            var IabHelper = Java.use("com.android.vending.billing.IabHelper");
            console.log("[*] Found IabHelper");
            
            IabHelper.launchPurchaseFlow.implementation = function(request, sku, requestCode, listener) {
                console.log("[*] launchPurchaseFlow(\"" + sku + "\") -> bypassing");
                setTimeout(function() {
                    if (listener != null) {
                        try {
                            listener.onPurchaseSuccess(null, '{"productId":"' + sku + '"}');
                        } catch(e) {}
                    }
                }, 10);
                return true;
            };
            console.log("[*] IabHelper.launchPurchaseFlow hooked");
        } catch(e) {
            console.log("[*] IabHelper not found: " + e);
        }
        
        console.log("[*] All hooks installed successfully");
    });
}, 0);