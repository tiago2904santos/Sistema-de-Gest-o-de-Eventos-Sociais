# Meta 5 — Termos de autorização · Documentos e prévia

**Origem:** `termos:termo_cadastro_downloads`, `termo_cadastro_pdf_inline`, `termo_cadastro_generico_pdf_inline`, `termo_cadastro_servidor_pdf_inline`, `termo_cadastro_viatura_pdf_inline`, `baixar_termo_cadastro_pdf`, `baixar_termo_cadastro_docx`, `baixar_termo_cadastro_viatura`, `baixar_termo_cadastro_generico`, `baixar_termo_cadastro_servidor`, `termo_cadastro_generico_assinado_anexar`, `termo_cadastro_servidor_assinado_anexar`; e, pelo ofício, `preview_termo_oficio`, `termo_servidor_pdf_inline`, `termo_oficio_assinado_anexar`, `baixar_termo_servidor`, `baixar_termos_todos_pdf`, `baixar_termo_lote_zip`.
**Destino:** `viagens_termos:detalhe`, `preview`, `preview_servidor`, `gerar`, `gerar_viatura`, `lote`, `todos_pdf`, `acao`; `viagens_oficios:assinatura_artefato`, `preview_artefato`, `documentos:baixar`; pelo ofício, `viagens_oficios:termo`, `termos_lote`, `termos_todos_pdf` (Meta 3).
**Data:** 14/09/2026.

Sem fotografia da tela de downloads da origem no repositório; a régua foram as rotas e os serviços portados (`build_termo_cadastro_payload`, variantes `semipreenchido` / `completo_com_viatura` / `completo_sem_viatura`). Fica registrado como desvio do protocolo (P23).

Capturas do destino: [termo avulso](imagens/meta5-termo-detalhe-destino.png) ([antes](imagens/meta5-termo-detalhe-antes.png)), [termo preso a um ofício](imagens/meta5-termo-detalhe-oficio-destino.png), [prévia em tela](imagens/meta5-termo-previa-destino.png).

## Campos (leitura)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Dados do termo | destino, período, ofício, viatura | iguais, com "Herdado do ofício" quando vem de lá; ofício com protocolo e ligação ao detalhe | igual |
| Resumo | — | situação, servidores, viatura, documentos, criado em | **adaptado**: lateral do detalhe V3.2 |
| Documentos gerados | lista de artefatos | tabela documento / servidor / gerado em / formato, com Baixar, Abrir e Anexar assinado / Assinado | igual |

## Listagem (documentos que o termo emite)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Por servidor | `servidor/<pk>/pdf-inline/`, `servidor/<pk>/<formato>/`, `servidor/<pk>/assinado/anexar/` | Visualizar (PDF inline em nova aba), PDF, DOCX, Anexar assinado (inativo até haver PDF) | igual |
| Genérico | `pdf-inline/generico/`, `generico/<formato>/`, `generico/assinado/anexar/` | "Termo genérico — Só destino e período, semipreenchido": Visualizar, Baixar PDF, Baixar DOCX; anexar assinado no menu da lista e nos documentos gerados | igual |
| Viatura | `viatura/pdf-inline/`, `viatura/<formato>/` | "Termo da viatura — placa modelo, campos do servidor em branco": Visualizar, Baixar PDF, Baixar DOCX; só quando há viatura efetiva | igual |
| Todos | `pdf/` (um PDF só), `docx/` (ZIP) | "PDF único" (`todos/pdf/`, consolidado com pypdf), "ZIP de PDFs", "ZIP de DOCX" | igual |
| Prévia em tela | `pdf-inline` | "Abrir prévia" — o payload lido como documento, com troca de servidor; o PDF inline continua em "Visualizar" | **adaptado**: acréscimo daqui, o PDF inline é o mesmo da origem |
| Sem servidor | — | "Nenhum servidor: o termo sai só na versão genérica, para preencher à mão." | **adaptado** |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Geração | GET | POST em formulários de um botão; `?inline=1` abre em nova aba | igual (o método é infraestrutura daqui) |
| Editar termo | link | botão principal, `?next=` de volta ao detalhe | igual |
| Excluir | `termos:excluir` | menu "Mais ações do termo" com confirmação | igual |
| Cancelar / reativar | — | seção "Cancelamento" com motivo; "Reativar termo" no menu quando cancelado | **adaptado**: `ModeloCancelavel` já existia aqui |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nome do PDF único | `termo-<pk>-todos.pdf` | igual | igual |
| Cancelado (termo ou ofício) | — | "Reative o termo e o ofício antes de gerar documentos."; aviso com motivo no topo; botões de geração escondidos | **adaptado** |
| Erro do motor | mensagem do motor | mensagem de erro no topo e volta ao detalhe | igual |
| Formato inválido | 404 | 404 | igual |
