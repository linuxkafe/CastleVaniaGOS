# Castlevania: Grimoire of Souls — Reverse Engineering Analysis Report

**APK:** `castlevania-grimoire-of-souls-1-1-4.apk` (v1.1.4)
**DMG:** `Castlevania_Grimoire_of_Souls_v1_4_2.dmg` (v1.4.2 macOS)
**Date:** 2026-10-20
**Engine:** Unity 2018.4.11f1 with Il2CPP (version 24)
**Architecture:** ARM64 (also ARMv7 for Android, x86_64 for macOS)
**Developer:** Konami Digital Entertainment

---\n

## Executive Summary

This is a **mobile gacha RPG** developed by Konami, running on Unity with IL2CPP compilation. The game's C# code has been compiled to native ARM64 machine code, but the full type system, method names, field names, and string data remain intact in the metadata blob (`global-metadata.dat`). The game logic, balance tables, quest data, character stats, and ability systems are all recoverable.

### Key Stats
| Metric | Value |
|--------|-------|
| Total Types (classes/structs) | 19,843 |
| Total Methods | 206,344 |
| Total Fields | 140,794 |
| String Table Size | 4.17 MB (~212,000 strings) |
| Game-related types | ~6,700+ |
| Unity Tables Found | 350+ |
| Metadata Version | 24 |

---\n

## Architecture

### Binary Structure (Android APK)
```
libil2cpp.so        100 MB   — Main game logic (C# → ARM64 native)
libunity.so         15 MB    — Unity engine runtime
libSPFXUnityPlugin.so 4.5MB  — Unknown plugin (possibly anti-cheat or analytics)
libFirebaseCppApp-6.0.0.so   ~4 MB — Firebase services
libFirebaseCppMessaging.so   ~100 KB — Firebase Cloud Messaging
libgpg.so              2.5MB — Google Play Games
classes.dex            3 MB  — Android Java wrapper layer
```

### Binary Structure (macOS DMG - Partial)
```
Castlevania: Grimoire of Souls.app/
├── Contents/MacOS/           — Game binary (Mach-O, not extracted)
├── Contents/Frameworks/      — Unity frameworks
├── Contents/Resources/       — Game data
│   └── Data/
│       ├── globalgamemanagers
│       ├── sharedassets0.assets
│       └── Managed/Metadata/global-metadata.dat
```

### Game Layers
1. **Android/Java Layer** (`classes.dex`) — Entry points, lifecycle, native binding
2. **Il2CPP/Native Layer** (`libil2cpp.so`) — All game logic as ARM64 machine code
3. **Unity Engine Layer** (`libunity.so`) — Rendering, audio, input, physics
4. **Metadata Layer** (`global-metadata.dat`) — Full C# type system preserved
5. **Asset Layer** (`sharedassets0.assets`, `globalgamemanagers`) — Unity serialized objects

---\n

## Recovered Game Systems

### 1. Balance/Data Tables (350+ tables found)

#### Character System
| Table | Purpose |
|-------|---------|
| `charactertable` | Base character definitions |
| `characterparametertable` | Character stats (HP, MP, ATK, DEF, MDEF, CRT, LCK) |
| `characterleveluptable` | Stat growth per level |
| `characterattacktable` | Attack data |
| `characterattackreactiontable` | Attack reaction frames |
| `characterabilitytable` | Character abilities |
| `characterabilityreleasetable` | Ability unlock conditions |
| `charactergrouptable` | Character groupings |
| `characteravatartable` | Avatar appearances |
| `charactercommonvoicetable` | Common voice lines |
| `characteruniqueparametertable` | Unique character parameters |
| `characterpotentialstatustable` | Potential status effects |
| `resourcecharactertable` | Character resource IDs |

#### Equipment System
| Table | Purpose |
|-------|---------|
| `weapontable` | Main weapon stats |
| `weaponleveltable` | Weapon level scaling |
| `subweapontable` | Sub-weapon stats |
| `subweaponleveltable` | Sub-weapon level scaling |
| `protectortable` | Armor/protector stats |
| `protectorleveltable` | Armor level scaling |
| `accessorytable` | Accessory stats |
| `equipboosttable` | Equipment boost data |
| `equipboostleveltable` | Equipment boost scaling |
| `equiplimitbreakcosttable` | Limit break costs |
| `equipmainabilitytable` | Main equipment abilities |
| `equipadditionparametertable` | Additional equip parameters |

#### Ability/Skill System
| Table | Purpose |
|-------|---------|
| `abilitytable` | Ability definitions |
| `abilityleveltable` | Ability level scaling |
| `abilitygrouptable` | Ability groups |
| `abilitytypetable` | Ability types |
| `abilityoverlaptable` | Ability overlap rules |
| `skilltable` | Skill definitions |
| `skillleveltable` | Skill level scaling |
| `skillbufftable` | Skill buff data |
| `skillbuffsettable` | Skill buff sets |
| `skillicontable` | Skill icon references |
| `specialattacktable` | Special attack data |
| `specialattackleveltable` | Special attack scaling |
| `foodabilitytable` | Food ability effects |
| `foodcombinationtable` | Food combination bonuses |

#### Quest System
| Table | Purpose |
|-------|---------|
| `questtable` | Quest definitions |
| `questenemytable` | Quest enemy lists |
| `questeventtable` | Quest events |
| `questgrouptable` | Quest groups |
| `questdifficultytable` | Difficulty settings |
| `questrewardtable` | Quest rewards |
| `questcampaigntable` | Campaign quests |
| `questbossrushtable` | Boss rush quests |
| `challengequesttable` | Challenge quests |
| `questmobatable` | Moba quest data |
| `questmobascenegrouptable` | Moba scene groups |

#### Battle System
| Table | Purpose |
|-------|---------|
| `enemytable` | Enemy definitions |
| `enemyaitable` | Enemy AI behavior |
| `enemyattackreactiontable` | Enemy attack reactions |
| `enemyguardtypetable` | Enemy guard types |
| `enemypartstable` | Enemy part data |
| `enemypartsattacktable` | Enemy part attacks |
| `enemyracetable` | Enemy race types |
| `enemycompensatetable` | Enemy compensation |
| `enemysettable` | Enemy spawn sets |
| `gimmicktable` | Field gimmicks |
| `gimmicksettable` | Gimmick sets |
| `statusailmenttable` | Status ailment data |

#### Game Modes
| Table | Purpose |
|-------|---------|
| `mobatable` | Moba mode settings |
| `mobacamptable` | Moba camp data |
| `raceactivetable` | Active race data |
| `race tier table` | Race tier settings |
| `race season info table` | Season information |
| `bossrushtable` | Boss rush settings |
| `cannonballchallengetable` | Cannonball challenge |
| `challengetable` | Challenge settings |

#### Progression & Rewards
| Table | Purpose |
|-------|---------|
| `achievementtable` | Achievement definitions |
| `achievementconditiontable` | Achievement conditions |
| `loginbonustable` | Login bonus data |
| `comebackloginbonustable` | Comeback login bonuses |
| `dailyboxtable` | Daily box rewards |
| `treasureboxtable` | Treasure box data |
| `rewardtable` | Reward definitions |
| `leaguetable` | League settings |
| `leaguegradetable` | League grade data |

#### Gacha & Shop
| Table | Purpose |
|-------|---------|
| `gachatable` | Gacha settings |
| `gachabannerlisttable` | Gacha banner list |
| `gachapackagetable` | Gacha packages |
| `gachararitygrouptable` | Rarity groups |
| `shopproducttable` | Shop products |
| `exchangeproducttable` | Exchange products |

#### Items & Materials
| Table | Purpose |
|-------|---------|
| `commonitemtable` | Common items |
| `ingameitemtable` | In-game items |
| `materialitemtable` | Material items |
| `fragmenttable` | Character fragments |
| `soultable` | Soul items |
| `itemtypetable` | Item types |

#### Multiplayer & Social
| Table | Purpose |
|-------|---------|
| `friendrewardtable` | Friend rewards |
| `gifttable` | Gift data |
| `chatstamp table` | Chat stamps |
| `chatchanneltable` | Chat channels |

#### UI & Localization
| Table | Purpose |
|-------|---------|
| `stringtable` | Base strings |
| `mlstringnametable_*` | Character names (multi-lang) |
| `mlstringdesctable_*` | Descriptions (multi-lang) |
| `flavortexttable` | Flavor text |
| `tipstable` | Tips |
| `helptable` | Help content |
| `dialogdatatable` | Dialog data |

#### Audio & Visual
| Table | Purpose |
|-------|---------|
| `soundtable` | Sound effects |
| `soundbgmtable` | BGM tracks |
| `soundvoicetable` | Voice lines |
| `movietable` | Movie references |
| `moviesubtitlestable` | Movie subtitles |

---\n

### 2. Game Modes

| Mode | Description |
|------|-------------|
| **Story Quest** | Main campaign with chapters and levels |
| **Moba** | 4v4 multiplayer battle arena |
| **Race** | Time attack racing mode |
| **Boss Rush** | Continuous boss fight challenge |
| **Cannonball** | Challenge mode with specific rules |
| **League** | Ranked competitive mode |
| **Tutorial** | Onboarding system |
| **Museum** | Collection/exhibition mode |
| **Bonus Quest** | Side quests with extra rewards |

---\n

### 3. Battle AI States

From Japanese strings in the binary:
```
WALK, JUMP, LAND, SLEEP_START, SLEEP_LOOP
ATTACK_01 through ATTACK_05
GUARD, DAMAGE_01, DEATH
FOLLOW, CHASE (索敵), PATROL (地上徘徊)
AIR_ATTACK, AIR_MOVE
LAUNCH, KNOCKBACK
SPECIAL: FREEZE, STUN, POISON, SLEEP, PARALYSIS
```

---\n

### 4. Status Effects

| Effect | Japanese |
|--------|----------|
| Poison | 毒 |
| Curse | 呪 |
| Freeze | 凍 |
| Paralysis | 電 |
| Slow | 鈍 |
| Burn | 燃 |
| Stone | 石 |
| Pierce | ピ |

---\n

### 5. Elemental Attributes

Fire (炎), Ice (氷), Wind (風), Thunder (雷), Holy (聖), Dark (闇)

---\n

### 6. Damage Types

Slash (斬), Strike (打), Magic (魔)

---\n

### 7. Enemy Types

Material (物質), Flora/Fauna (動植物), Human/Demi-human (人・亜人), Demon (魔族), Undead (アンデッド)

---\n

## Network/Online Features

| Feature | Implementation |
|---------|---------------|
| **Photon PUN2** | Real-time multiplayer (Moba mode) |
| **Firebase** | Cloud messaging, analytics |
| **Google Play Games** | Achievements, leaderboards, saved games |
| **Nearby Connections** | Local multiplayer |
| **WebSocket** | `ws://160.13.90.143:3001/_sys` (dev endpoint) |
| **HTTP API** | `login_user_data_get.php` |

---\n

## Scenes

| Scene | Purpose |
|-------|---------|
| `title.unity` | Title screen |
| `home.unity` | Home hub |
| `battle.unity` | Battle arena |
| `copyright.unity` | Copyright screen |

---\n

## Development Artifacts Found

```
https://prjdjpdev1.microvision.co.jp/drc_server/Web/test.mp4
ws://160.13.90.143:3001/_sys
nodejs_client/data1234_DX11
```

---\n

## DMG (macOS) Analysis Status

| Component | Status |
|-----------|--------|
| Format Detection | ✅ Identified as macOS DMG (zlib compressed UDIF) |
| Decompression | ⚠️ Partial — 183.5 MB decompressed from 2.6 GB |
| Info.plist | ✅ Found — reveals Unity version 2020.3.30f1 |
| Game Binary | ❌ Not extracted (compressed/nested) |
| Asset Data | ⚠️ Partial (HFS+ filesystem detected) |

**Note:** The DMG contains a macOS version of the game (v1.4.2). The zlib compression is multi-stream and requires specialized handling for full extraction. The APK analysis provides more complete coverage.

---\n

## Recovery Status

| Component | Recovered? | Quality |
|-----------|-----------|---------|
| Class names | ✅ 100% | Full |
| Method names | ✅ 100% | Full |
| Field names | ✅ 100% | Full |
| String literals | ✅ 100% | Full (212K strings) |
| Table references | ✅ 350+ tables | Complete list |
| Source code (logic) | ⚠️ Partial | Disassembled ARM64 |
| Game assets (images/audio) | ⚠️ Needs extraction | Unity asset format |
| DMG macOS binary | ❌ Blocked | Compression issue |

---\n

## Extracted Files

All extracted data saved to:
- `work/metadata_summary.json` — Full type/method/field metadata (189 MB)
- `work/ANALYSIS_REPORT.md` — This report
- `extracted/lib/arm64-v8a/libil2cpp.so` — Main binary (100 MB)
- `extracted/assets/bin/Data/Managed/Metadata/global-metadata.dat` — Metadata (24 MB)
- `extracted/assets/bin/Data/globalgamemanagers` — Unity scene data (551 KB)
- `extracted/assets/bin/Data/sharedassets0.assets.split[0-3]` — Game assets (3.8 MB)
- `dmg_work/manifest.plist` — DMG file manifest (partial)

---\n

## Next Steps for Deeper Analysis

1. **Unity Asset Extraction** — Use `AssetStudio` to extract textures, models, animations
2. **ARM64 Disassembly** — Use `ghidra` or `radare2` on `libil2cpp.so` for logic analysis
3. **Table Data Parsing** — Parse the actual numeric values from Unity assets
4. **Network Protocol** — Hook the WebSocket/HTTP layer to capture game server API
5. **Save Data Format** — Analyze local storage encryption/format
6. **DMG Full Extraction** — Use `hdiutil` or custom DMG parser for complete macOS extraction

---\n

## Legal Note

This analysis is for **educational/research purposes only**. The game code and assets are copyrighted by Konami. This report does not distribute any game code or assets — it only documents what was observed during analysis.
