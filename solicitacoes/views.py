from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def nova_solicitacao(request):
    """Tela "Nova Solicitação de Evento Social".

    Nesta etapa o formulário é apenas layout: as opções dos selects são
    mockadas e o envio ainda não persiste dados.
    """
    contexto = {
        "tipos_evento": ["Ação social", "Feira de serviços", "Mutirão CIN", "Evento institucional"],
        "municipios": ["Curitiba", "Londrina", "Maringá", "Cascavel", "Ponta Grossa"],
        "regioes": ["Curitiba e RM", "Norte", "Noroeste", "Oeste", "Campos Gerais"],
        "orgaos": ["Instituto de Identificação", "Delegacia Regional", "Diretoria-Geral"],
        "servicos": [
            "Emissão de CIN",
            "Coleta de digitais",
            "Atendimento social",
            "Orientação jurídica",
            "Fotografia para documento",
        ],
        "equipes": ["Equipe Alfa", "Equipe Bravo", "Equipe Charlie"],
        "motoristas": ["A definir", "Motorista 1", "Motorista 2"],
        "tipos_operacao": ["Ordinária", "Itinerante", "Especial"],
        "decisoes_dg": ["Pendente", "Deferida", "Indeferida"],
    }
    return render(request, "pages/solicitacoes/nova.html", contexto)
