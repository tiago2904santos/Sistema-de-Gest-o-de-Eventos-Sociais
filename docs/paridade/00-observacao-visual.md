# Observação inicial do inventário — 10/09/2026

Os dois sistemas foram abertos no navegador com o usuário Tiago. Origem: `http://127.0.0.1:8000/`; destino: `http://localhost:8021/`. A sigla DPC exibida na sessão do GV foi conferida na lista de áreas: corresponde a **policia Civil, área 1**. A captura `imagens/meta0-area-gv.png` registra essa correspondência. A lista de ofícios da origem mostrou 59 registros.

Esta observação confirma divergências do inventário; **não certifica paridade**. Não foram submetidos cadastros, exclusões, documentos ou alterações de negócio na origem. Os quantitativos diferentes refletem bancos distintos; esta etapa não executa importação de dados.

## Comparações registradas

As capturas originais e os registros de conteúdo exibido estão em `imagens/meta0-<tela>-origem.png`, `imagens/meta0-<tela>-destino.png` e `imagens/meta0-<tela>-observacao.json`. A [galeria local](imagens/comparacao-inicial.html) apresenta cada par lado a lado, sem modificar as capturas.

- **Servidores:** GV com cartões, iniciais, nome, cargo, CPF, RG, telefone e unidade; busca, filtro por cargo, paginação de 25 itens e ações Editar/Excluir. Destino com tabela, sem RG e sem filtro por cargo, além da coluna Qualidade. Classificação mantida: existe e está incompleta.
- **Roteiros:** GV com cartões de percurso, período, número de trechos, valor e ações Editar/Excluir. Destino com tabela Tipo/Sede/Destinos/Servidores/Diárias/Situação, e ação Abrir. Classificação mantida: existe e está incompleta. A composição do formulário da F2 ainda será conferida separadamente.
- **Ofícios:** GV com ordenação por número, filtros de situação e período, paginação e cartões contendo equipe, veículo, trechos, valores, justificativa e menus de documentos/ações. Destino com filtros Busca/Situação/Ano/Fila e tabela com ação Abrir. Classificação mantida: existe e está incompleta.
- **Justificativas:** GV lista justificativas aplicadas aos ofícios, com busca, paginação, cadastro, edição e exclusão. O catálogo acessível no destino contém modelos de justificativa. A comparação evidencia funções distintas: o catálogo não atende à rota `justificativas:index`, que continua marcada como não existe.
- **Termos:** GV com cartões de destino/período, situação, servidores, ofício/viatura quando presentes, escolha de documentos, anexação, edição e exclusão. Destino com busca, opção Cancelados e tabela; o banco de destino apresentou estado vazio. As ações de uma linha preenchida do destino não foram inferidas desse estado. Classificação mantida: existe e está incompleta.
- **Prestações:** GV com cartões por servidor, solicitação editável, período de diárias, equipe, veículo, trechos, valores, downloads, anexação, finalização e arquivamento. Destino com abas de fila, busca/status e tabela com Abrir/Documentos/Arquivar/PDF final. Classificação mantida: existe e está incompleta.

## Limites e pendências

As seis capturas iniciais foram ampliadas conforme o registro abaixo. Os quadros são observações parciais: estados ainda não exercitados continuam pendentes e nenhuma observação transforma uma rota em “existe e está fiel”.

A captura anterior `meta0-gv-servidores-inicial.png`, feita antes da autenticação atual, mostrou apenas um registro e não deve ser usada como evidência da área 1. A captura autenticada `meta0-servidores-origem.png` a substitui para essa finalidade e mostra 174 registros.

A página `/perfil/` da origem apresentou `ImproperlyConfigured` ao carregar credenciais do Drive. A área ativa foi confirmada pela lista de áreas, que abriu normalmente. O erro do perfil não foi corrigido nem usado como padrão de tela: perfil e Drive estão fora do escopo destas 161 rotas.

A decisão P01 sobre assinantes de PT/OS continua pendente. A decisão P02 preserva a permissão atual de edição de diárias no destino.

## Formulário de servidor — observação adicional

O par `imagens/meta0-servidor-form-{origem,destino}.png` e o arquivo `imagens/meta0-servidor-form-campos.json` registram a tela de novo servidor e os atributos dos seus controles no navegador.

- Ambos exibem os seis campos na ordem Nome, Cargo, CPF, RG, Telefone e Unidade. Somente Nome é obrigatório. A referência histórica a CPF obrigatório em `CADASTROS_FUNCIONAL.md` não descreve a tela atual observada.
- GV agrupa Nome/Cargo/CPF/RG/Telefone em “Identificação funcional” e Unidade em “Lotação”. O destino distribui os campos por três blocos: “Identificação funcional”, “Documentos pessoais” e “Contato e lotação”.
- GV informa “Só o nome é obrigatório; demais campos podem ser completados depois.” e usa Voltar/Salvar. O destino apresenta outros textos de apoio e Cancelar/Criar registro.
- GV tem acessos Gerenciar cargos/Gerenciar unidades e pesquisa de unidade. Esses acessos não aparecem no formulário atual do destino.
- CPF usa máscara e limite de 14 caracteres nos dois lados. RG usa limite 20 no GV e 30 no destino; Telefone usa limite 20 no GV e 16 no destino. As divergências estão registradas, sem alteração de validações nesta etapa.
- O cargo padrão da origem apareceu preenchido; o destino abriu sem cargo selecionado. Os bancos têm configurações diferentes, portanto essa observação isolada não prova falha da regra de valor padrão.

Nenhum formulário foi enviado. Validações após envio, mensagens de sucesso e persistência não foram certificadas por esta observação.

## Decisão de sequência

P03: o usuário determinou **“Não, manter a Meta 0 aberta”** ao ser consultado sobre encerrar apenas o inventário e tratar as provas completas nas metas seguintes. A Meta 0 permanece aberta; as comparações iniciais não autorizam iniciar a Meta 1.

Posteriormente, **P04 autorizou expressamente as correções com a Meta 0 aberta**. A Meta 1 começou por servidores; nenhuma meta foi encerrada e nenhuma ausência foi dispensada. A restrição anterior de não iniciar correções foi substituída apenas quanto à sequência.

## Ampliação dos cadastros

Foram consolidados **46 pares de capturas reais**, vinculados a **22 entradas do inventário**, com **16 documentos de quatro quadros**. São observações, não provas concluídas. A [galeria](imagens/comparacao-inicial.html) mostra todos os pares e explicita quando os estados ou funções não são equivalentes.

- [Servidores — lista e busca](cadastros-servidores-lista.md): filtro por cargo expandido e busca sem resultado.
- [Servidor — cadastro](cadastros-servidor-form.md): campos, ordem, obrigatoriedade, limites e acessos de gestão.
- [Servidor — exclusão](cadastros-servidor-exclusao.md): diálogo preventivo no GV e bloqueio por vínculo no destino; nenhum envio.
- [Cargos](cadastros-cargos.md): lista, inclusão rápida, ação de padrão e tentativa de edição que permaneceu na lista do GV.
- [Combustíveis](cadastros-combustiveis.md): lista e inclusão rápida comparada ao formulário próprio.
- [Unidades](cadastros-unidades.md): lista e inclusão rápida; formulário completo da origem ainda não comprovado.
- [Viaturas — lista](cadastros-viaturas-lista.md): informações e opções do filtro expandido.
- [Viatura — cadastro](cadastros-viatura-form.md): campos, agrupamento, seleção de motoristas e acessos de gestão.
- [Configuração](cadastros-configuracao.md): abas Instituição/Ofício e dependência de assinantes PT/OS; P01 continua pendente.
- [Diárias](cadastros-diarias.md): formulário e histórico; permissão preservada por P02, sem alegar ensaio visual de todos os perfis.
- [Entrada dos cadastros](cadastros-entrada.md): ordem, grupos, textos e acessos a Configurações e Estados.
- [Estados](cadastros-estados.md): lista e inclusão rápida no GV; a imagem do destino mostra a entrada de Cadastros, pois não há rota pública equivalente.
- [Cidades — lista](cadastros-cidades-lista.md): paginação para a segunda página, busca sem resultado e limpeza exercitadas nos dois sistemas.
- [Cidade — inclusão](cadastros-cidade-form.md): inclusão rápida no GV e diálogo no destino; diferenças entre Capital/IBGE/coordenadas e Região registradas sem mudar campos ou regras.

As fichas usam `igual` apenas para propriedades descritas e observadas, `adaptado` para a decisão P02 e `ausente` para elementos da origem não reproduzidos. Nenhuma ausência dessas fichas foi dispensada. Limitações de amostragem e estados não exercitados são indicados no texto, sem transformá-los em ausências confirmadas. Quantidades diferentes entre bases não são classificadas como falhas.

As capturas de inclusão rápida não comprovam o contrato de envio de suas rotas. O clique de edição de cargo não abriu editor na origem: sua imagem foi preservada como tentativa, sem inventar evidência de funcionamento ou decidir descartar um possível defeito. Ações de gravar, excluir e definir padrão não foram submetidas.

## Aprofundamento da lista de ofícios

Mais onze pares documentam os filtros de situação, seis opções de ordenação, sua aplicação por Enter na busca, calendários de Viagem/Criação, quatro menus do cartão, busca sem resultado e opções da Fila do destino. Os quadros estão em [oficios-lista.md](oficios-lista.md) e [oficios-menus.md](oficios-menus.md). As 16 fichas atuais incluem 14 de cadastros e duas de ofícios.

A seleção de Número: menor alterou inicialmente apenas o controle; após Enter, o GET incluiu `sort=numero_asc` e a lista passou a começar por 01/2026, 02/2026 e 03/2026. Os menus foram confirmados nas imagens, pois a árvore acessível nem sempre refletiu a expansão. A lista do destino oferece Abrir; o conteúdo do detalhe ainda precisa ser comparado, portanto não se concluiu que as funções dos menus estejam ausentes de todo o destino.

Os calendários visuais Viagem e Criação compartilham o mesmo nome acessível na origem, embora abram painéis diferentes. A duplicidade foi registrada sem decisão de correção ou dispensa. Nenhum item de geração, cancelamento, retificação, exclusão ou anexação foi acionado. Novo ofício na origem é um POST e não foi acionado. A Meta 3 não começou: estas observações ampliam a régua da Meta 0.

## Correção inicial de servidores — P04

Foram implementados cartões com RG e iniciais, filtro pelos três cargos mais frequentes com contagens dependentes da busca, paginação de 25, mensagens do estado sem resultado e confirmação de exclusão em diálogo. O formulário usa campos explicitamente posicionados em Identificação funcional e Lotação, com Voltar/Salvar e links de gerenciamento que preservam o rascunho ao retornar. A view de exclusão conserva a proteção de vínculos e as permissões preexistentes.

Quatro pares `meta1-*` registram lista, formulário, confirmação preventiva e busca sem resultado. As fichas de servidores foram atualizadas; as evidências anteriores permanecem no histórico. O retorno de Gerenciar cargos restaurou o nome fictício digitado no ensaio; ele foi apagado sem salvar. Não houve criação ou exclusão de dados reais nos ensaios de navegador.

Validação: **94 testes de cadastros aprovados em PostgreSQL e 94 em SQLite**, check sem problemas e makemigrations sem alterações; detalhes em [validacao-servidores.json](validacao-servidores.json). Essa execução não substitui a suíte completa exigida para fechar a meta. Os limites de RG/telefone, o texto de ajuda de RG e demais estados ainda pendentes impedem certificar fidelidade completa. Nenhuma meta foi encerrada.
