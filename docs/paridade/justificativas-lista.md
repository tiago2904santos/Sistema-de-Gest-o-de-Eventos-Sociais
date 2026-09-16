# Meta 4 — Justificativas · Lista, inclusão rápida e exclusão

**Origem:** `justificativas:index` (`/justificativas/`), `justificativas:api_buscar_oficios` (`/justificativas/api/oficios/`) e `justificativas:justificativa_delete` (`/justificativas/<pk>/excluir/`). Os modelos (`modelos_index`, `modelo_create`, `modelo_update`, `modelo_definir_padrao`, `modelo_delete`) estão fichados em [oficios-catalogos.md](oficios-catalogos.md); a aplicação de modelo ao texto e a regra de prazo, em [oficios-form.md](oficios-form.md).
**Destino:** `viagens_oficios:justificativas`, `justificativas_buscar_oficios` e `justificativa_excluir`, em `viagens_oficios/justificativas_views.py`, `forms.py::JustificativaQuickAddForm`, `pages/viagens_oficios/justificativas.html` e `static/js/viagens-justificativas.js`. Item "Justificativas" na navegação do módulo.
**Data:** 14/09/2026.

> **Atualização de 16/09/2026 — tela refeita a pedido do usuário.** A página
> passou a seguir as listas de cadastros, roteiros e termos (situações na
> trilha, busca na barra, uma célula de conteúdo e um menu de ações por linha).
> A **inclusão rápida** (vários ofícios de uma vez) e a busca
> `justificativas_buscar_oficios` foram **removidas**; `criar_justificativas_quick_add`
> e `JustificativaQuickAddForm` saíram do código. Cadastro e edição acontecem
> num modal, como "Novo servidor": rotas `justificativa_nova` e
> `justificativa_editar`, formulário `JustificativaCadastroForm`, serviço
> `salvar_justificativa`, template `_justificativa_modal.html`. A busca de
> ofícios que o cadastro de termos usa mudou para `viagens_oficios/busca_oficios.py`.
> O que segue abaixo descreve a tela de 14/09 e fica como registro.

## Como esta comparação foi feita

A origem **não tem fotografia desta tela** neste repositório e o Gerenciador de Viagens não estava disponível no ambiente desta rodada. A régua foi o que a Fase 4 portou do app `justificativas` da origem e nunca ganhou tela: `criar_justificativas_quick_add(form)` (um texto e um modelo para vários ofícios), o seletor de ofícios em `picker.py` (busca no servidor, teto de 30 — "quem digita algo que casa com mais de 30 refina a busca em vez de rolar", opção com rótulo, `search_text`, e `main`/`meta` com protocolo e assunto), o modelo `Justificativa` (1:1 com o ofício, `status` Rascunho/Finalizada, snapshots da regra de prazo) e as três rotas do inventário. **A conferência lado a lado com a tela da origem continua devida** (P22).

Capturas do destino: [lista](imagens/meta4-justificativas-lista-destino.png), [pendentes](imagens/meta4-justificativas-pendentes-destino.png), [inclusão rápida com a busca](imagens/meta4-justificativas-inclusao-rapida-destino.png), [menu de documentos](imagens/meta4-justificativas-menu-destino.png).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Ofícios (inclusão rápida) | seletor múltiplo com busca no servidor, até 30 resultados, rótulo "Ofício N/AAAA" e linha com protocolo e assunto | igual: busca por número, protocolo, viajante ou destino; cada escolhido vira uma linha removível; aviso "Mais de 30 ofícios casam com a busca. Refine o termo." | igual |
| Modelo de justificativa | escolha que preenche o texto | igual | igual |
| Texto | obrigatório, espaços normalizados | igual ("Informe o texto da justificativa.") | igual |
| Ofícios cancelados | — | não entram na busca nem na lista | **adaptado**: sem fotografia da origem |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Uma linha por justificativa | ofício, regra de prazo, texto, estado | cartão com nº e protocolo, período e destinos, selo temporal; bloco da regra (Obrigatória / Não exigida / Regra pendente, antecedência, prazo mínimo, primeira saída, avaliação); bloco do texto com Preenchida/Pendente e o modelo usado | **adaptado**: composição reconstruída com os blocos do cartão de ofício |
| Busca | `api_buscar_oficios` existe para o seletor; busca da lista não observada | busca por ofício, protocolo, viajante, destino ou texto | **adaptado** |
| Situação | não observada | Todas / Pendentes / Preenchidas | **adaptado** |
| Ordem | — | número decrescente | **adaptado** |
| Paginação | — | 20 por página, `?page=` | **adaptado** |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Inclusão rápida | formulário que aplica modelo e texto a vários ofícios e os marca como finalizadas | igual: painel "Inclusão rápida" com "Aplicar aos ofícios"; inválido reabre o painel com os escolhidos preservados | igual |
| Editar justificativa | leva à etapa de justificativa do wizard | lápis para o formulário do ofício, seção 4, com `?next=` | igual |
| Documentos | visualizar, PDF, DOCX da justificativa | menu com os três itens e as descrições da origem | igual |
| Excluir | `justificativa_delete` | "Excluir" com confirmação: apaga texto e modelo, volta a Rascunho; a regra de prazo e o registro 1:1 ficam | igual (o registro fica porque o ofício sempre tem uma justificativa aqui) |
| Abrir o ofício | — | "Ofício" no rodapé, para a conferência | **adaptado** |
| Permissão | quem edita | leitor vê a lista sem inclusão, exclusão e menus; POST dá 403 | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Vazio / sem resultado | — | "Nenhuma justificativa" com texto para lista vazia e para filtro sem resultado | **adaptado** |
| Aplicação | — | "Justificativa aplicada a N ofícios." | **adaptado** |
| Erro | — | "Não foi possível aplicar a justificativa. Revise os campos indicados." / "Escolha ao menos um ofício." | **adaptado** |
| Exclusão | — | "Justificativa do ofício N excluída." | **adaptado** |

## Aliases legados

`justificativas:legacy_modelo_create`, `legacy_modelo_update`, `legacy_modelo_definir_padrao` e `legacy_modelo_delete` (`/justificativas/novo/`, `/<pk>/editar/`, `/<pk>/padrao/`, `/<pk>/excluir/`) são aliases das rotas de modelos; na origem o último padrão é sombreado pelo `justificativa_delete`. **Ausentes**, aguardando a decisão P21.
