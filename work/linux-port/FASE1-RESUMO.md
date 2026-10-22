# T009 — Fase 1: Resumo Executado

## ✅ Concluído

### Infraestrutura
- **Imagem do emulator**: `localhost/cvgos-android-emu:latest` (5.46 GB)
  - API 30 Google APIs x86_64
  - SwiftShader para rendering
  - Frida-server incluído (16.2.1)
  - KVM acceleration habilitada

- **Assets extraídos**: 8.3 MB
  - `globalgamemanagers` (539 KB)
  - `sharedassets0.assets.split{0-3}` (4 MB)
  - `unity default resources` (3.5 MB)
  - `level0` (84 KB) — cena do título

### Scripts Criados
- `work/linux-port/asset_server.py` — HTTP server para assets
- `work/linux-port/run_phase1.sh` — Script de deploy
- `work/linux-port/IMPLEMENTACAO.md` — Documentação técnica

### Tickets AES
- `aes/tickets/T009-linux-port.md` — Ticket principal
- `aes/tickets/T009-plan.md` — Plano em 3 fases
- `aes/shadow/SD-T009-PHASE1.md` — Shadow doc da fase 1
- `aes/kanban.md` — Atualizado com T009 e sprint-03

## ❌ Bloqueios Identificados

| Bloqueio | Causa | Impacto | Mitigação |
|----------|-------|---------|-----------|
| License check falha | Cleartext blocked no Android 9+ | Jogo para na tela de license | Patch APK ou Frida hook |
| Frida não disponível | Sem pip/npm/sudo no Deck | Não é possível hook em runtime | Usar apktool para patch |
| Porta 8080 em uso | Steam webhelper | Conflito com asset server | Usar porta 8888 |

## 🎯 Próximos Passos (Recomendação)

### Opção C — Teste Rápido (5 min)
```bash
# No Deck:
cd /home/deck/cvgos-emulator
python3 asset_server.py 8888 assets/ &
/opt/android-sdk/platform-tools/adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity
# Verificar se jogo avança além do license check
```

### Opção A — APK Patch (30 min)
1. Instalar apktool no Deck
2. Descompilar APK: `apktool d castlevania-grimoire-of-souls-1-1-4.apk`
3. Remover/modificar chamada do LicenseChecker
4. Recompilar: `apktool b`
5. Assinar e instalar

### Opção B — Frida (requer instalação)
1. Instalar pip: `curl https://bootstrap.pypa.io/get-pip.py | python3`
2. Instalar frida: `python3 -m pip install frida --break-system-packages`
3. Hook no `LicenseChecker.checkLicense()`
4. Retornar 0 (LICENSE_OK)

## 📊 Métricas
- Tempo de build da imagem: ~7 minutos
- Tempo de boot do emulator: ~35 segundos
- Tamanho dos assets: 8.3 MB
- Tamanho do APK: 74 MB
- Tamanho da imagem Docker: 5.46 GB

## 🔗 Documentos Relacionados
- T005: Emulator deployment (bloqueios originais)
- SD-EMULATOR-001: Análise técnica do emulator
- SD-LINUX-001: Estratégia de port nativo
- FINAL_ANALYSIS_REPORT.md: Análise estática do APK
