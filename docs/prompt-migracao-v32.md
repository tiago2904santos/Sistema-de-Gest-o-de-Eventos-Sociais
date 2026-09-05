# Prompt para o Codex — migrar todos os módulos para o Design System V3.2

> Copie tudo abaixo da linha e cole no Codex.

---

## 1. Quem é você nesta tarefa

Você é um desenvolvedor Django sênior trabalhando no repositório **Sistema de Gestão de Eventos Sociais** da Polícia Civil do Paraná (PCPR). Sua tarefa é **migrar a interface de todos os módulos restantes para o Design System V3.2**, que já foi implementado e aprovado no módulo *Eventos Sociais*. O visual das telas de Eventos Sociais é a **referência canônica**: você adapta as demais telas a ele, não reinventa nada.

Regra número um: **isto é uma migração visual. Nenhuma regra de negócio, permissão, nome de campo, filtro, coluna, ação, status ou texto de domínio pode mudar.** Se uma tela hoje mostra 6 colunas com esses nomes, ela continua mostrando as mesmas 6 colunas com os mesmos nomes, só que vestidas com o novo padrão.

## 2. Ambiente e comandos

- Django 6.1, Python 3.14, virtualenv em `.venv`.
- Windows. Interpretador: `.venv\Scripts\python.exe`.
- Rodar testes: `.venv\Scripts\python.exe manage.py test`
- Servidor de desenvolvimento: `.venv\Scripts\python.exe manage.py runserver 8021` (**sempre com porta**; produção roda waitress na 8000 e um `runserver` sem porta atrapalha).
- Banco de desenvolvimento tem dados reais importados; não rode migrations destrutivas nem comandos de importação.
- **Baseline obrigatório: `manage.py test` passa com 448 testes OK.** Esse número não pode cair e nenhum teste pode falhar ao final do seu trabalho.

## 3. O que já está pronto (sua referência — leia antes de tudo)

### Arquivos do Design System

| Arquivo | Papel |
| --- | --- |
| `static/css/ds-v32.css` | Cópia byte a byte do CSS aprovado no projeto de design. **NUNCA edite este arquivo.** |
| `static/css/ds-v32-bridge.css` | Ponte: tudo que falta, ajusta ou adapta o V3.2 ao HTML real do Django. **Todo CSS novo vai aqui**, com comentário explicando o porquê. |
| `static/js/ds-v32.js` | Comportamentos das telas V3.2: stepper numérico, rolagem para seção (`[data-ir]`), bottom sheets do mobile, lateral flutuante. Complementa o `app.js`, não o substitui. |
| `templates/layouts/app_shell_v32.html` | Shell V3.2 (faixa institucional, barra de módulo, conteúdo, rodapé). Carrega só `ds-v32.css` + bridge, sobrescrevendo `{% block css_principal %}` de `base.html`. |
| `templates/components/v32/filtro_fc.html` | Controle de filtro da barra de listagem. Lista curta vira menu de links; lista longa vira combobox com busca. |
| `templates/components/v32/cad_rail.html` | Trilha lateral de cadastros com contadores. |
| `core/templatetags/consulta.py` | Tag `{% qs_definir 'nome' valor %}`: reescreve a querystring preservando os demais filtros e zerando a página. |

### Telas já migradas (copie os padrões daqui)

- `templates/pages/solicitacoes/lista.html` — **listagem**: cabeçalho com indicadores, abas de fila, barra de busca/filtros/chips, tabela em painel, paginação, Data List do mobile e bottom sheets.
- `templates/pages/solicitacoes/detalhe.html` — **detalhe/workflow**: cabeçalho com status e ações, seções de resumo, bloco de decisão, lateral com acompanhamento, anexos e histórico.
- `templates/pages/solicitacoes/form.html` — **formulário longo**: seções, lateral com resumo vivo e etapas, barra de ações flutuante.
- `templates/pages/dashboard/index.html` — **painel**: KPIs, gráfico de barras, cartão de indicadores, duas listas lado a lado.
- `templates/pages/cadastros/{index,lista,form}.html` — **cadastros**: trilha lateral + lista + formulário curto.

### Pilotos originais do design (para ver a intenção visual)

Em `docs/design-import/` estão os HTML estáticos aprovados: `Piloto V3.2 - Solicitacoes (desktop).html`, `Padrao de Listagem - Mobile.html`, `Piloto - Detalhe da Solicitacao 216.html`, `Piloto - Nova Solicitacao (desktop).html`, `Piloto - Painel Eventos Sociais (desktop).html`, `Piloto - Cadastros (desktop).html`, entre outros. O `docs/design-import/github.md` explica as decisões. Abra esses arquivos quando tiver dúvida de composição.

## 4. Inventário exato do que migrar

São **32 templates**: 27 no shell antigo (`layouts/app_shell.html`) e 5 no layout de autenticação (`layouts/auth.html`). Confira com:

```bash
grep -rln 'extends "layouts/app_shell.html"' templates
grep -rln 'extends "layouts/auth.html"' templates
```

### 4.1 Módulo Coffee Break (`coffee_break`, 53 testes)

Navegação: Painel · Lotes · Solicitações · Cadastros (só admin).

- `templates/pages/coffee_break/painel.html` → padrão **painel** (referência: `pages/dashboard/index.html`)
- `templates/pages/coffee_break/lotes_lista.html` → padrão **listagem**
- `templates/pages/coffee_break/lote_detalhe.html` → padrão **detalhe**
- `templates/pages/coffee_break/solicitacoes_lista.html` → padrão **listagem**
- `templates/pages/coffee_break/detalhe.html` → padrão **detalhe**
- `templates/pages/coffee_break/form.html` → padrão **formulário**
- `templates/pages/coffee_break/cadastro_lista.html` → padrão **cadastros/lista**
- `templates/pages/coffee_break/cadastro_form.html` → padrão **cadastros/form**

### 4.2 Módulo Demandas ASCOM (`demandas_eventos`, 16 testes)

Navegação: Dashboard · Demandas · Cadastros.

- `templates/pages/demandas_eventos/dashboard.html` → **painel**
- `templates/pages/demandas_eventos/lista.html` → **listagem**
- `templates/pages/demandas_eventos/detalhe.html` → **detalhe**
- `templates/pages/demandas_eventos/form.html` → **formulário**
- `templates/pages/demandas_eventos/cadastro_lista.html` → **cadastros/lista**
- `templates/pages/demandas_eventos/cadastro_form.html` → **cadastros/form**

### 4.3 Núcleo e conta (`core` 17 testes, `accounts` 18 testes)

- `templates/pages/core/hub.html` → portal de módulos. Não existe piloto: use os cartões `kpi`/`pa-card` e o cabeçalho `d-cabeca--secao` para compor uma grade de módulos coerente com o resto.
- `templates/pages/core/notificacoes.html` → listagem simples (Data List `m-lista`/`m-item` funciona bem aqui, ou tabela `dt`).
- `templates/pages/accounts/lista.html` → **listagem**
- `templates/pages/accounts/form.html` → **formulário** curto (padrão cadastros/form)
- `templates/pages/auth/alterar_senha.html` → formulário curto
- `templates/403.html` → página de erro: use `.semres` centralizado dentro do shell V3.2

### 4.4 Módulo Viagens (`viagens_cadastros` 80 testes, `viagens_roteiros` 96 testes) — **deixe por último**

- `templates/pages/viagens_cadastros/index.html` → **cadastros/index**
- `templates/pages/viagens_cadastros/lista.html` → **cadastros/lista**
- `templates/pages/viagens_cadastros/form.html` → **cadastros/form**
- `templates/pages/viagens_cadastros/diarias.html` → listagem/tabela de vigências
- `templates/pages/viagens_cadastros/confirmar_exclusao.html` → confirmação simples
- `templates/pages/viagens_roteiros/lista.html` → **listagem**
- `templates/pages/viagens_roteiros/form.html` → **formulário complexo**, com editor de roteiro

**Atenção crítica no módulo Viagens:**
- Há trabalho não commitado nesses apps (`viagens_cadastros/*.py`, templates e `static/css/viagens-cadastros.css`, `static/js/viagens-cadastros.js`). **Não descarte, não reverta e não reescreva a lógica desses arquivos.**
- `templates/pages/viagens_roteiros/form.html` usa `static/js/roteiro-editor.js` e os parciais `_destino_row.html`, `_trecho_card.html`, `_trecho_linha.html`, com formset dinâmico, cálculo de diárias, autosave e numeração de trechos. **Todo hook, id, name, data-attribute e classe consumida por esse JS deve continuar existindo.** Se precisar mudar a marcação, ajuste o JS junto e rode `manage.py test viagens_roteiros viagens_cadastros` (176 testes) até ficar verde.
- Se o editor de roteiro se mostrar arriscado demais para migrar sem quebrar, migre as demais telas de Viagens, deixe essa por último e relate exatamente o que faltou e por quê.

### 4.5 Autenticação (`accounts`, 18 testes)

Estas telas não usam o shell de aplicação: são tela cheia, com faixa institucional no topo e um cartão centralizado, montadas por `templates/layouts/auth.html` (que hoje usa `components/top_header.html` e as classes `.auth-shell*`, `.auth-card*`, `.auth-alerta` do `design-system.css`).

Templates a migrar:

- `templates/pages/auth/login.html` — acesso ao sistema
- `templates/pages/auth/senha_reset.html` — pedir link de recuperação
- `templates/pages/auth/senha_reset_enviado.html` — confirmação de envio
- `templates/pages/auth/senha_reset_confirmar.html` — definir nova senha (trata `validlink` falso)
- `templates/pages/auth/senha_reset_concluido.html` — senha alterada

**Como migrar:**

1. Crie `templates/layouts/auth_v32.html`, análogo ao `app_shell_v32.html`: estende `layouts/base.html`, sobrescreve `{% block css_principal %}` carregando `ds-v32.css` + `ds-v32-bridge.css` e monta a faixa institucional com a marcação do shell V3.2 (`ident`, `marca`, `marca__moldura`, `marca__org`, `risco-i`, `ident__sistema`) — sem sino e sem menu de usuário, que exigem sessão. Abaixo dela, uma área centralizada com o cartão e o rodapé `rodape-v32`.
2. Refaça o cartão com as primitivas do V3.2: `pa-card` para a moldura, `kicker`/`h1`/`d-cabeca__sub` para o cabeçalho, `campo-e`/`ctrl` ou `components/input.html` para os campos, `msg-erro`/`form-erro` para os erros, `aviso aviso--erro` para o erro geral do formulário e `btn-primaria` em largura total para a ação principal.
3. Porte para o `ds-v32-bridge.css` só o que faltar (largura do cartão, centralização vertical, faixa de fundo). As classes `.auth-*` antigas podem ser abandonadas, já que só essas telas as usam — mas **não apague nada de `design-system.css`**, porque ele continua servindo os módulos ainda não migrados.
4. As telas de senha dentro do sistema (`templates/pages/auth/alterar_senha.html`, listada no item 4.3) devem receber o mesmo tratamento de campo de senha, para as duas experiências combinarem.

**O que não pode mudar nestas telas:**

- Nomes dos campos: `username`, `password`, `manter_conectado`, `next` (campo oculto), `email`, `old_password`, `new_password1`, `new_password2`.
- Atributos de acessibilidade e de navegador: `autofocus`, `autocomplete="username"`, `autocomplete="current-password"`, `autocomplete="new-password"`, `required`, `type="password"`.
- O botão de mostrar/ocultar senha, que depende dos hooks `[data-campo-senha]` e `[data-alternar-senha]` do `app.js`, com `aria-pressed` e `aria-label`.
- O link **Esqueci minha senha** apontando para `accounts:senha_reset` — há teste verificando a presença dessa URL na página de login.
- A renderização de `form.non_field_errors` e dos erros por campo.
- A linha "Ambiente restrito e monitorado" e o aviso de contato com o administrador da unidade.
- O ramo `{% if validlink %}` da tela de definir nova senha, com a mensagem de link inválido no `else`.

**Verificação específica:** `manage.py test accounts` (18 testes) mais um teste manual do fluxo completo: login com senha errada, login correto, "esqueci minha senha", e-mail de recuperação, link de redefinição, senha alterada e novo login.

### 4.6 Fora de escopo

- `atendimento_imprensa` e `publicacoes` ainda não têm templates. Ignore.

## 5. Como migrar uma página (procedimento)

Para **cada** template, nesta ordem:

1. **Leia a view** que renderiza a página e anote todo o contexto disponível (nomes exatos das variáveis), os filtros, a paginação e as permissões. Leia também os testes do app que tocam essa URL.
2. **Leia o template atual inteiro** e faça uma lista do que ele entrega: colunas, filtros, ações por linha, estados vazios, mensagens, textos, atributos `data-*`, ids e names.
3. **Escolha o padrão correspondente** entre as telas já migradas e abra o arquivo de referência lado a lado.
4. **Reescreva o template** estendendo `layouts/app_shell_v32.html`, usando as classes do V3.2 e mantendo item por item a lista do passo 2.
5. **Só então** ajuste a view, e apenas se faltar dado para o novo layout (por exemplo, um contador para o cabeçalho). Contexto novo é aditivo: não remova nem renomeie o que já existe.
6. **CSS novo só no `ds-v32-bridge.css`**, com comentário curto explicando a razão da regra.
7. **Rode os testes do app** e depois a suíte inteira.
8. **Confira no navegador** em 1440px e em 375px de largura.

## 6. Vocabulário do Design System V3.2

Para a lista completa: `grep -n "^\." static/css/ds-v32.css`. As principais famílias:

**Shell (já pronto no layout):** `pagina`, `ident`, `marca`, `navbar`, `modulo`, `nav-mod`, `conteudo`, `rodape-v32`.

**Cabeçalho de página:**
- Listagem: `cabeca`, `cabeca__esq`, `cabeca__dir`, `kicker`, `cabeca__sub`, `ind`, `ind__i`, `ind__ic` (`--n`/`--a`/`--d`), `ind__v`.
- Seção/painel/cadastro: `d-cabeca d-cabeca--secao`, `d-cabeca__esq`, `d-cabeca__sub`, `d-acoes`.
- Detalhe/formulário: `d-cabeca`, `voltar`, `d-cabeca--form`.

**Barra de filtros:** `filas`, `fila`, `fila__n`, `barra__esq`, `busca`, `fc`, `fc__rot`, `fc__n`, `fc--ferramenta`, `fc--combo`, `fc__limpar`, `fpanel`, `fpanel__grid`, `fpanel__ferr`, `campo`, `campo__label`, `chips`, `chip`, `btn--quieta`.

**Tabela:** `painel`, `dt-w`, `dt`, `dt__ord`, colunas `c-id`, `c-status`, `c-tipo`, `c-mun`, `c-per`, `c-sol`, `c-data`, `c-nome`, `c-sit`, `c-cad-acoes`; ações `acoes`, `acao-linha`, `ib-linha`; estado `st` + `st--<status em minúsculas>`; paginação `pag`, `pag__nav`, `pag__n`, `pag__passo`, `pag__el`; vazios `semres`, `semres__t`, `dt__vazio`.

**Menus:** `dd`, `dd__c` (`--esq`, `--rolavel`), `dd__i` (`--sel`, `--perigo`), `dd__t`, `dd__s`, `dd__vaga`, `dd__check`.

**Detalhe:** `d-grade`, `reg`, `reg__t`, `reg__st`, `gc`, `gc--3`, `f`, `chips-s`, `chip-g`, `dl-eq`, `resumo-op`, `reg--dg`, `dg-grade`, `dg-op`, `ta`, `dec-leitura`, `etapas`, `etapa`, `etapa--concluida`, `etapa--andamento`, `etapa__m`, `etapa__estado`, `resumo__linha`, `anexo`, `anexo__abrir`, `linha-t`, `evento`, `sticky`, `aviso`, `aviso--callout`, `aviso--erro`, `aviso--ok`, `aviso--info`.

**Formulário:** `frm-cabeca`, `frm-rasc`, `frm-grade`, `g-form`, `g-form--2`, `g-form--3`, `cheia`, `c2`, `campo-e`, `campo-e--bloco`, `ctrl`, `ctrl--erro`, `msg-erro`, `opc-cards`, `opc-card`, `seg2`, `condicional`, `eq-linha`, `stepper-n`, `an-add`, `step-v`, `step-i`, `frm-acoes`, `frm-acoes--flut`, `frm-cancelar`, `grupo-erro`.

**Painel:** `db-kpis`, `kpi`, `kpi--destaque`, `kpi__ic`, `db-2col`, `db-linha2`, `pa-card`, `pa-card--lista`, `pa-card--uc`, `pa-h`, `pa-h--lista`, `gr`, `gr__c`, `gr__b`, `gr__m`, `gr__t`, `gr__c--hoje`, `pa-dg`, `pa-dg__i`, `pa-dg__i--wn`, `pa-mini`, `pa-ev`, `pa-ev__d`, `pa-ev__t`, `pa-ev__m`, `pa-link`, `pa-rodape`, `pa-periodo`.

**Cadastros:** `cad-grade`, `cad-rail`, `cad-rail__h`, `cad-i`, `cad-i__ic`, `cad-i__t`, `cad-i__n`, `cad-titulo`, `cad-barra`, `cad-barra__fim`, `cad-visao`, `cad-lista`, `cad-limpar`, `cad-frm`, `cad-frm__intro`, `cad-frm__nota`, `cad-frm__acoes`.

**Mobile:** `lista-mobile-v32`, `m-lista`, `m-item`, `m-item__topo`, `m-item__id`, `m-item__tipo`, `m-item__meta`, `m-item__sol`, `m-item__rodape`, `m-pag`, `m-pag__meio`, `m-ferramentas`, `m-bt`, `m-bt__contagem`, `m-veu`, `m-sheet`, `m-sheet__alca`, `m-sheet__topo`, `m-sheet__fechar`, `m-sheet__corpo`, `m-sheet__rodape`, `m-op`, `m-vazio`.

**Botões:** `btn-primaria`, `btn--secundaria`, `btn--quieta`, `btn--destrutiva`.

**Ícones:** sempre `{% include "components/icon.html" with nome="..." %}`. Disponíveis hoje: activity, alert, arrow-down, arrow-right, arrow-up, ban, bell, calendar, chart, check, check-circle, checklist, chevron-down, chevron-left, chevron-right, clipboard, clock, coffee, columns, crown, document, document-plus, download, eye, eye-off, filter, gavel, grip, home, hourglass, info, kebab, landmark, lock, login, mail, map-pin, ordenar, pencil, plus, search, send, settings, shield, trash, truck, undo, upload, user, users, volante, x. Precisando de outro, adicione em `components/icon.html` no mesmo estilo (traço 1.8, 24×24, `currentColor`).

## 7. Componentes obrigatórios de formulário

**Nunca use `<input type="date">` ou `<select>` cru.** O usuário rejeita explicitamente o widget nativo do navegador. Use sempre:

- Data única: `{% include "components/input.html" with name="..." label="..." tipo="date" obrigatorio=True valor=... erros=... desabilitado=... %}`
- Intervalo de datas: `{% include "components/date_range.html" with name="periodo" start_name="data_inicio" end_name="data_fim" label="..." valor_inicio=... valor_fim=... erros=... %}`
- Select e combobox: `{% include "components/select.html" with name="..." label="..." opcoes=... selecionado=... erros=... %}`; para listas longas acrescente `pesquisavel=True`; para lista dependente, `dependente_de="estado"` e opções com `estado` no dicionário.
- Texto, telefone, número: `components/input.html` (`mascara="telefone"` liga a máscara).
- Área de texto: `components/textarea.html` ou `<textarea class="ta">`.

O `app.js` transforma essas marcações em calendário e combobox próprios. O CSS deles já foi portado para os tokens V3.2 no bridge (`.custom-date*`, `.custom-select*`, `.form-campo`, `.form-label`, `.form-controle`), então eles já saem com a cara certa dentro do shell V3.2.

Detalhe importante: `components/select.html` **não** aceita uma opção com valor vazio (ela é serializada errada). Para limpar um filtro, use um link separado com `{% qs_definir 'nome' '' %}`, como faz `components/v32/filtro_fc.html`.

## 8. Hooks de JavaScript que precisam sobreviver

Do `app.js` (carregado em todas as páginas):

| Hook | Efeito |
| --- | --- |
| `[data-menu]` + `[data-menu-gatilho]` + `[data-menu-corpo]` | menu suspenso, fecha com Escape e clique fora |
| `form[data-auto-enviar]` | envia o formulário a cada `change` |
| `[data-expande="#alvo"]` | mostra/esconde painel |
| `[data-tabela-colunas]`, `[data-colunas-menu]`, `[data-coluna-toggle]`, `[data-col]` | seletor de colunas (aplica `.coluna-oculta`) |
| `[data-linha-url]` | linha da tabela clicável |
| `[data-confirmar]`, `[data-confirmar-exclusao]` | confirmação antes de enviar |
| `[data-mask-telefone]` | máscara de telefone |
| `[data-equipe-alocacao]`, `[data-equipe-checkbox]`, `[data-equipe-quantidade]` | linhas de equipe |
| `[data-upload-anexos]`, `[data-upload-dropzone]` | anexos com arrastar e soltar |
| `[data-custom-select]`, `[data-searchable]`, `[data-depends-on]` | combobox |
| `[data-custom-date]`, `[data-custom-date-range]` | calendários |
| `[data-resumo-erros]` | foco no resumo de erros |
| `.form-campo` | wrapper que a validação e as regras condicionais procuram |

Do `ds-v32.js`: `[data-stepper]` com `[data-stepper-menos]`/`[data-stepper-mais]`, `[data-ir="#secao"]`, `[data-abrir-sheet]`/`[data-fechar-sheet]`, `.sticky` (lateral flutuante), âncora `#despacho-dg`.

Se uma tela precisa de comportamento novo, **acrescente ao `ds-v32.js`** seguindo o mesmo estilo (IIFE, sem dependências, tolerante à ausência dos elementos). Não crie um arquivo JS por página.

## 9. Armadilhas já descobertas (leia com atenção, custaram caro)

1. **Elemento posicionado sem `left` alarga a página.** Um `<span class="sr-only">` no fim de uma tabela larga criava 318px de rolagem horizontal fantasma. O bridge já força `.sr-only{left:0}`; não introduza outros elementos absolutos sem ancoragem.
2. **Tabela larga não pode alargar a página.** Ela rola dentro de `.dt-w` (o bridge já faz isso em containers de até 1100px). Verifique sempre que `document.scrollingElement.scrollWidth === clientWidth`.
3. **A lateral `.sticky` nunca pode ter barra de rolagem própria.** O `ds-v32.js` mede a lateral e só a faz flutuar quando ela cabe inteira na janela; quando não cabe, ela rola com a página e apenas a barra de ações fica presa no rodapé. Não recoloque `max-height` + `overflow:auto` nela.
4. **A barra de ações só gruda no rodapé se tiver `margin-top:auto`** dentro da lateral esticada. Sem isso o `position:sticky;bottom` não tem para onde empurrar.
5. **Não transforme o seletor de módulo num menu com os outros módulos.** Existe teste (`coffee_break.tests.test_navbar_contextual_dentro_e_fora_do_modulo`) exigindo que, dentro de um módulo, os demais não apareçam na navegação. O `a.modulo` é um link para o portal e assim deve permanecer.
6. **Formulário com `data-auto-enviar` envia a qualquer `change`.** Campos de texto disparam `change` ao perder o foco. Se adicionar um campo de busca dentro desse formulário, pare o evento nele (`stopPropagation`), como já é feito para o combobox.
7. **Alguns testes verificam marcação.** Exemplos: `assertContains(resposta, "form-erro")`, textos de estado vazio, rótulos de ação. Ao mudar a marcação, ajuste a asserção **somente** quando ela testar aparência; se ela testa comportamento, conserte o template.
8. **Use `{% estatico %}`** (de `{% load estaticos %}`) para CSS e JS: ele acrescenta versão pelo mtime em DEBUG e evita cache velho. `{% static %}` só para imagens e ícones.
9. **Layout responsivo é feito com `@container`**, não `@media`: `.pagina` declara `container-type: inline-size`. Os cortes usados são 1100px, 900px e 680px. `@media` fica reservado para altura de janela.
10. **Estados (`st--...`) precisam de classe correspondente.** O V3.2 traz as classes dos status de Eventos Sociais e `st--ativo`/`st--inativo`. Para os status dos outros módulos, crie no bridge classes com os mesmos tokens semânticos: `--ok-*` (sucesso), `--wn-*` (atenção), `--dg-*` (erro/negado), `--in-*` (informação), `--nt-*` (neutro).
11. **Escreva os arquivos com Write/Edit ou script Python.** Heredoc de bash quebra com `{# ... #}` do Django.
12. **Não edite `ds-v32.css`.** Toda diferença vai para o bridge.

## 10. Verificação obrigatória por página

1. `.venv\Scripts\python.exe manage.py test <app>` — verde.
2. Ao final de cada módulo: `.venv\Scripts\python.exe manage.py test` — 448 testes, OK.
3. Visual: suba `runserver 8021` e abra a página. Confira:
   - sem rolagem horizontal em 1440px e em 375px;
   - sem barra de rolagem interna em cartões ou laterais;
   - console do navegador sem erros;
   - menus, filtros, ordenação, paginação, ações por linha e formulários funcionando;
   - estado vazio e estado com erro de validação.
4. Alternativa sem login no navegador: renderize com o cliente de teste. Há dois exemplos prontos em `auditoria-visual/render_paginas.py` e `auditoria-visual/render_painel_cadastros.py` (fazem `force_login`, reescrevem `/static/` para `http://127.0.0.1:8021/static/` e salvam HTML numa pasta ignorada pelo git, servida por `python -m http.server 8022`).

## 11. Ordem de trabalho sugerida

1. Coffee Break (módulo completo, é o melhor espelho do que já foi feito).
2. Demandas ASCOM.
3. Núcleo: hub, notificações, contas, alterar senha, 403.
4. Autenticação: layout `auth_v32.html`, login e as quatro telas de senha.
5. Viagens (cadastros primeiro, roteiros por último).

Trabalhe **um módulo por vez** e deixe a suíte verde antes de passar para o próximo. Não commite nada sem eu pedir; se commitar, um commit por módulo, mensagem em português no imperativo.

## 12. Critérios de aceite

- [ ] Nenhum template restante estende `layouts/app_shell.html`.
- [ ] As cinco telas de autenticação usam o novo `layouts/auth_v32.html`, e o fluxo completo de login e recuperação de senha foi testado à mão.
- [ ] `manage.py test` com 448 testes OK.
- [ ] Nenhuma regra de negócio, permissão, filtro, coluna, ação ou texto de domínio alterado.
- [ ] Nenhum `<select>` ou `<input type="date">` cru nas telas migradas.
- [ ] Todo CSS novo em `ds-v32-bridge.css`, comentado; `ds-v32.css` intocado.
- [ ] Todo JS novo em `ds-v32.js`.
- [ ] Sem rolagem horizontal e sem barra de rolagem interna indevida, em 1440px e 375px.
- [ ] Console sem erros nas telas migradas.
- [ ] Trabalho não commitado de Viagens preservado.

## 13. Como me reportar

Ao final de cada módulo, entregue um resumo curto com: telas migradas, o que mudou em views (se mudou), regras novas no bridge e por quê, testes rodados e resultado, e qualquer decisão que você tomou por conta própria. Se encontrar uma tela cuja migração exigiria mudar comportamento, **pare, explique e siga para a próxima** em vez de adivinhar.
