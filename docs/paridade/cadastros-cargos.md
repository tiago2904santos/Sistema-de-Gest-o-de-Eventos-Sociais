# Cargos — lista e inclusão rápida

**Metas 0 e 1 abertas; correções autorizadas por P04, sem certificação completa.**

Pares atuais: [lista GV](imagens/meta1-cargos-lista-origem.png)/[Eventos](imagens/meta1-cargos-lista-destino.png), [inclusão GV](imagens/meta1-cargo-inclusao-origem.png)/[Eventos](imagens/meta1-cargo-inclusao-destino.png). Capturas anteriores `meta0-*` preservadas como histórico.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cargo | Texto obrigatório, limite 120, vazio e habilitado | Mesmo campo na inclusão rápida | igual |
| Placeholder | Nenhum exemplo | Nenhum exemplo | igual |
| Composição da inclusão | Um campo no grupo Dados do cargo — Nome do cargo | Grupo nomeado com o mesmo campo explícito, usando input V3.2 | adaptado — somente componentes e pele, conforme seção 2 |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca | Buscar cargos | Mesmo rótulo e busca na lista | igual |
| Nome e ação de padrão | Nome no cartão, selo no padrão, ação direta nos demais | Nome e ação direta observados; padrão atual difere entre as bases | igual |
| Composição | Cartões | Cartões com componentes e classes V3.2, conforme seção 2 | adaptado |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cadastrar cargo | Expande o painel na lista; vazio pode ser recolhido | Expansão e recolhimento exercitados | igual |
| Rota direta Novo | Abre o catálogo com inclusão recolhida | Mesma composição; par meta1-cargo-rota-novo | igual |
| Editar na lista | Editor dentro da lista observado para cargo | Ainda abre formulário separado; composição original ausente, sem autorização | ausente |
| Abrir pelo teclado | Botão Excluir acionado por Space abre a confirmação e foca Voltar | Mesmo comportamento observado | igual |
| Circular o foco | Shift+Tab de Voltar leva a Excluir; Tab de Excluir leva a Voltar | Mesmo ciclo observado, corrigido para não perder foco fora do diálogo | igual |
| Cancelar pelo teclado | Escape fecha a confirmação sem envio | Mesmo fechamento observado sem envio | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Apoio da inclusão | Dados do cargo — Nome do cargo nomeia o grupo acessível, sem título ou subtítulo visível | Mesmo nome acessível; títulos visuais duplicados removidos | igual |
| Confirmação antes de excluir | Excluir cargo?; aviso de vínculos e de ação permanente; Voltar/Excluir | Mesmos textos e cancelamento exercitado, diálogo V3.2 permitido pela seção 2 | adaptado |

A edição foi finalmente observada no navegador: o botão Editar abre o campo Cargo no trilho da lista, preenchido. A tentativa anterior não comprovava um defeito. O destino ainda abre formulário separado; par [origem](imagens/meta1-cargo-edicao-pendente-origem.png)/[destino](imagens/meta1-cargo-edicao-pendente-destino.png). Não foi salvo o editor da origem.

Confirmação de exclusão comparada sem confirmar: [origem](imagens/meta1-cargo-confirmacao-origem.png)/[destino](imagens/meta1-cargo-confirmacao-destino.png).

A ação direta de padrão foi implementada reutilizando a regra transacional existente. Os testes verificam que GET não grava, POST troca o padrão único, preserva a auditoria e bloqueia leitores. Isso não substitui a comparação visual após gravar.

Pendências: edição inline (P05); comparação dos estados de escrita com a origem, especialmente erro/exclusão bloqueada; paginação no navegador; transformação de maiúsculas comparada; retorno entre formulários; perfis sem permissão nos dois sistemas. O destino mantém a edição genérica até a correção desses fluxos. Nenhuma ausência foi dispensada.

Validação técnica deste incremento: 99 testes de cadastros em PostgreSQL e 99 em SQLite, ambos aprovados. `check`, `makemigrations --check --dry-run` e verificação de espaços limpos. Suíte completa e prova de toda a meta continuam pendentes.

## Ensaios adicionais de fluxo no destino

A rota direta `/novo/` foi comparada com as duas páginas abertas: [GV](imagens/meta1-cargo-rota-novo-origem.png)/[Eventos](imagens/meta1-cargo-rota-novo-destino.png). As respostas de criação e exclusão voltam ao catálogo e preservam o caminho de retorno validado. Erro de duplicidade mantém o campo preenchido e o painel aberto, com resumo “Corrija antes de continuar”.

Foi criado e removido o cargo temporário `ENSAIO PARIDADE CARGOS 20260910 01`; a tentativa duplicada foi recusada. Capturas somente do destino: [criação](imagens/meta1-cargo-criado-ensaio.png) e [duplicidade](imagens/meta1-cargo-duplicado-ensaio.png).

[Registro dos ensaios](imagens/meta1-catalogos-fluxos-ensaio.json). Estes ensaios de escrita são somente do destino e não constituem comparação de gravação na origem. A exclusão com vínculo protegido foi verificada nos testes, sem apagar o registro. Nenhum campo ou validação foi dispensado.

Validação após os ajustes de fluxo: 102 testes de cadastros por banco e **1.088 testes da suíte completa por banco**, todos aprovados, com quatro dispensas no PostgreSQL e cinco no SQLite. `check`, `makemigrations --check --dry-run` e verificação de espaços limpos. Logs e limites em [validacao-catalogos-fluxos.json](validacao-catalogos-fluxos.json).

A composição das iniciais dos catálogos foi alinhada à origem: duas primeiras letras para nome de uma palavra, primeira/última inicial nos nomes compostos; combustível usa CT. Par adicional do combustível: `meta1-combustiveis-marcador`. P05 permanece pendente para edição.

## Busca automática após P04

A busca agora envia o GET após um segundo sem digitação, com foco e cursor restaurados. O par `meta1-cargos-busca-automatica` registra o termo zzbuscaautomatica e as mensagens sem resultado nos dois lados, sem pressionar Enter. Essa observação não certifica os demais estados da tela. Paginação compartilhada ajustada para as mesmas reticências e limites desabilitados; os ensaios de múltiplas páginas deste incremento foram feitos em unidades. Validação atual em `validacao-cadastros-busca.json`.

Validação atual desta rodada: 117 testes de cadastros e 1.103 testes completos por banco, aprovados (quatro dispensas no PostgreSQL; cinco no SQLite). [Logs e limitações](validacao-cadastros-busca.json). Substitui os resultados anteriores como evidência técnica atual, sem certificar a meta.

## Retornos e entrada de texto após P04

O link de retorno passou para depois da lista, como na origem. Pares desta rodada: `meta1-cargos-retorno-rodape`, `meta1-cargos-busca-com-retorno`, `meta1-cargos-limpar-retorno`. Busca com next manteve o retorno até usar Limpar; Limpar removeu busca e next nos dois sistemas. A navegação pelo atalho Gerenciar cargos da origem voltou ao formulário nesta rodada; a comparação do catálogo foi feita abrindo diretamente o href observado, portanto o fluxo completo do atalho continua pendente.

A edição rápida continua pendente de P05. Validação desta rodada em `validacao-diarias-catalogos.json`; não constitui fechamento das metas.

## Teclado das confirmações após P04 — 10/09/2026

Comparação real: o destino antes deixava o foco sair do diálogo ao usar Shift+Tab em Voltar; o GV o levava ao botão Excluir. O ciclo foi alinhado. A ação da lista agora usa botão, como a origem, permitindo abertura por Space. O envio continua no botão Excluir dentro da confirmação, com a mesma URL, permissões e regras da view.

Pares: [meta1-cargos-exclusao-teclado](imagens/meta1-cargos-exclusao-teclado-observacao.json), [meta1-cargos-exclusao-ciclo-foco](imagens/meta1-cargos-exclusao-ciclo-foco-observacao.json). [Sequência de teclas e foco](imagens/meta1-dialogos-teclado-ensaio.json); [validação](validacao-dialogos.json). Capturas JPEG originais, sem edição, na galeria.

Somente no destino, três registros temporários foram criados e removidos para exercitar as listas vazias: combustível 4, unidade 99 e viatura 3 (ZZT9T91). Nenhum servidor foi vinculado. Ausência desses registros confirmada no banco. Os demais registros foram apenas usados para abrir e cancelar diálogos. Nenhum POST na origem. Sucesso e bloqueios após POST da origem continuam pendentes; a comparação do teclado não os certifica.

## Composição e busca conferidas em 10/09/2026

A classificação anterior dos títulos de apoio era imprecisa: a origem usa essas palavras apenas no nome acessível do grupo. O destino agora faz o mesmo, com fieldset nomeado e campos explícitos; os títulos visuais adicionais foram removidos. Capturas anteriores permanecem históricas. Foram conferidos campo vazio e preenchido, ordem, tipo, obrigatoriedade, limites e transformação em maiúsculas. A comparação real dos atributos resultou igual nos três grupos. Isso não certifica os resultados após POST. [Atributos](imagens/meta1-grupos-cadastro-atributos.json).

A busca usa type=text como no GV. O rótulo e o exemplo coincidem; zzgrupo20260910 foi digitado sem Enter nas duas telas. A consulta automática manteve termo e foco e mostrou as mensagens sem resultado. [Atributos e URLs reais](imagens/meta1-cadastros-busca-tipos-depois.json).

Pares atuais: [meta1-cargos-grupo-acessivel](imagens/meta1-cargos-grupo-acessivel-observacao.json), [meta1-cargos-grupo-preenchido](imagens/meta1-cargos-grupo-preenchido-observacao.json), [meta1-cargos-busca-texto](imagens/meta1-cargos-busca-texto-observacao.json). JPEGs originais na [galeria](imagens/comparacao-inicial.html#meta1-cargos-grupo-acessivel). A declaração anterior de nenhuma gravação foi corrigida: o ensaio de cargo criou o registro34 na origem e o registro4 no destino. Ver incidente abaixo.

Validação: sete templates compilados; check e makemigrations limpos; campos e buscas exercitados no navegador. A suíte de 142 testes por banco aprovada na rodada de diálogos antecede este ajuste de apresentação e não foi repetida. As metas e as demais pendências continuam abertas. [Registro](validacao-grupos-cadastros.json).

## Correção do relato da rodada de grupos

A rodada gravou indevidamente ENSAIO DE CARGO no GV (cargo34, área1) e no destino (cargo4). O registro do destino foi removido; a remoção na origem aguarda P14. As capturas e os atributos observados permanecem evidências dos estados mostrados, mas a rodada não cumpriu a restrição de origem somente leitura. [Registro completo e prevenção](incidente-cargo-origem.md). Nenhuma meta pode ser certificada com base na declaração anterior de ausência de gravação.
