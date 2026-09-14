# Meta 3 — Ofícios · Menus do cartão

**Origem:** os quatro menus observados no ofício 161/2026 em 10/09/2026 (`imagens/meta0-oficios-menu-*-origem.png`).
**Destino:** `pages/viagens_oficios/_cartao.html` (lista) e `detalhe.html` (conferência).
**Data:** 14/09/2026.

Capturas do destino: [ações](imagens/meta3-oficios-menu-acoes-destino.png), [documentos](imagens/meta3-oficios-menu-documentos-destino.png), [termo por pessoa](imagens/meta3-oficios-menu-termo-destino.png), [justificativa](imagens/meta3-oficios-menu-justificativa-destino.png). Origem: [ações](imagens/meta0-oficios-menu-acoes-origem.png), [documentos](imagens/meta0-oficios-menu-documentos-origem.png), [termo](imagens/meta0-oficios-menu-termo-origem.png), [justificativa](imagens/meta0-oficios-menu-justificativa-origem.png).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Entrada de dados nos menus | nenhuma | nenhuma; o motivo do cancelamento é pedido na tela de conferência | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Onde ficam | rodapé do cartão: lápis, pasta, mais ações; menu junto a cada viajante; lápis e pasta no bloco da justificativa | mesmos lugares | igual |
| Abertura | menu flutuante com título, ícone, rótulo e descrição por item | menu do V3.2 (`data-menu`) com título, ícone, rótulo em negrito e descrição | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Mais ações | Retificar ofício · Atualizar o estado de retificação; Ofício complementar · Identificar o documento como complementar; Cancelar ofício · Interromper o fluxo mantendo o histórico; Excluir ofício · Remover permanentemente quando permitido | mesmos rótulos e descrições; POST com confirmação em dois toques para cancelar e excluir | igual |
| Documentos do ofício | Visualizar ofício · Abrir o documento no navegador; Baixar PDF · Documento pronto para impressão; Baixar DOCX · Arquivo editável do ofício | iguais; "Visualizar" gera o PDF e abre em nova aba (`?inline=1`) | igual |
| Termo individual | Visualizar termo · Abrir o documento no navegador; Baixar PDF · Documento pronto para assinatura; Baixar DOCX · Arquivo editável do termo; Anexar assinado · Enviar o PDF depois da assinatura | iguais; "Anexar assinado" leva à tela de anexação do último PDF do termo daquele servidor e fica inativo, com a explicação, enquanto o PDF não foi gerado | igual (inativo explicado é acréscimo) |
| Documentos da justificativa | Visualizar justificativa · Abrir o documento no navegador; Baixar PDF · Documento pronto para impressão; Baixar DOCX · Arquivo editável da justificativa | iguais | igual |
| Cancelado | não observado | os menus de documento e de termo somem; "Reativar ofício · Retomar o fluxo do documento" entra no lugar de cancelar | **adaptado**: sem fotografia da origem para o caso |
| Ofício ou termo por GET | a origem abre `oficio-pdf-inline` e `baixar_documento/<formato>` por GET | aqui a geração é POST (`gerar`, `termo`), como a Fase 4 definiu; o menu envia formulários | **adaptado**: contrato de geração da F4, autorizado no plano mestre |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Descrições dos itens | as dezoito frases acima | as mesmas dezoito | igual |
| Confirmação | não observada (nenhum item foi acionado) | "Confirmar cancelamento?" / "Confirmar exclusão?" no próprio botão, por quatro segundos | **adaptado**: padrão de confirmação deste projeto |
| Retorno | não observado | mensagem no topo com o número do ofício e a ação | **adaptado** |

Pendente para a origem: destino de cada item e confirmações não foram exercitados lá (nada que grave, gere ou anexe foi acionado na Meta 0). O que está igual aqui é o conteúdo do menu e o que cada item faz segundo a descrição.
