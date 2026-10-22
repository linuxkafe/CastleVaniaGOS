// bypass_license_v4.js — hooks the concrete IPC callback e$a (probe-verified).
// Obfuscation map: work/linux-port/LICENSE_OBFUSCATION_MAP.md
// Probe evidence: work/linux-port/probe_output.txt, probe_ea output
//
// Strategy:
//   e$a is the concrete ILicenseResultListener. Its a(int,String,String) is the IPC
//   callback from the vending service. We hook it to force responseCode=0 and
//   deliver LICENSED via this.b.a().a(0) (validator's callback -> app callback).
//   Plus a proxy at e.a(f) (defence: error path) and a g.a guard.
//
// Guardrails (peer review F8/F10): no this.<method>() recursion; each class verified.
console.log("=== bypass_license_v4 (e$a IPC callback) ===");

Java.perform(function () {
    var fIface = null, eCls = null, gCls = null, eaCls = null;
    try { fIface = Java.use("com.google.android.vending.licensing.f"); console.log("[+] Found f"); } catch (e) { console.log("[-] f: " + e); }
    try { eCls = Java.use("com.google.android.vending.licensing.e"); console.log("[+] Found e"); } catch (e) { console.log("[-] e: " + e); }
    try { gCls = Java.use("com.google.android.vending.licensing.g"); console.log("[+] Found g"); } catch (e) { console.log("[-] g: " + e); }
    try { eaCls = Java.use("com.google.android.vending.licensing.e$a"); console.log("[+] Found e$a"); } catch (e) { console.log("[-] e$a: " + e); }

    // Register proxy implementing f that forces LICENSED.
    var ProxyCls = null;
    if (fIface) {
        try {
            ProxyCls = Java.registerClass({
                name: "com.example.LicenseProxy4",
                implements: [fIface],
                fields: { original: "com.google.android.vending.licensing.f" },
                methods: {
                    a: function (code) { console.log("[proxy] f.a(" + code + ") -> original.a(0)"); try { if (this.original) this.original.a(0); } catch (e) {} },
                    b: function (code) { console.log("[proxy] f.b(" + code + ") -> original.a(0)"); try { if (this.original) this.original.a(0); } catch (e) {} },
                    c: function (code) { console.log("[proxy] f.c(" + code + ") -> original.a(0)"); try { if (this.original) this.original.a(0); } catch (e) {} }
                }
            });
            console.log("[+] Registered LicenseProxy4");
        } catch (e) { console.log("[-] registerClass: " + e); }
    }

    // 1. Hook e.a(f) (checkLicense entry) -> replace callback with proxy.
    if (eCls && ProxyCls) {
        try {
            eCls["a"].overload("com.google.android.vending.licensing.f").implementation = function (cb) {
                console.log("[+] e.a(checkLicense) called; replacing callback with proxy");
                var proxy = ProxyCls.$new();
                try { proxy.original.value = cb; } catch (e) { try { proxy.original = cb; } catch (e2) {} }
                return this.a(proxy);
            };
            console.log("[+] Hooked e.a(f)");
        } catch (e) { console.log("[-] e.a hook: " + e); }
    }

    // 2. Hook e$a.a(int,String,String) (IPC callback) -> force LICENSED.
    if (eaCls) {
        try {
            eaCls["a"].overload("int", "java.lang.String", "java.lang.String").implementation = function (responseCode, signedData, signature) {
                console.log("[+] e$a.a(IPC) called responseCode=" + responseCode + " — forcing LICENSED");
                try {
                    var cb = this.b.a(); // g.a() -> f (proxy)
                    if (cb) { cb.a(0); console.log("[+] delivered f.a(0) (LICENSED)"); }
                } catch (e) { console.log("[!] deliver failed: " + e); }
                // do not call original
            };
            console.log("[+] Hooked e$a.a(int,String,String)");
        } catch (e) { console.log("[-] e$a.a hook: " + e); }
    }

    // 3. Hook g.a(PublicKey,int,String,String) (verify) -> skip RSA, force callback 0.
    if (gCls) {
        try {
            gCls["a"].overload("java.security.PublicKey", "int", "java.lang.String", "java.lang.String").implementation = function (pk, nonce, signedData, signature) {
                console.log("[+] g.a(verify) called — forcing LICENSED");
                try {
                    var cb = this.a();
                    if (cb) cb.a(0);
                } catch (e) { console.log("[!] g.a cb failed: " + e); }
            };
            console.log("[+] Hooked g.a(PublicKey,int,String,String)");
        } catch (e) { console.log("[-] g.a hook: " + e); }
    }

    console.log("=== bypass_license_v4 loaded ===");
});