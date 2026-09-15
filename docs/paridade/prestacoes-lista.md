# Meta 6 — Prestações de contas · Lista

**Origem:** `prestacoes_contas:index` (`/prestacoes-contas/`), com `prestacao_servidor_solicitacao_autosave`, `prestacao_downloads`, `prestacao_download_compilado`, `prestacao_download_assinado`, os `*_assinado_anexar`, `prestacao_servidor_finalizar`, `prestacao_servidor_arquivar` e o `card_menus`.
**Destino:** `viagens_prestacoes:index` (`/viagens/prestacoes/`), em `viagens_prestacoes/index.html` + `_cartao.html` (`viagens_prestacoes/cartoes.py`), com as mesmas rotas de autosave, anexação, finalização e arquivamento.
**Data:** 14/09/2026.

Régua: a árvore acessível e a captura da origem gravadas na Meta 0 (`imagens/meta0-prestacoes-observacao.json`, `meta0-prestacoes-origem.png`). O Gerenciador de Viagens não estava disponível no ambiente desta rodada; o conteúdo dos dois menus (documentos para baixar, documentos assinados) e o texto do WhatsApp foram reconstruídos das rotas e dos presenters portados (P25).

Capturas do destino: [lista](imagens/meta6-prestacoes-destino.png) ([antes](imagens/meta6-prestacoes-antes.png)), [menu de documentos](imagens/meta6-prestacoes-menu-destino.png), [período das diárias](imagens/meta6-prestacoes-periodo-destino.png), [anexar assinados](imagens/meta6-prestacoes-anexar-destino.png).

## Campos (o cartão, um por servidor)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cabeçalho | `161/2026 · 12.345.678-9 · ALMIRANTE TAMANDARÉ/PR, ANTONINA/PR · 25/08 a 30/08/2026` | igual (`titulo_do_cartao`) | igual |
| Selo | Pendente / Em preenchimento / … | os mesmos status; "Finalizada" quando finalizada | igual |
| Número da solicitação | caixa de texto na linha do servidor, grava sozinha | igual, `Número da solicitação de <nome>`, autosave em `prestacao_servidor_solicitacao_autosave`; sem JS, o formulário grava pelo `index` | igual |
| Período das diárias | botão "Período" (`Definir período das diárias de <nome>`), mostra `10/08 → 24/08/2026` quando definido | igual: menu com liberação e prazo de saque (calendário) e "Salvar período"; o rótulo do botão vira o período | igual |
| Servidor | nome, marca "Motorista", "✓ Comprovante" quando há comprovante, cargo · unidade | iguais | igual |
| WhatsApp | botão "Enviar aviso de liberação de diárias por WhatsApp" | igual, `wa.me` com o telefone do servidor e o texto do aviso (ofício, evento, valor, liberação, prazo, unidade) | **adaptado**: o texto exato da origem não estava disponível (P26) |
| Placa / Modelo | "Placa AAA-1234 · Modelo DUSTER"; "Não informado" | iguais | igual |
| Trechos | `CURITIBA/PR → ALMIRANTE TAMANDARÉ/PR` com saída → chegada | iguais | igual |
| Valor total, extenso, quantidade | `R$ 1.452,75`, por extenso, `5 x 100%` | iguais | igual |
| Agrupamento | cartões seguidos do mesmo ofício | mesmo cabeçalho repetido; cartões do mesmo ofício encostados | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca | "Buscar por servidor, ofício, protocolo ou solicitação…" | mesmo placeholder; busca sem acento em servidor, cargo, protocolo, número/ano e solicitação | igual |
| Situação | combobox "Filtrar por situação" | as quatro filas combináveis com contagem (Não liberadas / Liberadas / Arquivados / Finalizados), como as outras listas do módulo; `?aba=` continua o parâmetro | **adaptado**: mesma régua das outras listas |
| Status / período / ordenação | — | os parâmetros `status`, `viagem_de`, `viagem_ate` e `sort` seguem aceitos pela URL, sem controle na tela | **adaptado**: nenhum filtro inventado |
| Paginação | "Mostrando 1–20 de 38", páginas, próxima | igual (`?page=`), no topo e no rodapé | igual |
| Contagem | — | "N prestações" | **adaptado** |
| Vazio | — | mensagem da fila ("Nenhum servidor com diárias pendentes de liberação." etc.) e atalho para os ofícios ou para limpar | **adaptado** |
| Tabela Ofício/Servidor/Solicitação/Status/Ações (antes) | — | removida | igual à origem |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Abrir prestação na etapa 1 | link ao diário do servidor | igual | igual |
| Escolher documentos para baixar | menu com original/assinado de cada documento e o compilado | menu: cada documento (ofício, despacho, diário, RT, comprovante) com "Original · PDF/DOCX" e "Assinado · PDF" quando há, mais "Pacote final (PDF)"; "Documentos e downloads" abre a etapa 4 | igual |
| Anexar / Gerenciar documentos assinados | modal com os cinco documentos | menu com os cinco documentos: escolher o arquivo já envia; mostra o anexado e "Ver … anexado"; o rótulo vira "Gerenciar documentos assinados" quando já há algum | igual (menu em vez de modal é pele) |
| Finalizar prestação / Reabrir | botão | botão com confirmação em dois cliques, volta à lista como estava | igual |
| Arquivar prestação / Desarquivar | botão | idem | igual |
| Modelos de texto | link no topo (na origem, rota própria) | botão "Modelos de texto" no cabeçalho | igual |
| Leitor | — | vê os cartões e "Abrir prestação na etapa 1"; sem solicitação editável, sem anexar, finalizar ou arquivar (403) | **adaptado**: perfis daqui |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Autosave | indicador de gravação | "Salvando…" / "Salvo" / o erro devolvido ("Data inválida…", "O valor da diária não foi salvo.") | igual |
| Finalizar / arquivar | mensagens | "Prestação de <nome> finalizada." / "… reaberta." / "… arquivada." / "… desarquivada." (já existiam) | igual |
| Anexar do cartão | mensagens do carimbo | "Documento assinado anexado." e os avisos do carimbo (já existiam); recusa do arquivo em alerta | igual |
