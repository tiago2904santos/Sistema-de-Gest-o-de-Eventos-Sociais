# Documentos institucionais: nova arquitetura de geração e edição

Registro da análise do estado atual e do plano de implementação da geração de
PDF direta (HTML → PDF), da prévia A4 em tela e do editor documental
controlado, com sincronização bidirecional entre documento e banco.

Data da análise: 16/09/2026.

---

## 1. Estado atual (diagnóstico)

### 1.1 Como o PDF é produzido hoje

O caminho normal é `docxtpl → .docx → conversor externo → PDF`:

1. `DocumentoFacade.gerar` (`documentos/services/facade.py:58`) valida tipo e
   formato, consulta o cache de artefatos e renderiza.
2. Para PDF, `_render_pdf` (`facade.py:236`) primeiro renderiza o **DOCX** com
   docxtpl (`prefer_docx = docxtpl_context is not None`, `facade.py:256`) e
   depois converte pela cadeia de motores de `pdf_engine.py:185`:
   - Windows: `word_com → libreoffice → weasyprint → simple_fallback`
   - `word_com` usa docx2pdf/win32com (abre o Word); `libreoffice` chama o
     `soffice` por subprocesso com timeout de 90 s.
3. Só quando os dois anteriores faltam é que o WeasyPrint entra, renderizando
   os HTML de `templates/documentos/pdf/*.html` — **sem brasão** (o brasão vive
   dentro dos `.docx`, em `word/media/image1.png`) e com CSS mínimo.

Medição em 16/09/2026, ofício nº 900005/2026, máquina de desenvolvimento
(`DocumentoFacade().gerar`, tipo `oficio`):

| Cenário                          | Tempo   |
|----------------------------------|---------|
| PDF, cache frio (Word COM)       | 7,66 s  |
| PDF, cache quente (artefato)     | 0,02 s  |
| Chrome headless, A4 de 1 página  | 0,9–1,1 s por processo |

O tempo frio é dominado pela abertura do Word (a conversão em si leva ~1,8 s).

### 1.2 O que já existe e deve ser reaproveitado

- **Façade, registro, cache e persistência** (`documentos/services/`): a
  `DocumentoFacade` já resolve motor, valida, persiste `DocumentoArtefato` com
  `payload_snapshot`, `hash_sha256`, `cache_key`, `engine`, e devolve o artefato
  em cache quando a chave não mudou (`document_cache.py`). A chave já inclui
  a assinatura dos templates e a versão do gerador.
- **Payload canônico** do ofício: `build_canonical_document_payload`
  (`viagens_oficios/documents.py:146`) → `{institucional, oficio, justificativa}`,
  já pensado para HTML (o `oficio.html` atual o consome). O contexto plano do
  DOCX é outro (`docxtpl_context.py`), com as regras de texto do documento:
  `_orgao_destino`, `_custeio_text`, `_motorista_formatado`, `_route_columns`,
  `_diarias`, assinatura e rodapé.
- **Regras de emissão**: `validar_oficio_para_documento` (`services.py:184`),
  `resolver_assunto_oficio` (`assunto_oficio.py:50`), `reservar_numero_oficio`,
  promoção `RASCUNHO → GERADO` em `document_generation.py:11`.
- **Auditoria**: app `auditoria` com `RegistroAuditoria` imutável e delta campo a
  campo gravado por signals (`auditoria/signals.py`), já cobrindo
  `viagens_oficios`, `viagens_termos` e `documentos`. A tela do ofício já mostra
  os últimos 20 registros (`views.py:174`).
- **Componentes globais de formulário**: `components/select.html`,
  `input.html` (data), `date_range.html`, `textarea.html`,
  `v32/multi_pick.html`, `v32/lista_escolha.html`, todos religáveis em
  conteúdo dinâmico por `DS.aprimorar(raiz)` (`app.js:1036`).
- **Padrões de endpoint JSON**: `viagens_roteiros/views.py` (previa, rota,
  autosave) e `viagens-prestacoes.js` (JSON + `X-CSRFToken`).
- **Streaming de PDF inline** com Range: `documentos/services/pdf_streaming.py`.
- **Testes**: 28 arquivos em `documentos/tests/` (golden dos `.docx`, motores,
  cache, permissões de download), mais os `test_docxtpl_*` do ofício.

### 1.3 O que falta ou está errado para o objetivo

- **WeasyPrint não importa nesta máquina**: `OSError: cannot load library
  'libgobject-2.0-0'`. Não há runtime GTK instalado (nem em `Program Files`
  nem em MSYS2). Produção também é Windows (waitress). Sem GTK, o "motor
  preferencial" do pedido não roda.
- Os HTML de PDF atuais não têm brasão, fontes nem cabeçalho/rodapé
  institucionais; são um esqueleto de fallback.
- Não existe prévia HTML do ofício; só a do termo (`viagens_termos/preview.html`),
  somente leitura.
- Não existe campo de versão nem lock otimista nos models; há `atualizado_em`
  (`core/models.py:10`).
- `RegistroAuditoria` não distingue a origem da alteração (formulário, editor,
  sistema).
- Não existe armazenamento para conteúdo documental (parágrafos do documento
  que não são campo de model) nem para overrides.
- Código morto/paralelo: `documentos/services/renderer.py`, a camada
  `services/renderers/` (só testes a usam), `converter_docx_pronto_para_pdf`
  sem chamador, templates registrados que não existem
  (`relatorio_tecnico.html`, `diario_bordo.html`).
- Ordem de Serviço, Plano de Trabalho e documento de Roteiro **não existem**
  no código; só menções.

---

## 2. Decisões arquiteturais

### D1. Motor de PDF: HTML/CSS direto, sem DOCX no caminho

O PDF passa a ser renderizado a partir do template HTML institucional, em
memória, nunca via DOCX. A geração de DOCX continua existindo como renderizador
irmão (docxtpl), separado (item 21 do pedido).

**Sobre o motor**, a escolha depende de infraestrutura e precisa de decisão:

| Opção | Prós | Contras |
|---|---|---|
| **A. WeasyPrint** (preferência do pedido) | pure-Python, `@page`, cabeçalho/rodapé por CSS paginado, sem processo externo, ~0,2–0,5 s | exige instalar o **runtime GTK3** no desenvolvimento e na produção (instalador `gtk3-runtime` ou MSYS2, ~30 MB, acesso administrativo); fidelidade editor≈PDF depende de manter o CSS dentro do que o WeasyPrint suporta |
| **B. Chrome headless** (`--print-to-pdf`) | já instalado; **mesmo motor do navegador do editor**, fidelidade máxima editor↔PDF; sem GTK | ~1 s por PDF ao abrir um processo por chamada (dá para ir a ~0,1–0,2 s mantendo um Chrome residente via DevTools Protocol, mais complexidade); dependência do Chrome no servidor |

Recomendação: **A** se puder instalar o GTK nos dois ambientes (é a arquitetura
pedida e a mais simples de operar). **B** como plano de contingência se a
instalação não for possível. A camada `pdf_renderer.py` abstrai o motor, então a
troca entre A e B não muda o resto do sistema. Em ambos os casos, Word COM e
LibreOffice saem do caminho crítico do PDF (permanecem disponíveis só para os
tipos ainda não migrados, atrás da cadeia existente).

### D2. Um template, dois modos

O mesmo template HTML (`documentos/pdf/oficio.html`, estendendo
`base_institucional.html`) renderiza a prévia A4 na tela e o PDF. A diferença
é um `modo` no contexto: no modo `editor` os trechos editáveis recebem
marcação (`data-doc-campo`, `data-doc-bloco`); no modo `pdf` não. O CSS se
divide em três camadas: `documento.css` (tipografia, blocos, tabelas — comum),
`documento-impressao.css` (`@page`, quebras, cabeçalho/rodapé repetidos) e
`documento-editor.css` (a folha A4 na tela, marcações de editável/protegido).

### D3. Fonte de verdade: o model; o documento só guarda o que é dele

- **Dados estruturados** (motivo, protocolo, data, custeio, servidores,
  viatura, motorista, roteiro...) continuam nos models. O editor grava neles,
  pelo mesmo caminho de validação do formulário.
- **Conteúdo documental** (parágrafos fixos do modelo, frases calculadas que o
  usuário pode reescrever, quebras de página) vai para `DocumentoBloco`, com
  original, atual, override e autoria.
- Nunca haverá `Oficio.motivo` e `Documento.motivo` independentes.

### D4. Registro explícito de campos editáveis

`documentos/editor/campos.py` declara, por tipo de documento, quais campos
podem ser editados pelo editor, com: caminho no model, componente de edição,
regra de validação (o próprio `Field` do `ModelForm` existente), e condição de
estado (ex.: nada é editável em ofício cancelado; número/ano nunca). A API
recusa qualquer campo fora do registro. Nada de `setattr` genérico.

### D5. Validação e permissão reutilizadas, não copiadas

Cada `PATCH` de campo: limpa o valor com o `Field` correspondente de
`OficioForm`, atribui na instância, roda `full_clean` do model e o `clean()`
de negócio do form (as regras de motorista/viatura/custeio), grava com
`update_fields`, e reavalia `validar_oficio_para_documento` para devolver as
pendências à tela. Permissão: `acesso_ao_modulo` + `pode_editar_cadastros`
(a mesma porta do formulário). CSRF pelo header `X-CSRFToken`.

### D6. Histórico pela trilha existente

`RegistroAuditoria` já grava o delta de cada `save`. Acrescenta-se o campo
`origem` (`formulario | editor | sistema`), preenchido a partir de um marcador
que o endpoint do editor coloca na requisição corrente (mesmo mecanismo do
`obter_requisicao_atual` que os signals já usam). Regenerações de PDF entram
como `sistema`. A tela de histórico do ofício passa a mostrar a origem.

### D7. Concorrência por versão de leitura

O editor recebe, ao abrir, `atualizado_em` do ofício e de cada bloco e devolve
esse carimbo em cada `PATCH`. Se o registro mudou desde então, o backend
responde 409 com o valor atual, e o editor mostra "alterado por outro usuário"
com opção de recarregar. Proporcional ao sistema: sem campo novo no `Oficio`.

### D8. PDF sob demanda, com cache por versão

O PDF **não** é regenerado a cada salvamento. A prévia em tela é HTML (barata,
regenerada a cada alteração). O PDF é produzido quando pedido (visualizar/baixar)
e guardado como `DocumentoArtefato` com `cache_key` derivada de:
`tipo + pk + atualizado_em do ofício + máximo atualizado_em dos blocos +
versão do gerador + assinatura dos templates`. Qualquer alteração muda a chave
e invalida; sem alteração, devolve em ~0,02 s (já medido no cache atual).

---

## 3. Modelagem

### `documentos.DocumentoBloco` (novo)

| Campo | Tipo | Observação |
|---|---|---|
| `tipo_documento` | Char(64) | `oficio`, `termo_autorizacao`... (mesmo vocabulário de `DocumentoTipo`) |
| `oficio` / `termo` / `prestacao` | FK nulas | mesmo padrão de vínculo explícito de `DocumentoArtefato` |
| `chave` | Char(64) | identificador estável do bloco no template (`declaracao_cartao`, `quebra_apos_roteiro`) |
| `tipo` | Char(16) | `paragrafo` \| `quebra_pagina` |
| `ordem` | PositiveInteger | posição relativa quando o template permite reordenar |
| `conteudo_original` | Text | o que o sistema calculou na última regeneração |
| `conteudo_atual` | Text | o que vale; igual ao original quando não há override |
| `editado_manualmente` | Bool | override em vigor |
| `editado_por` / `editado_em` | FK user / DateTime | autoria do override |
| `criado_em` / `atualizado_em` | | carimbo para concorrência |
| unique | `(tipo_documento, oficio, chave)` etc. | um bloco por chave e documento |

Regra: ao regenerar, o sistema recalcula `conteudo_original`; se
`editado_manualmente`, mantém `conteudo_atual` e sinaliza na tela que o
original mudou (com "restaurar automático"). Conteúdo é texto simples com
quebras de linha; nunca HTML do usuário (escapado na renderização).

### `auditoria.RegistroAuditoria.origem` (novo campo)

Char(16), choices `formulario`, `editor`, `sistema`, default `formulario`.
Migração pequena; registros antigos ficam como `formulario`.

---

## 4. Organização do código

```
documentos/
  services/
    pdf_renderer.py        # HTML+CSS → PDF em memória; abstrai o motor (WeasyPrint | Chrome)
    document_context.py    # contexto único por tipo (payload canônico + textos documentais + blocos)
    document_blocks.py     # leitura/gravação de DocumentoBloco, overrides, restaurar
    document_versioning.py # chave de versão (carimbos) e invalidação do cache
  editor/
    campos.py              # registro de campos editáveis por tipo (D4)
    api.py                 # views JSON: PATCH campo, POST bloco, GET html/pdf
    urls.py
templates/documentos/pdf/
  base_institucional.html  # A4, brasão, cabeçalho, rodapé, assinatura, paginação
  oficio.html              # só o conteúdo do ofício
  (termo_autorizacao.html, justificativa.html… migram depois)
static/css/documento.css, documento-impressao.css, documento-editor.css
static/js/documento-editor.js
templates/pages/viagens_oficios/documento.html   # a tela do editor (folha A4 + toolbar)
```

A `DocumentoFacade` continua sendo a porta de entrada: ganha um motor
`html_pdf` (via `pdf_renderer.py`) que, para os tipos migrados, é o único da
cadeia; os demais tipos seguem na cadeia antiga até migrarem.

---

## 5. Editor: comportamento

- Rota `viagens_oficios:documento` (`/oficios/<pk>/documento/`).
- Folha A4 renderizada pelo servidor (mesmo template do PDF, modo `editor`).
- Trechos editáveis marcados com `data-doc-campo="motivo"` (ou
  `data-doc-bloco="declaracao_cartao"`), com ícone de lápis discreto ao passar
  o mouse; protegidos sem marcação e com cursor padrão.
- Clique abre o componente certo, ancorado ao trecho: texto → `textarea`;
  data → `input.html` tipo `date`; servidores → `multi_pick.html`; viatura →
  `lista_escolha.html`; custeio/status → `select.html`. Todos religados por
  `DS.aprimorar`.
- Salvar: ao sair do campo, `Ctrl+Enter` ou botão; `PATCH` JSON com
  `{campo, valor, versao}`. Resposta traz o HTML da folha regenerado (troca
  em bloco, mantendo a rolagem) e as pendências de emissão atualizadas.
- Quebra de página: elemento controlado (`DocumentoBloco` tipo
  `quebra_pagina`) inserido/removido pela toolbar entre blocos permitidos.
- Toolbar: zoom, página, mostrar editáveis, histórico, baixar PDF, voltar ao
  formulário. Sem desfazer/refazer na primeira versão (o histórico com
  "restaurar" cobre o caso).

---

## 6. Ordem de implementação (prova de conceito no Ofício)

1. **Preparação** — branch própria; commit do trabalho pendente de design.
2. **Motor** — `pdf_renderer.py` com o motor escolhido; `base_institucional.html`
   com brasão (extraído dos `.docx` para `static/img/brasao-pcpr.png`),
   cabeçalho, rodapé, assinatura e `@page`; teste de PDF válido, multipágina,
   acentos, tabela, imagem.
3. **Contexto único** — `document_context.py` para o ofício, reaproveitando
   `build_canonical_document_payload` e as regras de texto de
   `docxtpl_context.py` (extraídas para funções sem dependência do docxtpl).
   Golden test do HTML do ofício.
4. **Façade** — motor `html_pdf` para `oficio`; chave de cache por versão;
   `gerar_documento` passa a usar o novo caminho; medir tempo.
5. **Prévia A4** — tela `documento.html` somente leitura; fidelidade
   conferida contra o PDF.
6. **Campos inline** — registro `campos.py`, `PATCH`, componentes; motivo,
   data, protocolo, custeio, servidores, viatura, motorista, roteiro.
7. **Blocos e overrides** — `DocumentoBloco`, migração, restaurar, quebra de
   página.
8. **Histórico e concorrência** — `origem` na auditoria, 409 por versão, tela
   de histórico com origem.
9. **Validação final** — testes dos itens do pedido (sincronização nos dois
   sentidos, validação, permissão, PDF, override, performance) e registro das
   medições neste documento.
10. **Expansão** — termo de autorização e justificativa pelo mesmo motor;
    DOCX permanece por docxtpl.

Cada passo é um commit; testes rodam por app tocado em cada passo, e a suíte
inteira ao fim do bloco.

---

## 7. Riscos e limitações conhecidas

- **GTK no Windows** é o risco de infraestrutura número um (D1).
- **Golden tests dos `.docx`** continuam valendo para o DOCX; o PDF ganha os
  seus próprios (texto extraído com pypdf).
- **Cabeçalho/rodapé repetidos por página** são triviais no WeasyPrint
  (`@page` + `position: running()`) e limitados no Chrome headless (só via
  `--print-to-pdf` com cabeçalho nativo desligado e repetição por CSS
  `position: fixed`, que funciona mas com menos controle).
- **Fontes**: o sistema usa fontes do sistema (Segoe UI / Arial). Para o PDF
  ser igual em qualquer servidor, embarcar uma fonte livre (ex.: Liberation
  Sans, métrica compatível com Arial) em `static/fonts/` e usá-la nos dois
  modos.
- **Documentos inexistentes** (Ordem de Serviço, Plano de Trabalho, Roteiro)
  não entram nesta fase; o motor fica pronto para recebê-los.

---

## 8. Estado da implementação (16/09/2026, branch `feature/documentos-editor`)

Passos 1 a 8 da ordem acima estão feitos para o Ofício. O que foi decidido
na prática e difere (ou detalha) o plano:

### 8.1 O que existe

| Peça | Onde |
|---|---|
| Folha institucional + ofício em HTML | `templates/documentos/pdf/base_institucional.html`, `oficio.html`, `documento.css`, `documento-impressao.css`, `documento-editor.css` |
| Contexto único (payload + textos + blocos) | `documentos/services/document_context.py` |
| Motor HTML → PDF (WeasyPrint, memória) | `documentos/services/pdf_renderer.py`; encaixe em `DocumentoFacade._render_pdf_html` |
| Prévia A4 na tela | `viagens_oficios:documento` (página) e `viagens_oficios:documento_folha` (a folha, num iframe da mesma origem) |
| Registro de campos editáveis | `documentos/editor/campos.py` (data, protocolo, motivo, custeio+observação, viajantes, porte de arma) |
| Ponte com o domínio | `documentos/editor/vinculos.py` (`VinculoOficio`: carregar, permissão, form, versão, opções, gravar) |
| API do editor | `documentos/editor/api.py` — `campos/<chave>/` GET/PATCH, `blocos/<chave>/` GET/PATCH/DELETE, `quebras/<chave>/` PATCH |
| Blocos e pontos de quebra | `documentos/editor/blocos.py` (registro), `documentos/services/document_blocks.py`, model `DocumentoBloco` |
| Origem na auditoria | `RegistroAuditoria.origem` + `request.auditoria_origem` lido pelos signals |
| Histórico do ofício | `viagens_oficios.views.historico_do_oficio`: ofício + blocos dele, com origem e campos alterados |
| Editor na tela | `static/js/documento-editor.js`, painel `templates/documentos/editor/campo.html` e `bloco.html` |

### 8.2 Decisões tomadas durante a implementação

- **Folha em iframe da mesma origem.** O CSS do shell (resets, tabelas,
  parágrafos) não alcança o documento; o HTML da folha é o mesmo que vai ao
  WeasyPrint, com `documento-editor.css` inline por cima. A página em volta
  (cabeçalho, ações, painel de edição) usa os componentes globais normalmente.
- **Cabeçalho e rodapé nas faixas das margens.** Na tela ocupam 4,6 cm em
  cima e 3,3 cm embaixo, centralizados — a mesma regra dos `@top-center` e
  `@bottom-center` da folha de impressão. A folha é contínua na tela (um
  documento longo cresce; o PDF pagina).
- **Gravação parcial, validação inteira.** O PATCH monta o `OficioForm`
  com o ofício inteiro e o valor novo, roda `is_valid()` (regras de `clean()`
  incluídas), mas persiste só o campo pedido e os derivados declarados no
  vínculo (`servidores` → `servidores_termo_autorizacao`,
  `diarias_quantidade_servidores`). Erro em campo que não é o pedido
  (dado antigo que a regra de hoje rejeita) volta como aviso, não bloqueia.
  Erro no campo pedido é 400 com a mensagem do formulário.
- **Texto padrão dos blocos vive em Python**, não no template
  (`documentos/editor/blocos.py`). Assim a API sabe o original sem renderizar,
  e `conteudo_original` do bloco é sempre o texto do registro.
- **Quebra de página só em ponto registrado.** O template declara
  `{% ponto_de_quebra "chave" %}` onde admite quebra; a quebra é um
  `DocumentoBloco` do tipo `quebra_pagina` para essa chave. Chave fora do
  registro é 404.
- **Override entra no payload** (`payload["documento"]`), logo na chave de
  cache e no `payload_snapshot` do artefato. O DOCX (docxtpl) não conhece
  overrides — sai com o texto do modelo.
- **Contingência sem GTK.** Sem o runtime nativo do WeasyPrint,
  `render_pdf` levanta `DocumentRendererUnavailable`. Em produção é erro;
  em desenvolvimento (`DOCUMENTOS_PDF_HTML_FALLBACK_DOCX`, padrão `DEBUG`)
  a façade avisa e cai na cadeia antiga. Os testes da cadeia antiga desligam
  o caminho novo com `override_settings(DOCUMENTOS_PDF_HTML_NATIVO=())`.
- **Painel ao lado da folha, não contenteditable.** Clicar num trecho
  marcado abre o painel do campo com o componente global do tipo; texto
  grava com espera de digitação (900 ms), escolhas gravam na hora; a folha
  recarrega depois de cada gravação e o campo continua aberto. 409 pede
  recarga; erros aparecem no lugar sem redesenhar o painel.

### 8.3 Medições (máquina de desenvolvimento, ofício de uma página)

| Etapa | Mediana |
|---|---|
| PDF pela cadeia antiga (Word COM), frio | 7,66 s |
| PDF pela cadeia antiga, em cache | 0,02 s |
| Chrome headless `--print-to-pdf` (referência) | 0,9–1,1 s |
| Contexto do ofício (payload + textos + blocos) | 27 ms |
| HTML do documento (template já compilado) | 0,2 ms |
| Folha do editor (contexto + HTML, modo editor) | 28 ms |
| PDF pelo WeasyPrint | **não medido** — runtime GTK ausente nesta máquina |

Os testes `PdfRealTests` ficam atrás de `skipUnless(weasyprint_disponivel())`
e rodam assim que o GTK3 estiver instalado (`python -c "import weasyprint"`).

### 8.4 Pendências

- Instalar o runtime GTK3 (Windows) e medir o WeasyPrint; conferir a
  paginação real contra a prévia.
- Campos compostos ainda fora do registro: `roteiro`, `transporte`
  (viatura/placa manual), `motorista` — marcados no template, sem painel.
- O aviso de pendências acima da folha não se atualiza depois de uma
  gravação pelo editor (só ao recarregar a página).
- Migrar termo de autorização e justificativa para o mesmo caminho
  (template HTML + registro de campos e blocos); prestação de contas depois.
- Regeneração: quando o texto padrão de um bloco mudar no registro, avisar
  na tela que o original mudou (o `conteudo_original` gravado permite).
