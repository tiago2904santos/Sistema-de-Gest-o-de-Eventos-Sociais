# Auditoria prática — 29/09/2026

Triagem feita no navegador, módulo a módulo, no servidor de desenvolvimento
(`django-dev`, porta 8021), com a conta `auditoria.visual`. Cada achado abaixo foi
visto na tela ou provado no console — não há suposição.

**Como ler:** `BUG` = está quebrado ou engana o usuário. `UX` = funciona, mas custa
tempo ou atenção de quem usa. `A11Y` = barreira de acessibilidade.
Cada item traz o arquivo quando a causa foi localizada.

---

## Resumo

O sistema está **sadio por baixo**: varri as 96 rotas GET do projeto e nenhuma
devolveu erro 500. Os fluxos centrais funcionam — o despacho, a geração da viagem,
a leitura de e-mail, o cálculo de diárias, os documentos em PDF.

O que pesa é o acabamento, e ele se concentra em **cinco pontos que se repetem em
todos os módulos**. Resolver esses cinco muda a sensação de uso do sistema inteiro
mais do que qualquer tela nova:

1. A linha de uma lista não é clicável — abrir um registro exige ⋮ → "Abrir".
2. O foco do teclado é invisível no sistema inteiro.
3. Os rótulos de dia da semana da agenda estão um dia atrás.
4. O cinza da paleta não alcança o contraste mínimo em texto pequeno.
5. Não existe página 404 nem 500 própria.

---

## 1. Bugs

### BUG-01 — A agenda mostra o dia da semana errado · **grave**

`static/js/agenda.js:254, 258, 260`

A coluna rotulada "sáb." contém 30/08/2026, que é **domingo**. A que diz "seg." é
01/09, uma **terça**. Todo rótulo está deslocado um dia, no mês, na semana e na
programação.

A causa: o FullCalendar entrega a data como marcador em UTC e o código lê o dia em
horário local (UTC−3), então recua um dia.

```js
// hoje
return DIAS_CURTOS[arg.date.getDay()];      // new Date('2026-08-30').getDay() === 6 → "sáb."
// correto
return DIAS_CURTOS[arg.date.getUTCDay()];   // getUTCDay() === 0 → "dom."
```

O mesmo vale para `getDate()` e `getMonth()` nas linhas 254 e 258. Numa agenda, um
rótulo de dia errado faz marcar compromisso no dia errado — por isso é o item mais
urgente da lista.

### BUG-02 — A seção "Anexos" fica só com o título

`templates/pages/solicitacoes/form.html:231`

Numa solicitação já deferida, sem anexos e sem permissão de anexar, a seção
"3 Anexos" aparece com o número, o título e **nada embaixo**. Falta o `{% else %}`
com o estado vazio ("Nenhum arquivo anexado."), ou esconder a seção inteira.

### BUG-03 — Não existe página 404 nem 500

Existe `templates/403.html`, mas não `404.html` nem `500.html` e não há
`handler404`/`handler500` em `config/urls.py`. Em produção (`DJANGO_DEBUG=0`) quem
erra um link cai na página crua do Django: fundo branco, "Not Found", sem cabeçalho
PCPR e sem caminho de volta.

### BUG-04 — Banco de desenvolvimento atrás do código *(já resolvido nesta sessão)*

A home quebrava com `ProgrammingError: coluna
coffee_break_solicitacaocoffeebreak.endereco não existe`. Havia 5 migrações
pendentes (coffee_break 0021, demandas_eventos 0017, solicitacoes 0024,
viagens_planos 0009, viagens_viagem 0005). Rodei `migrate` e a home voltou.

**As mesmas 5 estão pendentes em produção** — conferir antes do próximo deploy.

---

## 2. O que vale para o sistema inteiro

### UX-01 — A linha da lista não abre o registro · **maior ganho isolado**

Em Eventos Sociais, Coffee Break, Palestras, Publicações, Imprensa, Roteiros,
Ofícios e Prestações a linha inteira é inerte. A única porta é o menu ⋮ →
"Abrir"/"Editar". São dois cliques e uma leitura de menu para a ação mais comum do
sistema.

**Fazer:** o título da linha vira `<a>` para a tela de edição; a linha inteira ganha
`cursor: pointer` e um hover cinza (`--hover-b`). O ⋮ continua para o resto.

### A11Y-01 — O foco do teclado é invisível

`static/css/ds-v32.css:33` — `:focus-visible{outline:none}` global.

Alguns componentes recolocam o anel por conta própria (agenda, `custom-select`,
`custom-date`), mas link, botão, campo e aba do casco V3.2 ficam sem nenhuma marca.
Conferido na tela: com o foco em "Cadastros", a captura não mostra diferença
nenhuma.

**Fazer:** trocar a regra global por um anel padrão com o token que já existe:

```css
:focus-visible{ outline:2px solid var(--foco); outline-offset:2px }
```

E remover os `outline:none` individuais que sobraram por cima.

### A11Y-02 — O cinza da paleta não alcança o mínimo de contraste

Medido no navegador, em texto real:

| Onde | Cor | Contraste | Mínimo |
|---|---|---|---|
| `.form-label` 11px | `#777` | **4,33:1** | 4,5:1 |
| metadados da linha ("Sem solicitante", "Local não informado") 12px | `#808080` | **3,78:1** | 4,5:1 |
| `.custom-date__valor` (data vazia, "dd/mm/aaaa") 14px | `#A6A8AA` | **2,23:1** | 4,5:1 |

O `#808080` é token da casa, então a correção é de paleta, não de tela: escurecer o
cinza de texto para `#6B6B6B` (≈5,3:1) e manter o `#808080` só para ícone e traço.
O texto de data vazia precisa de um salto maior.

### UX-02 — Links repetidos com o mesmo nome

Na home são seis "Entrar no módulo"; em "Textos dos documentos", dez "Abrir modelo".
Quem navega por teclado ou leitor de tela ouve uma lista de itens idênticos.

**Fazer:** o cartão inteiro vira o link e o botão sai, ou o rótulo leva o nome
("Entrar em Coffee Break").

### UX-03 — O dourado carrega dois significados ao mesmo tempo

A regra da casa é dourado = identidade + estado ativo/escolhido. Hoje ele também
marca número que pede atenção: "12 aguardando despacho", "149 pendências",
"814 em aberto", "6 deadline vencido", o cartão destacado do painel, o chip
"0 de 10", o selo "SIMULADO". Em Imprensa, "em aberto" (814) e "deadline vencido"
(6) recebem exatamente o mesmo dourado, embora um seja rotina e o outro seja prazo
estourado.

**Fazer:** uma escada de gravidade — dourado para "olhe isto", e um tom quente
próprio (ou só o ícone + peso do número) para "isto venceu". Assim o dourado volta
a significar uma coisa só.

### UX-04 — Dois padrões de rótulo no mesmo formulário

Em `/solicitacoes/<id>/editar/`, "Período", "Destino" e "Quem pede" usam rótulo à
esquerda; "Tipo do evento", "Local do evento" e "Tipo de operação" usam rótulo em
cima. As telas de Coffee Break e Palestras usam só rótulo em cima.

**Fazer:** adotar rótulo em cima em tudo (é o padrão da maioria das telas) e
aposentar a variante à esquerda.

### UX-05 — Faixas com vários campos sob um rótulo só

Ainda em Eventos Sociais: "Quem pede" cobre **quatro** controles; "Período" e
"Destino" cobrem dois cada. Os rótulos existem no HTML (o leitor de tela lê), mas
não na tela — quem enxerga adivinha pelo placeholder qual campo é órgão e qual é
sigla.

**Fazer:** rótulo visível em cada campo, ou um rótulo de grupo com sub-rótulos
pequenos ("de" / "até", "UF" / "município").

### UX-06 — Registro travado parece editável

Na solicitação #223, 28 dos 50 campos estão bloqueados. A diferença é o fundo
`#F7F8F8` contra `#FFF` — quase imperceptível. Pior: o campo de data desabilitado
mantém `cursor: pointer`, convidando ao clique que não responde. E não há nenhuma
frase dizendo por que está travado.

**Fazer:** quando o registro está travado, não desenhar caixas — mostrar os valores
como texto, em folha de leitura, com uma faixa no topo: "Solicitação deferida. Para
mudar algo, use Editar."

### UX-07 — Ação principal no meio da página

Na solicitação, "Voltar" e "Marcar como atendida" ficam no fim da seção 3, com mais
cinco blocos abaixo (Despacho, Viagem, Encerramento, Responsável, Histórico). Quem
rola até o fim não encontra botão nenhum.

**Fazer:** barra de ação fixa no rodapé da tela, ou mover os botões para depois do
último bloco.

### UX-08 — O que foi digitado se perde sem aviso

Preenchi "Local de entrega" numa solicitação de coffee break e naveguei para outra
página: saiu sem perguntar nada. Em Viagens há autosave (plano e ofício se salvam
sozinhos); em Coffee Break e Eventos Sociais, não.

**Fazer:** ou estender o autosave, ou um `beforeunload` quando o formulário está
sujo. Hoje o comportamento muda de módulo para módulo sem o usuário saber.

### UX-09 — Sem estado de carregamento

A agenda abre com a grade vazia e só depois recebe os 237 eventos; o formulário com
documento embutido mostra um vão branco até a folha aparecer. Nas duas telas eu
cheguei a capturar o estado vazio e achar que não havia dado.

**Fazer:** esqueleto cinza no lugar do conteúdo enquanto carrega.

### UX-10 — Paginação de 15 em 15

105 solicitações viram 7 páginas. Sem escolha de quantidade.

**Fazer:** 25 por padrão, com opção de 50/100.

---

## 3. Módulo a módulo

### Central de módulos (`/`)

- Os cartões de Agenda e Relatório não têm métrica e ficam com um vão vazio até o
  botão, enquanto os outros mostram três números. Dar métrica própria a eles
  ("hoje / esta semana"; "último gerado") ou deixar o cartão encolher.
- **As métricas não são clicáveis.** "12 aguardando despacho" deveria abrir a lista
  já filtrada — é o atalho mais óbvio do sistema e hoje obriga a entrar no módulo e
  filtrar de novo.
- O botão do menu do usuário e o link do brasão não têm nome acessível.
- A área "Solte o e-mail aqui" não parece um alvo de arrastar: sem borda tracejada,
  sem estado de hover. Só o botão "Colar o texto" comunica.
- A ordem dos cartões não segue nada visível. Vale separar "trabalho do dia"
  (Eventos, Coffee Break, Palestras, Publicações, Imprensa) de "consulta"
  (Agenda, Relatório) e "apoio" (Usuários).

**Funciona muito bem:** a leitura de e-mail. Colei um pedido fictício de palestra e
o sistema classificou certo, abriu "Nova palestra", preencheu **13 campos** (data
20/10/2026, hora 14:00, Ponta Grossa, "auditório da escola", público 120),
destacou em dourado o que preencheu, ofereceu "Não é uma palestra? abrir como
Evento social · Coffee break · Publicações", listou a sugestão que não usou e
ainda deu "Desfazer o preenchimento". É o melhor recurso do sistema.

### Agenda

- BUG-01 acima.
- Sem estado de carregamento (UX-09).
- O modal do evento está ótimo: tarja, abas Resumo/Histórico, "Abrir no sistema",
  fecha com Esc. Só falta devolver o foco ao evento que abriu (hoje volta ao
  `body`).

### Eventos Sociais

- **Painel:** o gráfico "Solicitações por mês" não tem eixo nem valor — não dá para
  saber se a barra é 3 ou 30. Mês sem dado fica sem barra e sem "0", parecendo falta
  de dado em vez de zero.
- **Painel e lista:** dois selos de famílias diferentes na mesma linha ("Rascunho" é
  situação da solicitação, "Realizado" é situação do evento) desenhados igual.
  Distinguir: um sólido, outro de contorno.
- **Lista:** o número da solicitação existe (`#223`) mas só no rótulo do menu. A
  busca pede "nº" e a lista não mostra nenhum. Vi três linhas seguidas idênticas
  ("Evento · ADRIANÓPOLIS", mesmas datas, "Sem solicitante") sem nada que as
  distinga. Pôr `#223` no começo da linha.
- **Cadastros:** `/cadastros/servicos/` ainda tem coluna **"Situação: Ativo"**,
  contra a regra da casa de não haver Ativo/Inativo em cadastro (o que não serve,
  apaga-se). Os cadastros de Viagens já não têm. Falta migrar este.
- O botão flutuante "+ Nova solicitação" cobre o rodapé e a última linha da lista.

**Funciona muito bem:** o painel da viagem. A solicitação #223 estava sem viagem;
"Tentar de novo" gerou a **Viagem #97** na hora, e o painel já listava o que falta,
em português claro: "Faltam 10 servidores (Ascom 2, Demafe 8)", "O prazo para o
ofício sem justificativa terminou em 11/09/2026", "Roteiro #96: informe a sede".
Esse padrão — dizer exatamente o que falta, por área — merece ser repetido em todos
os módulos.

### Coffee Break

- A fila "O que fazer hoje" é o melhor componente de trabalho do sistema: agrupa por
  pendência, diz há quanto tempo está parada e põe a ação na própria linha
  ("Anexar a nota →"). Vale copiar para Eventos Sociais e Palestras.
- Aqui a lista **mostra o número** (33/2026) — é o comportamento certo, que falta em
  Eventos Sociais.
- O quinto cartão de indicador cai sozinho numa segunda fileira. Equilibrar 3+2.
- As três faixas de alerta do topo (estoque baixo, duas certidões vencidas) têm o
  mesmo peso visual, sendo problemas de gravidade diferente.
- O menu ⋮ carrega **oito** ações, com "Excluir" na mesma lista de "Editar" e
  "Duplicar". Separar as destrutivas por um traço, no fim.
- A prévia do documento (folha A4 embutida, com "Campos", "Próximo campo vazio",
  "Faltam 2" e a lista do que impede a emissão) é excelente — mas **não acompanha o
  que está sendo digitado**: preenchi "Local de entrega" e tanto a folha quanto o
  aviso "Informe o local de entrega" continuaram como estavam, porque a folha vem de
  um `iframe` que só recarrega ao salvar. Em Viagens o comportamento é o outro
  (autosave + recarga da folha). Uniformizar.

### Palestras e Eventos

- Painel limpo, mas sem gráfico, enquanto Eventos Sociais e Publicações têm. E
  nenhum cartão em destaque, enquanto os outros destacam um. Os painéis dos seis
  módulos deveriam ter a mesma anatomia.
- Os cadastros aparecem duas vezes: na aba "Cadastros" e como chips no rodapé do
  painel ("Palestrantes | Temas | Respostas padrão").
- Na lista, o primeiro grupo de chips (situação) não tem rótulo, mas o segundo tem
  ("EVENTO"). Rotular os dois.
- Um registro mostrava `10/12/2026 · 13:00 · 10/12 13 as 13:00hs` — o texto cru do
  campo de horário aparece ao lado do valor formatado.
- O seletor de tema abre com mais de 50 opções em três telas de rolagem. Já existe
  um filtro por nome: começar mostrando as 6 mais usadas + "ver todos".

### Publicações e Atendimento à Imprensa

- As duas telas estão bem construídas (barras por jornalista/responsável, unidades
  que mais publicam, tempo médio até publicar).
- Mesmo problema de gráfico sem eixo nem valores.
- Em Imprensa, dois cartões em dourado ao mesmo tempo, um deles sendo prazo vencido
  (ver UX-03).

### Viagens

- **Não tem painel.** `/viagens/` cai direto em Roteiros. É o único módulo sem tela
  de entrada com indicadores — justamente o mais complexo.
- A barra do módulo tem **12 itens** (Viagens, Prestações, Ofícios, Justificativas,
  Termos, Roteiros, Planos, Ordens, Cadastros, Modelos, Configurações, Textos).
  Agrupar os de documento sob um item só.
- **Roteiro (`/viagens/roteiros/95/editar/`) é a tela mais bem resolvida do
  sistema:** mapa com a rota traçada, quatro números de distância/tempo, trechos com
  data e hora, diárias com valor por extenso, "Como foi calculado" e histórico. Duas
  observações pequenas: os quatro indicadores são redundantes (ida e volta é o dobro
  da ida — cabem em dois) e os botões `+`/`−` do tempo são alvos pequenos demais.
- **Roteiros (lista):** 44 registros, quase todos rascunhos vazios ("Sem período · 0
  trechos · Sem diárias calculadas"). Falta um chip "Rascunhos" para tirá-los da
  frente.
- **Prestações:** a linha de cabeçalho de cada ofício imprime os campos vazios como
  travessões — "Ofício — PROTOCOLO — DESTINO MARINGÁ/PR PERÍODO — POR SERVIDOR —".
  Omitir o par quando não há valor. E há campos de formulário editáveis dentro das
  linhas da lista, o que deixa a tela com cara de rascunho.
- **Cadastros de servidores:** todos com "NÃO POSSUI RG" e CPF vazio — dado
  importado que ninguém completou; vale um filtro "incompletos".

### Conta e avisos

- **Alterar senha** é a melhor tela de formulário do sistema: medidor de força,
  requisitos em lista, dica de segurança. Só sobra o número "1" da seção, já que só
  existe uma.
- **Usuários e perfis:** bem resolvida. O chip diz "Todas 7" — deveria ser "Todos".
- **Notificações:** a limpeza semanal manda um aviso que é só zeros ("Removidos 0
  PDF/DOCX; 0 anexo(s); 0 planilha(s)") junto com "134 arquivo(s) órfão(s)" sem
  nenhuma ação oferecida. Quando não há nada a relatar, não mandar o aviso; quando
  há órfãos, oferecer o que fazer.

---

## 4. Por onde começar

Ordenado por (impacto ÷ esforço):

| # | Item | Onde | Esforço |
|---|---|---|---|
| 1 | Dia da semana da agenda (`getUTCDay`) | `static/js/agenda.js` | minutos |
| 2 | Anel de foco de volta | `static/css/ds-v32.css:33` | minutos |
| 3 | Estado vazio dos Anexos | `templates/pages/solicitacoes/form.html:231` | minutos |
| 4 | Páginas 404 e 500 próprias | `templates/`, `config/urls.py` | 1 hora |
| 5 | Número do registro na linha da lista | listagens de Eventos Sociais | 1 hora |
| 6 | Linha da lista clicável | helper de listagem (`core/listagens`) | meio dia |
| 7 | Contraste do cinza de texto | tokens da paleta | meio dia |
| 8 | Métricas da home viram links filtrados | `core/views.py` + template | meio dia |
| 9 | Registro travado vira folha de leitura | formulários | 1 dia |
| 10 | Um só padrão de rótulo | `solicitacoes/form.html` | 1 dia |

E duas coisas de dono do produto, não de código: as **5 migrações pendentes em
produção**, e decidir a escada de gravidade do dourado antes de mexer nas telas —
senão cada correção reabre a discussão.

---

## O que foi testado de fato

- Varredura das 96 rotas GET do projeto com cliente autenticado: nenhum erro 500.
- Login, logout e sessão.
- Agenda: feed de 237 eventos, modal de dossiê, Esc, rótulos de coluna contra
  `data-date`.
- Eventos Sociais: painel, lista, filtros, paginação, solicitação #223, geração da
  Viagem #97.
- Coffee Break: painel, fila de pendências, lista, solicitação 36/2026, documento
  embutido, teste de perda de rascunho.
- Palestras, Publicações, Imprensa: painéis e listas.
- Viagens: roteiros, roteiro #95, viagem #97, ofícios, prestações, cadastros.
- Relatório consolidado, usuários, alterar senha, notificações, textos dos
  documentos.
- Leitura de e-mail colado, de ponta a ponta.
- Contraste medido em texto real, foco de teclado com Tab, nomes acessíveis,
  hierarquia de títulos, imagens sem `alt`.

Nada foi gravado no banco além da **Viagem #97**, que foi o teste pedido. O que
digitei nos formulários de coffee break e de palestra foi descartado sem salvar.
