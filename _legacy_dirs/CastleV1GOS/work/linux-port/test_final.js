// Final cleartext bypass - targeting the correct class
console.log("=== Final Bypass Script ===");

Java.perform(function () {
    console.log("[+] Java.perform started");

    // Hook NetworkSecurityPolicy - use the correct class name from Android 11
    try {
        var NSP = Java.use("android.security.NetworkSecurityPolicy");
        console.log("[+] Found NetworkSecurityPolicy");

        // Hook isCleartextTrafficPermitted(String)
        try {
            NSP.isCleartextTrafficPermitted.overload("java.lang.String").implementation = function(host) {
                console.log("[+] NSP.isCleartextTrafficPermitted(host=" + host + ") -> true");
                return true;
            };
            console.log("[+] Hooked isCleartextTrafficPermitted(String)");
        } catch(e) {
            console.log("[-] String overload: " + e);
        }

        // Hook isCleartextTrafficPermitted()
        try {
            NSP.isCleartextTrafficPermitted.overload().implementation = function() {
                console.log("[+] NSP.isCleartextTrafficPermitted() -> true");
                return true;
            };
            console.log("[+] Hooked isCleartextTrafficPermitted()");
        } catch(e) {
            console.log("[-] No-arg overload: " + e);
        }

        // Hook setCleartextTrafficPermitted
        try {
            NSP.setCleartextTrafficPermitted.overload("boolean").implementation = function(allowed) {
                console.log("[+] NSP.setCleartextTrafficPermitted(" + allowed + ") -> forcing true");
                this.setCleartextTrafficPermitted(true);
            };
            console.log("[+] Hooked setCleartextTrafficPermitted");
        } catch(e) {
            console.log("[-] setCleartextTrafficPermitted hook: " + e);
        }
    } catch(e) {
        console.log("[-] NSP hook failed: " + e);
    }

    // Hook Apache HttpClient DefaultRequestDirector.execute
    try {
        var DRD = Java.use("org.apache.http.impl.client.DefaultRequestDirector");
        console.log("[+] Found DefaultRequestDirector");

        DRD.execute.overload(
            "org.apache.http.HttpHost",
            "org.apache.http.HttpRequest",
            "org.apache.http.protocol.HttpContext"
        ).implementation = function(host, request, context) {
            console.log("[+] DRD.execute: " + host);

            // If it's the license server, return a mock response
            if (host && host.toString && host.toString().indexOf("android.clients.google.com") >= 0) {
                console.log("[+] Intercepting license server request!");

                var mockBody = "0|123456789|jp.konami.castlevania|1|user1|0";
                var BasicHttpResponse = Java.use("org.apache.http.message.BasicHttpResponse");
                var BasicStatusLine = Java.use("org.apache.http.message.BasicStatusLine");
                var ProtocolVersion = Java.use("org.apache.http.ProtocolVersion");
                var StringEntity = Java.use("org.apache.http.entity.StringEntity");

                var version = ProtocolVersion.$new("HTTP", 1, 1);
                var statusLine = BasicStatusLine.$new(version, 200, "OK");
                var response = BasicHttpResponse.$new(statusLine);
                var entity = StringEntity.$new(mockBody);
                response.setEntity(entity);

                console.log("[+] Returning mock LICENSED response");
                return response;
            }

            try {
                return this.execute(host, request, context);
            } catch(e) {
                console.log("[+] Exception: " + e.getMessage());
                throw e;
            }
        };
        console.log("[+] Hooked DRD.execute");
    } catch(e) {
        console.log("[-] DRD hook failed: " + e);
    }

    // Hook the callback interface d (license response callback)
    try {
        var dStub = Java.use("com.google.android.vending.licensing.d$a");
        console.log("[+] Found callback d$a");

        dStub.a.overload("int", "java.lang.String", "java.lang.String").implementation = function(responseCode, signedResponse, signature) {
            console.log("[+] License callback: responseCode=" + responseCode);
            console.log("[+] signedResponse: " + signedResponse);

            if (responseCode != 0) {
                console.log("[+] Forcing LICENSED (changed " + responseCode + " -> 0)");
                return this.a(0, "0|123456789|jp.konami.castlevania|1|user1|0", "mock_sig");
            }
            return this.a(responseCode, signedResponse, signature);
        };
        console.log("[+] Hooked d$a.a(int, String, String)");
    } catch(e) {
        console.log("[-] d$a hook failed: " + e);
    }

    // Hook callback interface f
    try {
        var f = Java.use("com.google.android.vending.licensing.f");
        console.log("[+] Found callback interface f");

        f.b.implementation = function(errorCode) {
            console.log("[+] f.b(" + errorCode + ") -> converting to LICENSED");
            return this.a(0);
        };
        console.log("[+] Hooked f.b -> f.a(0)");
    } catch(e) {
        console.log("[-] f hook failed: " + e);
    }

    // Hook LicenseValidator
    try {
        var g = Java.use("com.google.android.vending.licensing.g");
        console.log("[+] Found LicenseValidator g");

        g.d.implementation = function() {
            console.log("[+] LicenseValidator.d() -> converting to success");
            var callback = this.b;
            callback.a(0);
        };
        console.log("[+] Hooked g.d() -> success");
    } catch(e) {
        console.log("[-] g hook failed: " + e);
    }

    console.log("[+] All hooks installed!");
});

console.log("[*] Script loaded, waiting for license check...");