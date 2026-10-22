// skip_uda.js — prevent UnityDownloaderActivity from being launched.
console.log("=== skip_uda START ===");
Java.perform(function () {
    var Activity = Java.use("android.app.Activity");
    // Hook startActivity(Intent)
    Activity.startActivity.overload("android.content.Intent").implementation = function (intent) {
        var cmp = null;
        try { cmp = intent.getComponent(); } catch (e) {}
        var cmpStr = cmp ? cmp.flattenToString() : null;
        if (cmpStr && cmpStr.indexOf("UnityDownloaderActivity") >= 0) {
            console.log("[skip_uda] startActivity -> UnityDownloaderActivity DROPPED");
            return;
        }
        return this.startActivity(intent);
    };
    // Hook startActivity(Intent, Bundle)
    try {
        Activity.startActivity.overload("android.content.Intent", "android.os.Bundle").implementation = function (intent, opts) {
            var cmp = null;
            try { cmp = intent.getComponent(); } catch (e) {}
            var cmpStr = cmp ? cmp.flattenToString() : null;
            if (cmpStr && cmpStr.indexOf("UnityDownloaderActivity") >= 0) {
                console.log("[skip_uda] startActivity(Bundle) -> UnityDownloaderActivity DROPPED");
                return;
            }
            return this.startActivity(intent, opts);
        };
        console.log("[skip_uda] hooked startActivity(Intent,Bundle)");
    } catch (e) { console.log("[skip_uda] startActivity(Intent,Bundle) not found: " + e); }
    // Hook startActivityForResult
    try {
        Activity.startActivityForResult.overload("android.content.Intent", "int").implementation = function (intent, code) {
            var cmp = null;
            try { cmp = intent.getComponent(); } catch (e) {}
            var cmpStr = cmp ? cmp.flattenToString() : null;
            if (cmpStr && cmpStr.indexOf("UnityDownloaderActivity") >= 0) {
                console.log("[skip_uda] startActivityForResult -> UnityDownloaderActivity DROPPED");
                return;
            }
            return this.startActivityForResult(intent, code);
        };
        console.log("[skip_uda] hooked startActivityForResult(Intent,int)");
    } catch (e) { console.log("[skip_uda] startActivityForResult not found: " + e); }

    console.log("[skip_uda] loaded");
});