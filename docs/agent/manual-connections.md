# Conexões manuais necessárias

Nada aqui bloqueia o laboratório: cada item tem substituto em uso. Nenhuma credencial foi criada, inventada ou gravada.

| Ferramenta | Motivo | Benefício | O que conectar | Onde | Impacto se não conectar |
|---|---|---|---|---|---|
| **GitHub** (conector + plugin) | Push/PR/issues pelo agente | Publicar a branch, abrir PR com o relatório, criar issues dos achados | Concluir a conexão do conector GitHub (estado atual: `connect_incomplete`) **e** incluir o repositório `tiago2904santos/Sistema-de-Gest-o-de-Eventos-Sociais` nas fontes da sessão | claude.ai → Configurações → Conectores; ao abrir a tarefa, adicionar o repositório | Entrega continua por bundle na pasta local; push manual (`git push -u origin agent/bootstrap-lab`) |
| **Context7** (conector) | Documentação versionada de bibliotecas | Menos APIs inventadas; exemplos atuais | Conector Context7 (o plugin só traz um MCP remoto que não sobe nesta sessão; `mcp.context7.com` bloqueado pelo proxy daqui) | claude.ai → Conectores → Context7 | `research-library` lê o código instalado (`.venv`, `node_modules`) + `WebFetch` na doc oficial |
| **Figma** (conector + plugin) | Design ↔ código | Gerar/ler telas, tokens como variáveis, Code Connect | Conta Figma via OAuth; criar/indicar o arquivo do DS | claude.ai → Conectores → Figma | Direção visual no UI Lab, tokens DTCG e artefatos do tipo Design; skills `figma:*` ficam disponíveis mas sem ferramentas |
| **Axe MCP** (plugin Deque) | Remediação guiada + teste de teclado (IGT) | Sugestões de correção por violação | Chave/OAuth do axe DevTools (Deque) | skill `axe-accessibility:mcp-setup` | Varredura segue com `@axe-core/playwright` (sem chave) |
| **Playwright MCP** (plugin) | Exploração genérica | — | Nada (funciona no Claude Code CLI) | — | Coberto por `browser_*` do project-mcp |
| **Tavily** | Pesquisa web por API | Extração/crawl | API key | plugin | Coberto por WebSearch/WebFetch nativos (escolhido) |
| **Sentry** | Erros de produção | Alertas reais | Conta + DSN, decisão de produto | settings (opcional) | Observabilidade local do lab + logs |
| **Tesseract** (sistema) | 2 testes de OCR do produto | Suíte 100% verde | `apt install tesseract-ocr` / instalador Windows | máquina | 2 falhas conhecidas (KP-09) |

Quando um conector for ligado, rode `npm run agent:doctor` e atualize `docs/agent/tool-registry.json` (status → READY).
