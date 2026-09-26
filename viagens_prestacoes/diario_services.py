"""Geração do diário de bordo do veículo a partir do roteiro do ofício.

Cabeçalho (motorista, viatura, ofício, e-protocolo) vem do ofício; as linhas
vêm dos trechos do roteiro. KM inicial/final e necessidade de abastecimento são
complementados pelo usuário e persistidos em ``DiarioBordoTrecho``.
"""

from __future__ import annotations

import re

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from viagens_cadastros.selectors import build_configuracao_context
from core.normalizers import normalize_spaces
from core.errors import capture
from core.utils.masks import format_cpf
from core.utils.masks import format_placa
from core.utils.masks import format_protocolo
from documentos.services.adapters.xlsx_render import fill_diario_bordo_xlsx
from documentos.services.formatters import format_document_display
from documentos.services.exceptions import DocumentValidationError
from documentos.services.libreoffice_resolve import resolve_libreoffice_binary
from documentos.services.pdf_engine import build_pdf_unavailable_message
from documentos.services.pdf_engine import resolve_pdf_engine
from documentos.services.timing import track_document_generation
from viagens_cadastros.models import Viatura
from viagens_oficios.models import Oficio
from viagens_roteiros.models import RoteiroTrecho

from .models import DiarioBordo
from .models import DiarioBordoTrecho


def roteiro_efetivo(prestacao):
    """Roteiro usado pelo diário: a cópia ajustada, se existir; senão o do ofício."""
    return prestacao.roteiro_ajustado or getattr(prestacao.oficio, "roteiro", None)


def _copiar_campos_concretos(origem, destino, excluir: set) -> None:
    # Um ajuste feito aqui é um novo registro nativo, não a mesma linha do GV.
    excluir = excluir | {"legado_origem", "legado_pk"}
    for campo in origem._meta.concrete_fields:
        if campo.primary_key or campo.name in excluir:
            continue
        setattr(destino, campo.attname, getattr(origem, campo.attname))


@transaction.atomic
def clonar_roteiro(origem):
    """Cria uma cópia independente do roteiro (cabeçalho + destinos + trechos)."""
    from viagens_roteiros.models import Roteiro
    from viagens_roteiros.models import RoteiroDestino

    novo = Roteiro()
    _copiar_campos_concretos(origem, novo, excluir={"solicitacao"})
    novo.pk = None
    novo.solicitacao = None
    novo.tipo = Roteiro.Tipo.AVULSO
    novo.save()

    for destino in origem.destinos.all():
        nd = RoteiroDestino()
        _copiar_campos_concretos(destino, nd, excluir={"roteiro"})
        nd.pk = None
        nd.roteiro = novo
        nd.save()

    for trecho in origem.trechos.all():
        nt = RoteiroTrecho()
        _copiar_campos_concretos(trecho, nt, excluir={"roteiro"})
        nt.pk = None
        nt.roteiro = novo
        nt.save()

    from viagens_roteiros.models import RoteiroDiariaComponente
    for componente in origem.componentes_diarias.all():
        nc = RoteiroDiariaComponente()
        _copiar_campos_concretos(componente, nc, excluir={"roteiro"})
        nc.roteiro = novo
        nc.save()
    return novo


CAMPOS_COMPARACAO_ROTEIRO = ["origem_municipio_id", "saida_dt", "chegada_dt", "retorno_saida_dt", "retorno_chegada_dt", "resumo_diarias", "valor_diarias", "quantidade_servidores", "observacoes", "rota_distancia_km", "rota_duracao_min"]
CAMPOS_COMPARACAO_TRECHO = ["sentido", "ordem", "origem_municipio_id", "destino_municipio_id", "saida_dt", "chegada_dt", "distancia_km", "duracao_min", "tempo_viagem_min", "tempo_adicional_min"]


def snapshot_comparavel_roteiro(roteiro):
    """Dict com os campos relevantes do roteiro (+ destinos/trechos), para comparar
    uma cópia (`roteiro_ajustado`) com o original sem considerar pk/timestamps."""
    dados = {campo: getattr(roteiro, campo) for campo in CAMPOS_COMPARACAO_ROTEIRO}
    dados["destinos"] = [
        (d.municipio_id, d.ordem) for d in roteiro.destinos.all().order_by("ordem", "id")
    ]
    dados["trechos"] = [
        tuple(getattr(t, campo) for campo in CAMPOS_COMPARACAO_TRECHO)
        for t in roteiro.trechos.all().order_by("ordem", "id")
    ]
    return dados


def diferencas_entre_roteiros(original, copia):
    """Lista as chaves (campo/destinos/trechos) que diferem entre dois roteiros.
    Lista vazia = cópia idêntica ao original (nunca foi de fato ajustada)."""
    a = snapshot_comparavel_roteiro(original)
    b = snapshot_comparavel_roteiro(copia)
    return [chave for chave in a if a[chave] != b[chave]]


@transaction.atomic
def garantir_roteiro_ajustado(prestacao):
    """Garante a cópia editável do roteiro na prestação (clona do ofício na 1ª vez)."""
    bloqueada = type(prestacao).objects.select_for_update().get(pk=prestacao.pk)
    if bloqueada.roteiro_ajustado_id:
        prestacao.roteiro_ajustado = bloqueada.roteiro_ajustado
        return prestacao.roteiro_ajustado
    origem = getattr(prestacao.oficio, "roteiro", None)
    if origem is None:
        return None
    copia = clonar_roteiro(origem)
    prestacao.roteiro_ajustado = copia
    prestacao.save(update_fields=["roteiro_ajustado", "atualizado_em"])
    return copia


def diaria_info(prestacao) -> dict:
    """Compara a diária do roteiro ajustado com a do ofício para sinalizar alteração."""
    copia = prestacao.roteiro_ajustado
    if copia is None:
        return {"alterada": False, "ajustado": False}
    original = getattr(prestacao.oficio, "roteiro", None)

    def valor(r):
        return getattr(r, "valor_diarias", None) if r else None

    def qtd(r):
        return (getattr(r, "resumo_diarias", "") or "").strip() if r else ""

    def moeda(v):
        if v is None:
            return "—"
        try:
            from documentos.services.formatters import format_currency_br

            return format_currency_br(v)
        except (AttributeError, TypeError, ValueError):
            return str(v)

    alterada = (valor(original) != valor(copia)) or (qtd(original) != qtd(copia))
    return {
        "alterada": alterada,
        "ajustado": True,
        "valor_oficio": valor(original),
        "valor_ajustado": valor(copia),
        "valor_oficio_label": moeda(valor(original)),
        "valor_ajustado_label": moeda(valor(copia)),
        "qtd_oficio": qtd(original) or "—",
        "qtd_ajustado": qtd(copia) or "—",
    }


def _upper(value: object) -> str:
    return str(value or "").strip().upper()


def _local(dt):
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return timezone.localtime(dt)
    return dt


def _cidade_label(cidade, estado) -> str:
    if cidade is not None:
        return _upper(getattr(cidade, "nome", cidade))
    if estado is not None:
        return _upper(getattr(estado, "sigla", estado))
    return ""


def trechos_ordenados(roteiro) -> list[RoteiroTrecho]:
    """Trechos do roteiro na ordem do documento: IDA (por ordem) e depois RETORNO."""
    if roteiro is None:
        return []
    qs = list(
        roteiro.trechos.select_related(
            "origem_municipio",
            "origem_municipio__estado",
            "destino_municipio",
            "destino_municipio__estado",
        ),
    )

    def chave(t):
        return (0 if t.sentido == RoteiroTrecho.Sentido.IDA else 1, t.ordem, t.pk)

    return sorted(qs, key=chave)


def _fmt_dt_legivel(dt) -> str | None:
    local = _local(dt)
    if local is None:
        return None
    return local.strftime("%d/%m/%Y às %H:%M")


def alteracoes_datas_horarios_roteiro(prestacao) -> list[str]:
    """Frases descrevendo as mudanças de saída/chegada entre os trechos do roteiro do
    ofício e o roteiro ajustado desta prestação. Pareia pela posição dentro de cada
    tipo (IDA/RETORNO) — o número de ``ordem`` não é confiável entre as duas cópias
    (a copia editável pode ser reindexada a partir de 0)."""
    copia = prestacao.roteiro_ajustado
    original = getattr(prestacao.oficio, "roteiro", None)
    if copia is None or original is None:
        return []

    def agrupar_por_tipo(roteiro):
        grupos: dict[str, list] = {}
        for t in trechos_ordenados(roteiro):
            grupos.setdefault(t.sentido, []).append(t)
        return grupos

    originais_por_tipo = agrupar_por_tipo(original)
    itens = []
    for tipo, trechos_novos in agrupar_por_tipo(copia).items():
        trechos_velhos = originais_por_tipo.get(tipo, [])
        for t_novo, t_velho in zip(trechos_novos, trechos_velhos, strict=False):
            rota = (
                f"{format_document_display(_cidade_label(t_novo.origem_municipio, getattr(t_novo.origem_municipio, "estado", None)))}"
                f" → {format_document_display(_cidade_label(t_novo.destino_municipio, getattr(t_novo.destino_municipio, "estado", None)))}"
            )
            de_saida = _fmt_dt_legivel(t_velho.saida_dt) or "não informada"
            para_saida = _fmt_dt_legivel(t_novo.saida_dt) or "não informada"
            if de_saida != para_saida:
                itens.append(f"saída ({rota}) de {de_saida} para {para_saida}")

            de_chegada = _fmt_dt_legivel(t_velho.chegada_dt) or "não informada"
            para_chegada = _fmt_dt_legivel(t_novo.chegada_dt) or "não informada"
            if de_chegada != para_chegada:
                itens.append(f"chegada ({rota}) de {de_chegada} para {para_chegada}")
    return itens


#: `DB-08` fatia 2: bloco livre para onde as posições vão no primeiro passo.
#: Fica acima de qualquer posição final — e as finais são `0..len(trechos)`, uma
#: por trecho do roteiro. Cabe com folga no `PositiveIntegerField`.
DESLOCAMENTO_ORDEM_TRECHO = 1_000_000


@transaction.atomic
def sincronizar_trechos(diario: DiarioBordo) -> list[DiarioBordoTrecho]:
    """Garante uma linha de diário por trecho do roteiro, preservando o que já foi digitado.

    `DB-08` fatia 2: atômica. Nenhum dos chamadores abre transação — nem as três
    views de `diario_views.py`, nem `services.py:574` — e sem ela uma falha no meio
    deixa as posições estacionadas no bloco de deslocamento, à vista do usuário.
    """
    roteiro = roteiro_efetivo(diario.prestacao)
    trechos = trechos_ordenados(roteiro)

    # `DB-08` fatia 2, **primeiro passo**. As posições finais entram uma a uma no
    # laço abaixo, e a linha é reaproveitada por `id`: quando o roteiro muda de
    # ordem, a posição que estou gravando ainda pertence a outra linha. Este
    # `UPDATE` único tira todas do caminho; o laço as traz de volta já no lugar, e
    # o `delete()` do fim leva as que sobraram. `deferrable=DEFERRED` não serve —
    # o SQLite não o suporta e a suíte roda nos dois bancos.
    #
    # **Antes da leitura, não depois.** Lendo primeiro, os objetos em memória
    # ficariam com a posição antiga enquanto o banco já teria a deslocada, e o
    # `save()` do laço — que grava todos os campos — devolveria o valor velho por
    # acidente. Funciona enquanto o laço atribuir `ordem` explicitamente, e é
    # exatamente o tipo de acerto silencioso que some quando alguém mexe no laço.
    # Medido: com a leitura antes, o teste do bloco passa mesmo com o laço não
    # devolvendo linha nenhuma.
    diario.trechos.update(ordem=F("ordem") + DESLOCAMENTO_ORDEM_TRECHO)

    existentes = list(diario.trechos.all().order_by("ordem", "pk"))
    por_trecho = {dt.trecho_id: dt for dt in existentes}
    ids_atuais = {t.id for t in trechos}
    # Linhas cujo trecho deixou de existir (ex.: roteiro foi clonado/recriado):
    # ficam disponíveis para reaproveitar, preservando KM/abastecimento por ordem.
    # A ordem relativa sobrevive ao deslocamento: ele soma o mesmo em todas.
    sobrando = [dt for dt in existentes if dt.trecho_id not in ids_atuais]

    usados = []
    for i, trecho in enumerate(trechos):
        linha = por_trecho.get(trecho.id)
        if linha is None and sobrando:
            linha = sobrando.pop(0)
        if linha is None:
            # Padrão: necessidade de abastecimento = Sim.
            linha = DiarioBordoTrecho(diario=diario, abastecimento=True)
        linha.trecho = trecho
        linha.ordem = i
        linha.save()
        usados.append(linha.pk)

    diario.trechos.exclude(pk__in=usados).delete()
    return list(diario.trechos.select_related("trecho").all())


def _motorista_nome_cpf(oficio: Oficio) -> tuple[str, str]:
    if oficio.motorista_id:
        servidor = oficio.motorista
        return servidor.nome, (servidor.cpf_formatado or "")
    if oficio.motorista_modo == Oficio.MOTORISTA_MODO_MANUAL:
        return (
            (oficio.motorista_manual_nome or "").strip(),
            (oficio.motorista_manual_cpf or "").strip(),
        )
    return "", ""


def motorista_do_oficio(oficio: Oficio) -> tuple[str, str]:
    """(nome, cpf) do motorista definido no ofício (referência para a Etapa 3)."""
    return _motorista_nome_cpf(oficio)


def _split_oficio_ref(ref: object) -> tuple[str, str]:
    """Divide 'número/ano' em (número, ano); sem '/', devolve (ref, '')."""
    raw = str(ref or "").strip()
    if "/" in raw:
        numero, ano = raw.split("/", 1)
        return numero.strip(), ano.strip()
    return raw, ""


def motorista_diario(diario: DiarioBordo) -> tuple[str, str]:
    """(nome, cpf) do motorista do diário considerando o override; senão vem do ofício."""
    modo = diario.motorista_modo
    if modo == DiarioBordo.MOTORISTA_MODO_SERVIDOR and diario.motorista_servidor_id:
        servidor = diario.motorista_servidor
        return servidor.nome, (servidor.cpf_formatado or "")
    if modo == DiarioBordo.MOTORISTA_MODO_OUTRO:
        nome = (diario.motorista_manual_nome or "").strip()
        cpf = (diario.motorista_manual_cpf or "").strip()
        return nome, (format_cpf(cpf) or cpf)
    return _motorista_nome_cpf(diario.prestacao.oficio)


def _viatura_label(modelo: object, tipo_display: object) -> str:
    """`Onix (Descaracterizada)` — modelo + tipo entre parênteses, em capitalize."""
    modelo_fmt = format_document_display(modelo)
    tipo_fmt = format_document_display(tipo_display)
    if modelo_fmt and tipo_fmt:
        return f"{modelo_fmt} ({tipo_fmt})"
    return modelo_fmt or tipo_fmt


def _viatura_dados(oficio: Oficio) -> dict:
    if oficio.viatura_id:
        v = oficio.viatura
        return {
            "viatura": _viatura_label(v.modelo, v.get_tipo_display() if (v.tipo or "").strip() else ""),
            "combustivel": _upper(v.combustivel) if v.combustivel_id else "",
            "placa": format_placa(v.placa) if v.placa else "",
        }
    tm = (oficio.transporte_tipo_manual or "").strip()
    return {
        "viatura": _viatura_label(oficio.transporte_modelo_manual, oficio.get_transporte_tipo_manual_display() if tm else ""),
        "combustivel": (
            _upper(oficio.transporte_combustivel_manual)
            if oficio.transporte_combustivel_manual_id
            else ""
        ),
        "placa": format_placa(oficio.transporte_placa_manual) if oficio.transporte_placa_manual else "",
    }


def _viatura_dados_diario(diario: DiarioBordo) -> dict:
    """Dados da viatura efetiva do diário, considerando o override; senão vem do ofício."""
    modo = diario.viatura_modo
    if modo == DiarioBordo.VIATURA_MODO_BANCO and diario.viatura_id:
        v = diario.viatura
        return {
            "viatura": _viatura_label(v.modelo, v.get_tipo_display() if (v.tipo or "").strip() else ""),
            "combustivel": _upper(v.combustivel) if v.combustivel_id else "",
            "placa": format_placa(v.placa) if v.placa else "",
        }
    if modo == DiarioBordo.VIATURA_MODO_MANUAL:
        tipo_display = dict(Viatura.Tipo.choices).get((diario.viatura_manual_tipo or "").strip(), "")
        return {
            "viatura": _viatura_label(diario.viatura_manual_modelo, tipo_display),
            "combustivel": _upper(diario.viatura_manual_combustivel),
            "placa": format_placa(diario.viatura_manual_placa) if diario.viatura_manual_placa else "",
        }
    return _viatura_dados(diario.prestacao.oficio)


def viatura_resumo_diario(diario: DiarioBordo) -> dict:
    """Resumo da viatura efetiva do diário para exibição (nome/placa/combustível)."""
    dados = _viatura_dados_diario(diario)
    return {
        "viatura": dados.get("viatura") or "—",
        "placa": dados.get("placa") or "",
        "combustivel": dados.get("combustivel") or "",
        "alterada": diario.viatura_alterada,
    }


def viatura_resumo_oficio(oficio: Oficio) -> dict:
    """Resumo da viatura definida no ofício (referência para a Etapa 3)."""
    dados = _viatura_dados(oficio)
    return {
        "viatura": dados.get("viatura") or "—",
        "placa": dados.get("placa") or "",
        "combustivel": dados.get("combustivel") or "",
    }


def _viatura_texto(dados: dict) -> str:
    partes = [dados.get("viatura") or "", dados.get("placa") or ""]
    txt = " — ".join(p for p in partes if p)
    return txt or "não informada"


def alteracoes_motorista_viatura_e_exigencia(prestacao) -> tuple[list[str], bool]:
    """Descreve as trocas e informa se elas exigem justificativa no RT.

    Trocar para outro servidor já pertencente ao ofício e trocar a viatura são
    ocorrências meramente informativas. A justificativa só é exigida quando o
    motorista vem de outro ofício.
    """
    diario = (
        DiarioBordo.objects.filter(prestacao=prestacao)
        .select_related("viatura", "viatura__combustivel", "motorista_servidor")
        .first()
    )
    if diario is None:
        return [], False
    oficio = prestacao.oficio
    itens = []
    exige_justificativa = False

    if diario.motorista_alterado:
        nome_of, _ = motorista_do_oficio(oficio)
        nome_novo, _ = motorista_diario(diario)
        de = format_document_display(nome_of) or "não informado"
        para = format_document_display(nome_novo) or "não informado"
        if de != para:
            itens.append(f"houve a troca do motorista {de} para {para}")
            exige_justificativa = diario.motorista_modo == DiarioBordo.MOTORISTA_MODO_OUTRO

    if diario.viatura_alterada:
        de = _viatura_texto(_viatura_dados(oficio))
        para = _viatura_texto(_viatura_dados_diario(diario))
        if de != para:
            itens.append(f"houve a troca da viatura {de} para {para}")

    return itens, exige_justificativa


def alteracoes_motorista_viatura(prestacao) -> list[str]:
    """Frases descrevendo a troca de motorista e/ou viatura no diário desta prestação,
    em relação ao ofício. Vazio quando nada foi trocado (ou não há diário)."""
    itens, _ = alteracoes_motorista_viatura_e_exigencia(prestacao)
    return itens


def _abastecimento_label(valor) -> str:
    sim = "X" if valor is True else " "
    nao = "X" if valor is False else " "
    return f"( {sim} ) Sim   ( {nao} ) Não"


def build_diario_bordo_context(diario: DiarioBordo) -> tuple[dict, list[dict]]:
    oficio = diario.prestacao.oficio
    inst = build_configuracao_context()
    motorista_nome, motorista_cpf = motorista_diario(diario)
    viatura = _viatura_dados_diario(diario)

    # Ofício/protocolo do motorista: por padrão são os do próprio ofício; quando o
    # motorista é de outro ofício, usam a referência informada no override.
    # Em branco no diário, herda o que o ofício já registrou do motorista de fora.
    if diario.motorista_modo == DiarioBordo.MOTORISTA_MODO_OUTRO:
        numero_motorista, ano_motorista = _split_oficio_ref(
            diario.motorista_oficio_referencia or oficio.motorista_oficio_referencia)
        protocolo_motorista = format_protocolo(diario.motorista_protocolo_ref or oficio.motorista_protocolo_ref) or ""
    else:
        numero_motorista = str(oficio.numero or "").strip()
        ano_motorista = str(oficio.ano or "").strip()
        protocolo_motorista = format_protocolo(oficio.protocolo) or ""

    header = {
        "divisao": _upper(inst.get("divisao")),
        "unidade_cabecalho": _upper(inst.get("unidade")),
        "oficio_motorista": numero_motorista,
        "ano": ano_motorista,
        "protocolo_motorista": protocolo_motorista,
        "viatura": viatura["viatura"],
        "combustivel": viatura["combustivel"],
        "placa": viatura["placa"],
        "placa_reservada": "",
        "motorista": _upper(motorista_nome),
        "cpf_motorista": motorista_cpf,
    }

    linhas = []
    for linha in sincronizar_trechos(diario):
        t = linha.trecho
        saida = _local(getattr(t, "saida_dt", None)) if t else None
        chegada = _local(getattr(t, "chegada_dt", None)) if t else None
        linhas.append(
            {
                "id": linha.pk,  # a linha do diário: o editor documental grava km e abastecimento nela
                "data_saida": saida.strftime("%d/%m/%Y") if saida else "",
                "hora_saida": saida.strftime("%H:%M") if saida else "",
                "km_inicial": linha.km_inicial if linha.km_inicial is not None else "",
                "data_chegada": chegada.strftime("%d/%m/%Y") if chegada else "",
                "hora_chegada": chegada.strftime("%H:%M") if chegada else "",
                "km_final": linha.km_final if linha.km_final is not None else "",
                "origem": _cidade_label(getattr(t, "origem_municipio", None), getattr(getattr(t, "origem_municipio", None), "estado", None)) if t else "",
                "destino": _cidade_label(getattr(t, "destino_municipio", None), getattr(getattr(t, "destino_municipio", None), "estado", None)) if t else "",
                "abastecimento": _abastecimento_label(linha.abastecimento),
            },
        )

    return header, linhas


# ---------------------------------------------------------------------------
# m078 / m095 — hodômetro encadeado, distância prevista e conferência.
#
# O operador digita o km de saída e o de chegada; a distância de cada trecho vem
# da tabela permanente de distâncias (`viagens_roteiros.services.distancias`),
# a mesma que o roteiro usa. A tela sugere o km de chegada de cada trecho
# (saída + distância) e aqui se confere o que foi digitado. Tudo é aviso: nada
# impede de salvar — só o km final menor que o inicial, que o banco já recusa.
# ---------------------------------------------------------------------------

#: Diferença tolerada entre o rodado e a distância prevista do trecho: 20% da
#: distância, nunca menos que 10 km (desvio, abastecimento, entrada na cidade).
TOLERANCIA_KM_PERCENTUAL = 20
TOLERANCIA_KM_MINIMA = 10


def tolerancia_km(prevista: int) -> int:
    return max(TOLERANCIA_KM_MINIMA, (prevista * TOLERANCIA_KM_PERCENTUAL + 99) // 100)


def _rota_da_linha(linha) -> str:
    t = linha.trecho
    if t is None:
        return f"trecho {linha.ordem + 1}"
    origem = format_document_display(_cidade_label(t.origem_municipio, None)) or "—"
    destino = format_document_display(_cidade_label(t.destino_municipio, None)) or "—"
    return f"{origem} → {destino}"


def _fmt_km(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def viatura_id_do_diario(diario: DiarioBordo):
    """A viatura do cadastro usada neste diário (a trocada ou a do ofício); manual não conta."""
    if diario.viatura_modo == DiarioBordo.VIATURA_MODO_BANCO:
        return diario.viatura_id
    if diario.viatura_modo == DiarioBordo.VIATURA_MODO_OFICIO:
        return diario.prestacao.oficio.viatura_id
    return None


def ultimo_km_da_viatura(diario: DiarioBordo) -> dict | None:
    """O último km de chegada registrado para a mesma viatura em outro diário (m088).

    Só informação: nada é preenchido com ele. "Último" é o da viagem mais recente
    que chegou antes da saída desta (quando a saída é conhecida), para uma viagem
    lançada fora de ordem não comparar com o futuro.
    """
    from django.db.models import Q

    viatura_id = viatura_id_do_diario(diario)
    if not viatura_id:
        return None
    candidatas = (
        DiarioBordoTrecho.objects.filter(km_final__isnull=False)
        .exclude(diario=diario)
        .filter(
            Q(diario__viatura_modo=DiarioBordo.VIATURA_MODO_BANCO, diario__viatura_id=viatura_id)
            | Q(diario__viatura_modo=DiarioBordo.VIATURA_MODO_OFICIO, diario__prestacao__oficio__viatura_id=viatura_id)
        )
    )
    saida = (
        diario.trechos.filter(trecho__saida_dt__isnull=False)
        .order_by("trecho__saida_dt")
        .values_list("trecho__saida_dt", flat=True)
        .first()
    )
    if saida is not None:
        candidatas = candidatas.filter(Q(trecho__chegada_dt__lte=saida) | Q(trecho__chegada_dt__isnull=True))
    linha = (
        candidatas.select_related("trecho", "diario__prestacao__oficio")
        .order_by(F("trecho__chegada_dt").desc(nulls_last=True), "-km_final", "-pk")
        .first()
    )
    if linha is None:
        return None
    quando = _local(getattr(linha.trecho, "chegada_dt", None)) or _local(linha.diario.atualizado_em)
    return {
        "km": linha.km_final,
        "km_label": _fmt_km(linha.km_final),
        "data": quando.strftime("%d/%m/%Y") if quando else "",
        "data_curta": quando.strftime("%d/%m") if quando else "",
        "oficio": linha.diario.prestacao.oficio.numero_formatado,
    }


def conferir_hodometro(diario: DiarioBordo, linhas=None) -> dict:
    """Distância prevista por trecho, rodado, totais e avisos do diário.

    Os avisos são o que parece estranho no hodômetro: o km de saída de um trecho
    menor que o de chegada do anterior (voltou para trás) e o rodado de um trecho
    fora da tolerância da distância prevista. A tela mostra ao abrir e a cada
    gravação automática (vai na resposta do autosave).
    """
    from viagens_roteiros.services.distancias import distancia_do_trecho

    if linhas is None:
        linhas = list(
            diario.trechos.select_related(
                "trecho__origem_municipio", "trecho__destino_municipio"
            ).order_by("ordem", "pk")
        )
    itens = []
    avisos = []
    ultimo = ultimo_km_da_viatura(diario)
    primeira = linhas[0] if linhas else None
    if ultimo and primeira is not None and primeira.km_inicial is not None and primeira.km_inicial < ultimo["km"]:
        avisos.append(
            f"O km de saída ({_fmt_km(primeira.km_inicial)}) é menor que o último km registrado desta "
            f"viatura ({ultimo['km_label']}, em {ultimo['data']}, Ofício {ultimo['oficio']})."
        )
    total_rodado = 0
    total_previsto = 0
    anterior = None
    for linha in linhas:
        distancia = distancia_do_trecho(linha.trecho)
        prevista = int(round(distancia)) if distancia else None
        rodado = None
        if linha.km_inicial is not None and linha.km_final is not None:
            rodado = linha.km_final - linha.km_inicial
            total_rodado += rodado
        if prevista:
            total_previsto += prevista
        rota = _rota_da_linha(linha)
        if (
            anterior is not None
            and anterior.km_final is not None
            and linha.km_inicial is not None
            and linha.km_inicial < anterior.km_final
        ):
            avisos.append(
                f"{rota}: o km de saída ({_fmt_km(linha.km_inicial)}) é menor que o de chegada "
                f"do trecho anterior ({_fmt_km(anterior.km_final)}) — o hodômetro voltou para trás."
            )
        if rodado is not None and prevista and abs(rodado - prevista) > tolerancia_km(prevista):
            avisos.append(
                f"{rota}: {_fmt_km(rodado)} km rodados, e a distância prevista é de "
                f"{_fmt_km(prevista)} km (diferença de {_fmt_km(abs(rodado - prevista))} km)."
            )
        itens.append({"id": linha.pk, "prevista": prevista, "rodado": rodado})
        anterior = linha
    return {
        "linhas": itens,
        "total_rodado": total_rodado,
        "total_previsto": total_previsto,
        "total_rodado_label": _fmt_km(total_rodado),
        "total_previsto_label": _fmt_km(total_previsto),
        "avisos": avisos,
        "ultimo_km": ultimo,
    }


def corrigir_distancia_da_linha(linha: DiarioBordoTrecho, distancia_km) -> None:
    """Corrige, na tabela permanente, a distância entre os municípios do trecho.

    Vale para todos os roteiros e diários daqui para a frente — é a distância
    entre as cidades, não um dado desta prestação. Levanta `ValueError` com a
    mensagem para o operador.
    """
    from viagens_roteiros.services.distancias import corrigir

    trecho = linha.trecho
    if trecho is None or not trecho.origem_municipio_id or not trecho.destino_municipio_id:
        raise ValueError("Este trecho não tem origem e destino cadastrados.")
    corrigir(trecho.origem_municipio_id, trecho.destino_municipio_id, distancia_km)


def _template_path() -> Path:
    return Path(settings.BASE_DIR) / "documentos" / "resources" / "diario_bordo.xlsx"


def gerar_diario_bordo_documento(diario, formato):
    from documentos.services.facade import build_default_facade
    from documentos.services.types import DocumentoTipo
    from documentos.services.document_blocks import conteudo_documental
    header, trechos = build_diario_bordo_context(diario)
    return build_default_facade().gerar(
        tipo=DocumentoTipo.DIARIO_BORDO, formato=formato,
        payload={"header": header, "trechos": trechos, "documento": conteudo_documental(DocumentoTipo.DIARIO_BORDO, diario.prestacao)},
        reference=diario.prestacao.oficio.numero_formatado.replace("/", "-"),
        prestacao_id=diario.prestacao_id, oficio_id=diario.prestacao.oficio_id,
    )


def gerar_diario_bordo_xlsx(diario: DiarioBordo) -> bytes:
    from documentos.services.types import DocumentoFormato
    return gerar_diario_bordo_documento(diario, DocumentoFormato.XLSX).conteudo


def gerar_diario_bordo_pdf(diario: DiarioBordo) -> bytes:
    from documentos.services.types import DocumentoFormato
    return gerar_diario_bordo_documento(diario, DocumentoFormato.PDF).conteudo


def nome_arquivo_diario(diario: DiarioBordo, formato: str = "xlsx") -> str:
    pc = diario.prestacao
    oficio = pc.oficio.numero_formatado.replace("/", "-")
    ext = "pdf" if formato == "pdf" else "xlsx"
    return f"DIARIO_DE_BORDO_OFICIO_{oficio}.{ext}"


# ---------------------------------------------------------------------------
# `BE-14` fatia 4 — a gravação do diário sai das views.
#
# `sincronizar_trechos` (acima) já era atômica desde o `DB-08`: a parte que **cria** as
# linhas do diário estava protegida, a que **preenche** não estava. Estas três funções
# fecham isso.
# ---------------------------------------------------------------------------

#: Campos que o autosave do diário aceita, por linha.
CAMPOS_AUTOSAVE_DIARIO = frozenset({"km_inicial", "km_final", "abastecimento"})

#: Qual status marcar depois de gravar — a única diferença entre as duas rotas de
#: autosave do diário, como no RT (`rt_services.ESCOPO_*`).
ESCOPO_SERVIDOR = "servidor"
ESCOPO_EQUIPE = "equipe"

_CAMPO_LINHA = re.compile(r"^form-(\d+)-(km_inicial|km_final|abastecimento)$")


def obter_ou_criar_diario(prestacao) -> DiarioBordo:
    """O diário da prestação, criado na primeira visita à tela.

    Fica no service e não em `selectors.py` porque `get_or_create` **grava**
    (`docs/PADRAO_SELECTORS.md`: selector é consulta) — mesma razão de
    `rt_services.obter_ou_criar_relatorio_tecnico`, na fatia 1.
    """
    diario, _ = DiarioBordo.objects.get_or_create(prestacao=prestacao)
    return diario


def _parse_km(value):
    digitos = re.sub(r"\D", "", str(value or ""))
    return int(digitos) if digitos else None


class DiarioValidacaoError(Exception):
    """Erro de domínio do autosave do diário: o que o operador digitou não vale.

    Mesmo papel do `DelecaoProtegidaError` em `core/deletion.py` — o service não sabe
    o que é uma resposta HTTP (`docs/PADRAO_SERVICES.md:18`), então levanta, e a view
    traduz em `autosave_json_response(ok=False, ...)`.
    """


@transaction.atomic
def salvar_autosave_do_diario(
    diario: DiarioBordo, *, fields, dirty_fields, escopo, servidor_prestacao=None
) -> int:
    """Grava km e abastecimento das linhas sujas, e marca o status. Devolve quantas linhas mudou.

    Atômica porque grava **em laço**, uma linha por vez: duas linhas sujas são duas
    gravações, e sem transação uma falha entre elas deixa metade — o operador vê uma
    linha salva e a outra não, sem nada dizendo isso (`BE-14`).

    **Uma gravação por linha, não por campo** (`NOVO-116`). O `diario_trecho_km_ordenado`
    compara os dois km entre si, e o payload não promete ordem: gravar campo a campo passa
    por um estado intermediário que mistura o km novo com o antigo do par. Corrigir uma
    linha de `100→200` para `5000→6000` violaria a constraint no meio do caminho — em
    `km_inicial=5000` contra o `km_final=200` que ainda não foi gravado — e derrubaria uma
    edição perfeitamente válida, de forma intermitente. Juntar os campos da linha numa
    gravação só faz o estado intermediário deixar de existir.

    Recebe o payload já interpretado, nunca o `request` (`docs/PADRAO_SERVICES.md:20`).
    """
    from .services import marcar_servidor_em_preenchimento
    from .services import marcar_servidores_pendentes

    linhas = list(diario.trechos.select_related("trecho").order_by("ordem", "pk"))

    # Agrupa por linha preservando a ordem de chegada, para a gravação sair determinística.
    por_linha: dict[int, dict[str, object]] = {}
    for nome in dirty_fields:
        match = _CAMPO_LINHA.match(str(nome or ""))
        if not match:
            continue
        indice, campo = int(match.group(1)), match.group(2)
        if indice >= len(linhas):
            continue
        por_linha.setdefault(indice, {})[campo] = fields.get(nome)

    gravadas = 0
    for indice, campos in por_linha.items():
        linha = linhas[indice]
        for campo, valor in campos.items():
            if campo in {"km_inicial", "km_final"}:
                setattr(linha, campo, _parse_km(valor))
            else:
                linha.abastecimento = str(valor or "") != "nao"
        # Antes de gravar, e não depois: sem isto a violação chega como `IntegrityError`
        # na view, que não a trata — o operador levava 500 em vez da mensagem.
        try:
            linha.validate_constraints()
        except ValidationError as exc:
            raise DiarioValidacaoError(" ".join(exc.messages)) from exc
        linha.save(update_fields=sorted(campos))
        gravadas += 1

    if gravadas:
        diario.save(update_fields=["atualizado_em"])
    if dirty_fields:
        if escopo == ESCOPO_SERVIDOR:
            marcar_servidor_em_preenchimento(servidor_prestacao)
        else:
            marcar_servidores_pendentes(diario.prestacao)
    return gravadas


@transaction.atomic
def salvar_linhas_do_diario(formset, servidor_prestacao) -> int:
    """Caminho sem JS: o formset das linhas e a marcação de status na mesma transação.

    O form já validou; aqui só se grava. `formset.save()` escreve N linhas de uma vez, e
    a marcação é a N+1.
    """
    from .services import marcar_servidor_em_preenchimento

    salvas = formset.save()
    marcar_servidor_em_preenchimento(servidor_prestacao)
    return len(salvas)


@transaction.atomic
def trocar_motorista_do_diario(form, prestacao, servidor_prestacao) -> None:
    """Troca motorista/viatura só deste diário, com a prévia do RT e o status juntos.

    São **três gravações**: o diário, a prévia de "informações complementares" do RT e a
    marcação. O texto do RT é o que **explica a troca** no documento — deixá-lo para trás
    numa falha significa emitir o documento sem a explicação, e a tela não diz nada.

    `sincronizar_info_complementares_rt` só preenche quando o campo está vazio: não
    sobrescreve texto do usuário. Essa regra é de antes desta fatia e não mudou.
    """
    from .services import marcar_servidor_em_preenchimento

    form.save()
    sincronizar_info_complementares_rt(prestacao)
    marcar_servidor_em_preenchimento(servidor_prestacao)


def sincronizar_info_complementares_rt(prestacao) -> bool:
    """Gera a prévia de "informações complementares" do RT, se ainda estiver vazia.

    Devolve se gravou. Não sobrescreve texto do usuário — a checagem de vazio é a regra,
    não um detalhe de implementação.
    """
    from .models import RelatorioTecnico
    from .services import descricao_ajustes_prestacao

    relatorio = RelatorioTecnico.objects.filter(prestacao=prestacao).first()
    if relatorio is None or normalize_spaces(relatorio.info_complementares or ""):
        return False
    texto = descricao_ajustes_prestacao(prestacao)
    if not texto:
        return False
    relatorio.info_complementares = texto
    relatorio.save(update_fields=["info_complementares", "atualizado_em"])
    return True
