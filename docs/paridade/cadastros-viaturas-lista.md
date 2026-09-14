# Viaturas — lista e filtros

**Metas 0 e 1 abertas. Correção parcial autorizada por P04; sem certificação completa.**

Pares atuais: [cartões GV](imagens/meta1-viaturas-cartoes-ensaio-origem.png)/[Eventos](imagens/meta1-viaturas-cartoes-ensaio-destino.png), [opções GV](imagens/meta1-viaturas-filtro-opcoes-origem.png)/[Eventos](imagens/meta1-viaturas-filtro-opcoes-destino.png), [filtro aplicado GV](imagens/meta1-viaturas-filtro-aplicado-origem.png)/[Eventos](imagens/meta1-viaturas-filtro-aplicado-destino.png), [sem resultado GV](imagens/meta1-viaturas-sem-resultado-origem.png)/[Eventos](imagens/meta1-viaturas-sem-resultado-destino.png), [confirmação GV](imagens/meta1-viaturas-confirmacao-origem.png)/[Eventos](imagens/meta1-viaturas-confirmacao-destino.png).

O destino usa uma viatura temporária de ensaio nas capturas preenchidas. Não se equiparam as bases. A viatura ZZZ0Z99 e seu combustível foram removidos ao final; o servidor fictício preexistente não foi removido nem editado. [Registro da limpeza](imagens/meta1-viaturas-limpeza-ensaio.json). Capturas `meta0-*` preservadas como histórico.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca | Buscar viaturas | Mesmo rótulo e termo preservado após envio | igual |
| Filtro | Controle de unidade ou combustível com contagens | Componente select V3.2; adaptação visual permitida pela seção 2 | adaptado |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Identificação | Cartão com iniciais, modelo e placa no título | Mesma composição, nas classes V3.2 permitidas pela seção 2 | adaptado |
| Linha de informações | Placa, unidade, combustível, tipo e nomes dos motoristas, nesta ordem | Mesma ordem e conteúdo no cartão de ensaio; referências e quantidades são próprias de cada banco | igual |
| Filtro de combustível | DIESEL (2) retorna duas viaturas | Combustível de ensaio (1) retorna uma viatura; diferença de dados, mesmo recorte | igual |
| Busca dentro do filtro | GET conserva combustível selecionado ao procurar termo inexistente | GET conserva combustível selecionado; capturas de sem resultado registradas | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nova viatura | Link ao final da lista | Link ao final da lista | igual |
| Editar | Ação por cartão | Ação por cartão; fidelidade do formulário continua pendente na ficha própria | igual |
| Excluir: abertura | Diálogo com identificação da viatura | Mesma identificação e redação, em diálogo V3.2 permitido pela seção 2 | adaptado |
| Limpar | Remove busca e recorte, retornando à lista | Mesmo resultado exercitado | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca sem resultado | Nenhum registro cadastrado; Nenhuma viatura cadastrada ainda. | Mesmas palavras | igual |
| Aviso de exclusão | Você está prestes a excluir… Se houver vínculos com outros registros, a exclusão será bloqueada. | Mesmas palavras | igual |
| Aviso permanente | Esta ação é permanente e não poderá ser desfeita. | Mesmas palavras | igual |

Pendências para certificar: paginação no navegador com mais de 15 itens, filtro da unidade configurada no destino, top três com base equivalente, rascunhos e motoristas ausentes, perfis sem edição, exclusão protegida e respectivas mensagens, formulário próprio de criação/edição. Os testes cobrem paginação, filtros inválidos, prioridade do combustível, busca sem acentos em todos os dados e deduplicação de viaturas com vários motoristas; isso não substitui as comparações visuais pendentes.

Validação deste incremento: 108 testes de cadastros em PostgreSQL e 108 em SQLite, todos aprovados; check e makemigrations limpos. A última suíte completa de 1.088 testes é anterior a esta correção da lista; não representa fechamento da Meta 1.

## Busca automática após P04

A busca agora envia o GET após um segundo sem digitação, com foco e cursor restaurados. O par `meta1-viaturas-busca-automatica` registra o termo zzbuscaautomatica e as mensagens sem resultado nos dois lados, sem pressionar Enter. Essa observação não certifica os demais estados da tela. Paginação compartilhada ajustada para as mesmas reticências e limites desabilitados; os ensaios de múltiplas páginas deste incremento foram feitos em unidades. Validação atual em `validacao-cadastros-busca.json`.

Validação atual desta rodada: 117 testes de cadastros e 1.103 testes completos por banco, aprovados (quatro dispensas no PostgreSQL; cinco no SQLite). [Logs e limitações](validacao-cadastros-busca.json). Substitui os resultados anteriores como evidência técnica atual, sem certificar a meta.

A confirmação de exclusão foi comparada por teclado em 10/09/2026: Space abre, Shift+Tab/Tab circulam entre ações e Escape cancela. A viatura temporária ZZT9T91 foi removida após o ensaio; nenhuma confirmação foi enviada na origem. [Prova de teclado](cadastros-viatura-exclusao.md).

## Composição e busca conferidas em 10/09/2026

A busca usa type=text como no GV. O rótulo e o exemplo coincidem; zzgrupo20260910 foi digitado sem Enter nas duas telas. A consulta automática manteve termo e foco e mostrou as mensagens sem resultado. [Atributos e URLs reais](imagens/meta1-cadastros-busca-tipos-depois.json).

Pares atuais: [meta1-viaturas-busca-texto](imagens/meta1-viaturas-busca-texto-observacao.json). JPEGs originais na [galeria](imagens/comparacao-inicial.html#meta1-viaturas-busca-texto). A declaração anterior de nenhuma gravação foi corrigida: o ensaio de cargo criou o registro34 na origem e o registro4 no destino. Ver incidente abaixo.

Validação: sete templates compilados; check e makemigrations limpos; campos e buscas exercitados no navegador. A suíte de 142 testes por banco aprovada na rodada de diálogos antecede este ajuste de apresentação e não foi repetida. As metas e as demais pendências continuam abertas. [Registro](validacao-grupos-cadastros.json).

## Correção do relato da rodada de grupos

A rodada gravou indevidamente ENSAIO DE CARGO no GV (cargo34, área1) e no destino (cargo4). O registro do destino foi removido; a remoção na origem aguarda P14. As capturas e os atributos observados permanecem evidências dos estados mostrados, mas a rodada não cumpriu a restrição de origem somente leitura. [Registro completo e prevenção](incidente-cargo-origem.md). Nenhuma meta pode ser certificada com base na declaração anterior de ausência de gravação.
