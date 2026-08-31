# Auditoria de Viabilidade — Unificação dos Sistemas de Eventos Sociais e Central de Viagens 3

**Data:** 31/08/2026
**Sistemas auditados:**

- **Sistema A — "Sistema de Gestão de Eventos Sociais"** (`tiago2904santos/Sistema-de-Gest-o-de-Eventos-Sociais`)
- **Sistema B — "Central de Viagens 3 / Gerenciador de Viagens"** (`tiago2904santos/gerenciador-de-viagens`)

Este documento consolida a leitura integral dos dois códigos-fonte (modelos, views, services, testes, CI, documentação) e entrega os 15 itens pendentes da auditoria, mais a recomendação técnica, riscos, marcos e decisões que dependem do usuário.

---

## 1. Resumo executivo

A unificação é **viável e recomendada**, mas os dois sistemas não são pares: são uma ordem de grandeza diferentes em tamanho e maturidade de engenharia.

| Dimensão | Sistema A (Eventos) | Sistema B (Central de Viagens 3) |
|---|---|---|
| Linhas de Python | 13.614 | 146.514 |
| Modelos concretos | 17 | ~60 |
| Testes (`def test_`) | ~214 (unittest) | **2.731** (unittest) + Vitest/axe no front |
| Migrações | 34 | 205 |
| Django / Python | **6.1** / 3.14 | 5.2 / 3.12 |
| Multi-tenancy | Não (Setor↔Módulo é autorização, não recorte) | **Sim** — `AreaTrabalho` + `AreaScopedManager` em 28+ modelos |
| Auditoria | `LogAuditoria` manual (só usuários/cadastros) | `AuditEvent` imutável, por signals globais em 11 apps |
| Geração de documentos | Nenhuma (só CSV) | Núcleo completo DOCX/PDF (docxtpl, 5 motores com fallback, cache, jobs Celery) |
| Storage/anexos | `media/` local, download por view, 10 MB | Mídia privada com X-Accel-Redirect, ClamAV fail-closed, Google Drive por OAuth |
| Infra | waitress no Windows, backup OneDrive | VPS nginx+gunicorn+Redis+Celery+unoserver, deploy por CI |
| CI | 1 workflow (check + testes) | 8 workflows, ruff teto zero, 8 catracas de auditoria, CodeQL |
| Estado | Estável, escopo pequeno e coeso | Ciclo de refactor de 10 fases **encerrado em 13/08/2026** |

**O que cada um traz de único:** o Sistema A traz o domínio (workflow de solicitações de eventos com máquina de estados explícita, coffee break com controle de saldo contratual, demandas ASCOM), um sistema de **notificações internas + e-mail** que o B não possui, views SQL para Power BI e a identidade visual institucional refinada. O Sistema B traz a plataforma: tenancy, auditoria, núcleo documental, integração Drive/eProtocolo, disciplina de desempenho medido e uma suíte de testes 12× maior.

**Recomendação (ver §2): Opção B — Central de Viagens 3 como base**, portando o domínio de eventos do Sistema A como novos apps dentro da arquitetura do B, em uma `AreaTrabalho` própria. A alternativa inversa (A como base) exigiria reconstruir no A praticamente tudo que o B levou dois ciclos de refactor para consolidar; uma terceira base do zero descartaria os dois ativos.

---

## 2. Recomendação de base técnica

### Opção B — Central de Viagens 3 como base ✅ (recomendada)

**Evidências a favor:**

1. **O mecanismo de unificação já existe.** O B é multi-tenant por `usuarios.AreaTrabalho` com recorte automático de leitura (`AreaScopedManager`, `default_manager_name="all_objects"`), middleware de área corrente e RBAC por vínculo (`ADMIN`/`EDITOR`/`LEITOR`). Hospedar o domínio de eventos é criar apps novos seguindo `docs/PADRAO_APP.md` — não inventar arquitetura.
2. **Assimetria de porte:** portar ~13,6 mil linhas coesas para dentro de uma base de 146,5 mil é tratável; o inverso significaria reimplementar no A o núcleo documental (9,2 mil linhas), o Drive (9,5 mil), prestações de contas (18,4 mil), protocolos, numeração com advisory lock, auditoria por signals — sem os 2.731 testes que os protegem.
3. **Qualidade defendida por máquina:** o B tem ruff teto zero, `makemigrations --check`, 8 catracas "o número só desce", golden files dos templates DOCX, testes de contrato de arquitetura (ORM em view reprova o PR). Qualquer código portado herda essa proteção.
4. **Infra de produção real:** VPS com nginx/gunicorn/Redis/Celery/ClamAV e deploy condicionado a testes verdes, contra tarefa agendada do Windows com waitress e backup em pasta OneDrive (o próprio B documenta os problemas de rodar sob OneDrive — `G-03`/`N-12`).
5. **Convergência semântica favorável:** a `Regiao` operacional do A (Capital/Interior/Brasília, migração `0006_regioes_operacionais`) coincide exatamente com a `faixa` da `TabelaDiaria` do B (`INTERIOR`/`CAPITAL`/`BRASILIA`) — os dois sistemas já falam a mesma língua regional da PCPR.

**Custos assumidos (ver §8 e §17):**

- O A usa `AUTH_USER_MODEL` customizado (`accounts.User`); o B usa o `User` padrão. Trocar `AUTH_USER_MODEL` numa base madura é inviável na prática — a unificação **mantém o User padrão** e migra os campos extras do A (`deve_trocar_senha`, `setores`) para modelos satélites (§12).
- O A está em Django 6.1; o B em 5.2 LTS-track. O código portado precisa rodar em 5.2 (nada exclusivo de 6.x foi encontrado no A — os recursos usados são todos estáveis desde 4.x), e o upgrade do B para 6.x vira item de roadmap, não pré-requisito.
- O front do A (design system próprio de 3,3 mil linhas de CSS + Lucide) será **reexpresso** nos componentes Cotton/tokens do B, preservando a identidade visual como tema (§ decisão D5).

### Opção A — Eventos como base ❌

Descartada por evidência: exigiria reconstruir no A o equivalente a ~130 mil linhas testadas do B ou abrir mão de documento/Drive/prestações — os motivos de existir do B. O refinamento visual do A não compensa; visual porta-se, plataforma não.

### Opção C — terceira base unificada ❌

Descartada: o B **já é** a "terceira base" — a Central de Viagens 3 foi reescrita como plataforma modular document-centric justamente para receber domínios novos ("Eventos podem agrupar documentos, mas não são obrigatórios" — `README.md` do B). Recomeçar descartaria dois ciclos de refactor documentados e 2.731 testes.

---

## 3. Inventário de módulos dos dois sistemas

### 3.1 Sistema A (13.614 LOC Python; 34 migrações; ~50 rotas)

| App | LOC | Migr. | Modelos | Papel |
|---|---:|---:|---|---|
| `solicitacoes` | 5.301 | 16 | SolicitacaoEvento, SolicitacaoEventoServico, SolicitacaoEventoEquipe, AnexoSolicitacao, HistoricoSolicitacao | **Núcleo maduro**: workflow com máquina de estados em `services.py`, anexos, export CSV, views Power BI |
| `coffee_break` | 2.962 | 2 | Fornecedor, ContratoCoffeeBreak, LoteCoffeeBreak, SolicitacaoCoffeeBreak | Módulo ASCOM: saldo contratual com `select_for_update`, situação financeira derivada |
| `cadastros` | 1.451 | 7 | CadastroBase(abstr.), TipoEvento, Servico, Equipe, OrgaoResponsavel, Regiao, UnidadeMovel, Estado, Municipio, Motorista | CRUD genérico por slug; seeds + importador IBGE |
| `demandas_eventos` | 1.301 | 3 | Tema, RespostaPadrao, Palestrante, DemandaEvento | Módulo ASCOM: demandas com isolamento por Setor |
| `accounts` | 1.144 | 3 | User(AbstractUser), Setor, Modulo | Usuário customizado, portal de módulos, troca de senha obrigatória |
| `core` | 760 | 2 | Notificacao | Hub de módulos + central de notificações (in-app e e-mail on_commit) |
| `dashboard` | 341 | 0 | — | Indicadores sobre `solicitacoes` (sparklines 12 meses) |
| `auditoria` | 80 | 1 | LogAuditoria | Subutilizado: só gestão de usuários e cadastros, sem signals, sem telas |

Dois eixos de autorização: **Groups** (SOLICITANTE / GESTOR_DG / ADMINISTRADOR) para o fluxo de eventos, e **Setor↔Modulo** (middleware por namespace) para os módulos ASCOM.

### 3.2 Sistema B (146.514 LOC Python; 205 migrações; ~230 rotas)

| App | LOC | Migr. | Papel |
|---|---:|---:|---|
| `core` | 21.370 | 4 | Abstratos, AuditEvent, middleware (área, sessão, CSP, request_id), numeração com advisory lock, paginação, mídia privada, throttle de login |
| `prestacoes_contas` | 18.399 | 37 | Maior superfície: prestação por servidor/ofício, RT, diário de bordo, carimbo em PDF, **assinatura eletrônica por link público** com token cifrado |
| `roteiros` | 16.440 | 16 | A "viagem": destinos, trechos, mapa Leaflet+ORS, componentes de diária imutáveis (`DB-13`) |
| `oficios` | 13.814 | 20 | Documento principal de autorização; wizard 6 etapas; numeração com lacunas |
| `cadastros` | 11.597 | 28 | Unidade, Estado, **Cidade**, Cargo, Combustivel, **Servidor**, **Viatura**, ConfiguracaoSistema (singleton por área), TabelaDiaria vigenciada |
| `planos_trabalho` | 11.151 | 25 | Wizard 4 etapas, multi-evento, catálogos por área |
| `integracoes.google_drive` | 9.519 | 12 | OAuth por usuário, organizer canônico+atalhos, fila Celery própria, pendências |
| `documentos` | 9.266 | 13 | **Núcleo documental**: DocumentoArtefato (UUID, payload_snapshot, hash), 5 motores PDF com fallback, cache por fingerprint, geração assíncrona, versões de assinatura append-only |
| `termos` | 5.389 | 10 | Termos de autorização com cascata de resolução de efetivo |
| `eventos` | 5.342 | 17 | Agrupador **opcional** de documentos; fluxo guiado por etapas |
| `protocolos` | 4.543 | 2 | Tramitação eProtocolo/PR (client, mocks, logs mascarados) |
| `ordens_servico` | 4.425 | 14 | OS com papéis de equipe e numeração por lacuna |
| `usuarios` | 2.842 | 2 | **AreaTrabalho (tenant)** + VinculoUsuarioArea (papel ADMIN/EDITOR/LEITOR) |
| `justificativas` | 2.432 | 5 | Justificativa 1:1 com ofício, modelos por área |

---

## 4. Matriz de equivalência módulo a módulo

| Sistema A | Sistema B | Veredicto |
|---|---|---|
| `accounts.User` (custom) | `auth.User` padrão + `usuarios.VinculoUsuarioArea` | **Conflito estrutural** — manter User padrão; portar `deve_trocar_senha`/`setores` como satélites (§12) |
| `accounts.Setor` + `accounts.Modulo` | `usuarios.AreaTrabalho` + papel do vínculo | Setor→Área ou Setor→catálogo interno, conforme decisão D2 |
| `auditoria.LogAuditoria` | `core.AuditEvent` | **B substitui A por completo** (superset); LogAuditoria vira dado legado importado |
| `cadastros.Estado` | `cadastros.Estado` | Equivalência ~1:1 (mesmos campos: nome, sigla unique, codigo_ibge) |
| `cadastros.Municipio` | `cadastros.Cidade` | Equivalente com renomeação; B é superset (uf denormalizada, capital, lat/long). A `Regiao` do A **não existe** no B como FK — ver conflito C2 |
| `cadastros.Regiao` (Capital/Interior/Brasília) | `TabelaDiaria.faixa` (mesmo trio, mas não é entidade) | Portar `Regiao` como catálogo do domínio de eventos OU derivar da geografia — conflito C2 |
| `cadastros.Motorista` | **não existe** — motorista é `Servidor` | **Conflito C1**: converter Motorista→Servidor (regra de pedra do B: `docs/REGRAS_DE_NEGOCIO.md`) |
| `cadastros.TipoEvento` (global) | `eventos.TipoEvento` (por área) | Fundir no do B, com carga por área |
| `cadastros.{Servico, Equipe, OrgaoResponsavel, UnidadeMovel}` | sem equivalente direto (`Unidade` cobre parcialmente OrgaoResponsavel) | Portar como catálogos por área no novo app de eventos sociais, no padrão `is_padrao`/4 constraints do B |
| `solicitacoes.SolicitacaoEvento` + workflow | **não existe** — no B "solicitação" é anexo (`EventoDocumentoSolicitacao`) e `Evento` não tem workflow de aprovação | **Ativo único do A** — portar como app novo `solicitacoes_eventos` com a máquina de estados intacta |
| `solicitacoes.HistoricoSolicitacao` | sem equivalente de domínio (AuditEvent é técnico) | Portar junto: é trilha de negócio, complementar ao AuditEvent |
| `solicitacoes.AnexoSolicitacao` | padrão de mídia privada + `validate_private_document_upload` | Portar aderindo ao pipeline do B (ClamAV, magic bytes, X-Accel-Redirect) |
| `core.Notificacao` + e-mail on_commit | **não existe no B** | **Ativo único do A** — portar como componente transversal (candidato a `core` do B) |
| `coffee_break.*` | sem equivalente | Portar como app novo por área |
| `demandas_eventos.*` | sem equivalente | Portar como app novo por área |
| `dashboard` | `core:dashboard` do B | Reexpressar os cartões/sparklines no dashboard do B |
| Export CSV + views SQL Power BI | export CSV de cidades existe; views Power BI não | Portar as views (`vw_solicitacoes` etc.) para o PostgreSQL do B |
| Design system próprio (3,3k CSS, Lucide) | Design system tokens + Cotton + tema claro/escuro + catracas | Adotar o do B; identidade visual do A vira tema/tokens (decisão D5) |
| — | Núcleo documental, Drive, eProtocolo, prestações, roteiros, ofícios… | Permanecem como estão; o domínio de eventos **ganha acesso** a eles (ex.: gerar ofício a partir de solicitação deferida — evolução futura) |

---

## 5. Mapa de entidades e relacionamentos atuais (ER lógico)

### 5.1 Sistema A — núcleo

```
User (custom) ──M2M── Setor ──M2M── Modulo
  │
  ├─ cria ─► SolicitacaoEvento ──FK── Municipio ──FK── Estado
  │             │                        └─FK── Regiao (derivada no save)
  │             ├─FK── TipoEvento / OrgaoResponsavel / UnidadeMovel / Motorista
  │             ├─M2M(through)── Servico  [SolicitacaoEventoServico]
  │             ├─M2M(through)── Equipe   [SolicitacaoEventoEquipe → recalcula qtd_servidores]
  │             ├─◄── AnexoSolicitacao (FileField, 10 MB)
  │             ├─◄── HistoricoSolicitacao (ação, status_anterior→novo)
  │             └─◄── Notificacao (por usuário, lida/não lida)
  │
  ├─ coffee_break: Fornecedor ─► Contrato ─► Lote (M2M Municipio; saldo) ─► SolicitacaoCoffeeBreak
  └─ demandas_eventos: DemandaEvento ──FK Municipio/TipoEvento ──M2M Palestrante(─M2M Tema)/Setor
```

### 5.2 Sistema B — núcleo (simplificado)

```
AreaTrabalho (tenant) ◄──FK── quase tudo (28+ modelos, AreaScopedManager)
   └─◄ VinculoUsuarioArea ──FK── auth.User (papel ADMIN/EDITOR/LEITOR)

Evento (agrupador OPCIONAL, cancelamento em cascata)
   ├─◄ Roteiro (a viagem: destinos, trechos, diárias componentizadas, rota/mapa)
   ├─◄ Oficio ──M2M── Servidor; FK Viatura; numeração (área, ano, número) c/ lacunas
   │      ├─ 1:1 Justificativa      ├─◄ TermoAutorizacao
   │      └─ 1:1 PrestacaoContas ─◄ PrestacaoServidor ─◄ RT / DiarioBordo / Assinaturas
   ├─◄ PlanoTrabalho (wizard, multi-evento)   └─◄ OrdemServico (M2M oficios)
   
DocumentoArtefato (UUID; FKs opcionais p/ oficio/servidor/evento/termo;
                   payload_snapshot + hash; versões de assinatura append-only)
   └─ 1:1 DriveArquivo → Google Drive (canônico + atalhos)
Protocolo (GenericFK origem) → eProtocolo/PR
Cidade ──FK── Estado (base geográfica GLOBAL, sem área)
Servidor / Viatura / Cargo / Combustivel / Unidade (por área, constraints pareadas global/área)
```

---

## 6. Proposta de modelo de domínio unificado

Princípio: **o domínio de eventos sociais entra no B como área + apps novos**, sem tocar o núcleo. Nome de trabalho dos apps: `eventos_sociais` (solicitações), `coffee_break`, `demandas_ascom`.

```
AreaTrabalho "EVENTOS SOCIAIS" (ou uma por setor — decisão D2)
   │
   ├─ eventos_sociais.SolicitacaoEventoSocial   ← porta SolicitacaoEvento
   │     FK area (PROTECT) · FK cidade → cadastros.Cidade (PROTECT)
   │     FK regiao_operacional → eventos_sociais.RegiaoOperacional (catálogo por área)
   │     FK tipo_evento → eventos.TipoEvento (reuso do catálogo por área do B)
   │     FK orgao → eventos_sociais.OrgaoResponsavel · FK unidade_movel
   │     FK motorista → cadastros.Servidor          ← conversão C1
   │     M2M servicos (through c/ observacao) · M2M equipes (through c/ quantidade)
   │     status/decisao_dg/timestamps idênticos ao A (máquina de estados portada)
   │     herda TimeStampedModel; managers all_objects/objects padrão do B
   │
   ├─ eventos_sociais.HistoricoSolicitacao      ← portado 1:1 (trilha de negócio)
   ├─ eventos_sociais.AnexoSolicitacao          ← FileField no pipeline de mídia privada do B
   ├─ catálogos por área: Servico, Equipe, OrgaoResponsavel, UnidadeMovel, RegiaoOperacional
   │     (padrão B: nome, ativo, ordem, is_padrao, 4 constraints, index (area, ordem, nome))
   │
   ├─ coffee_break.{Fornecedor, Contrato, Lote, SolicitacaoCoffeeBreak}  ← + FK area
   ├─ demandas_ascom.{Tema, RespostaPadrao, Palestrante, DemandaEvento}  ← + FK area
   │     (Setor do A → ver decisão D2)
   │
   └─ core.Notificacao (NOVO no B, transversal)  ← porta core.Notificacao do A
         FK user · GenericFK origem (em vez de FK fixa p/ solicitação) · lida · link

Auditoria: adicionar os novos apps a AUDITED_APP_LABELS → AuditEvent automático.
Ponte futura (fase 2+): solicitação DEFERIDA pode semear um eventos.Evento do B
e gerar documentos pelo núcleo documental — é a sinergia que justifica a unificação.
```

Regras de aderência ao B (invioláveis pelo `AGENTS.md`): camadas `models → forms → selectors → services → presenters → views`, sem ORM em view, componentes Cotton, sem `fetch()` cru, cores só por token.

---

## 7. Matriz preliminar de campos e regras de correspondência

Entidades com migração de dados não-trivial (campos idênticos omitidos):

| Origem (A) | Destino (unificado no B) | Regra |
|---|---|---|
| `Municipio.nome + estado` | `Cidade` | Casar por `codigo_ibge` quando houver; fallback `(nome normalizado, estado.sigla)`. Municípios do A sem par no B são criados (base do B já é IBGE) |
| `Municipio.regiao` | `SolicitacaoEventoSocial.regiao_operacional` + tabela de mapeamento cidade→região | A região deixa de morar na cidade (que no B é global/sem área) e passa a catálogo do domínio + vínculo cidade→região por área |
| `Motorista(nome, telefone)` | `Servidor(nome, telefone, cargo="MOTORISTA")` | Nome em MAIÚSCULAS (regra do B), dedupe por nome normalizado; sem CPF/RG → status RASCUNHO |
| `TipoEvento` (global) | `eventos.TipoEvento` (por área) | get_or_create por `(area, nome)` |
| `SolicitacaoEvento.status` | idem | Domínio preservado; status legados (`ENVIADA`, `EM_ANALISE`) só existem em histórico — migrar como texto, sem choices (mesma técnica do A) |
| `HistoricoSolicitacao.usuario` | idem | Mapear por username; usuário ausente → NULL + observação de migração |
| `AnexoSolicitacao.arquivo` | idem, sob `MEDIA_ROOT` do B | Copiar arquivo físico, revalidar (extensão/magic/ClamAV); reprovados vão a relatório de quarentena, nunca descartados silenciosamente |
| `quantidade_servidores` | idem | Recalcular no destino a partir dos itens de equipe (não confiar no valor gravado) |
| `LoteCoffeeBreak.municipios` (M2M) | M2M → `Cidade` | Mesma regra de casamento de município |
| `SolicitacaoCoffeeBreak.situacao_financeira` | derivada | **Não migrar** — é calculada dos marcos; migrar apenas os marcos (datas/NF/protocolo) |
| `DemandaEvento.chave_importacao` | idem (unique) | Preservar — é a chave de idempotência das planilhas ASCOM |
| `User(username, …, deve_trocar_senha, setores)` | `auth.User` + satélites | §12. Hash de senha PBKDF2 é compatível — migra sem reset |
| `LogAuditoria` | tabela legada `eventos_sociais.LogAuditoriaLegado` (somente leitura) | AuditEvent é imutável e não aceita back-dating; trilha antiga preserva-se como dado histórico consultável |
| `Notificacao.solicitacao` (FK fixa) | GenericFK origem | Generalização para servir aos demais domínios do B |

---

## 8. Lista de conflitos semânticos

| # | Conflito | Resolução proposta |
|---|---|---|
| **C1** | **Motorista vs Servidor.** A tem entidade `Motorista`; o B proíbe por regra de pedra ("não existe Motorista; motorista é um Servidor") | Converter no ETL (§10). O fluxo de eventos passa a selecionar `Servidor` com função de condução — alinhado a `Oficio.motorista` |
| **C2** | **Município vs Cidade + Região.** No A a região operacional é FK do município e é derivada no `save()` da solicitação; no B `Cidade` é base global sem área e sem região | `Cidade` permanece global; região vira catálogo por área + mapeamento cidade→região do domínio de eventos. A derivação automática no save é portada para o service |
| **C3** | **User customizado vs padrão.** `AUTH_USER_MODEL` divergente — inconciliável por migração de schema | Manter `auth.User`; `deve_trocar_senha` → modelo satélite + middleware portado; `setores` → decisão D2 |
| **C4** | **Perfis:** Groups (SOLICITANTE/GESTOR_DG/ADMINISTRADOR) vs papel por área (ADMIN/EDITOR/LEITOR) | Dois níveis distintos que **coexistem**: papel de área controla escrita/leitura (plataforma); a política de negócio (`pode_despachar`, `pode_concluir`…) porta-se como funções de service do app, mapeando GESTOR_DG→papel/flag de domínio. Mapa inicial: ADMINISTRADOR→ADMIN, GESTOR_DG→EDITOR+flag `gestor_dg`, SOLICITANTE→EDITOR, ANALISTA(legado)→EDITOR |
| **C5** | **"Evento" significa coisas diferentes:** no A é a solicitação com workflow; no B é agrupador opcional de documentos | Nomes distintos no código unificado: `SolicitacaoEventoSocial` (workflow) ≠ `eventos.Evento` (agrupador). Ponte opcional na fase 2 |
| **C6** | **"Solicitação" no B é outro conceito** (anexo de pedido de viagem; `numero_solicitacao` é financeiro) | Nunca reutilizar `EventoDocumentoSolicitacao`/`numero_solicitacao` para o domínio de eventos; nomenclatura própria |
| **C7** | **TipoEvento duplicado** (global no A, por área no B) | Fundir no do B |
| **C8** | **Auditoria:** manual e parcial no A vs signals imutáveis no B | AuditEvent assume; `HistoricoSolicitacao` permanece como trilha de negócio (são complementares, não redundantes) |
| **C9** | **Setor vs Área** | Decisão D2 do usuário |
| **C10** | **Anexos:** 10 MB/10 extensões no A vs 20 MB/4 extensões + antivírus no B | Adotar pipeline do B; a lista de extensões do A (doc/docx/xls/xlsx/odt/ods) precisa ser **adicionada** ao validador do B para o novo app — mudança pequena e testável |
| **C11** | **Django 6.1 vs 5.2** | Código portado roda em 5.2 (sem dependência de 6.x detectada); upgrade do B é item separado do roadmap |
| **C12** | **Postgres 18 (CI do A) vs 16 (CI/prod do B)** | Padronizar no 16 do B; nada no A exige 18 |

---

## 9. Inventário de funcionalidades que precisam de teste de caracterização

Antes de portar, congelar o comportamento atual do A com testes de caracterização (o `AGENTS.md` do B já exige isso para qualquer código que envolva dinheiro — o coffee break se enquadra):

1. **Máquina de estados de `solicitacoes/services.py`** — `TRANSICOES_VALIDAS` completo, incluindo: devolvida→reenvio, cancelamento a partir de cada status, observação obrigatória em NAO_ATENDER/CANCELADO/DEVOLVER, `TransicaoInvalida` nos caminhos proibidos.
2. **`pendencias_para_envio`** — os 8 campos obrigatórios + ≥1 serviço + ≥1 equipe com quantidade>0 + unidade móvel designada quando marcada.
3. **Derivação `regiao = municipio.regiao` no save** e a validação de coerência no `clean()`.
4. **`recalcular_quantidade_servidores`** — disparo em save/delete do item de equipe.
5. **Saldo do coffee break** (💰): `com_consumo()` (canceladas fora da soma), `salvar_com_saldo` com `select_for_update`, reativação que estoura saldo, alerta ≤15%.
6. **Situação financeira derivada** — a cadeia NF→protocolo→atesto→OB→envio→concluída e o curto-circuito de cancelada.
7. **Export CSV** — 25 colunas, BOM, `;`, CRLF, respeito aos filtros (golden file).
8. **Notificações** — destinatários por transição (quem recebe o quê em envio/devolução/decisão/conclusão) e e-mail via on_commit.
9. **Visibilidade**: rascunho privado do criador; filas por perfil (despacho só GESTOR_DG); `pode_gerenciar_anexos` fechado após finalização inclusive para superusuário.
10. **Isolamento por setor das demandas ASCOM** (`queryset_visivel`) e dedupe por `chave_importacao` nos importadores de planilha.
11. **Troca de senha obrigatória** — redirecionamento e rotas liberadas.
12. **Dashboard** — janelas das métricas (mês/ano/próximos 30 dias) para paridade visual pós-porte.

O A já cobre boa parte disso (108 testes em solicitacoes, 44 em coffee_break); a tarefa é **adaptar esses testes ao harness do B** (`core/testing.py::area_de_teste`, `com_request(area)`) antes de portar o código — eles são a rede da migração.

---

## 10. Estratégia de migração de dados (idempotente, auditável, reversível)

**Forma:** management commands no B, um por entidade, na ordem de dependência:
`usuarios → catálogos → cidades/regiões → solicitações (+ itens, anexos, histórico) → coffee break → demandas → notificações → log legado`.

**Idempotência:** toda linha migrada grava origem em coluna própria (`legado_origem="eventos_sociais_v1"`, `legado_pk`) com `UniqueConstraint` condicional — reexecutar é upsert, nunca duplicação. (Mesma técnica da `chave_importacao` que o A já usa.)

**Auditabilidade:** cada execução produz relatório (contagens por entidade: criadas/atualizadas/ignoradas/reprovadas + arquivo de rejeições com motivo). O comando roda com `--dry-run` por padrão; a execução real exige `--commit`. Anexos reprovados na revalidação vão para relatório de quarentena.

**Reversibilidade:** duas camadas — (1) `pg_dump` automático pré-migração (o deploy do B já faz isso); (2) como toda linha carrega `legado_origem`, um comando `desfazer_migracao_eventos --commit` remove exatamente o que foi importado, enquanto nada nativo tiver referenciado essas linhas (verificação de FKs reversas antes de apagar).

**Fonte:** dump PostgreSQL do A (ou o SQLite de dev para ensaio). O comando lê por conexão `django.db.connections["legado"]` configurada por env var — sem acoplamento de código entre os projetos.

**Ensaios:** ≥2 execuções completas em homologação (o B mantém ambiente de homologação separado por `AMBIENTES.md`) com conferência da matriz de paridade (§14) antes da janela de produção.

## 11. Estratégia para arquivos (anexos, DOCX/PDF, Drive)

1. **Anexos do A** (`media/solicitacoes/{id}/…`): copiados para o `MEDIA_ROOT` do B sob `eventos_sociais/solicitacoes/{novo_id}/`, revalidados (extensão, magic bytes, ClamAV). Download passa a usar `core/private_media.py` (X-Accel-Redirect em produção) — o A já tinha a semântica certa (nunca servir MEDIA direto), o B tem a implementação industrial.
2. **Extensões:** ampliar o validador do app novo para aceitar o conjunto do A (`pdf png jpg jpeg doc docx xls xlsx odt ods`), mantendo 20 MB como teto (superset do limite atual de 10 MB — nenhum anexo legado reprova por tamanho).
3. **Geração de documentos:** fase 1 **não** gera DOCX/PDF para eventos (paridade primeiro — o A não gerava). Fase 2: registrar tipos novos no `DocumentoTipo`/registry do núcleo documental (ex.: memorando de despacho da DG) — é exatamente o ponto de extensão que o núcleo expõe.
4. **Google Drive:** opcional por área — a sincronização do B é acionada por signals sobre artefatos/anexos; incluir os anexos de eventos na fase 2, com pasta própria no organizer ("Eventos Sociais/…"), reaproveitando `DriveArquivoExterno` (GenericFK, feito para FileFields fora do núcleo).
5. **Export CSV/Power BI:** portar `exportar_solicitacoes` (mesmas 25 colunas, golden file) e recriar as views `vw_solicitacoes`, `vw_solicitacao_servicos`, `vw_solicitacao_equipes`, `vw_tempos_workflow` por migração no B, com `GRANT` ao role `powerbi_reader` — apontando o Power BI para o banco do B após a virada.

## 12. Estratégia de autenticação e permissões unificadas

1. **Modelo de usuário:** `auth.User` padrão (do B). Migração dos usuários do A por username/e-mail; hashes PBKDF2 compatíveis — **ninguém precisa redefinir senha**.
2. **`deve_trocar_senha`:** novo modelo satélite (ex.: `usuarios.PoliticaSenha` OneToOne) + porte do `TrocaDeSenhaObrigatoriaMiddleware` para a pilha do B. Atenção: o B exige senha ≥12 caracteres — usuários do A com senha mais curta continuam logando (hash migra), mas a política nova vale na próxima troca.
3. **Tenancy:** criar `AreaTrabalho` para o domínio (decisão D2: uma área "EVENTOS SOCIAIS" vs uma por setor). Vínculos criados na migração conforme mapa C4.
4. **Política de negócio:** `permissions.py` do app portado mantém as funções do A (`pode_despachar`, `acoes_permitidas`…), reimplementadas sobre `request.vinculo_area` + flag de gestor DG (Group `GESTOR_DG` pode ser mantido como flag de domínio — o B não usa Groups, então não há colisão).
5. **Módulos ASCOM:** o controle Setor↔Modulo do A é substituído pelo próprio recorte por área do B (quem não tem vínculo com a área do coffee break não vê nada — mais forte que o middleware por namespace do A).
6. **Ganhos imediatos para o domínio de eventos:** rate limit de login, sessão renovada com economia de queries, CSP, SSO opcional por header MFA — tudo herdado da plataforma.
7. **Perda funcional a repor:** o A tem **recuperação de senha por e-mail**; o B deliberadamente não tem (`AUTENTICACAO.md`). Decisão D6 do usuário: adotar o fluxo de reset do A na plataforma unificada (recomendado, já que haverá SMTP configurado para notificações) ou manter a política restritiva do B.

## 13. Estratégia de auditoria e rastreabilidade

1. **Trilha técnica:** adicionar `eventos_sociais`, `coffee_break`, `demandas_ascom` a `AUDITED_APP_LABELS` — todo CREATE/UPDATE/DELETE vira `AuditEvent` imutável com delta, ator, área e request_id, de graça.
2. **Trilha de negócio:** `HistoricoSolicitacao` portado como está (é a fonte da timeline da tela e das views de tempos do Power BI). Coffee break ganha o que hoje não tem: AuditEvent cobre o que o cancelamento inline não registra.
3. **Legado:** `LogAuditoria` do A importado como tabela somente-leitura (AuditEvent recusa inserts com data retroativa por design — não falsificar trilha).
4. **Correlação:** `request_id` no log JSON + `X-Request-ID` já existem no B; notificações e transições de workflow devem registrar o request_id na observação do histórico quando relevante.
5. **Sentry** (opcional, já plugado no B) passa a cobrir o domínio de eventos.

## 14. Plano de testes e matriz de paridade

**Fundação:** suíte do B permanece verde a cada fase (gate de CI existente). Testes do A adaptados ao harness do B somam-se à suíte (meta: ≥214 portados + caracterizações do §9).

**Matriz de paridade** (executada em homologação a cada ensaio de migração, por amostragem dirigida + totais):

| Verificação | Critério |
|---|---|
| Contagens por entidade e por status | A = B (menos rejeições justificadas no relatório) |
| Soma de `quantidade` de coffee por lote e saldo | idênticos, canceladas excluídas |
| Timeline de 20 solicitações amostrais (1+ por status, incl. status legados) | histórico byte a byte equivalente |
| Export CSV de um mesmo filtro nos dois sistemas | diff vazio (após normalizar IDs) |
| Anexos: contagem, tamanho total, hash de amostra | iguais; quarentena relatada |
| Situação financeira derivada de todas as solicitações coffee | igual campo a campo |
| Views Power BI: mesma consulta nos dois bancos | resultados equivalentes |
| Fluxo manual roteirizado (criar→enviar→devolver→reenviar→deferir→concluir) | comportamento e notificações idênticos |

**Front:** os testes de contrato do B (Cotton, tokens, acessibilidade axe, foco visível) aplicam-se automaticamente às telas novas; catracas de auditoria não podem subir.

## 15. Baseline e plano de desempenho

**Baseline atual do B (régua vigente do PLANO_MESTRE):** `PF-05` = 33,2 ms / 7 consultas no regime quente canônico; CSS usado por rota 37,5–60,3% (`PF-02`). Essa régua é o teto de entrada: **as telas portadas não podem rebaixá-la**.

**Baseline a medir no A antes do porte** (o A nunca foi medido): rodar `scripts/medir_desempenho.py` do B adaptado sobre as rotas do A com dados reais — lista de solicitações, detalhe, dashboard, painel coffee — para ter números de comparação pós-porte.

**Riscos conhecidos de N+1 no código do A a corrigir no porte** (o A usa pouco `select_related` — 294 ocorrências no B contra quase nenhuma no A):

- Lista de solicitações: FKs município/tipo/órgão/região por linha → `select_related` obrigatório.
- Timeline/histórico: `usuario` por item → `select_related("usuario")`.
- Filtro de situação financeira do coffee em Python (documentado no A) — aceitável no volume atual; anotar a derivação em SQL é melhoria futura, não bloqueio.
- Dashboard: sparklines de 12 meses — agregar em uma query por série (o B tem o padrão).

**Índices no destino** (padrão B): `(area, -data_solicitacao, -id)` na solicitação; `(area, status)`; `(area, ordem, nome)` nos catálogos; manter os dois índices que o A já declarou em demandas. Cache Redis herdado (fragmentos, throttle); paginação por `core/pagination.py`.

---

## 16. Roadmap por fases, marcos e estimativas

Estimativas em **sessões de trabalho** (uma sessão ≈ um bloco de desenvolvimento com suíte verde e PR), no modelo de execução do B (uma etapa por sessão, gate por fase):

| Fase | Conteúdo | Gate de saída | Estimativa |
|---|---|---|---:|
| **F0 — Fundação** | Decisões D1–D6 ratificadas; `AreaTrabalho` criada; caracterizações do §9 escritas e verdes contra o A | Testes de caracterização passam nos dois lados | 2–3 sessões |
| **F1 — Catálogos e geografia** | Apps novos com catálogos por área; mapeamento Município→Cidade + RegiaoOperacional; ETL de catálogos | ETL idempotente com relatório; paridade de contagens | 2–3 sessões |
| **F2 — Solicitações (o 1º marco)** | Porte de `solicitacoes` (modelos, services, permissions, views, templates Cotton), notificações transversais, anexos no pipeline do B; ETL completo em homologação | **Marco 1:** fluxo completo criar→despachar→concluir funcionando no B com dados reais migrados em homologação, matriz de paridade §14 verde | 5–8 sessões |
| **F3 — Coffee break** | Porte com FK área + AuditEvent; ETL | Paridade de saldo/situação financeira | 2–3 sessões |
| **F4 — Demandas ASCOM** | Porte + importadores de planilha; ETL | Dedupe por chave preservado | 2 sessões |
| **F5 — Dashboard, Power BI e virada** | Cartões no dashboard do B; views SQL; ensaio final; janela de produção; A em somente-leitura | Power BI apontado ao B; usuários operando no B | 2–3 sessões |
| **F6 — Sinergia (pós-unificação)** | Solicitação deferida semeia `Evento` do B; geração de documento de despacho; Drive para anexos de eventos; upgrade Django 6.x | Cada item com plano próprio | contínuo |

**Total até a virada (F0–F5): ~15–22 sessões.** O maior risco de cronograma é a F2 (templates: ~27 páginas do A a reexpressar em Cotton).

**Primeiro marco entregável** (o que mostra valor primeiro): fim da **F2** — o workflow de eventos rodando dentro da plataforma B com dados reais em homologação. Tudo antes disso é preparação; tudo depois é repetição do padrão.

## 17. Maiores riscos

1. **Volume de front (F2):** reexpressar 27 páginas/18 componentes do A no design system do B é o item mais trabalhoso e o mais sujeito a regressão visual. Mitigação: fluxo roteirizado da matriz §14 + catracas de acessibilidade do B.
2. **Migração de usuários e permissões (C3/C4):** erro aqui bloqueia gente real. Mitigação: ensaios em homologação, login testado com hash migrado, mapa C4 ratificado pelo usuário antes da F0.
3. **Disciplina do B:** o `AGENTS.md` do B proíbe trabalho fora de ID de defeito — a unificação precisa entrar como **novo ciclo/plano oficial** no formato do PLANO_MESTRE (com IDs próprios), senão conflita com a governança que protege a base. Este documento é o insumo desse plano.
4. **Duas produções vivas durante a transição:** dados divergem a cada dia. Mitigação: ETL idempotente reexecutável + janela de virada curta com A em somente-leitura.
5. **Downgrade de Django (6.1→5.2) no código portado:** risco baixo (nenhum recurso 6.x detectado), mas só a suíte portada prova. Mitigação: rodar os testes do A adaptados já na F0.
6. **Anexos reprovados pela revalidação** (ClamAV/magic bytes) podem "sumir" da visão do usuário. Mitigação: quarentena relatada, nunca descarte silencioso.
7. **Envelhecimento da própria auditoria:** o `ESTADO_ATUAL_3_0.md` do B já está defasado em relação ao código — este documento também envelhecerá; datas e contagens aqui valem para 31/08/2026.

## 18. Decisões que dependem do usuário

| # | Decisão | Recomendação |
|---|---|---|
| **D1** | Ratificar a base: Central de Viagens 3 (Opção B) | Sim (evidências no §2) |
| **D2** | Tenancy do domínio de eventos: **uma** área "EVENTOS SOCIAIS" (setores viram catálogo interno para as demandas ASCOM) ou **uma área por setor** | Uma área única — o isolamento por setor do A só existe nas demandas ASCOM e é mais fielmente reproduzido por filtro de domínio do que por multiplicar tenants |
| **D3** | Destino do sistema A após a virada: somente-leitura por N meses vs desligamento | Somente-leitura por 3–6 meses, depois arquivar repositório |
| **D4** | Ordem dos módulos ASCOM: coffee antes de demandas (proposta F3→F4) ou juntos | Como proposto — coffee tem dinheiro, merece fase própria |
| **D5** | Identidade visual: adotar o design system do B com tokens da paleta institucional do A (grafite/dourado) como tema, ou manter dois visuais | Tema por tokens — o B foi construído para isso (duas camadas de token, desenho único) |
| **D6** | Recuperação de senha por e-mail na plataforma unificada (o A tem, o B recusa por política) | Adotar o fluxo do A — haverá SMTP institucional de qualquer forma para as notificações |
| **D7** | Power BI: virar as views na F5 ou manter o A como fonte até estabilizar | Virar na F5, com período de dupla checagem |

---

*Gerado a partir da leitura integral dos dois repositórios em 31/08/2026 (commit `1d0694d` no Sistema A; HEAD do dia no Sistema B). Contagens e caminhos citados referem-se a esse estado.*
