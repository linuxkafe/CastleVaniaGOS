# T009 — Fase 1: Emulator Asset Patch — Implementação

## O que foi feito

### 1. Asset Server HTTP
Criado `asset_server.py` que serve os Unity assets via HTTP:
- `globalgamemanagers` (539 KB)
- `sharedassets0.assets.split{0-3}` (~4 MB)
- `unity default resources` (3.5 MB)
- `level0` (84 KB) — cena do título

### 2. Scripts de Deploy
Criado `run_phase1.sh` que orquestra:
1. Inicia asset server na porta 8888
2. Inicia emulator Android via podman
3. Instala APK
4. Lança jogo
5. Coleta logcat

### 3. Infraestrutura no Deck
- Assets copiados: `/home/deck/cvgos-emulator/assets/`
- Frida-server disponível: `/home/deck/cvgos-emulator/frida-server` (108 MB)
- Imagem do emulator: `localhost/cvgos-android-emu:latest`

## Bloqueios Atuais

### Bloqueio 1: Porta 8080 em uso
A porta 8080 está sendo usada pelo `steamwebhelper`. Solução: usar porta 8888.

### Bloqueio 2: License Check
O jogo falha no license check do Google Play:
```
LicenseValidator: Error contacting licensing server.
Cleartext traffic not permitted: http://android.clients.google.com
```

**Soluções possíveis:**
1. **Frida hook** — Não disponível (sem pip/npm no Deck, sem sudo)
2. **APK patch** — Descompilar APK, remover license check, recompilar
3. **Ignorar falha** — Testar se o jogo continua mesmo com license check falhando

### Bloqueio 3: Tempo de teste
Os testes estão levando > 5 minutos por execução (boot + install + launch).

## Próximos Passos Recomendados

### Opção A: Patch no APK (Recomendado)
1. Usar `apktool` para descompilar o APK
2. Remover/modificar a chamada do license check
3. Recompilar e assinar o APK
4. Instalar versão patchada

**Vantagens:**
- Resolve o problema permanentemente
- Não requer Frida
- Funciona em qualquer dispositivo

**Desvantagens:**
- Requer apktool (não instalado)
- Pode quebrar se o jogo verificar integridade

### Opção B: Bypass via Frida (Se possível)
1. Instalar Frida client no Deck
2. Hook no `LicenseChecker.checkLicense()`
3. Retornar `LICENSE_OK` (0)

**Vantagens:**
- Não modifica o APK
- Pode ser desfeito facilmente

**Desvantagens:**
- Frida não disponível no Deck
- Requer instalação de dependências

### Opção C: Testar sem bypass (Mais rápido)
1. Executar o jogo normalmente
2. Verificar se ele continua após o license check falhar
3. Se sim, o asset server resolve o problema principal

**Vantagens:**
- Teste rápido (5 min)
- Sem necessidade de tools adicionais

**Desvantagens:**
- Pode não funcionar se o jogo fechar ao falhar license

## Recomendação AES

**Opção C primeiro** — Testar se o jogo continua após falha do license check.
Se não continuar, partir para **Opção A** (APK patch).

## Próximos Comandos

```bash
# No Deck:
cd /home/deck/cvgos-emulator

# Testar sem Frida (apenas asset server)
python3 asset_server.py 8888 assets/ &
# Em outro terminal:
/opt/android-sdk/platform-tools/adb shell am start -n jp.konami.castlevania/jp.konami.android.common.iab.KonamiIabUnityPlayerActivity

# Verificar se o jogo avança além do license check
/opt/android-sdk/platform-tools/adb logcat -s Unity:V AndroidRuntime:E
```
