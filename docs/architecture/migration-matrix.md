# Matriz de migração (DS v3.2 → DS v4, dentro do monólito)

"Atual" = layout e CSS de hoje. "Novo" = casco `app_shell_v4` + componentes v4 + tokens. Risco considera
regras de negócio na tela, tamanho (rotas/templates) e dívida medida. Status inicial: **não iniciado** em todos.

| Módulo | Rotas | Páginas | Atual | Novo | Status | Risco | Observações medidas |
|---|---|---|---|---|---|---|---|
| Login / conta (`accounts`) | 11 | 7 | `auth.html` + design-system.css | auth v4 | não iniciado | baixo | Piloto ideal: pequeno, sem regra de negócio; 3 violações de contraste |
| Hub / portal (`core`) | 8 | 2 | app_shell_v32 | app_shell_v4 | não iniciado | baixo | Define o casco (identidade, navegação de módulos) |
| Dashboard | 1 | 1 | v32 | v4 | não iniciado | baixo | Arquétipo DASHBOARD |
| Relatórios | 2 | 1 | v32 | v4 | não iniciado | baixo | Arquétipo REPORT |
| Cadastros gerais (`cadastros`) | 8 | 3 | v32 | v4 | não iniciado | baixo | CRUD genérico por slug — migra muitas telas de uma vez |
| Agenda | 7 | 2 | v32 + FullCalendar + 3 CSS próprios | v4 | não iniciado | **alto** | 5 violações críticas; bug de dia da semana já corrigido |
| Eventos sociais (`solicitacoes`) | 19 | 2 | v32 | v4 | não iniciado | médio | Workflow de despacho DG; formulário longo |
| Coffee Break | 60 | 16 | v32 | v4 | não iniciado | médio | Links públicos de fornecedor, lotes, pagamento |
| Palestras (`demandas_eventos`) | 16 | 5 | v32 | v4 | não iniciado | baixo | Pedido público |
| Publicações | 12 | 3 | v32 | v4 | não iniciado | baixo | Lista padrão `lista_registros` |
| Atendimento à imprensa | 12 | 3 | v32 | v4 | não iniciado | baixo | Lista padrão `lista_registros` |
| Viagens — navegação do módulo | — | — | nav-mod 12 itens | nav v4 com agrupamento | não iniciado | médio | Causa o overflow em 40 combinações (KP-04) |
| Viagens — cadastros | 11 | 5 | v32 + viagens-cadastros.css | v4 | não iniciado | baixo | |
| Viagens — roteiros | 14 | 2 | v32 + roteiro-editor.js (1,8 mil linhas) + Leaflet | v4 | não iniciado | **alto** | Cálculo de diárias (dinheiro) |
| Viagens — ofícios / justificativas | 29 | 6 | v32 | v4 | não iniciado | **alto** | Numeração oficial, eProtocolo, documentos |
| Viagens — termos | 12 | 3 | v32 | v4 | não iniciado | médio | Documentos |
| Viagens — viagem | 13 | 3 | v32 + viagens-viagem.css | v4 | não iniciado | médio | |
| Viagens — ordens de serviço | 8 | 2 | v32 | v4 | não iniciado | médio | Documentos |
| Viagens — planos de trabalho | 12 | 3 | v32 + viagens-planos.css | v4 | não iniciado | médio | Documentos |
| Viagens — prestações | 64 | 9 | v32 | v4 | não iniciado | **alto** | Maior módulo; lista com 656 KB de HTML; assinatura por link |
| Diário de campo (PWA) | 4 | 2 | próprio | v4 mobile | não iniciado | médio | Offline/Service Worker |
| Editor de documentos (`documentos`) | 23 | 1 | v32 + documento-editor.js | v4 | não iniciado | **alto** | Concorrência de edição, versões |
| Páginas públicas (pedido, fornecedor) | 4 | 5 | `auth.html` | público v4 | não iniciado | médio | Sem login; limite por IP |
| Páginas de erro 403/404/500 | — | 3 | próprias | v4 | não iniciado | baixo | Prévia em `/_lab/erro/<código>/` |

## Ordem sugerida

1. Tokens v4 + casco v4 + componentes base (botão, campo, select, tabela, diálogo, paginação, cabeçalho) no UI Lab.
2. Piloto: login + páginas de erro (baixo risco, validam o ciclo inteiro).
3. Hub, cadastros gerais, publicações, imprensa (padrão de lista).
4. Navegação de Viagens (resolve KP-04) e listas de Viagens.
5. Formulários longos (solicitações, ofícios), agenda, editores e prestações — com paridade reforçada.
6. Remover `design-system.css`, `ds-v32.css` e `ds-v32-bridge.css` quando o inventário mostrar zero uso.
