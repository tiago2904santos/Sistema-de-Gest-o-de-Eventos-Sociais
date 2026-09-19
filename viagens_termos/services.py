from __future__ import annotations

from django.utils import timezone
import hashlib
import io
import logging

from django.conf import settings

from viagens_cadastros.models import Servidor
from viagens_cadastros.models import Viatura
from viagens_cadastros.selectors import build_configuracao_context
from core.utils.masks import format_placa
from core.errors import capture
from core.deletion import excluir_com_protecao

from documentos.services.facade import DocumentoFacade
from documentos.services.facade import DocumentoGerado
from documentos.services.document_cache import build_document_cache_key
from documentos.services.document_cache import build_template_cache_signature
from documentos.services.document_cache import documento_gerado_from_artifact
from documentos.services.document_cache import get_cached_document_artifact
from documentos.services.timing import track_document_generation
from documentos.services.pdf_engine import resolve_pdf_engine
from documentos.services.templates import DocumentTemplateDefinition
from documentos.services.templates import DocumentTemplateRegistry
from documentos.services.templates import default_template_registry
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo
from documentos.services.formatters import format_institucional_rodape_linha

from viagens_oficios.documents import VarianteTermo
from viagens_oficios.documents import _document_text
from viagens_oficios.documents import _format_date
from viagens_oficios.documents import _oficio_termo_payload
from viagens_oficios.documents import _resolver_variante_padrao
from viagens_oficios.documents import _transporte_payload
from viagens_oficios.documents import _viagem_payload
from viagens_oficios.documents import build_termo_payload
from viagens_oficios.models import Oficio

from .models import TermoAutorizacao


def excluir_termo(instance: TermoAutorizacao) -> None:
    excluir_com_protecao(instance)

logger = logging.getLogger(__name__)


_TEMPLATE_DOCX_BY_VARIANTE = {
    VarianteTermo.SEMIPREENCHIDO: "termo_autorizacao.docx",
    VarianteTermo.COMPLETO_COM_VIATURA: "termo_autorizacao_automatico.docx",
    VarianteTermo.COMPLETO_SEM_VIATURA: "termo_autorizacao_automatico_sem_viatura.docx",
}


def listar_servidores_com_termo(oficio: Oficio):
    return oficio.servidores_termo_autorizacao.select_related("cargo", "unidade").order_by("nome")


def preview_termo_context(
    oficio: Oficio,
    servidor: Servidor | None = None,
    *,
    modo_semipreenchido: bool = False,
    variante: str | None = None,
) -> dict:
    servidores_termo = listar_servidores_com_termo(oficio)
    srv = servidor or servidores_termo.first()
    if srv is None:
        return {"erro": "Nenhum servidor selecionado para Termo de Autorizacao neste oficio."}
    if not servidores_termo.filter(pk=srv.pk).exists():
        return {"erro": "Servidor nao selecionado para Termo de Autorizacao neste oficio."}
    payload = build_termo_payload(
        oficio,
        srv,
        modo_semipreenchido=modo_semipreenchido,
        variante=variante,
    )
    return {
        "payload": payload,
        "servidor": srv,
        "servidores": list(servidores_termo),
        "variante_efetiva": payload["termo"]["variante"],
    }


def _facade_termo_com_template(template_docx: str) -> DocumentoFacade:
    registry = DocumentTemplateRegistry()
    for definition in default_template_registry.all():
        if definition.tipo == DocumentoTipo.TERMO_AUTORIZACAO and definition.formato == DocumentoFormato.DOCX:
            definition = DocumentTemplateDefinition(
                tipo=definition.tipo,
                formato=definition.formato,
                template_path=template_docx,
                required_placeholders=definition.required_placeholders,
                stylesheet_paths=definition.stylesheet_paths,
            )
        registry.register(definition)
    return DocumentoFacade(template_registry=registry)


def _legacy_docx_context(payload: dict) -> dict:
    institucional = payload.get("institucional") or {}
    termo = payload.get("termo") or {}
    participante = termo.get("participante") or {}
    viagem = termo.get("viagem") or {}
    transporte = termo.get("transporte") or {}

    endereco_partes = [
        institucional.get("logradouro"),
        institucional.get("numero"),
        institucional.get("bairro"),
        institucional.get("cidade_endereco"),
        institucional.get("uf"),
        institucional.get("cep_formatado"),
    ]
    endereco = ", ".join(str(parte).strip() for parte in endereco_partes if str(parte or "").strip())

    return {
        "unidade": institucional.get("unidade") or termo.get("oficio", {}).get("origem") or "",
        "divisao": institucional.get("divisao") or "",
        "endereco": endereco,
        "telefone": participante.get("telefone_formatado") or "",
        "email": institucional.get("email") or "",
        "unidade_rodape": format_institucional_rodape_linha(institucional),
        "data_do_evento": viagem.get("periodo") or viagem.get("saida") or "",
        "destino": viagem.get("destinos_texto") or viagem.get("destino_principal") or "",
        "nome_servidor": participante.get("nome") or "",
        "rg_servidor": participante.get("rg_formatado") or "",
        "cpf_servidor": participante.get("cpf_formatado") or participante.get("cpf") or "",
        "lotacao": participante.get("unidade") or "",
        "viatura": transporte.get("modelo") or "",
        "placa": transporte.get("placa") or "",
        "combustivel": transporte.get("combustivel") or "",
    }


@track_document_generation("termo_gerar_documento")
def _participante_payload(servidor: Servidor | None) -> dict:
    if servidor is None:
        return {
            "id": "",
            "nome": "",
            "cargo": "",
            "rg_formatado": "",
            "cpf": "",
            "cpf_formatado": "",
            "unidade": "",
            "telefone_formatado": "",
            "email": "",
        }
    return {
        "id": servidor.pk,
        "nome": _document_text(servidor.nome),
        "cargo": _document_text(servidor.cargo.nome if servidor.cargo_id else ""),
        "rg_formatado": servidor.rg_formatado,
        "cpf": servidor.cpf or "",
        "cpf_formatado": servidor.cpf_formatado,
        "unidade": _document_text(servidor.unidade.nome if servidor.unidade_id else ""),
        "telefone_formatado": servidor.telefone_formatado,
        "email": "",
    }


def _viatura_payload(viatura: Viatura | None) -> dict:
    if viatura is None:
        return {
            "tem_viatura": False,
            "placa": "-",
            "modelo": "-",
            "tipo": "-",
            "combustivel": "-",
            "motorista": "-",
            "porte_armas": "Sim",
            "unidade": "-",
        }
    return {
        "tem_viatura": True,
        "placa": format_placa(viatura.placa),
        "modelo": _document_text(viatura.modelo),
        "tipo": _document_text(viatura.get_tipo_display() if viatura.tipo else ""),
        "combustivel": _document_text(str(viatura.combustivel) if viatura.combustivel_id else ""),
        "motorista": "-",
        "porte_armas": "Sim",
        "unidade": _document_text(viatura.unidade if viatura.unidade_id else ""),
    }


_MESES = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def _fmt_extenso(d) -> str:
    return f"{d.day} de {_MESES[d.month]} de {d.year}"


def _periodo_texto(termo: TermoAutorizacao) -> str:
    inicio, fim = termo.periodo_efetivo()
    if not inicio:
        return "-"
    if not fim or fim == inicio:
        return f"no dia {_fmt_extenso(inicio)}"
    if inicio.month == fim.month and inicio.year == fim.year:
        return f"nos dias {inicio.day} até {fim.day} de {_MESES[inicio.month]} de {inicio.year}"
    if inicio.year == fim.year:
        return (
            f"nos dias {inicio.day} de {_MESES[inicio.month]} até "
            f"{fim.day} de {_MESES[fim.month]} de {fim.year}"
        )
    return f"nos dias {_fmt_extenso(inicio)} até {_fmt_extenso(fim)}"


def _viagem_payload_termo(termo: TermoAutorizacao) -> dict:
    if termo.oficio_id and not termo.destino_cidade_id and not termo.destino_estado_id and not termo.destinos_extras and not termo.data_evento_inicio:
        payload = _viagem_payload(termo.oficio)
        payload["periodo"] = _periodo_texto(termo)
        return payload

    destino = termo.destino_efetivo() or "-"
    inicio, fim = termo.periodo_efetivo()
    saida = inicio.strftime("%d/%m/%Y") if inicio else "-"
    retorno = fim.strftime("%d/%m/%Y") if fim else saida
    return {
        "destino_principal": destino,
        "destinos_texto": destino,
        "saida": saida,
        "retorno": retorno,
        "periodo": _periodo_texto(termo),
        "roteiro_ida": [destino] if destino != "-" else [],
        "roteiro_ida_texto": destino,
        "roteiro_retorno": [],
        "roteiro_retorno_texto": "-",
        "quantidade_diarias": "-",
        "valor_diarias": "-",
        "valor_diarias_extenso": "-",
        "motivo": "Termo de autorizacao para deslocamento em evento.",
    }


def _oficio_payload_termo(termo: TermoAutorizacao) -> dict:
    if termo.oficio_id:
        return _oficio_termo_payload(termo.oficio)
    return {
        "numero_formatado": f"Termo #{termo.pk or 'novo'}",
        "protocolo_formatado": "-",
        "data_criacao": _format_date(timezone.localtime(termo.criado_em).date() if termo.criado_em else None),
        "assunto": "Termo de autorizacao avulso",
        "origem": build_configuracao_context().get("unidade") or "-",
        "destino": "Direcao/chefia competente",
    }


def _transporte_payload_termo(termo: TermoAutorizacao) -> dict:
    if termo.viatura_id:
        return _viatura_payload(termo.viatura)
    if termo.oficio_id:
        return _transporte_payload(termo.oficio)
    return _viatura_payload(None)


def _resolver_variante_termo_cadastro(
    termo: TermoAutorizacao, servidor: Servidor | None, *, forcar_viatura: bool = False
) -> str:
    if servidor is None:
        # Termo so da viatura: usa o template completo (o unico com placa,
        # viatura e combustivel) com os campos de servidor vazios. Sem esta
        # excecao, servidor=None cai no SEMIPREENCHIDO, que so tem destino e data.
        if forcar_viatura and termo.viatura_efetiva() is not None:
            return VarianteTermo.COMPLETO_COM_VIATURA
        return VarianteTermo.SEMIPREENCHIDO
    if termo.viatura_id:
        return VarianteTermo.COMPLETO_COM_VIATURA
    if termo.oficio_id:
        return _resolver_variante_padrao(termo.oficio)
    return VarianteTermo.COMPLETO_SEM_VIATURA


def build_termo_cadastro_payload(
    termo: TermoAutorizacao,
    servidor: Servidor | None = None,
    *,
    forcar_viatura: bool = False,
) -> dict:
    institucional = build_configuracao_context()
    payload = {
        "institucional": institucional,
        "oficio": _oficio_payload_termo(termo),
    }
    variante = _resolver_variante_termo_cadastro(termo, servidor, forcar_viatura=forcar_viatura)
    payload["termo"] = {
        "variante": variante,
        "participante": _participante_payload(servidor),
        "viagem": _viagem_payload_termo(termo),
        "transporte": _transporte_payload_termo(termo),
        "oficio": _oficio_payload_termo(termo),
        "textos": {
            "titulo": "TERMO DE AUTORIZACAO",
            "corpo_autorizacao": (
                "Autorizo o servidor acima identificado a realizar o deslocamento descrito neste "
                "termo, observadas as normas administrativas aplicaveis ao servico publico e ao "
                "uso do transporte informado."
            ),
            "declaracao": (
                "O servidor declara ciencia das informacoes registradas, do periodo autorizado "
                "e das responsabilidades funcionais decorrentes da viagem."
            ),
            "observacoes": "-",
        },
    }
    return payload


def servidores_para_termo_cadastro(termo: TermoAutorizacao) -> list[Servidor | None]:
    servidores = list(termo.servidores_efetivos())
    return servidores or [None]



def _conteudo_documental(dono):
    """Os textos do modelo reescritos no editor (o termo do cadastro, ou o
    ofício, para o termo tirado dele): entram no PDF e na chave do cache."""
    from documentos.services.document_blocks import conteudo_documental

    return conteudo_documental(DocumentoTipo.TERMO_AUTORIZACAO, dono)


def _gerar(payload, formato, ref, *, oficio_id=None, termo_id=None, servidor_id=None, roteiro_id=None, usar_assinado=True):
    template = _TEMPLATE_DOCX_BY_VARIANTE[payload["termo"]["variante"]]
    return DocumentoFacade().gerar(
        tipo=DocumentoTipo.TERMO_AUTORIZACAO, formato=formato, payload=payload,
        reference=ref, docxtpl_context=_legacy_docx_context(payload),
        docx_template_path=template, oficio_id=oficio_id, termo_id=termo_id,
        servidor_id=servidor_id, roteiro_id=roteiro_id, usar_assinado=usar_assinado,
    )


def gerar_termo_um(oficio, servidor, formato, *, modo_semipreenchido=False, variante=None, usar_assinado=True):
    if not listar_servidores_com_termo(oficio).filter(pk=servidor.pk).exists():
        raise ValueError("Servidor não selecionado para termo neste ofício.")
    payload = build_termo_payload(oficio, servidor, modo_semipreenchido=modo_semipreenchido, variante=variante)
    payload["documento"] = _conteudo_documental(oficio)
    return _gerar(payload, formato, f"{oficio.numero_formatado.replace('/', '-')}-termo-{servidor.pk}",
        oficio_id=oficio.pk, servidor_id=servidor.pk, roteiro_id=oficio.roteiro_id, usar_assinado=usar_assinado)


def gerar_termo_lote(oficio, formato):
    return [gerar_termo_um(oficio, s, formato) for s in listar_servidores_com_termo(oficio)]


def gerar_termo_cadastro_um(termo, servidor, formato, *, forcar_viatura=False, usar_assinado=True):
    """`usar_assinado=False` pede o arquivo original mesmo com versão assinada anexada."""
    if servidor is not None and not termo.servidores_efetivos().filter(pk=servidor.pk).exists():
        raise ValueError("Servidor não pertence a este termo.")
    payload = build_termo_cadastro_payload(termo, servidor, forcar_viatura=forcar_viatura)
    payload["documento"] = _conteudo_documental(termo)
    ref_servidor = servidor.pk if servidor else "viatura" if forcar_viatura else "sem-servidor"
    return _gerar(payload, formato, f"termo-{termo.pk}-cadastro-{ref_servidor}",
        oficio_id=termo.oficio_id, termo_id=termo.pk, servidor_id=servidor.pk if servidor else None,
        roteiro_id=termo.oficio.roteiro_id if termo.oficio_id else None, usar_assinado=usar_assinado)


def gerar_termo_cadastro_lote(termo, formato):
    return [gerar_termo_cadastro_um(termo, s, formato) for s in servidores_para_termo_cadastro(termo)]
