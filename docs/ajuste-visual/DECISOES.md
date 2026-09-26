# Diário de decisões — ajuste visual (branch `ajuste-visual`)

Cada entrada diz o que foi unificado em quê e por quê. As regras do dono do
sistema (seção 4 da prompt em `docs/prompt-ajuste-visual-fable.md`) valem como
requisito e não são rediscutidas aqui.

## Fase 0 — diagnóstico (26/09/2026)

- **Piso de testes**: a suíte completa na `main` (commit `8e8b779`) roda 2122
  testes; o resultado da primeira execução foi `FAILED (failures=2, errors=31,
  skipped=4)`. As falhas são anteriores a este trabalho (a branch só tinha o
  ajuste da central de módulos e a prompt). A lista nominal está em
  `auditoria-visual/testes-piso-completo.txt`; o critério de pronto passa a ser
  "nenhum teste que passava deixa de passar", e não "zero falhas".
- **Prints de antes**: 321 imagens em `auditoria-visual/antes/` (100 páginas ×
  3 larguras + estados), tiradas por `auditoria-visual/capturar.py` com o
  Playwright que já estava no ambiente. `resumo.csv` registra status HTTP,
  largura de rolagem e erros de console por página.
- **Conta de teste** `auditoria.visual` só no banco local; credenciais em
  `auditoria-visual/conta-teste.txt` (pasta no `.gitignore`). O login do
  navegador de captura é feito por cookie de sessão gerado no shell, para a
  senha não passar pela conversa.
- **Achados do diagnóstico que viram trabalho**:
  - Todo o módulo Viagens rola na horizontal a 768px (largura 1300px): a barra
    de navegação do módulo tem 11 itens sem quebra e não rola dentro da faixa.
  - No celular (375px) o cabeçalho quebra: título truncado e os ícones de
    Agenda/Relatório/notificações caem sobre o texto.
  - Rolagem horizontal no celular em: agenda, cb-editar, cb-nota, pal-nova,
    vg-oficios, vg-justificativas, vg-prestacoes (e derivadas).
  - O botão flutuante das listas cobre a última linha e o menu ⋮ da linha.
  - O login e a recuperação de senha ainda são do `design-system.css` antigo
    (botão dourado, rótulos em caixa alta, campos com outro contorno).
  - Inventário de valores em `INVENTARIO-VALORES.md`; de componentes em
    `INVENTARIO.md`.

## Fase 1 — fundação (tokens)

- **Onde**: bloco `:root` no topo de `static/css/ds-v32-bridge.css`. O
  `ds-v32.css` continua intocado (cópia do design aprovado); a ponte é o lugar
  de tudo que o adapta.
- **Espaço**: a prática real do CSS era uma grade de 2px (6, 10, 14, 18px são
  os valores mais comuns depois de 8/12/16). Em vez de forçar 4px em tudo e
  mexer em centenas de medidas, a escala fechada ficou em passos de 2px até
  20px e depois 24/28/32/40/48: `--s0` 2, `--s1` 4, `--s1-5` 6, `--s2` 8,
  `--s2-5` 10, `--s3` 12, `--s3-5` 14, `--s4` 16, `--s4-5` 18, `--s5` 20,
  `--s6` 24, `--s7` 28, `--s8` 32, `--s10` 40, `--s12` 48. Valores ímpares
  (1, 3, 5, 7, 9, 11, 13, 15) foram arredondados para cima (1px a mais de ar);
  22→24 e 30→32. Ficaram crus: 34, 38 e 42px (recuo de campo para caber o
  ícone, que é medida do ícone e não ritmo) e margens negativas (encostos
  deliberados em bordas de cartão).
- **Raio**: seis papéis. `--raio-selo` 5px (selos, chips, botõezinhos ×),
  `--raio-controle` 7px (botão e campo — os 7px do botão são regra do dono),
  `--raio-bloco` 10px (menu, calendário, painel dentro do cartão, cartão de
  escolha), `--raio-cartao` 12px (cartão, seção, modal), `--raio-pilula`
  999px, `--raio-circulo` 50%. Mapa: 4–5→selo, 6–7→controle, 8–10→bloco,
  11–14→cartão. O modal `.an-dialogo` (14px) e o `.pc-zoom` (10px) passam a
  12px, como o `.mo` do ds-v32. Exceção mantida: o dia selecionado do
  calendário fica com 3px, aprovado em 15/09.
- **Sombra**: não existia token. Três níveis (`--sombra-1` repouso,
  `--sombra-2` elevado: menu/lista/calendário/gaveta, `--sombra-3` modal e
  toast) mais as duas sombras espelhadas da lista que abre para cima
  (`--sombra-2-acima`, `--sombra-2-acima-aberta`, aprovadas em 15/09) e a da
  lista aberta em foco (`--sombra-2-aberta`). Cor única `--sombra-rgb`
  (26,25,23, o grafite quente que o ds-v32 já usava); as sombras em preto puro
  e em (38,38,38) passaram para a mesma cor. `--sombra-foco`,
  `--sombra-foco-erro` e `--sombra-hover` carregam as três regras do dono.
  `--veu` é o fundo dos `::backdrop`.
- **Tipografia**: 12 tamanhos com papel: `--fs-rotulo` 11, `--fs-apoio` 12,
  `--fs-meta` 12.5, `--fs-texto` 13, `--fs-controle` 13.5 (botão e campo,
  regra do dono), `--fs-base` 14, `--fs-destaque` 15, `--fs-titulo` 16,
  `--fs-titulo-2` 20, `--fs-titulo-1` 22, `--fs-numero` 26, `--fs-h1` 28.
  Colapsos: 10 e 10.5→11; 11.5→12; 14.5→14; 15.5→15; 18→20; 21→22. Ficaram
  crus: 8 e 9px (letrinhas do calendário e do gráfico) e 64px (código da
  página de erro).
- **Alturas**: `--alt-botao` 36 (texto), `--alt-campo` 38, `--alt-botao-icone`
  38 (o "+" ao lado de um campo, aprovado em 15/09), `--alt-ib` 32 (botão de
  ícone de linha), `--alt-linha` 56 (linha de lista de escolha),
  `--alt-cabecalho-cartao` 56, `--alt-controle-celular` 46. A aplicação a cada
  componente é da Fase 2.
- **Cores**: `#fff` cru → `--branco`; os 44 valores reserva errados dentro de
  `var(--x, #…)` saíram (o token existe); os quatro tokens inexistentes
  passaram para os equivalentes (`--erro-t`→`--dg-t`, `--n-0`→`--branco`,
  `--av-t`→`--wn-t`, `--av-b`→`--wn-b`); o dourado escuro cru `#4d3703` →
  `--wn-t`; o vermelho próprio de "certidão vencida" → `--dg-r`/`--dg-t`; os
  textos sobre o grafite do cabeçalho ganharam `--sobre-grafite` e
  `--sobre-grafite-suave`; os véus de modal → `--veu`.
- **Regra morta removida**: `.fc[data-ativo] ␠\n.chips-v32{…}` (bridge 62–63)
  era um seletor quebrado sem uso em template.
- **Não tocado nesta fase**: `agenda.css` (tamanhos em rem, tratado na Fase 3
  junto com a tela), `design-system.css` (só as telas de login o usam; Fase 3),
  `pdf-place.css` (tokens inexistentes; a tela do carimbo é tratada na Fase 3).
  `viagens-cadastros.css` e `viagens-prestacoes.css` não são carregados por
  template nenhum: vão embora na Fase 4.
- **Foco**: o bridge tinha `*:focus,*:focus-visible{outline:none}` com o
  comentário "Nada de foco em lugar nenhum, a pedido de 15/09/2026", e a
  sombra de foco não existia mais em regra nenhuma. A leitura adotada: o que
  incomodava era o foco desenhado a cada clique de mouse. Foco por teclado
  (`:focus-visible`) volta com a sombra aprovada (`--sombra-foco`), porque sem
  ela quem navega por teclado não vê onde está; foco por clique (`:focus`)
  continua sem desenho. Fica registrado como ponto a confirmar no relatório.

## Fase 2 — um componente por função (primeira leva)

- **Selos**: o CSS passa a conhecer seis tons — `st--neutro`, `st--aviso`,
  `st--info`, `st--ok`, `st--perigo`, `st--dourado` — num bloco único do
  bridge. Os 25 nomes de domínio que os presenters ainda emitem (`pendente`,
  `atendido`, `pc-enviada`…) viraram apelidos desses tons no mesmo bloco; as
  definições espalhadas (bridge 477, 697, 1095, 1273, 1677 e a `cb-st--vencida`)
  saíram. Conflitos resolvidos: `st--rascunho` volta a ser **cinza** (o
  desenho aprovado do `ds-v32`; o azul do bridge era sobreposição posterior) e
  `st--neutro` tem uma definição só. Tons trocados no presenter porque o
  significado pedia: Viagem "Rascunho" âmbar→neutro (como Planos e Roteiros),
  Atendimento "Deadline vencido" cinza→perigo, Coffee "≥ x% consumido"
  cinza→perigo. O `status-badge` do editor de roteiro (templates e
  `roteiro-editor.js`) virou `st` com tom. Três testes que citavam as classes
  antigas foram atualizados (`viagens_viagem`, `viagens_roteiros`,
  `coffee_break`).
- **Botão destrutivo**: só existe a secundária em vermelho
  (`btn--secundaria btn--destrutiva`), sem `!important` (o seletor composto dá
  a especificidade). O "Cancelar solicitação" do Coffee, que era primária
  vermelha, e os dois "Excluir" em `btn-primaria` dos cadastros de Viagens
  passaram para ela. `ib-linha--perigo` idem.
- **Cabeçalho numerado da seção**: ficou só a versão em texto dourado com
  divisor (regra de 15/09); a versão em círculo, que ela sobrepunha, saiu. As
  três definições de `.section-card__cabecalho` viraram a global.
- **Cabeçalho de formulário**: as classes sem CSS no shell (`solicitacao-intro`,
  `page-header`, `page-header__identificacao/__icone/__titulo/__subtitulo`)
  saíram de 27 templates; o que vale é `d-cabeca d-cabeca--form frm-topo` +
  `d-cabeca__esq` + `d-identificacao` + `kpi__ic` + `frm-titulo` + `d-titulo-v32`.
- **Modais**: `an-dialogo`, `catalogo-paridade__dialog`, `pc-zoom` e `ag-modal`
  passam a usar as medidas do `.mo` (título 16px/600, botões de 36px, raio de
  cartão, véu `--veu`). A estrutura HTML e os scripts de cada diálogo foram
  preservados; o X de fechar nos `an-dialogo` fica para uma segunda leva.
- **Sim/não**: `viagens-switch` (cadastros de Viagens e editor de documentos)
  virou o `interruptor` canônico — antes aparecia como caixa de seleção crua,
  porque o CSS dele estava num arquivo órfão.
- **Erro e ajuda de campo**: `msg-erro`, `an-erro` → `form-erro`;
  `field__help`, `cb-ajuda` → `form-ajuda`. `ag-erro` da Agenda ficou, porque
  é mensagem de estado do painel, não erro de campo; `grupo-erro` também, porque
  é a caixa que envolve um grupo inválido.
- **Estado vazio**: `texto-vazio` alinhado ao `dt__vazio`/`lt__vazio`
  (`--fs-texto`, `--n-500`).
- **Foco e hover**: `*:focus{outline:none}` continua (clique não desenha);
  `:focus-visible` ganha `--sombra-foco`; campos de texto mostram a sombra
  também no `:focus`; `.is-invalid` troca pela vermelha. Os sete
  `outline:2px solid var(--foco…)` e o `border-color` de foco do
  "preencher por e-mail" viraram a mesma sombra. Halo de hover
  (`--sombra-hover`) aplicado a botões, botão de ícone, item da trilha,
  paginação, ícones do cabeçalho e KPI — não a itens dentro de menus, onde
  vazaria sobre os vizinhos, nem a campos.
- **Conflito resolvido**: `linha-quantidade__q` tinha 96px/36px e 74px/32px;
  ficou a última decisão (74/32) com o `text-align:center` da primeira.
