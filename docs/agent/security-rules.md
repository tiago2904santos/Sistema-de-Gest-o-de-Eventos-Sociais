# Regras de segurança do agente

- Nunca ler, exibir, copiar, commitar ou enviar `.env`, tokens, senhas, chaves ou dumps. O lab funciona sem `.env`.
- `.claude/settings.json` nega leitura/edição de `.env` para o Claude Code.
- Credenciais do laboratório (`Lab@2026!seguro`) são fictícias e só existem no banco do lab — nunca reutilizar em outro lugar.
- Integrações reais (eProtocolo, WhatsApp, e-mail, ORS, Anthropic, banco legado) ficam desligadas no lab; ativar só com pedido explícito.
- Comandos destrutivos (`agent_reset`) recusam banco sem marcador de descarte e recusam DEBUG desligado.
- Não instalar pacote de origem desconhecida; dependência nova entra fixada e registrada em `tooling-inventory.md`.
- Plugins/MCP só de fonte oficial ou parceira revisada; revisar permissões antes.
- Ferramentas externas recebem só o necessário (ex.: Playwright MCP navega no lab, com dados sintéticos).
- Manter rollback possível: branch + commits pequenos; nunca `push --force` em `main`.
- Relatórios não podem conter dados pessoais reais: o lab só tem dados sintéticos; se auditar o banco real, relatório fica fora do git.
