# Lições de ferramental

- **O SDK MCP repassa ambiente mínimo ao servidor stdio** — sem `PLAYWRIGHT_BROWSERS_PATH` o Chromium "não existe". Clientes de teste devem repassar `process.env` (Claude Code repassa).
- **Reporter com cor quebra parsing** — `run()` do MCP remove ANSI e força `NO_COLOR`/`DJANGO_COLORS=nocolor`.
- **"0 testes" não é sucesso** — `runPlaywright` exige `expected > 0` e nenhum erro global (globalSetup quebrado passava como ok).
- **Substituição de texto silenciosa** — dois ajustes (filtro de módulos do seed e caminho do SQLite no reset) não aplicaram/erraram sem aviso; os testes do lab e o check de volume do doctor pegaram. Regra: todo patch automático com `assert old in s`, e todo comando destrutivo com teste do efeito.
- **Sessão salva vence banco novo** — após `lab_reset`, `.lab/auth/*.json` aponta para usuários de outro banco; o MCP confere e refaz o login.
- **Identidade de função importa para o Django** — trocar `timezone.now` por outra função gera migrações falsas; trocar o `__code__` preserva a identidade.
- **Plugins só-MCP não sobem no Cowork na nuvem** — conferir com `RefreshMcpTools` antes de declarar capacidade.
