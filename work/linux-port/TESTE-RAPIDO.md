# T009 — Teste Rápido Fase 1
## Objetivo: Verificar se o jogo avança mesmo com license check falhando

## Comandos para executar no Deck:

# 1. Iniciar asset server
cd /home/deck/cvgos-emulator
python3 asset_server.py 8888 assets/ &

# 2. Iniciar emulator (se não estiver rodando)
/opt/android-sdk/platform-tools/adb start-server
/opt/android-sdk/emulator/emulator -avd cvgos -gpu swiftshader_indirect -no-window -no-boot-anim -no-snapshot -netdelay none -netspeed full -no-audio &

# 3. Aguardar boot (~60s)
sleep 60

# 4. Instalar jogo
/opt/android-sdk/platform-tools/adb install -r -d -g /home/deck/cvgos-emulator/castlevania-grimoire-of-souls-1-1-4.apk

# 5. Lanzar jogo
/opt/android-sdk/platform-tools/adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity

# 6. Verificar logs
/opt/android-sdk/platform-tools/adb logcat -c
sleep 10
/opt/android-sdk/platform-tools/adb logcat -s Unity:V AndroidRuntime:E | head -50

## O que observar:
# - Se o jogo mostrar "License check failed" mas continuar → ✅ ASSET SERVER FUNCIONANDO
# - Se o jogo fechar → ❌ License check é bloqueio hard
# - Se aparecer erro de assets → ❌ Asset server não está sendo acessado

## Diagnóstico:
# Verificar se asset server recebeu requests:
ss -tnp | grep :8888

# Verificar logs do asset server:
cat /tmp/asset_server.log
