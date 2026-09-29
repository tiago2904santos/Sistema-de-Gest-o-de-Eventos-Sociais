# Auditoria de banco

Gerado em 2026-09-29T14:07:29-03:00.

- Cascatas sensíveis (apagar usuário/município/servidor apaga dependentes): **9**
- FKs anuláveis: 139
- Campos de rastreio do legado (`legado_*`): 106
- Modelos sem `ordering` (paginação pode oscilar): 15
- Modelos com constraints declaradas: 74

## Cascatas sensíveis

- accounts.AssinaturaAgenda.usuario → accounts.User (CASCADE)
- accounts.PautaSemanal.usuario → accounts.User (CASCADE)
- core.Feriado.municipio → cadastros.Municipio (CASCADE)
- core.Notificacao.usuario → accounts.User (CASCADE)
- viagens_cadastros.AssinaturaSubstituicao.servidor → viagens_cadastros.Servidor (CASCADE)
- viagens_ordens.OrdemServicoDestino.municipio → cadastros.Municipio (CASCADE)
- viagens_prestacoes.PrestacaoServidor.servidor → viagens_cadastros.Servidor (CASCADE)
- viagens_roteiros.DistanciaMunicipios.destino → cadastros.Municipio (CASCADE)
- viagens_roteiros.DistanciaMunicipios.origem → cadastros.Municipio (CASCADE)

## Dados

- Tabelas vazias: 67
- Duplicidades em chaves naturais: 0
