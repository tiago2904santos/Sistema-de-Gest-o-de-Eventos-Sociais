# Meta 5 — Termos de autorização · Lista

**Origem:** `termos:index` (`/termos/`), com `termos:excluir` e os menus "Escolher documentos para baixar" e "Anexar termo assinado" de cada cartão.
**Destino:** `viagens_termos:lista` (`/viagens/termos/`), em `pages/viagens_termos/lista.html`, com `viagens_termos:acao` (`excluir`).
**Data:** 14/09/2026.

Régua: a árvore acessível da origem gravada na Meta 0 (`imagens/meta0-termos-observacao.json`) e a captura `imagens/meta0-termos-origem.png`. O Gerenciador de Viagens não estava disponível no ambiente desta rodada; o conteúdo dos menus foi reconstruído das rotas de download da origem (`termos/urls.py`), o que fica registrado como desvio do protocolo (P23).

Capturas do destino: [lista](imagens/meta5-termos-destino.png) ([antes](imagens/meta5-termos-antes.png)), [menu de documentos](imagens/meta5-termos-menu-destino.png), [busca com situação](imagens/meta5-termos-filtro-destino.png).

## Campos (o cartão)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Título | `DESTINO/PR · 24/08/2026 a 30/08/2026`; só `PR` quando há apenas a UF; só a data quando é um dia | igual (`titulo_do_termo`) — destino herdado do ofício também sai como `Cidade/UF` | igual |
| Selo | "Realizado", "Sem período" | os mesmos; "Previsto", "Em andamento" e "Cancelado" completam a régua para os termos que a origem não tinha na foto | **adaptado** (P24) |
| Linha de descrição | `Ofício: 153/2026 · ADEMAR SCHONS, ADILSON JOSE DOMINGUES · AAA-1234 DUSTER`; sem ofício, só os servidores; vazia quando não há nada | igual (`descricao_do_termo`) | igual |
| Herança | — | "Herda do ofício: destino, período, servidores, viatura." quando o campo está em branco e vem do ofício | **adaptado**: explicita a regra dos valores efetivos |
| Cancelado | — (a origem lista e some) | cartão riscado com selo "Cancelado" | **adaptado** |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca | "Buscar por destino, ofício, protocolo, viatura ou servidor" | mesmo placeholder; busca em destino próprio e extras, destino do roteiro do ofício, servidores próprios e do ofício, número `N/AAAA`, protocolo com ou sem máscara, placa com ou sem hífen, modelo | igual |
| Situação | combobox "Filtrar por situação" | quatro situações combináveis com contagem (Que vão acontecer / Em andamento e realizados / Finalizados / Cancelados), a mesma régua dos roteiros e ofícios; `?cancelados=1` continua valendo | **adaptado**: mesma régua das outras listas do módulo |
| Contagem e paginação | — | "N termos"; "Mostrando 1–20 de N" com `?page=` acima de 20 | **adaptado** |
| Ordem | mais recentes primeiro | igual (`-criado_em`) | igual |
| Vazio | — | "Nenhum termo de autorização registrado ainda." / "Nenhum termo encontrado com os filtros aplicados." + "Limpar" | **adaptado** |
| Tabela Termo/Ofício/Destino/Período (antes) | — | removida: era o `form_simples`/tabela genérica daqui, sem correspondência na origem | igual à origem |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Novo termo | link ao fim da lista | botão no cabeçalho e no estado vazio | igual (posição é pele) |
| Escolher documentos para baixar | menu: PDF de todos, DOCX de todos, genérico, viatura, por servidor | menu com "Baixar PDF" (um PDF só), "Baixar DOCX" (ZIP), "Visualizar termo genérico", "Visualizar termo da viatura" (quando há viatura) e "Todos os documentos" (abre o detalhe, onde ficam os de cada servidor) | igual |
| Anexar termo assinado | menu por servidor e genérico | igual; item inativo "Gere o PDF do termo primeiro" enquanto não há PDF | igual |
| Editar termo | `/termos/<pk>/editar/` | `?next=` de volta à lista | igual |
| Excluir termo | botão com confirmação | botão com confirmação em dois cliques ("Confirmar exclusão?") | igual |
| Termo cancelado | — | menu de documentos mostra "Termo cancelado — Reative para gerar documentos" | **adaptado** |
| Leitor | — | vê "Abrir"; sem novo/editar/excluir/gerar (403 nas rotas) | **adaptado**: perfis daqui |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Exclusão | redireciona à lista | "Termo #N excluído." e volta ao `next` | igual |
| Cancelar / reativar | — | "Termo #N cancelado. O histórico foi mantido." / "Termo #N reativado." | **adaptado** |
