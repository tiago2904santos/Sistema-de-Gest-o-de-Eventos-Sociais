# Componentes canônicos (Design System V3.2 + ponte)

Um componente por função. Tudo o que está aqui vive em `static/css/ds-v32.css`
(base aprovada, não se edita) e `static/css/ds-v32-bridge.css` (a ponte), com
os templates em `templates/components/` e `templates/components/v32/`. Os
tokens estão no topo do bridge (`:root`); valor cru não entra em regra nenhuma.

## Tokens

| Família | Tokens | Uso |
|---|---|---|
| Espaço | `--s0` 2 · `--s1` 4 · `--s1-5` 6 · `--s2` 8 · `--s2-5` 10 · `--s3` 12 · `--s3-5` 14 · `--s4` 16 · `--s4-5` 18 · `--s5` 20 · `--s6` 24 · `--s7` 28 · `--s8` 32 · `--s10` 40 · `--s12` 48 | padding, margin, gap |
| Raio | `--raio-selo` 5 · `--raio-controle` 7 · `--raio-bloco` 10 · `--raio-cartao` 12 · `--raio-pilula` · `--raio-circulo` | selo/chip · botão e campo · menu, calendário, painel interno · cartão, seção, modal |
| Sombra | `--sombra-1` repouso · `--sombra-2` elevado (menu, lista aberta, calendário) · `--sombra-2-aberta` · `--sombra-2-acima(-aberta)` · `--sombra-3` modal/toast · `--sombra-foco` · `--sombra-foco-erro` · `--sombra-hover` · `--veu` | uma cor só (`--sombra-rgb`) |
| Fonte | `--fs-rotulo` 11 · `--fs-apoio` 12 · `--fs-meta` 12.5 · `--fs-texto` 13 · `--fs-controle` 13.5 · `--fs-base` 14 · `--fs-destaque` 15 · `--fs-titulo` 16 · `--fs-titulo-2` 20 · `--fs-titulo-1` 22 · `--fs-numero` 26 · `--fs-h1` 28 | rótulo em versalete · apoio · metadados de linha · texto · botão e campo · corpo · destaque · título de seção · h2 · h2 grande · número · h1 |
| Altura | `--alt-botao` 36 · `--alt-campo` 38 · `--alt-botao-icone` 38 · `--alt-ib` 32 · `--alt-linha` 56 · `--alt-cabecalho-cartao` 56 · `--alt-controle-celular` 46 | |
| Cor | paleta do `ds-v32` (`--n-*`, `--d-*`, estados `--ok/--wn/--dg/--in/--nt`), semânticos `--sel-b/r/f`, `--hover-b`, `--link`, `--marcado`, `--rotulo`, `--foco`, `--grafite`; na ponte `--sobre-grafite(-suave)` para texto sobre a faixa | |

## Botões

| Função | Classe | Notas |
|---|---|---|
| Ação principal | `btn-primaria` | grafite, 36px, raio 7, sem borda; a única em grafite |
| Secundária | `btn--secundaria` | contorno `--n-200`, 36px |
| Destrutiva | `btn--secundaria btn--destrutiva` | texto e borda vermelhos; fundo só no hover. Nunca primária vermelha |
| Discreta (texto) | `btn--quieta` | 26px, sem borda |
| Só ícone ao lado de campo | `btn--secundaria btn--quadrado` | 38×38 (o "+" e o remover de linha) |
| Só ícone de linha (⋮, recolher) | `ib-linha` | 28×28; 44 no celular; sempre com `aria-label` |
| Flutuante | `btn-primaria btn-flutuante` | canto inferior direito, z 30; `form.btn-flutuante-form` quando é POST |
| Link de linha "Abrir" | `acao-linha` | quando o usuário só consulta |
| Fechar modal | `mo__fechar` + ícone `x` | nunca o caractere × |

Componente: `components/v32/button.html` (`variante`: secundario · perigo · fantasma; padrão primária).
Removidos: `btn`, `btn--dourado`, `btn--secundario`, `btn--perigo`, `btn--compacto`, `btn--com-icone`, `btn--peq`, `btn--bloco`, `ag-btn`, `ag-ico`.

## Selos e chips

`st st--{tom}` com seis tons por significado: `neutro`, `aviso`, `info`, `ok`,
`perigo`, `dourado`. Os nomes de domínio (`pendente`, `atendido`, `cancelada`,
`pc-enviada`…) são apelidos desses tons, definidos num bloco só do bridge;
código novo emite o tom. Rascunho é `neutro`. Registro padrão: `st--padrao`
(dourado) ao lado do nome. Chips de filtro da Agenda: `ag-chip` (mesma família:
pílula com borda `--nt-r`, escolhido `--sel-b`/`--sel-r`).
Removidos: `status-badge`, `cb-st--vencida`, `badge`, `chip`, `tag`.

## Cartão e seção

```django
<section class="section-card reg" id="…">
  <header class="section-card__cabecalho reg__t">
    <span class="section-card__numero reg-numero" aria-hidden="true">1</span>
    <h2 class="section-card__titulo">Dados</h2>
    <div class="section-card__acao">…</div>   {# opcional, à direita #}
  </header>
  <div class="section-card__corpo">…</div>
</section>
```
Ou `{% include "components/v32/section_card.html" with numero="1" titulo="…" %}`
(mesma marcação). Cabeçalho em faixa branca no topo do cartão, número em texto
dourado com divisor. Cartão de painel: `pa-card` (+ `pa-h` para o título);
cartão de lista: `pa-card pa-card--lista cad-lista`.

## Cabeçalho de página

- Lista/painel: `d-cabeca d-cabeca--secao` › `d-cabeca__esq` (`kicker
  kicker--junto` + `h1`) › `d-acoes` (ações secundárias) — ou
  `components/v32/page_header.html`.
- Formulário: `d-cabeca d-cabeca--form frm-topo` › `d-cabeca__esq` ›
  `d-identificacao` (`kpi__ic` com ícone + `frm-titulo` com `h1.d-titulo-v32` e o
  selo `st`) › `frm-topo__acoes`. Só título e selo: nada de metadados.

## Campos

`components/input.html`, `select.html` (nunca `<select>` nativo visível;
`permitir_vazio` expõe a opção vazia), `textarea.html`, `date_range.html`,
`date_multi.html`, `upload_anexos.html`. Rótulo `form-label` sobre a borda;
ajuda `form-ajuda`; erro de campo `form-erro` (um nome só); grupo inválido
`grupo-erro`; altura `--alt-campo`. Busca: `.busca` (ícone + `input[type=search]`).
Sim/não: `label.interruptor` › `input.sr-only` + `interruptor__trilho`
(`interruptor__botao`) + `interruptor__rotulo`. Escolha em cartões:
`components/v32/cartoes_escolha.html`. Escolha de registro relacionado:
`lista_escolha.html` (único) e `multi_pick.html` (vários).

## Listas

`components/v32/lista_registros.html` — a única lista: trilha `cad_rail.html`
à esquerda, busca na barra, célula única por registro (`conteudo_linha`:
`of-cartao__titulo tm-titulo` + `tm-fatos`/`tm-fato`), menu ⋮ (`acoes_linha`),
Data List no celular, `paginacao.html` no pé. Opcionais: `icone_linha`,
`linha_attrs`, `celula_classe`, `tabela_classe`, `q`, `filtro_valores`,
`soltar_url/titulo/sub`, `param`. Sem busca nem paginação:
`lista_embutida.html`. Cada linha vem do presenter (`linha_da_lista`) com
`cancelada` para riscar.

## Menu ⋮

`div.dd.of-menu.cad-acoes[data-menu]` › `button.ib-linha[data-menu-gatilho]` ›
`div.dd__c.of-menu__corpo.tm-menu[data-menu-corpo]` com itens `dd__i of-item`
(`<b>` título, `<small>` descrição), destrutivo `dd__i--perigo`, desabilitado
`of-item--inativo`. Exclusão em dois cliques: `data-confirmar-exclusao`.

## Modal

`<dialog class="mo v32-cadastro-modal [--larga]">` com `mo__topo` (h2 16px/600 +
`mo__fechar`), `mo__corpo`, `mo__rodape` (botões 36px, Cancelar e Salvar do
mesmo tamanho); conteúdo por fetch no protocolo `data-cadastro-modal` /
`X-Cadastro-Modal` / `{"ok": true}`. Os diálogos `an-dialogo`,
`catalogo-paridade__dialog`, `pc-zoom` e `ag-modal` seguem as mesmas medidas
(título, botões, raio `--raio-cartao`, véu `--veu`).

## Estado vazio, avisos, paginação, linha do tempo, stepper

- Vazio em tabela: `td.v32-suave.dt__vazio`; em bloco de formulário:
  `p.lista-vazia` (com ícone); texto solto: `p.texto-vazio`; histórico:
  `p.lt__vazio`. Mesmo tom (`--n-500`) e tamanho (`--fs-texto`).
- Aviso: `aviso aviso--erro|--ok|--info` e `aviso--callout` (com `aviso__txt`,
  `aviso__corpo`). Erros gerais ficam fora do cartão, acima da seção.
- Paginação: `components/v32/paginacao.html` (reescreve a querystring com
  `qs_definir`; `param` = nome do parâmetro). Só aparece com mais de uma página.
- Histórico: `components/v32/historico_status.html` (linha do tempo `lt`).
- Acompanhamento: `vg-stepper` (`andamento_topo.html`), `vg-stepper__lista--auto`
  com menos de cinco etapas; precisa de `js/trilho.js`.
- Segmentado: `bx-seg` (rádios) ou o mesmo desenho em botões (`ag-seg`).

## Estados de interação

Foco por teclado: `--sombra-foco` (nada no clique); campos de texto também no
`:focus`; erro `--sombra-foco-erro`. Hover: fundo/cor do próprio controle +
`--sombra-hover` nos controles soltos; nunca muda a cor da borda. Selecionado é
dourado, repouso é cinza. Animações respeitam `prefers-reduced-motion`.
