# T009 — Fase 1: Status Atual

## ✅ Concluído
- Infraestrutura do emulator pronta no Deck
- Assets extraídos (8.3 MB)
- Asset server implementado (asset_server.py)
- Frida-server disponível (108 MB)

## 🔄 Em andamento
- Testes de integração asset server + emulator
- Bypass do license check

## 🚫 Bloqueios
1. **License check** — Falha com "Cleartext traffic not permitted" (cleartext block at framework layer; iptables redirect alone cannot help)
2. **Frida client** — Available inside the container image (`runtime/android-emulator/Dockerfile` installs `frida-tools`); the Deck host itself has no pip/npm. Run frida from inside the container, not from the host.
3. **Portas** — 8080 in use by Steam on the Deck host; asset server default is 8080 (see `work/linux-port/CONFIG.md` for the canonical port)

## 🎯 Próximos Passos Imediatos
1. Iniciar asset server em porta alternativa (9999)
2. Verificar se jogo acessa o servidor
3. Se license check for hard block, tentar APK patch

## Comandos para testar manualmente no Deck:
```bash
# Iniciar asset server
cd /home/deck/cvgos-emulator
python3 asset_server.py 9999 assets/ &

# Verificar se está rodando
ss -tlnp | grep 9999

# Testar acesso
curl http://localhost:9999/globalgamemanagers

# Iniciar emulator (se necessário)
/opt/android-sdk/platform-tools/adb start-server
/opt/android-sdk/emulator/emulator -avd cvgos -gpu swiftshader_indirect -no-window -no-boot-anim &

# Aguardar boot e instalar jogo
sleep 60
/opt/android-sdk/platform-tools/adb install -r castlevania-grimoire-of-souls-1-1-4.apk

# Lanzar jogo
/opt/android-sdk/platform-tools/adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity

# Verificar logs
/opt/android-sdk/platform-tools/adb logcat -s Unity:V
```
