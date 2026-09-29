# Arquitetura atual (medida em 29/09/2026, commit 53dbf3f)

## Visão geral

```text
Navegador ──HTML──▶ Django 6.1 (monólito, 27 apps) ──ORM──▶ PostgreSQL (prod/CI) | SQLite (dev)
   │  CSS: ds-v32.css + ds-v32-bridge.css (+ design-system.css nas telas de auth/públicas)
   │  JS: 45 arquivos vanilla em static/js (sem bundler), vendor: FullCalendar, Leaflet, pdf.js
   ▼
Serviços de domínio (services.py por app) ── documentos: docxtpl → Word COM | LibreOffice | WeasyPrint | fpdf2
Integrações: eProtocolo PR (mock por padrão) · OpenRouteService · OSM/Nominatim · WhatsApp Cloud · Anthropic (opcional) · SMTP
Execução: waitress (Windows) / gunicorn+nginx (VPS) · WhiteNoise · rotinas diárias via middleware (sem cron/Celery)
```

## Números (fonte: `ui-inventory/summary.json`)

| Item | Qtde |
|---|---|
| Apps de projeto | 27 (+ `agent_lab` no desenvolvimento) |
| Rotas (incl. admin) | 600 |
| Templates de página / layouts / componentes | 201 / 3 / 40 |
| Formulários | 62 |
| Modelos | 109 |
| Testes Django | 3.054 (≈ 70 mil linhas) |
| Python de produção | ≈ 150 mil linhas (fora testes e migrações) |
| CSS / JS próprios | ≈ 9,8 mil / 14,9 mil linhas |

## Camadas e fronteiras

- **Domínio**: cada app tem `models.py`, `services.py`/`services/`, `forms.py`, `views.py`, `presenters` quando lista.
  Regras de dinheiro (diárias), numeração anual com reserva transacional e lacunas, e documentos oficiais têm testes de
  caracterização e goldens.
- **Autorização**: `accounts.modulos` (Setor ↔ Módulo) registrado por app no `ready()`; middleware bloqueia o namespace e
  o decorator `acesso_ao_modulo` protege as views (163). Grupos: SOLICITANTE, GESTOR_DG, ADMINISTRADOR, VIAGENS_GESTOR, VIAGENS_OPERADOR.
- **Auditoria**: trilha imutável por signals (`auditoria.RegistroAuditoria`) + `LogAuditoria` manual.
- **Documentos**: app `documentos` (registry de tipos, façade síncrona, cache por fingerprint, artefatos com hash, assinatura versionada).
- **Portal**: `MODULOS_PORTAL` alimenta o hub e a navbar contextual (8 módulos; Viagens com 12 itens).

## Acoplamento (fonte: `reports/architecture/dependency-graph.json`)

- 176 arestas de import entre apps no código de produção; **um único ciclo com 19 apps** (inclui `core`, `accounts`,
  `documentos` e todos os `viagens_*`). `core` importa apps de domínio — a base depende do topo.
- Relações de modelo entre apps: 53; ciclo `accounts ↔ viagens_cadastros` (usuário ↔ servidor).

## Frontend

- Um layout de aplicação (`layouts/app_shell_v32.html`) usado por todas as páginas internas; `layouts/auth.html` para login e páginas públicas.
- Três camadas de CSS concorrentes: `design-system.css` (4,2 mil linhas, V2), `ds-v32.css` (1 mil, V3.2) e `ds-v32-bridge.css`
  (3,2 mil, adaptação V2→V3.2). 308 seletores definidos em mais de um arquivo; 207 custom properties, 42 sem uso.
- Sem escalas: 115 `font-size` distintos, 18 breakpoints, 12+ raios, sombras e z-index literais.
- Componentização por `{% include %}` com contrato em comentário no topo do template (bom padrão; sem verificação automática).

## Qualidade medida no laboratório

| Dimensão | Resultado | Relatório |
|---|---|---|
| Desempenho | TTFB 16–234 ms, LCP 150–480 ms, CLS ≈ 0 nas 20 páginas-chave | `reports/performance/summary.md` |
| Acessibilidade | 5 críticas (agenda), 177 sérias (quase todas contraste) | `reports/accessibility/summary.md` |
| Responsivo | Overflow horizontal em 40 de 120 combinações (navegação de Viagens) | `reports/responsive/summary.md` |
| Rotas | Nenhuma rota GET sem parâmetro devolve 5xx | `tests/smoke/routes.spec.ts` |

## Conclusão

O backend é o ativo: domínio rico, testado, com invariantes no banco. O passivo está na camada de
apresentação (CSS em três gerações, sem escalas nem tokens semânticos, acessibilidade abaixo do AA)
e no acoplamento entre apps. Ver a decisão em [adr/0001](adr/0001-arquitetura-alvo.md).
