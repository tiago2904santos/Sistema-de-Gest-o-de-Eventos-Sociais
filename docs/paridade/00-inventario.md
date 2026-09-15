# Meta 0 — Inventário de paridade das telas

**Estado: inventário técnico preparado; Meta 0 ainda não encerrada.** As 161 declarações de rota da origem foram mapeadas, incluindo aliases e um padrão duplicado. Nenhuma tela está certificada como fiel sem a comparação visual exigida pelo pedido.

## Régua e evidência

- Origem: leitura estática dos seis `urls.py`, sem importar ou executar código do GV. A fotografia está em `rotas-origem.json`, com linhas e SHA-256 de cada arquivo.
- Destino: resolução efetiva das URLs pelo Django; fotografia em `rotas-destino.json`. O mapeamento individual revisável está em `mapeamento.json`. `validacao-inventario.json` registra a cobertura: 161 IDs em 161 linhas, 138 referências de destino resolvidas pelo Django e seis hashes da origem conferidos; essa validação não afirma paridade visual.
- Classificação inicial: 138 correspondências incompletas ou com fidelidade ainda não comprovada; 21 rotas sem correspondente; duas rotas de ordem de serviço fora do escopo expresso. Zero rotas certificadas como fiéis.
- Um endereço genérico pode atender várias rotas de origem. A existência da view não comprova equivalência de campos, mensagens, permissões, estados ou ações. Endpoints auxiliares permanecem na régua mesmo quando o comportamento atual usa outra técnica.
- Foram lidos os sete documentos de referência solicitados. Eles orientam a inspeção, mas não substituem as telas: alguns registram estados históricos anteriores ao código atual.

## Contagem conferida em 10/09/2026

| App da origem | Declarações de rota | Correspondência principal no destino | Padrões atuais no destino |
|---|---:|---|---:|
| cadastros | 32 | viagens_cadastros; configuração em viagens_oficios; municípios em cadastros | 9 no app de viagens |
| roteiros | 11 | viagens_roteiros | 14 |
| oficios | 31 | viagens_oficios | 15 |
| justificativas | 12 | catálogo e campos em viagens_oficios | compartilhados com os 15 acima |
| termos | 23 | viagens_termos e geração por ofício | 12 no app de termos |
| prestacoes_contas | 52 | viagens_prestacoes e viagens_assinaturas | 48 internos + 6 públicos |

Os cinco apps de viagens e o namespace público de assinaturas somam **100 padrões atuais**, antes de contar os cadastros gerais e outros auxiliares. A referência a cinco rotas de Prestações no pedido não descreve mais o código: a F5 já ampliou esse conjunto. Isso não reduz a dívida de interface.

## Bloqueios e decisões antes de avançar

1. **Acesso visual:** resolvido nos dois sistemas. GV em `http://127.0.0.1:8000/`, Eventos em `http://localhost:8021/`, com sessões autenticadas separadas. A sigla DPC exibida no GV foi conferida como **área 1 — policia Civil** na lista de áreas. As seis comparações iniciais foram ampliadas para **46 pares de capturas**, **22 entradas com observação** e **16 fichas de quatro quadros**, detalhadas em [00-observacao-visual.md](00-observacao-visual.md). Nenhuma ficha certifica paridade. A lista autenticada do GV mostrou 174 servidores e 59 ofícios. A captura anterior sem área confirmada foi identificada como preliminar e não comprova o contexto da área 1.
2. **Configuração e módulos excluídos:** a tela da origem tem assinantes de Plano de Trabalho e de Ordem de Serviço. **Decisão do usuário em 10/09/2026: manter a meta pendente dessa decisão.** A omissão não foi autorizada; a Meta 1 não poderá ser fechada enquanto isso estiver em aberto. As duas rotas documentais exclusivamente de OS já estão identificadas como fora de escopo pelo próprio pedido.
3. **Permissão das diárias:** `cadastros/views.py` da origem permite o POST de diárias somente a superusuário. O destino permite também VIAGENS_GESTOR. **Adaptação autorizada pelo usuário em 10/09/2026: manter a permissão atual daqui e documentar.** VIAGENS_GESTOR continua autorizado; nenhuma permissão foi alterada.
4. **Geografia:** municípios existem no cadastro administrativo de Eventos; estados não têm CRUD público correspondente. A permissão administrativa e a composição devem ser resolvidas na Meta 1, sem alterar acesso em produção por inferência.
5. **Alias sombreado:** `justificativas:<pk>/excluir/` aparece duas vezes, com callbacks distintos. O segundo padrão continua inventariado; a decisão sobre esse comportamento permanece aberta, sem reproduzir ou eliminar um possível defeito silenciosamente.
6. **Diárias na origem:** pertencem à tela de configuração por aba, não a uma rota CRUD autônoma entre as 32. No destino existem quatro rotas próprias. A Meta 1 deve comparar formulário, vigências, histórico e modo de consulta, sem criar rotas apenas para igualar contagens.

## Prova e sequência

Cada tela receberá um arquivo `<app>-<tela>.md`, com as quatro tabelas de campos, listagem, ações, estados/mensagens e as capturas reais de ambos os sistemas em `imagens/`. Situações por elemento: **igual**, **adaptado** com razão, ou **ausente** com autorização para permitir o fechamento. 14 fichas de cadastros já contêm observações reais; suas ausências não autorizadas mantêm as pendências abertas. Estados ainda não exercitados ficam explicitamente pendentes. Este inventário não é prova de fidelidade.

**P04 autorizada em 10/09/2026: “Autorizar correções com a Meta 0 aberta”.** A Meta 1 começou por servidores, mantendo a Meta 0 aberta como determinado em P03. Esta autorização muda somente a sequência: não dispensa divergências e não permite fechar metas antes das provas completas. A suíte completa anterior às correções tinha 1.073 testes; deve ser executada novamente para o fechamento. As Metas 2 a 7 ainda não começaram. A Meta 2 preservará a composição específica já existente dos roteiros.

## Rotas, uma a uma

`pk`, `ps_pk`, `pc_pk`, UUID, token e formato são parâmetros, não identificadores de registros reais. Os parâmetros fixos após a rota de destino indicam a especialização da view genérica. “Não existe” significa pendência, nunca dispensa autorizada.

### cadastros

| Rota da origem | Destino correspondente | Situação | Evidência e pendência |
|---|---|---|---|
| `cadastros:index`<br>`/cadastros/` | `viagens_cadastros:index`<br>`/viagens/cadastros/` | existe e está incompleta | Correspondência técnica; conteúdo, estados e comportamento ainda aguardam comparação visual. Fonte: `cadastros/urls.py:8`. |
| `cadastros:configuracao`<br>`/cadastros/configuracao/` | `viagens_oficios:institucional`<br>`/viagens/oficios/institucional/` | existe e está incompleta | Formulário genérico, sem as abas da origem; assinantes em catálogo separado. PT/OS na tela de origem: decisão de escopo pendente. Fonte: `cadastros/urls.py:9`. |
| `cadastros:configuracao_aba`<br>`/cadastros/configuracao/<slug:aba>/` | `viagens_oficios:institucional`<br>`/viagens/oficios/institucional/` | existe e está incompleta | Formulário genérico, sem as abas da origem; assinantes em catálogo separado. PT/OS na tela de origem: decisão de escopo pendente. Fonte: `cadastros/urls.py:10`. |
| `cadastros:api_consulta_cep`<br>`/cadastros/api/cep/<str:cep>/` | `viagens_cadastros:api_consulta_cep`<br>`/viagens/cadastros/api/cep/<str:cep>/` | existe e está incompleta | Serviço sem persistência implementado; integração visual pendente de P10. Fonte: `cadastros/urls.py:11`. |
| `cadastros:estados_index`<br>`/cadastros/estados/` | viagens_cadastros:estados | existe e está incompleta | CRUD implementado; P07/P12 e provas restantes pendentes. Fonte: `cadastros/urls.py:12`. |
| `cadastros:estado_update`<br>`/cadastros/estados/<int:pk>/editar/` | viagens_cadastros:estado_editar | existe e está incompleta | CRUD implementado; P07/P12 e provas restantes pendentes. Fonte: `cadastros/urls.py:13`. |
| `cadastros:estado_delete`<br>`/cadastros/estados/<int:pk>/excluir/` | viagens_cadastros:estado_excluir | existe e está incompleta | CRUD implementado; P07/P12 e provas restantes pendentes. Fonte: `cadastros/urls.py:14`. |
| `cadastros:unidades_index`<br>`/cadastros/unidades/` | `viagens_cadastros:lista`<br>`/viagens/cadastros/<slug:slug>/`<br>`slug=unidades` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:15`. |
| `cadastros:unidade_create`<br>`/cadastros/unidades/nova/` | `viagens_cadastros:novo`<br>`/viagens/cadastros/<slug:slug>/novo/`<br>`slug=unidades` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:16`. |
| `cadastros:unidade_update`<br>`/cadastros/unidades/<int:pk>/editar/` | `viagens_cadastros:editar`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/editar/`<br>`slug=unidades` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:17`. |
| `cadastros:unidade_delete`<br>`/cadastros/unidades/<int:pk>/excluir/` | `viagens_cadastros:excluir`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/excluir/`<br>`slug=unidades` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:18`. |
| `cadastros:cargos_index`<br>`/cadastros/cargos/` | `viagens_cadastros:lista`<br>`/viagens/cadastros/<slug:slug>/`<br>`slug=cargos` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:19`. |
| `cadastros:cargo_create`<br>`/cadastros/cargos/novo/` | `viagens_cadastros:novo`<br>`/viagens/cadastros/<slug:slug>/novo/`<br>`slug=cargos` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:20`. |
| `cadastros:cargo_update`<br>`/cadastros/cargos/<int:pk>/editar/` | `viagens_cadastros:editar`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/editar/`<br>`slug=cargos` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:21`. |
| `cadastros:cargo_set_default`<br>`/cadastros/cargos/<int:pk>/definir-padrao/` | `viagens_cadastros:definir_padrao`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/padrao/` | existe e está incompleta | Ação direta implementada com a regra existente; GET sem escrita, POST e permissões testados. Prova visual após gravação pendente. |
| `cadastros:cargo_delete`<br>`/cadastros/cargos/<int:pk>/excluir/` | `viagens_cadastros:excluir`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/excluir/`<br>`slug=cargos` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:23`. |
| `cadastros:combustiveis_index`<br>`/cadastros/combustiveis/` | `viagens_cadastros:lista`<br>`/viagens/cadastros/<slug:slug>/`<br>`slug=combustiveis` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:24`. |
| `cadastros:combustivel_create`<br>`/cadastros/combustiveis/novo/` | `viagens_cadastros:novo`<br>`/viagens/cadastros/<slug:slug>/novo/`<br>`slug=combustiveis` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:25`. |
| `cadastros:combustivel_update`<br>`/cadastros/combustiveis/<int:pk>/editar/` | `viagens_cadastros:editar`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/editar/`<br>`slug=combustiveis` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:26`. |
| `cadastros:combustivel_set_default`<br>`/cadastros/combustiveis/<int:pk>/definir-padrao/` | `viagens_cadastros:definir_padrao`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/padrao/` | existe e está incompleta | Ação direta implementada com a regra existente; GET sem escrita, POST e permissões testados. Prova visual após gravação pendente. |
| `cadastros:combustivel_delete`<br>`/cadastros/combustiveis/<int:pk>/excluir/` | `viagens_cadastros:excluir`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/excluir/`<br>`slug=combustiveis` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:32`. |
| `cadastros:cidades_index`<br>`/cadastros/cidades/` | `viagens_cadastros:cidades`<br>`/viagens/cadastros/cidades/` | existe e está incompleta | Consulta em cartões, busca e paginação15 observadas. Inclusão P13 e perfis da origem pendentes. Fonte: `cadastros/urls.py:33`. |
| `cadastros:cidade_create`<br>`/cadastros/cidades/nova/` | `cadastros:novo`<br>`/cadastros/<slug:slug>/novo/`<br>`slug=municipios` | existe e está incompleta | Cadastro correspondente, mas restrito ao administrador de Eventos. Permissão, campos, inclusão rápida e mensagens ainda divergem. Fonte: `cadastros/urls.py:34`. |
| `cadastros:cidades_export_csv`<br>`/cadastros/cidades/exportar.csv` | `viagens_cadastros:cidades_exportar_csv`<br>`/viagens/cadastros/cidades/exportar.csv` | existe e está incompleta | CSV implementado/testado; download pareado e perfis da origem pendentes. Fonte: `cadastros/urls.py:35`. |
| `cadastros:servidores_index`<br>`/cadastros/servidores/` | `viagens_cadastros:lista`<br>`/viagens/cadastros/<slug:slug>/`<br>`slug=servidores` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:36`. |
| `cadastros:servidor_create`<br>`/cadastros/servidores/novo/` | `viagens_cadastros:novo`<br>`/viagens/cadastros/<slug:slug>/novo/`<br>`slug=servidores` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:37`. |
| `cadastros:servidor_update`<br>`/cadastros/servidores/<int:pk>/editar/` | `viagens_cadastros:editar`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/editar/`<br>`slug=servidores` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:38`. |
| `cadastros:servidor_delete`<br>`/cadastros/servidores/<int:pk>/excluir/` | `viagens_cadastros:excluir`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/excluir/`<br>`slug=servidores` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:39`. |
| `cadastros:viaturas_index`<br>`/cadastros/viaturas/` | `viagens_cadastros:lista`<br>`/viagens/cadastros/<slug:slug>/`<br>`slug=viaturas` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:40`. |
| `cadastros:viatura_create`<br>`/cadastros/viaturas/nova/` | `viagens_cadastros:novo`<br>`/viagens/cadastros/<slug:slug>/novo/`<br>`slug=viaturas` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:41`. |
| `cadastros:viatura_update`<br>`/cadastros/viaturas/<int:pk>/editar/` | `viagens_cadastros:editar`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/editar/`<br>`slug=viaturas` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:42`. |
| `cadastros:viatura_delete`<br>`/cadastros/viaturas/<int:pk>/excluir/` | `viagens_cadastros:excluir`<br>`/viagens/cadastros/<slug:slug>/<int:pk>/excluir/`<br>`slug=viaturas` | existe e está incompleta | Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens. Fonte: `cadastros/urls.py:43`. |

### roteiros

| Rota da origem | Destino correspondente | Situação | Evidência e pendência |
|---|---|---|---|
| `roteiros:index`<br>`/roteiros/` | `viagens_roteiros:lista`<br>`/viagens/roteiros/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:9`. |
| `roteiros:novo`<br>`/roteiros/novo/` | `viagens_roteiros:novo`<br>`/viagens/roteiros/novo/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:10`. |
| `roteiros:roteiro-autosave-create`<br>`/roteiros/autosave/criar/` | `viagens_roteiros:autosave_novo`<br>`/viagens/roteiros/autosave/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:11`. |
| `roteiros:api_cidades_por_estado`<br>`/roteiros/api/cidades/<int:estado_id>/` | — | não existe | Não há API de cidades por estado; o destino usa opções locais dependentes. Conferir equivalência do comportamento. Fonte: `roteiros/urls.py:12`. |
| `roteiros:calcular_diarias`<br>`/roteiros/calcular-diarias/` | `viagens_roteiros:previa_diarias`<br>`/viagens/roteiros/previa-diarias/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:13`. |
| `roteiros:trechos_estimar`<br>`/roteiros/trechos/estimar/` | `viagens_roteiros:estimar_trecho`<br>`/viagens/roteiros/estimar-trecho/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:14`. |
| `roteiros:calcular_rota`<br>`/roteiros/api/calcular-rota/` | `viagens_roteiros:calcular_rota`<br>`/viagens/roteiros/calcular-rota/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:15`. |
| `roteiros:calcular_rota_preview`<br>`/roteiros/api/calcular-rota-preview/` | `viagens_roteiros:calcular_rota`<br>`/viagens/roteiros/calcular-rota/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:16`. |
| `roteiros:roteiro-autosave`<br>`/roteiros/<int:pk>/autosave/` | `viagens_roteiros:autosave`<br>`/viagens/roteiros/<int:pk>/autosave/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:17`. |
| `roteiros:editar`<br>`/roteiros/<int:pk>/editar/` | `viagens_roteiros:editar`<br>`/viagens/roteiros/<int:pk>/editar/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:18`. |
| `roteiros:excluir`<br>`/roteiros/<int:pk>/excluir/` | `viagens_roteiros:excluir`<br>`/viagens/roteiros/<int:pk>/excluir/` | existe e está incompleta | F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa. Fonte: `roteiros/urls.py:19`. |

### oficios

| Rota da origem | Destino correspondente | Situação | Evidência e pendência |
|---|---|---|---|
| `oficios:index`<br>`/oficios/` | `viagens_oficios:lista`<br>`/viagens/oficios/` | existe e está fiel | cartão, filtros, situações, ordenação, períodos e menus da origem (Meta 3, `oficios-lista.md`). Fonte: `oficios/urls.py:9` |
| `oficios:novo`<br>`/oficios/novo/` | `viagens_oficios:novo`<br>`/viagens/oficios/novo/` | existe e está fiel | POST cria o rascunho numerado e abre o editor (`viagens_oficios:criar`); o GET antigo continua (`oficios-form.md`). Fonte: `oficios/urls.py:10` |
| `oficios:modelos_motivo_index`<br>`/oficios/modelos-motivo/` | `viagens_oficios:catalogo`<br>`/viagens/oficios/catalogos/<str:tipo>/`<br>`tipo=motivos` | existe e está fiel | catálogo no padrão de cadastros da Meta 1 (`oficios-catalogos.md`). Fonte: `oficios/urls.py:11` |
| `oficios:modelo_motivo_create`<br>`/oficios/modelos-motivo/novo/` | `viagens_oficios:catalogo_novo`<br>`/viagens/oficios/catalogos/<str:tipo>/novo/`<br>`tipo=motivos` | existe e está fiel | modal de inclusão (`oficios-catalogos.md`). Fonte: `oficios/urls.py:12` |
| `oficios:modelo_motivo_update`<br>`/oficios/modelos-motivo/<int:pk>/editar/` | `viagens_oficios:catalogo_editar`<br>`/viagens/oficios/catalogos/<str:tipo>/<int:pk>/`<br>`tipo=motivos` | existe e está fiel | modal de edição (`oficios-catalogos.md`). Fonte: `oficios/urls.py:13` |
| `oficios:modelo_motivo_definir_padrao`<br>`/oficios/modelos-motivo/<int:pk>/padrao/` | `viagens_oficios:catalogo_editar`<br>`/viagens/oficios/catalogos/<str:tipo>/<int:pk>/`<br>`tipo=motivos` | existe e está fiel | `viagens_cadastros:definir_padrao` no menu da linha (`oficios-catalogos.md`). Fonte: `oficios/urls.py:14` |
| `oficios:modelo_motivo_delete`<br>`/oficios/modelos-motivo/<int:pk>/excluir/` | `viagens_oficios:catalogo_editar`<br>`/viagens/oficios/catalogos/<str:tipo>/<int:pk>/`<br>`tipo=motivos` | existe e está fiel | `viagens_cadastros:excluir` com diálogo (`oficios-catalogos.md`). Fonte: `oficios/urls.py:19` |
| `oficios:detalhe`<br>`/oficios/<int:pk>/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/` | existe e está fiel | conferência com todos os blocos (`oficios-detalhe.md`). Fonte: `oficios/urls.py:20` |
| `oficios:card_menus`<br>`/oficios/<int:pk>/menus/` | — | adaptado | os quatro menus são renderizados no próprio cartão, sem endpoint separado (`oficios-menus.md`). Fonte: `oficios/urls.py:21` |
| `oficios:editar`<br>`/oficios/<int:pk>/editar/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/editar/` | existe e está fiel | formulário por blocos (`oficios-form.md`). Fonte: `oficios/urls.py:22` |
| `oficios:dados_viajantes`<br>`/oficios/<int:pk>/dados-viajantes/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/editar/` | existe e está fiel | seção 1 do formulário: identificação, motivo, custeio e equipe (`oficios-form.md`). Fonte: `oficios/urls.py:23` |
| `oficios:dados_viajantes_autosave`<br>`/oficios/<int:pk>/dados-viajantes/autosave/` | — | ausente | gravação automática das etapas aguarda decisão (P19). Fonte: `oficios/urls.py:24` |
| `oficios:transporte`<br>`/oficios/<int:pk>/transporte/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/editar/` | existe e está fiel | seção 2: viatura cadastrada ou manual, motorista servidor ou externo, referência de origem, armas (`oficios-form.md`). Fonte: `oficios/urls.py:25` |
| `oficios:transporte_autosave`<br>`/oficios/<int:pk>/transporte/autosave/` | — | ausente | gravação automática das etapas aguarda decisão (P19). Fonte: `oficios/urls.py:26` |
| `oficios:wizard_roteiro`<br>`/oficios/<int:pk>/roteiro/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/editar/` | existe e está fiel | seção 3 com o resumo da rota (`oficios-form.md`). Fonte: `oficios/urls.py:27` |
| `oficios:wizard_roteiro_autosave_criar`<br>`/oficios/<int:pk>/roteiro/autosave/criar/` | — | ausente | gravação automática das etapas aguarda decisão (P19). Fonte: `oficios/urls.py:28` |
| `oficios:wizard_justificativa`<br>`/oficios/<int:pk>/justificativa/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/editar/` | existe e está fiel | seção 4 com regra de prazo, modelo e texto (`oficios-form.md`). Fonte: `oficios/urls.py:33` |
| `oficios:justificativa_autosave`<br>`/oficios/<int:pk>/justificativa/autosave/` | — | ausente | gravação automática das etapas aguarda decisão (P19). Fonte: `oficios/urls.py:34` |
| `oficios:wizard_resumo`<br>`/oficios/<int:pk>/resumo/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/` | existe e está fiel | conferência das seis etapas com pendências (`oficios-detalhe.md`). Fonte: `oficios/urls.py:35` |
| `oficios:api_viatura_por_placa`<br>`/oficios/<int:pk>/api/viatura-por-placa/` | — | adaptado | a viatura cadastrada é escolhida por busca no próprio seletor (placa e modelo), sem consulta ao servidor. Fonte: `oficios/urls.py:36` |
| `oficios:wizard_documentos`<br>`/oficios/<int:pk>/documentos/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/` | existe e está fiel | emissão, termos e documentos gerados na conferência (`oficios-detalhe.md`). Fonte: `oficios/urls.py:37` |
| `oficios:oficio_pdf_inline`<br>`/oficios/<int:pk>/documentos/oficio-pdf-inline/` | `viagens_oficios:preview_artefato`<br>`/viagens/oficios/documentos/<uuid:pk>/preview/` | existe e está fiel | "Visualizar ofício" gera e abre em nova aba (`gerar` com `?inline=1`). Fonte: `oficios/urls.py:38` |
| `oficios:justificativa_pdf_inline`<br>`/oficios/<int:pk>/documentos/justificativa-pdf-inline/` | `viagens_oficios:preview_artefato`<br>`/viagens/oficios/documentos/<uuid:pk>/preview/` | existe e está fiel | "Visualizar justificativa" (`gerar` com `?inline=1`). Fonte: `oficios/urls.py:39` |
| `oficios:ordem_servico_pdf_inline`<br>`/oficios/<int:pk>/documentos/ordem-servico-pdf-inline/` | — | fora de escopo | Geração/prévia de ordem de serviço: fora do escopo expresso do pedido. Pontos de entrada em telas mistas ainda dependem de decisão. Fonte: `oficios/urls.py:44`. |
| `oficios:baixar_justificativa_documento`<br>`/oficios/<int:pk>/documentos/justificativa/<str:formato>/` | `viagens_oficios:gerar`<br>`/viagens/oficios/<int:pk>/gerar/<str:tipo>/<str:formato>/`<br>`tipo=justificativa` | existe e está fiel | "Baixar PDF/DOCX" da justificativa nos menus e na conferência. Fonte: `oficios/urls.py:49` |
| `oficios:baixar_ordem_servico_documento`<br>`/oficios/<int:pk>/documentos/ordem-servico/<str:formato>/` | — | fora de escopo | Geração/prévia de ordem de serviço: fora do escopo expresso do pedido. Pontos de entrada em telas mistas ainda dependem de decisão. Fonte: `oficios/urls.py:54`. |
| `oficios:baixar_documento`<br>`/oficios/<int:pk>/documentos/<str:formato>/` | `viagens_oficios:gerar`<br>`/viagens/oficios/<int:pk>/gerar/<str:tipo>/<str:formato>/`<br>`tipo=oficio` | existe e está fiel | "Baixar PDF/DOCX" do ofício nos menus e na conferência. Fonte: `oficios/urls.py:59` |
| `oficios:excluir`<br>`/oficios/<int:pk>/excluir/` | `viagens_oficios:acao`<br>`/viagens/oficios/<int:pk>/acao/<str:acao>/`<br>`acao=excluir` | existe e está fiel | "Excluir ofício" com confirmação, volta para onde foi disparado, bloqueio por vínculo. Fonte: `oficios/urls.py:60` |
| `oficios:cancelar`<br>`/oficios/<int:pk>/cancelar/` | `viagens_oficios:acao`<br>`/viagens/oficios/<int:pk>/acao/<str:acao>/`<br>`acao=cancelar` | existe e está fiel | "Cancelar ofício" com motivo na conferência e confirmação no cartão. Fonte: `oficios/urls.py:61` |
| `oficios:retificar`<br>`/oficios/<int:pk>/retificar/` | `viagens_oficios:acao`<br>`/viagens/oficios/<int:pk>/acao/<str:acao>/`<br>`acao=retificar` | existe e está fiel | liga e desliga a marca de retificação. Fonte: `oficios/urls.py:62` |
| `oficios:marcar_complementar`<br>`/oficios/<int:pk>/complementar/` | `viagens_oficios:acao`<br>`/viagens/oficios/<int:pk>/acao/<str:acao>/`<br>`acao=complementar` | existe e está fiel | liga e desliga a marca de complementar. Fonte: `oficios/urls.py:63` |

### justificativas

| Rota da origem | Destino correspondente | Situação | Evidência e pendência |
|---|---|---|---|
| `justificativas:index`<br>`/justificativas/` | `viagens_oficios:justificativas`<br>`/viagens/oficios/justificativas/` | existe e está fiel | lista com regra de prazo, texto e ações, mais a inclusão rápida (`justificativas-lista.md`). Fonte: `justificativas/urls.py:9` |
| `justificativas:api_buscar_oficios`<br>`/justificativas/api/oficios/` | `viagens_oficios:justificativas_buscar_oficios`<br>`/viagens/oficios/justificativas/api/oficios/` | existe e está fiel | `viagens_oficios:justificativas_buscar_oficios`, até 30 resultados (`justificativas-lista.md`). Fonte: `justificativas/urls.py:10` |
| `justificativas:justificativa_delete`<br>`/justificativas/<int:pk>/excluir/` | `viagens_oficios:justificativa_excluir`<br>`/viagens/oficios/justificativas/<int:pk>/excluir/` | existe e está fiel | `viagens_oficios:justificativa_excluir` apaga o texto e o modelo (`justificativas-lista.md`). Fonte: `justificativas/urls.py:11` |
| `justificativas:modelos_index`<br>`/justificativas/modelos/` | `viagens_oficios:catalogo`<br>`/viagens/oficios/catalogos/<str:tipo>/`<br>`tipo=justificativas` | existe e está fiel | catálogo no padrão de cadastros da Meta 1 (`oficios-catalogos.md`). Fonte: `justificativas/urls.py:12` |
| `justificativas:modelo_create`<br>`/justificativas/modelos/novo/` | `viagens_oficios:catalogo_novo`<br>`/viagens/oficios/catalogos/<str:tipo>/novo/`<br>`tipo=justificativas` | existe e está fiel | modal de inclusão (`oficios-catalogos.md`). Fonte: `justificativas/urls.py:13` |
| `justificativas:modelo_update`<br>`/justificativas/modelos/<int:pk>/editar/` | `viagens_oficios:catalogo_editar`<br>`/viagens/oficios/catalogos/<str:tipo>/<int:pk>/`<br>`tipo=justificativas` | existe e está fiel | modal de edição (`oficios-catalogos.md`). Fonte: `justificativas/urls.py:14` |
| `justificativas:modelo_definir_padrao`<br>`/justificativas/modelos/<int:pk>/padrao/` | `viagens_oficios:catalogo_editar`<br>`/viagens/oficios/catalogos/<str:tipo>/<int:pk>/`<br>`tipo=justificativas` | existe e está fiel | `viagens_cadastros:definir_padrao` (`oficios-catalogos.md`). Fonte: `justificativas/urls.py:15` |
| `justificativas:modelo_delete`<br>`/justificativas/modelos/<int:pk>/excluir/` | `viagens_oficios:catalogo_editar`<br>`/viagens/oficios/catalogos/<str:tipo>/<int:pk>/`<br>`tipo=justificativas` | existe e está fiel | `viagens_cadastros:excluir` com diálogo (`oficios-catalogos.md`). Fonte: `justificativas/urls.py:16` |
| `justificativas:legacy_modelo_create`<br>`/justificativas/novo/` | — | não existe | Alias legado a decidir; há dois padrões de exclusão idênticos na origem e o último fica sombreado. Não corrigir nem dispensar sem autorização. Fonte: `justificativas/urls.py:17`. |
| `justificativas:legacy_modelo_update`<br>`/justificativas/<int:pk>/editar/` | — | não existe | Alias legado a decidir; há dois padrões de exclusão idênticos na origem e o último fica sombreado. Não corrigir nem dispensar sem autorização. Fonte: `justificativas/urls.py:18`. |
| `justificativas:legacy_modelo_definir_padrao`<br>`/justificativas/<int:pk>/padrao/` | — | não existe | Alias legado a decidir; há dois padrões de exclusão idênticos na origem e o último fica sombreado. Não corrigir nem dispensar sem autorização. Fonte: `justificativas/urls.py:19`. |
| `justificativas:legacy_modelo_delete`<br>`/justificativas/<int:pk>/excluir/` | — | não existe | Alias legado a decidir; há dois padrões de exclusão idênticos na origem e o último fica sombreado. Não corrigir nem dispensar sem autorização. Fonte: `justificativas/urls.py:20`. |

### termos

| Rota da origem | Destino correspondente | Situação | Evidência e pendência |
|---|---|---|---|
| `termos:index`<br>`/termos/` | `viagens_termos:lista`<br>`/viagens/termos/` | existe e está fiel | cartão, busca, situações e menus (`termos-lista.md`). Fonte: `termos/urls.py:9` |
| `termos:api_buscar_oficios`<br>`/termos/api/oficios/` | `viagens_termos:api_buscar_oficios`<br>`/viagens/termos/api/oficios/` | existe e está fiel | mesma busca de ofícios das justificativas, teto de 30 (`termos-form.md`). Fonte: `termos/urls.py:10` |
| `termos:novo`<br>`/termos/novo/` | `viagens_termos:novo`<br>`/viagens/termos/novo/` | existe e está fiel | cadastro por blocos com seletor de ofício, destinos adicionais, período, servidores e viatura (`termos-form.md`). Fonte: `termos/urls.py:11` |
| `termos:editar`<br>`/termos/<int:pk>/editar/` | `viagens_termos:editar`<br>`/viagens/termos/<int:pk>/editar/` | existe e está fiel | idem, com o que herda do ofício (`termos-form.md`). Fonte: `termos/urls.py:12` |
| `termos:excluir`<br>`/termos/<int:pk>/excluir/` | `viagens_termos:acao`<br>`/viagens/termos/<int:pk>/acao/<str:acao>/`<br>`acao=excluir` | existe e está fiel | confirmação em dois cliques na lista e no menu do detalhe (`termos-lista.md`). Fonte: `termos/urls.py:13` |
| `termos:termo_cadastro_downloads`<br>`/termos/<int:pk>/downloads/` | `viagens_termos:detalhe`<br>`/viagens/termos/<int:pk>/` | existe e está fiel | "Escolher documentos para baixar": por servidor, genérico, viatura, todos (`termos-documentos.md`). Fonte: `termos/urls.py:14` |
| `termos:termo_cadastro_pdf_inline`<br>`/termos/<int:pk>/pdf-inline/` | `viagens_termos:gerar`<br>`/viagens/termos/<int:pk>/gerar/0/pdf/?inline=1` | existe e está fiel | PDF genérico em nova aba; prévia em tela em `viagens_termos:preview` (`termos-documentos.md`). Fonte: `termos/urls.py:15` |
| `termos:termo_cadastro_generico_pdf_inline`<br>`/termos/<int:pk>/pdf-inline/generico/` | `viagens_termos:gerar`<br>`/viagens/termos/<int:pk>/gerar/0/pdf/?inline=1` | existe e está fiel | "Visualizar termo genérico" (`termos-documentos.md`). Fonte: `termos/urls.py:16` |
| `termos:termo_cadastro_servidor_pdf_inline`<br>`/termos/<int:pk>/servidor/<int:servidor_pk>/pdf-inline/` | `viagens_termos:gerar`<br>`/viagens/termos/<int:pk>/gerar/<int:servidor_id>/pdf/?inline=1` | existe e está fiel | "Visualizar" por servidor; prévia em tela em `viagens_termos:preview_servidor` (`termos-documentos.md`). Fonte: `termos/urls.py:21` |
| `termos:baixar_termo_cadastro_pdf`<br>`/termos/<int:pk>/pdf/` | `viagens_termos:todos_pdf`<br>`/viagens/termos/<int:pk>/todos/pdf/` | existe e está fiel | um PDF só com todos os termos, `termo-<pk>-todos.pdf` (`termos-documentos.md`). Fonte: `termos/urls.py:26` |
| `termos:baixar_termo_cadastro_docx`<br>`/termos/<int:pk>/docx/` | `viagens_termos:lote`<br>`/viagens/termos/<int:pk>/gerar/docx/` | existe e está fiel | ZIP com os DOCX de todos os servidores (`termos-documentos.md`). Fonte: `termos/urls.py:27` |
| `termos:termo_cadastro_generico_assinado_anexar`<br>`/termos/<int:pk>/generico/assinado/anexar/` | `viagens_oficios:assinatura_artefato`<br>`/viagens/oficios/documentos/<uuid:pk>/assinatura/` | existe e está fiel | ponto de entrada no menu "Anexar termo assinado" da lista e nos documentos gerados (`termos-lista.md`). Fonte: `termos/urls.py:28` |
| `termos:termo_cadastro_servidor_assinado_anexar`<br>`/termos/<int:pk>/servidor/<int:servidor_pk>/assinado/anexar/` | `viagens_oficios:assinatura_artefato`<br>`/viagens/oficios/documentos/<uuid:pk>/assinatura/` | existe e está fiel | por servidor, na lista e no detalhe; inativo até haver PDF (`termos-documentos.md`). Fonte: `termos/urls.py:33` |
| `termos:termo_cadastro_viatura_pdf_inline`<br>`/termos/<int:pk>/viatura/pdf-inline/` | `viagens_termos:gerar_viatura`<br>`/viagens/termos/<int:pk>/gerar/viatura/pdf/?inline=1` | existe e está fiel | "Visualizar termo da viatura" (`termos-documentos.md`). Fonte: `termos/urls.py:40` |
| `termos:baixar_termo_cadastro_viatura`<br>`/termos/<int:pk>/viatura/<str:formato>/` | `viagens_termos:gerar_viatura`<br>`/viagens/termos/<int:pk>/gerar/viatura/<str:formato>/` | existe e está fiel | PDF e DOCX da viatura com campos do servidor em branco (`termos-documentos.md`). Fonte: `termos/urls.py:45` |
| `termos:baixar_termo_cadastro_generico`<br>`/termos/<int:pk>/generico/<str:formato>/` | `viagens_termos:gerar`<br>`/viagens/termos/<int:pk>/gerar/0/<str:formato>/` | existe e está fiel | PDF e DOCX do genérico (`termos-documentos.md`). Fonte: `termos/urls.py:50` |
| `termos:baixar_termo_cadastro_servidor`<br>`/termos/<int:pk>/servidor/<int:servidor_pk>/<str:formato>/` | `viagens_termos:gerar`<br>`/viagens/termos/<int:pk>/gerar/<int:servidor_id>/<str:formato>/` | existe e está fiel | PDF e DOCX por servidor (`termos-documentos.md`). Fonte: `termos/urls.py:55` |
| `termos:preview_termo_oficio`<br>`/termos/oficio/<int:pk>/preview/` | `viagens_oficios:editar`<br>`/viagens/oficios/<int:pk>/` | existe e está fiel | termos por servidor e em lote na conferência do ofício (`oficios-detalhe.md`). Fonte: `termos/urls.py:60` |
| `termos:termo_servidor_pdf_inline`<br>`/termos/oficio/<int:pk>/servidor/<int:servidor_pk>/pdf-inline/` | `viagens_oficios:termo`<br>`/viagens/oficios/<int:pk>/termos/<int:servidor_id>/pdf/?inline=1` | existe e está fiel | "Visualizar termo" no menu do servidor (`oficios-menus.md`). Fonte: `termos/urls.py:61` |
| `termos:termo_oficio_assinado_anexar`<br>`/termos/oficio/<int:pk>/servidor/<int:servidor_pk>/assinado/anexar/` | `viagens_oficios:assinatura_artefato`<br>`/viagens/oficios/documentos/<uuid:pk>/assinatura/` | existe e está fiel | "Anexar assinado" no menu do termo do servidor (`oficios-menus.md`). Fonte: `termos/urls.py:66` |
| `termos:baixar_termo_servidor`<br>`/termos/oficio/<int:pk>/servidor/<int:servidor_pk>/<str:formato>/` | `viagens_oficios:termo`<br>`/viagens/oficios/<int:pk>/termos/<int:servidor_id>/<str:formato>/` | existe e está fiel | PDF e DOCX por servidor no ofício (`oficios-detalhe.md`). Fonte: `termos/urls.py:71` |
| `termos:baixar_termos_todos_pdf`<br>`/termos/oficio/<int:pk>/todos/pdf/` | `viagens_oficios:termos_todos_pdf`<br>`/viagens/oficios/<int:pk>/termos/todos/pdf/` | existe e está fiel | um PDF só com os termos do ofício (`oficios-detalhe.md`). Fonte: `termos/urls.py:76` |
| `termos:baixar_termo_lote_zip`<br>`/termos/oficio/<int:pk>/lote/<str:formato>/` | `viagens_oficios:termos_lote`<br>`/viagens/oficios/<int:pk>/termos/<str:formato>/` | existe e está fiel | ZIP de PDFs ou DOCX (`oficios-detalhe.md`). Fonte: `termos/urls.py:81` |

### prestacoes_contas

| Rota da origem | Destino correspondente | Situação | Evidência e pendência |
|---|---|---|---|
| `prestacoes_contas:index`<br>`/prestacoes-contas/` | `viagens_prestacoes:index`<br>`/viagens/prestacoes/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:11` |
| `prestacoes_contas:prestacao_downloads`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/downloads/` | `viagens_prestacoes:prestacao_downloads`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/downloads/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:12` |
| `prestacoes_contas:prestacao_download_compilado`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/downloads/compilado/` | `viagens_prestacoes:prestacao_download_compilado`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/downloads/compilado/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:13` |
| `prestacoes_contas:prestacao_download_assinado`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/downloads/assinado/<str:item_id>/<str:formato>/` | `viagens_prestacoes:prestacao_download_assinado`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/downloads/assinado/<str:item_id>/<str:formato>/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:14` |
| `prestacoes_contas:prestacao_servidor_arquivar`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/arquivar/` | `viagens_prestacoes:prestacao_servidor_arquivar`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/arquivar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:16` |
| `prestacoes_contas:prestacao_servidor_finalizar`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/finalizar/` | `viagens_prestacoes:prestacao_servidor_finalizar`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/finalizar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:21` |
| `prestacoes_contas:documentos_servidor`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/documentos/` | `viagens_prestacoes:documentos_servidor`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/documentos/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:26` |
| `prestacoes_contas:rt_servidor`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/rt/` | `viagens_prestacoes:rt_servidor`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/rt/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:31` |
| `prestacoes_contas:diario_servidor`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/diario/` | `viagens_prestacoes:diario_servidor`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/diario/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:32` |
| `prestacoes_contas:consolidado_servidor`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/consolidado/` | `viagens_prestacoes:consolidado_servidor`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/consolidado/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:37` |
| `prestacoes_contas:prestacao_arquivar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/arquivar/` | `viagens_prestacoes:prestacao_arquivar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/arquivar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:43` |
| `prestacoes_contas:prestacao_finalizar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/finalizar/` | `viagens_prestacoes:prestacao_finalizar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/finalizar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:44` |
| `prestacoes_contas:documentos`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/documentos/` | `viagens_prestacoes:documentos`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/documentos/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:45` |
| `prestacoes_contas:prestacao_arquivo_autosave`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/despacho/autosave/` | `viagens_prestacoes:prestacao_arquivo_autosave`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/despacho/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:46` |
| `prestacoes_contas:prestacao_despacho_assinado_anexar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/despacho-assinado/anexar/` | `viagens_prestacoes:prestacao_despacho_assinado_anexar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/despacho-assinado/anexar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:47` |
| `prestacoes_contas:prestacao_oficio_assinado_anexar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/oficio-assinado/anexar/` | `viagens_prestacoes:prestacao_oficio_assinado_anexar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/oficio-assinado/anexar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:52` |
| `prestacoes_contas:prestacao_carimbo_ajustar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/oficio-assinado/carimbo/` | `viagens_prestacoes:prestacao_carimbo_ajustar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/oficio-assinado/carimbo/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:57` |
| `prestacoes_contas:prestacao_oficio_assinado_cru`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/oficio-assinado/cru/` | `viagens_prestacoes:prestacao_oficio_assinado_cru`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/oficio-assinado/cru/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:62` |
| `prestacoes_contas:prestacao_servidor_assinado_anexar`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/assinado/<str:tipo>/anexar/` | `viagens_prestacoes:prestacao_servidor_assinado_anexar`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/assinado/<str:tipo>/anexar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:67` |
| `prestacoes_contas:prestacao_documento_delete`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/anexo/<int:anexo_pk>/excluir/` | `viagens_prestacoes:prestacao_documento_delete`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/anexo/<int:anexo_pk>/excluir/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:72` |
| `prestacoes_contas:prestacao_documento_conteudo`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/anexo/<int:anexo_pk>/conteudo/` | `viagens_prestacoes:prestacao_documento_conteudo`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/anexo/<int:anexo_pk>/conteudo/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:73` |
| `prestacoes_contas:prestacao_servidor_solicitacao_autosave`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/solicitacao/autosave/` | `viagens_prestacoes:prestacao_servidor_solicitacao_autosave`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/solicitacao/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:78` |
| `prestacoes_contas:prestacao_servidor_arquivo_autosave`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/comprovante/autosave/` | `viagens_prestacoes:prestacao_servidor_arquivo_autosave`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/comprovante/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:79` |
| `prestacoes_contas:rt_criar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/rt/` | `viagens_prestacoes:rt_criar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/rt/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:80` |
| `prestacoes_contas:rt_autosave`<br>`/prestacoes-contas/rt/<int:pk>/autosave/` | `viagens_prestacoes:rt_autosave`<br>`/viagens/prestacoes/rt/<int:pk>/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:81` |
| `prestacoes_contas:card_menus`<br>`/prestacoes-contas/<int:pk>/menus/` | `viagens_prestacoes:index`<br>`/viagens/prestacoes/` | existe e está fiel | os menus do cartão (documentos para baixar, documentos assinados) saem no próprio HTML da lista, sem endpoint de fragmento (`prestacoes-lista.md`). Fonte: `prestacoes_contas/urls.py:82` |
| `prestacoes_contas:rt_servidor_autosave`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/rt/autosave/` | `viagens_prestacoes:rt_servidor_autosave`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/rt/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:83` |
| `prestacoes_contas:rt_download_servidor`<br>`/prestacoes-contas/rt/servidor/<int:ps_pk>/download/` | `viagens_prestacoes:rt_download_servidor`<br>`/viagens/prestacoes/rt/servidor/<int:ps_pk>/download/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:88` |
| `prestacoes_contas:rt_download_servidor_formato`<br>`/prestacoes-contas/rt/servidor/<int:ps_pk>/download/<str:formato>/` | `viagens_prestacoes:rt_download_servidor_formato`<br>`/viagens/prestacoes/rt/servidor/<int:ps_pk>/download/<str:formato>/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:89` |
| `prestacoes_contas:diario_criar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/diario/` | `viagens_prestacoes:diario_criar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/diario/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:90` |
| `prestacoes_contas:diario_editar_roteiro`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/diario/editar-roteiro/` | `viagens_prestacoes:diario_editar_roteiro`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/diario/editar-roteiro/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:91` |
| `prestacoes_contas:diario_servidor_editar_roteiro`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/diario/editar-roteiro/` | `viagens_prestacoes:diario_servidor_editar_roteiro`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/diario/editar-roteiro/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:92` |
| `prestacoes_contas:diario_motorista`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/diario/motorista/` | `viagens_prestacoes:diario_motorista`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/diario/motorista/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:97` |
| `prestacoes_contas:diario_servidor_motorista`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/diario/motorista/` | `viagens_prestacoes:diario_servidor_motorista`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/diario/motorista/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:98` |
| `prestacoes_contas:diario_autosave`<br>`/prestacoes-contas/diario/<int:pk>/autosave/` | `viagens_prestacoes:diario_autosave`<br>`/viagens/prestacoes/diario/<int:pk>/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:103` |
| `prestacoes_contas:diario_servidor_autosave`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/diario/autosave/` | `viagens_prestacoes:diario_servidor_autosave`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/diario/autosave/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:104` |
| `prestacoes_contas:diario_download`<br>`/prestacoes-contas/diario/<int:pk>/download/` | `viagens_prestacoes:diario_download`<br>`/viagens/prestacoes/diario/<int:pk>/download/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:109` |
| `prestacoes_contas:diario_download_formato`<br>`/prestacoes-contas/diario/<int:pk>/download/<str:formato>/` | `viagens_prestacoes:diario_download_formato`<br>`/viagens/prestacoes/diario/<int:pk>/download/<str:formato>/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:110` |
| `prestacoes_contas:consolidado`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/consolidado/` | `viagens_prestacoes:consolidado`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/consolidado/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:111` |
| `prestacoes_contas:consolidado_download`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/consolidado/download/` | `viagens_prestacoes:consolidado_download`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/consolidado/download/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:112` |
| `prestacoes_contas:assinatura_rt_gerar`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/assinatura-rt/gerar/` | `viagens_prestacoes:assinatura_rt_gerar`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/assinatura/gerar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:114` |
| `prestacoes_contas:assinatura_rt_cancelar`<br>`/prestacoes-contas/servidor-prestacao/<int:ps_pk>/assinatura-rt/cancelar/` | `viagens_prestacoes:assinatura_rt_cancelar`<br>`/viagens/prestacoes/servidor-prestacao/<int:ps_pk>/assinatura/cancelar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:115` |
| `prestacoes_contas:assinatura_db_gerar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/assinatura-db/gerar/` | `viagens_prestacoes:assinatura_db_gerar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/diario/assinatura/gerar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:116` |
| `prestacoes_contas:assinatura_db_cancelar`<br>`/prestacoes-contas/prestacao/<int:pc_pk>/assinatura-db/cancelar/` | `viagens_prestacoes:assinatura_db_cancelar`<br>`/viagens/prestacoes/prestacao/<int:pc_pk>/diario/assinatura/cancelar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-etapas.md`). Fonte: `prestacoes_contas/urls.py:117` |
| `prestacoes_contas:assinatura_landing`<br>`/prestacoes-contas/assinar/<str:token>/` | `viagens_assinaturas:assinatura_landing`<br>`/assinatura/<str:token>/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:119` |
| `prestacoes_contas:assinatura_concluido`<br>`/prestacoes-contas/assinar/<str:token>/concluido/` | `viagens_assinaturas:assinatura_concluido`<br>`/assinatura/<str:token>/concluido/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:120` |
| `prestacoes_contas:assinatura_identidade`<br>`/prestacoes-contas/assinar/<str:token>/<str:tipo>/identidade/` | `viagens_assinaturas:assinatura_identidade`<br>`/assinatura/<str:token>/<str:tipo>/identidade/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:121` |
| `prestacoes_contas:assinatura_assinar`<br>`/prestacoes-contas/assinar/<str:token>/<str:tipo>/assinar/` | `viagens_assinaturas:assinatura_assinar`<br>`/assinatura/<str:token>/<str:tipo>/assinar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:122` |
| `prestacoes_contas:assinatura_pdf_origem`<br>`/prestacoes-contas/assinar/<str:token>/<str:tipo>/pdf/` | `viagens_assinaturas:assinatura_pdf_origem`<br>`/assinatura/<str:token>/<str:tipo>/origem.pdf` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:123` |
| `prestacoes_contas:modelos_index`<br>`/prestacoes-contas/modelos-texto/` | `viagens_prestacoes:modelos_index`<br>`/viagens/prestacoes/modelos-texto/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:125` |
| `prestacoes_contas:modelo_update`<br>`/prestacoes-contas/modelos-texto/<int:pk>/editar/` | `viagens_prestacoes:modelo_update`<br>`/viagens/prestacoes/modelos-texto/<int:pk>/editar/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:126` |
| `prestacoes_contas:modelo_delete`<br>`/prestacoes-contas/modelos-texto/<int:pk>/excluir/` | `viagens_prestacoes:modelo_delete`<br>`/viagens/prestacoes/modelos-texto/<int:pk>/excluir/` | existe e está fiel | tela e comandos no V3.2, sem laço genérico (`prestacoes-modelos-assinatura.md`). Fonte: `prestacoes_contas/urls.py:127` |

## Verificação técnica e preservação do ambiente

- Baseline anterior à F6: 1.050 testes PostgreSQL, 381,438 s, quatro dispensas previstas. Após a estrutura inicial: 1.069 testes, 424,690 s, quatro dispensas previstas.
- `manage.py check`: sem problemas; `makemigrations --check --dry-run`: nenhuma mudança; `git diff --check`: limpo.
- Estado atual do PostgreSQL: **1.073 testes passaram**, 146,044 s, quatro dispensas previstas (`logs/paridade-meta0-postgresql.txt`). Esta execução usa hasher rápido apenas na configuração de testes; as senhas persistidas não foram modificadas.
- SQLite: **1.073 testes passaram**, 87,348 s, cinco dispensas previstas (`logs/paridade-meta0-sqlite.txt`), com hasher rápido apenas no ambiente de testes.
- O erro inicial do navegador era a falta das colunas de procedência da F6 no banco de desenvolvimento. Foi corrigido aplicando somente as migrações de esquema já preparadas e autorizadas; nenhuma carga de dados foi executada.
- Backup antes da aplicação: `backups/antes-esquema-f6-20260910-112938.dump`, 3.555.455 bytes, SHA-256 `9961f44f2c2e938ed8f00c1ad1d8b8a319ffeb22c8aa5a6651c72793d001eb2c`; catálogo de restauração validado.
- As 83 tabelas anteriores conservaram seus valores. A ampliação de `django_content_type` e `auth_permission` contém somente os quatro modelos de controle da F6 e suas permissões técnicas; vínculos e permissões anteriores permaneceram iguais. Evidência: `logs/paridade-esquema-preservacao.json`.
- Foram comparados os 105 hashes de origem registrados na F5: nenhuma alteração (`logs/f6-preservacao-origem.json`). Os seis arquivos de URL têm também hashes na fotografia desta meta.
- Nenhum commit ou push executado. Nenhuma edição em `ds-v32.css`. Nenhum campo, fluxo ou permissão de negócio alterado por esta Meta 0.

## Reproduzir a fotografia técnica

```powershell
.venv\Scripts\python.exe -X utf8 scripts/inventariar_paridade_viagens.py --origem "C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens"
```

`scripts/gerar_inventario_paridade.py` gera apenas a correspondência inicial a partir das fotografias. Ele recusa sobrescrever mapeamento que já tenha prova visual registrada. Atualizações posteriores devem preservar as evidências e as decisões aceitas.

## Incremento de cargos e combustíveis após P04

Meta 0 permanece aberta. Meta 1 em andamento: listas com cartões, inclusão rápida própria e ação direta de padrão implementadas. Edição inline e estados posteriores ainda pendentes. Foram registrados sete novos pares reais, totalizando 53 pares de observação parcial; nenhuma rota certificada.

A validação deste incremento abrange 99 testes de cadastros em cada banco, todos aprovados, além de `check` e `makemigrations --check --dry-run` limpos. Os resultados de 1.073 testes acima são anteriores a este incremento; não constituem prova de fechamento da Meta 1. Detalhes em `validacao-catalogos.json`.

## Continuação dos fluxos de catálogos

As rotas diretas de inclusão de cargos/combustíveis passaram a abrir o catálogo, como o GV. Inclusão inválida mantém valores e erros visíveis; exclusão responde na lista com o retorno validado. Ensaios de criação, duplicidade, padrão e exclusão foram realizados somente no destino, com limpeza dos itens temporários. P05 aguarda decisão sobre preservar o padrão ao editar o nome.

A suíte completa atual passou com **1.088 testes em cada banco** (quatro dispensas no PostgreSQL, cinco no SQLite). Isso substitui a execução anterior como evidência técnica atual, sem certificar a Meta 1. Existem 57 pares de observação parcial e nenhuma rota certificada. Evidências e limites em `validacao-catalogos-fluxos.json`.

## Lista de viaturas após P04

Cartões, filtro da unidade configurada e dos três combustíveis frequentes, busca em todos os dados, paginação de 15 itens e diálogo de exclusão implementados. Ensaios de cartão preenchido, seleção de combustível, busca sem resultado e limpeza realizados no navegador. Viatura e combustível temporários removidos. Foram acrescentados seis pares, incluindo a conferência do marcador CT de combustíveis; total de 63 pares parciais. Nenhuma rota certificada. Validação: 108 testes de cadastros por banco, todos aprovados; a suíte completa registrada anteriormente antecede este incremento.

## Formulário de viaturas após P04

Formulário próprio com Identificação, Lotação e Motoristas, pesquisa/seleção por cartões e retorno dos três cadastros implementados. Comparados formulário inicial, busca, seleção e ausência de resultado. Ensaios de retorno, teclado e erro de placa no destino; nenhum POST na origem. Quatro novos pares; total de 67 pares parciais. 111 testes de cadastros passaram por banco; check e makemigrations limpos. Limite/máscara da placa e provas restantes mantêm as metas abertas.

## Lista de unidades após P04

Cartões com nome/sigla, busca por ambos, inclusão rápida e diálogo de exclusão implementados. Criação, duplicidade, cancelamento e limpeza ensaiados somente no destino. O formulário completo e o gerenciamento de lotação foram preservados; edição inline e criação direta continuam pendentes. Sete novos pares, total de 74 pares parciais; nenhuma certificação. 116 testes de cadastros passaram em cada banco, check e makemigrations limpos. O comportamento do atalho de retorno na origem requer investigação adicional; não foi certificado a partir do ensaio do destino. Detalhes em cadastros-unidades.md e validacao-unidades.json.

## Busca automática e paginação dos cadastros após P04

Busca GET após um segundo com restauração do foco, filtro de cargos pelo select do DS e régua de paginação alinhada ao GV. Doze pares adicionais; total de 86 observações parciais. Paginação inicial/intermediária/final, busca por nome sem acentos e avanço com filtro exercitados com 97 unidades temporárias, removidas ao final. P06 pergunta sobre preservação de lotação na edição rápida e aguarda resposta.

A suíte completa atual passou com **1.103 testes em cada banco**, com quatro dispensas no PostgreSQL e cinco no SQLite; 117 testes de cadastros por banco. Check, makemigrations e diff check limpos. Avisos e limitações de conversão documental constam de `validacao-cadastros-busca.json`. Nenhuma meta encerrada ou ausência dispensada.

## Entrada de Cadastros e ordem dos dados de servidores

Os seis cartões principais passaram a usar a ordem e os textos do GV, com acesso à configuração existente. O grupo Estados continua ausente; acesso atual a diárias mantido enquanto a aba Roteiros da configuração está pendente. A lista de servidores apresenta cargo, CPF, RG, telefone e unidade na ordem da origem. Dois novos pares, total de 88 observações parciais; nenhuma certificação. 117 testes de cadastros aprovados por banco, check e makemigrations limpos. A última suíte completa (1.103 por banco) antecede este incremento. P07 solicita autorização para os ajustes de Estado; auditoria somente leitura encontrou 27 registros, maior nome com 19 caracteres.

## Respostas de gravação e exclusão de servidores e viaturas

Mensagens de servidor rascunho/criado/atualizado, resumo de erro com foco e retorno da edição à lista alinhados ao contrato da origem. Exclusão de servidor por GET retorna à lista sem remover; viatura tem confirmação própria também por acesso direto. Exclusões preservam as proteções existentes e respondem na lista. Ensaiados erro de CPF, rascunho, atualização completa, cancelamento e exclusão somente dos registros temporários no destino; limpeza comprovada em `limpeza-ensaio-respostas.json`.

Novo par da confirmação direta de viatura: total de 89 pares parciais, 24 rotas com observação e 17 fichas de quatro quadros; nenhuma rota certificada. Respostas de POST da origem, bloqueios específicos e perfis seguem pendentes. Validação técnica e limites da suíte completa em `validacao-cadastros-respostas.json`. Meta 0 e Meta 1 permanecem abertas.

Nesta rodada, **1.108 testes da suíte completa passaram em cada banco** (quatro pulados no PostgreSQL, cinco no SQLite), incluindo 122 testes de cadastros. Check, makemigrations e diff check limpos. A aprovação técnica não encerra as metas nem certifica conversão documental e estados de navegador ainda pendentes.

## Inclusão e histórico de diárias; retornos dos catálogos

Nova vigência, prévia de 15%/30% e histórico reunidos em uma tela própria, com textos do GV e cinco colunas. A integração com as abas da configuração continua pendente. Regras e endpoints existentes de edição/exclusão preservados; cartões e ações adicionais retirados da composição do histórico. Retornos de cargos/combustíveis movidos para após a lista; Limpar remove busca e next como na origem.

Onze novos pares, total de 100 observações parciais. Cálculo ao digitar, calendário, retorno à viatura e erros de mínimo/duplicidade no destino ensaiados. As três vigências permaneceram intactas. 125 testes de cadastros por banco aprovados; check e makemigrations limpos. A última suíte completa de 1.108 por banco antecede este incremento. P08 aguarda decisão sobre o mínimo; limites e logs em `validacao-diarias-catalogos.json`. Nenhuma meta encerrada.

## Calendário de diárias — controles e campo oculto

Componente DS recebeu modo GV optativo, aplicado à vigência: campo de exibição somente leitura, abertura pelo campo ou teclado, semana na segunda-feira, controles mensais e Limpar mantendo o painel aberto. Calendário padrão conferido no formulário de solicitações, sem gravação. Sete novos pares, total de 107 observações parciais.

Retificada a afirmação anterior de digitação livre: o campo de origem é readonly. Inspeção encontrou data visível sem preenchimento do hidden na origem, reproduzida após recarregar; P09 pendente. Nenhum POST foi enviado e não há prova de equivalência do envio. A suíte completa passou com **1.111 testes em cada banco** (quatro pulados no PostgreSQL, cinco no SQLite), check e makemigrations limpos. Logs, avisos e limites em `validacao-calendario-diarias.json`. Metas permanecem abertas.

## Consulta de CEP — endpoint implementado

A rota antes ausente agora resolve para uma consulta sem persistência, com contrato e falhas cobertos por testes. Consulta real ao exemplo oficial retornou o endereço esperado. Navegação direta ao JSON da origem foi recusada pelo navegador; nenhuma prova visual nova foi certificada. A integração institucional depende de P10, registrada com auditoria dos campos.

Classificação atual: 139 correspondências incompletas, 20 ausentes e duas fora de escopo; 161 rotas mantidas. Permanecem 107 pares de capturas e zero rotas certificadas. 131 testes de cadastros aprovados por banco; check e makemigrations limpos. A suíte completa anterior (1.111 por banco) antecede este incremento. Evidência em `validacao-cep.json`.


### Seletor de motoristas — observação adicional

Busca por cargo/CPF, seleção múltipla, remoção e reabertura por setas comparadas em sete pares adicionais. Galeria com 114 pares, sem certificação de novas rotas. 132 testes de Cadastros por banco aprovados. [Validação e limites](validacao-motoristas.json). Metas 0 e 1 permanecem abertas; selo Rascunho e demais estados não comprovados seguem pendentes.


### Selo de rascunho no seletor de motoristas

Selo implementado no resultado e cartão com base no status existente, observado nos dois sistemas. Limite inferior da navegação também comparado. Cinco pares adicionais; galeria com 119 pares, ainda sem novas rotas certificadas. [Testes e limites do retorno](validacao-motoristas-rascunho.json). Metas abertas.


### Retorno à viatura — P11

P11 autorizou manter o retorno na lista de servidores, criação e busca. Corrigido envio de next pelo diálogo de exclusão; origem já o envia. Ensaio com registro temporário do destino criado e removido, cinco testes de respostas por banco aprovados e dois novos pares, totalizando 121. [Validação](validacao-servidores-retorno.json). Sem novas certificações; metas abertas.

### Estados — três rotas implementadas

Lista com inclusão/edição, confirmação e exclusão acrescentadas sobre a base compartilhada. P07 e P12 permanecem pendentes; nenhuma rota certificada. {'existe e está incompleta': 142, 'não existe': 17, 'fora de escopo': 2}. Dez pares novos; total 131. Dados originais preservados. [Ficha](cadastros-estados.md).


Validação atual de Estados: suíte completa com 1.124 testes por banco aprovada, quatro pulados no PostgreSQL e cinco no SQLite. Check e makemigrations limpos. Metas abertas, com P07/P12 e provas restantes pendentes. [Resultado e limites](validacao-estados.json).

## Consulta de cidades após P04 — 10/09/2026

Consulta própria de Viagens com cartões, 15 itens, busca automática por nome/UF/estado e exportação CSV. O cadastro administrativo de Eventos continua em sua rota. P13 mantém a inclusão pendente de decisão sobre Nome, Região e coordenadas. Oito pares reais adicionados, sem gravação na base de desenvolvimento. Classificação atual: 143 incompletas, 16 sem correspondente e 2 fora do escopo; nenhuma certificada. Os 142 testes de cadastros passaram em cada banco, check e makemigrations limpos. A suíte completa de 1.124 casos é anterior a este incremento. [Prova parcial](cadastros-cidades-lista.md) e [validação](validacao-cidades.json).

## Teclado das confirmações após P04 — 10/09/2026

Quinze pares reais adicionados para servidores, cargos, combustíveis, unidades, estados e viaturas. Botões de abertura e ciclo de foco alinhados ao GV; Escape cancela. Next preservado na ação de servidor. Os três registros temporários do destino foram removidos. Os 142 testes de cadastros passaram em cada banco; check, makemigrations e JavaScript limpos. Nenhuma classificação de rota mudou: 143 incompletas, 16 ausentes e 2 excluídas do escopo. Total de 154 pares; nenhuma meta certificada. [Validação](validacao-dialogos.json).

## Grupos acessíveis e busca — 10/09/2026

Três inclusões rápidas alinhadas ao grupo acessível da origem, com correção das conclusões antigas sobre títulos visíveis. Seis buscas alinhadas a type=text e exercitadas sem Enter. Doze pares adicionados, total 166. Sete templates compilados, check e makemigrations limpos. A afirmação anterior de nenhuma gravação foi corrigida: cargo34 criado na origem, aguardando P14; cargo4 do destino removido. Classificação permanece 143 incompletas, 16 sem correspondente e 2 fora do escopo. Meta 0 aberta. [Validação](validacao-grupos-cadastros.json).

## Incidente de escrita na origem

A comparação de grupos de inclusão gravou indevidamente o cargo34 ENSAIO DE CARGO no GV, área1. O cargo4 correspondente no destino foi removido. Consulta somente leitura confirmou ausência de vínculos do cargo34; remoção aguarda autorização excepcional P14. Relatos de nenhuma gravação nessa rodada foram corrigidos. Hashes dos arquivos não comprovam preservação do banco. [Incidente](incidente-cargo-origem.md). Metas continuam abertas.

## Cargo opcional — 10/09/2026

Opção vazia exposta no menu de Cargo do formulário de servidor. Escolha e retirada comparadas sem enviar cadastro, quatro pares novos, total170. Metas e incidente P14 permanecem abertos. [Validação](validacao-cargo-opcional.json).

## Seletores de viatura e suíte completa — 10/09/2026

Combustível permite retirar a escolha pelo item Selecione (opcional). Tipo conserva as duas opções observadas no GV. Seis pares adicionais, total 176; combustível temporário 5 criado e removido somente no destino. Nenhum formulário da origem foi enviado neste ensaio.

Suíte completa aprovada: 1.128 testes no PostgreSQL (206,529 s, quatro pulados) e no SQLite (149,528 s, cinco pulados). Esta execução inclui cidades, diálogos, grupos de cadastro e seletores de cargo/combustível. Check e makemigrations limpos. Avisos de datas sem fuso, bibliotecas do WeasyPrint e exceção do Word COM registrados na [validação](validacao-seletores-viatura.json); ambos os processos terminaram com código zero.

Classificação mantida: 143 rotas incompletas, 16 sem correspondente e duas fora de escopo. Meta 0 aberta, Meta 1 em andamento por P04, zero rotas certificadas. P11 mantém o retorno à viatura autorizado; P14 sobre o cargo34 da origem continua aguardando resposta.


## Pesquisa de lotação — 10/09/2026

Controle de Unidade alinhado nos formulários de servidor e viatura: nome completo e sigla nos resultados, busca sem acentos, limpeza, seleção por teclado e retorno pelo catálogo. Dezenove pares novos (incluindo a diferença anterior), total 195. Unidades temporárias 100/101 removidas somente no destino; nenhum cadastro da origem enviado nesta rodada. Os 142 testes de Cadastros passaram por banco, check e makemigrations limpos. A suíte completa anterior de 1.128 casos antecede este incremento. Classificação mantida: 143 incompletas, 16 sem correspondente e duas fora do escopo, sem rotas certificadas. Metas e P14 permanecem abertos. [Validação e limites](validacao-unidade-picker.json).

## Decisões respondidas — 14/09/2026

As onze pendências abertas foram respondidas pelo usuário na folha
[decisoes-para-o-usuario.md](decisoes-para-o-usuario.md); `decisoes.json` está
atualizado com a resposta, a data e o efeito de cada uma. **Não há mais decisão
aguardando resposta**, e nenhuma meta continua bloqueada por pendência.

Quatro delas foram aplicadas no código na mesma data, com teste que falha sem o
conserto. A suíte de cadastros passou de 142 para 147 casos.

| Item | Decisão | Situação |
|---|---|---|
| P05 | Preservar o padrão ao editar só o nome | aplicado |
| P06 | Edição rápida preserva a lotação | aplicado |
| P12 | Sigla do estado com exatamente duas letras | aplicado |
| P15 | Telefone de 16 para 20; placa já estava certa; RG mantido | aplicado |
| P01 | Assinantes de plano e ordem de serviço não vêm | autorizado, registrar nas fichas |
| P07 | Nome e código do IBGE do estado não mudam | registrar como adaptação |
| P08 | Mínimo da diária continua R$ 0,04 | registrar como adaptação |
| P09 | Data continua em ISO | registrar como diferença deliberada |
| P13 | Nome, região e coordenadas de cidade não mudam | registrar como adaptação |
| P10 | Alinhar a configuração institucional, sem remover campos nossos | **pendente de implementação** |
| P14 | Cargo de ensaio removido pelo usuário, na tela da origem | fora do agente |

Dois pontos que mudaram em relação ao que as perguntas assumiam, conferidos no
código e nos dados em 14/09/2026:

- **A placa já estava em sete caracteres e sem separadores.** A parte da P15 que
  pedia essa mudança estava resolvida antes da resposta.
- **Aumentar o telefone não habilita código de país.** A regra de conteúdo exige
  10 ou 11 dígitos e recusa o DDI; a folga de 20 caracteres serve à pontuação.
  Mudar a regra de conteúdo não foi pedido nem autorizado.

O que ainda falta para a Meta 1 fechar: implementar a P10, registrar nas fichas
as adaptações acima com a respectiva autorização, e a remoção do cargo de ensaio
na origem, que é do usuário. As Metas 2 a 7 continuam sem começar.

## Meta 2 — Roteiros, comparada em 14/09/2026

As duas telas do módulo foram comparadas contra a origem e estão fichadas em
`roteiros-lista.md` e `roteiros-editor.md`. A origem foi lida no código e
consultada somente leitura no banco; não foi aberta no navegador, pelo desvio
de protocolo já registrado em 10/09/2026.

**Lista.** Reescrita para o conteúdo da origem: rota no título com unidade
federativa, selo temporal com as palavras de lá, período, contagem de trechos
e valor na linha, quatro situações combináveis com contagem, e exclusão na
própria linha voltando à lista como estava. Onze testes novos; a suíte do app
foi de 119 para 130 casos.

**Editor.** Já vinha em paridade desde 02/09/2026. A conferência achou uma
lateral que a origem não tem — "Resumo do roteiro" e "Etapas" eram invenção
nossa — e ela saiu inteira, junto com o "Salvar rascunho" que a gravação
automática já cobre. As ações ficaram no rodapé do cartão, como lá: Voltar e
Salvar roteiro, com o aviso de gravação automática só para leitor de tela. A
tabela de trechos perdeu os pisos de largura de 920px e 1050px, que existiam
para a tela de duas colunas e obrigavam a arrastar para o lado.

**Prova.** 220 testes de `viagens_roteiros`, `viagens_oficios` e
`viagens_termos` passando. Tabela de trechos medida no navegador: 875px de
conteúdo em 875px visíveis no desktop, 615px em 615px no tablet, e no celular
ela vira lista empilhada — nenhuma rolagem horizontal em nenhuma das três
larguras, nenhuma célula transbordando.

**Pendência.** P16: a quantidade de diárias é digitada na origem e derivada
aqui, pelo motor da Fase 2. Recomendação é manter derivado e registrar como
adaptação permanente; é diferença visível na tela e aguarda a resposta do dono
do produto, pela regra da seção 4 das metas. Nada mais da Meta 2 depende dela.

## Meta 3 — Ofícios, comparada em 14/09/2026

As telas do módulo estão fichadas em `oficios-lista.md`, `oficios-menus.md`,
`oficios-form.md`, `oficios-detalhe.md` e `oficios-catalogos.md`. A lista e os
menus foram comparados com as capturas e as árvores acessíveis da Meta 0; o
formulário, a conferência e os catálogos não têm fotografia da origem neste
repositório, e o Gerenciador de Viagens não estava disponível no ambiente
desta rodada — a régua foi o modelo, as regras portadas na Fase 4 e o padrão
de cadastros da Meta 1. Isso fica registrado como desvio do protocolo da
seção 6 e pede a conferência lado a lado (P18).

**Lista.** A tabela de seis colunas virou o cartão da origem: cabeçalho com
número e protocolo, período e destinos, selo temporal, equipe com cargo,
unidade e marca de motorista, placa e modelo, trechos com horários, valor
total por extenso, quantidade de diárias e o bloco da justificativa. Filtros
de status/ano/fila viraram busca por número, protocolo, motivo ou destino,
quatro situações combináveis com contagem, seis ordenações (`?sort=`), dois
períodos com calendário e "Limpar"; "Mostrando 1–20 de N" com `?page=`. Os
quatro menus do cartão trazem os dezoito itens com as descrições de lá.
"Novo ofício" passou a criar o rascunho numerado e abrir o editor.

**Formulário.** O laço genérico sobre campos saiu. As seis etapas do wizard
são seções de uma tela só, com os blocos da origem: identificação, motivo,
custeio, equipe com termo por viajante; viatura cadastrada ou não cadastrada,
motorista servidor ou externo com cartão e referência de origem, armas;
roteiro com resumo da rota; regra de prazo e texto da justificativa;
conferência com as pendências. A lateral mostra as seis etapas com o estado
de cada uma.

**Conferência e documentos.** O detalhe reúne as etapas 5 e 6: dados,
equipe e termos, transporte, roteiro e diárias, justificativa, emissão do
ofício e da justificativa (visualizar, PDF, DOCX), termos por servidor e em
lote, documentos gerados com anexação de assinado, mais ações (retificar,
complementar, arquivar, cancelar com motivo, reativar, excluir) e histórico.

**Catálogos.** Motivos e modelos de justificativa passaram ao padrão de
cadastros da Meta 1: lista com busca, situação Ativo/Inativo, modal de
inclusão e edição, "Definir padrão" no menu da linha e exclusão com diálogo.
Não entram no trilho nem nos cartões da entrada de Cadastros.

**Prova.** 21 testes novos em `viagens_oficios/tests/test_paridade_meta3.py`;
a suíte dos apps de viagens passou de 337 para 358 casos. Capturas do destino
em `imagens/meta3-*.png`, ao lado das da origem (`meta0-oficios-*-origem.png`).

**Pendências.** P17 a P20 na folha de decisões: gravação automática das
etapas, conferência do formulário contra a origem, o link "Resumo" no cartão
e a manutenção de `form_simples.html` para as telas fora da meta.

## Meta 4 — Justificativas, comparada em 14/09/2026

Das doze rotas da origem, cinco (modelos) já estavam fiéis desde a Meta 3
(`oficios-catalogos.md`), e a aplicação de modelo ao texto e a regra de prazo
estão no formulário do ofício (`oficios-form.md`). Esta meta trouxe a tela que
faltava: `justificativas:index`, com a inclusão rápida (vários ofícios, um
modelo, um texto — `criar_justificativas_quick_add`, portado na F4 e sem tela
até aqui), a busca de ofícios pelo servidor com teto de 30
(`api_buscar_oficios`, `picker.py`) e a exclusão (`justificativa_delete`).
Ficha em `justificativas-lista.md`; item "Justificativas" na navegação do
módulo. Sem fotografia da origem no repositório: a régua foi o código portado
(P22). Os quatro aliases legados continuam ausentes, à espera da P21.

**Prova.** 8 testes novos em `viagens_oficios/tests/test_paridade_meta4.py`.
Capturas em `imagens/meta4-*.png`.

## Meta 5 — Termos de autorização, comparada em 14/09/2026

As 23 rotas do app `termos` da origem estão cobertas: as 14 do cadastro de
termos pelo app `viagens_termos` e as 9 "pelo ofício" pela conferência do
ofício (Meta 3), agora com `viagens_oficios:termos_todos_pdf` para o PDF
único. Fichas em `termos-lista.md`, `termos-form.md` e
`termos-documentos.md`.

**Lista.** A tabela genérica Termo/Ofício/Destino/Período virou o cartão da
origem, conferido com a árvore acessível da Meta 0: título
"DESTINO/PR · período" (só "PR" quando há apenas a UF), selo "Realizado" /
"Sem período", linha "Ofício: N/AAAA · servidores · placa modelo", e os
quatro comandos — escolher documentos para baixar, anexar termo assinado,
editar e excluir. Busca pelo placeholder da origem (destino, ofício,
protocolo, viatura ou servidor) e as quatro situações combináveis do módulo
no lugar do combobox único. O destino herdado do ofício passou a sair como
"Cidade/UF", como o próprio.

**Cadastro.** `form_simples.html` saiu; a tela tem os blocos da origem:
ofício vinculado com busca no servidor (o mesmo seletor das justificativas,
um só ofício), destino com destinos adicionais e "Adicionar destino" sem
gravar, período, servidores com busca e viatura; ao editar, o aviso do que
o termo herda do ofício. Corrigido de passagem: os pares de destino
adicional não levavam `name` no template anterior desta rodada.

**Documentos.** O detalhe reúne o `termo_cadastro_downloads`: por servidor
(visualizar, PDF, DOCX, anexar assinado), genérico, viatura (variante
completa com os campos do servidor em branco), todos num PDF só
(`todos/pdf/`, consolidado com pypdf) ou em ZIP, documentos gerados e a
prévia em tela com troca de servidor. Cancelar com motivo, reativar e
excluir no mesmo padrão dos ofícios.

**Prova.** 20 testes novos em `viagens_oficios/tests/test_paridade_meta5.py`;
a suíte dos apps de viagens foi a 407 casos. Capturas em
`imagens/meta5-*.png`, ao lado das da origem (`meta0-termos-origem.png`).

**Pendências.** P23 (conferência do cadastro e dos downloads contra a
origem, sem fotografia aqui) e P24 (os selos "Previsto", "Em andamento" e
"Cancelado", que completam os dois da origem).

## Meta 6 — Prestações de contas, comparada em 14/09/2026

As 52 rotas do app `prestacoes_contas` estão cobertas por `viagens_prestacoes`
e pelas páginas públicas de `viagens_assinaturas`; o `card_menus` (fragmento
dos menus do cartão) não precisa de endpoint porque os menus saem no HTML da
lista. Fichas em `prestacoes-lista.md`, `prestacoes-etapas.md` e
`prestacoes-modelos-assinatura.md`.

**Lista.** A tabela Ofício/Servidor/Solicitação/Status/Ações virou o cartão
por servidor da origem, conferido com a árvore acessível da Meta 0: cabeçalho
"N/AAAA · protocolo · destinos · período", selo, número da solicitação que
grava sozinho, botão "Período" das diárias, marca de motorista, "✓
Comprovante", cargo e unidade, aviso por WhatsApp, placa e modelo, trechos
em CIDADE/UF, valor total por extenso e quantidade de diárias, e os cinco
comandos: abrir na etapa 1, escolher documentos para baixar (original,
assinado e pacote), anexar/gerenciar documentos assinados (direto do
cartão), finalizar e arquivar. Busca pelo placeholder da origem e as quatro
filas combináveis com contagem.

**Etapas.** As quatro etapas por servidor têm um esqueleto só (`base.html`):
cabeçalho com etapa, servidor e ofício; lateral com as etapas, a equipe (que
troca de servidor sem sair da etapa), quem saiu da equipe e o resumo do
ofício; rodapé com os comandos. O laço genérico `_campos.html` saiu de todas:
diário de bordo com motorista/viatura, deslocamentos em tabela (km e
abastecimento com autosave) e assinatura; troca de motorista/viatura com os
modos e o preenchimento por outro ofício; relatório técnico com custeio, os
cinco textos com modelo, a diária recebida, documentos e assinatura;
documentos com solicitação/datas e os cinco anexos; PDF final com pendências,
pacote, originais/assinados, finalizar e arquivar.

**Modelos de texto** no padrão de catálogo: abas por campo, busca, inclusão
rápida antes da lista, edição e exclusão com confirmação.

**Prova.** 12 testes novos em `viagens_prestacoes/test_paridade_meta6.py`,
mais os 306 já existentes do app, todos verdes; capturas em
`imagens/meta6-*.png`, ao lado da origem (`meta0-prestacoes-origem.png`).

**Pendências.** P25 (conferência das etapas e menus contra a origem, sem
fotografia aqui), P26 (texto do aviso de WhatsApp) e P27 (a situação como
quatro filas combináveis em vez do combobox único).
