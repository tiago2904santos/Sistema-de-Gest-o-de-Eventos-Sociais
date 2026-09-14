# Registro de gravação indevida na origem — 10/09/2026

Na rodada de comparação de grupos de inclusão, o cargo **34 — ENSAIO DE CARGO**, área 1, foi gravado no GV, contrariando a exigência de origem somente leitura. O cargo **4** também foi criado no destino. A declaração anterior de que nenhum formulário foi enviado estava incorreta.

O passo problemático ocorreu após preencher o nome e tentar limpar o campo: o botão Cadastrar cargo, usado para recolher o painel, também pode enviar o formulário. O valor efetivo não foi verificado antes do clique. O motivo exato de a tentativa de limpeza não ter evitado o envio não foi reproduzido na origem, para não gerar outra escrita.

Uma consulta SQL com `default_transaction_read_only=on` confirmou o cargo34, criação em 10/09/2026 às16:51:47-03, não padrão. Não há vínculos nas três tabelas que referenciam cargos: servidores, efetivo de plano e efetivo de evento. A leitura desses vínculos não executou qualquer função dos módulos excluídos do escopo. Os nomes ENSAIO DE COMBUSTIVEL e ENSAIO DE UNIDADE não foram encontrados nas respectivas tabelas.

O cargo4 do destino foi identificado pelo nome e URL de exclusão e removido pelo navegador. Sua ausência e a ausência dos outros dois nomes de ensaio no destino foram confirmadas. O cargo34 da origem permanece, aguardando a autorização excepcional P14 para remoção. Não houve tentativa de apagar auditoria ou alterar qualquer outro registro.

[Consulta e estado da correção](incidente-cargo-origem.json). Os hashes de arquivos de rotas continuam conferindo; isso prova somente preservação desses arquivos, não preservação do banco. A rodada não satisfaz a restrição de somente leitura da origem.

Para os próximos ensaios, entradas temporárias da origem serão abandonadas por recarregamento ou navegação GET. Não será usado o botão de cadastro para recolher um painel que recebeu dados, pois ele também pode salvar. Opções de seleção e buscas GET podem ser comparadas sem enviar formulários de cadastro. Qualquer limpeza do dado indevido depende da autorização específica de P14.
