# Meta 2 — Roteiros · Editor

**Origem:** `roteiros:novo` e `roteiros:editar`, em `roteiro_form_page.html`,
`includes/_roteiro_editor_v2.html` e três parciais (`_origem_body`,
`_bate_volta`, `_retorno_body`), 537 linhas somadas.
**Destino:** `viagens_roteiros:novo` e `viagens_roteiros:editar`, em
`pages/viagens_roteiros/form.html` e três parciais, 748 linhas somadas.
**Data:** 14/09/2026.

Este editor foi portado em 02/09/2026 com auditoria de paridade própria, e não
é o caso da tela genérica: estimativa por trecho, rota gravada, calendário
sequencial, bate-volta por dia, autosave e chip de estado das diárias já vieram
de lá. Esta ficha confere o que restou.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Estado e cidade da sede | `origem_estado`, `origem_cidade` | `origem_estado`, `origem_municipio` | igual |
| Destinos | lista com tipo de destino | lista de destinos | igual |
| Bate-volta: datas, horas e tempos | `bate_volta_*`, seis campos | `bv_*`, seis campos | igual |
| Rota do mapa | `map_route_*`, seis campos ocultos | `rota_*`, seis campos ocultos | igual |
| Trechos: saída, chegada, distância, tempos | por trecho | por trecho | igual |
| Retorno | bloco próprio com saída, chegada, distância, duração, tempo adicional e fonte | o retorno é o último trecho, com os mesmos campos | **adaptado**: composição diferente, mesmo conteúdo |
| `quantidade_servidores` | campo do editor | fora da tela | **adaptado**, autorizado pelo dono do produto em 01/09/2026 |
| `quantidade_diarias` | digitado pelo operador | derivado pelo motor de cálculo da F2 (`resumo_diarias`) | **adaptado**: ver pendência abaixo |
| Observações | não exibido | não exibido | igual |

## Ações e comportamento

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Gravação automática do rascunho | `roteiro-autosave` e `-create` | `autosave` e `autosave_novo` | igual |
| Cálculo das diárias | `calcular_diarias` | `previa_diarias` e `calcular` | igual |
| Estimativa de trecho | `trechos_estimar` | `estimar_trecho` | igual |
| Rota pelo mapa | `calcular_rota` e `calcular_rota_preview` | `calcular_rota` atende os dois usos | **adaptado**: um endereço no lugar de dois |
| Cidades por estado | `api_cidades_por_estado` | cascata no cliente (`dependente_de`) | **adaptado**: sem ida ao servidor |
| Excluir | tela de confirmação própria (`confirm_delete.html`) | confirmação no diálogo (`data-confirmar-exclusao`), na linha da lista | **adaptado**: sem página intermediária |
| Cancelar, reativar e recalcular | não existe no editor | não existe no editor; o cartão "Situação do roteiro" foi retirado em 14/09/2026 | igual |
| Ações do formulário | rodapé do cartão: Voltar e Salvar roteiro, e o aviso de gravação automática só para leitor de tela | igual | igual |
| Painel lateral | não existe | não existe | igual |
| Tela de detalhe | não existe | não existe; o endereço antigo redireciona | igual |

## Pendência que precisa de decisão

**A quantidade de diárias é digitada na origem e derivada aqui.** Lá o operador
escreve quantas diárias o roteiro rende; aqui o motor da Fase 2 calcula e grava
o resumo, e a tela mostra o que ele produziu. Reproduzir a digitação permitiria
que o documento oficial dissesse um número e o cálculo, outro. Reproduzi-la
também contraria a caracterização que fixou o cálculo ao centavo contra os
demonstrativos oficiais.

Recomendação: manter derivado e registrar como adaptação permanente. **Aguarda
decisão do dono do produto**, porque é diferença visível na tela e não pode ser
dispensada sem autorização, pela regra da seção 4 das metas.

## O que mudou no destino nesta meta

A comparação achou uma lateral que a origem não tem. O editor de lá é uma
coluna só, com as ações no rodapé do cartão; aqui havia um `aside` com
"Resumo do roteiro" e "Etapas", ambos invenção nossa. A lateral saiu inteira,
e com ela o botão "Salvar rascunho" — a gravação automática já é o rascunho.

- `aside.editor-roteiro__lateral` removido; o editor passou a uma coluna
  (`grid-template-columns: minmax(0, 1fr)`).
- Ações no rodapé do cartão: Voltar e Salvar roteiro, com o aviso de gravação
  automática em `sr-only`, como na origem.
- O cartão "Situação do roteiro" (recalcular, cancelar, reativar, excluir),
  que morava na lateral, foi retirado do editor a pedido do dono do produto.
  As rotas continuam existindo no servidor; excluir segue na linha da lista.
- `roteiro-editor.js` perdeu as oito escritas em `data-resumo-*` e a marcação
  de etapa, que não têm mais destino.
- A tabela de trechos deixou de ter piso de largura: os pisos de 920px e
  1050px existiam para a tela de duas colunas e obrigavam a arrastar para o
  lado. Agora ela divide a largura disponível (`table-layout: fixed`), e a
  dica "arraste para ver mais" saiu do `app.js`.
- Ajustes de acabamento pedidos na revisão da tela: rótulo da métrica na mesma
  linha do ícone, primeiro destino sem a folga da alça de arrastar, resumo do
  bate-volta escondido enquanto vazio, e a data escolhida em preto no lugar do
  cinza claro.

## Situação da tela

Comparada. Fora a pendência acima, as diferenças estão marcadas como adaptadas,
com o motivo na linha.

Prova: 220 testes de `viagens_roteiros`, `viagens_oficios` e `viagens_termos`
passando depois das mudanças, e a tabela de trechos medida no navegador em
875px de conteúdo para 875px visíveis — sem rolagem horizontal e sem célula
transbordando.
