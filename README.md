# Castlevania: Grimoire of Souls — Native Linux Port & Reverse Engineering

> **Status:** Licence bypass closed (F1/F2); game runs on Linux (via Android emulator on Steam
> Deck) but is stuck in a busy-wait on the Unity main thread (100% CPU, black screen).
> Title screen not yet reached. See §7 for open blockers.

---

## Abstract

This repository documents the reverse engineering and attempted native Linux port of
*Castlevania: Grimoire of Souls* v1.1.4 (Android, Unity 2018.4.11f1, IL2CPP, ARM64-only).
The game is a dead live-service title whose asset CDN and Google Play licence server are
offline. Two parallel tracks are pursued:

1. **Track A (short-term):** Run the Android APK on a Steam Deck via an x86_64 Android
   emulator (podman/KVM) with the ARM native bridge (`libndk_translation`), bypassing
   the Google Play licence check and serving extracted assets locally.
2. **Track B (long-term):** Native Linux x86_64 build loading the extracted Unity assets
   directly (not started; T009 AC-01..AC-05 all unmet).

The licence bypass was the major blocker identified by a peer review (BLOCKER F1). It has
been closed by re-designing the Frida hooks around obfuscated class names discovered by
a probing technique. The game now initialises Unity (EGL/GLES 3.1) without crash, but
is stuck in a busy-wait on the Unity main thread (100% CPU, black screen) — root cause
unidentified.

---

## 1. Methodology

### 1.1 Reverse engineering (T001–T008)

- **Il2CPP metadata extraction:** Derived struct strides from `global-metadata.dat`
  (24,622,684 B, sanity `0xFAB11BAF`, version 24) rather than hardcoding them.
  Bootstrap invariants validate the derived layout.
- **String extraction:** 213,293 heap tokens + 19,297 literals.
- **Table catalog:** Full categorisation of metadata tables.
- **Reproducible pipeline:** Makefile, scripts, SHA-256 manifest. Every number in the
  reports is quotable from a command. `make -C work verify` regenerates artifacts
  byte-identically.

### 1.2 Peer review (round 1)

A multi-perspective review (4 personas: Cínico, Purista, Pragmático, Utilizador) produced
**5 BLOCKER, 4 MAJOR, 7 MINOR** findings. The root cause of all metadata miscounts was a
single bug class: hardcoded Il2CPP struct strides (SD-META-001, SD-CI-001). Round 2
(T008) corrected the review's own errors (rubric hash placeholder, F-002, F-013, F-014).

### 1.3 Emulator deployment (T009, T010, T011)

- **Container:** Ubuntu 24.04 + Android SDK (API 30, google_apis, x86_64) + emulator +
  frida-tools + frida-server 16.2.1. Built with podman (no Docker). GPU mode: host
  (Mesa/DRI passthrough via `/dev/dri`), with Xvfb virtual display.
- **ARM bridge:** `libndk_translation` runs the ARM64-only Unity/IL2CPP binary on x86_64
  under KVM acceleration.
- **Licence bypass:** Google LVL (License Verification Library) client is ProGuard-obfuscated
  into `com.google.android.vending.licensing.a`..`m`. The bypass hooks `e.onServiceConnected`
  (LicenseChecker), iterates the pending queue (`j` = LinkedList of LicenseValidator `g`),
  calls `g.a().a(0)` (deliver LICENSED), and skips the original (which would make the
  cleartext HTTP request to `android.clients.google.com`).
- **Asset delivery:** Unity assets are extracted from the APK (`extracted/assets/bin/Data/`,
  ~8 MB). An asset server (`asset_server.py`) serves them locally. Not yet wired to the game.

### 1.4 AES rigor

This project follows the Ambrósio Engineering System (AES): ticket → plan → build → verify →
review → learn. Peer reviews use pre-registered rubrics with SHA-256 hashes. Findings become
tickets. Decision records (D001–D004) are machine-readable. Shadow docs (SD-*) feed the hot
index.

---

## 2. Key findings

### 2.1 Licence bypass (T010 — CLOSED)

The original bypass scripts (`bypass_license.js`, `bypass_all.js`, etc.) hooked classes that
do **not** exist in the game's DEX:
`com.android.vending.licensing.LicenseChecker`, `com.google.android.vending.licensing.LicenseChecker`,
`com.android.vending.billing.IabHelper`, `com.android.vending.licensing.Security`,
`jp.konami.android.common.iab.KonamiIabHelper`, `android.security.net.config.NetworkSecurityPolicy`,
`okhttp3.OkHttpClient` — all 0 occurrences in `extracted/classes.dex`.

The licensing client is present only under obfuscated names (`com.google.android.vending.licensing.a`..`m`).

**Probe technique:** iterate `Java.use("com.google.android.vending.licensing." + letter)` for
a..z in a Frida script (try/catch for absent classes). This enumerated all 13 classes with
their methods and fields in one run. `Java.enumerateLoadedClasses()` crashes Frida and is
unusable.

**Bypass:** hook `e.onServiceConnected` (LicenseChecker), iterate the pending queue
(`j` = LinkedList of LicenseValidator `g`), call `g.a().a(0)` (deliver LICENSED to app
callback), skip the original. Also hook `g.a(PublicKey,...)` (verify) and `e$a.a(int,String,String)`
(IPC callback) as defence in depth.

**Evidence:** logcat shows "LicenseChecker: Binding to licensing service." then no
"Error contacting licensing server." The game proceeds past the licence check.

### 2.2 Busy-wait (T011 — BLOCKED)

The game initialises Unity (EGL/GLES 3.1, context created) but the Unity main thread
spins at 100% CPU in `libndk_translation.so` (ARM interpreter, single opaque frame).
No title screen renders (screenshot 100% black). No network requests beyond licence check.
The game is unresponsive to input.

Root cause is **not identifiable** with available tooling (no guest symbol map, no root
for thread dumps). Three hypotheses remain unverified:
1. Skipped `UnityDownloaderActivity` leaves an undelivered state.
2. Missing `SPFXConfig.asset` triggers a retry loop.
3. Incomplete licence callback (game waits for a second state).

### 2.3 Peer review findings (round 1)

- **F1 (BLOCKER, CLOSED):** Frida hooks target classes absent from the game DEX.
- **F2 (MAJOR, CLOSED):** Frida hooks target methods that do not exist.
- **F3 (MAJOR, CORRECTED):** Shadow doc claimed "verified: 335 bytes" for globalgamemanagers
  (actual 551,616 bytes).
- **F4 (MAJOR, CORRECTED):** Port numbers (8080/8888/9999), GPU modes (host vs swiftshader),
  asset sizes inconsistent across artifacts.
- **F5 (MAJOR, CORRECTED):** Deploy scripts used host-specific absolute paths.
- **F6 (MAJOR, CORRECTED):** Asset server redirect pointed at port 80, server listens elsewhere.
- **F7 (MAJOR, CORRECTED):** Ticket ACs for native binary but work is emulator patching.
- **F8 (MAJOR, CORRECTED):** Status docs contained stale/unearned claims.
- **F9 (MAJOR, CORRECTED):** Mock servers bound to 0.0.0.0 without auth.
- **F10 (MAJOR, CORRECTED):** `bypass_iab.js` `onStart` hook caused infinite recursion.

---

## 3. Repository structure

```
CastleVaniaGOS/
├── aes/                    # AES project management (kanban, tickets, shadow docs, decisions)
│   ├── decisions/          # D001-D004 machine-readable decision records
│   ├── peer-reviews/       # Round-1 review (rubric, findings, synthesis, validate.sh)
│   ├── shadow/             # SD-* shadow docs (insights + review findings)
│   └── tickets/            # T001-T011 tickets and plans
├── extracted/              # Extracted APK contents (classes.dex, assets/, lib/, Managed/)
├── lib/                    # Native libraries
├── runtime/                # Android emulator container (Dockerfile, entrypoint.sh)
├── scripts/                # Extraction and pipeline scripts
├── tests/                  # Unit tests
├── work/
│   ├── linux-port/         # All bypass/deploy/probe scripts
│   │   ├── bypass_license_v5.js    # Working licence bypass (probe-verified)
│   │   ├── bypass_all_v3.js        # Licence + UnityDownloaderActivity skip
│   │   ├── probe_licensing.js      # Class/method probe (a..z)
│   │   ├── probe_output.txt        # Probe results (13 classes mapped)
│   │   ├── LICENSE_OBFUSCATION_MAP.md
│   │   ├── CONFIG.md               # Single source of truth (ports, GPU, sizes)
│   │   ├── asset_server.py         # Local asset HTTP server
│   │   ├── mock_license_server.py  # Mock licence server
│   │   ├── history/                # Earlier bypass iterations
│   │   └── diag_*.js, probe_*.js  # Diagnostics
│   ├── ANALYSIS_REPORT.md
│   └── FINAL_ANALYSIS_REPORT.md
├── _legacy_dirs/           # Consolidated from scattered project dirs
├── castlevania-grimoire-of-souls-1-1-4.apk  # NOT in git (excluded)
└── README.md
```

---

## 4. How to reproduce

### Build the emulator container

```bash
cd runtime/android-emulator
podman build -t localhost/cvgos-android-emu:gpu-host .
```

### Run the emulator (on the Deck)

```bash
podman run --rm --device /dev/kvm --device /dev/dri:/dev/dri \
  -p 5554:5554 -v /path/to/apk:/apks \
  localhost/cvgos-android-emu:gpu-host
```

### Run the licence bypass

```bash
# Inside the container:
frida -U -f jp.konami.castlevania -l work/linux-port/bypass_license_v5.js --runtime=v8
```

### Verify

```bash
adb logcat -d | grep -iE "LicenseChecker|Error contacting|crash|SIGSEGV"
# Expected: "LicenseChecker: Binding to licensing service." with no "Error contacting licensing server."
```

---

## 5. Open issues

| ID | Title | Status |
|----|-------|--------|
| T009 | Native Linux port (IL2CPP standalone) | Not started (0/5 ACs) |
| T010 | Licence bypass completion | Done (AC-03 partial — game runs but busy-waits) |
| T011 | Asset delivery / rendering | Blocked (100% CPU, black screen) |

---

## 6. Decision records

| ID | Verdict | Question |
|----|---------|----------|
| D001 | SUPORTADA | Why is the game stuck in a busy-wait? (UnityMain spinning in libndk_translation) |
| D002 | NÃO-VERIFICÁVEL | Root cause (3 candidates, none verified) |
| D003 | SUPORTADA | Cheapest experiments (A: 30 min, B: 1-2h, C: 2-4h, D: 4-8h) |
| D004 | NÃO-VERIFICÁVEL | Pivot to native build? (Recommendation: no, run A first) |

---

## 7. Limitations and honest assessment

- **The game does not reach the title screen.** It runs Unity but is stuck in a busy-wait
  (100% CPU) with a black screen. The root cause is unidentified.
- **The licence bypass is not a general solution.** It works for this specific APK build
  (obfuscated class names are version-specific). A different build would need re-probing.
- **No independent review.** The peer review was conducted by the same agent that authored
  the work (routed personas, not independent reviewers). Findings are INFERRIDOS until a
  human executes the validation script.
- **The native Linux port (T009) is unstarted.** Feasibility is unverified.
- **AES rigor was applied throughout:** pre-registered rubrics, SHA-256 hashes, decision
  records, shadow docs, and a machine-readable verdict system.

---

## 8. References

- AES (Ambrósio Engineering System): `/opt/aes`
- Peer review protocol: `/opt/aes/docs/PEER_REVIEW.md`
- Multi-perspective review: `/opt/aes/docs/review/MULTI_PERSPECTIVE_REVIEW.md`
- T010 learn: `aes/tickets/T010-learn.md`
- T010 plan: `aes/tickets/T010-plan.md`
- Obfuscation map: `work/linux-port/LICENSE_OBFUSCATION_MAP.md`
- Probe output: `work/linux-port/probe_output.txt`
- Decision records: `aes/decisions/D001.md`–`D004.md`