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

### Fase 1 — Cadastros de viagens ✅ (entregue)

Decisões tomadas na abertura da fase:

- **DA1 — app novo `viagens_cadastros`**, e não extensão de `cadastros`. O app existente tem um CRUD genérico por slug construído sobre `CadastroBase` (`nome` único + `ativo`); `Servidor`, `Viatura` e `TabelaDiaria` não cabem nesse molde — têm status derivado, unicidade condicional, vigência e validação de conteúdo (CPF, placa). Enfiá-los ali obrigaria a enfraquecer o CRUD que hoje serve bem aos cadastros de eventos.
- **DA2 — dois grupos, `VIAGENS_GESTOR` e `VIAGENS_OPERADOR`**, sob o módulo `VIAGENS`. Os três papéis por área do sistema de origem (ADMIN/EDITOR/LEITOR) colapsam aqui: quem tem o módulo e nenhum grupo **consulta**; o operador mantém servidores, viaturas e catálogos; só o gestor mexe na **tabela de diárias**, porque é dinheiro que vai para documento oficial.

Entregue:

- `Unidade`, `Cargo`, `Combustivel`, `Servidor`, `Viatura`, `TabelaDiaria` — sem coluna `area`, com as unicidades pareadas da origem colapsadas em **uma constraint global** cada (a versão mais forte); placa única no sistema.
- Normalização e máscaras próprias (`normalizacao.py`): o dado é guardado cru (só dígitos, placa sem hífen, nome em maiúsculas) e formatado na exibição, para a unicidade valer sobre o dado real.
- `TabelaDiaria` com vigência e percentuais de 15%/30% derivados e gravados; `vigente_em` devolve `None` em vez de inventar valor. `faixa_da_regiao()` liga as três regiões operacionais de `cadastros.Regiao` às três faixas, sem tornar o dinheiro dependente de um catálogo editável.
- Módulo `VIAGENS` no portal, CRUD completo, tela própria de diárias.
- **`Motorista` convertido em `Servidor`** e `SolicitacaoEvento.motorista` re-apontado, em três migrações (estrutura → dados → estrutura). A conversão é idempotente (`legado_origem`/`legado_pk`), reversível, funde motoristas que eram a mesma pessoa e tolera telefone repetido ou inválido no legado.
- 90 testes novos, incluindo sete que exercitam a migração de dados real pelo executor de migrações. Suíte completa verde **em SQLite e em PostgreSQL**.

Fica para depois, sem bloquear a F2: enriquecer `Municipio` (capital, lat/long) e importar a base geográfica do sistema de origem.

### Fase 2 — Roteiros e diárias ✅ (F2b, o mapa, segue opcional e em aberto)

**Entregue nesta etapa — o cálculo, que é a parte de dinheiro:**

- **Testes de caracterização primeiro**, como o plano exige: os demonstrativos do sistema oficial de solicitação de diárias (R$ 773,19, R$ 1.144,45, R$ 1.169,47, R$ 290,55, R$ 371,26) reproduzidos ao centavo antes de qualquer decisão de implementação. Eles descrevem o que a administração paga, não o que o código faz — se quebrarem, o defeito é do código.
- **Motor portado** (`viagens_roteiros/services/diarias.py`) com as três regras que os demonstrativos revelam: o período de um destino vai da *chegada* nele à *chegada* no seguinte (o tempo de estrada é faturado onde o servidor estava, em vez de sumir da conta); períodos consecutivos da mesma faixa formam **um** trecho tarifário, com um único complemento sobre a sobra somada; e a escada do resto por **duração** (≤6h nada, ≤8h 15%, ≤12h 30%, >12h uma diária cheia) — o calendário não entra.
- **Modelos** `Roteiro`, `RoteiroDestino`, `RoteiroTrecho` e `RoteiroDiariaComponente`, com as constraints de período encadeado e não-negativos defendidas pelo banco (`core/constraints.py`, reaproveitável nas fases seguintes).
- **Gravação da composição**: cada parcela guarda a vigência que a sustentou, e a vigência fica protegida contra exclusão — é o que explica um pagamento anos depois, quando os valores já forem outros. Recalcular substitui o conjunto inteiro numa transação, em vez de editar parcela existente.

Duas diferenças deliberadas em relação à origem, ambas documentadas no módulo:

- **Sem tabela de valores embutida no código.** Lá, sem vigência cadastrada o cálculo cai numa tabela fixa no módulo; aqui levanta `SemTabelaDeDiarias`. Valor de diária mora em `TabelaDiaria` — é o motivo de ela existir — e um valor congelado no código envelhece em silêncio.
- **Capitais numa tabela única** (as 27 UFs). A origem cruza a base geográfica com um mapa de reserva e mantém um teste para os dois não divergirem; aqui não há duas fontes para divergir.

**Telas entregues** (`viagens_roteiros/`), no padrão visual do A: lista com busca e filtro de situação, formulário que monta o percurso trecho a trecho num formset, e tela de detalhe que dispara o cálculo e mostra a composição parcela a parcela — cada uma com a vigência que a sustentou. O módulo "Viagens" passa a abrir nos roteiros; os cadastros viram um item da mesma navegação.

**O que só apareceu ao abrir as telas de verdade.** A suíte estava verde e o motor, correto, quando um passeio pelas páginas contra um PostgreSQL semeado revelou sete defeitos que nenhum teste de banco pegaria — todos agora com teste de regressão que falha sem o conserto:

| Defeito | Por que passava despercebido |
| --- | --- |
| Cartões do topo montados à mão com uma classe CSS inventada (`resumo-cards`) | O design system tem `grid-resumo` + `summary_card`; nada quebra, só fica feio |
| Cartões da tabela de diárias escrevendo `R$ 43.58` sobre uma tabela que dizia `R$ 43,58` | Um f-string cru não passa pela localização que o template aplica |
| Campos do formulário sem `form-controle` | O navegador desenhava controles nativos no meio de uma tela estilizada |
| Opção vazia dos selects em inglês (*"Select an option"*, padrão do Django 6.1) | O resto do sistema diz "Selecione...", via um componente que este formulário não usa |
| `min="0"` no número de servidores, que o servidor recusa | O erro só apareceria depois de enviar |
| Linha de trecho em branco virando trecho vazio | `ordem` tem `default=1`: mexer só nesse número marca a linha como alterada, contra o "linhas em branco são ignoradas" escrito na própria tela |
| Corrigir um trecho recusado criando um segundo roteiro a cada tentativa | O roteiro já fora gravado, mas o `action=""` do formulário reenviava para `/novo/` — o comentário da própria view afirmava o contrário do que o código fazia |

A lição que fica para as fases seguintes: **suíte verde não é tela conferida.** Defeito de apresentação e de formulário não aparece em teste que só olha para o banco.

**Falta para fechar o domínio:** como subfase opcional, o mapa com cálculo automático de rota (F2b, decisão DA3).

**Gate cumprido:** cálculo idêntico ao da origem nos casos de caracterização; telas exercitadas de ponta a ponta contra PostgreSQL semeado (montar, calcular, cancelar, reativar, excluir); suíte verde em SQLite e PostgreSQL.

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

| # | Decisão | Quando | Situação |
|---|---|---|---|
| DA1 | App único `viagens_*` vs estender `cadastros` existente | Início da F1 | ✅ app novo `viagens_cadastros` |
| DA2 | Grupos/perfis do domínio de viagens | F1 | ✅ `VIAGENS_GESTOR` + `VIAGENS_OPERADOR` sob o módulo `VIAGENS` |
| DA3 | Incluir F2b (mapa/ORS) ou manter km/duração manuais | Fim da F2 | aberta |
| DA4 | Destino das funções fora de escopo do B (Drive, eProtocolo, planos, OS) | Antes da F6 | aberta |
| DA5 | Hospedagem do sistema unificado (manter Windows/waitress vs VPS) | Antes da F6 | aberta |
| DA6 | Quais setores recebem o módulo `VIAGENS` (o seed não vincula nenhum) | Ao implantar a F1 | aberta |

## 5. Lições da F1 que valem para as próximas fases

- **Rodar a suíte em PostgreSQL antes de subir.** A conversão de motoristas passava em SQLite e falhava em PostgreSQL: o banco recusa `ALTER TABLE` numa tabela com eventos de gatilho pendentes, e a migração misturava, na mesma transação, a inserção dos servidores e a alteração da coluna. Em produção o `migrate` abortaria no meio. Daí a regra: **migração de dados nunca divide arquivo com migração de esquema**.
- **`max_length` do modelo valida a entrada crua do formulário**, antes de qualquer normalização — um CPF digitado com pontuação era recusado por tamanho. Campos que guardam dado normalizado precisam declarar o campo de formulário à mão, com folga.
- Testar migração de dados exige fixar o alvo de **todos** os apps envolvidos: o estado histórico de um alvo só inclui as migrações de que ele depende.
- **Data e hora vindas do banco estão em UTC** (`USE_TZ=True`). Formatá-las sem localizar faria uma saída às 08:00 sair como 11:00 no documento. Todo ponto que exibe horário precisa passar por `timezone.localtime` — e um teste com data ciente do fuso é o que impede a regressão.

## 6. F1 — mudanças de comportamento visíveis e pendências

A conversão de motoristas muda coisas que o usuário percebe. Nada disso é defeito, mas convém saber antes de implantar:

- **O campo "Motorista" da solicitação lista quem exerce o papel**: servidor com cargo MOTORISTA ou designado como condutor de alguma viatura. Sem esse recorte, a tela passaria a expor o quadro inteiro de servidores a qualquer solicitante, inclusive a quem não tem o módulo de viagens. Cadastrar um motorista novo exige, portanto, dar-lhe o cargo MOTORISTA ou vinculá-lo a uma viatura.
- **Nomes de motorista passam a aparecer em MAIÚSCULAS** nas telas e no CSV exportado, porque é assim que o domínio de viagens grava pessoas. Os cadastros de eventos seguem como estavam.
- **`importar_planilha --limpar` não apaga mais os servidores** criados por importações anteriores (eles agora vivem em outro app). Apaga o que sempre apagou dos cadastros de eventos.
- O módulo `VIAGENS` nasce **sem setor vinculado**: ninguém, além do superusuário, enxerga as telas até que um administrador ligue o setor ao módulo (decisão DA6).

Achados da revisão adversarial que **não** foram corrigidos nesta entrega, por serem menores que o risco de ampliar o PR:

- A reversão da conversão devolve os nomes já normalizados (em maiúsculas), não a grafia original — a informação de caixa do cadastro antigo não é recuperável, porque não é guardada.
- Violação de unicidade que escape da validação do formulário (dois operadores gravando ao mesmo tempo) ainda aparece como erro técnico, não como mensagem de campo.
- A busca da lista compara o termo digitado com o dado normalizado: procurar CPF com pontuação não encontra. Buscar por nome funciona (a comparação ignora caixa).
