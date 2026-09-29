# Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `browser_open_page` cai no login | sessão salva de um banco recriado | já é refeita automaticamente; se persistir, `lab_reset` |
| `Executable doesn't exist … chromium` no MCP | cliente MCP não repassou `PLAYWRIGHT_BROWSERS_PATH` | cliente deve repassar o ambiente (ver `tools/project-mcp/test/client.ts`); ou `npx playwright install chromium` |
| Visual falha "em tudo" depois de um reset | seed fora do relógio ancorado (corrigido: o seed se ancora sozinho) ou dados acumulados | `npm run agent:doctor` (checa volume do cenário) → `--fix` |
| `agent_reset` recusado | banco não é LAB | correto: só o banco do laboratório pode ser recriado; use `lab.py reset` |
| Mudança em Python não aparece no lab | `runserver --noreload` | reinicie (`pkill -f "[r]unserver 127.0.0.1:8031"`) ou `serve --reload` |
| `git` trava na cópia Windows | `index.lock`/`gc.pid` órfãos da VM | ver `memory/corrections.md` |
| Plugin instalado mas sem ferramentas MCP | MCP remoto de plugin não sobe na sessão Cowork na nuvem | conecte o conector no claude.ai ou use o substituto (`manual-connections.md`) |
| `makemigrations` acusa mudança falsa com relógio ancorado | (corrigido) o relógio troca `__code__` e preserva a identidade de `timezone.now` | — |
