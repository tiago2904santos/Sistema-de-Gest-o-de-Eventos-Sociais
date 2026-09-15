# Meta 3 — Ofícios · Conferência e documentos

**Origem:** `oficios:wizard_resumo` e `oficios:wizard_documentos` (etapas 5 e 6 do wizard), mais `oficios:detalhe`, `oficio_pdf_inline`, `justificativa_pdf_inline`, `baixar_documento`, `baixar_justificativa_documento`, `excluir`, `cancelar`, `retificar`, `marcar_complementar`.
**Destino:** `viagens_oficios:editar`, em `pages/viagens_oficios/form.html` (o ofício tem uma tela só), com `gerar`, `termo`, `termos_lote`, `acao`, `preview_artefato`, `assinatura_artefato` e `documentos:baixar`.
**Data:** 14/09/2026.

Mesma ressalva da ficha do formulário: não há fotografia das etapas 5 e 6 da origem neste repositório. A régua foi o conteúdo do cartão da lista (que a origem mostra por inteiro), as regras de conferência portadas e o inventário de rotas.

Capturas do destino: [conferência completa](imagens/meta3-oficio-detalhe-destino.png) ([antes](imagens/meta3-oficio-detalhe-antes.png)), [mais ações](imagens/meta3-oficio-detalhe-menu-destino.png), [rascunho com pendências](imagens/meta3-oficio-detalhe-rascunho-destino.png).

## Campos (leitura)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Identificação | número, protocolo, data, unidade, custeio, assunto do documento (Autorização/Convalidação/Retificado/Complementar), motivo | iguais, em "Dados do ofício" | igual |
| Equipe | viajantes com cargo, unidade e motorista; termo por pessoa | igual, com "Sem termo" para quem não recebe termo | igual |
| Transporte | placa, modelo, combustível, tipo; motorista (servidor ou externo com cartão e referência) | iguais | igual |
| Roteiro e diárias | trechos com horários, valor total, por extenso, quantidade de diárias, efetivo considerado; abrir roteiro | iguais | igual |
| Justificativa | regra de prazo e texto; Preenchida/Pendente | iguais | igual |
| Documentos gerados | lista dos artefatos com download, abertura e anexação de assinado | tabela com documento, servidor, data, formato, Baixar, Abrir, Anexar assinado / Assinado | igual |
| Histórico | trilha de auditoria | igual | igual |

## Listagem (conferência)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Estado das seis etapas | resumo com o que falta em cada etapa | lateral "Conferência" com 1–6 e a lista de pendências; aviso no topo "Faltam informações para emitir o documento" com atalho para completar | igual |
| Resumo operacional | — | número, situação, data, viajantes, termos, diárias, valor, documentos | **adaptado**: acréscimo de pele (lateral do detalhe V3.2) |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Emitir ofício | visualizar (inline), PDF, DOCX | "Visualizar ofício" (nova aba), "Baixar PDF", "Baixar DOCX" | igual |
| Emitir justificativa | visualizar, PDF, DOCX | iguais | igual |
| Termos | por servidor (menu) e em lote | menu por servidor e "Todos em PDF/DOCX (ZIP)" | igual |
| Anexar assinado | por documento | por documento gerado e no menu do termo | igual |
| Editar ofício | volta ao wizard | botão principal, com `?next=` para a conferência | igual |
| Retificar, complementar, cancelar, excluir | rotas próprias | menu "Mais ações" com as mesmas descrições; cancelar pede o motivo na seção "Cancelamento"; retificar/complementar desfazem no mesmo item | igual |
| Arquivar / reativar | `STATUS_ARQUIVADO` e reativação já existiam aqui | "Arquivar ofício" no menu; "Reativar ofício" quando cancelado | **adaptado**: mantido o que já estava em produção aqui |
| Prestação de contas | fora do wizard | atalho "Abrir prestação de contas" na lateral | **adaptado**: ligação com a Meta 6, já existente |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Pendências | frases de `validar_oficio_para_documento` | as mesmas | igual |
| Pronto | — | "Pronto para emissão." | **adaptado** |
| Cancelado | — | aviso com motivo e data; documentos bloqueados ("Ofício cancelado: reative para emitir documentos.") | **adaptado** |
| Erro de geração | mensagem do motor | mensagem de erro no topo (já existia) | igual |
| Ações | — | "Ofício N marcado como retificado.", "… identificado como complementar.", "… arquivado.", "… cancelado. O histórico foi mantido.", "… reativado.", "… excluído. O número volta para a sequência.", bloqueio por vínculo | **adaptado** |
