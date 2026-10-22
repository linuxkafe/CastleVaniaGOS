# T009 — Fase 1: Emulator Asset Patch
## Status: Implementação em andamento

### Resumo
Implementando workaround para rodar Castlevania: Grimoire of Souls no Steam Deck:
1. ✅ Emulador Android configurado (API 30 + SwiftShader)
2. ✅ Assets extraídos e prontos
3. ⏳ Asset server HTTP sendo testado
4. ❌ License check ainda bloqueia (requer Frida)

### Bloqueios Atuais
- Frida client não disponível no Deck (sem pip/npm, sem sudo)
- License check falha com "Cleartext traffic not permitted"

### Próximos Passos
1. Testar se asset server funciona (bypass da CDN morta)
2. Se funcionar, jogo roda mesmo com license check falhando
3. Documentar workaround como solução temporária

### Arquivos Criados
```
work/linux-port/
├── asset_server.py
├── run_phase1.sh
└── README.md

/home/deck/cvgos-emulator/
├── asset_server.py
├── run_phase1.sh
└── assets/ (8.3 MB de Unity assets)
```
