"""Campos automáticos dos modelos de motivo e de justificativa.

O modelo pode trazer marcadores como `{destino}` ou `{periodo}`; ao aplicar o
modelo, a tela troca cada um pelo valor do ofício (ou da ordem de serviço).
Marcador sem valor ainda — ofício sem roteiro, por exemplo — fica como está,
à vista, e é preenchido na gravação, quando o roteiro e a equipe já existem.
Marcador desconhecido também fica: o texto nunca perde nada.

A troca é por expressão regular, não por `str.format_map`: uma chave solta
no texto (ex.: "{") não pode derrubar a tela.
"""

import re

from django.utils import timezone

MARCADOR = re.compile(r"\{(\w+)\}")

#: Os campos que os modelos aceitam, na ordem em que a tela de cadastro os lista.
CAMPOS = (
    ("destino", "destinos da viagem"),
    ("periodo", "período da viagem"),
    ("data_saida", "data da primeira saída"),
    ("data_retorno", "data do retorno"),
    ("dias_antecedencia", "dias entre a data do ofício e a saída"),
    ("prazo", "prazo mínimo de antecedência"),
    ("evento", "nome da viagem"),
    ("servidores", "nomes da equipe"),
    ("data_oficio", "data do ofício"),
    ("numero_oficio", "número do ofício"),
)

AJUDA_CAMPOS = (
    "Campos automáticos, preenchidos ao aplicar o modelo: "
    + ", ".join(f"{{{chave}}} ({rotulo})" for chave, rotulo in CAMPOS)
    + "."
)


def aplicar(texto, valores):
    """Troca os marcadores que têm valor; os demais ficam no texto."""
    if not texto or "{" not in texto:
        return texto

    def trocar(encontrado):
        valor = valores.get(encontrado.group(1))
        return str(valor) if valor not in (None, "") else encontrado.group(0)

    return MARCADOR.sub(trocar, texto)


def _data(valor):
    if valor is None:
        return None
    if hasattr(valor, "astimezone") and hasattr(valor, "hour"):
        valor = timezone.localtime(valor).date()
    return valor


def _periodo(inicio, fim):
    inicio, fim = _data(inicio), _data(fim)
    if not inicio:
        return ""
    if not fim or fim == inicio:
        return f"{inicio:%d/%m/%Y}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def _nomes(pessoas):
    nomes = [p.nome for p in pessoas]
    if len(nomes) < 2:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def valores_do_oficio(oficio):
    """Os valores dos campos automáticos para este ofício, no estado gravado."""
    from .justificativas_services import calcular_dias_antecedencia_justificativa, get_prazo_justificativa_dias
    from .presenters import destinos_resumidos
    from .roteiro_context import periodo_roteiro

    roteiro = oficio.roteiro if oficio.roteiro_id else None
    saida, retorno = periodo_roteiro(roteiro)
    dias = calcular_dias_antecedencia_justificativa(oficio) if roteiro else None
    viagem = oficio.viagem if oficio.viagem_id else None
    return {
        "destino": destinos_resumidos(roteiro, maximo=100) if roteiro else "",
        "periodo": _periodo(saida, retorno),
        "data_saida": f"{_data(saida):%d/%m/%Y}" if saida else "",
        "data_retorno": f"{_data(retorno):%d/%m/%Y}" if retorno else "",
        "dias_antecedencia": "" if dias is None else dias,
        "prazo": get_prazo_justificativa_dias(),
        "evento": (viagem.titulo or "") if viagem else "",
        "servidores": _nomes(oficio.servidores.order_by("nome")) if oficio.pk else "",
        "data_oficio": f"{oficio.data_criacao:%d/%m/%Y}" if oficio.data_criacao else "",
        "numero_oficio": oficio.numero_formatado if oficio.numero else "",
    }


def valores_da_ordem(ordem):
    """Os campos automáticos na ordem de serviço: o que ela tem de próprio."""
    from viagens_roteiros.presenters import rotulo_cidade

    destinos = list(ordem.destinos.select_related("estado").order_by("nome")) if ordem.pk else []
    viagem = ordem.viagem if ordem.viagem_id else None
    return {
        "destino": ", ".join(rotulo_cidade(m).upper() for m in destinos),
        "periodo": _periodo(ordem.data_evento_inicio, ordem.data_evento_fim),
        "data_saida": f"{ordem.data_evento_inicio:%d/%m/%Y}" if ordem.data_evento_inicio else "",
        "data_retorno": f"{ordem.data_evento_fim:%d/%m/%Y}" if ordem.data_evento_fim else "",
        "evento": (viagem.titulo or "") if viagem else "",
        "servidores": _nomes(ordem.servidores.order_by("nome")) if ordem.pk else "",
    }


def preencher_marcadores_do_oficio(oficio):
    """Na gravação: o que ficou marcado no motivo e na justificativa vira valor."""
    from .models import Justificativa

    valores = None
    if "{" in (oficio.motivo or ""):
        valores = valores_do_oficio(oficio)
        novo = aplicar(oficio.motivo, valores)
        if novo != oficio.motivo:
            oficio.motivo = novo
            oficio.save(update_fields=["motivo", "atualizado_em"])
    justificativa = Justificativa.objects.filter(oficio=oficio).first()
    if justificativa and "{" in (justificativa.texto or ""):
        valores = valores or valores_do_oficio(oficio)
        novo = aplicar(justificativa.texto, valores)
        if novo != justificativa.texto:
            justificativa.texto = novo
            justificativa.save(update_fields=["texto", "atualizado_em"])
