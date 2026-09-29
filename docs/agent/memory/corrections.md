# Correções (erros do agente)

- **2026-09-29 · `git` na cópia Windows pela VM do Cowork deixa `.git/index.lock` órfão.** A pasta montada não permite
  apagar arquivos sem permissão explícita; o `git status` cria o lock e não consegue removê-lo, travando o git do usuário.
  Correção aplicada: pedi permissão de exclusão e removi o lock. **Regra**: não rodar git lá; quando inevitável, só com
  permissão de exclusão concedida, `-c core.autocrlf=true`, e conferir `ls .git/*.lock` no fim.
- **2026-09-29 · Clonei numa pasta vazia errada ("Central de Viagens 3.0").** O usuário indicou que o projeto é o repositório
  "Solicitações de eventos". Removi o `.git` parcial. **Regra**: confirmar a pasta/repo antes de escrever.
- **2026-09-29 · `pkill -f "<padrão>"` matou o próprio shell** porque a linha de comando continha o padrão. Use `pkill -f "[r]unserver …"`.
- **2026-09-29 · `playwright.clock.setFixedTime` quebra `performance.getEntriesByType("navigation")`.** Métricas de desempenho
  usam `asRole(role, { clock: false })`.
- **2026-09-29 · `JSON.stringify(obj, arrayDeChaves)` filtra também chaves aninhadas** — gerou baseline vazio. Use `sort` antes.
- **2026-09-29 · `git fetch` na cópia Windows disparou `gc --auto`** e deixou `.git/gc.log.lock` e `.git/gc.pid` órfãos (removidos).
  **Regra**: na pasta montada, sempre `git -c core.autocrlf=true -c gc.auto=0 -c maintenance.auto=false …` e conferir `ls .git/*.lock .git/gc.pid` no fim.
- **2026-09-29 · Entrega sem push**: a branch vai por `git bundle` → `git fetch <bundle> agent/x:agent/x` na cópia do usuário (só cria a ref; não toca índice nem arquivos).
