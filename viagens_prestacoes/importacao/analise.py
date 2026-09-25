"""Análise do processo do eProtocolo para a prestação de contas de Viagens.

Lê o PDF (`core.leitura`), descobre de qual prestação ele é e decide o destino
de cada documento. **Não grava nada** e roda fora da transação de escrita: ler
um volume de 50 folhas leva alguns segundos, e segurar a transação nesse tempo
travaria o resto do sistema. Só consulta o banco.

**De qual prestação**, em camadas (achar o ofício é achar a prestação):

1. protocolo do rodapé/título/capa igual a `Oficio.protocolo` (só dígitos).
   Origem SIMULADO ou TREINAMENTO vale pouco: o número foi inventado aqui, e o
   processo real traz outro;
2. nº/ano do ofício — capa ("Nº/Ano"), título do próprio ofício, "Ref. ao
   Ofício" do RT, "Referente ao Ofício:" do diário, assunto do despacho. Com o
   protocolo simulado por padrão, é via principal tanto quanto a 1;
3. CPFs da equipe (tabela do ofício, RT, termos) — só confirma, desempata ou
   sugere; sozinha nunca aplica.

PDF só de termos (sem protocolo nem nº do ofício — os termos assinados de uma
viagem, escaneados juntos): os CPFs dos termos e a data escrita neles apontam a
viagem. É seguro quando todos os termos são de quem tem termo naquela viagem, a
data cai no período dela e nenhuma outra viagem faz o mesmo. Termo do cadastro
sem ofício (avulso) também é candidato, sem prestação.

A identificação é **segura** quando há ao menos um sinal forte (protocolo
oficial, nº/ano da capa ou do ofício), dois sinais independentes e nenhum
concorrente perto. Senão a tela de conferência pergunta, com os candidatos.

**Para onde vai cada documento**: ofício, despacho(s) e diário são do ofício
(compartilhados); o ofício assinado também vira a versão assinada do documento
do ofício, e justificativa, termos (um por servidor) e ordem de serviço vão para
a versão assinada do documento deles (`documentos`, `artefatos`); RT e
comprovante são de um servidor — pelo CPF completo no RT;
no comprovante pelo CPF mascarado (meio `***.456.789-**` ou pontas
`123.***.***-00`), pelo nome (tolerando truncado e sem acento), pelo valor
(nunca acima da diária liberada) e, na falta, por quem inseriu ou assinou no
eProtocolo. Só dentro da equipe ativa da prestação.

LGPD: CPF e texto do documento não saem daqui — nem para o plano, nem para log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from django.utils import timezone

from core.leitura import classificacao as tipos
from core.leitura.eprotocolo import Processo
from core.leitura.eprotocolo import ler_processo
from core.leitura.pdf import fica_em_paisagem
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.texto import normalizar
from core.utils.masks import format_protocolo

from ..models import PrestacaoContas
from ..models import PrestacaoDocumentoAnexo as Anexo
from . import documentos as docs_do_oficio
from .montagem import descrever_paginas
from .plano import DESTINO_JUSTIFICATIVA
from .plano import DESTINO_ORDEM_SERVICO
from .plano import DESTINO_TERMO
from .plano import IGNORAR
from .plano import ORIGENS
from .plano import Candidato
from .plano import ItemPlano
from .plano import Plano

__all__ = ["analisar", "semelhanca_nome", "DESTINO_DO_TIPO"]

#: Tipo lido → tipo de anexo da prestação.
DESTINO_DO_TIPO = {
    tipos.OFICIO: Anexo.TIPO_OFICIO_ASSINADO,
    tipos.DESPACHO: Anexo.TIPO_DESPACHO,
    tipos.RT: Anexo.TIPO_RT_ASSINADO,
    tipos.DIARIO_BORDO: Anexo.TIPO_DB_ASSINADO,
    tipos.COMPROVANTE: Anexo.TIPO_COMPROVANTE,
    tipos.JUSTIFICATIVA: DESTINO_JUSTIFICATIVA,
    tipos.TERMO_AUTORIZACAO: DESTINO_TERMO,
    tipos.ORDEM_SERVICO: DESTINO_ORDEM_SERVICO,
}

#: Documentos do processo que não vão para lugar nenhum de Viagens, e por quê.
_FORA_DA_PRESTACAO = {
    tipos.CAPA: "Capa do processo.",
    tipos.PLANO_TRABALHO: "Plano de trabalho: não faz parte da prestação.",
    tipos.EMAIL: "E-mail: não faz parte da prestação.",
}

#: Peso de cada lugar onde o nº/ano do ofício aparece. O diário pesa menos: o
#: motorista de outro ofício leva o nº daquele ofício no cabeçalho.
_PESO_NUMERO_ANO = {
    "capa": 1.0,
    "ofício": 1.0,
    "relatório técnico": 0.8,
    "despacho": 0.5,
    "justificativa": 0.5,
    "diário de bordo": 0.4,
}
#: "no ofício", "na capa" — para as frases da tela.
_NO_LUGAR = {
    "capa": "na capa",
    "ofício": "no ofício",
    "relatório técnico": "no relatório técnico",
    "despacho": "no despacho",
    "justificativa": "na justificativa",
    "diário de bordo": "no diário de bordo",
}
_FONTES_FORTES = {"protocolo", "numero_ano:capa", "numero_ano:ofício"}
#: Abaixo desta confiança o tipo lido vai para a conferência.
CONFIANCA_MINIMA = 0.5
#: Semelhança de nome que basta para casar um comprovante com o servidor.
NOME_CASA = 0.85
_RX_OFICIO_NO_TEXTO = re.compile(r"\bOF(?:ICIO|\.)\s*(?:N\s*[O°º.]*\s*)?:?\s*0*(\d{1,4})\s*/\s*(\d{4})")


# ─────────────────────────────────────────────────────────────────
# Nomes
# ─────────────────────────────────────────────────────────────────

_LIGACOES = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def _tokens(nome: str) -> list[str]:
    return [t for t in normalizar(nome).replace(".", " ").split() if t not in _LIGACOES]


def semelhanca_nome(lido: str, cadastrado: str) -> float:
    """De 0 a 1: o nome lido (comprovante, rodapé) é o do cadastro?

    Tolera o que os bancos fazem: sem acento, caixa alta, truncado no fim
    ("FULANO DE TA"), abreviado ("FULANO D TAL") e o nome do meio omitido.
    """
    a, b = _tokens(lido), _tokens(cadastrado)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Truncado: o lido é o começo do cadastrado, com a última palavra cortada.
    if len(a) <= len(b) and a[:-1] == b[: len(a) - 1] and b[len(a) - 1].startswith(a[-1]) and len(" ".join(a)) >= 8 and len(a) >= 2:
        return 0.92
    # Abreviado: cada palavra lida é o começo da cadastrada (iniciais).
    if len(a) == len(b) and all(y.startswith(x) for x, y in zip(a, b)):
        return 0.9
    # Primeiro e último batem (nome do meio omitido).
    if len(a) >= 2 and a[0] == b[0] and a[-1] == b[-1]:
        return 0.88
    # Nome curto do cartão: primeiro nome e um dos sobrenomes ("FULANA PEREIRA"
    # para "FULANA VILLELA DE SOUZA PEREIRA LIMA").
    if len(a) == 2 and a[0] == b[0] and len(a[1]) >= 3 and a[1] in b[1:]:
        return 0.86
    return round(SequenceMatcher(None, " ".join(a), " ".join(b)).ratio(), 3)


# ─────────────────────────────────────────────────────────────────
# Identificação
# ─────────────────────────────────────────────────────────────────

@dataclass
class _Identificacao:
    prestacao: PrestacaoContas | None = None
    termo: object = None
    camada: str = ""
    segura: bool = False
    evidencias: list[str] = field(default_factory=list)
    candidatos: list[Candidato] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _numero_ano(texto: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*0*(\d{1,4})\s*/\s*(\d{4})\s*", str(texto or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _referencias_ao_oficio(processo: Processo) -> list[tuple[int, int, str]]:
    """(número, ano, onde) de cada citação ao nº/ano do ofício no processo."""
    saida = []
    capa = _numero_ano(processo.capa.get("numero_ano", ""))
    if capa:
        saida.append((*capa, "capa"))
    for doc in processo.documentos:
        dados = doc.dados or {}
        if doc.tipo == tipos.OFICIO and dados.get("numero") and dados.get("ano"):
            saida.append((int(dados["numero"]), int(dados["ano"]), "ofício"))
        elif doc.tipo in (tipos.RT, tipos.DIARIO_BORDO, tipos.JUSTIFICATIVA) and dados.get("oficio_numero") and dados.get("oficio_ano"):
            onde = {tipos.RT: "relatório técnico", tipos.DIARIO_BORDO: "diário de bordo"}.get(doc.tipo, "justificativa")
            saida.append((int(dados["oficio_numero"]), int(dados["oficio_ano"]), onde))
        elif doc.tipo == tipos.DESPACHO:
            m = _RX_OFICIO_NO_TEXTO.search(normalizar(dados.get("assunto", "")))
            if m:
                saida.append((int(m.group(1)), int(m.group(2)), "despacho"))
    return saida


def _cpfs_da_equipe_no_processo(processo: Processo) -> set[str]:
    cpfs = set()
    for doc in processo.documentos:
        if doc.tipo == tipos.OFICIO:
            cpfs.update(doc.dados.get("cpfs") or [])
        elif doc.tipo in (tipos.RT, tipos.TERMO_AUTORIZACAO) and doc.dados.get("cpf"):
            cpfs.add(doc.dados["cpf"])
    return cpfs


def rotulo_do_oficio(oficio) -> str:
    """"Ofício 12/2026 · 26.613.666-8 · 20/09/2026" — para a lista de candidatos."""
    partes = [f"Ofício {oficio.numero_formatado}"]
    if oficio.protocolo:
        partes.append(format_protocolo(oficio.protocolo) or oficio.protocolo)
    if oficio.data_criacao:
        partes.append(oficio.data_criacao.strftime("%d/%m/%Y"))
    return " · ".join(partes)


def _candidatos(processo: Processo, *, incluir: PrestacaoContas | None = None) -> dict[int, Candidato]:
    """Prestações a que o processo pode pertencer, pontuadas pelas três camadas."""
    from viagens_oficios.models import Oficio

    nao_oficiais = Oficio.PROTOCOLO_ORIGENS_NAO_OFICIAIS
    pontos: dict[int, Candidato] = {}
    oficios: dict[int, Oficio] = {}

    def candidato(oficio) -> Candidato | None:
        prestacao = getattr(oficio, "prestacao_contas", None)
        if prestacao is None or oficio.cancelado:
            return None
        if oficio.pk not in pontos:
            pontos[oficio.pk] = Candidato(prestacao_id=prestacao.pk, oficio_id=oficio.pk, rotulo=rotulo_do_oficio(oficio))
            oficios[oficio.pk] = oficio
        return pontos[oficio.pk]

    base = Oficio.objects.select_related("prestacao_contas").filter(cancelado=False)

    # Camada 1: protocolo.
    if processo.protocolo:
        numero = format_protocolo(processo.protocolo) or processo.protocolo
        for oficio in base.filter(protocolo=processo.protocolo):
            c = candidato(oficio)
            if c is None:
                continue
            if oficio.protocolo_origem in nao_oficiais:
                c.pontos += 0.3
                c.fontes.append("protocolo_simulado")
                c.motivos.append(f"protocolo {numero} igual ao do ofício, mas o dele não é oficial")
            else:
                c.pontos += 2.0
                c.fontes.append("protocolo")
                c.motivos.append(f"protocolo {numero} igual ao do ofício")

    # Camada 2: nº/ano do ofício.
    for numero, ano, onde in _referencias_ao_oficio(processo):
        for oficio in base.filter(numero=numero, ano=ano):
            c = candidato(oficio)
            if c is None:
                continue
            fonte = f"numero_ano:{onde}"
            if fonte in c.fontes:
                continue
            c.pontos += _PESO_NUMERO_ANO.get(onde, 0.4)
            c.fontes.append(fonte)
            c.motivos.append(f"Ofício {numero:02d}/{ano} citado {_NO_LUGAR.get(onde, onde)}")

    # Camada 3: CPFs da equipe (só confirma; gera candidato fraco se nada mais achou).
    # A equipe do ofício inclui quem tem termo nele (o PDF pode trazer só termos).
    cpfs = _cpfs_da_equipe_no_processo(processo)
    if cpfs:
        if not pontos:
            from django.db.models import Q

            recentes = (
                base.filter(Q(servidores__cpf__in=cpfs) | Q(servidores_termo_autorizacao__cpf__in=cpfs))
                .distinct().order_by("-data_criacao", "-pk")[:5]
            )
            for oficio in recentes:
                candidato(oficio)
        for oficio_id, c in pontos.items():
            equipe = set(oficios[oficio_id].servidores.values_list("cpf", flat=True))
            equipe |= set(oficios[oficio_id].servidores_termo_autorizacao.values_list("cpf", flat=True))
            achados = sum(1 for cpf in equipe if cpf and cpf in cpfs)
            if achados:
                c.pontos += round(0.6 * min(1.0, achados / max(1, len(equipe))), 2)
                c.fontes.append("equipe")
                c.motivos.append(
                    f"{achados} servidor da equipe achado pelo CPF" if achados == 1
                    else f"{achados} servidores da equipe achados pelo CPF"
                )

    # Camada dos termos: de quem são e quando (o PDF só de termos não traz mais nada).
    cpfs_termos = docs_do_oficio.cpfs_dos_termos(processo)
    if cpfs_termos:
        from .artefatos import servidores_com_termo

        datas = docs_do_oficio.datas_dos_termos(processo)
        for oficio_id, c in pontos.items():
            oficio = oficios[oficio_id]
            com_termo = {s.cpf for s in servidores_com_termo(oficio) if s.cpf}
            if cpfs_termos <= com_termo:
                c.pontos += 0.4
                c.fontes.append("termos")
                c.motivos.append("os termos são de servidores com termo nesta viagem")
            if docs_do_oficio.dentro(datas, *docs_do_oficio.periodo_da_viagem(oficio)):
                c.pontos += 0.4
                c.fontes.append("periodo_termo")
                c.motivos.append("a data dos termos cai no período da viagem")

    # Camada do comprovante avulso: a foto ou o PDF só do comprovante não traz
    # ofício nem protocolo — quem transferiu ou sacou diz de qual prestação é.
    comprovantes = [d for d in processo.documentos if d.tipo == tipos.COMPROVANTE]
    if not pontos and comprovantes:
        for ps, nota, motivos, alertas in _donos_do_comprovante(comprovantes):
            c = candidato(ps.prestacao.oficio)
            if c is None:
                continue
            if nota > c.pontos:
                c.pontos = nota
                c.motivos = motivos
                c.servidor_id = ps.servidor_id
                c.alertas = alertas
            if "comprovante" not in c.fontes:
                c.fontes.append("comprovante")

    if incluir is not None and incluir.oficio_id not in pontos:
        candidato(incluir.oficio)
    return pontos


def _donos_do_comprovante(comprovantes) -> list[tuple[object, float, list[str], list[str]]]:
    """Servidores de prestações abertas que podem ter feito o comprovante, pontuados.

    Casa o CPF mascarado ou o nome (tolerante a truncado e sem acento) com os
    servidores das prestações não finalizadas; o valor não pode passar da diária
    liberada; a data deve caber na liberação/prazo de saque; quem ainda não tem
    comprovante anexado ganha preferência. Devolve (servidor da prestação, pontos,
    motivos, alertas); os alertas são o que pesa contra e impede aplicar sozinho.
    """
    from ..models import PrestacaoServidor
    from ..services import valor_diaria_liberado

    abertos = (
        PrestacaoServidor.objects.filter(finalizada=False, prestacao__oficio__cancelado=False)
        .select_related("servidor", "prestacao__oficio")
    )
    melhores: dict[int, tuple[object, float, list[str], list[str]]] = {}
    for doc in comprovantes:
        dados = doc.dados or {}
        nomes = list(dict.fromkeys(n for n in [dados.get("nome"), dados.get("favorecido"), *dados.get("nomes", [])] if n))
        meio, pontas = dados.get("cpf_meio", ""), dados.get("cpf_pontas", "")
        valor, dia = dados.get("valor"), dados.get("data")
        for ps in abertos:
            cpf = ps.servidor.cpf or ""
            por_cpf = len(cpf) == 11 and ((meio and cpf[3:9] == meio) or (pontas and cpf[:3] + cpf[9:] == pontas))
            nota_nome = max((semelhanca_nome(n, ps.servidor.nome) for n in nomes), default=0.0)
            if not por_cpf and nota_nome < NOME_CASA:
                continue
            nota, motivos, alertas = 0.0, [], []
            if por_cpf:
                nota += 1.0
                motivos.append(f"CPF mascarado do comprovante confere com {ps.servidor.nome}")
            if nota_nome >= NOME_CASA:
                nota += 0.8 * nota_nome
                motivos.append(f"nome no comprovante confere com {ps.servidor.nome}")
            # Valor e data só pesam: o cadastro pode estar incompleto (diária
            # não calculada, liberação não informada) e nem por isso o
            # comprovante deixa de ser dele.
            if valor is not None:
                try:
                    liberado = valor_diaria_liberado(ps)
                except Exception:  # roteiro incompleto: sem teto
                    liberado = None
                if liberado:
                    if valor > liberado + Decimal("0.01"):
                        nota -= 0.4
                        alertas.append("valor acima da diária liberada")
                    else:
                        nota += 0.3
                        if liberado - valor < 1:
                            nota += 0.2
                            motivos.append("valor igual ao da diária liberada")
                        else:
                            motivos.append("valor dentro da diária liberada")
            if dia is not None:
                criado = ps.prestacao.oficio.data_criacao
                if criado and dia < criado - timedelta(days=60):
                    nota -= 0.5
                    alertas.append("data bem anterior ao ofício")
                if ps.data_liberacao_diarias:
                    if dia < ps.data_liberacao_diarias:
                        nota -= 0.3
                        alertas.append("data anterior à liberação das diárias")
                    else:
                        nota += 0.3
                        if not ps.prazo_limite_saque or dia <= ps.prazo_limite_saque:
                            nota += 0.2
                            motivos.append("data dentro do prazo de saque")
            if not ps.documentos_anexos.filter(tipo=Anexo.TIPO_COMPROVANTE).exists():
                nota += 0.3
                motivos.append("ainda sem comprovante anexado")
            atual = melhores.get(ps.pk)
            if atual is None or nota > atual[1]:
                melhores[ps.pk] = (ps, round(max(nota, 0.05), 2), motivos + [f"{a} — confira" for a in alertas], alertas)
    return sorted(melhores.values(), key=lambda item: -item[1])


def _candidatos_termo_avulso(processo: Processo) -> list[Candidato]:
    """Termos do cadastro sem ofício que os termos do PDF apontam (CPF e data)."""
    from viagens_termos.models import TermoAutorizacao

    cpfs = docs_do_oficio.cpfs_dos_termos(processo)
    if not cpfs:
        return []
    datas = docs_do_oficio.datas_dos_termos(processo)
    saida = []
    consulta = (
        TermoAutorizacao.objects.filter(oficio__isnull=True, cancelado=False, servidores__cpf__in=cpfs)
        .distinct().order_by("-data_evento_inicio", "-pk")[:5]
    )
    for termo in consulta:
        equipe = {s.cpf for s in termo.servidores_efetivos() if s.cpf}
        achados = len(cpfs & equipe)
        c = Candidato(prestacao_id=None, oficio_id=None, rotulo=docs_do_oficio.rotulo_do_termo(termo), termo_id=termo.pk)
        c.pontos += round(0.6 * min(1.0, achados / max(1, len(equipe))), 2)
        c.fontes.append("equipe")
        c.motivos.append(f"{achados} servidor do termo achado pelo CPF" if achados == 1 else f"{achados} servidores do termo achados pelo CPF")
        if cpfs <= equipe:
            c.pontos += 0.4
            c.fontes.append("termos")
            c.motivos.append("os termos são de servidores deste termo")
        if docs_do_oficio.dentro(datas, *termo.periodo_efetivo()):
            c.pontos += 0.4
            c.fontes.append("periodo_termo")
            c.motivos.append("a data dos termos cai no período do termo")
        saida.append(c)
    return saida


def _so_termos_seguros(lider: Candidato, ranking: list[Candidato]) -> bool:
    """PDF só de termos: todos do grupo de termo do líder, na data da viagem dele, e de mais ninguém."""
    precisa = {"termos", "periodo_termo"}
    if not precisa <= set(lider.fontes):
        return False
    return not any(c is not lider and precisa <= set(c.fontes) for c in ranking)


def _conflitos(processo: Processo, oficio) -> list[str]:
    """Citações fortes (capa, ofício) a outro nº/ano que não o do ofício escolhido."""
    saida = []
    for numero, ano, onde in _referencias_ao_oficio(processo):
        if onde in ("capa", "ofício") and (numero, ano) != (oficio.numero, oficio.ano):
            saida.append(f"O processo cita o Ofício {numero:02d}/{ano} {_NO_LUGAR.get(onde, onde)}, e a prestação é do Ofício {oficio.numero_formatado}.")
    return list(dict.fromkeys(saida))


def _prestacao_do_termo(termo) -> PrestacaoContas | None:
    """A prestação do ofício do termo do cadastro (None no termo avulso ou de ofício cancelado)."""
    if termo is None or not termo.oficio_id or termo.oficio.cancelado:
        return None
    return PrestacaoContas.objects.select_related("oficio").filter(oficio_id=termo.oficio_id).first()


def _concorrente_forte(ranking: list[Candidato], *, fora) -> Candidato | None:
    """O melhor candidato de outro registro com sinal forte (protocolo, nº/ano da capa ou do ofício)."""
    return next(
        (c for c in ranking if not fora(c) and c.pontos >= 1.5 and set(c.fontes) & _FONTES_FORTES),
        None,
    )


#: A evidência de quem veio pelo ⋮ de um registro, conforme a lista.
_ESCOLHIDO_NA_LISTA = {"oficios": "ofício escolhido na lista", "termos": "termo escolhido na lista"}


def _identificar(
    processo: Processo, *, prestacao_fixa: PrestacaoContas | None, termo_fixo=None, origem: str = "prestacoes",
) -> _Identificacao:
    if termo_fixo is not None and prestacao_fixa is None:
        prestacao_fixa = _prestacao_do_termo(termo_fixo)
    pontuados = _candidatos(processo, incluir=prestacao_fixa)
    # Termo avulso só concorre quando nada aponta um ofício com força (PDF só de termos).
    avulsos = [] if any(set(c.fontes) & _FONTES_FORTES for c in pontuados.values()) else _candidatos_termo_avulso(processo)
    ranking = sorted(
        [*pontuados.values(), *avulsos],
        key=lambda c: (-c.pontos, -(c.oficio_id or 0), -(c.termo_id or 0)),
    )
    resultado = _Identificacao(
        termo=termo_fixo,
        candidatos=[
            c for c in ranking
            if c.pontos > 0 or (prestacao_fixa and c.prestacao_id == prestacao_fixa.pk)
        ],
    )

    if termo_fixo is not None and prestacao_fixa is None:
        # Veio do ⋮ de um termo avulso (sem ofício): o termo é o escolhido, sem prestação.
        resultado.camada = "escolhida"
        escolhido = next((c for c in avulsos if c.termo_id == termo_fixo.pk), None)
        resultado.evidencias = ["termo escolhido na lista"] + (escolhido.motivos if escolhido else [])
        concorrente = _concorrente_forte(ranking, fora=lambda c: c.termo_id == termo_fixo.pk)
        if concorrente is not None:
            resultado.avisos.append(
                f"Este processo parece ser do {concorrente.rotulo} ({'; '.join(concorrente.motivos)}). "
                "Confira antes de aplicar."
            )
        resultado.segura = not resultado.avisos
        return resultado

    if prestacao_fixa is not None:
        # Veio do ⋮ do ofício (ou de um termo preso a ele): a prestação é a
        # escolhida. Só se desconfia se o processo aponta, com força, para outro ofício.
        resultado.prestacao = prestacao_fixa
        resultado.camada = "escolhida"
        escolhido = pontuados.get(prestacao_fixa.oficio_id)
        escolha = "termo escolhido na lista" if termo_fixo is not None else _ESCOLHIDO_NA_LISTA.get(origem, "prestação escolhida na lista")
        resultado.evidencias = [escolha] + (escolhido.motivos if escolhido else [])
        concorrente = _concorrente_forte(ranking, fora=lambda c: c.prestacao_id == prestacao_fixa.pk)
        conflitos = _conflitos(processo, prestacao_fixa.oficio)
        if concorrente is not None and (escolhido is None or concorrente.pontos > escolhido.pontos):
            resultado.avisos.append(
                f"Este processo parece ser do {concorrente.rotulo} ({'; '.join(concorrente.motivos)}). "
                "Confira antes de aplicar."
            )
        resultado.avisos.extend(conflitos)
        resultado.segura = not resultado.avisos
        return resultado

    if not ranking or ranking[0].pontos <= 0:
        nomes = [
            n for d in processo.documentos if d.tipo == tipos.COMPROVANTE
            for n in dict.fromkeys([(d.dados or {}).get("nome"), *(d.dados or {}).get("nomes", [])]) if n
        ]
        if nomes:
            resultado.avisos.append(
                "Nenhuma prestação aberta tem servidor com o nome do comprovante "
                f"({', '.join(dict.fromkeys(nomes))}): escolha o ofício."
            )
        else:
            resultado.avisos.append(
                "Não foi possível descobrir de qual prestação é este processo: escolha o ofício."
            )
        return resultado

    lider = ranking[0]
    segundo = ranking[1] if len(ranking) > 1 else None
    fortes = set(lider.fontes) & _FONTES_FORTES
    independentes = set(lider.fontes) - {"protocolo_simulado"}
    folga = lider.pontos - (segundo.pontos if segundo else 0.0)
    so_termos = _so_termos_seguros(lider, ranking)
    resultado.evidencias = list(lider.motivos)

    if lider.prestacao_id is None:
        # Termo avulso: os termos do PDF são de um termo do cadastro sem ofício.
        from viagens_termos.models import TermoAutorizacao

        resultado.termo = TermoAutorizacao.objects.get(pk=lider.termo_id)
        resultado.camada = "termos"
        resultado.segura = so_termos
        if not resultado.segura:
            resultado.avisos.append("Achado só pelos servidores dos termos: confira de qual termo é este PDF.")
        return resultado

    resultado.prestacao = PrestacaoContas.objects.select_related("oficio").get(pk=lider.prestacao_id)
    resultado.camada = (
        "protocolo" if "protocolo" in lider.fontes
        else "numero_ano" if any(f.startswith("numero_ano:") for f in lider.fontes)
        else "termos" if so_termos
        else "equipe"
    )
    conflitos = _conflitos(processo, resultado.prestacao.oficio)
    resultado.avisos.extend(conflitos)
    if "comprovante" in lider.fontes and not fortes:
        # Só comprovante(s): aplica sozinho quando o dono não deixa dúvida.
        so_comprovantes = all(d.tipo == tipos.COMPROVANTE for d in processo.documentos)
        resultado.camada = "comprovante"
        motivo = _duvida_do_comprovante(lider, ranking[1:])
        resultado.segura = so_comprovantes and not conflitos and not motivo
        if not resultado.segura:
            resultado.avisos.append(
                f"Achado pelo comprovante, mas {motivo}: confira a prestação antes de aplicar." if motivo
                else "Achado pelo comprovante (nome, valor e data): confira a prestação antes de aplicar."
            )
        return resultado
    resultado.segura = (
        (bool(fortes) and len(independentes) >= 2 and folga >= 1.0) or (so_termos and not fortes)
    ) and not conflitos
    if not resultado.segura:
        if segundo and folga < 1.0 and not so_termos:
            resultado.avisos.append("O processo combina com mais de uma prestação: confira qual é a certa.")
        elif not fortes:
            resultado.avisos.append(
                "Achado só pelos servidores da equipe (sem protocolo nem nº do ofício): confira a prestação."
            )
        elif len(independentes) < 2:
            resultado.avisos.append("Só um sinal aponta esta prestação: confira antes de aplicar.")
    return resultado


#: Pontos mínimos do dono do comprovante: o nome sozinho, quando confere bem
#: (0,8 × nota ≥ 0,7), ou o nome parcial somado a valor ou data que batem.
DONO_MINIMO = 0.7
#: Folga sobre outro servidor com nome parecido.
FOLGA_OUTRO_SERVIDOR = 0.5
#: Folga entre duas viagens abertas do mesmo servidor: precisa de valor ou data
#: (só "ainda sem comprovante" não basta para escolher a viagem).
FOLGA_MESMO_SERVIDOR = 0.4


def _duvida_do_comprovante(lider: Candidato, outros: list[Candidato]) -> str:
    """Por que não aplicar sozinho o comprovante no `lider` ("" = sem dúvida)."""
    if lider.alertas:
        return " e ".join(lider.alertas)
    if lider.pontos < DONO_MINIMO:
        return "o nome confere só em parte e nem valor nem data confirmam"
    outro = next((c for c in outros if c.servidor_id != lider.servidor_id), None)
    if outro is not None and lider.pontos - outro.pontos < FOLGA_OUTRO_SERVIDOR:
        return f"o nome também combina com o {outro.rotulo}"
    mesmo = next((c for c in outros if c.servidor_id == lider.servidor_id), None)
    if mesmo is not None and lider.pontos - mesmo.pontos < FOLGA_MESMO_SERVIDOR:
        return f"o servidor também tem o {mesmo.rotulo} aberto e valor e data não decidem"
    return ""


def _protocolo_para_gravar(processo: Processo, oficio) -> str:
    """O protocolo real lido, quando o ofício está sem protocolo oficial e o número é só dele."""
    from viagens_oficios.models import Oficio

    lido = processo.protocolo
    if not lido or not processo.eh_eprotocolo or lido == (oficio.protocolo or ""):
        return ""
    oficial = bool(oficio.protocolo) and oficio.protocolo_origem not in Oficio.PROTOCOLO_ORIGENS_NAO_OFICIAIS
    if oficial:
        return ""
    de_outro = (
        Oficio.objects.filter(protocolo=lido, cancelado=False)
        .exclude(pk=oficio.pk)
        .exclude(protocolo_origem__in=Oficio.PROTOCOLO_ORIGENS_NAO_OFICIAIS)
        .exists()
    )
    return "" if de_outro else lido


# ─────────────────────────────────────────────────────────────────
# Servidor de cada documento
# ─────────────────────────────────────────────────────────────────

@dataclass
class _Membro:
    ps: object
    nome: str
    cpf: str
    liberado: object = None


def _equipe(prestacao) -> list[_Membro]:
    from ..services import valor_diaria_liberado

    if prestacao is None:
        return []
    membros = []
    for ps in prestacao.servidores_prestacao.select_related("servidor").order_by("pk"):
        try:
            liberado = valor_diaria_liberado(ps)
        except Exception:  # roteiro incompleto: sem teto, sem bônus
            liberado = None
        membros.append(_Membro(ps=ps, nome=ps.servidor.nome, cpf=(ps.servidor.cpf or ""), liberado=liberado))
    return membros


def _unico(achados):
    return achados[0] if len(achados) == 1 else None


def _servidor_do_rt(doc, equipe) -> tuple[_Membro | None, list[str]]:
    cpf = (doc.dados or {}).get("cpf", "")
    if cpf:
        membro = _unico([m for m in equipe if m.cpf and m.cpf == cpf])
        if membro:
            return membro, [f"CPF do relatório confere com {membro.nome}"]
    nome = (doc.dados or {}).get("nome", "")
    if nome:
        notas = sorted(((semelhanca_nome(nome, m.nome), m) for m in equipe), key=lambda item: -item[0])
        if notas and notas[0][0] >= 0.95 and (len(notas) == 1 or notas[1][0] < 0.85):
            return notas[0][1], [f"nome do relatório confere com {notas[0][1].nome}"]
    for assinatura in doc.assinaturas:
        if assinatura.cpf_meio:
            membro = _unico([m for m in equipe if m.cpf and m.cpf[3:9] == assinatura.cpf_meio])
            if membro and semelhanca_nome(assinatura.nome, membro.nome) >= NOME_CASA:
                return membro, [f"assinado no eProtocolo por {membro.nome}"]
    return None, []


def _servidor_do_comprovante(doc, equipe) -> tuple[_Membro | None, list[str], bool]:
    """(membro, evidências, certo). `certo` = CPF mascarado ou nome batem só com ele."""
    dados = doc.dados or {}
    notas: dict[int, float] = {id(m): 0.0 for m in equipe}
    motivos: dict[int, list[str]] = {id(m): [] for m in equipe}
    certeza: dict[int, bool] = {id(m): False for m in equipe}

    meio, pontas = dados.get("cpf_meio", ""), dados.get("cpf_pontas", "")
    if meio or pontas:
        por_cpf = [
            m for m in equipe
            if len(m.cpf) == 11 and ((meio and m.cpf[3:9] == meio) or (pontas and m.cpf[:3] + m.cpf[9:] == pontas))
        ]
        if len(por_cpf) == 1:
            notas[id(por_cpf[0])] += 0.6
            certeza[id(por_cpf[0])] = True
            motivos[id(por_cpf[0])].append("CPF mascarado confere")
    nomes = list(dict.fromkeys(n for n in [dados.get("nome"), dados.get("favorecido"), *dados.get("nomes", [])] if n))
    if nomes:
        def nota_do_nome(m):
            return max(semelhanca_nome(n, m.nome) for n in nomes)

        for m in equipe:
            nota = nota_do_nome(m)
            if nota >= NOME_CASA:
                notas[id(m)] += 0.4 * nota
                motivos[id(m)].append("nome no comprovante confere")
        casados = [m for m in equipe if nota_do_nome(m) >= NOME_CASA]
        if len(casados) == 1:
            certeza[id(casados[0])] = True
    # Na falta de CPF e nome: quem inseriu ou assinou o comprovante no eProtocolo.
    quem = [doc.inserido_por] + [a.nome for a in doc.assinaturas]
    for m in equipe:
        if any(q and semelhanca_nome(q, m.nome) >= NOME_CASA for q in quem):
            notas[id(m)] += 0.3
            motivos[id(m)].append("inserido/assinado no eProtocolo por ele(a)")
    valor = dados.get("valor")
    for m in equipe:
        if valor is not None and m.liberado is not None:
            if valor > m.liberado:
                # Só desempata: a diária calculada pode estar desatualizada.
                notas[id(m)] -= 0.05
            elif notas[id(m)] > 0:
                notas[id(m)] += 0.05

    ordenados = sorted(equipe, key=lambda m: -notas[id(m)])
    if not ordenados or notas[id(ordenados[0])] < 0.3:
        return None, [], False
    lider = ordenados[0]
    segundo = notas[id(ordenados[1])] if len(ordenados) > 1 else 0.0
    if notas[id(lider)] - segundo < 0.2:
        return None, [], False
    return lider, motivos[id(lider)], certeza[id(lider)]


# ─────────────────────────────────────────────────────────────────
# Destino de cada documento
# ─────────────────────────────────────────────────────────────────

def _rotacoes(doc, processo: Processo, *, paisagem: bool) -> tuple[dict[str, int], dict[str, int], bool]:
    """(/Rotate final por página, /Rotate original por página, alguma ficou sem saber)."""
    finais, originais, incerta = {}, {}, False
    for indice in doc.paginas:
        pagina = processo.paginas[indice]
        originais[str(indice)] = pagina.rotacao
        if indice in doc.folhas_assinatura:
            finais[str(indice)] = pagina.rotacao
            continue
        rotacao = rotacao_para_ficar_em_pe(pagina)
        if rotacao is None:
            rotacao = pagina.rotacao
            if paisagem:
                incerta = True
                if not fica_em_paisagem(pagina, rotacao):
                    rotacao = (rotacao + 90) % 360
        finais[str(indice)] = rotacao
    return finais, originais, incerta


def _sem_texto(doc, processo: Processo) -> bool:
    conteudo = doc.paginas_de_conteudo or doc.paginas
    return all(processo.paginas[i].sem_texto and not processo.paginas[i].ocr for i in conteudo)


def _data_plausivel(dia: date, oficio) -> bool:
    hoje = timezone.localdate()
    if dia > hoje + timedelta(days=1):
        return False
    inicio = getattr(oficio, "data_criacao", None)
    return not inicio or dia >= inicio - timedelta(days=120)


def _reais(valor) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _frase_da_divergencia(divergencias) -> str:
    nomes = {"valor": "o valor", "data": "a data"}
    partes = []
    for chave, primeira, segunda in divergencias:
        if chave == "valor":
            partes.append(f"o valor ({_reais(primeira)} ou {_reais(segunda)})")
        elif chave == "data":
            partes.append(f"a data ({primeira:%d/%m/%Y} ou {segunda:%d/%m/%Y})")
        else:
            partes.append(nomes.get(chave, chave))
    return "As duas leituras da foto não deram o mesmo resultado para " + " e ".join(partes) + ": confira."


def _ja_anexado(ps, item) -> bool:
    """O servidor já tem comprovante com este valor e esta data."""
    valor, dia = item.valor_decimal, item.data_operacao
    if valor is None or dia is None:
        return False
    return ps.documentos_anexos.filter(tipo=Anexo.TIPO_COMPROVANTE, valor=valor, data_operacao=dia).exists()


def _itens(processo: Processo, prestacao) -> list[ItemPlano]:
    oficio = prestacao.oficio if prestacao is not None else None
    equipe = _equipe(prestacao)
    itens: list[ItemPlano] = []
    oficio_ja = False
    # Só comprovantes (a foto do WhatsApp): eles se somam aos já anexados, então o
    # que já está lá (mesmo servidor, valor e data) não entra de novo.
    so_comprovantes = bool(processo.documentos) and all(d.tipo == tipos.COMPROVANTE for d in processo.documentos)

    for doc in processo.documentos:
        dados = doc.dados or {}
        paisagem = doc.tipo == tipos.DIARIO_BORDO
        rotacoes, originais, incerta = _rotacoes(doc, processo, paisagem=paisagem)
        item = ItemPlano(
            ordem=doc.ordem,
            paginas=list(doc.paginas),
            titulo=doc.titulo or "",
            tipo_lido=doc.tipo,
            rotulo=tipos.ROTULOS.get(doc.tipo, "Documento"),
            confianca=float(doc.confianca or 0.0),
            rotacoes=rotacoes,
            rotacoes_originais=originais,
            rotacao_incerta=incerta,
            assinado=bool(doc.assinaturas),
            assinado_por=list(dict.fromkeys(a.nome for a in doc.assinaturas if a.nome))[:3],
            sem_texto=_sem_texto(doc, processo),
            evidencias=list(doc.evidencias)[:4],
        )
        folhas = descrever_paginas(doc.paginas)

        if doc.tipo in _FORA_DA_PRESTACAO:
            item.destino, item.motivo = IGNORAR, _FORA_DA_PRESTACAO[doc.tipo]
        elif doc.tipo in DESTINO_DO_TIPO:
            item.destino = DESTINO_DO_TIPO[doc.tipo]
        elif doc.tipo == tipos.DESCONHECIDO:
            item.destino = ""
            item.conferir.append(
                "Página só de imagem, sem leitura do texto: diga o que é." if item.sem_texto
                else "Não foi possível identificar o documento: diga o que é."
            )
        else:
            item.destino = IGNORAR
            item.motivo = f"{item.rotulo}: não faz parte da prestação de Viagens."

        if item.destino in DESTINO_DO_TIPO.values() and item.confianca < CONFIANCA_MINIMA:
            item.conferir.append("Tipo identificado com pouca certeza: confira.")

        if item.destino == Anexo.TIPO_OFICIO_ASSINADO:
            numero, ano = dados.get("numero"), dados.get("ano")
            if oficio is not None and numero and ano and (numero, ano) != (oficio.numero, oficio.ano):
                item.conferir.append(f"Este é o Ofício {numero:02d}/{ano}, não o da prestação ({oficio.numero_formatado}).")
            if oficio_ja:
                item.conferir.append("Há mais de um ofício no processo: escolha qual entra.")
            oficio_ja = True
        elif item.destino == Anexo.TIPO_RT_ASSINADO:
            membro, evidencias = _servidor_do_rt(doc, equipe)
            if membro:
                item.servidor_prestacao_id = membro.ps.pk
                item.evidencias = evidencias  # de quem é: o que a tela mostra
            elif prestacao is not None:
                item.conferir.append("Não foi possível saber de qual servidor é o relatório: escolha.")
        elif item.destino == Anexo.TIPO_DB_ASSINADO:
            if incerta:
                item.conferir.append("Página do diário sem texto: confira a orientação (↺ ↻).")
        elif item.destino == Anexo.TIPO_COMPROVANTE:
            membro, evidencias, certo = _servidor_do_comprovante(doc, equipe)
            if membro:
                item.servidor_prestacao_id = membro.ps.pk
                item.evidencias = evidencias  # de quem é: o que a tela mostra
                if not certo:
                    item.conferir.append(f"Comprovante atribuído a {membro.nome} só por indícios: confira.")
            elif prestacao is not None:
                item.conferir.append("Não foi possível saber de quem é o comprovante: escolha o servidor.")
            valor, dia = dados.get("valor"), dados.get("data")
            item.valor = str(valor) if valor is not None else ""
            item.data = dia.isoformat() if isinstance(dia, date) else ""
            item.operacao = dados.get("operacao", "")
            if item.sem_texto:
                item.conferir.append("Comprovante só de imagem: informe o valor e a data.")
            else:
                if valor is None:
                    item.conferir.append("Valor não encontrado no comprovante: informe.")
                if not isinstance(dia, date):
                    item.conferir.append("Data da operação não encontrada: informe.")
                elif oficio is not None and not _data_plausivel(dia, oficio):
                    item.conferir.append("Data da operação fora do período esperado: confira.")
            if membro and valor is not None and membro.liberado is not None and valor > membro.liberado:
                item.conferir.append(f"Valor maior que a diária liberada para {membro.nome}: confira.")
            if dados.get("leituras") == "divergem":
                item.conferir.append(_frase_da_divergencia(dados.get("divergencias") or []))
            elif dados.get("leituras") == "conferem":
                item.evidencias.append("valor e data iguais nas duas leituras da foto")
            if so_comprovantes and membro and _ja_anexado(membro.ps, item):
                item.destino, item.duplicado, item.conferir = IGNORAR, True, []
                item.motivo = f"Já está na prestação: comprovante de {membro.nome} de {_reais(item.valor_decimal)} em {item.data_operacao:%d/%m/%Y}."

        if item.rotacao_incerta and item.destino != Anexo.TIPO_DB_ASSINADO and item.entra and item.sem_texto:
            item.conferir.append("Página só de imagem: confira a orientação (↺ ↻).")
        if not item.motivo and (item.entra or item.destino in DESTINO_DO_TIPO.values()):
            item.motivo = f"Folhas {folhas}" if folhas else ""
        itens.append(item)

    return itens


def _documentos_do_oficio(itens: list[ItemPlano], processo: Processo, *, prestacao, termo, origem: str) -> None:
    """Justificativa, termos e OS: de quem é cada um e qual documento recebe o assinado.

    Com um termo avulso (sem ofício) escolhido, não há prestação nem ofício: o que
    seria deles fica de fora, com o motivo.
    """
    from .artefatos import servidores_com_termo

    oficio = prestacao.oficio if prestacao is not None else None
    documentos = {doc.ordem: doc for doc in processo.documentos}
    servidores = servidores_com_termo(oficio, termo) if (oficio is not None or termo is not None) else []
    # Páginas só de imagem viram termos só num PDF solto (os termos escaneados juntos)
    # vindo da lista de Termos; no volume do eProtocolo, a imagem pode ser qualquer coisa.
    termos_escaneados = (origem == "termos" or termo is not None) and not processo.eh_eprotocolo
    termos_por_servidor: dict[int, ItemPlano] = {}
    imagens: list[ItemPlano] = []
    justificativa_ja = False

    for item in itens:
        doc = documentos[item.ordem]
        if prestacao is None and termo is not None and (item.entra or item.destino == DESTINO_JUSTIFICATIVA):
            item.destino = IGNORAR
            item.motivo = f"O Termo #{termo.pk} não tem ofício: não há prestação nem ofício para este documento."
            item.conferir = []
            continue
        if item.destino == "" and item.sem_texto and termos_escaneados and servidores:
            # Termos escaneados juntos, sem OCR: a página é um termo; de quem, a conferência diz.
            item.destino = DESTINO_TERMO
            item.rotulo = tipos.ROTULOS[tipos.TERMO_AUTORIZACAO]
            item.conferir = ["Termo só de imagem, sem leitura do texto: confira de quem é."]
            imagens.append(item)
            continue

        if item.destino == DESTINO_JUSTIFICATIVA:
            dados = doc.dados or {}
            numero, ano = dados.get("oficio_numero"), dados.get("oficio_ano")
            if oficio is not None and numero and ano and (numero, ano) != (oficio.numero, oficio.ano):
                item.conferir.append(f"Esta justificativa cita o Ofício {numero:02d}/{ano}, não o {oficio.numero_formatado}: confira.")
            if justificativa_ja:
                item.conferir.append("Há mais de uma justificativa no processo: escolha qual entra.")
            justificativa_ja = True
        elif item.destino == DESTINO_TERMO:
            servidor, evidencias = docs_do_oficio.servidor_do_termo(doc, servidores)
            if servidor is not None:
                if servidor.pk in termos_por_servidor:
                    item.conferir.append(f"Há mais de um termo de {servidor.nome} no processo: confira qual entra.")
                termos_por_servidor.setdefault(servidor.pk, item)
                item.servidor_id = servidor.pk
                item.evidencias = evidencias
            elif oficio is not None or termo is not None:
                de_fora = docs_do_oficio.quem_e_de_fora(doc)
                if de_fora is not None and oficio is not None:
                    item.conferir.append(
                        f"{de_fora.nome} não está marcado para termo no Ofício {oficio.numero_formatado}: "
                        "marque-o no ofício e importe de novo, ou deixe este termo de fora."
                    )
                elif de_fora is not None:
                    item.conferir.append(f"{de_fora.nome} não é servidor do Termo #{termo.pk}: confira.")
                else:
                    item.conferir.append("Não foi possível saber de quem é o termo: escolha o servidor.")
        elif item.destino == DESTINO_ORDEM_SERVICO:
            ordem, conferir, motivo = docs_do_oficio.ordem_do_documento(doc, oficio)
            if ordem is not None:
                item.ordem_servico_id = ordem.pk
                item.conferir.extend(conferir)
            elif conferir:
                item.conferir.extend(conferir)
            else:
                item.destino, item.motivo = IGNORAR, motivo

    # O servidor das páginas só de imagem: na ordem em que o sistema imprime os termos
    # (por nome), pulando quem já tem o seu termo lido pelo texto.
    livres = [s for s in servidores if s.pk not in termos_por_servidor]
    for item, servidor in zip(imagens, livres):
        item.servidor_id = servidor.pk
        item.evidencias = [f"proposto pela ordem dos termos: {servidor.nome}"]


# ─────────────────────────────────────────────────────────────────
# Entrada
# ─────────────────────────────────────────────────────────────────

def analisar(
    dados: bytes, nome_arquivo: str = "", *, prestacao: PrestacaoContas | None = None, termo=None,
    origem: str = "prestacoes",
) -> Plano:
    """Lê o processo e monta o plano. Não grava nada.

    `prestacao` é a do ⋮ do ofício (já escolhida, das listas de Prestações ou de
    Ofícios); `termo`, a do ⋮ de um termo (lista de Termos) — o termo preso a um
    ofício traz a prestação dele. Sem nenhum dos dois, o registro é descoberto
    pelo conteúdo. `origem` é a lista de onde o processo veio. Levanta
    `core.leitura.pdf.ArquivoIlegivel` se o arquivo não abrir.
    """
    processo = ler_processo(dados, nome_arquivo)
    identificacao = _identificar(processo, prestacao_fixa=prestacao, termo_fixo=termo, origem=origem)
    escolhida = identificacao.prestacao
    termo = identificacao.termo
    itens = _itens(processo, escolhida)
    _documentos_do_oficio(itens, processo, prestacao=escolhida, termo=termo, origem=origem)
    convalidacao = next(
        (doc.dados.get("convalidacao") for doc in processo.documentos if doc.tipo == tipos.OFICIO and "convalidacao" in doc.dados),
        None,
    )
    plano = Plano(
        protocolo=processo.protocolo,
        volume=processo.volume,
        eh_eprotocolo=processo.eh_eprotocolo,
        total_paginas=len(processo.paginas),
        prestacao_id=escolhida.pk if escolhida else None,
        oficio_id=escolhida.oficio_id if escolhida else None,
        oficio_rotulo=rotulo_do_oficio(escolhida.oficio) if escolhida else "",
        camada=identificacao.camada,
        identificacao_segura=identificacao.segura,
        evidencias=identificacao.evidencias,
        candidatos=identificacao.candidatos[:6],
        protocolo_para_gravar=_protocolo_para_gravar(processo, escolhida.oficio) if escolhida else "",
        convalidacao_no_texto=convalidacao,
        itens=itens,
        avisos=list(dict.fromkeys(processo.avisos + identificacao.avisos)),
        termo_id=termo.pk if termo is not None else None,
        termo_rotulo=docs_do_oficio.rotulo_do_termo(termo) if termo is not None else "",
        origem=origem if origem in ORIGENS else "prestacoes",
    )
    if not processo.eh_eprotocolo:
        plano.avisos.insert(0, "O arquivo não parece um volume do eProtocolo: os documentos foram separados pelo conteúdo.")
    return plano
