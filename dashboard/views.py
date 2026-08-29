from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    """Dashboard inicial com indicadores (dados mockados nesta etapa)."""
    resumo = [
        {"titulo": "Solicitações no mês", "valor": 18, "variacao": "+3 em relação a julho"},
        {"titulo": "Aguardando despacho", "valor": 5, "variacao": "2 com prazo próximo"},
        {"titulo": "Atendidas no ano", "valor": 112, "variacao": "87% de atendimento"},
        {"titulo": "Eventos nos próximos 30 dias", "valor": 7, "variacao": "3 com unidade móvel"},
    ]
    ultimas_solicitacoes = [
        {
            "id": 1042,
            "municipio": "Curitiba",
            "tipo_evento": "Ação social",
            "data_inicio": "05/09/2026",
            "status": "AGUARDANDO_DESPACHO",
            "status_label": "Aguardando despacho",
        },
        {
            "id": 1041,
            "municipio": "Londrina",
            "tipo_evento": "Feira de serviços",
            "data_inicio": "12/09/2026",
            "status": "EM_ANALISE",
            "status_label": "Em análise",
        },
        {
            "id": 1040,
            "municipio": "Maringá",
            "tipo_evento": "Mutirão CIN",
            "data_inicio": "20/09/2026",
            "status": "ATENDIDA",
            "status_label": "Atendida",
        },
        {
            "id": 1039,
            "municipio": "Cascavel",
            "tipo_evento": "Ação social",
            "data_inicio": "28/08/2026",
            "status": "NAO_ATENDIDA",
            "status_label": "Não atendida",
        },
        {
            "id": 1038,
            "municipio": "Ponta Grossa",
            "tipo_evento": "Evento institucional",
            "data_inicio": "30/08/2026",
            "status": "ENVIADA",
            "status_label": "Enviada",
        },
    ]
    return render(
        request,
        "pages/dashboard/index.html",
        {"resumo": resumo, "ultimas_solicitacoes": ultimas_solicitacoes},
    )
