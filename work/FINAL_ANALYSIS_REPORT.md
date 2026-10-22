# Castlevania: Grimoire of Souls — Análise Completa

**Data:** 2026-10-20  
**Versão:** v1.1.4 (Android APK)  
**Engine:** Unity 2018.4.11f1 + Il2CPP (v24)  
**Arquitetura:** ARM64  
**Desenvolvedora:** Konami Digital Entertainment

---\n

## 1. Executiva

Jogo mobile de RPG gacha da Konami, baseado na série Castlevania. Compilado com Il2CPP (C# → ARM64), mas todo o sistema de tipos, nomes de métodos, campos e strings permanece no metadata `global-metadata.dat`.

### Métricas Principais
| Métrica | Valor |
|---------|-------|
| Types (classes/structs) | 19,843 |
| Methods | 206,344 |
| Fields | 140,794 |
| Strings | ~212,000 (4.17 MB) |
| Tabelas Unity | 350+ |
| Versão Metadata | 24 |

---\n

## 2. Estrutura do Binário

```
libil2cpp.so        100 MB   — Lógica do jogo (C# → ARM64)
libunity.so         15 MB    — Runtime Unity
libSPFXUnityPlugin  4.5 MB   — Plugin desconhecido
libFirebaseCppApp   3.8 MB   — Firebase
libFirebaseCppMsg   0.1 MB   — Firebase Cloud Messaging
libgpg.so           2.5 MB   — Google Play Games
classes.dex         3.0 MB   — Wrapper Java/Android
```

---\n

## 3. Sistemas Recuperados

### 3.1 Tabelas de Dados (350+ tabelas)

#### Personagens (18 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `charactertable` | Definições base dos personagens |
| `characterparametertable` | Stats base (HP, MP, ATK, DEF, MDEF, CRT, LCK) |
| `characterleveluptable` | Crescimento de stats por nível |
| `characterattacktable` | Dados de ataque |
| `characterattackreactiontable` | Frames de reação a ataques |
| `characterabilitytable` | Habilidades dos personagens |
| `characterabilityreleasetable` | Condições de unlock de habilidades |
| `charactergrouptable` | Agrupamentos de personagens |
| `characteravatartable` | Aparências/avatar |
| `charactercommonvoicetable` | Linhas de voz comuns |
| `characteruniqueparametertable` | Parâmetros únicos por personagem |
| `characterpotentialstatustable` | Efeitos de status potenciais |
| `resourcecharactertable` | IDs de recursos dos personagens |

#### Equipamentos (20 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `weapontable` | Stats das armas principais |
| `weaponleveltable` | Scaling de nível das armas |
| `subweapontable` | Stats de armas secundárias |
| `subweaponleveltable` | Scaling de nível sub-armas |
| `protectortable` | Stats de armaduras |
| `protectorleveltable` | Scaling de nível armaduras |
| `accessorytable` | Stats de acessórios |
| `equipboosttable` | Dados de boost de equipamento |
| `equipboostleveltable` | Scaling de boost |
| `equiplimitbreakcosttable` | Custos de limit break |
| `equipmainabilitytable` | Habilidades principais de equipamento |
| `equipadditionparametertable` | Parâmetros adicionais de equipamento |

#### Habilidades (15 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `abilitytable` | Definições de habilidades |
| `abilityleveltable` | Scaling por nível |
| `abilitygrouptable` | Agrupamentos de habilidades |
| `abilitytypetable` | Tipos de habilidades |
| `abilityoverlaptable` | Regras de sobreposição |
| `skilltable` | Definições de skills |
| `skillleveltable` | Scaling de skills |
| `skillbufftable` | Dados de buff de skill |
| `skillbuffsettable` | Conjuntos de buff |
| `skillicontable` | Referências de ícone de skill |
| `specialattacktable` | Dados de ataque especial |
| `specialattackleveltable` | Scaling de ataque especial |
| `foodabilitytable` | Efeitos de habilidade de comida |
| `foodcombinationtable` | Bônus de combinação de comida |

#### Inimigos (19 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `enemytable` | Definições de inimigos |
| `enemyaitable` | Comportamento AI |
| `enemyattackreactiontable` | Reações a ataques |
| `enemyguardtypetable` | Tipos de guarda |
| `enemypartstable` | Dados de partes do corpo |
| `enemypartsattacktable` | Ataques por parte |
| `enemyracetable` | Raças de inimigos |
| `enemycompensatetable` | Compensação de inimigos |
| `enemysettable` | Spawns de inimigos |
| `gimmicktable` | Gimmicks de campo |
| `gimmicksettable` | Conjuntos de gimmick |
| `statusailmenttable` | Dados de status ailment |

#### Modos de Jogo (34 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `mobatable` | Configurações do modo Moba |
| `mobacamptable` | Dados de camp do Moba |
| `raceactivetable` | Dados de corrida ativa |
| `race tier table` | Configurações de tier |
| `bossrushtable` | Configurações de Boss Rush |
| `cannonballchallengetable` | Desafio Cannonball |
| `challengetable` | Configurações de desafio |

#### Progressão (26 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `achievementtable` | Definições de conquistas |
| `achievementconditiontable` | Condições de conquistas |
| `loginbonustable` | Bônus de login |
| `comebackloginbonustable` | Bônus de retorno |
| `dailyboxtable` | Recompensas diárias |
| `treasureboxtable` | Dados de cofre |
| `rewardtable` | Definições de recompensas |
| `leaguetable` | Configurações de league |
| `leaguegradetable` | Dados de grade |

#### Gacha/Shop (10 tabelas)
| Tabela | Propósito |
|--------|-----------|
| `gachatable` | Configurações de gacha |
| `gachabannerlisttable` | Lista de banners |
| `gachapackagetable` | Pacotes de gacha |
| `gachararitygrouptable` | Grupos de raridade |
| `shopproducttable` | Produtos da shop |
| `exchangeproducttable` | Produtos de troca |

#### Itens/Materiais
| Tabela | Propósito |
|--------|-----------|
| `commonitemtable` | Itens comuns |
| `ingameitemtable` | Itens do jogo |
| `materialitemtable` | Itens de material |
| `fragmenttable` | Fragmentos de personagem |
| `soultable` | Itens de soul |
| `itemtypetable` | Tipos de item |

---\n

## 4. Sistema de Batalha

### Estados de AI (strings em japonês no binário)
```
WALK, JUMP, LAND, SLEEP_START, SLEEP_LOOP
ATTACK_01..ATTACK_05
GUARD, DAMAGE_01, DEATH
FOLLOW, CHASE (索敵), PATROL (地上徘徊)
AIR_ATTACK, AIR_MOVE
LAUNCH, KNOCKBACK
SPECIAL: FREEZE, STUN, POISON, SLEEP, PARALYSIS
```

### Status Effects
| Efeito | Japonês |
|--------|---------|
| Poison | 毒 |
| Curse | 呪 |
| Freeze | 凍 |
| Paralysis | 電 |
| Slow | 鈍 |
| Burn | 燃 |
| Stone | 石 |
| Pierce | ピ |

### Elementos
- 🔥 Fire (炎)
- ❄️ Ice (氷)
- 🌪️ Wind (風)
- ⚡ Thunder (雷)
- ✨ Holy (聖)
- 🌑 Dark (闇)

### Tipos de Dano
- Slash (斬)
- Strike (打)
- Magic (魔)

### Raças de Inimigos
- Material (物質)
- Flora/Fauna (動植物)
- Human/Demi-human (人・亜人)
- Demon (魔族)
- Undead (アンデッド)

---\n

## 5. Modos de Jogo

| Modo | Descrição |
|------|-----------|
| **Story Quest** | Campanha principal com capítulos |
| **Moba** | Arena 4v4 multiplayer |
| **Race** | Time attack racing |
| **Boss Rush** | Desafio contínuo de chefes |
| **Cannonball** | Modo desafio com regras específicas |
| **League** | Modo competitivo ranked |
| **Tutorial** | Sistema de onboarding |
| **Museum** | Modo coleção/exposição |
| **Bonus Quest** | Side quests com recompensas extras |

---\n

## 6. Network/Online

| Feature | Implementação |
|---------|---------------|
| **Photon PUN2** | Multiplayer real-time (Moba) |
| **Firebase** | Cloud messaging, analytics |
| **Google Play Games** | Achievements, leaderboards, saved games |
| **Nearby Connections** | Local multiplayer |
| **WebSocket** | `ws://160.13.90.143:3001/_sys` (endpoint dev) |
| **HTTP API** | `login_user_data_get.php` |

---\n

## 7. Scenes

| Scene | Propósito |
|-------|-----------|
| `title.unity` | Title screen |
| `home.unity` | Home hub |
| `battle.unity` | Battle arena |
| `copyright.unity` | Copyright screen |

---\n

## 8. Artifacts de Desenvolvimento

```
https://prjdjpdev1.microvision.co.jp/drc_server/Web/test.mp4
ws://160.13.90.143:3001/_sys
nodejs_client/data1234_DX11
```

---\n

## 9. Localização (MLStrings)

Tabelas de strings multi-idioma para:
- `mlstringadmintable_*` — Textos administrativos
- `mlstringdesctable_*` — Descrições
- `mlstringnametable_*` — Nomes
- `mlstringgifttable_*` — Gift texts

Idiomas suportados:
- ENG, JPN, KOR, CHS, CHO, FRA, GER, ITA, PRT, RUS, SPA, TUR

---\n

## 10. Status de Extração

| Componente | Estado |
|------------|--------|
| Class names | ✅ 100% |
| Method names | ✅ 100% |
| Field names | ✅ 100% |
| String literals | ✅ 212K strings |
| Table references | ✅ 350+ tabelas |
| Source code (logic) | ⚠️ Parcial (ARM64 disassembled) |
| Game assets (images/audio) | ⚠️ Precisa extração |

---\n

## 11. Arquivos Extraídos

```
extracted/lib/arm64-v8a/libil2cpp.so        (100 MB)
extracted/assets/bin/Data/globalgamemanagers (551 KB)
extracted/assets/bin/Data/Managed/Metadata/global-metadata.dat (24 MB)
work/full_metadata.json                      (24 MB)
work/table_catalog.json                      (catálogo de tabelas)
work/method_index.json                       (índice de métodos)
work/FINAL_ANALYSIS_REPORT.md                (este relatório)
```

---\n

## 12. Próximos Passos

1. **AssetStudio** — extrair texturas/modelos dos `.assets`
2. **Ghidra/radare2** — disassembly de `libil2cpp.so`
3. **Frida** — hooking de rede para capturar API requests
4. **Parse das tabelas** — extrair valores numéricos dos dados Unity
5. **Análise de save data** — format e criptografia local

---\n

## Legal Note

Análise para **fins educacionais/de pesquisa**. O código e assets são copyright da Konami. Este relatório não distribui código ou assets — apenas documenta o observado durante a análise.
