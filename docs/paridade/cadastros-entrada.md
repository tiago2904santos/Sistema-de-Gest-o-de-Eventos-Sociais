# Cadastros — entrada

**Meta 0 aberta; Meta 1 em andamento por P04. Observação parcial, sem certificação.** Comparação autenticada em 10/09/2026. [GV](imagens/meta1-cadastros-entrada-origem.png), [Eventos](imagens/meta1-cadastros-entrada-destino.png), [conteúdo observado](imagens/meta1-cadastros-entrada-observacao.json). O par meta0 preserva a apresentação anterior.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Entrada de dados | Sem formulário nesta entrada | Sem formulário nesta entrada | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cadastros principais | Servidores, Cargos, Viaturas, Combustíveis, Unidades, Configurações do sistema, nessa ordem | Mesma sequência de seis cartões | igual |
| Composição dos cartões | Iniciais, categoria, título, descrição e ação Abrir | Mesmos elementos, na composição DS V3.2 | adaptado — pele autorizada na seção 2 |
| Categorias dos cartões | Cadastro para os cinco primeiros; Sistema para Configurações | Mesmos textos | igual |
| Contagens e criação direta | Não apresentados nos cartões | Removidos os contadores e os atalhos Criar novo da entrada; cadastro continua nas respectivas telas | igual |
| Cadastros internos | Grupo de Estados após os principais | Mesmo grupo após os principais; cartão Estados presente | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Abrir categorias compartilhadas | Link Abrir em cada cartão | Mesmo controle nos seis cartões | igual |
| Abrir Servidores | Leva à lista de servidores | Mesmo resultado observado ao clicar no cartão | igual |
| Configurações do sistema | Leva à configuração institucional | Leva à configuração institucional existente; composição interna pendente em ficha própria | igual |
| Abrir Estados | Link ao cadastro de estados | Link abre a nova lista de Estados; navegação exercitada | igual |
| Posição de acesso a diárias | Dentro da configuração, na aba Roteiros | O atalho Tabela de diárias permanece depois dos cartões, até a configuração ser corrigida; fluxo original ausente e sem dispensa | ausente |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Título e apoio | Cadastros; Dados-base e cadastros auxiliares dos fluxos. | Mesmas palavras | igual |
| Grupo principal | Operação; Cadastros principais; Dados compartilhados pelos documentos e fluxos de viagem. | Mesmas palavras | igual |
| Descrições operacionais | Pessoas vinculadas aos fluxos.; Cargos utilizados em servidores.; Veículos operacionais.; Tipos de combustível.; Unidades administrativas. | Mesmas palavras e ordem | igual |
| Descrição de configuração | Dados institucionais e assinaturas por tipo de documento. | Mesmas palavras | igual |
| Grupo interno | Configuração; Cadastros internos; Parâmetros administrativos e referências de apoio. | Mesmos textos | igual |
| Descrição de Estados | Base administrativa interna para suporte à malha de cidades. | Mesmo cartão e texto | igual |

Navegação exercitada pelos cartões: [Servidores](imagens/meta1-entrada-navegacao-servidores-ensaio.json) e [Configurações](imagens/meta1-entrada-navegacao-configuracao-ensaio.json). Nenhum formulário enviado. Pendente: navegação pelos outros quatro cartões, perfis sem permissão e acesso a diárias pela configuração. As permissões das telas de destino permanecem as anteriores; o acesso à configuração continua restrito aos perfis já habilitados.

P07 aguarda autorização para código IBGE opcional e limite 128 do nome de Estado. Auditoria somente leitura: 27 estados, maior nome com 19 caracteres, nenhum acima de 128 ([registro](estados-compatibilidade-nome.json)). Esse levantamento não autoriza alterar esquema; o grupo foi implementado posteriormente sem essa mudança.

Validação deste incremento em `validacao-cadastros-entrada.json`. Nenhuma meta encerrada ou diferença dispensada.


Grupo interno e navegação para Estados implementados sem alterar a base. Par atual `meta1-cadastros-estados-entrada`, com iniciais ES e categoria Base interna. P07 permanece sobre regras dos campos; não impede esta composição. A posição do atalho de diárias e os demais fluxos ainda estão pendentes.
