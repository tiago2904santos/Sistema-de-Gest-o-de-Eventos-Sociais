# Estados — lista, inclusão, edição e exclusão

**Metas 0 e 1 abertas; implementação parcial por P04, sem certificação.** A ausência de tela observada nos pares meta0 é histórica. A nova lista usa a base Estado compartilhada com Eventos. Os 27 registros originais foram preservados, incluindo metadados; não houve alteração de esquema. P07 e P12 continuam pendentes.

Pares atuais na [galeria](imagens/comparacao-inicial.html#meta1-estados-lista): `meta1-estados-lista`, `meta1-estados-inclusao`, `meta1-estados-busca`, `meta1-estados-edicao`, `meta1-estados-confirmacao`, `meta1-estados-exclusao-direta`, `meta1-estados-sem-resultado`, `meta1-estados-edicao-recolhida`. Capturas da área visível, com DOM completo nos respectivos JSONs. [Atributos observados](imagens/meta1-estados-campos.json).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nome | Texto obrigatório, limite 128; primeiro campo | Campo presente, mas limite 150 preservado até P07; limite original ausente, sem dispensa | ausente |
| Sigla: apresentação | Texto obrigatório, limite 2; segundo campo | Mesmos atributos observados | igual |
| Codigo ibge | Numérico opcional; terceiro campo | Numérico obrigatório pela base atual; opcionalidade ausente, P07 pendente | ausente |
| Composição | Três campos em um grupo; sem títulos extras visíveis | Mesma composição com input V3.2, conforme seção 2 | adaptado |
| Busca | Buscar estados | Mesmo rótulo e envio automático | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Identificação | Nome, sigla e IBGE; exemplo PARANÁ, PR · 41 | Mesmos dados no cartão Paraná; grafias e quantidade pertencem a bases diferentes | igual |
| Composição | Cartões com sigla de identificação e ações | Cartões DS V3.2 com os mesmos elementos; pele permitida na seção 2 | adaptado |
| Busca sem acentos | parana encontra PARANÁ | parana encontra Paraná | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cadastrar estado | Expande inclusão na lista | Mesma expansão observada | igual |
| Editar | Abre os três campos preenchidos na própria lista | Mesma composição e valores do registro local | igual |
| Recolher edição incompleta | Limpar Nome, recolher e reabrir limpa os campos e volta à ação de criação | Mesma sequência; action não permanece na edição | igual |
| Excluir na lista | Diálogo preventivo; cancelado por Voltar | Mesmo diálogo e cancelamento, com componentes V3.2 permitidos | adaptado |
| URL direta de exclusão | Página confirma nome, permanência e bloqueio por cidades | Mesmos textos e Voltar, sem enviar | igual |
| Abrir pelo teclado | Botão Excluir acionado por Space abre a confirmação e foca Voltar | Mesmo comportamento observado | igual |
| Circular o foco | Shift+Tab de Voltar leva a Excluir; Tab de Excluir leva a Voltar | Mesmo ciclo observado, corrigido para não perder foco fora do diálogo | igual |
| Cancelar pelo teclado | Escape fecha a confirmação sem envio | Mesmo fechamento observado sem envio | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Título | Estados | Estados | igual |
| Identificação acessível do grupo | Dados do estado — Nome, sigla e código IBGE | Mesma identificação acessível | igual |
| Sem resultado | Nenhum registro cadastrado; Nenhum estado cadastrado ainda. | Mesmas mensagens | igual |
| Diálogo | Excluir estado?; aviso de vínculos; ação permanente | Mesmos textos | igual |
| Página de confirmação | Não é possível excluir se existirem cidades vinculadas. | Mesmo texto | igual |

Paginação do destino exercitada: 15 itens na primeira página e 12 na segunda, Mostrando 16–27 de 27. A origem tem um Estado nesta sessão, portanto não há prova pareada de múltiplas páginas. [Registro](imagens/meta1-estados-pagina2-destino.json). A pesquisa considera nome/sigla, sem acentos, como na origem; não inclui IBGE.

Ensaio de escrita **somente no destino**: criado Estado temporário 28, ENSAIO ESTADO PARIDADE 20260910, sigla ZT/IBGE 999; nome atualizado com sufixo EDITADO e registro removido pelo diálogo após conferir o alvo. Foram observadas mensagens Estado criado/atualizado/excluído com sucesso. A tentativa de nova inclusão com sigla PR foi recusada e preservou os campos preenchidos, com resumo focado. [CRUD](imagens/meta1-estados-crud-ensaio.json), [erro](imagens/meta1-estados-erro-destino.json). Comparação integral dos 27 estados antes/depois confirmou que nenhum original mudou; registro temporário removido. Nenhum POST na origem.

A escrita reutiliza a barreira já existente na administração Django: usuário ativo, staff e permissão do modelo para adicionar, alterar ou excluir. Ter apenas o módulo Viagens não concede escrita na base compartilhada. Leitura exige acesso ao módulo. As permissões de outros perfis na origem ainda não foram comparadas; isso não certifica equivalência de acesso. Ativo e campos de legado não entram no formulário e são preservados na edição. Bloqueios por municípios são respeitados; teste verifica ausência de auditoria de exclusão em caso protegido.

P07: Nome 150/IBGE obrigatório permanecem, sem alteração de esquema. P12: validação de Sigla exatamente 2 caracteres solicitada; todos os 27 existentes já têm 2, mas a regra atual aceita 1 ou 2 e permanece. As diferenças não foram dispensadas. Demais erros da origem, perfis e responsividade ainda precisam de ensaios pareados. Não foram declaradas rotas certificadas.

Validação e limites desta rodada em [validacao-estados.json](validacao-estados.json); 138 testes de Cadastros passaram em cada banco. Suíte completa aprovada: 1.124 testes por banco, com quatro pulados no PostgreSQL e cinco no SQLite. Check, makemigrations e sintaxe JavaScript limpos. Avisos preexistentes de conversão documental registrados no JSON; aprovação dos testes não certifica visualmente a conversão de documentos.


Maiúsculas comparadas no par `meta1-estados-maiusculas`: digitados ensaio de estado e zt; ao sair de Sigla, ambos apresentaram ENSAIO DE ESTADO e ZT. Nenhum envio. [Valores observados](imagens/meta1-estados-maiusculas.json). O botão considera todos os campos obrigatórios: a diferença do IBGE preservada sob P07 afeta quando passa de Cadastrar para Salvar.

## Teclado das confirmações após P04 — 10/09/2026

Comparação real: o destino antes deixava o foco sair do diálogo ao usar Shift+Tab em Voltar; o GV o levava ao botão Excluir. O ciclo foi alinhado. A ação da lista agora usa botão, como a origem, permitindo abertura por Space. O envio continua no botão Excluir dentro da confirmação, com a mesma URL, permissões e regras da view.

Pares: [meta1-estados-exclusao-teclado](imagens/meta1-estados-exclusao-teclado-observacao.json), [meta1-estados-exclusao-ciclo-foco](imagens/meta1-estados-exclusao-ciclo-foco-observacao.json). [Sequência de teclas e foco](imagens/meta1-dialogos-teclado-ensaio.json); [validação](validacao-dialogos.json). Capturas JPEG originais, sem edição, na galeria.

Somente no destino, três registros temporários foram criados e removidos para exercitar as listas vazias: combustível 4, unidade 99 e viatura 3 (ZZT9T91). Nenhum servidor foi vinculado. Ausência desses registros confirmada no banco. Os demais registros foram apenas usados para abrir e cancelar diálogos. Nenhum POST na origem. Sucesso e bloqueios após POST da origem continuam pendentes; a comparação do teclado não os certifica.

## Composição e busca conferidas em 10/09/2026

A busca usa type=text como no GV. O rótulo e o exemplo coincidem; zzgrupo20260910 foi digitado sem Enter nas duas telas. A consulta automática manteve termo e foco e mostrou as mensagens sem resultado. [Atributos e URLs reais](imagens/meta1-cadastros-busca-tipos-depois.json).

Pares atuais: [meta1-estados-busca-texto](imagens/meta1-estados-busca-texto-observacao.json). JPEGs originais na [galeria](imagens/comparacao-inicial.html#meta1-estados-busca-texto). A declaração anterior de nenhuma gravação foi corrigida: o ensaio de cargo criou o registro34 na origem e o registro4 no destino. Ver incidente abaixo.

Validação: sete templates compilados; check e makemigrations limpos; campos e buscas exercitados no navegador. A suíte de 142 testes por banco aprovada na rodada de diálogos antecede este ajuste de apresentação e não foi repetida. As metas e as demais pendências continuam abertas. [Registro](validacao-grupos-cadastros.json).

## Correção do relato da rodada de grupos

A rodada gravou indevidamente ENSAIO DE CARGO no GV (cargo34, área1) e no destino (cargo4). O registro do destino foi removido; a remoção na origem aguarda P14. As capturas e os atributos observados permanecem evidências dos estados mostrados, mas a rodada não cumpriu a restrição de origem somente leitura. [Registro completo e prevenção](incidente-cargo-origem.md). Nenhuma meta pode ser certificada com base na declaração anterior de ausência de gravação.
