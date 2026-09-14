# Meta 3 — Ofícios · Catálogos de motivo e de modelo de justificativa

**Origem:** `oficios:modelos_motivo_index`, `modelo_motivo_create`, `modelo_motivo_update`, `modelo_motivo_definir_padrao`, `modelo_motivo_delete`; `justificativas:modelos_index`, `modelo_create`, `modelo_update`, `modelo_definir_padrao`, `modelo_delete` (e os quatro aliases legados de justificativas).
**Destino:** `viagens_oficios:catalogo`, `catalogo_novo`, `catalogo_editar` (`motivos` e `justificativas`), que passaram a responder com o padrão de cadastros da Meta 1: `viagens_cadastros:lista`, `novo`, `editar`, `excluir`, `definir_padrao` nos slugs `motivos-oficio` e `modelos-justificativa`.
**Data:** 14/09/2026.

A origem não tem fotografia destes catálogos neste repositório; a régua foi o modelo portado (`nome`, `texto`, `ativo`, `ordem`, `is_padrao`, padrão único) e o padrão de lista, formulário e exclusão que a Meta 1 fixou para os catálogos com "padrão" (cargos e combustíveis).

Capturas do destino: [lista](imagens/meta3-oficios-catalogo-destino.png) ([antes](imagens/meta3-oficios-catalogo-antes.png)), [modal de inclusão](imagens/meta3-oficios-catalogo-modal-destino.png), [menu da linha](imagens/meta3-oficios-catalogo-menu-destino.png).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nome | obrigatório, gravado em maiúsculas, único | igual ("Nome do modelo", caixa alta automática) | igual |
| Texto | obrigatório | igual, área de texto | igual |
| Ordem | inteiro, padrão 100 | igual, com ajuda | igual |
| Ativo | marcado por padrão | chave "Ativo" com ajuda | igual |
| Padrão | um só por catálogo; marcar troca o anterior | "Usar como padrão" na inclusão e "Definir padrão" no menu da linha | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Colunas | nome, ordem, padrão, ativo | Nome, Ordem, Padrão, Situação (Ativo/Inativo) | igual |
| Busca | por nome | por nome, com "Limpar filtros" | igual |
| Ordem | `ordem`, nome | igual | igual |
| Onde fica | rotas do app de ofícios/justificativas | mesmas rotas continuam respondendo; a tela é a dos cadastros de viagens, sem entrar no trilho nem nos cartões da entrada de Cadastros (certificados na Meta 1 com os seis grupos da origem) | **adaptado**: padrão da Meta 1 |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Novo | página de formulário | modal na própria lista (`?novo=1`); `catalogo_novo` abre a lista já com o modal | **adaptado**: padrão da Meta 1 |
| Editar | página de formulário | modal (`?editar=<pk>`) | **adaptado**: padrão da Meta 1 |
| Definir padrão | rota própria por POST | idem, no menu da linha, só para quem não é o padrão | igual |
| Excluir | rota própria com confirmação | diálogo de confirmação da lista; bloqueada quando há vínculo | igual |
| Voltar aos ofícios | — | botão "Voltar aos ofícios" quando aberto a partir da lista de ofícios (`?next=`) | **adaptado** |
| Aliases legados de justificativas | `justificativas:legacy_*` | não existem | **ausente** — inventário já os marca "a decidir" (Meta 4) |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Vazio | — | "Nenhum modelo de motivo cadastrado ainda." / "Nenhum modelo de justificativa cadastrado ainda." | **adaptado** |
| Gravação | — | "Modelo de motivo criado/atualizado com sucesso.", "… definido como padrão com sucesso.", "… excluído com sucesso." | **adaptado**: mensagens do padrão de cadastros |

## O que mudou no destino nesta meta

- `catalogo.html` (tabela genérica) e `form_simples.html` deixaram de servir motivos e modelos de justificativa; continuam apenas para assinantes, numeração e configuração institucional (P10) e para termos (Meta 5).
- `viagens_cadastros/views.py` ganhou os dois catálogos no registro `CADASTROS`, o descritor de área de texto em `_campo_para_template`/`_campo.html`, e o selo Ativo/Inativo para catálogos com `ativo`.
