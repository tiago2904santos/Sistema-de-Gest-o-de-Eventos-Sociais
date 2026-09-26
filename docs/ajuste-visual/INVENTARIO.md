# Inventário de componentes de interface (Fase 0, 26/09/2026)

Contagem por ocorrência dentro de `class="…"` em `templates/`; quando um
`{% if %}` alterna duas classes, cada ramo conta. Caminhos sem prefixo ficam
em `templates/pages/`. O módulo Viagens é a referência visual. A coluna
**Canônica** diz o que fica depois da Fase 2.

## 0. Três fatos que mudam a leitura do resto

| Fato | Evidência | Consequência |
|---|---|---|
| `design-system.css` (4.130 linhas) só é carregado pelas 5 telas de login e senha | `layouts/base.html:8`; as 55 páginas do `app_shell_v32.html` sobrescrevem o bloco | Toda classe que só existe lá **não tem efeito** nas telas V3.2: `btn`, `btn--compacto`, `btn--dourado`, `btn--secundario`, `btn--perigo`, `btn--com-icone`, `page-header__*`, `solicitacao-intro`, `status-badge--*`, `check-chip`, `alerta` |
| `viagens-cadastros.css` e `viagens-prestacoes.css` não são referenciados | nenhum `<link>` | CSS órfão. O `.viagens-switch` só tem visual de interruptor nesse arquivo órfão: hoje aparece como checkbox cru |
| Muito CSS morto | dos 403 nomes de classe do `ds-v32.css`, 229 não aparecem em template/JS/Python; no bridge 328 de 1.158 | Blocos inteiros de protótipo sem uso: `m-sheet`, `mf-*`, `fpanel`, `ind`, `fila`, `etapa`, `step-i`, `ctrl`, `campo-e/-v`, `chip*`, `mo-veu`, `mo-toast`, `of-tag`, `perfil-badge`, `of-vazio` |

## 1. Botões

| Função | Variação | Usos | Onde | Canônica / observação |
|---|---|---|---|---|
| Principal | `btn-primaria` | 77 | todos | **Canônica.** Altura em `ds-v32:101` = 44 (`--ctrl-h`) e bridge força 36 |
| Principal | `btn btn--dourado btn-primaria` (+`--compacto`/`--com-icone`) | 17 | `_acoes_fim.html` de Ordens/Planos/Termos/Viagem, `viagens_oficios/form.html` ×3 | sinônimos sem CSS; a referência carrega o legado |
| Principal | `btn-primaria btn--compacto` | 4 | Coffee (certidões, nota, protocolo) | `--compacto` sem efeito |
| Principal (login) | `btn btn--dourado btn--bloco` | 5 | `auth/*` | único lugar em que `btn--dourado` funciona |
| Principal (agenda) | `ag-btn`, `ag-btn--peq`, `ag-btn--filtros` | 6 | `agenda/painel.html` | botão próprio |
| Secundária | `btn--secundaria` | 76 | todos; `v32/button.html` (6 includes, todos `variante="secundario"`) | **Canônica**, 36px |
| Secundária | `btn--secundaria btn--compacto` | 27 | painéis, Coffee, importação | `--compacto` sem efeito |
| Secundária | `btn btn--secundario btn--secundaria btn--compacto` | 6 | editor de roteiro, `_trecho_linha.html`, `date_multi.html` | três nomes para a mesma coisa |
| Secundária | `btn btn--secundario btn--compacto` | 4 | `_trecho_card.html` (parcial órfão) | sem estilo |
| Destrutiva | `btn--secundaria btn--destrutiva` | 6 | `coffee_break/form.html`, `confirmar_exclusao.html`, `assinatura.html` | **Canônica** (CSS com `!important`) |
| Destrutiva | `btn btn--perigo btn--secundaria btn--destrutiva btn--compacto` | 3 | remover destino (Roteiros, Termos), remover efetivo (Planos) | |
| Destrutiva | `btn-primaria btn--destrutiva` | 1 | `coffee_break/_modal_cancelar.html` | texto vermelho sobre grafite; destoa |
| Destrutiva | `btn-primaria` "Excluir" | 2 | `_dialogo_exclusao.html`, `viaturas/confirmar_exclusao.html` | exclusão sem cara de destrutiva |
| Destrutiva (menu) | `dd__i dd__i--perigo of-item` | 16 | todos os `_acoes_linha.html` | **Canônica** em menu |
| Destrutiva | `an-remover` | 1 | `dialogo_assinado.html` | |
| Destrutiva | `acao-linha--perigo`, `ib-linha--perigo` | 0 | só CSS | morto |
| Discreta | `btn--quieta` | 0 reais | ramo `fantasma` do `button.html` | CSS existe, sem uso |
| Discreta | `acao-linha` ("Abrir") | 5 | Solicitações, Ordens, Planos, Termos, Viagem | **Canônica** como link de linha (28px) |
| Discreta | `pa-link`, `ag-link`, `ag-link-doc` ×5, `de-texto-botao` ×4, `ofc-doc__abrir` ×6, `pc-imp__abrir` ×2, `fc__limpar`, `an-limpar`, `custom-date__salto` ×10 | 31 | uma por módulo | cada uma com estilo próprio |
| Só ícone (linha) | `ib-linha` (+`cb-copiar-mini`, `of-item--inativo`, `pt-evento__remover`) | 49 | gatilho ⋮, recolher seção | **Canônica** (28×28, ícone 15; 14 em `ofc-pessoa`) |
| Só ícone (quadrado) | `btn--secundaria btn--quadrado` (13) e `… btn--compacto btn--quadrado` (5) | 18 | forms de Ofícios/Ordens/Planos, `lista_escolha.html` | **Canônica** para "+"/remover (38×38) |
| Só ícone | `mo__fechar` ×11 (30px redondo), `ag-m__x`, `pc-doc__remover`, `ident-icone` ×3 | 16 | modais, agenda, prestações, cabeçalho | 4 botões de fechar diferentes; `.ib` (44px) sem uso |
| Flutuante | `btn-primaria btn-flutuante` | 26 | 25 listas/painéis + `page_header.html` | **Canônica** |
| Flutuante | `form.btn-flutuante-form` | 3 | Ofícios, Viagem, `_etapa_3` | envelope de POST (`display:contents`) |
| Flutuante c/ menu | `dd vg-fab` | 1 | `_etapa_4.html` | |
| Compacto | `btn--compacto` | 56 | 28 arquivos | **sem efeito**; única regra `.cb-anexo .btn--compacto svg` |

**Canônico**: `btn-primaria`, `btn--secundaria`, `btn--secundaria btn--destrutiva`, `btn--secundaria btn--quadrado`, `ib-linha`, `btn-primaria btn-flutuante`, `acao-linha`. Saem: `btn`, `btn--dourado`, `btn--secundario`, `btn--perigo`, `btn--compacto`, `btn--com-icone` (>100 usos sem efeito). *(Feito na Fase 1: removidos dos templates V3.2.)*

## 2. Selos e marcadores

Base `.st` (`ds-v32:225`, 24px): 101 usos; 44 com modificador por variável (`st--{{…}}`), 3 `st--pc-{{…}}`.

| Cor | Modificadores | CSS | Uso literal | Observação |
|---|---|---|---|---|
| Âmbar | `pendente`, `aguardando`, `aguardando_despacho`, `aguardando_retorno`, `devolvida`, `pc-pendente` | bridge 444, 664 (pendente 2×), 667, 1240; ds 227–228 | pendente 13, aguardando 2 | 6 nomes, 1 cor |
| Azul | `em_andamento`, `evento_agendado`, `deferida_em_andamento`, `pc-em_preenchimento`, `rascunho` | bridge 445, 665 (2×), 1062, 1241; ds 229 | rascunho 2 (agenda, como rótulo "Motorista") | `st--rascunho` **cinza em ds:226 e azul em bridge:1062** |
| Verde | `atendido`, `atendida`, `publicada`, `ativo`, `pc-aprovada` | bridge 666, 1243; ds 230, 890 | atendido 15, ativo 3, atendida 1 | `atendido`/`atendida` convivem; agenda converte |
| Vermelho | `nao_atendida`, `nao_atender`, `nao_responder`, `pc-reprovada` | ds 231; bridge 446, 668, 1244 | — | 4 nomes |
| Cinza | `neutro`, `cancelada`, `inativo` | bridge 1063 **e** 1644 (cores diferentes); ds 232, 891 | neutro 12, cancelada 2, inativo 3 | `st--neutro` 2× |
| Dourado | `padrao`, `pc-enviada` | ds 893; bridge 1242 | padrao 2 | |
| Sem CSS | `st--cancelado` | — | `prestacoes-importar.js:66` | selo sem cor (bug) |

Quem escolhe o tom em Python: presenters de solicitacoes:37, coffee_break:32/123/173, demandas_eventos:38, atendimento_imprensa:16, viagens_oficios:88, viagens_ordens:34, viagens_planos:14, viagens_roteiros:58, viagens_termos:41/174–177, viagens_viagem:56/67, `agenda/detalhes.py:185–212`; mapas em `atendimento_imprensa/models.py:73`, `coffee_break/services.py:22`, `publicacoes/models.py:55`; string em `viagens_cadastros/views.py:616, 641–644`.

Incoerências: "Rascunho" tem 4 cores (azul em Ofícios, cinza em Planos, âmbar em Viagem, cinza `status-badge` em Roteiros); "faltam N dias" é `aguardando` em Ordens/Roteiros e `em_andamento` em Viagem; "deadline vencido" e "consumo ≥ x%" usam `cancelada` (cinza) para alerta; agenda mapeia `em_andamento`→âmbar e `deferida_em_andamento`→verde (nas listas os dois são azuis).

Outros marcadores: `status-badge status-badge--*` (Roteiros, 5 + JS), `pc-chip pc-chip--feito` (4), `ag-chip` (6 + JS), `cb-st--vencida` (2), `lista-escolha__chip` (1 + JS), `ofc-chip-motorista` (1). CSS morto: `chip`, `chips`, `chip-s`, `chip-g`, `chips-v32`, `of-tag`, `perfil-badge`, `check-chip`, `fila-chip`.

**Canônico**: `st st--{tom}` com 6 tons — `aviso`, `info`, `ok`, `perigo`, `neutro`, `dourado` — e os nomes de domínio convertidos em tom no presenter, não em CSS novo.

## 3. Modais (25 `<dialog>`, 4 famílias)

| Família | Usos | Estrutura | Abre/fecha | Observação |
|---|---|---|---|---|
| `mo v32-cadastro-modal` (10 com `--larga`) | 16 | conteúdo por fetch: `mo__topo` (h2 16px + `mo__fechar`), `mo__corpo`, `mo__rodape` (36px); 11 parciais `_modal_*` + `andamento_modal.html` | `ds-v32.js:381–470` (`data-cadastro-dialog` 16, `data-cadastro-modal` 18) | **Canônica.** `querySelector` → só um modal por página. 520/760px, véu .45 |
| `an-dialogo` | 7 | `an-form`, `an-titulo` 22px/700, `an-texto`, `an-rodape` (40px). **Sem X** | um script por diálogo: `anexar-assinado.js`, `baixar-documentos.js`, `coffee-break-importar.js`, `prestacoes-importar.js`, `viagens-prestacoes.js`, **`trilho.js:60–86`**, `agenda.js:251` | larguras 560/640/680/1120; título 2× o do `mo` |
| `catalogo-paridade__dialog` | 1 | h2 22px, `catalogo-paridade__acoes`, padding 28 | `viagens-catalogos.js` + `viagens-dialogos-cadastros.js` | véu `#0007`; "Excluir" em `btn-primaria` |
| `pc-zoom` | 1 | `pc-zoom__barra`, `pc-zoom__area` | `prestacoes-importacao.js:144–153` | visualizador de PDF, véu .7 |

Exclusão em três padrões: dois cliques no menu (`data-confirmar-exclusao`, 14 templates, `app.js:1608–1620`), diálogo `catalogo-paridade`, página inteira (`confirmar_exclusao.html` ×2). Morto: `m-sheet` (CSS + `ds-v32.js:210–222`), `mo-veu`, `mo-toast`, `mo--media`, `.v32-sheet-filtros`. **10 scripts** reimplementam abrir/fechar/clique fora.

## 4. Cartões e seções

| Variação | Usos | Padding/cabeçalho | Observação |
|---|---|---|---|
| `section.section-card.reg` + `header.section-card__cabecalho.reg__t` + `section-card__numero reg-numero` + `h2.section-card__titulo` + `section-card__corpo` | 74 seções (59 numeradas, 25 com `__acao`) em 33 arquivos | `.reg` 16/20, raio 12; título 16/600 (15.5 com número); número círculo dourado 22px (bridge 418) | **Canônica.** `.section-card__cabecalho` definido 3× (735, 1085, 2399) |
| `v32/section_card.html` (`reg-cabecalho`, número dentro do h2, `cad-frm__intro`) | 2 | | estrutura diferente da escrita à mão |
| `section.reg` solto | 5 | | |
| `pa-card pa-card--lista cad-lista` | 25 | padding 0, raio 9 | canônica para listas |
| `pa-card` + `pa-h` | 11 / 9 | 16/18, raio 9 | cartão de painel |
| `kpi` (`summary_card.html`) | 3 includes | 15/16, raio 9, `kpi__ic` 34 | **duplicado à mão** em dashboard, publicações, imprensa, cadastros |
| `metrica` (`--destaque`, `--larga`) | 11 | 16, raio 8 | outro KPI, só Viagens |
| `portal-card` | 2 | 20 | hub |
| `bloco-split` | 14 | 180px + 1fr | configurações, etapa 1, editor |
| blocos locais `v32-bloco`, `vg-bloco`, `pal-bloco`, `tm-bloco`, `ofc-grupo` ×9, `frm-fieldset` ×4, `rel-secao`, `ag-bloco` | 23 | cada um o seu | subseção sem padrão |
| `painel`, `pa-card--uc`, `pa-card--larga`, `reg--tabela`, `reg--dg` | 0 | | morto |

## 5. Cabeçalho de página

| Variação | Usos | Observação |
|---|---|---|
| Listas: `d-cabeca d-cabeca--secao` + `d-cabeca__esq` + `kicker kicker--junto` + `h1` | 29 à mão | **Canônica** |
| `v32/page_header.html` (mesma estrutura) | 7 includes / 6 arquivos | ignora `subtitulo` e `icone` |
| `d-acoes` (ações secundárias) | 9 | |
| Formulários: `solicitacao-intro d-cabeca d-cabeca--form frm-topo` + `page-header d-cabeca__esq` + `page-header__identificacao d-identificacao` + `page-header__icone kpi__ic` + `frm-titulo` + `h1.page-header__titulo d-titulo-v32` + `frm-topo__acoes` | 16–17 | três sistemas de nomes; `solicitacao-intro`, `page-header__*` **sem CSS**. **Canônico**: `d-cabeca--form frm-topo`, `d-identificacao`, `d-titulo-v32` |
| roteiro: `editor-roteiro__topo/__titulo/__topo-acoes` | 1 | |
| `frm-ident` 10, `frm-meta` 4, `d-cabeca__sub` 5, `sol-subtitulo` 7, `viagens-eyebrow` 2 | | complementos |
| `ag-topo`, `rel-cabeca`, `d-titulo`, `auth-card__cabecalho` ×5, `top_header.html` | 1 cada | próprios |

## 6. Campos

| Variação | Usos | Observação |
|---|---|---|
| `input.html` 102 · `select.html` 73 · `textarea.html` 29 · `date_range.html` 8 · `date_multi.html` 1 | | `is-invalid` no invólucro nos dois primeiros, **no próprio `<textarea>`** no terceiro |
| `viagens_cadastros/_campo.html` | 24 | booleano em `viagens-switch` **sem estilo** |
| `v32/campos_cadastro.html` | **0** | órfão; duplica o `_campo.html` |
| `viagens_oficios/_campos.html` | | checkbox cru |
| `form-campo` à mão | ~40 de 48 | |
| `form-label` 54, `form-label__obrigatorio` 14 | | rótulo flutuante (bridge 2121) |
| Ajuda: `form-ajuda` 25, `field__help` 1, `cb-ajuda` 4, `*__dica` | | **Canônico**: `form-ajuda` |
| Erro: `form-erro` 70 (+ `app.js:1767`, `documento-editor.js`), `msg-erro` 2, `an-erro` 3, `grupo-erro` 5, `de-campo__erros` 2, `trecho-linha__erros` 1, `cad-frm__erro-geral` 6, `v32-erro` 1, `ag-erro` 1 | | 9 nomes. **Canônico**: `form-erro` |
| Grades: `g-form` 40 (`--1` 5, `--2` 10, `--3` 14, `--4` 2), `v32-form-grid` 6, `form-grid` 2 (órfão), `pc-imp__campo` 7, `f` 7 | | |
| Alturas: `form-controle` 38; `busca`/`fc` 44 ou 38 em `cad-barra`; `pc-linha`/`pc-solic` 34; `pc-trechos`/`pc-diario` 36; `tempo-stepper` 32; `linha-quantidade__q` **36 e 32** (2375 vs 2586); botões 36 | | |

## 7. Listas

| Variação | Usos | Observação |
|---|---|---|
| `v32/lista_registros.html` | 10 | **nenhuma lista de Viagens usa** |
| mesma marcação à mão (com paginação embutida) | 7 | Ofícios, Justificativas, Ordens, Planos, Termos, Roteiros, Viagem — a referência duplicada |
| `v32/lista_embutida.html` | 9 | painéis |
| embutido à mão | 6 + 2 | `_etapa_2..5`, agenda |
| tabelas multi-coluna | 2 | `cadastros/lista.html`, `viagens_cadastros/lista.html` (mobile e paginação próprias) |
| `trechos-tabela` 2, `tm-tabela`, `rel-tabela`, `jt-tabela`, `pc-lista` | | |
| conteúdo da linha `of-cartao__titulo tm-titulo` + `tm-fatos`/`tm-fato` (`--ausente`) | 24 parciais; `tm-fato` 52 | **Canônica.** Variantes: `vg-fato__valor` 33, `of-fato*` 9, `ag-fato*` 6, `jt-fato*`, `os-fato*`, `cbi-fatos`, `pc-imp__fatos` |
| ícone da 1ª coluna | `icone_documento.html` 14 (Viagens, link) vs `span.tabela__icone-doc` nos componentes | duas formas |
| `data-linha-url` | 0 no HTML | `app.js:1844` morto |

## 8. Menu ⋮

`dd of-menu cad-acoes` + `data-menu` + gatilho `ib-linha` (22 + 1) — **canônica**. Corpo `dd__c of-menu__corpo tm-menu` (15) vs sem `tm-menu` (14; Roteiros e Justificativas em Viagens) — o `tm-menu` só dá `min-width:320px`. `dd__t` (nome do registro) só nos cadastros (2). Itens `dd__i of-item` 96, `dd__i--perigo` 15, `of-item--inativo` 11. Variantes de corpo 1× cada: `--acima`, `--rolavel`, `--esq`, `pc-menu`, `pc-seletor__menu`, `pt-gerenciar__menu`, `de-menu__corpo`.

## 9. Estado vazio

`td.v32-suave.dt__vazio` (21 arquivos, sem ícone, textos variados) · `p.dt__vazio` fora de tabela (7) · `p.m-vazio` (9; `.m-vazio__ic` sem uso) · `p.lista-vazia` com ícone (9; único com ícone) · `p.texto-vazio` (5) · `p.lt__vazio` (5; dois textos) · `trechos-vazio` (2) · `semres` (2) · avulsas: `hs__vazio`, `ag-vazio`, `ag-m__vazio`, `pc-lista__vazio`, `cb-anexo__vazio`, `upload-anexos__vazio`, `ofc-picker__vazio`, `custom-select__vazio` ×5, `c-vazio`. Mortos: `of-vazio`, `notificacoes-vazio`, `viagens-vazio`.

## 10. Avisos

`aviso aviso--erro` 36 (ícone "info" em 15 e "alert" em 9) · `aviso--callout` 18 (ícones ban 8, alert 3, activity 3 + 4) · `aviso--info` 12 · `aviso--ok` 1 (definido 2×: bridge 16 e 1097) · mensagens do Django em `app_shell_v32.html:92–103`; login usa `auth-alerta` e `alerta alerta--error` · `aviso-rota` 3 (definido 3×: 722, 1096, 1206) · locais `dc-aviso`, `cb-avisos`, `cbi-avisos`, `cb-anexo-avisos`, `pc-imp__avisos`, `cbi-aviso`.

## 11. Abas, segmentado, trilha

`cad_rail.html` 21 páginas (20 `sem_titulo`) — **canônica** · `demandas_rail.html` 2 (cópia com itens fixos, sem contagem) · `cad-rail-pilha` 1 · `bx-seg` 5 · `vg-docs__abas vg-trilho` 1 (`trilho.js`) · `ag-seg` 1 · `ag-abas` 1 (única com `role=tablist`) · `ag-toggle`, `pt-atividades__barra`, `de-barra__grupo`. Mortos: `filas`/`fila`, `ind`, `seg2`, `v32-aba`, `pc-abas`, `of-filtros`, `os-func-seg`, `sim-nao`, `segmented-control`.

## 12. Paginação

`v32/paginacao.html` (só via `lista_registros`, `?pagina=`) · mesma marcação à mão nas 7 listas de Viagens · reduzida em `core/notificacoes.html` · `viagens_cadastros/_paginacao_nav.html` (**`?page=`**, Anterior desabilitado, `aria-label`) · à mão com `qs_definir` em `cadastros/lista.html` · `m-pag` (celular) só em 2 listas.

## 13. Linha do tempo, histórico, stepper

`v32/historico_status.html` (`lt`) 2 includes — **canônica** · cópias à mão em Demandas, Coffee (sem selo), Solicitações · `historico_alteracoes.html` 1 · `ag-hist`, `de-historico` próprios · `vg-stepper` em 6 arquivos (componente `andamento_topo.html` em 2; à mão em Coffee, Demandas, Solicitações, Prestações, Viagem); modificadores `sol-stepper` 3, `vg-stepper__lista--auto` 3, `pc-etapas` 2 · cópias do andamento: `demandas_eventos/_andamento.html`, `_andamento_campos.html` ×2, `_modal_andamento.html` ×2 (6–29 linhas de diferença cada).

## 14. Sim/não, cartões de escolha, seleção

`label.interruptor` 3 · `button.interruptor[--ligado]` + `data-expande` 4 (mesma cara, função de mostrar/esconder) · `viagens-switch` 2 (checkbox cru) · checkbox cru 2 · `de-interruptor`, `ofc-termo`, `ag-toggle` · `cartoes_escolha.html` 8 — **canônica**; clones `os-tipo`, `pc-modo`; mortos `opc-card`, `mf-opc-card` · `lista_escolha.html` 10 · `multi_pick.html` 5 · `nome_sugerido.html` 1 · `select_multiple.html` 2 · próprios `ofc-picker`, `pc-seletor`, `unidade-picker`.

## 15. Ícones

`icon.html` 758 includes → `svg.ui-icon` 15px. **16 tamanhos** de 10 a 31px (13: 27 regras, 14: 24, 15: 29, 16: 22, 17: 10, 18: 11). Caixa de ícone: `kpi__ic` 34 (ícone 17 em `ds:730` **e** 16 em `:731`), `of-av` 34/15, `pc-linha__av`/`cbi-etapa__icone`/`ag-ico` 36/18, `de-icone`/`ident-icone` 32/18–17, `m-icone` 38, `tabela__icone-doc` 30/15, `cad-i__ic` 22/13 — 7 caixas. Ícone em botão 16→15; em linha/menu 15 (14 em `ofc-pessoa`), `acao-linha` 13, `pag__passo` 14; título de seção 15/16/17/18.

## 16. Prefixos de módulo

`pc-*` 125 classes/191 usos (Prestações 178, Coffee 11) · `cb-*`/`cbi-*` 55/83 e 29/40 · `ag-*` 60/101 (botão, segmentado, abas, chips, modal, histórico próprios) · `pt-*` 50/65 (Demandas usa 7) · `os-*` 16/18 · `pal-*` 16/29 (`pal-andamento__*` em 4 módulos) · `bx-*` 8/15 · `jt-*`, `rel-*`, `cfg-*`, `pe__*`, `de-*`/`dc-*` · **`ofc-*` 45/182 em 13 módulos** (`ofc-percurso`, `ofc-doc` viraram genéricos) · `editor-roteiro` 54 usos em 14 módulos e `bate-volta__rotulo` 40 em 10 (viraram invólucro de formulário e rótulo de período) · `custom-date` à mão 38 usos (Roteiros 20, Planos 18).

## 17. Órfãos

Templates: `v32/campos_cadastro.html` (órfão), `v32/paginacao.html` (só via `lista_registros`), `v32/andamento_modal.html` (renderizado por Python), `v32/button.html` (só `secundario`), `pages/coffee_break/_documento_pdf.html`, `_doc_gerado.html`, `pages/viagens_oficios/_artefatos.html`, `pages/viagens_roteiros/_trecho_card.html`. JS: todos referenciados; morto dentro: `ds-v32.js:210–222` (sheet), `app.js:1844` (`data-linha-url`), diálogo da etapa 4 em `trilho.js:60–86`. CSS: `viagens-cadastros.css`, `viagens-prestacoes.css`.

## Duplicações mais graves (por impacto)

1. Listas de Viagens copiam `lista_registros`/`paginacao` à mão (7 + 8 embutidas).
2. >100 classes de botão sem efeito; destrutivo de 4 jeitos. *(classes mortas já removidas na Fase 1)*
3. 25 modificadores `st--*` para 6 cores; `rascunho`/`neutro` definidos 2× em conflito; `st--cancelado` sem CSS; `status-badge` paralelo.
4. Cabeçalho de página: componente em 6 arquivos vs 29 cópias; formulário com 3 sistemas de nomes.
5. Modais: 4 famílias, títulos 16/22, botões 36/40, X ou não, 5 véus; 10 scripts; 3 padrões de exclusão.
6. Histórico e andamento copiados (3 + 4 cópias).
7. Paginação: 4 marcações, `pagina` vs `page`, celular só em 2.
8. CSS repetido/conflitante: `btn-primaria`, `section-card__cabecalho` ×3, `aviso-rota` ×3, `aviso--ok`, `st--pendente`, `st--em_andamento`, `st--neutro`, `st--rascunho`, `linha-quantidade__q`, `kpi__ic .ui-icon`; ~57% do `ds-v32.css` sem uso.
9. Sim/não em 5 versões; o padrão (`campos_cadastro.html`) é órfão.
10. KPIs: 5 caixas de número.
11. Prefixos vazando (`ofc-*`, `editor-roteiro`, `bate-volta__rotulo`, `pc-*`, `pt-*`) enquanto Agenda, Coffee e Prestações têm botões/abas/chips/diálogos próprios.
12. Erro (9), ajuda (4), vazio (>10); `is-invalid` ora no invólucro, ora no controle.
