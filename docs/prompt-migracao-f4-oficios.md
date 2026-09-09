# Prompt para o Codex — Fase 4 da unificação: ofícios, justificativas e termos

> Só comece esta fase depois que a **Fase 3 (núcleo documental)** estiver entregue e verde: nada aqui gera documento sem ela.
> Copie tudo abaixo da linha e cole no Codex.

---

## 1. Quem é você nesta tarefa

Você é um desenvolvedor Django sênior no repositório **Sistema de Gestão de Eventos Sociais** da Polícia Civil do Paraná (PCPR), em `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos`.

Este repositório é a base de uma unificação em andamento: o domínio do **Gerenciador de Viagens** (Central de Viagens 3, daqui em diante **GV**) está sendo portado para dentro dele, fase a fase, conforme `docs/PLANO_MESTRE_UNIFICACAO.md`. As fases 0 a 3 já foram entregues. **Sua tarefa é a Fase 4: o ofício de autorização de viagem, a justificativa que o acompanha e os termos de autorização dos servidores.**

O código do GV está disponível **somente para leitura** em:

```
C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens
```

**Nunca grave, edite ou rode nada dentro dessa pasta.**

Esta é a fase em que o sistema passa a produzir **documento oficial que vira dinheiro e vai para o eProtocolo**. Duas consequências práticas: porte a regra do GV como ela é, e não invente atalho em nada que numere, autorize ou pague.

## 2. Ambiente e comandos

- Django 6.1, Python 3.14, virtualenv em `.venv`. Windows.
- Interpretador: `.venv\Scripts\python.exe` (sempre esse).
- Testes: `.venv\Scripts\python.exe manage.py test`
- Servidor: `.venv\Scripts\python.exe manage.py runserver 8021` — **sempre com porta** (produção roda waitress na 8000).
- Banco de desenvolvimento: PostgreSQL `eventos_sociais`, com **dados reais**. Nada de `flush`, reimportação ou comando destrutivo.
- O GV roda em Django 5.2 / Python 3.12; o código portado tem que rodar em 6.1 / 3.14.

Antes de escrever qualquer linha: rode a suíte inteira e **anote o número de testes**; rode `makemigrations --check --dry-run` e confirme que está limpo; leia `docs/PLANO_MESTRE_UNIFICACAO.md` (seções 2 e 5) e o relatório da Fase 3 em `docs/`.

## 3. O que já está pronto e você vai usar

| De onde | O que | Como você usa |
| --- | --- | --- |
| F1 | `viagens_cadastros`: `Servidor`, `Viatura`, `Unidade`, `Cargo`, `Combustivel`, `TabelaDiaria` | são os cadastros que o ofício referencia — **não crie equivalentes** |
| F2 | `viagens_roteiros`: `Roteiro`, destinos, trechos, componentes de diária, editor completo com mapa | o ofício aponta para um roteiro e herda o cálculo de diárias dele |
| F3 | `documentos`: façade de geração, registro de tipos, cadeia de motores DOCX/PDF, `DocumentoArtefato` | você **não** gera documento na mão: monta o payload e chama a façade |
| Base | módulo `VIAGENS` (`accounts/modulos.py`), grupos `VIAGENS_GESTOR` e `VIAGENS_OPERADOR` | autorização; nada de grupo novo |
| Base | Design System V3.2 (`static/css/ds-v32.css` + bridge, `templates/layouts/app_shell_v32.html`) | toda tela nova nasce aqui dentro |
| Base | `core/listagens.py`, `core/constraints.py`, `core/models.py` (`ModeloTemporal`, `ModeloCancelavel`), `auditoria/signals.py` | reaproveite em vez de recriar |

## 4. O que você vai entregar

Ao final desta fase, um operador com o módulo `VIAGENS` consegue, pela interface:

1. Criar um ofício de autorização de viagem, percorrendo as etapas de viajantes, transporte, roteiro, justificativa e resumo.
2. Gerar o ofício em DOCX e PDF, com número reservado sem colisão e sem buraco não intencional na sequência.
3. Gerar o termo de autorização de cada servidor, individualmente e em lote, na variante certa do modelo.
4. Cancelar, arquivar e reemitir, com trilha de auditoria.
5. Manter os catálogos de motivo de ofício e de modelos de justificativa.

## 5. Decisões já tomadas — não reabra

1. **Dois apps novos**: `viagens_oficios` (ofício, numeração, justificativa e os catálogos dos dois) e `viagens_termos` (termo de autorização, inclusive o termo avulso sem ofício). A justificativa é 1:1 com o ofício e não tem vida própria: fica junto. O termo tem cadastro próprio e telas próprias no GV: fica separado.
2. **Sem multi-tenancy.** Todo `area`, `AreaScopedManager`, `all_objects`, `get_current_area` e `default_manager_name` sai. Onde a unicidade do GV é `(area, ano, numero)`, aqui é `(ano, numero)` — a versão mais forte, como já foi feito na F1.
3. **Sem `eventos.Evento`.** O app agrupador do GV está fora do escopo ratificado: a FK `evento` do ofício não vem. O ofício se liga a `viagens_roteiros.Roteiro`, a `viagens_cadastros.Servidor` (M2M de viajantes), a `Viatura` e a `Unidade` solicitante.
4. **Sem planos de trabalho, ordens de serviço, Drive e eProtocolo.** Se um campo do ofício só existe para alimentar essas funções, ele não vem — anote no relatório.
5. **Numeração portada como está**, com as duas implementações: `pg_advisory_xact_lock` no PostgreSQL e `select_for_update` como alternativa. O sistema de dev pode cair em SQLite, e a suíte roda nos dois.
6. **Geração síncrona**, pela façade da F3. Nada de Celery, `async_documents.py` ou fila.
7. **As telas são reexpressas no Design System V3.2**, com views baseadas em função (o padrão deste repositório). O wizard em etapas do GV vira o formulário longo com lateral de etapas que já existe em `templates/pages/solicitacoes/form.html` e no editor de roteiro.

## 6. Mapa do porte

### 6.1 Numeração (faça primeiro — o resto depende)

| Origem | Destino |
| --- | --- |
| `core/numeracao.py` | `core/numeracao.py` |
| `oficios/models.py::ConfiguracaoNumeracaoOficio`, `OficioNumeroLacuna` | `viagens_oficios/models.py` |
| `oficios/services.py::reservar_numero_oficio` e o que ele chama | `viagens_oficios/services.py` |

Preserve: reserva dentro de transação, reuso da menor lacuna, piso configurável, contador por ano, e a constante com o nome da constraint que o módulo de numeração compara contra o metadado da exceção (`CONSTRAINT_NUMERO_OFICIO` no GV). Excluir ofício numerado **abre lacuna** que o próximo ofício reaproveita — é assim de propósito, porque a administração exige sequência sem furo.

### 6.2 Ofício

`oficios/models.py::Oficio` → `viagens_oficios/models.py`, herdando de `core.ModeloTemporal` e `core.ModeloCancelavel` (no lugar de `TimeStampedModel`/`CancelavelModel` do GV).

Preserve os estados (`RASCUNHO`, `GERADO`, `ARQUIVADO`, e `FINALIZADO` como legado), as opções de custeio, o snapshot do efetivo considerado nas diárias (`diarias_quantidade_servidores`, que não muda quando um servidor some do cadastro depois), a M2M separada de servidores com termo de autorização, o porte de armas, o protocolo normalizado e a normalização de espaços/caixa dos textos.

Da camada de serviço e apresentação, porte adaptando: `services.py`, `selectors.py`, `presenters.py`, `docxtpl_context.py`, `document_generation.py`, `documents.py`, `catalogs.py`, `checks.py`, `forms.py`, `picker.py`, `view_helpers.py`.

Deixe de fora: `api_views.py`, `card_menu_views.py`, `card_rendering.py`, `route_views.py` (mapa já existe na F2), `wizard_document_views.py` na parte assíncrona, e tudo que fala com Drive ou eProtocolo.

### 6.3 Justificativa

`justificativas/` → dentro de `viagens_oficios`. Vêm `Justificativa` (1:1 com o ofício), `ModeloJustificativa` (com modelo padrão), `services.py`, `selectors.py`, `forms.py` e as telas de catálogo de modelos. As rotas legadas de redirecionamento do GV não vêm.

### 6.4 Termos de autorização

`termos/` → `viagens_termos`. Vem `TermoAutorizacao` com o que o GV chama de valores efetivos (`periodo_efetivo`, `destino_efetivo`: o termo herda do ofício e só sobrescreve o que foi preenchido nele). Vêm a geração individual e em lote, a resolução da variante do modelo (com viatura, sem viatura, automático), o preview e os downloads. `async_documents.py` não vem.

Copie de `Gerenciador de Viagens\documentos\resources\` para `documentos/resources/`, em binário: `termo_autorizacao_automatico.docx` e `termo_autorizacao_automatico_sem_viatura.docx`, com os golden files correspondentes de `documentos\tests\golden\`.

### 6.5 O que muda no app `documentos` da F3

A F3 deixou combinado que as FKs de origem entram agora. Acrescente a `DocumentoArtefato` as FKs opcionais para `viagens_oficios.Oficio` e `viagens_termos.TermoAutorizacao`, em **migração de esquema própria** (migração de dados nunca divide arquivo com migração de esquema). Registre os tipos documentais novos no registro da F3, se algum faltar.

### 6.6 Autorização, navegação e auditoria

- Todas as rotas exigem o módulo `VIAGENS`. Criar e editar ofício, justificativa e termo é do `VIAGENS_OPERADOR`; quem tem o módulo e nenhum grupo apenas consulta. Configurar a numeração (piso, contador, ano) é do `VIAGENS_GESTOR` — mexer nisso é mexer na sequência oficial.
- Acrescente os itens de navegação do módulo `VIAGENS` em `viagens_roteiros/apps.py` (ou onde o módulo é registrado): Ofícios e Termos entram ao lado de Roteiros e Cadastros.
- Inclua `"viagens_oficios"` e `"viagens_termos"` em `APPS_AUDITADOS` (`auditoria/signals.py`).

## 7. Telas

Reexpressas no V3.2, sem inventar composição nova:

| Tela | Padrão de referência |
| --- | --- |
| Lista de ofícios (busca, filtros de status/ano, filas) | `templates/pages/solicitacoes/lista.html` |
| Ofício em edição, por etapas | `templates/pages/solicitacoes/form.html` + editor de roteiro (`templates/pages/viagens_roteiros/form.html`) |
| Detalhe/resumo do ofício com ações e documentos gerados | `templates/pages/solicitacoes/detalhe.html` |
| Catálogos (motivos, modelos de justificativa) | `templates/pages/cadastros/{lista,form}.html` |
| Termos: lista, formulário e downloads | listagem + formulário do mesmo conjunto |

Regras de front que valem aqui:

- **Nunca `<select>` ou `<input type=date>` crus**: use `components/select.html`, `components/input.html` com `tipo="date"` e `components/date_range.html`, que o `app.js` transforma nos controles do sistema. O usuário rejeita o widget nativo do navegador.
- Município sempre com o estado que o filtra (`data-parent-value` + `dependente_de`).
- Campo oculto numérico ou de data que o JS lê ou reenvia nunca passa por valor localizado: datas em ISO, números como string crua.
- A lateral fixa rola com a página; só a barra de ações fica presa no rodapé.

## 8. Armadilhas conhecidas deste repositório

- **Nunca edite arquivo com acento usando `Set-Content` / `Get-Content` do PowerShell** — corrompe o UTF-8. Use as ferramentas de escrita ou um script Python.
- **Rode a suíte em PostgreSQL e em SQLite.** A F1 passou em SQLite e quebrou em PostgreSQL no `migrate`.
- **Data e hora do banco estão em UTC** (`USE_TZ=True`): tudo que vai para documento passa por `timezone.localtime`, senão a saída às 08:00 vira 11:00 no papel assinado.
- **Dinheiro formatado por f-string sai errado** (`R$ 43.58` num sistema que escreve `R$ 43,58`). Use a localização do Django.
- **`max_length` do modelo valida a entrada crua do formulário**, antes de qualquer normalização.
- **Formset com ordem única exige cuidado**: veja `FormSetTolerante` e `_ordens_afastadas` em `viagens_roteiros/` antes de escrever qualquer formset com chave composta.
- **Suíte verde não é tela conferida.** Abra cada tela nova no navegador contra o banco de dev antes de dizer que está pronta.

## 9. Testes

Testes viajam com o código, no mesmo commit. Porte, adaptando, de `Gerenciador de Viagens\oficios\tests\`, `justificativas\tests\` e `termos\tests\` tudo que não dependa de área, Drive, eProtocolo, Celery ou dos apps fora de escopo.

Obrigatórios, mesmo que você precise escrevê-los do zero:

1. **Numeração sob concorrência**: duas reservas simultâneas não produzem o mesmo número (teste transacional em PostgreSQL, com o caminho `select_for_update` exercitado à parte).
2. **Lacuna**: excluir o ofício do meio e criar outro reaproveita o número, sem furar a sequência.
3. **Ciclo completo**: criar rascunho, percorrer as etapas, gerar DOCX e PDF, arquivar, cancelar e reativar.
4. **Termo em lote**: um ofício com N servidores gera N termos, cada um com o servidor certo, na variante certa do modelo.
5. **Valores efetivos do termo**: o que não foi preenchido no termo vem do ofício; o que foi preenchido prevalece.
6. **Autorização**: sem o módulo `VIAGENS` dá 403; sem o grupo de operador não cria nem edita; a numeração só o gestor configura.
7. **Snapshot do efetivo**: excluir um servidor do cadastro depois não muda o total de diárias já registrado no ofício.

## 10. Gates de saída

1. Suíte inteira verde, com número de testes **maior** que o baseline anotado no início.
2. Mesma suíte verde em SQLite.
3. `makemigrations --check --dry-run` limpo; `manage.py check` sem avisos novos.
4. Um ofício real criado de ponta a ponta pela interface, contra o banco de dev, com DOCX e PDF gerados e abertos para conferência — inclusive o termo de autorização de cada servidor.
5. Golden files dos dois modelos novos verdes.
6. Nenhum arquivo do repositório do GV alterado.

## 11. Como entregar

Commits pequenos, nesta ordem, cada um com a suíte verde:

1. `core/numeracao.py` + modelos de numeração + testes de concorrência e lacuna.
2. Modelo `Oficio` + migração + serviços e seletores + testes de domínio.
3. Justificativa e catálogos de motivo/modelo.
4. Contexto docxtpl + geração pela façade da F3 + FKs novas em `DocumentoArtefato`.
5. `viagens_termos` + modelos `.docx` novos + goldens + geração individual e em lote.
6. Telas V3.2, navegação do módulo e autorização.
7. Auditoria, documentação e relatório.

Ao final, escreva em `docs/` um relatório curto no estilo das seções de fase do plano mestre: o que entrou, o que ficou de fora e por quê, divergências encontradas em relação ao GV, o que a Fase 5 vai precisar mexer aqui, e o número de testes antes e depois. Atualize a seção "Fase 4" do `PLANO_MESTRE_UNIFICACAO.md`.

**Não faça commit nem push sem pedir.** Defeito encontrado no código existente vai para o relatório, não para uma correção de passagem.

## 12. Pare e pergunte se

- um campo do ofício só fizer sentido com `Evento`, plano de trabalho, ordem de serviço, Drive ou eProtocolo;
- a numeração exigir comportamento que só funciona em PostgreSQL e a suíte precisar rodar em SQLite;
- um modelo `.docx` exigir variável que não existe em nenhum cadastro deste sistema;
- o porte exigir mudar comportamento de algo que já está em produção aqui.
