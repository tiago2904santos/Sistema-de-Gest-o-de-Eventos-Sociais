# Servidores — lista e busca

**Meta 0 aberta; observação parcial, sem certificação de fidelidade.** Comparação em 10/09/2026, GV na área 1 e Eventos autenticados. Os bancos contêm registros diferentes; quantidades e valores não são divergências de regra.

**Correção iniciada após P04:** [lista atual GV](imagens/meta1-servidores-lista-origem.png)/[destino](imagens/meta1-servidores-lista-destino.png), [busca vazia atual GV](imagens/meta1-servidores-sem-resultado-origem.png)/[destino](imagens/meta1-servidores-sem-resultado-destino.png). As tabelas abaixo refletem os elementos corrigidos; as imagens `meta0` preservam o estado anterior. Ainda não é prova completa da meta.

Evidências: [origem](imagens/meta0-servidores-origem.png), [destino](imagens/meta0-servidores-destino.png), [filtro da origem](imagens/meta0-servidores-filtro-cargo-origem.png), [filtro do destino](imagens/meta0-servidores-filtro-cargo-destino.png), [busca vazia na origem](imagens/meta0-servidores-sem-resultado-origem.png), [busca vazia no destino](imagens/meta0-servidores-sem-resultado-destino.png). Conteúdo exibido nos respectivos arquivos `-observacao.json`.

`igual` abaixo vale somente para o elemento descrito. `ausente` identifica uma composição ou comportamento da origem ainda não reproduzido; **nenhuma dessas ausências foi autorizada**.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca textual | Campo de busca, preenchido com `ZZZ_PARIDADE_SEM_RESULTADO` no ensaio | Mesmo termo permaneceu visível após a busca | igual |
| Seletor de cargo | Select com opções e contagens | Controle select do DS V3.2; Todos e cargos frequentes, contagens respeitam busca | adaptado — componente visual autorizado na seção 2 |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Conteúdo por servidor | Cartão com iniciais e nome; metadados na ordem cargo, CPF, RG, telefone e unidade, sem rótulos adicionais | Mesma ordem e formato de metadados; selo Rascunho quando aplicável | igual |
| Busca automática com recorte | Após uma pausa, adilson encontra o servidor dentro de cargo=1; foco no campo | Após uma pausa, robson encontra o servidor dentro de cargo=1; foco no campo | igual |
| Paginação em página única | Régua ausente quando o filtro tem uma página | Régua ausente com uma página | igual |
| Filtro por cargo | Todos e os três cargos mais frequentes da base, com contagens | Mesma regra; no banco observado, Todos (6) e MOTORISTA (5); seleção reduziu a lista para cinco | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Limpar busca | Limpar exibido após buscar | Limpar exibido após buscar | igual |
| Editar e Excluir: presença | Ações por servidor | Ações por servidor; comportamento de exclusão registrado separadamente | igual |
| Novo servidor no rodapé | Ação ao final da lista | Ação ao final da lista, inclusive sem resultado | igual |
| Retorno à viatura | View prepara next, mas template não exibe Voltar nem repassa à criação/busca | Mantidos Voltar à viatura e next na criação/busca, autorizados por P11 | adaptado |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca sem resultado | “Nenhum registro cadastrado”; “Nenhum servidor cadastrado ainda.” | Mesmas duas mensagens, verificadas com o mesmo termo | igual |
| Recuperação da busca vazia | Busca mantém o termo e oferece Limpar | Busca mantém o termo e oferece Limpar | igual |

Pendente: comparação de todos os estados de seleção, ordenação, segunda página no navegador, perfis sem permissão, carregamento e erro. Paginação de 25, pesquisa sem acentos por nome/cargo/unidade, filtro e contagens foram exercitados em testes isolados nos dois bancos. Seleção de MOTORISTA foi exercitada no navegador do destino. A busca não gravou dados. A mensagem da origem foi reproduzida.

## Select e busca automática após P04

O menu de cargos foi substituído pelo componente select do DS. O envio ocorre após um segundo, como no GV. As iniciais agora usam a primeira e a última palavra nos nomes compostos. A régua deixa de aparecer quando há uma página e usa a mesma faixa com reticências. Pares: `meta1-servidores-filtro-select`, `meta1-servidores-filtro-cargo-aplicado`, `meta1-servidores-busca-automatica-cargo`. Origem: Todos (174) e cargo escolhido AGENTE DE POLÍCIA JUDICIÁRIA (119). Destino: Todos (6) e MOTORISTA (5). Busca preservou cargo=1 e o foco, com valores diferentes das respectivas bases. [Foco observado](imagens/meta1-servidores-foco-busca-ensaio.json). Nenhum servidor gravado. Demais pendências e Meta 0 continuam abertas.

Validação atual desta rodada: 117 testes de cadastros e 1.103 testes completos por banco, aprovados (quatro dispensas no PostgreSQL; cinco no SQLite). [Logs e limitações](validacao-cadastros-busca.json). Substitui os resultados anteriores como evidência técnica atual, sem certificar a meta.

## Ordem dos dados após P04

A linha de metadados foi alinhada à ordem cargo, CPF, RG, telefone e unidade, sem acrescentar rótulos que não aparecem na origem. Par real `meta1-servidores-ordem-dados`, com registros diferentes das duas bases. Nenhum modelo, valor ou regra de validação foi alterado. Os testes de 1.103 casos completos acima antecedem este incremento de apresentação; ver `validacao-cadastros-entrada.json`.


## Retorno autorizado por P11

O usuário autorizou “Preservar o retorno atual e documentar”. O GV prepara `back_url` e `next_url` em `servidores_index`, mas o template de lista não apresenta esse retorno. O link Novo servidor usa a URL sem next; o formulário de busca envia apenas q e cargo. O comportamento foi confirmado com a URL de lista contendo next: botão de retorno ausente na origem e busca removendo next. O destino conserva o caminho para a viatura, conforme P11. [Par da busca](imagens/meta1-servidores-busca-retorno-p11-observacao.json).

A exclusão é independente dessa adaptação: a origem já transmite next pela ação do diálogo. O destino passou a incluí-lo no link que o diálogo copia para action. A view já preservava esse retorno, mas a tela não o enviava. [Par da confirmação](imagens/meta1-servidores-exclusao-retorno-observacao.json).

Ensaio somente no destino: criado o servidor temporário 8, ENSAIO RETORNO P11 20260910, por Novo servidor com next. Salvar retornou à viatura. O mesmo registro foi excluído pelo diálogo após conferir nome e identificador; a lista manteve next e exibiu Servidor excluído com sucesso. Voltar à viatura funcionou. Ausência do registro confirmada no banco; nenhum outro servidor foi removido. [Registro](imagens/meta1-servidores-retorno-p11-ensaio.json). Nenhum POST na origem.

P11 não autoriza omissões nas demais ações ou estados. [Validação técnica e limites](validacao-servidores-retorno.json); metas continuam abertas.

Abertura da confirmação por botão e teclado alinhada ao GV em 10/09/2026. O endereço de exclusão agora vem de data-delete-url; o next autorizado por P11 continua chegando à action. O teste existente passou a extrair a URL do botão real, mantendo o ensaio de GET sem remoção e POST com auditoria. [Ações reais com retorno](imagens/meta1-dialogos-retorno-action.json) e [devolução de foco](imagens/meta1-dialogos-foco-retorno.json).

## Composição e busca conferidas em 10/09/2026

A busca usa type=text como no GV. O rótulo e o exemplo coincidem; zzgrupo20260910 foi digitado sem Enter nas duas telas. A consulta automática manteve termo e foco e mostrou as mensagens sem resultado. [Atributos e URLs reais](imagens/meta1-cadastros-busca-tipos-depois.json).

Pares atuais: [meta1-servidores-busca-texto](imagens/meta1-servidores-busca-texto-observacao.json). JPEGs originais na [galeria](imagens/comparacao-inicial.html#meta1-servidores-busca-texto). A declaração anterior de nenhuma gravação foi corrigida: o ensaio de cargo criou o registro34 na origem e o registro4 no destino. Ver incidente abaixo.

Validação: sete templates compilados; check e makemigrations limpos; campos e buscas exercitados no navegador. A suíte de 142 testes por banco aprovada na rodada de diálogos antecede este ajuste de apresentação e não foi repetida. As metas e as demais pendências continuam abertas. [Registro](validacao-grupos-cadastros.json).

## Correção do relato da rodada de grupos

A rodada gravou indevidamente ENSAIO DE CARGO no GV (cargo34, área1) e no destino (cargo4). O registro do destino foi removido; a remoção na origem aguarda P14. As capturas e os atributos observados permanecem evidências dos estados mostrados, mas a rodada não cumpriu a restrição de origem somente leitura. [Registro completo e prevenção](incidente-cargo-origem.md). Nenhuma meta pode ser certificada com base na declaração anterior de ausência de gravação.
