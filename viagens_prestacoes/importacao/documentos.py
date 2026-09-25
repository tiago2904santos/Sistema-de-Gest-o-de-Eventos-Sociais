"""Análise dos documentos que voltam para o documento gerado: justificativa, termos e OS.

Só lê: acha de quem é cada termo, qual ordem de serviço é a do processo e o que
os termos dizem sobre a viagem (servidores e data), para a identificação de um
PDF que só traz termos. Quem grava é `aplicacao` (via `artefatos`).

**Termo de autorização.** Um por servidor, com "Eu NOME, RG: …, CPF: …". O CPF
completo decide; na falta dele, o RG; por último, o nome (tolerando acento e
abreviação). Só vale quem tem termo nesta viagem (`artefatos.servidores_com_termo`):
achar um CPF de fora da lista vira pergunta, nunca termo gravado no lugar errado.
PDF só de imagem (os termos escaneados), sem OCR: quando o processo veio da lista
de Termos, cada página vira um termo, e o servidor é proposto na ordem em que o
sistema imprime os termos (por nome) — sempre para conferir.

**Ordem de serviço.** Pelo nº/ano do título, entre as OS de Viagens não
canceladas; a vinculada ao ofício do processo vence. OS que não é de Viagens (a
do Coffee Break, por exemplo) fica de fora, com o motivo.

LGPD: CPF, RG e texto não saem daqui; as evidências dizem "CPF do termo confere
com FULANO", sem o número.
"""

from __future__ import annotations

import re
from datetime import date
from datetime import timedelta

from django.utils import timezone

from core.leitura import classificacao as tipos
from core.leitura.texto import achar_datas

__all__ = [
    "datas_dos_termos",
    "cpfs_dos_termos",
    "ordem_do_documento",
    "periodo_da_viagem",
    "quem_e_de_fora",
    "servidor_do_termo",
    "rotulo_do_termo",
]


def _digitos(valor: str) -> str:
    return re.sub(r"[^0-9X]", "", str(valor or "").upper())


def rotulo_do_termo(termo) -> str:
    """"Termo #5 · PONTA GROSSA/PR · 20/09/2026" — para a tela e para os candidatos."""
    partes = [f"Termo #{termo.pk}"]
    destino = termo.destino_efetivo()
    if destino:
        partes.append(destino.upper())
    inicio, fim = termo.periodo_efetivo()
    if inicio:
        partes.append(f"{inicio:%d/%m/%Y}" if not fim or fim == inicio else f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}")
    return " · ".join(partes)


# ─────────────────────────────────────────────────────────────────
# Termos
# ─────────────────────────────────────────────────────────────────

def servidor_do_termo(doc, servidores) -> tuple[object | None, list[str]]:
    """(servidor, evidências) do termo, entre os `servidores` com termo nesta viagem.

    CPF completo, depois RG, depois o nome (≥ 0,95 e sem empate). None se nada
    bate com um só.
    """
    from .analise import semelhanca_nome

    dados = doc.dados or {}
    cpf = dados.get("cpf", "")
    if cpf:
        achados = [s for s in servidores if (s.cpf or "") == cpf]
        if len(achados) == 1:
            return achados[0], [f"CPF do termo confere com {achados[0].nome}"]
    rg = _digitos(dados.get("rg", ""))
    if rg:
        achados = [s for s in servidores if s.rg and _digitos(s.rg) == rg]
        if len(achados) == 1:
            return achados[0], [f"RG do termo confere com {achados[0].nome}"]
    nome = dados.get("nome", "")
    if nome:
        notas = sorted(((semelhanca_nome(nome, s.nome), s) for s in servidores), key=lambda item: -item[0])
        if notas and notas[0][0] >= 0.95 and (len(notas) == 1 or notas[1][0] < 0.85):
            return notas[0][1], [f"nome do termo confere com {notas[0][1].nome}"]
    return None, []


def quem_e_de_fora(doc) -> object | None:
    """O servidor do cadastro com o CPF do termo, quando ele não tem termo nesta viagem (para a pergunta)."""
    from viagens_cadastros.models import Servidor

    cpf = (doc.dados or {}).get("cpf", "")
    if not cpf:
        return None
    return Servidor.objects.filter(cpf=cpf).first()


def cpfs_dos_termos(processo) -> set[str]:
    return {doc.dados["cpf"] for doc in processo.documentos if doc.tipo == tipos.TERMO_AUTORIZACAO and doc.dados.get("cpf")}


def datas_dos_termos(processo) -> list[date]:
    """As datas escritas nos termos ("no dia 20 de setembro de 2026", "nos dias 3 até 5 de…")."""
    saida: list[date] = []
    for doc in processo.documentos:
        if doc.tipo != tipos.TERMO_AUTORIZACAO:
            continue
        texto = "\n".join(processo.paginas[i].corpo or "" for i in doc.paginas_de_conteudo)
        for dia in achar_datas(texto):
            if dia not in saida:
                saida.append(dia)
    return saida


def periodo_da_viagem(oficio) -> tuple[date | None, date | None]:
    """Primeiro e último dia da viagem do ofício (roteiro), em data local."""
    from viagens_oficios.roteiro_context import periodo_roteiro

    saida, retorno = periodo_roteiro(getattr(oficio, "roteiro", None))

    def dia(valor):
        if valor is None:
            return None
        return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()

    inicio, fim = dia(saida), dia(retorno)
    return inicio, fim or inicio


def dentro(datas: list[date], inicio: date | None, fim: date | None, *, folga: int = 1) -> bool:
    if not datas or inicio is None:
        return False
    fim = fim or inicio
    return any(inicio - timedelta(days=folga) <= d <= fim + timedelta(days=folga) for d in datas)


# ─────────────────────────────────────────────────────────────────
# Ordem de serviço
# ─────────────────────────────────────────────────────────────────

def ordem_do_documento(doc, oficio) -> tuple[object | None, list[str], str]:
    """(OS de Viagens, o que conferir, motivo para ficar de fora) do documento.

    Com a OS achada, o motivo vem vazio; sem ela, o documento fica de fora com o
    motivo. OS achada pelo número mas sem vínculo com o ofício do processo vai
    para a conferência.
    """
    from viagens_ordens.models import OrdemServico

    dados = doc.dados or {}
    numero, ano = dados.get("numero"), dados.get("ano")
    base = OrdemServico.objects.filter(cancelado=False)
    vinculadas = list(base.filter(oficios=oficio).order_by("-ano", "-numero", "-pk")) if oficio is not None else []

    if numero:
        anos = [ano] if ano else sorted({d.year for d in (getattr(oficio, "data_criacao", None), timezone.localdate()) if d}, reverse=True)
        achadas = [o for o in vinculadas if o.numero == numero and o.ano in anos]
        if not achadas:
            achadas = list(base.filter(numero=numero, ano__in=anos).order_by("-ano", "-pk"))
        rotulo = f"{numero:02d}/{ano}" if ano else f"{numero:02d}"
        if len(achadas) == 1:
            ordem = achadas[0]
            conferir = []
            if oficio is not None and ordem not in vinculadas:
                conferir.append(f"A Ordem de Serviço {rotulo} não está vinculada ao Ofício {oficio.numero_formatado}: confira.")
            return ordem, conferir, ""
        if len(achadas) > 1:
            return None, [f"Há mais de uma Ordem de Serviço {rotulo} em Viagens: escolha qual."], ""
        return None, [], f"Ordem de Serviço {rotulo}: não está cadastrada em Viagens."
    if len(vinculadas) == 1:
        return vinculadas[0], ["Número da ordem de serviço não lido: confira se é a do ofício."], ""
    return None, [], "Ordem de serviço sem número lido e sem OS vinculada ao ofício."
