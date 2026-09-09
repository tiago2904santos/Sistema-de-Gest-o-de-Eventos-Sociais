# Fase 3 — Núcleo documental

Porte do GV para Eventos Sociais, em 09/09/2026. Implementação síncrona no app
`documentos`, sem modelos de domínio da F4 e sem alterações nas telas existentes.

## Entregue

- Registry extensível com `oficio`, `justificativa` e `termo_autorizacao`; contratos,
  validação, placeholders, nomenclatura, renderizadores e formatadores portados.
- DOCX por docxtpl; PDF automático na sequência Word/COM → LibreOffice →
  WeasyPrint → fpdf2. Imports opcionais protegidos, cache de sondas e conversão
  pelo cache padrão do Django. WeasyPrint mantém os HTML/CSS da origem.
- `DocumentoArtefato`: UUID, hash SHA-256, snapshot JSON, metadados do gerador,
  arquivo, assinatura manual e FKs opcionais para servidor, roteiro e usuário.
  Migração inicial exclusivamente de esquema; app incluído na auditoria.
- `DocumentoAssinaturaVersao` e serviços de anexação/revogação portados, com as
  proteções de imutabilidade da origem. Nenhuma rota de upload ou token público.
- `DocumentoFacade.gerar()` persiste por padrão e reutiliza o artefato pelo
  fingerprint. Resultado inclui `artefato_id`, `cache_hit` e `pdf_engine_used`.
  O cache diferencia as FKs opcionais e o criador, inclusive valores nulos.
- `GET /documentos/<uuid>/baixar/`: login, módulo VIAGENS ou superusuário;
  versão assinada preferida, MIME/extensão corretos, `no-store`, FileResponse.
  Não há rota pública de mídia nem X-Accel-Redirect.
- Os três DOCX e seus golden textuais são cópias binárias do GV. Um manifesto
  SHA-256 adicional também detecta trocas de imagens, cabeçalhos ou formatação.
  O modo `ATUALIZAR_GOLDEN=1` foi exercitado e está documentado no teste.
- `documentos_check`, com `--json`, `--verbose` e códigos de saída do GV:
  0 = DOCX/PDF disponíveis, 1 = PDF indisponível, 2 = DOCX indisponível.
  Avisos impressos por bibliotecas vão para stderr para preservar o JSON.
- Dependências com marcadores de Windows; CI mantém PostgreSQL 18 e acrescenta
  uma execução da suíte em SQLite. Motores nativos não exigem instalação apt.

## Adaptações e divergências

- Removidos tenancy, recortes e referências de domínio ausentes. `nome_drive`
  virou `nome_exibicao`. Persistência e cache, coordenados fora da façade no GV,
  foram conectados ao ponto de entrada síncrono desta fase.
- **Exceção autorizada pelo usuário:** `pywin32>=311,<313`. A faixa do GV,
  `>=306,<308`, não tem distribuição para Python 3.14; o pip recusou a instalação.
- Datas cientes de fuso passam por `timezone.localtime` antes de aparecerem no
  DOCX, no fallback e no nome do arquivo. Moeda usa a localização do Django,
  conservando a grafia do GV (`R$43,58`). Snapshot conserva ISO/Decimal sem perda.
- Removidas dependências de `core.errors`/`core.metrics` da origem; erros e tempos
  usam logging daqui. O helper de erro de download recebe a URL de retorno do
  chamador em vez de depender do wizard de ofícios.
- Os testes foram portados com exclusão apenas das partes de tipos futuros,
  XLSX, warm cache e unoserver, além das exclusões expressamente pedidas.

**Limitações encontradas no GV, conservadas para decisão posterior:**

- WeasyPrint renderiza HTML; fpdf2 produz texto simplificado, transliterado para
  ASCII, sem reproduzir o layout institucional. Apenas Word/LibreOffice convertem
  o DOCX. **Corrigido na revisão** (ver adiante): o fallback simples deixou de vir
  ligado por padrão em produção.
- ~~O fingerprint de HTML concatena `BASE_DIR/template_path`~~ — **corrigido na
  revisão**: o caminho passa pelo carregador de templates e a edição do modelo
  volta a invalidar o cache. CSS e DOCX já participavam; mudar
  `DOCUMENTOS_GENERATOR_VERSION` continua invalidando tudo.
- O cache de artefatos não serializa duas gerações simultâneas do mesmo conteúdo;
  repetição sequencial é deduplicada, concorrência ainda pode duplicar arquivos.
- A imutabilidade das assinaturas é implementada em `save/delete`, sem proteção
  contra operações em lote pelo ORM/SQL. Revogações de assinaturas sucessivas
  seguem a seleção de versões vigente na origem.
- O adaptador docxtpl conserva a política de escape XML da origem. A F4 deve
  validar os contextos de domínio, inclusive conteúdo com caracteres de marcação.

## Integração da F4 e operação

O chamador fornece `payload` canônico (`institucional`, `oficio` e, conforme o
tipo, `justificativa`/`termo`) e `docxtpl_context` com as variáveis planas dos
modelos reais. São dicionários: nenhum modelo de ofício é necessário na F3.
Exemplo de chamada:

```python
doc = DocumentoFacade().gerar(
    tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF,
    payload=payload, docxtpl_context=contexto,
    reference="123-2026", criado_por=request.user,
    servidor_id=servidor.pk, roteiro_id=roteiro.pk,
)
url = reverse("documentos:baixar", args=[doc.artefato_id])
```

A F4 deve construir esses contextos, validar as pendências de domínio, acrescentar
as FKs de Ofício/Termo em migração própria e incorporá-las à persistência e ao
recorte do cache. As telas ficam para essa fase. `persistir=False` permite render
isolado sem gravação; o fluxo oficial usa o padrão persistente.

Configuração: `DOCUMENTOS_DEFAULT_PDF_ENGINE` (padrão `auto`),
`DOCUMENTOS_LIBREOFFICE_BINARY`, `DOCUMENTOS_SIMPLE_PDF_FALLBACK` (padrão: ligado
só com `DEBUG`; desligado em produção), `DOCUMENTOS_PDF_AUTO_FALLBACK` (padrão
`0`, para motor explicitamente escolhido).
A migração de produção ainda deve ser aplicada pelo fluxo normal de implantação;
nenhuma migração ou geração desta validação gravou no banco de desenvolvimento.

Ficaram fora: Celery/Redis, DocumentoGeracao, Drive, protocolos, links públicos,
assinatura por token, unoserver, XLSX, overlay e documentos das fases seguintes.

## Evidências

- Baseline PostgreSQL: **509 testes, 182,620 s, zero falhas**.
- Pós-porte PostgreSQL: **645 testes, 226,226 s, zero falhas, quatro skips**
  (integração e três testes de segurança do WeasyPrint, sem bibliotecas nativas).
- Pós-porte SQLite, sem variáveis `POSTGRES_*` e sem carregar `.env`: **645 testes,
  214,672 s, zero falhas e os mesmos quatro skips**. Log: `logs/fase3_sqlite.log`.
  Foram acrescentados **136 testes** aos 509 preexistentes.
- `check` sem problemas; `makemigrations --check --dry-run` limpo.
- Bootstrap e `check` verificados com imports dos motores documentais bloqueados.
- `documentos_check` detectou Word/COM e LibreOffice; WeasyPrint sem bibliotecas
  nativas. fpdf2 disponível e habilitado pela configuração nova.
- Prova reproduzível: `.venv\Scripts\python.exe scripts/documentos/verificar_fase3.py`.
  Usa SQLite em memória e mídia temporária sob `logs/`, sem conectar ao PostgreSQL.
  Os seis arquivos desta execução estão em `logs/fase3__kgrlmr7/`; manifesto registra
  hashes, UUIDs e cache hits. Os três PDFs usaram **word_com**, uma página cada.
- Durante testes reais do Word houve diagnóstico nativo RPC `0x800706be`, sem
  falha do teste ou do PDF. A prova subsequente dos três tipos concluiu normalmente.
- Os 141 arquivos de `documentos/` e `templates/documentos/` do GV mantiveram o
  mesmo hash agregado antes/depois:
  `601fc121c286c31c39d858737fe24088c3f2b905e0ad9402c5ac42b75dc40574`.
  Nenhum comando foi executado com diretório de trabalho no GV.
- Alterações preexistentes em cadastros, solicitações e interface preservadas.
  Etapas validadas incrementalmente; nenhum commit ou push foi feito.

## Revisão da fase (09/09/2026)

Revisão independente do porte, com os gates reexecutados em vez de aceitos pelo
relatório. Confirmados: os três DOCX, os três golden e os três HTML têm hash
idêntico ao da origem; o repositório do GV não foi tocado; `documentos` não tem
migração pendente; os 136 testes do app passam com quatro skips justificados; a
execução em SQLite realmente cai em SQLite; e o roteiro de prova reproduz os seis
documentos. Três ajustes foram aplicados sobre o que foi entregue.

1. **Fallback simples de PDF desligado em produção.** Vinha ligado por padrão,
   inclusive fora de desenvolvimento: se Word e LibreOffice falhassem, o sistema
   entregava em silêncio um PDF de texto transliterado no lugar do documento
   oficial. A origem mantém esse recurso restrito ao ambiente de desenvolvimento.
   Agora o padrão acompanha `DEBUG`, e `DOCUMENTOS_SIMPLE_PDF_FALLBACK=1` liga de
   forma consciente. Nenhum teste dependia do padrão anterior; o teste de motores
   passou a declarar a própria precondição.
2. **A impressão digital do modelo HTML voltou a enxergar o arquivo.** O nome
   registrado é relativo ao motor de templates e era concatenado com o
   `BASE_DIR`, o que dava um caminho inexistente: editar o modelo do PDF não
   invalidava o artefato em cache. O caminho passa pelo carregador de templates,
   com teste de regressão que falha se a assinatura voltar a apontar para o vazio.
3. **A trilha de auditoria deixou de copiar o payload do documento.**
   `payload_snapshot` entrou em `CAMPOS_SENSIVEIS`: o conteúdo já vive no
   artefato e, repetido na trilha, multiplicaria dado pessoal (nome, CPF,
   lotação) sem acrescentar rastro. Quem gerou, quando e qual artefato continuam
   registrados, com teste que fixa esse contrato.

Achados menores, deixados como estão por serem menores que o risco de ampliar o
escopo da revisão: o acesso ao download usa a palavra `VIAGENS` escrita à mão em
vez da constante do módulo; formato desconhecido no artefato produz erro 500 em
vez de 404; e o arquivo é gravado dentro da criação do registro, então transação
revertida pelo chamador deixa arquivo órfão em disco — isso passa a importar na
F5, onde a prestação grava anexos dentro de transações.

Suíte completa após os ajustes: **737 testes, zero falhas, quatro skips**.
