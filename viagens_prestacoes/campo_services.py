"""O diário de bordo no celular do motorista, mesmo sem internet (m096).

O operador gera um **link pessoal** do diário (token longo e aleatório) e o manda
ao motorista pelo WhatsApp. A página do link (`campo_views`) abre sem login, mostra
só o que o motorista precisa — trechos, datas, viatura e os campos do diário — e
guarda os lançamentos no próprio celular; quando a conexão volta, eles seguem para
cá numa fila, cada um com um id gerado no celular.

Aqui é o lado do servidor: gerar/revogar o link, conferir se ele ainda vale, montar
os dados da página e gravar os lançamentos — de forma idempotente e pelo mesmo
caminho do autosave do diário (`diario_services.salvar_autosave_do_diario`), com a
mesma conferência do hodômetro e os mesmos avisos (`conferir_hodometro`).
"""

from __future__ import annotations

import datetime
import re
from urllib.parse import quote

from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from .diario_services import ESCOPO_EQUIPE
from .diario_services import DiarioValidacaoError
from .diario_services import _cidade_label
from .diario_services import _local
from .diario_services import conferir_hodometro
from .diario_services import motorista_diario
from .diario_services import roteiro_efetivo
from .diario_services import salvar_autosave_do_diario
from .diario_services import sincronizar_trechos
from .diario_services import viatura_resumo_diario
from .models import DiarioBordo
from .models import LancamentoDiarioCampo
from .models import LinkDiarioCampo

#: Por quantos dias depois da chegada de volta o link continua valendo — tempo de
#: o motorista lançar o que ficou para trás.
DIAS_VALIDADE_APOS_RETORNO = 5
#: Sem data de retorno no roteiro, o link vale isto a partir de quando foi gerado.
DIAS_VALIDADE_SEM_RETORNO = 30
#: Quantos lançamentos cabem num envio; a fila do celular manda em lotes.
MAX_LANCAMENTOS_POR_ENVIO = 50
#: O maior km aceito (o campo é `PositiveIntegerField`; hodômetro não passa disto).
KM_MAXIMO = 9_999_999

_ID_CLIENTE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class LinkInvalido(Exception):
    """O link não abre: não existe, foi revogado, venceu ou a viagem foi cancelada."""

    def __init__(self, motivo: str, mensagem: str):
        super().__init__(mensagem)
        self.motivo = motivo


class EnvioInvalido(Exception):
    """O corpo do envio não tem o formato esperado (a fila do celular manda outro)."""


# ---------------------------------------------------------------------------
# Datas da viagem e validade do link
# ---------------------------------------------------------------------------


def datas_da_viagem(prestacao) -> tuple[datetime.datetime | None, datetime.datetime | None]:
    """Saída da sede e chegada de volta, pelo roteiro que o diário usa."""
    roteiro = roteiro_efetivo(prestacao)
    if roteiro is None:
        return None, None
    saida, retorno = roteiro.saida_dt, roteiro.retorno_chegada_dt
    if saida is None or retorno is None:
        trechos = list(roteiro.trechos.all())
        saidas = [t.saida_dt for t in trechos if t.saida_dt]
        chegadas = [t.chegada_dt for t in trechos if t.chegada_dt]
        saida = saida or (min(saidas) if saidas else None)
        retorno = retorno or (max(chegadas) if chegadas else None)
    return saida, retorno


def validade_do_link(prestacao, agora=None) -> datetime.datetime:
    """Até quando um link gerado agora vale: alguns dias depois da chegada de volta."""
    agora = agora or timezone.now()
    _saida, retorno = datas_da_viagem(prestacao)
    if retorno is not None:
        limite = retorno + datetime.timedelta(days=DIAS_VALIDADE_APOS_RETORNO)
        # Viagem que já voltou há tempo: ainda dá alguns dias a partir de hoje.
        return max(limite, agora + datetime.timedelta(days=DIAS_VALIDADE_APOS_RETORNO))
    return agora + datetime.timedelta(days=DIAS_VALIDADE_SEM_RETORNO)


def link_ativo(diario: DiarioBordo) -> LinkDiarioCampo | None:
    agora = timezone.now()
    return diario.links_campo.filter(revogado_em__isnull=True, expira_em__gt=agora).first()


@transaction.atomic
def gerar_link(diario: DiarioBordo, usuario=None) -> LinkDiarioCampo:
    """Um link novo para o diário; o anterior, se houver, deixa de abrir."""
    revogar_links(diario)
    return LinkDiarioCampo.objects.create(
        diario=diario,
        expira_em=validade_do_link(diario.prestacao),
        criado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
    )


def revogar_links(diario: DiarioBordo) -> int:
    return diario.links_campo.filter(revogado_em__isnull=True).update(revogado_em=timezone.now())


def obter_link_valido(token: str) -> LinkDiarioCampo:
    """O link do token, se ainda abre; senão `LinkInvalido` com o motivo."""
    token = str(token or "")
    link = None
    if 20 <= len(token) <= 64:
        link = (
            LinkDiarioCampo.objects.select_related("diario__prestacao__oficio")
            .filter(token=token)
            .first()
        )
    if link is None:
        raise LinkInvalido("inexistente", "Este link não existe. Peça um novo a quem enviou.")
    if link.revogado_em is not None:
        raise LinkInvalido("revogado", "Este link foi desativado. Peça o link novo a quem enviou.")
    if link.expira_em <= timezone.now():
        raise LinkInvalido("vencido", "Este link venceu. Se ainda falta lançar algo, peça um novo.")
    if link.diario.prestacao.oficio.cancelado:
        raise LinkInvalido("cancelado", "Esta viagem foi cancelada.")
    return link


def diario_travado(diario: DiarioBordo) -> bool:
    """A equipe inteira já finalizou a prestação: o diário é só leitura (m092)."""
    from .trava import equipe_finalizada

    return equipe_finalizada(diario.prestacao)


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------


def telefone_do_motorista(diario: DiarioBordo) -> str:
    """Celular do motorista com DDI 55, quando o cadastro tem os 11 dígitos."""
    from .presenters import _whatsapp_phone

    servidor = None
    if diario.motorista_modo == DiarioBordo.MOTORISTA_MODO_SERVIDOR:
        servidor = diario.motorista_servidor
    elif diario.motorista_modo == DiarioBordo.MOTORISTA_MODO_OFICIO:
        servidor = diario.prestacao.oficio.motorista
    return _whatsapp_phone(servidor) if servidor is not None else ""


def mensagem_whatsapp(link: LinkDiarioCampo, url: str) -> str:
    """O texto pronto que vai com o link: como funciona e por que vale a pena."""
    oficio = link.diario.prestacao.oficio
    nome, _cpf = motorista_diario(link.diario)
    primeiro_nome = (nome or "").strip().split(" ")[0].title()
    saida, _retorno = datas_da_viagem(link.diario.prestacao)
    saida_local = _local(saida)
    quando = f" que sai em {saida_local:%d/%m às %H:%M}" if saida_local else ""
    validade = _local(link.expira_em)
    linhas = [
        f"Olá{', ' + primeiro_nome if primeiro_nome else ''}! Este é o link do diário de bordo da viagem do Ofício {oficio.numero_formatado}{quando}:",
        url,
        "",
        "Como funciona:",
        "1. Abra o link no celular antes de sair, ainda com internet. Se quiser, adicione à tela inicial.",
        "2. Em cada trecho, digite o km do painel na saída e na chegada e marque se precisou abastecer.",
        "3. Pode preencher sem sinal: fica salvo no celular e é enviado sozinho quando a internet voltar.",
        "",
        "Vantagens: nada de anotar em papel ou lembrar o km de memória na volta; o km de chegada já vem sugerido pela distância do trecho; e o diário fica pronto para gerar e assinar assim que você chegar.",
        "",
        "O link é pessoal: não repasse. Ele só dá acesso a este diário"
        + (f" e vale até {validade:%d/%m/%Y}." if validade else "."),
    ]
    return "\n".join(linhas)


def url_whatsapp(link: LinkDiarioCampo, url: str) -> str:
    texto = quote(mensagem_whatsapp(link, url))
    telefone = telefone_do_motorista(link.diario)
    return f"https://wa.me/{telefone}?text={texto}" if telefone else f"https://wa.me/?text={texto}"


# ---------------------------------------------------------------------------
# A página do motorista
# ---------------------------------------------------------------------------


def _estado_das_linhas(linhas, hodometro) -> list[dict]:
    previstas = {item["id"]: item["prevista"] for item in hodometro["linhas"]}
    trechos = []
    for linha in linhas:
        t = linha.trecho
        saida = _local(getattr(t, "saida_dt", None)) if t else None
        chegada = _local(getattr(t, "chegada_dt", None)) if t else None
        trechos.append(
            {
                "id": linha.pk,
                "ordem": linha.ordem + 1,
                "origem": _cidade_label(getattr(t, "origem_municipio", None), None) if t else "",
                "destino": _cidade_label(getattr(t, "destino_municipio", None), None) if t else "",
                "saida": saida.strftime("%d/%m %H:%M") if saida else "",
                "chegada": chegada.strftime("%d/%m %H:%M") if chegada else "",
                "prevista": previstas.get(linha.pk),
                "km_inicial": linha.km_inicial,
                "km_final": linha.km_final,
                "abastecimento": linha.abastecimento,
            }
        )
    return trechos


def _linhas(diario: DiarioBordo):
    return list(
        diario.trechos.select_related(
            "trecho__origem_municipio", "trecho__destino_municipio"
        ).order_by("ordem", "pk")
    )


def estado_do_diario(diario: DiarioBordo) -> dict:
    """O que a página do motorista mostra e o que volta a cada sincronização.

    Só o necessário: nada de CPF nem dos outros servidores da equipe. O último km
    da viatura vai só como número e data, sem o ofício de outra viagem.
    """
    linhas = _linhas(diario)
    hodometro = conferir_hodometro(diario, linhas)
    ultimo = hodometro.get("ultimo_km")
    return {
        "trechos": _estado_das_linhas(linhas, hodometro),
        "avisos": hodometro["avisos"],
        "total_rodado": hodometro["total_rodado"],
        "total_previsto": hodometro["total_previsto"],
        "ultimo_km": {"km": ultimo["km"], "data": ultimo["data"]} if ultimo else None,
        "travado": diario_travado(diario),
    }


def dados_da_pagina(link: LinkDiarioCampo) -> dict:
    diario = link.diario
    sincronizar_trechos(diario)
    oficio = diario.prestacao.oficio
    nome, _cpf = motorista_diario(diario)
    viatura = viatura_resumo_diario(diario)
    saida, retorno = datas_da_viagem(diario.prestacao)
    return {
        "oficio": oficio.numero_formatado,
        "motorista": nome or "",
        "viatura": viatura.get("viatura") or "",
        "placa": viatura.get("placa") or "",
        "saida": _local(saida).strftime("%d/%m/%Y %H:%M") if saida else "",
        "retorno": _local(retorno).strftime("%d/%m/%Y %H:%M") if retorno else "",
        "validade": _local(link.expira_em).strftime("%d/%m/%Y"),
        **estado_do_diario(diario),
    }


# ---------------------------------------------------------------------------
# Sincronização
# ---------------------------------------------------------------------------


def _km(valor, rotulo):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{rotulo} inválido.")
    if isinstance(valor, str):
        if not valor.strip().isdigit():
            raise ValueError(f"{rotulo} deve ter só números.")
        valor = int(valor.strip())
    if not isinstance(valor, int):
        raise ValueError(f"{rotulo} inválido.")
    if valor < 0 or valor > KM_MAXIMO:
        raise ValueError(f"{rotulo} fora do limite.")
    return valor


def _validar(bruto, indice_por_linha) -> tuple[int, dict]:
    """Confere um lançamento; devolve o índice da linha e os campos a gravar."""
    try:
        linha_pk = int(bruto.get("linha"))
    except (TypeError, ValueError):
        raise ValueError("Trecho não informado.") from None
    if isinstance(bruto.get("linha"), bool) or linha_pk not in indice_por_linha:
        raise ValueError("Este trecho não está mais no diário (o roteiro mudou). Recarregue a página.")
    campos = {}
    for nome, rotulo in (("km_inicial", "Km de saída"), ("km_final", "Km de chegada")):
        if nome in bruto:
            campos[nome] = _km(bruto[nome], rotulo)
    if "abastecimento" in bruto:
        valor = bruto["abastecimento"]
        if valor is not None and not isinstance(valor, bool):
            raise ValueError("Abastecimento inválido.")
        if valor is not None:
            campos["abastecimento"] = valor
    if not campos:
        raise ValueError("Nada para gravar.")
    return indice_por_linha[linha_pk], campos


def _resultado(registro: LancamentoDiarioCampo) -> dict:
    return {"id": registro.cliente_id, "situacao": registro.situacao, "mensagem": registro.mensagem}


def _gravar(link, indice, campos) -> None:
    fields, dirty = {}, []
    for campo, valor in campos.items():
        nome = f"form-{indice}-{campo}"
        if campo == "abastecimento":
            fields[nome] = "sim" if valor else "nao"
        else:
            fields[nome] = "" if valor is None else str(valor)
        dirty.append(nome)
    salvar_autosave_do_diario(link.diario, fields=fields, dirty_fields=dirty, escopo=ESCOPO_EQUIPE)


def aplicar_lancamentos(link: LinkDiarioCampo, lancamentos) -> list[dict]:
    """Grava os lançamentos na ordem em que chegaram; devolve o resultado de cada um.

    Idempotente pelo id do celular: o que já foi recebido devolve o mesmo resultado
    sem gravar de novo. Um lançamento recusado (km de chegada menor que o de saída,
    trecho que sumiu do roteiro, valor inválido) não impede os outros — cada um
    grava no seu próprio ponto de salvamento.
    """
    if not isinstance(lancamentos, list):
        raise EnvioInvalido("Envio sem a lista de lançamentos.")
    if len(lancamentos) > MAX_LANCAMENTOS_POR_ENVIO:
        raise EnvioInvalido(f"No máximo {MAX_LANCAMENTOS_POR_ENVIO} lançamentos por envio.")
    diario = link.diario
    sincronizar_trechos(diario)
    indice_por_linha = {pk: i for i, pk in enumerate(diario.trechos.order_by("ordem", "pk").values_list("pk", flat=True))}
    resultados = []
    gravou = False
    for bruto in lancamentos:
        cliente_id = bruto.get("id") if isinstance(bruto, dict) else None
        if not isinstance(cliente_id, str) or not _ID_CLIENTE.match(cliente_id):
            resultados.append({"id": cliente_id if isinstance(cliente_id, str) else "", "situacao": LancamentoDiarioCampo.SITUACAO_RECUSADO, "mensagem": "Lançamento sem identificação válida."})
            continue
        existente = LancamentoDiarioCampo.objects.filter(diario=diario, cliente_id=cliente_id).first()
        if existente is not None:
            resultados.append(_resultado(existente))
            continue
        situacao, mensagem, linha_pk, campos = LancamentoDiarioCampo.SITUACAO_GRAVADO, "", None, {}
        try:
            indice, campos = _validar(bruto, indice_por_linha)
            linha_pk = next(pk for pk, i in indice_por_linha.items() if i == indice)
        except ValueError as exc:
            situacao, mensagem = LancamentoDiarioCampo.SITUACAO_RECUSADO, str(exc)
        try:
            with transaction.atomic():
                registro = LancamentoDiarioCampo.objects.create(
                    diario=diario,
                    link=link,
                    cliente_id=cliente_id,
                    linha_id=linha_pk,
                    dados=campos,
                    situacao=situacao,
                    mensagem=mensagem[:255],
                )
                if situacao == LancamentoDiarioCampo.SITUACAO_GRAVADO:
                    try:
                        with transaction.atomic():
                            _gravar(link, indice, campos)
                        gravou = True
                    except DiarioValidacaoError as exc:
                        registro.situacao = LancamentoDiarioCampo.SITUACAO_RECUSADO
                        registro.mensagem = str(exc)[:255]
                        registro.save(update_fields=["situacao", "mensagem"])
        except IntegrityError:
            # Chegou ao mesmo tempo por outra requisição: vale o que ela gravou.
            registro = LancamentoDiarioCampo.objects.get(diario=diario, cliente_id=cliente_id)
        resultados.append(_resultado(registro))
    if gravou:
        LinkDiarioCampo.objects.filter(pk=link.pk).update(ultimo_envio_em=timezone.now())
    return resultados
