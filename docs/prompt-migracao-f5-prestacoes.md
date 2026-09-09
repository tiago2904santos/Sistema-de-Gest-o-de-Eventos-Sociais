# Prompt para o Codex — Fase 5 da unificação: prestações de contas e assinatura eletrônica

> Só comece depois que as **Fases 3 e 4** estiverem entregues e verdes: a prestação nasce de um ofício e usa o núcleo documental.
> Esta fase tem duas metades. Entregue a **F5a** inteira antes de tocar na **F5b**.
> Copie tudo abaixo da linha e cole no Codex.

---

## 1. Quem é você nesta tarefa

Você é um desenvolvedor Django sênior no repositório **Sistema de Gestão de Eventos Sociais** da Polícia Civil do Paraná (PCPR), em `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos`.

O domínio do **Gerenciador de Viagens** (Central de Viagens 3, daqui em diante **GV**) está sendo portado para cá fase a fase, conforme `docs/PLANO_MESTRE_UNIFICACAO.md`. As fases 0 a 4 já foram entregues. **Sua tarefa é a Fase 5: a prestação de contas da viagem — relatório técnico, diário de bordo, comprovantes, consolidação e assinatura eletrônica.**

Código do GV, **somente leitura**:

```
C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens
```

**Nunca grave, edite ou rode nada dentro dessa pasta.**

Esta é a maior superfície do sistema de origem (cerca de 18 mil linhas) e a que mais mexe com arquivo e com gente de fora do sistema. Porte devagar, na ordem indicada, e não invente regra: o que está lá foi aprendido com prestação devolvida.

## 2. Ambiente e comandos

- Django 6.1, Python 3.14, virtualenv em `.venv`. Windows.
- Interpretador: `.venv\Scripts\python.exe`. Testes: `.venv\Scripts\python.exe manage.py test`.
- Servidor: `.venv\Scripts\python.exe manage.py runserver 8021` — **sempre com porta**.
- Banco de dev: PostgreSQL `eventos_sociais`, com dados reais. Nada destrutivo.
- Antes de escrever: rode a suíte inteira e **anote o número de testes**; rode `makemigrations --check --dry-run`; leia os relatórios das fases 3 e 4 em `docs/`.

## 3. O que já está pronto e você vai usar

| De onde | O que |
| --- | --- |
| F1 | `viagens_cadastros`: `Servidor`, `Viatura`, `Unidade`, `TabelaDiaria` |
| F2 | `viagens_roteiros`: `Roteiro`, destinos, trechos, componentes de diária e o motor de cálculo |
| F3 | `documentos`: façade DOCX/PDF, `DocumentoArtefato`, cadeia de motores, `pdf_overlay` |
| F4 | `viagens_oficios`: `Oficio` numerado, justificativa; `viagens_termos` |
| Base | módulo `VIAGENS`, grupos `VIAGENS_GESTOR`/`VIAGENS_OPERADOR`, Design System V3.2, `core/listagens.py`, `core/constraints.py`, auditoria por signals |

Se a Fase 3 tiver deixado `documentos/services/pdf_overlay.py` de fora (ela podia), **porte agora**: a assinatura e o carimbo dependem dele.

## 4. O que você vai entregar

**F5a — a prestação.** Depois que a viagem acontece, o operador abre a prestação do ofício e consegue: registrar o diário de bordo do motorista, escrever o relatório técnico de cada servidor, anexar comprovantes e o despacho assinado, carimbar o número de solicitação no ofício que voltou do protocolo, baixar tudo consolidado e finalizar.

**F5b — a assinatura.** O relatório técnico e o diário de bordo podem ser assinados por quem não tem conta no sistema, por um link com prazo, sem login.

## 5. Decisões já tomadas — não reabra

1. **Um app novo `viagens_prestacoes`**, com o diário de bordo dentro dele (no GV existe uma pasta `diario_bordo` vazia; o modelo mora em `prestacoes_contas`).
2. **Sem multi-tenancy**: todo `area`, `AreaScopedManager`, `all_objects`, `get_current_area` sai.
3. **Sem Drive, sem eProtocolo, sem Celery.** Geração e consolidação são síncronas, pela façade da F3.
4. **A ordem das etapas é: Diário de Bordo primeiro, Relatório Técnico depois.** O GV inverteu isso recentemente e de propósito (commit `90ccdeea`); porte o estado atual, não o antigo.
5. **`PrestacaoServidor` tem remoção reversível** (o manager de ativos do GV): servidor tirado da prestação some da tela, mas o que ele já preencheu não é apagado.
6. **A assinatura é a do GV, não a do plano.** O `PLANO_MESTRE_UNIFICACAO.md` fala em "token cifrado Fernet"; o código atual usa token aleatório (`secrets.token_urlsafe(32)`), guarda no banco só o **hash SHA-256**, com expiração em dias. Porte o código, e corrija a frase do plano no seu relatório.
7. **O carimbo do número de solicitação é por âncora, não por coordenada.** O sistema gera o mesmo ofício com os números, lê onde cada um caiu, e transporta a posição para o PDF assinado usando o nome do servidor como âncora. É isso que faz o carimbo continuar certo quando o protocolo acrescenta cabeçalho ou página. Não substitua por coordenada fixa.
8. **O texto do carimbo não é guardado**: sai de `numero_solicitacao` na hora de desenhar, para não existirem duas cópias que divirjam.

## 6. F5a — mapa do porte

Origem: `Gerenciador de Viagens\prestacoes_contas\`. Destino: `viagens_prestacoes\`.

### 6.1 Modelos (`models.py`)

| Modelo | Papel | Observação de porte |
| --- | --- | --- |
| `PrestacaoContas` | uma por ofício (1:1) | tire `area`; mantenha `roteiro_ajustado` — a cópia editável do roteiro, que é o que de fato aconteceu na viagem, sem alterar o ofício |
| `PrestacaoServidor` | a parte individual de cada servidor | mantenha o manager de ativos e a remoção reversível |
| `PrestacaoDocumentoAnexo` | comprovantes e despacho | validação de extensão e tamanho no padrão daqui (`solicitacoes/forms.py`, 10 MB) |
| `CarimboSolicitacao` | posição do número no PDF | ver §5.7 |
| `RelatorioTecnico` + `ModeloTextoRelatorioTecnico` | RT e seus textos-modelo | |
| `DiarioBordo` + `DiarioBordoTrecho` | diário do motorista, com quilometragem | |
| `AssinaturaDocumento` | só entra na F5b | |

Estados da prestação: `pendente`, `em_preenchimento`, `enviada`, `aprovada`, `reprovada`. Porte as transições como estão.

### 6.2 Serviços

Porte adaptando: `services.py`, `rt_services.py`, `diario_services.py`, `anexo_services.py`, `carimbo_services.py`, `download_services.py`, `solicitacao_services.py`, `selectors.py`, `presenters.py`, `signals.py`, `view_common.py`, `forms.py`.

Fica de fora: `async_documents.py` e tudo que fala com Drive.

Dos comandos de manutenção, porte os que fazem sentido sem tenancy: `sincronizar_prestacao_servidores`, `limpar_arquivos_orfaos`, `diagnosticar_roteiros_ajustados`, `mesclar_roteiros_ajustados_identicos`.

### 6.3 Documentos e consolidação

Modelos `.docx`/`.xlsx` a copiar em binário de `documentos\resources\` para `documentos/resources/`, com os goldens correspondentes:

- `relatorio-tecnico.docx`
- `diario_bordo.xlsx`

O diário sai de planilha: se a Fase 3 não portou `services/adapters/xlsx_render.py` e `excel_pdf.py`, porte agora. Registre os dois tipos novos no registro de tipos da F3 e acrescente a FK de origem em `DocumentoArtefato` (migração de esquema própria).

O download consolidado junta os PDFs da prestação num arquivo só, na ordem definida pelo GV, usando `pypdf`. Preserve essa ordem: ela é a ordem em que a administração confere.

### 6.4 Telas (Design System V3.2)

| Tela | Padrão de referência |
| --- | --- |
| Lista de prestações com filas por status | `templates/pages/solicitacoes/lista.html` |
| Prestação por etapas (diário → RT → comprovantes → finalização) | `templates/pages/solicitacoes/form.html` + editor de roteiro |
| Painel do servidor dentro da prestação, com downloads | `templates/pages/solicitacoes/detalhe.html` |
| Modelos de texto do RT | `templates/pages/cadastros/{lista,form}.html` |

Regras de front: nada de `<select>` ou `<input type=date>` crus (use os componentes do sistema); campo oculto numérico ou de data nunca passa por valor localizado; a lateral fixa rola com a página.

## 7. F5b — assinatura eletrônica por link público

Só comece com a F5a verde. É a única parte do sistema que **um anônimo acessa**; trate como superfície pública.

Fluxo do GV, a ser preservado:

1. Da tela do documento, o operador emite um link com prazo (padrão de 7 dias) para o RT de um servidor ou para o diário de bordo do motorista.
2. O signatário abre o link, confirma identidade com os primeiros dígitos do CPF e o nome.
3. Assina, escolhendo entre nome em fonte manuscrita ou desenho à mão, renderizado como PNG transparente no navegador.
4. O servidor **carimba** esse PNG sobre o snapshot do PDF de origem (`arquivo_origem`) e guarda o resultado em `arquivo_assinado`. O carimbo é `reportlab` + `pypdf`, independente do motor de geração.
5. O documento assinado ganha código de verificação e passa a ser o arquivo oficial.

Porte `assinatura_services.py`, `assinatura_views.py`, `signature_views.py` e o modelo `AssinaturaDocumento`.

Exigências de segurança, que valem mesmo que o GV não tenha todas — se você acrescentar alguma, diga no relatório:

- O banco guarda **hash** do token, nunca o token.
- Link expirado ou revogado responde igual a link inexistente (sem revelar se o documento existe).
- A confirmação de identidade tem limite de tentativas.
- A página pública não vaza CPF completo, telefone nem lista de servidores.
- Assinar duas vezes não empilha carimbo: a segunda assinatura revoga a primeira ou é recusada, conforme o GV faz.
- A rota pública fica fora do middleware de módulo, mas com throttle. Confira que `accounts.modulos.AutorizacaoPorModuloMiddleware` e o middleware de troca de senha obrigatória não a bloqueiam.

Dependências novas prováveis: `reportlab` e `qrcode` (se o código de verificação usar QR). Declare no `requirements.txt` com as faixas do GV.

## 8. Armadilhas conhecidas deste repositório

- **Nunca edite arquivo com acento usando `Set-Content` / `Get-Content` do PowerShell.** Use as ferramentas de escrita ou um script Python.
- **Rode a suíte em PostgreSQL e em SQLite.**
- **Data e hora do banco estão em UTC**: tudo que vai para documento passa por `timezone.localtime`.
- **Dinheiro pela localização do Django**, nunca por f-string.
- **Upload é superfície de ataque**: valide extensão, tamanho e conteúdo; arquivo nunca é servido por `MEDIA_URL` — sempre por view com permissão, como em `solicitacoes.views.baixar_anexo`.
- **Transação e arquivo não se misturam bem**: gravar arquivo dentro de transação que pode rolar deixa órfão em disco. O GV tem testes específicos disso (`test_*_transacao_be14.py`) — porte-os.
- **Suíte verde não é tela conferida.**

## 9. Testes

Porte de `Gerenciador de Viagens\prestacoes_contas\` (os testes estão soltos na raiz do app, não em `tests/`), adaptando: `test_anexos.py`, `test_anexo_assinado_tipos.py`, `test_anexo_assinado_recusa.py`, `test_upload_validacao.py`, `test_relatorio_tecnico.py`, `test_diaria_rt.py`, `test_diaria_por_servidor.py`, `test_diario_motorista.py`, `test_diario_km_novo116.py`, `test_carimbo.py`, `test_finalizacao.py`, `test_listagem.py`, `test_solicitacao.py`, `test_remocao_equipe.py`, `test_modelos_texto.py`, `test_retorno_seguro.py`, `test_pdf_final_pendencias.py`, os três `test_*_transacao_be14.py`, `test_limpar_arquivos_orfaos.py`, `test_diagnosticar_roteiros_ajustados.py`, `test_mesclar_roteiros_ajustados_identicos.py`, `tests.py`, `test_helpers.py` e, na F5b, `test_assinatura_publica.py` e `tests_assinatura.py`.

Não porte: `test_sede_por_area.py`, `test_componentes_v2.py` e `test_orcamento_de_queries.py` (dependem de área ou da régua de desempenho do GV, que não existe aqui).

Obrigatórios, além dos portados:

1. Remoção reversível: tirar um servidor da prestação esconde, não apaga; recolocar recupera o que ele preencheu.
2. Consolidado: a ordem dos PDFs no arquivo único é a esperada e o total de páginas bate.
3. Carimbo: o número cai ao lado do nome certo mesmo quando o PDF assinado tem uma página a mais no começo.
4. Assinatura: link expirado, link revogado e token inválido respondem igual; tentativa de identidade errada é limitada; assinar grava o PDF carimbado e o código de verificação.
5. Autorização: sem o módulo `VIAGENS` dá 403 em tudo, menos na rota pública de assinatura.
6. Arquivo órfão: falha no meio da gravação não deixa arquivo solto em `media/`.

## 10. Gates de saída

1. Suíte inteira verde, com número de testes maior que o baseline anotado no início; verde também em SQLite.
2. `makemigrations --check --dry-run` limpo; `manage.py check` sem avisos novos.
3. Ciclo completo exercitado na interface contra o banco de dev: ofício → prestação → diário de bordo → relatório técnico → comprovantes → consolidado → finalizar.
4. Na F5b: um link emitido, aberto em janela anônima, assinado, e o PDF resultante aberto para conferência.
5. Goldens de `relatorio-tecnico.docx` e `diario_bordo.xlsx` verdes.
6. Nenhum arquivo do repositório do GV alterado.

## 11. Como entregar

Commits pequenos, nesta ordem, cada um com a suíte verde:

1. Modelos da prestação + migração + seletores + testes de domínio.
2. Diário de bordo (etapa 1) com trechos e quilometragem.
3. Relatório técnico e modelos de texto.
4. Anexos e validação de upload.
5. Carimbo do número de solicitação.
6. Downloads e consolidação.
7. Telas V3.2, navegação e autorização.
8. **Só então** a F5b: assinatura, rota pública, throttle e testes de segurança.
9. Comandos de manutenção, auditoria, documentação e relatório.

Relatório final em `docs/`, no estilo das seções de fase do plano mestre, incluindo a correção sobre o mecanismo de assinatura (§5.6) e o que a Fase 6 vai precisar migrar desta fase. Atualize a seção "Fase 5" do `PLANO_MESTRE_UNIFICACAO.md`.

**Não faça commit nem push sem pedir.**

## 12. Pare e pergunte se

- a consolidação de PDFs exigir uma dependência de sistema que a máquina de produção (Windows, waitress) não tem;
- o carimbo por âncora não achar o nome do servidor num PDF real de protocolo;
- a rota pública precisar ficar fora de alguma proteção global do projeto;
- algo da prestação depender de Drive, eProtocolo, plano de trabalho ou ordem de serviço.
