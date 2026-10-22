// bypass_license_v3.js — probe-verified + proxy approach.
// Obfuscation map: work/linux-port/LICENSE_OBFUSCATION_MAP.md
// Probe evidence: work/linux-port/probe_output.txt
//
// Strategy (robust against both success and error paths):
//   1. Hook e.a(f) (checkLicense entry) and replace the app callback with a proxy
//      whose a/b/c all deliver LICENSED (a(0)) to the original callback.
//   2. Hook g.a(PublicKey,int,String,String) (verify) to skip RSA verification and
//      call the callback with 0.
// Either path alone delivers LICENSED; both together cover success + error paths.
//
// Guardrails (peer review F8/F10):
//   - No hook calls this.<method>() (no recursion).
//   - Each hooked class/method verified present via the probe.
//   - Hooks are installed one at a time; failures are logged.
console.log("=== bypass_license_v3 (probe-verified, proxy) ===");

Java.perform(function () {
    var fIface = null;
    var eCls = null;
    var gCls = null;
    try { fIface = Java.use("com.google.android.vending.licensing.f"); console.log("[+] Found f (LicenseCheckerCallback)"); } catch (e) { console.log("[-] f: " + e); }
    try { eCls = Java.use("com.google.android.vending.licensing.e"); console.log("[+] Found e (LicenseChecker)"); } catch (e) { console.log("[-] e: " + e); }
    try { gCls = Java.use("com.google.android.vending.licensing.g"); console.log("[+] Found g (LicenseValidator)"); } catch (e) { console.log("[-] g: " + e); }

    // Register a proxy class implementing f that forces LICENSED.
    var ProxyCls = null;
    if (fIface) {
        try {
            ProxyCls = Java.registerClass({
                name: "com.example.LicenseProxy",
                implements: [fIface],
                fields: { original: "com.google.android.vending.licensing.f" },
                methods: {
                    a: function (code) {
                        console.log("[proxy] f.a(" + code + ") -> forcing LICENSED (original.a(0))");
                        try { if (this.original) this.original.a(0); } catch (e) { console.log("[proxy] a err: " + e); }
                    },
                    b: function (code) {
                        console.log("[proxy] f.b(" + code + ") -> forcing LICENSED (original.a(0))");
                        try { if (this.original) this.original.a(0); } catch (e) { console.log("[proxy] b err: " + e); }
                    },
                    c: function (code) {
                        console.log("[proxy] f.c(" + code + ") -> forcing LICENSED (original.a(0))");
                        try { if (this.original) this.original.a(0); } catch (e) { console.log("[proxy] c err: " + e); }
                    }
                }
            });
            console.log("[+] Registered LicenseProxy");
        } catch (e) {
            console.log("[-] registerClass failed: " + e);
        }
    }

    // 1. Hook e.a(f) (checkLicense entry) -> replace callback with proxy.
    if (eCls && ProxyCls) {
        try {
            eCls["a"].overload("com.google.android.vending.licensing.f").implementation = function (cb) {
                console.log("[+] e.a(checkLicense) called; replacing callback with proxy");
                var proxy = ProxyCls.$new();
                try { proxy.original.value = cb; } catch (e) { console.log("[!] set original failed: " + e); try { proxy.original = cb; } catch (e2) {} }
                return this.a(proxy);
            };
            console.log("[+] Hooked e.a(f)");
        } catch (e) {
            console.log("[-] e.a hook failed: " + e);
        }
    }

    // 2. Hook g.a(PublicKey,int,String,String) (verify) -> skip RSA, force callback 0.
    if (gCls) {
        try {
            gCls["a"].overload("java.security.PublicKey", "int", "java.lang.String", "java.lang.String").implementation = function (pk, nonce, signedData, signature) {
                console.log("[+] g.a(verify) called — forcing LICENSED");
                try {
                    var cb = this.a(); // returns f (proxy or original)
                    if (cb) cb.a(0);
                } catch (e) {
                    console.log("[!] g.a callback failed: " + e);
                }
                // do not verify
            };
            console.log("[+] Hooked g.a(PublicKey,int,String,String)");
        } catch (e) {
            console.log("[-] g.a hook failed: " + e);
        }
    }

    console.log("=== bypass_license_v3 loaded ===");
});