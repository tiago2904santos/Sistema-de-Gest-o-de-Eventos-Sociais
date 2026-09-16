"""Histórico de alterações de um registro, pronto para a tela.

Lê a trilha (`RegistroAuditoria`) de um objeto e dos filhos dele (destinos e
trechos de um roteiro, por exemplo) e devolve, do mais recente ao mais
antigo, quem mudou, quando, por onde e o quê — campo a campo, com rótulos e
valores legíveis (escolhas pelo nome, chaves estrangeiras pelo registro,
datas no formato do Brasil).

Filhos são achados pelo id atual e, para os já excluídos ou recém-criados,
pela chave para o pai gravada no próprio registro (`novo`/`antigo`).
Atualizações que só mexem em carimbos (`atualizado_em`) ficam de fora: a
gravação automática as produz aos montes e elas não dizem nada.
"""

from __future__ import annotations

from datetime import date, datetime

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone

CAMPOS_IGNORADOS = {"atualizado_em", "criado_em", "legado_origem", "legado_pk", "id"}
TAMANHO_MAXIMO = 160


def _modelo(label):
    try:
        return apps.get_model(label)
    except (LookupError, ValueError):
        return None


def _campo(modelo, nome):
    if modelo is None:
        return None
    try:
        return modelo._meta.get_field(nome)
    except FieldDoesNotExist:
        return None


def _rotulo(campo, nome):
    texto = str(getattr(campo, "verbose_name", "") or nome.replace("_", " "))
    return texto[:1].upper() + texto[1:]


def _texto_curto(valor):
    texto = str(valor)
    return texto if len(texto) <= TAMANHO_MAXIMO else texto[: TAMANHO_MAXIMO - 1] + "…"


def _data_hora(valor):
    if isinstance(valor, str):
        convertido = parse_datetime(valor)
        if convertido is None:
            dia = parse_date(valor)
            return dia.strftime("%d/%m/%Y") if dia else None
        valor = convertido
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return None


def _legivel(campo, valor):
    if valor is None or valor == "":
        return "—"
    if campo is None:
        return _texto_curto(valor)
    if getattr(campo, "choices", None):
        return str(dict(campo.flatchoices).get(valor, valor))
    if getattr(campo, "is_relation", False) and getattr(campo, "related_model", None):
        relacionado = campo.related_model._base_manager.filter(pk=valor).first()
        return _texto_curto(relacionado) if relacionado is not None else f"#{valor} (excluído)"
    tipo = campo.get_internal_type()
    if tipo == "BooleanField":
        return "Sim" if valor in (True, "True", "true", 1) else "Não"
    if tipo in ("DateTimeField", "DateField"):
        return _data_hora(valor) or _texto_curto(valor)
    if tipo == "DecimalField":
        return str(valor).replace(".", ",")
    return _texto_curto(valor)


def _mudancas(registro, modelo):
    """Campo a campo, só nas atualizações."""
    linhas = []
    for nome, delta in (registro.alteracoes or {}).items():
        if nome in CAMPOS_IGNORADOS or not isinstance(delta, dict):
            continue
        campo = _campo(modelo, nome)
        if "operacao" in delta:  # muitos-para-muitos
            relacionado = getattr(campo, "related_model", None)
            nomes = []
            for pk in delta.get("ids") or []:
                obj = relacionado._base_manager.filter(pk=pk).first() if relacionado else None
                nomes.append(str(obj) if obj is not None else f"#{pk}")
            linhas.append({"campo": _rotulo(campo, nome), "antes": "", "depois": f"{delta['operacao'].capitalize()}: {', '.join(nomes) or '—'}"})
            continue
        if "antes" not in delta and "depois" not in delta:
            continue
        antes, depois = _legivel(campo, delta.get("antes")), _legivel(campo, delta.get("depois"))
        # A trilha compara texto: a mesma data com outro fuso aparece como
        # mudança. Na tela, igual antes e depois não é alteração.
        if antes == depois:
            continue
        linhas.append({"campo": _rotulo(campo, nome), "antes": antes, "depois": depois})
    return linhas


def historico_de(objeto, filhos=(), sobre_filhos=None):
    """Todas as alterações de `objeto` e dos `filhos`, do mais recente ao mais antigo.

    `filhos`: pares (label do model, nome da chave para o pai), p.ex.
    `("viagens_roteiros.roteirotrecho", "roteiro")`. `sobre_filhos`: rótulo
    de cada label ("Trecho"), para a coluna "O quê".
    """
    from .models import RegistroAuditoria

    if objeto is None or not getattr(objeto, "pk", None):
        return []
    label = objeto._meta.label_lower
    filtro = Q(modelo=label, objeto_id=str(objeto.pk))
    for label_filho, fk in filhos:
        modelo_filho = _modelo(label_filho)
        atuais = []
        if modelo_filho is not None:
            atuais = [str(pk) for pk in modelo_filho._base_manager.filter(**{fk: objeto.pk}).values_list("pk", flat=True)]
        filtro |= Q(modelo=label_filho) & (
            Q(objeto_id__in=atuais)
            | Q(**{f"alteracoes__novo__{fk}": objeto.pk})
            | Q(**{f"alteracoes__antigo__{fk}": objeto.pk})
        )
    rotulos = dict(sobre_filhos or {})
    rotulos.setdefault(label, _rotulo(None, objeto._meta.verbose_name))

    itens = []
    registros = RegistroAuditoria.objects.filter(filtro).select_related("usuario").order_by("-criado_em", "-pk")
    for registro in registros:
        modelo = _modelo(registro.modelo)
        acao = registro.acao
        mudancas = _mudancas(registro, modelo) if acao == RegistroAuditoria.Acao.ATUALIZACAO else []
        if acao == RegistroAuditoria.Acao.ATUALIZACAO and not mudancas:
            continue
        tipo = rotulos.get(registro.modelo, registro.modelo)
        sobre = tipo if registro.modelo == label else f"{tipo} {registro.objeto_repr}".strip()
        itens.append({
            "quando": registro.criado_em,
            "usuario": registro.usuario,
            "origem": registro.get_origem_display(),
            "acao": registro.get_acao_display(),
            "acao_codigo": acao,
            "sobre": sobre,
            "mudancas": mudancas,
        })
    return itens
