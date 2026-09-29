# Cenários de dados (seed determinístico)

`python manage.py agent_seed --scenario <nome>` (aditivo) · `agent_reset --scenario <nome>` (do zero).
Semente fixa `20260915`, âncora de datas **15/09/2026**; mesma execução → mesmos registros.

| Cenário | Volume por entidade | Para testar |
|---|---|---|
| `empty` | só base (grupos, módulos, cadastros, 10 usuários de papel, tabela de diárias) | estados vazios |
| `small` | 3 | leitura rápida, fixtures de teste |
| `normal` | 25 | uso diário; padrão do lab e das baselines |
| `large` | 300 | paginação, filtros, ordenação |
| `very_large` | 3.000 solicitações (docs limitados a 1.500) | desempenho de listas/consultas |
| `edge_case` | 12, com todos os status, cancelados, textos longos, opcionais vazios e dados "inválidos" | bordas |
| `long_text` | 6, textos no limite do campo | quebra de layout |
| `missing_data` | 6, opcionais vazios | "não informado" |
| `invalid_data` | 6, CPF com dígitos repetidos, 0 servidores… (o que o banco aceita, o formulário recusaria) | robustez de exibição |

Entidades semeadas: solicitações de evento, servidores, viaturas, roteiros (com trechos e destino), ofícios (com equipe →
prestações criadas por signal), publicações, demandas de palestra, atendimentos de imprensa, coffee break (fornecedor,
contrato, lote, solicitações).

Estados de runtime (não são dados): **ERROR / network failure** → `page.route(..., r => r.abort())`;
**PERMISSION_DENIED** → papel `semModulo`; **loading** → `page.route` com atraso.
