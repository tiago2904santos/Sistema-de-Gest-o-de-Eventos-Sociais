# Prompt para o Codex — Fase 3 da unificação: núcleo documental (DOCX/PDF)

> Copie tudo abaixo da linha e cole no Codex.

---

## 1. Quem é você nesta tarefa

Você é um desenvolvedor Django sênior trabalhando no repositório **Sistema de Gestão de Eventos Sociais** da Polícia Civil do Paraná (PCPR), em `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos`.

Este repositório é a **base** de uma unificação em andamento: o domínio do **Gerenciador de Viagens** (também chamado Central de Viagens 3, daqui em diante **GV**) está sendo portado para dentro dele, fase a fase, conforme `docs/PLANO_MESTRE_UNIFICACAO.md`. As fases 0, 1 e 2 já foram entregues. **Sua tarefa é a Fase 3 — o núcleo documental**: a máquina que gera arquivos DOCX e PDF a partir de modelos `.docx`.

O código-fonte do GV está disponível **somente para leitura** em:

```
C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens
```

**Nunca grave, edite ou rode nada dentro dessa pasta.** Ela é a fonte que você lê e traduz; todo arquivo novo nasce no repositório de Eventos Sociais.

Regra número um desta fase: **porte, não reinvente.** O GV tem esse núcleo protegido por centenas de testes e anos de uso real com documentos oficiais. Onde o GV resolveu um problema, você copia a solução e adapta ao ambiente daqui. Onde você achar que o GV está errado, escreva a divergência no relatório final em vez de decidir sozinho.

Regra número dois: **nada do que já existe pode quebrar.** Este repositório está em produção.

## 2. Ambiente e comandos

- Django 6.1, Python 3.14, virtualenv em `.venv`. Windows.
- Interpretador: `.venv\Scripts\python.exe` (sempre esse; não use `python` solto).
- Testes: `.venv\Scripts\python.exe manage.py test`
- Servidor: `.venv\Scripts\python.exe manage.py runserver 8021` — **sempre com porta**. Produção roda waitress na 8000 e um `runserver` sem porta atrapalha o sistema real.
- O banco de desenvolvimento é PostgreSQL (`eventos_sociais`, configurado no `.env`) e **tem dados reais importados**. Não rode comandos destrutivos, `flush`, `--limpar`, nem reimportações.
- O GV roda em Django 5.2 / Python 3.12. O código portado tem que rodar em **6.1 / 3.14**: revise cada uso de API depreciada.

### Antes de escrever qualquer linha

1. Rode `.venv\Scripts\python.exe manage.py test` inteiro e **anote o número de testes e o tempo**. Esse número é o seu piso: ao final, nenhum teste pode faltar nem falhar.
2. Rode `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` e confirme que está limpo.
3. Leia, nesta ordem: `docs/PLANO_MESTRE_UNIFICACAO.md` (seções 2 e 5), `docs/AUDITORIA_UNIFICACAO_2026-08.md` (seções 3 e 4) e o `AGENTS.md` do GV.

## 3. O que já está migrado (não refaça)

| Fase | O que entrou | Onde está |
| --- | --- | --- |
| F0 — Fundação | `core.ModeloTemporal` / `core.ModeloCancelavel`, `core/middleware.py::RequisicaoAtualMiddleware`, `auditoria.RegistroAuditoria` (trilha imutável por signals), `core/constraints.py` | `core/`, `auditoria/` |
| F1 — Cadastros de viagens | `Unidade`, `Cargo`, `Combustivel`, `Servidor`, `Viatura`, `TabelaDiaria` (vigenciada), normalização de CPF/placa, módulo `VIAGENS` com os grupos `VIAGENS_GESTOR` e `VIAGENS_OPERADOR`, conversão de `Motorista` em `Servidor` | `viagens_cadastros/` |
| F2 — Roteiros e diárias | `Roteiro`, `RoteiroDestino`, `RoteiroTrecho`, `RoteiroDiariaComponente`, motor de diárias com testes de caracterização ao centavo, editor de roteiro completo, rota por OpenRouteService com mapa | `viagens_roteiros/` |

Também já existem, e você **usa** em vez de recriar: autorização por módulo (`accounts/modulos.py`, decorator `modulo_requerido`), helpers de listagem (`core/listagens.py`), design system V3.2 (`static/css/ds-v32.css` + `ds-v32-bridge.css`, shell `templates/layouts/app_shell_v32.html`).

## 4. O que você vai entregar nesta tarefa

Um app novo, **`documentos`**, que sabe pegar um modelo `.docx`, preencher com dados e devolver DOCX ou PDF, gravando o que foi gerado. Nada de domínio: ofícios, termos e justificativas **não** entram agora — eles são a Fase 4 e vão consumir este núcleo.

Ao final, deve ser possível:

1. `.venv\Scripts\python.exe manage.py documentos_check` diz quais motores de DOCX/PDF o ambiente tem.
2. Uma chamada de serviço gera o DOCX e o PDF dos três modelos portados, a partir de um dicionário de dados.
3. O que foi gerado fica registrado em `DocumentoArtefato` (com hash, snapshot do payload e o arquivo), e pode ser baixado por uma view protegida.
4. Trocar por acidente um `.docx` de modelo faz um teste falhar.

## 5. Decisões já tomadas — não reabra

Estas vêm do plano mestre e do que já foi decidido nas fases anteriores. Se alguma delas se mostrar inviável, **pare e relate**, não decida por conta própria.

1. **App novo `documentos`** na raiz do projeto (irmão de `viagens_cadastros` e `viagens_roteiros`), registrado em `INSTALLED_APPS`.
2. **Sem multi-tenancy.** O GV recorta tudo por `AreaTrabalho` (`AreaScopedManager`, `all_objects`, `default_manager_name`). Aqui **não existe área**: remova o campo `area`, o manager recortado e todo teste que só verifica recorte por área. O controle de acesso deste sistema é `Setor ↔ Modulo` + Groups.
3. **Geração síncrona.** Não porte Celery, Redis, `documentos/tasks.py`, `services/async_generation.py`, `DocumentoGeracao` nem `warm_cache`. A geração acontece dentro da requisição. Se um lote pesar, isso vira decisão futura (risco R3 do plano).
4. **Três tipos documentais nesta fase**: `OFICIO`, `JUSTIFICATIVA`, `TERMO_AUTORIZACAO`. O registro de tipos precisa aceitar novos sem alterar o motor — plano de trabalho, ordem de serviço, relatório técnico e diário de bordo ficam para as fases seguintes (os dois últimos são da F5).
5. **Nada de Google Drive, eProtocolo, links públicos temporários ou assinatura eletrônica por link.** `services/temporary_links.py`, `integracoes/`, `protocolos/` e a versão assinada por token ficam fora. Anexar manualmente um PDF assinado (`arquivo_assinado`) **pode** vir, porque é campo simples e útil.
6. **FKs do artefato**: nesta fase, `DocumentoArtefato` liga-se por FK opcional a `viagens_cadastros.Servidor` e `viagens_roteiros.Roteiro`, mais `criado_por` (`settings.AUTH_USER_MODEL`). As FKs para `Oficio` e `TermoAutorizacao` entram na Fase 4, por migração própria — não invente esses modelos agora nem use `GenericForeignKey`.
7. **Cadeia de motores de PDF** na ordem do GV: Word/COM (Windows) → LibreOffice → WeasyPrint → fallback simples. Cada motor é opcional: a ausência de um não pode quebrar import, `manage.py check` nem a suíte.

## 6. Mapa do porte, arquivo por arquivo

Origem = `Gerenciador de Viagens\documentos\`. Destino = `documentos\` deste repositório.

### 6.1 Serviços (o coração — porte fiel)

| Origem | Destino | Observação |
| --- | --- | --- |
| `services/types.py` | igual | `DocumentoTipo`, `DocumentoFormato`, `DocumentoTipoDefinicao` — mantenha os nomes dos valores |
| `services/exceptions.py` | igual | mantenha os nomes das exceções |
| `services/registry.py` | igual | registro de tipos; deixe só os três tipos desta fase |
| `services/templates.py` | igual | definição de template, chaves obrigatórias |
| `services/resources_paths.py` | igual | resolução do `.docx` em `documentos/resources/` |
| `services/validators.py` | igual | campos obrigatórios por tipo |
| `services/placeholders.py` | igual | leitura dos marcadores do `.docx` |
| `services/formatters.py` | igual | formatação de data, moeda, extenso — **confira o fuso** (ver §8) |
| `services/filenames.py` | igual | nomenclatura dos arquivos |
| `services/renderer.py`, `services/renderers/` | igual | renderizadores DOCX/PDF |
| `services/adapters/docxtpl_render.py` | igual | render docxtpl |
| `services/adapters/word_pdf.py` | igual | motor COM (Windows) |
| `services/adapters/libreoffice_pdf.py` + `services/libreoffice_resolve.py` | igual | motor LibreOffice |
| `services/adapters/weasyprint_pdf.py` | igual | motor WeasyPrint |
| `services/adapters/simple_pdf_fallback.py` | igual | fallback fpdf2 |
| `services/pdf_engine.py` | igual | escolha do motor + mensagem de indisponibilidade |
| `services/environment.py` | igual | relatório de ambiente (alimenta o `documentos_check`) |
| `services/document_cache.py` | igual | cache por fingerprint — mantenha, mas sem Redis (cache padrão do Django) |
| `services/persistence.py` | adaptar | grava o `DocumentoArtefato`: tire `area`, ajuste as FKs conforme §5.6 |
| `services/facade.py` | adaptar | ponto de entrada `DocumentoFacade.gerar(...)`; tire o que depender de área/Celery |
| `services/access.py` | reescrever | ver §6.4 |
| `services/responses.py`, `services/downloads.py`, `services/pdf_streaming.py` | adaptar | resposta HTTP do download; **não** use `X-Accel-Redirect` (aqui é waitress, não nginx) |
| `services/timing.py` | igual | medição por etapa, útil no log |
| `services/pdf_overlay.py` | opcional | carimbo em PDF; só é usado na F5 — porte apenas se sair de graça |

`services/adapters/excel_pdf.py` e `xlsx_render.py` são do diário de bordo (F5): deixe para depois.

### 6.2 Modelo e migrações

`DocumentoArtefato`, portado de `documentos/models.py`, **sem** `area`, **sem** `AreaScopedManager`, **sem** `DocumentoGeracao`. Mantenha: `id` UUID, `tipo`, `formato`, `payload_snapshot` (JSON), `hash_sha256`, `cache_key`, `generator_version`, `engine`, `nome_drive` (renomeie para `nome_exibicao`, já que não há Drive), `arquivo`, `arquivo_assinado`, `assinado_em`, `assinado_nome_original`, `criado_em`. Acrescente `criado_por` e as FKs opcionais do §5.6.

`DocumentoAssinaturaVersao` (versões append-only) **pode** vir, sem a parte de token público.

Uma migração inicial só de esquema. **Migração de dados nunca divide arquivo com migração de esquema** — foi assim que a F1 quebrou em PostgreSQL.

Inclua `"documentos"` em `APPS_AUDITADOS` (`auditoria/signals.py`): documento oficial gerado é exatamente o tipo de coisa que precisa de rastro.

### 6.3 Modelos `.docx` e golden files

Copie de `Gerenciador de Viagens\documentos\resources\` para `documentos/resources/`:

- `oficio.docx`
- `justificativa.docx`
- `termo_autorizacao.docx`

E os golden correspondentes de `documentos\tests\golden\` para `documentos/tests/golden/`. Copie **byte a byte** (binário; nada de abrir e salvar no Word).

Porte `tests/test_golden_templates.py` inteiro: é ele que trava o texto fixo e o conjunto de variáveis de cada documento. Confirme que a instrução de regravar com `ATUALIZAR_GOLDEN=1` continua funcionando e documente-a no topo do arquivo.

### 6.4 Views, URLs e acesso

Uma superfície mínima:

- `GET /documentos/<uuid>/baixar/` — devolve o arquivo efetivo (assinado se houver, senão o gerado), com `Content-Disposition` e o content-type certo.
- `documentos/services/access.py` reescrito para a autorização **deste** sistema: superusuário passa; quem tem o módulo `VIAGENS` (via `accounts.modulos.usuario_tem_modulo`) passa; o resto recebe 403. Anônimo é redirecionado ao login. Espelhe o padrão de `solicitacoes.views.baixar_anexo` (o download nunca é servido direto por `MEDIA_URL`).
- Sem tela nova. Se você achar que precisa de uma, pare e pergunte — telas seguem o Design System V3.2 e isso é escopo da Fase 4.

### 6.5 Comando de diagnóstico

Porte `documentos_check` (com `--json` e `--verbose`). Ele é o gate operacional: em produção, é assim que se descobre que a máquina perdeu o motor de PDF. `documentos_setup_pdf` e `documentos_unoserver_check` **não** vêm (unoserver é da infra do GV).

## 7. Dependências e CI

Acrescente ao `requirements.txt`, com as faixas que o GV usa:

```
python-docx>=1.1,<2.0
docxtpl>=0.20.2,<0.21
docxcompose>=1.4,<2.0
weasyprint>=69.0,<70.0
pypdf>=6.15.0,<7.0
fpdf2>=2.8,<3.0
Pillow>=12.3.0,<13.0
```

`docx2pdf` e `pywin32` são **só Windows**: declare com marcador de ambiente (`; sys_platform == "win32"`) para não quebrar o CI, que roda em Ubuntu.

O CI (`.github/workflows/ci.yml`) roda `check`, `makemigrations --check` e a suíte em PostgreSQL 18 no Ubuntu. Duas consequências:

1. WeasyPrint precisa de bibliotecas de sistema (pango/cairo). Ou você adiciona um passo `apt-get install` antes do `pip install`, ou garante que o import é preguiçoso e os testes que dependem dele são pulados quando indisponível. **Prefira a segunda**, e só adicione o `apt-get` se algum teste realmente precisar gerar PDF no CI.
2. Todo teste de motor tem que ser `skipUnless` do motor presente. A suíte precisa passar numa máquina sem Word, sem LibreOffice e sem WeasyPrint.

## 8. Armadilhas conhecidas deste repositório

Todas já custaram caro aqui. Leia antes de codar.

- **Nunca edite arquivo com acento usando `Set-Content` / `Get-Content` do PowerShell** — corrompe o UTF-8. Heredoc de bash com aspas dentro também já falhou. Use as ferramentas de escrita de arquivo ou um script Python.
- **Rode a suíte em PostgreSQL e em SQLite.** A F1 passou em SQLite e quebrou em PostgreSQL no `migrate` de produção.
- **Data e hora vindas do banco estão em UTC** (`USE_TZ=True`). Todo ponto que formata horário para documento passa por `timezone.localtime`, senão uma saída às 08:00 vira 11:00 no papel assinado. Teste isso com data ciente de fuso.
- **Número e data que o JS lê ou reenvia nunca passam por template localizado**: `{{ valor }}` de um `Decimal` sai "257,88" em pt-br e o próprio `DecimalField` recusa na volta. Datas em ISO, números como string crua.
- **Dinheiro é formatado pela localização do Django**, não por f-string: `R$ 43.58` num sistema que escreve `R$ 43,58` já foi defeito real aqui.
- **`max_length` do modelo valida a entrada crua do formulário**, antes de qualquer normalização.
- **Suíte verde não é tela conferida.** Se você tocar em algo com interface, abra a página no navegador contra o banco de dev antes de dizer que está pronto.

## 9. Testes — o que é obrigatório

A regra do plano é: **testes viajam junto com o código, no mesmo commit.** Porte de `Gerenciador de Viagens\documentos\tests\`, adaptando:

`test_registry.py`, `test_templates.py`, `test_placeholders.py`, `test_validators.py`, `test_formatters.py`, `test_filenames.py`, `test_facade.py`, `test_facade_pdf_single_docx.py`, `test_renderers.py`, `test_pdf_engine.py`, `test_simple_pdf_fallback.py`, `test_libreoffice_resolve.py`, `test_libreoffice_pdf.py`, `test_word_pdf.py`, `test_weasyprint_security.py`, `test_document_cache.py`, `test_cache_de_documento.py`, `test_persistence_snapshot.py`, `test_responses.py`, `test_download_errors.py`, `test_pdf_streaming.py`, `test_environment.py`, `test_documentos_check_command.py`, `test_docxtpl_nested_templates.py`, `test_timing.py`, `test_golden_templates.py`.

**Não** porte: `test_async_generation.py`, `test_recorte_por_area_fatia4.py`, `test_cache_recorte.py`, `test_temporary_links.py`, `test_unoserver_adapter.py`, `test_assinatura_manual.py` (só a parte de token), `test_regressao_oficio_935.py` e `test_pdf_artefato_views.py` (dependem de ofício — vão na F4), `test_documentos_setup_pdf_command.py`.

Escreva também, porque são novos daqui:

1. Download negado a quem não tem o módulo `VIAGENS`; permitido a quem tem; redirecionado quando anônimo.
2. Geração registra `DocumentoArtefato` com hash e snapshot; regerar o mesmo payload reaproveita o cache em vez de duplicar arquivo.
3. `documentos_check` responde sem motor nenhum instalado (não pode estourar exceção).
4. Um documento gerado com data/hora sai com o horário de São Paulo.

## 10. Gates de saída (o trabalho só está pronto quando todos passam)

1. `.venv\Scripts\python.exe manage.py test` — número de testes **maior** que o baseline anotado no início, zero falhas.
2. A mesma suíte verde em SQLite (sem as variáveis `POSTGRES_*`).
3. `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` limpo.
4. `.venv\Scripts\python.exe manage.py check` sem avisos novos.
5. `.venv\Scripts\python.exe manage.py documentos_check` executa e reporta os motores da máquina.
6. Os três tipos geram DOCX **e** PDF de ponta a ponta, com os golden files verdes. Prove: gere os seis arquivos numa pasta temporária e diga no relatório qual motor de PDF foi usado.
7. Nenhum arquivo do repositório do GV foi alterado.

## 11. Como entregar

Trabalhe em commits pequenos e nesta ordem, cada um com a suíte verde:

1. Esqueleto do app + `types`/`exceptions`/`registry`/`templates` + testes desses.
2. Recursos `.docx` + golden files + `test_golden_templates`.
3. Renderização DOCX (docxtpl) + validadores + formatadores + nomenclatura.
4. Cadeia de PDF (os quatro motores, cada um com skip) + `pdf_engine` + `environment` + `documentos_check`.
5. Modelo `DocumentoArtefato` + migração + persistência + cache + auditoria.
6. Façade + view de download + acesso.
7. Dependências, CI e documentação.

Ao final, escreva em `docs/` um relatório curto (no estilo das seções de fase do `PLANO_MESTRE_UNIFICACAO.md`) com: o que entrou, o que ficou de fora e por quê, as divergências que você encontrou em relação ao GV, o que a Fase 4 vai precisar mexer aqui, e o número de testes antes e depois. Atualize também a seção "Fase 3" do plano mestre marcando o que foi entregue.

**Não faça commit nem push sem pedir**, e não altere nada fora do escopo desta fase. Se encontrar um defeito no código existente, anote no relatório em vez de corrigir de passagem.

## 12. Se algo travar

Pare e pergunte, em vez de inventar, quando:

- um serviço do GV depender de `AreaTrabalho`, Celery ou Drive de um jeito que não dá para desmontar sem reescrever a lógica;
- um modelo `.docx` exigir variável que só existe no domínio de ofícios (F4);
- o PDF só sair com uma dependência de sistema que o CI não tem;
- o porte exigir mudar comportamento de algo que já está em produção aqui.
