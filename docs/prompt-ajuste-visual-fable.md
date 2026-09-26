# Prompt para o Fable: ajuste visual completo do sistema

> Copie tudo abaixo da linha e cole numa sessão nova do Claude Code com o
> modelo Fable, aberta na pasta do projeto.

---

## 1. Sua tarefa

Você é um designer de interface e desenvolvedor front-end sênior trabalhando no
**Sistema de Gestão de Eventos Sociais** da Polícia Civil do Paraná (PCPR),
um sistema Django com templates no servidor, CSS próprio e JavaScript sem
framework.

O objetivo é um **ajuste visual completo** do sistema inteiro. Ao final, o
sistema deve estar:

- **bonito, organizado e limpo**: menos ruído, hierarquia clara, respiro
  consistente;
- **alinhado**: margens, colunas, alturas, bases de texto e ícones batendo
  entre si dentro de cada tela e de uma tela para outra;
- **coerente**: **um componente por função**. Duas coisas que fazem o mesmo
  papel (dois tipos de botão secundário, dois modais, três tipos de selo) têm
  de parecer e se comportar igual, de preferência por serem o mesmo componente.
  Funções parecidas (por exemplo, selo de situação e chip de filtro) devem
  pertencer claramente à mesma família visual.

Isto é um trabalho **visual e de experiência de uso**. Nenhuma regra de
negócio, permissão, campo, coluna, filtro, ação, status ou texto de domínio pode
mudar. Se uma tela mostra seis campos com certos rótulos, ela continua mostrando
esses seis campos com esses rótulos, só que mais bem desenhados. Você pode
reorganizar a disposição, mas não pode tirar nem inventar informação.

Trabalhe de forma autônoma e vá até o fim. Não pare para pedir confirmação a
cada passo: as decisões de gosto que o dono do sistema já tomou estão na seção
4, e são elas que você segue. Só pare para perguntar se precisar contrariar uma
dessas regras.

## 2. Ambiente

- Windows 11, Django 6.1, Python 3.14. Interpretador: `.venv\Scripts\python.exe`.
- Servidor de desenvolvimento: configuração `django-dev` do `.claude/launch.json`
  (porta **8021**). Abra com a ferramenta de pré-visualização, nunca pelo
  terminal. **Nunca** rode `runserver` sem porta: a produção local usa a 8000.
- O banco de desenvolvimento tem dados reais importados. Não rode migrations
  destrutivas, comandos de importação ou de carga (`importar_*`, `migrar_gv`,
  `desfazer_migracao_gv`), nem nada que apague registros.
- **Não encoste na produção**: nada de SSH para o VPS, nada de deploy, nada de
  `git push`. Trabalhe numa branch local.
- Codificação: os arquivos têm acento e são UTF-8. **Não edite arquivos com
  `Set-Content`/`Get-Content` do PowerShell** (corrompe o UTF-8). Use as
  ferramentas de edição de arquivo. Em heredoc do Bash, evite `#`, porque os
  comentários `{# #}` do Django quebram o comando.

### Como ver as telas

1. Suba o `django-dev` pela pré-visualização e navegue pelas páginas.
   Se precisar de login, use uma conta **de teste** criada só no banco local
   (registre usuário e senha em `auditoria-visual/`, que está no `.gitignore`,
   e não escreva a senha no chat).
2. Alternativa sem login: renderize a página com `django.test.Client` +
   `force_login(usuario)` num script, grave o HTML em `auditoria-visual/`
   (fora do git) e sirva com a configuração `render-v32` (porta 8022). Há um
   exemplo pronto em `auditoria-visual/render_paginas.py`.
3. Confira cada tela em três larguras: **1440px** (computador), **768px**
   (tablet) e **375px** (celular). Não pode haver rolagem horizontal da página
   em nenhuma delas.

### Testes

- **No início**, rode a suíte inteira uma vez
  (`.venv\Scripts\python.exe manage.py test`, cerca de 5 minutos) e anote o
  número de testes que passam. Esse é o seu piso: ele não pode cair.
- Durante o trabalho, **não rode testes a cada ajuste**. Mudança de CSS,
  marcação e JS se confere pelo print da tela. Rode testes só quando mexer em
  Python (view, form, presenter, templatetag) ou quando um template puder
  quebrar uma asserção conhecida, e aí rode **só o app afetado**
  (`manage.py test coffee_break`).
- Muitos testes checam classes e trechos de HTML. Se trocar o nome de uma
  classe de propósito, atualize o teste junto e explique no commit.
- No fim de cada fase, rode a suíte inteira.

## 3. Como o front-end está montado hoje

### Camadas de CSS

| Arquivo | Linhas | Papel |
| --- | --- | --- |
| `static/css/ds-v32.css` | ~1.000 | Base do Design System V3.2, copiada do projeto de design aprovado. Tokens (`--n-*`, `--d-*`, `--grafite`, `--papel`…) e componentes-base. |
| `static/css/ds-v32-bridge.css` | ~2.900 | Tudo o que o V3.2 não tinha: shell, formulários, listas, detalhes, modais, calendário, seletores. Cresceu por acréscimo e é o maior foco de inconsistência. |
| `static/css/design-system.css` | ~4.100 | CSS antigo. Carregado pelo `layouts/base.html`; hoje só as telas de autenticação (`layouts/auth.html`) usam de fato. O `app_shell_v32.html` sobrescreve o bloco `css_principal` e não o carrega. |
| `static/css/viagens-*.css`, `agenda.css`, `pdf-place.css` | ~950 | CSS por módulo. |

### Layouts

- `templates/layouts/app_shell_v32.html`: shell de todas as telas internas
  (54 páginas o estendem). Faixa grafite com linha dourada, ícones de Agenda,
  Relatório e notificações no cabeçalho, navegação do módulo.
- `templates/layouts/auth.html` → `base.html`: login, recuperação de senha e
  afins (identidade própria, pode continuar diferente, mas deve parecer do
  mesmo sistema).

### Componentes

- `templates/components/`: `input.html`, `select.html`, `textarea.html`,
  `date_range.html`, `date_multi.html`, `upload_anexos.html`, `icon.html`,
  `top_header.html`. O `static/js/app.js` transforma select e data em combobox
  e calendário próprios.
- `templates/components/v32/`: `page_header`, `section_card`, `button`,
  `cad_rail` (trilha lateral), `lista_registros`, `lista_embutida`,
  `paginacao`, `lista_escolha`, `multi_pick`, `cartoes_escolha`,
  `campos_cadastro`, `filtro_fc`, `historico_*`, `andamento_*`, `dialogo_*`,
  `summary_card`, `breadcrumb` e outros.
- JavaScript de comportamento: `static/js/app.js` (hooks `data-menu`,
  `data-expande`, `data-auto-enviar`, `data-linha-url`,
  `data-confirmar-exclusao`, `DS.aprimorar`), `ds-v32.js`, `trilho.js`,
  `lista-escolha.js`, `multi-pick.js`, `destinos-arraste.js` e um JS por tela.

### Páginas (templates/pages)

Eventos Sociais (`solicitacoes`, `dashboard`, `cadastros`), Coffee Break
(`coffee_break`, 12 telas), Palestras e Eventos (`demandas_eventos`),
Publicações, Atendimento à Imprensa, cadastros da ASCOM, Viagens
(`viagens_viagem`, `viagens_oficios`, `viagens_termos`, `viagens_roteiros`,
`viagens_planos`, `viagens_ordens`, `viagens_prestacoes`,
`viagens_cadastros`), Agenda, Relatório, central de módulos (`core/hub.html`),
contas e usuários (`accounts`), notificações e autenticação (`auth`).

### A referência visual

Desde 20/09/2026 o **módulo Viagens é a referência visual do sistema**, e todos
os módulos foram refeitos nessa composição:

- **Listas**: trilha de situações à esquerda (`cad_rail`), busca na barra do
  cartão, uma célula por registro (título + selos + linha de fatos `tm-fatos`)
  e ações da linha num único botão ⋮ (`dd of-menu cad-acoes` com itens
  `of-item`). Tabela com pele `cad-lista`.
- **Formulários**: cabeçalho só com ícone, título e selo de situação; cartões
  `section-card reg` com cabeçalho numerado; campos sempre pelos componentes;
  ações no topo e no fim do último cartão.
- **Cadastros**: trilha + tabela `cad-lista`, criar e editar em modal.

Use essas telas como ponto de partida. O trabalho agora é refinar esse padrão e
fazer com que ele valha **por igual** em todo lugar.

## 4. Regras que o dono do sistema já decidiu (não contrarie)

Estas decisões custaram várias rodadas de ajuste. Trate como requisito.

### Paleta (obrigatória)

`#333333` grafite · `#BEA45A` dourado · `#D1D3D4` cinza claro · `#808080` cinza
médio · `#FFFFFF`. Fundo da página `--papel: #fafafa`. Neutros frios ancorados
na paleta (`--n-900 #333333`, `--n-400 #808080`, `--n-250 #d1d3d4`).

- **Dourado = identidade + o que está escolhido/ativo**: linha sob o cabeçalho,
  brasão, ponto de notificação, marcador do módulo, `kicker`, números de seção,
  aba/filtro/item da trilha ativo, linha selecionada, cartão marcado, página
  atual, chips "padrão", destaques de KPI, links (`--link`), foco (`--foco`).
- **Cinza = repouso, hover e estrutura.** Hover **nunca** ganha dourado;
  seleção **nunca** fica cinza.
- **Botão primário é grafite** (`--grafite`, hover `--n-800`, ativo `--n-950`),
  sem borda. É a única ação em grafite.
- **Proibido**: o tom `#96762f` (dourado escuro amarronzado) e qualquer dourado
  escuro como fundo; painéis inteiros ou fundos de hover dourados. O sistema
  não pode ficar "dourado demais" nem "todo cinza, sem vida".
- Interruptor ligado é cinza (`--n-700`). Calendário é cinza, sem dourado.
- Use sempre os tokens semânticos (`--sel-b`, `--sel-r`, `--sel-f`,
  `--hover-b`, `--link`, `--marcado`, `--rotulo`, `--foco`, `--grafite`), nunca
  a cor crua.

### Interação

- Foco: sombra `0 0 7px 3px var(--d-100)` (erro: `var(--dg-b)`), sem contorno e
  sem mudar a cor da borda. Vale para botão, campo, aba, select e calendário.
- **Hover nunca muda a cor da borda**, nem em estado aberto. Os campos também
  não escurecem a borda no hover.
- Halo de hover do sistema: `box-shadow: 0 0 9px 3px var(--n-100)` somado ao
  que o elemento já faz.
- **Botões com tamanho único** no computador: 36px de altura, padding 0 16px,
  raio 7px, fonte 13.5px (primário e secundário iguais). No celular, 46px.
  "Cancelar" e "Salvar" do rodapé de modal têm o mesmo tamanho.
- O "×" de fechar ou limpar é desenhado por máscara SVG, nunca pelo caractere.
- Um menu `data-menu` aberto por vez; ele abre para cima quando não cabe
  embaixo.
- Nunca usar `<input type="date">` nem `<select>` nativos visíveis: sempre
  pelos componentes, que viram calendário e combobox próprios.
- Barras de rolagem sem trilho colorido. Nada de véu escuro atrás de select
  aberto.
- Respeite `prefers-reduced-motion` em toda animação.

### Conteúdo e composição

- **Cabeçalho de tela de edição: só título e selo de situação.** Nada de datas,
  valores ou protocolo embaixo do título.
- **Nenhuma tela abre com aviso**: nada de "Faltam informações…" nem "pronto
  para emissão" ao abrir. Aviso só de cancelado e erros depois de salvar.
- Mensagens de erro gerais ficam **fora** dos cartões, logo acima da seção.
  Erro de um campo fica junto do campo.
- **Cadastros sem Ativo/Inativo e sem campo Ordem**; listas em ordem
  alfabética; o nome ocupa a linha inteira no formulário.
- Registro padrão aparece como chip `st--padrao` ao lado do nome, nunca como
  coluna "Sim".
- Listas: sem contador de resultados, sem "Limpar filtros", rodapé
  "Mostrando…" só com mais de uma página.
- **Não recrie** o que foi apagado de propósito: KPIs no topo das listas, abas
  de fila, painéis de filtro, ordenação por coluna, tabela de histórico `hs`
  (histórico é a linha do tempo `lt`), barras de ação presas na janela,
  laterais flutuantes, tela separada do editor de documentos.
- Seções de formulário numeradas: cabeçalho em faixa branca no topo do cartão,
  número em texto dourado `--d-600` 15px negrito com divisor `--d-200`, título
  escuro 15px. (Foram rejeitados: título dourado em caixa alta e número dentro
  de círculo.)
- Textos em português do Brasil, frases normais, sem CAIXA ALTA gritada (só
  rótulos pequenos de coluna em versalete).

## 5. Inconsistências já encontradas (ponto de partida, não lista completa)

Um levantamento rápido nos templates achou:

- **Botões**: `btn-primaria`, `btn--secundaria` **e** `btn--secundario`,
  `btn--destrutiva` **e** `btn--perigo`, `btn--compacto` **e** `btn--peq`,
  `btn--dourado`, `btn--quieta`, `btn--bloco`, `btn--quadrado`,
  `btn--com-icone`, `btn-flutuante` **e** `btn-flutuante-form`, `btn--filtros`,
  além de `btn` solto. Há pares com o mesmo papel e nomes diferentes.
- **Selos e marcadores**: `st--*` (o principal, com variantes `atendido` e
  `atendida`, `ativo`/`inativo`…), `badge--*`, `selo`, `chip`, `chip--feito`,
  `chip-motorista`, `tag`. Cinco famílias para a mesma função.
- **Modais**: `mo v32-cadastro-modal` (com `--larga`), `<dialog class="an-dialogo">`
  com seis variações (`pc-dialogo`, `pc-importar`, `cbi-dialogo`, `bx-dialogo`,
  `ag-modal`), `catalogo-paridade__dialog` e `pc-zoom`. Três sistemas.
- **Raio de borda**: 4, 5, 6, 7, 8, 9, 10 e 12px convivendo no bridge, mais
  `99px`, `999px` e `50%` para pílula e círculo.
- **Cores fixas**: cerca de 30 hexadecimais escritos direto no
  `ds-v32-bridge.css` em vez de tokens; 22 `!important`.
- **CSS legado**: `design-system.css` (4.100 linhas) carregado por
  `base.html`, com regras que provavelmente só servem às telas de login.

Procure também: espaçamentos que não seguem uma escala, alturas de campo
diferentes, ícones de tamanhos diferentes na mesma função, estados vazios
desenhados de formas diferentes, cartões com padding diferente, cabeçalhos de
página com alturas diferentes, títulos de seção em tamanhos diferentes, telas
de detalhe com composições diferentes, e componentes que só um módulo usa sem
motivo.

## 6. Plano de trabalho

Crie a branch `ajuste-visual` a partir da `main` e faça **um commit por bloco
coerente** (mensagem em português, dizendo o que mudou para quem usa). Mantenha
um diário em `docs/ajuste-visual/DECISOES.md`: cada decisão de padronização,
o que foi unificado em quê e por quê.

### Fase 0: diagnóstico (antes de mudar qualquer coisa)

1. Rode a suíte inteira e anote o piso de testes.
2. Tire prints **de antes** de todas as telas nas três larguras e guarde em
   `auditoria-visual/antes/` (fora do git). Inclua estados: lista com e sem
   registros, formulário vazio e com erro, modal aberto, menu ⋮ aberto, select
   aberto, calendário aberto, detalhe com histórico.
3. Faça o **inventário de componentes** em `docs/ajuste-visual/INVENTARIO.md`:
   para cada função (botão de ação principal, secundária, destrutiva, de ícone;
   selo de situação; chip; modal; cartão; cabeçalho de página; cabeçalho de
   seção; campo; lista; menu de ações; estado vazio; aviso; aba; paginação;
   linha do tempo; stepper), liste as variações que existem, onde aparecem
   (arquivo e tela) e qual será a versão canônica.
4. Faça o **inventário de valores**: cores, raios, sombras, espaçamentos,
   tamanhos de fonte e alturas usados no CSS, com contagem.

### Fase 1: fundação (tokens)

Defina e documente, no topo do `ds-v32-bridge.css` (ou num arquivo
`ds-v32-tokens.css` carregado antes dele), escalas fechadas:

- **espaço**: por exemplo 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48;
- **raio**: poucos valores com papel claro (campo/botão, cartão, modal,
  pílula), respeitando os 7px do botão;
- **sombra**: repouso, elevado (menu, lista aberta), modal;
- **tipografia**: tamanhos, pesos e alturas de linha para título de página,
  título de seção, texto, texto de apoio, rótulo, número de destaque;
- **alturas**: campo, botão, linha de lista, cabeçalho de cartão.

Troque os valores soltos pelos tokens. Cor crua só dentro da definição do token.

### Fase 2: componentes (um por função)

Para cada função do inventário, deixe **uma** implementação canônica e migre
todas as telas para ela. No mínimo:

- **Botões**: primário, secundário, destrutivo, discreto (texto), de ícone
  quadrado, flutuante. Um nome por variante; apague os sinônimos
  (`btn--secundario`, `btn--perigo`, `btn--peq`…) depois de migrar os usos.
- **Selos**: uma família (`st`) com variantes por significado (neutro,
  andamento, pendente, concluído, cancelado, padrão), não por palavra. Selo e
  chip de filtro devem parecer parentes.
- **Modal**: um sistema de modal, com tamanhos (estreito, largo, tela cheia no
  celular), cabeçalho, corpo com rolagem e rodapé de ações iguais em todo
  lugar. Preserve o protocolo dos cadastros (`data-cadastro-modal`, cabeçalho
  `X-Cadastro-Modal`, `JsonResponse({"ok": True})`) e os comportamentos de cada
  diálogo.
- **Cartão e seção**, **cabeçalho de página**, **campos** (mesma altura, mesmo
  rótulo, mesma mensagem de erro e de ajuda), **lista** (`cad-lista`),
  **menu ⋮**, **estado vazio**, **aviso**, **abas/segmentado**, **paginação**,
  **linha do tempo** e **stepper**.

Documente cada componente canônico em `docs/ajuste-visual/COMPONENTES.md`:
quando usar, classes, variantes, trecho de template.

### Fase 3: tela por tela

Passe por **todas** as páginas de `templates/pages`, módulo por módulo, na
ordem: Viagens → Eventos Sociais → Coffee Break → Palestras e Eventos →
Publicações → Atendimento à Imprensa → cadastros da ASCOM → Agenda →
Relatório → central de módulos → contas, usuários e notificações →
autenticação.

Em cada tela, confira:

- grade e alinhamento: bordas esquerdas alinhadas, colunas de formulário
  coerentes, rótulos e campos na mesma base, ações alinhadas à direita no
  mesmo lugar em todas as telas;
- hierarquia: um título claro, seções distinguíveis, texto de apoio discreto;
- densidade: nem apertado nem com vazios sem motivo; mesmo respiro entre
  cartões em todas as telas;
- só componentes canônicos;
- estados: vazio, erro, carregando, desabilitado, selecionado;
- as três larguras, sem rolagem horizontal e sem nada sobreposto;
- menus, listas abertas e calendários por cima de tudo que devem cobrir
  (confira `z-index` e `isolation`).

As telas de autenticação podem manter a identidade própria (cartão centralizado
sobre fundo claro), mas devem usar os mesmos tokens, campos e botões. Depois
disso, veja se o `design-system.css` pode ser reduzido ao que o login usa ou
substituído por completo.

### Fase 4: limpeza

- Apague CSS morto. Antes de apagar uma classe, procure o nome em templates,
  JS **e** Python (presenters e views montam classes em string, como
  `"st--" + situacao`). Na dúvida, não apague.
- Reduza os `!important` ao que for de fato necessário.
- Reorganize o `ds-v32-bridge.css` em seções com um índice no topo (tokens,
  base, shell, botões, campos, cartões, listas, modais, menus, selos,
  componentes de tela, utilitários, responsivo).
- Apague templates e JS de componentes que ficaram órfãos.

### Fase 5: acessibilidade e acabamento

- Contraste AA em texto sobre fundo (cuidado com cinza claro sobre branco e com
  texto dourado).
- Foco visível e navegação por teclado em menus, modais, selects e calendário.
- Área de toque de no mínimo 44px no celular.
- Ícones com `aria-hidden` quando decorativos; botões só de ícone com
  `aria-label`.

### Fase 6: fechamento

1. Rode a suíte inteira. O número de testes que passam não pode estar abaixo do
   piso da fase 0.
2. Tire os prints **de depois** em `auditoria-visual/depois/`, nas mesmas
   telas, estados e larguras.
3. Escreva `docs/ajuste-visual/RELATORIO.md`: o que foi unificado (antes →
   depois), tokens finais, componentes apagados, telas revisadas, o que ficou
   pendente e por quê, e qualquer ponto em que você precisou escolher entre
   duas leituras das regras.

## 7. Critérios de pronto

- [ ] Toda função de interface tem **um** componente canônico, documentado.
- [ ] Nenhuma classe sinônima sobrou (`btn--secundario`, `btn--perigo`,
      `badge`, `selo`, `tag`…), a não ser que o relatório explique por quê.
- [ ] Um sistema de modal só.
- [ ] Raios, sombras, espaçamentos e tamanhos de fonte vêm de escalas fechadas;
      nenhuma cor crua fora dos tokens.
- [ ] Todas as páginas de `templates/pages` revisadas nas três larguras, sem
      rolagem horizontal e sem sobreposição.
- [ ] As regras da seção 4 continuam valendo em todas as telas.
- [ ] Nenhum campo, rótulo, coluna, filtro, ação ou texto de domínio mudou.
- [ ] Suíte de testes no piso ou acima.
- [ ] Prints de antes e depois, e os quatro documentos em `docs/ajuste-visual/`.
- [ ] Tudo commitado na branch `ajuste-visual`, sem push e sem deploy.

## 8. Como se comportar durante o trabalho

- Leia antes de mudar: o template, o CSS que ele usa e o JS que o liga.
- Mudança pequena e verificada vale mais que reescrita grande às cegas. Depois
  de cada bloco, tire o print e compare com o de antes.
- Se um ajuste de um componente quebrar outra tela, conserte na mesma hora.
- Não invente funcionalidade nova, não mude fluxo, não mude texto de domínio.
- Não peça confirmação para seguir as regras da seção 4. Se precisar
  contrariar uma delas, ou se uma mudança visual exigir mexer em regra de
  negócio, pare e pergunte, explicando o caso com um print.
- Ao terminar, responda com um resumo curto: o que mudou, o número de testes
  (piso e final), onde estão os prints e o relatório, e o que ficou pendente.
