// STATUS: NON-FUNCTIONAL (as of 2026-10-22, round-1 peer review F1/F2).
// The classes and methods hooked below are ABSENT from the game's classes.dex
// (verified: strings -a extracted/classes.dex | grep -F -c <name> == 0 for each).
// The licensing client exists only under obfuscated names (com.google.android.vending.licensing.a..m).
// This script is retained for reference only and cannot bypass the licence check as written.
// See aes/peer-reviews/castlevania-t009-r1/final-synthesis.md (F1, F2).

// Frida script to bypass IAB purchase loop and proceed with game
setTimeout(function() {
    Java.perform(function() {
        console.log("[*] Bypassing IAB and download checks...");
        
        // Hook Konami IAB to return success without actual purchase
        try {
            var KonamiIab = Java.use("jp.konami.android.common.iab.KonamiIabHelper");
            console.log("[*] Found KonamiIabHelper");
            
            // Hook the purchase method to return success
            try {
                KonamiIab.buyItem.overload('java.lang.String', 'java.lang.String').implementation = function(productId, requestBody) {
                    console.log("[*] buyItem(\"" + productId + "\") -> returning success");
                    // Call the listener with success
                    setTimeout(function() {
                        try {
                            var listener = KonamiIab.mRequestListener.value;
                            if (listener != null) {
                                listener.onPurchaseSuccess(null, null);
                            }
                        } catch(e) {}
                    }, 10);
                    return true;
                };
                console.log("[*] buyItem hooked");
            } catch(e) {
                console.log("[*] buyItem hook error: " + e);
            }
            
            // Hook queryPurchases to return empty (no subscriptions owned)
            try {
                KonamiIab.queryInventoryAsync.implementation = function(callback) {
                    console.log("[*] queryInventoryAsync -> returning empty");
                    setTimeout(function() {
                        try {
                            if (callback != null) {
                                callback.onQueryInventoryFinished(null, null);
                            }
                        } catch(e) {}
                    }, 10);
                };
                console.log("[*] queryInventoryAsync hooked");
            } catch(e) {
                console.log("[*] queryInventoryAsync hook error: " + e);
            }
        } catch(e) {
            console.log("[*] KonamiIabHelper not found: " + e);
        }
        
        // Also hook the generic IAB helper
        try {
            var IabHelper = Java.use("com.android.vending.billing.IabHelper");
            console.log("[*] Found IabHelper");
            
            IabHelper.launchPurchaseFlow.implementation = function(request, sku, requestCode, listener) {
                console.log("[*] launchPurchaseFlow(\"" + sku + "\") -> bypassing");
                setTimeout(function() {
                    try {
                        if (listener != null) {
                            // Return success
                            var result = Java.use("com.android.vending.billing.IabResult");
                            var iabResult = result.$new(0, "Purchase successful");
                            listener.onPurchaseSuccess(null, '{"productId":"' + sku + '","orderId":"mock"}');
                        }
                    } catch(e) {
                        console.log("[*] Purchase callback error: " + e);
                    }
                }, 10);
                return true;
            };
            console.log("[*] IabHelper.launchPurchaseFlow hooked");
        } catch(e) {
            console.log("[*] IabHelper not found: " + e);
        }
        
        // Hook UnityDownloaderActivity to skip download
        try {
            var Downloader = Java.use("com.unity3d.plugin.downloader.UnityDownloaderActivity");
            console.log("[*] Found UnityDownloaderActivity");
            
            // Try to skip the download check
            try {
                Downloader.checkDownloadComplete.implementation = function() {
                    console.log("[*] checkDownloadComplete -> returning true (skipping)");
                    return true;
                };
                console.log("[*] checkDownloadComplete hooked");
            } catch(e) {}
            
            try {
                // Do NOT call this.onStart() here: under Frida that re-invokes this
                // replacement and recurses until stack overflow. The hook intentionally
                // does nothing (skips the download) and returns.
                Downloader.onStart.implementation = function() {
                    console.log("[*] onStart -> skipping download (no self-call)");
                };
                console.log("[*] onStart hooked");
            } catch(e) {}
        } catch(e) {
            console.log("[*] UnityDownloaderActivity not found: " + e);
        }
        
        // Hook the main activity to proceed
        try {
            var MainActivity = Java.use("jp.konami.android.common.iab.KonamiIabUnityPlayerActivity");
            console.log("[*] Found main activity");
            
            // Check if there's a method to skip intro
            var methods = MainActivity.class.getMethods();
            for (var i = 0; i < Math.min(10, methods.length); i++) {
                console.log("[*] Method: " + methods[i].toString());
            }
        } catch(e) {
            console.log("[*] Main activity not found: " + e);
        }
        
        console.log("[*] IAB bypass setup complete");
    });
}, 0);