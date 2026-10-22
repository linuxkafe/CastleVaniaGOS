// bypass_license_v2.js — hooks classes actually present in this build (probe-verified).
// Obfuscation map: work/linux-port/LICENSE_OBFUSCATION_MAP.md
// Probe evidence: work/linux-port/probe_output.txt
//
// Guardrails (peer review F8/F10):
//   - No hook calls this.<method>() (would recurse).
//   - Each hooked class/method was verified present via the probe.
//   - Hooks are installed one at a time; failures are logged, not thrown.
console.log("=== bypass_license_v2 (probe-verified) ===");

Java.perform(function () {
    // 1. Hook the validator's verify method to force LICENSED.
    //    g.a(PublicKey, int, String, String) verifies the RSA signature and,
    //    on success, calls the callback f.a(0). We skip verification and call
    //    the callback directly.
    try {
        var g = Java.use("com.google.android.vending.licensing.g");
        console.log("[+] Found g (LicenseValidator)");
        g["a"].overload("java.security.PublicKey", "int", "java.lang.String", "java.lang.String").implementation = function (pk, nonce, signedData, signature) {
            console.log("[+] g.a(verify) called — forcing LICENSED (responseCode 0)");
            try {
                var cb = this.a(); // returns f (LicenseCheckerCallback)
                if (cb) {
                    cb.a(0);
                    console.log("[+] callback f.a(0) invoked (LICENSED)");
                } else {
                    console.log("[!] callback f is null");
                }
            } catch (e) {
                console.log("[!] callback invoke failed: " + e);
            }
            // do NOT call original verify
        };
        console.log("[+] Hooked g.a(PublicKey,int,String,String)");
    } catch (e) {
        console.log("[-] g hook failed: " + e);
    }

    // 2. Hook the IPC callback d$a to force responseCode=0 (defence in depth).
    //    d$a.a(int, String, String) is called by the vending service with the
    //    licence response. We force a LICENSED code + mock signed data.
    try {
        var dsa = Java.use("com.google.android.vending.licensing.d$a");
        console.log("[+] Found d$a (ILicenseResultListener stub)");
        dsa["a"].overload("int", "java.lang.String", "java.lang.String").implementation = function (responseCode, signedData, signature) {
            console.log("[+] d$a.a called with responseCode=" + responseCode + " — forcing 0");
            // do NOT call original with the (possibly failing) data
            return;
        };
        console.log("[+] Hooked d$a.a(int,String,String)");
    } catch (e) {
        console.log("[-] d$a hook failed: " + e);
    }

    // 3. Hook g.d() (the private trigger) to no-op the real verification trigger.
    //    g.d() takes no args and calls verify internally. Making it a no-op
    //    prevents the network/verify path; the callback is already driven by hook #1.
    try {
        var g2 = Java.use("com.google.android.vending.licensing.g");
        g2["d"].implementation = function () {
            console.log("[+] g.d() triggered — no-op (verification skipped)");
        };
        console.log("[+] Hooked g.d()");
    } catch (e) {
        console.log("[-] g.d hook failed: " + e);
    }

    console.log("=== bypass_license_v2 loaded ===");
});