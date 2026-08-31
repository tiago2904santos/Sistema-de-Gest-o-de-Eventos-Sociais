# Plano Mestre da Unificação — Opção A (Eventos como base)

**Data:** 31/08/2026 · **Decisão D1 ratificada pelo usuário:** o **Sistema de Gestão de Eventos Sociais é a base** da unificação; o domínio do Gerenciador de Viagens (Central de Viagens 3) é portado para dentro dele.
**Escopo ratificado:** **núcleo essencial + prestações de contas** — cadastros de viagens, roteiros/diárias, núcleo documental DOCX/PDF, ofícios (com justificativas e termos) e prestações de contas.
**Documento-irmão:** [`AUDITORIA_UNIFICACAO_2026-08.md`](AUDITORIA_UNIFICACAO_2026-08.md) — inventários completos dos dois sistemas, ER e matriz de equivalência. Este plano **substitui** o roadmap da auditoria (que assumia a Opção B) no que divergirem.

---

## 1. Consequências da escolha da base A

O que muda em relação ao plano da auditoria (que recomendava a base B):

| Tema | Resolução sob a base A |
|---|---|
| **Plataforma** | Django 6.1 / Python 3.14 / PostgreSQL, design system institucional do A (grafite/dourado, Lucide), Django Templates puros. O código do B é portado **para** este padrão (5.2→6.1 na chegada, Cotton→componentes do A) |
| **Usuário** | `accounts.User` customizado do A permanece (`deve_trocar_senha`, `setores`). Usuários do B migram para ele — hash PBKDF2 compatível, sem reset de senha |
| **Tenancy** | O sistema unificado é **single-tenant** (padrão do A). A `AreaTrabalho` do B não é portada; o acesso ao domínio de viagens é controlado pelo mecanismo existente do A (**Setor ↔ Modulo**, novo módulo `VIAGENS`). Na migração de dados, importa-se a(s) área(s) relevante(s) do B; `area` some das tabelas portadas |
| **Perfis** | Groups do A. Novos grupos do domínio de viagens definidos na F1 (proposta: reutilizar ADMINISTRADOR para cadastros; papéis finos do B — ADMIN/EDITOR/LEITOR por área — colapsam no par módulo+grupo) |
| **Geografia** | `cadastros.Municipio` do A permanece e é **enriquecido** com os campos do `Cidade` do B (`capital`, `latitude`, `longitude`); a base do B (IBGE) complementa a carga. `Regiao` operacional do A vira também a `faixa` da tabela de diárias (mesmo trio Capital/Interior/Brasília) |
| **Pessoas** | `Servidor` do B é portado (F1) e passa a ser a entidade-pessoa. `Motorista` do A é **descontinuado**: dados migram para `Servidor` (cargo "MOTORISTA") e `SolicitacaoEvento.motorista` é re-apontado por migração. A regra do B ("motorista é um Servidor") vence porque elimina cadastro duplicado de pessoa |
| **Auditoria** | A técnica do B (trilha imutável por signals) é portada para o app `auditoria` do A (**Fase 0**, já nesta entrega) e passa a cobrir também o domínio de eventos. `LogAuditoria` continua para as mensagens manuais existentes |
| **Async/infra** | Sem Celery/Redis na fase inicial: a geração documental portada roda **síncrona** (a cadeia de motores do B funciona assim; no Windows de produção o motor `word_com` é o mais rápido). Fila assíncrona vira decisão futura se a geração em lote pesar |
| **Testes** | O A tem 214 testes; a rede do B (2.731) não vem junto automaticamente. **Regra deste plano: cada módulo portado traz seus testes adaptados junto, no mesmo PR** — nunca portar código sem os testes correspondentes |

### Fora do escopo ratificado (decisão futura, não portados)

`planos_trabalho`, `ordens_servico`, **Google Drive**, **eProtocolo/protocolos**, rota/mapa Leaflet+OpenRouteService (subfase opcional F2b). Quem depende dessas funções continua no B até decisão específica — ver risco R2.

---

## 2. Fases

### Fase 0 — Fundação da plataforma na base A ✅ (esta entrega)

Infraestrutura transversal que todo o resto usa, aplicada primeiro ao próprio domínio de eventos:

1. **Abstratos** em `core/models.py`: `ModeloTemporal` (`criado_em`/`atualizado_em`) e `ModeloCancelavel` (`cancelado`, `motivo_cancelamento`, `cancelado_em`, `cancelar()`/`reativar()`) — contratos que os modelos portados do B usarão.
2. **`core/middleware.py::RequisicaoAtualMiddleware`** — requisição corrente em thread-local, para a auditoria conhecer ator e caminho sem acoplamento com views.
3. **`auditoria.RegistroAuditoria`** — trilha imutável (save de update e delete levantam `TypeError`), gravada por signals globais (`pre_save`/`post_save`/`pre_delete`) nos apps auditados, com delta de campos, filtro de campos sensíveis (senha/token) e escrita em `transaction.on_commit`. Modelos que já têm trilha própria (`HistoricoSolicitacao`) ou que são ruído (`Notificacao`, `LogAuditoria`) ficam de fora.
4. Admin somente-leitura para consulta da trilha; testes cobrindo criação/delta/exclusão/imutabilidade/sensíveis/ator.

**Gate:** suíte completa verde (214 testes existentes + novos), `makemigrations --check` limpo.

### Fase 1 — Cadastros de viagens (3–5 sessões)

- Novo app `viagens_cadastros` (ou extensão de `cadastros` — decidir no início da fase): `Servidor`, `Cargo`, `Unidade`, `Combustivel`, `Viatura`, `TabelaDiaria` (vigenciada, valores 15/30% derivados — portar com os testes de caracterização do B).
- Sem coluna `area`; constraints de unicidade viram globais (CPF/RG/telefone/placa únicos — a versão mais forte, que o B listou como defeito `DB-05` da placa por área).
- Enriquecer `Municipio` (capital, lat/long) + comando de importação da base do B.
- Módulo `VIAGENS` registrado no portal do A; CRUD no padrão `CADASTROS` por slug do A.
- Migração `Motorista` → `Servidor` e re-aponte de `SolicitacaoEvento.motorista`.
- **Gate:** CRUDs operando, ETL de cadastros do B idempotente com relatório, suíte verde.

### Fase 2 — Roteiros e diárias (4–6 sessões)

- Portar `Roteiro`, `RoteiroDestino`, `RoteiroTrecho`, `RoteiroDiariaComponente` com todas as constraints de período/não-negativos (`DB-07`/`DB-13` do B).
- **Antes de qualquer código:** portar os testes de caracterização do cálculo de diárias do B (`roteiros/services/diarias.py` — regra do próprio B: dinheiro não muda sem caracterização).
- Telas no padrão do A (FBVs + services). Campos manuais de distância/duração; **F2b (opcional):** mapa Leaflet + OpenRouteService.
- **Gate:** cálculo de diárias idêntico ao B nos casos de caracterização; suíte verde.

### Fase 3 — Núcleo documental (4–6 sessões)

- Portar `documentos/services` do B: registry de tipos, façade, render docxtpl, cadeia de motores PDF (`word_com` → `libreoffice` → `weasyprint` → fallback), nomenclatura, `DocumentoArtefato` (payload_snapshot + hash) e versões de assinatura append-only. **Síncrono** (sem `DocumentoGeracao`/Celery).
- Copiar os templates `.docx` de ofício/justificativa/termo + golden files de placeholders.
- Novas dependências em `requirements.txt` (python-docx, docxtpl, docxcompose, weasyprint, pypdf, fpdf2; `docx2pdf`/`pywin32` só no Windows).
- **Gate:** `documentos_check` portado passa; geração DOCX+PDF dos 3 tipos com golden files verdes.

### Fase 4 — Ofícios, justificativas e termos (5–8 sessões)

- Portar `Oficio` (+ numeração com lacunas e advisory lock do PostgreSQL), `Justificativa` (1:1), `TermoAutorizacao`, catálogos de motivo.
- Fluxo no padrão do A (wizard de etapas do B reexpresso em FBVs: viajantes → transporte → roteiro → justificativa → resumo → documentos).
- **Gate:** ofício completo criado e gerado em DOCX/PDF de ponta a ponta; numeração serializada sob concorrência testada.

### Fase 5 — Prestações de contas (6–9 sessões)

- F5a: `PrestacaoContas`, `PrestacaoServidor` (soft-remove), `RelatorioTecnico`, `DiarioBordo` (+trechos), anexos com validação, carimbo de nº de solicitação em PDF, downloads consolidados.
- F5b: **assinatura eletrônica por link público** (token cifrado Fernet — adiciona `cryptography`; confirmação de identidade; carimbo de assinatura; código de verificação).
- **Gate:** ciclo ofício→prestação→RT/diário→consolidado completo; assinatura pública funcional em F5b.

### Fase 6 — Migração de dados do B e virada (3–4 sessões)

- ETL idempotente/auditável/reversível (mesma técnica do §10 da auditoria: `legado_origem`/`legado_pk`, `--dry-run`, relatório, quarentena de anexos), lendo dump do B por conexão `legado`.
- Matriz de paridade (contagens, diárias somadas, documentos regenerados × arquivados por hash, fluxo roteirizado).
- Virada: B em somente-leitura; usuários no sistema unificado.

**Total estimado: ~25–35 sessões** (F0 concluída nesta). A régua de qualidade por fase: suíte inteira verde, zero migração pendente, testes portados junto com o código.

---

## 3. Riscos específicos da Opção A

| # | Risco | Mitigação |
|---|---|---|
| R1 | **Porte sem a rede completa do B** — reescrever ~50–70 mil linhas relevantes protegidas lá por 2.731 testes | Regra "testes viajam com o código"; caracterização antes de qualquer lógica de dinheiro (diárias, prestações) |
| R2 | **Funções do B fora do escopo** (Drive, eProtocolo, planos, OS) somem da vida dos usuários do B na virada | Virada só após aceite explícito; B permanece somente-leitura como consulta |
| R3 | **Geração síncrona** pode segurar requests longos (lotes de termos) | `word_com` no Windows é rápido; medir na F3 e só então decidir sobre fila |
| R4 | **Downgrade de disciplina** — o A não tem ruff/catracas/CodeQL do B | Item de F1: adotar ruff no CI do A (teto zero) e avaliar as catracas que fizerem sentido |
| R5 | **Advisory lock exige PostgreSQL** — dev do A usa SQLite por fallback | Portar com fallback `select_for_update` (o B já tem essa dupla implementação) |
| R6 | Infra de produção do A (waitress/Windows/OneDrive) recebendo um sistema muito maior | Reavaliar hospedagem até a F6; o B documenta os riscos do OneDrive |

## 4. Decisões pendentes do usuário (novas, sob a base A)

| # | Decisão | Quando |
|---|---|---|
| DA1 | App único `viagens_*` vs estender `cadastros` existente | Início da F1 |
| DA2 | Grupos/perfis do domínio de viagens (quem cria roteiro, quem assina, quem presta contas) | F1 |
| DA3 | Incluir F2b (mapa/ORS) ou manter km/duração manuais | Fim da F2 |
| DA4 | Destino das funções fora de escopo do B (Drive, eProtocolo, planos, OS) | Antes da F6 |
| DA5 | Hospedagem do sistema unificado (manter Windows/waitress vs VPS) | Antes da F6 |
