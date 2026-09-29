# Módulos do produto

Fonte: `ui-inventory/navigation.json` (registro `MODULOS_PORTAL`) e `README.md` do projeto.

| Módulo | Código de acesso | Itens de navegação | Função |
|---|---|---|---|
| Agenda | aberto | 1 | Agenda institucional (FullCalendar), pauta semanal, assinatura ICS |
| Relatório | aberto | 1 | Relatórios consolidados |
| Eventos Sociais | aberto (perfis) | 3 | Solicitações de eventos: RASCUNHO → AGUARDANDO_DESPACHO → DEFERIDA/ATENDIDA/NÃO ATENDIDA/CANCELADA (decisão da DG) |
| Coffee Break | ASCOM_COFFEE_BREAK | 6 | Contratos, lotes, solicitações, fornecedor por link, notas e pagamento |
| Palestras e Eventos | ASCOM_DEMANDAS_EVENTOS | 3 | Demandas de palestra/evento, pedido público |
| Publicações | ASCOM_PUBLICACOES | 3 | Pautas e publicações |
| Atendimento à Imprensa | ASCOM_ATENDIMENTO_IMPRENSA | 3 | Pedidos de jornalistas |
| Viagens | VIAGENS | 12 | Cadastros (servidores, viaturas, diárias), roteiros e diárias, ofícios/justificativas/termos, viagem, ordens de serviço, planos de trabalho, prestações de contas, documentos |

Perfis: SOLICITANTE, GESTOR_DG, ADMINISTRADOR (eventos); VIAGENS_GESTOR, VIAGENS_OPERADOR (viagens; módulo sem grupo = consulta).
Setor ↔ Módulo decide o acesso; superusuário ignora restrições.
