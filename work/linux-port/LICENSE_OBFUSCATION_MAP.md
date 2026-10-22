# Obfuscation map — com.google.android.vending.licensing (this build)

Source: `work/linux-port/probe_licensing.js` run against PID 9700 on 2026-10-22.
Output archived at `work/linux-port/probe_output.txt`.

| Letter | Role (inferred) | Key methods |
|---|---|---|
| a | AES cipher helper | a(String,String), b(String,String) |
| b | Policy (caching) | a(int), a(), a(int,long), a(int,l), a(int,String), b(), b(int), b(int,String), c(), c(int), c(long) |
| c | interface (policy/query) | a(String) -> int |
| d | interface ILicenseResultListener (IPC callback) | a(int, String, String) (abstract); nested `d$a` stub |
| e | LicenseChecker (entry point; binds to service) | a(f) checkLicense, onServiceConnected, onServiceDisconnected |
| f | LicenseCheckerCallback (app-facing) | a(int), b(int), c(int) |
| g | LicenseValidator (verifies RSA, calls f) | a() -> f, a(PublicKey,int,String,String) verify, b() -> int, c() -> String, d() (trigger), a(int,l), a(int) |
| h | helper | a(String) -> int |
| i | interface | a(String,String), b(String,String) |
| j | interface (callback to Policy) | a(int,l), c() -> boolean |
| k | storage/obfuscator helper | a(), a(String,String), b(String,String) |
| l | ResponseData (parsed licence response) | a(String) static, toString() |
| m | Exception (extends Exception) | — |

## Bypass strategy (probe-verified)

- Hook `g.a(PublicKey, int, String, String)` (verify) to skip RSA verification and call
  the callback `f.a(0)` (LICENSED). Never call the original.
- Hook `d$a.a(int, String, String)` (IPC callback) to force responseCode=0 and return
  mock signed data (defence in depth).
- Never call `this.<method>()` inside a hook (F10 guardrail); capture the original
  reference before replacing if needed.

## History

Earlier iterations (preserved in `work/linux-port/history/`) discovered these same
obfuscated names (`d$a`, `f`, `g`) and validated the callback-forcing approach.