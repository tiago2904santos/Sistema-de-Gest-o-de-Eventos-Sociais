"""Como a ordem de serviço se apresenta na lista e no painel da viagem.

Do `ordens_servico/presenters.py` da origem vêm o selo temporal ("faltam 3
dias", "em andamento", "há 2 dias"), os servidores com o motorista marcado,
os destinos resumidos, os ofícios vinculados, o assinante e o motivo cortado
em 240 caracteres. A composição é a da lista de termos: título com selos e
fatos separados, cada um com o seu ícone.
"""

from django.urls import reverse
from django.utils import timezone

from core.utils.masks import format_protocolo
from documentos.services.types import DocumentoTipo
from viagens_oficios.presenters import iniciais

TAMANHO_DO_MOTIVO_RESUMIDO = 240


def assinante_da_ordem():
    """Nome e cargo de quem assina a OS — um por página, não um por linha."""
    from viagens_cadastros.models import AssinaturaConfiguracao, ConfiguracaoSistema

    ass = (
        ConfiguracaoSistema.get_singleton().assinaturas
        .filter(tipo=AssinaturaConfiguracao.ORDEM_SERVICO, ativo=True)
        .select_related("servidor__cargo").order_by("ordem").first()
    )
    if ass is None or ass.servidor is None:
        return None
    return {"nome": ass.servidor.nome, "cargo": ass.servidor.cargo.nome if ass.servidor.cargo_id else ""}


def selo_temporal(ordem):
    """Quanto falta ou quanto passou, como a origem dizia; sem data não há selo."""
    inicio = ordem.data_evento_inicio
    if not inicio:
        return "", "neutro"
    fim = ordem.data_evento_fim or inicio
    hoje = timezone.localdate()
    if hoje < inicio:
        dias = (inicio - hoje).days
        return ("falta 1 dia" if dias == 1 else f"faltam {dias} dias"), "aguardando"
    if inicio <= hoje <= fim:
        return ("começa hoje" if hoje == inicio else "em andamento"), "em_andamento"
    dias = (hoje - fim).days
    if dias == 0:
        return "foi hoje", "atendido"
    if dias == 1:
        return "foi ontem", "atendido"
    return f"há {dias} dias", "atendido"


def periodo_curto(ordem):
    inicio, fim = ordem.data_evento_inicio, ordem.data_evento_fim
    if not inicio:
        return ""
    if not fim or fim == inicio:
        return inicio.strftime("%d/%m")
    if inicio.year == fim.year:
        return f"{inicio:%d/%m} a {fim:%d/%m}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def destinos_resumidos(ordem):
    """Até três destinos, "Nome (UF)", e o que sobrar vira "+N". Usa o prefetch do selector."""
    destinos = list(ordem.destinos.all())
    if not destinos:
        return ""
    texto = ", ".join(f"{d.nome} ({d.estado.sigla})" for d in destinos[:3])
    if len(destinos) > 3:
        texto += f" +{len(destinos) - 3}"
    return texto


def servidores_da_ordem(ordem):
    """A equipe, marcando quem é motorista em algum dos ofícios vinculados."""
    motoristas = {o.motorista_id for o in ordem.oficios.all() if o.motorista_id}
    equipe = []
    for s in ordem.servidores.all():
        cargo = s.cargo.nome if s.cargo_id else ""
        unidade = (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""
        equipe.append({
            "pk": s.pk, "nome": s.nome, "iniciais": iniciais(s.nome), "cargo": cargo, "unidade": unidade,
            "detalhes": " · ".join(p for p in [cargo, unidade] if p), "is_motorista": s.pk in motoristas,
        })
    return equipe


def oficios_vinculados(ordem):
    return [
        {"pk": o.pk, "numero": o.numero_formatado, "protocolo": format_protocolo(o.protocolo) or "",
         "url": reverse("viagens_oficios:editar", args=[o.pk]), "cancelado": o.cancelado}
        for o in ordem.oficios.all()
    ]


def motivo_resumido(ordem):
    motivo = (ordem.motivo or "").strip()
    if len(motivo) > TAMANHO_DO_MOTIVO_RESUMIDO:
        return motivo[:TAMANHO_DO_MOTIVO_RESUMIDO] + "…"
    return motivo


def titulo_da_ordem(ordem):
    # O vazio é nomeado também no título, que agora é o único lugar do período e do destino.
    return " · ".join([ordem.numero_formatado, destinos_resumidos(ordem) or "Sem destino", periodo_curto(ordem) or "Sem período"])


def fatos_da_ordem(ordem, equipe, oficios, assinante):
    """A segunda linha da lista, item a item com ícone; o vazio é nomeado, não omitido.

    Período e destinos já estão no título: aqui ficam equipe, ofícios, o
    assinante (quando há) e o motivo, que corta com reticências na tela.
    """
    nomes = ", ".join(f"{s['nome']} (motorista)" if s["is_motorista"] else s["nome"] for s in equipe)
    motivo = motivo_resumido(ordem)
    fatos = [
        {"icone": "users", "rotulo": "Servidores", "texto": nomes or "Nenhum servidor informado", "ausente": not nomes},
        {"icone": "document", "rotulo": "Ofícios", "texto": "", "oficios": oficios, "ausente": not oficios},
    ]
    if assinante:
        texto = assinante["nome"] + (f" · {assinante['cargo']}" if assinante["cargo"] else "")
        fatos.append({"icone": "pencil", "rotulo": "Assinante", "texto": texto, "ausente": False})
    fatos.append({"icone": "clipboard", "rotulo": "Motivo", "texto": motivo or "Nenhum motivo informado", "ausente": not motivo, "motivo": True})
    return fatos


def artefatos_pdf_por_ordem(ordens):
    """ordem_id → PDF de OS já gerado (`{"pk", "assinado"}`), o alvo de "Anexar assinado".

    O PDF apontado é o mais recente; `assinado` olha o banco, não o storage —
    uma ida ao disco por linha pesaria na lista paginada.
    """
    from django.db.models import Exists, OuterRef

    from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao

    ids = [o.pk for o in ordens]
    if not ids:
        return {}
    versao_viva = DocumentoAssinaturaVersao.objects.filter(artefato=OuterRef("pk"), revogada_em__isnull=True)
    consulta = (
        DocumentoArtefato.objects
        .filter(ordem_servico_id__in=ids, formato="pdf", tipo=DocumentoTipo.ORDEM_SERVICO.value)
        .annotate(tem_versao=Exists(versao_viva))
        .order_by("criado_em")
        .values_list("ordem_servico_id", "pk", "tem_versao", "arquivo_assinado")
    )
    mapa = {}
    for ordem_id, pk, tem_versao, arquivo_assinado in consulta:
        assinado = bool(tem_versao) or bool(arquivo_assinado)
        # O mais recente é o alvo; se qualquer um já voltou assinado, a OS está assinada.
        anterior = mapa.get(ordem_id)
        mapa[ordem_id] = {"pk": pk, "assinado": assinado or bool(anterior and anterior["assinado"])}
    return mapa


def urls_da_ordem(ordem):
    return {
        "url_editar": reverse("viagens_ordens:editar", args=[ordem.pk]),
        "url_pdf": reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"]),
        "url_docx": reverse("viagens_ordens:gerar", args=[ordem.pk, "docx"]),
        "url_visualizar": reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"]) + "?inline=1",
        "url_excluir": reverse("viagens_ordens:acao", args=[ordem.pk, "excluir"]),
        "url_cancelar": reverse("viagens_ordens:acao", args=[ordem.pk, "cancelar"]),
        "url_reativar": reverse("viagens_ordens:acao", args=[ordem.pk, "reativar"]),
    }


def linha_da_lista(ordem, *, assinante=None, artefato_pdf=None):
    selo, tom = selo_temporal(ordem)
    equipe = servidores_da_ordem(ordem)
    oficios = oficios_vinculados(ordem)
    return {
        "ordem": ordem,
        "cancelada": ordem.cancelado,
        "titulo": titulo_da_ordem(ordem),
        "selo": selo, "selo_tom": tom,
        "fatos": fatos_da_ordem(ordem, equipe, oficios, assinante),
        "motivo_resumido": motivo_resumido(ordem),
        "servidores": equipe,
        "oficios": oficios,
        "url_assinado": reverse("viagens_ordens:assinatura_artefato", args=[artefato_pdf["pk"]]) if artefato_pdf else "",
        "assinado": bool(artefato_pdf and artefato_pdf["assinado"]),
        **urls_da_ordem(ordem),
    }
