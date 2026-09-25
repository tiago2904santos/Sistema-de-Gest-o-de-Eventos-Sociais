"""O que o texto diz, casado com o que o sistema conhece.

Município, cadastros (tipo de evento, serviço, tema…) por nome ou sinônimo,
telefone, protocolo do eProtocolo e quantidade de pessoas. Cada resposta é
um `Achado` com o valor, o texto para exibir, o trecho de onde saiu e a
confiança — "A" (tem âncora: "município de X", "protocolo nº"), "M"
(preenche e destaca para conferência) ou "B" (só sugestão).

Passe só o corpo da mensagem (sem assinatura, rodapé e citações): o
endereço da PCPR em Curitiba na assinatura casaria sempre.

Nada aqui grava. Só o município (quando não se passa a lista) consulta o
banco, e só para ler os ativos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from core.utils.masks import format_protocolo, format_telefone, validar_cpf_digitos

from .datas import _Ocupados, dobrar

__all__ = [
    "Achado",
    "MUNICIPIOS_AMBIGUOS",
    "UF_DO_DDD",
    "cadastro_no_texto",
    "cadastros_no_texto",
    "municipio_no_texto",
    "municipios_no_texto",
    "protocolo_no_texto",
    "quantidade_de_pessoas",
    "quantidade_no_texto",
    "telefone_no_texto",
    "telefones_no_texto",
]


@dataclass(frozen=True)
class Achado:
    """Um valor achado no texto, pronto para a tela conferir.

    `valor` é o que vai para o campo (objeto do cadastro, texto ou número);
    `exibir`, como mostrar; `trecho`, de onde saiu; `confianca`, "A", "M"
    ou "B"; `detalhes`, o que mais se soube (UF, ramal, tipo de telefone).
    """

    valor: Any
    exibir: str
    trecho: str
    confianca: str
    detalhes: dict = field(default_factory=dict, compare=False, hash=False)


def _chave(texto: str) -> str:
    """Palavras sem acento, minúsculas, separadas por um espaço."""
    return " ".join(re.findall(r"[a-z0-9]+", dobrar(texto).replace("'", "")))


def _frase(dobrado: str, inicio: int, fim: int) -> tuple[int, int]:
    """Início e fim da frase que contém o trecho (até 400 caracteres para cada lado)."""
    base = max(0, inicio - 400)
    comeco = base
    for m in re.finditer(r"[\n!?;]|\.\s", dobrado[base:inicio]):
        comeco = base + m.end()
    final = re.search(r"[\n!?;]|\.\s|\.$", dobrado[fim:fim + 400])
    return comeco, (fim + final.start() if final else min(len(dobrado), fim + 400))


def _trecho(texto: str, dobrado: str, inicio: int, fim: int, limite: int = 200) -> str:
    comeco, final = _frase(dobrado, inicio, fim)
    trecho = texto[comeco:final].strip()
    if len(trecho) <= limite:
        return trecho
    meio = texto[max(comeco, inicio - limite // 2):min(final, fim + limite // 2)]
    return meio.strip()


# ---------------------------------------------------------------------------
# Município
# ---------------------------------------------------------------------------

UF_DO_DDD = {
    "11": "SP", "12": "SP", "13": "SP", "14": "SP", "15": "SP", "16": "SP", "17": "SP", "18": "SP", "19": "SP",
    "21": "RJ", "22": "RJ", "24": "RJ", "27": "ES", "28": "ES",
    "31": "MG", "32": "MG", "33": "MG", "34": "MG", "35": "MG", "37": "MG", "38": "MG",
    "41": "PR", "42": "PR", "43": "PR", "44": "PR", "45": "PR", "46": "PR",
    "47": "SC", "48": "SC", "49": "SC", "51": "RS", "53": "RS", "54": "RS", "55": "RS",
    "61": "DF", "62": "GO", "63": "TO", "64": "GO", "65": "MT", "66": "MT", "67": "MS", "68": "AC", "69": "RO",
    "71": "BA", "73": "BA", "74": "BA", "75": "BA", "77": "BA", "79": "SE",
    "81": "PE", "82": "AL", "83": "PB", "84": "RN", "85": "CE", "86": "PI", "87": "PE", "88": "CE", "89": "PI",
    "91": "PA", "92": "AM", "93": "PA", "94": "PA", "95": "RR", "96": "AP", "97": "AM", "98": "MA", "99": "MA",
}
_UFS = frozenset(UF_DO_DDD.values())
_UF_POR_NOME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC",
    "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}

# Nomes de município que também são palavra comum, nome de gente ou de rua:
# só valem com âncora ("em Castro", "município de Reserva", "Toledo/PR") e
# escritos com inicial maiúscula.
MUNICIPIOS_AMBIGUOS = frozenset(_chave(n) for n in (
    # os medidos no levantamento (mapas/demandas.md §3.F)
    "Reserva", "Contenda", "Planalto", "Colombo", "Castro", "Toledo", "Palmas", "Pinhão",
    "Nova Esperança", "Bom Sucesso", "Céu Azul", "Lapa", "Pitanga", "Araucária",
    "Francisco Alves", "Assis Chateaubriand", "Jussara",
    # palavra comum
    "Bandeirantes", "Colorado", "Floresta", "Figueira", "Ventania", "Farol", "Turvo", "Palmeira",
    "Realeza", "Barracão", "Sulina", "Fênix", "Mirador", "Atalaia", "Faxinal", "Laranjal", "Palmital",
    "Terra Roxa", "Boa Esperança", "Santa Fé", "Renascença", "Roncador", "Sertaneja", "Marmeleiro",
    "Porto Rico", "Alto Paraná", "Rio Negro", "Rio Azul", "Rio Bom", "Cruzeiro do Sul", "São João",
    "Primeiro de Maio", "Nossa Senhora das Graças", "Salto do Lontra", "Entre Rios do Oeste", "Foz",
    "Campo Largo", "Campo Bonito", "Boa Vista da Aparecida", "Itambé", "Brasília",
    # nome de gente ou de rua
    "Mercedes", "Antonina", "Maria Helena", "Paula Freitas", "Santa Helena", "Santa Inês", "Santa Lúcia",
    "Santa Mônica", "Santa Amélia", "Marilena", "Mariluz", "Anahy", "Vitorino", "Marquinho", "Capanema",
    "Rondon", "Mallet", "Virmond", "Rebouças", "Salgado Filho", "Almirante Tamandaré", "Siqueira Campos",
    "Joaquim Távora", "Wenceslau Braz", "Cornélio Procópio", "Presidente Castelo Branco",
    "Marechal Cândido Rondon", "Francisco Beltrão", "Telêmaco Borba", "Cândido de Abreu", "Teixeira Soares",
    "Fernandes Pinheiro", "Moreira Sales", "Doutor Camargo", "Doutor Ulysses", "Engenheiro Beltrão",
    "Manoel Ribas", "Cruz Machado", "Paulo Frontin", "General Carneiro", "Enéas Marques", "Lunardelli",
    "Prado Ferreira", "Barbosa Ferraz", "Inácio Martins", "Capitão Leônidas Marques", "Coronel Vivida",
    "Coronel Domingos Soares", "Honório Serpa", "Tibagi", "Ivaí", "Guaíra", "Iguatu",
))

# Grafias erradas vistas nas planilhas (solicitacoes/.../importar_planilha.py,
# MUNICIPIO_FIX) e apelidos, para o nome oficial.
_GRAFIAS = {
    "pinhias": "pinhais",
    "santa terezinha do itaipu": "santa terezinha de itaipu",
    "foz": "foz do iguacu",
}

# Âncora antes do nome: "em X", "município de X", "Local: ... - X".
_R_ANCORA_ANTES = re.compile(
    r"(?:\bem|\bno\s+municipio\s+de|\bmunicipio\s+de|\bmunicipio\s*:|\bcidade\s+de|\bcidade\s*:|"
    r"\bcomarca\s+de|\bprefeitura\s+(?:municipal\s+)?de|\bcamara\s+(?:municipal\s+)?de|\bmunicipal\s+de|"
    r"\b(?:local|endereco|onde|localidade)\s*:[^\n]*|\bsediad[oa]\s+em|\brealizad[oa]\s+em|\bde\s+onde|"
    r"\d+\s*[-–,]|\bcep\s*:?\s*\d{5}-?\d{3}\s*[-–,]?)\s*[,:-]?\s*$"
)
# UF logo depois: "Toledo/PR", "Toledo - PR", "Toledo (PR)", "Toledo, Paraná".
_R_UF_DEPOIS = re.compile(r"^\s*(?:/|-|–|,|\()\s*([A-Za-z]{2})\b\)?")
_R_ESTADO_DEPOIS = re.compile(r"^\s*(?:/|-|–|,|\()\s*(" + "|".join(sorted(_UF_POR_NOME, key=len, reverse=True)) + r")\b")
# Rua, escola, bairro com nome de cidade: "Rua Curitiba", "Colégio Estadual Castro Alves".
_R_LOGRADOURO_ANTES = re.compile(
    r"\b(?:rua|r\.|av\.?|avenida|travessa|tv\.|alameda|al\.|praca|rodovia|estrada|largo|edificio|ed\.|"
    r"condominio|residencial|jardim|jd\.?|vila|bairro|conjunto|parque|loteamento|colegio|escola|"
    r"e\.\s?e\.|c\.\s?e\.|instituto|hotel|clube|shopping)"
    r"(?:\s+(?:estadual|municipal|federal|particular))?\s*$"
)
_R_EVENTO = re.compile(
    r"\b(?:realiz|sera\b|ocorre|acontec|evento|palestra|encontro|reuniao|solenidade|cerimonia|acao\b|"
    r"feira|atendimento|visita|curso|formatura|entrega|local\b|endereco)"
)


class _IndiceMunicipios:
    """Nomes (e variações) dos municípios, sem acento, para achar no texto."""

    def __init__(self, municipios: Iterable):
        self.por_chave: dict[str, list] = {}
        for municipio in municipios:
            for chave in self._variacoes(_chave(municipio.nome)):
                self.por_chave.setdefault(chave, []).append(municipio)
        for errada, certa in _GRAFIAS.items():
            if certa in self.por_chave and errada not in self.por_chave:
                self.por_chave[errada] = self.por_chave[certa]
        self.maior = max((len(c.split()) for c in self.por_chave), default=0)

    @staticmethod
    def _variacoes(chave: str) -> set[str]:
        variacoes = {chave}
        if "doeste" in chave.split():
            # "Diamante D'Oeste" também se escreve "d'Oeste", "do Oeste".
            variacoes |= {chave.replace("doeste", "d oeste"), chave.replace("doeste", "do oeste")}
        for longo, curto in (("santa ", "sta "), ("santo ", "sto "), ("sao ", "s ")):
            for v in list(variacoes):
                if v.startswith(longo):
                    variacoes.add(curto + v[len(longo):])
        return variacoes


def _palavras(dobrado: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[a-z0-9]+", dobrado)]


def _municipios_citados(texto: str, indice: _IndiceMunicipios):
    """(chave, início, fim) de cada nome de município no texto, o mais longo primeiro."""
    dobrado = dobrar(texto)
    palavras = _palavras(dobrado)
    # Duas palavras só formam um nome se entre elas houver espaço, hífen ou apóstrofo.
    junta = [
        bool(re.fullmatch(r"[\s'.-]{1,3}", dobrado[a[2]:b[1]])) for a, b in zip(palavras, palavras[1:])
    ]
    i = 0
    while i < len(palavras):
        achou = False
        for n in range(min(indice.maior, len(palavras) - i), 0, -1):
            if n > 1 and not all(junta[i:i + n - 1]):
                continue
            chave = " ".join(p[0] for p in palavras[i:i + n])
            if chave in indice.por_chave:
                yield chave, palavras[i][1], palavras[i + n - 1][2]
                i += n
                achou = True
                break
        if not achou:
            i += 1


def _uf_do_municipio(municipio) -> str:
    estado = getattr(municipio, "estado", None)
    return (getattr(estado, "sigla", "") or "").upper()


def municipios_no_texto(
    texto: str, municipios: Iterable | None = None, *, uf_preferida: str = "PR", ddd: str = ""
) -> list[Achado]:
    """Os municípios citados no texto, do mais provável ao menos provável.

    Vale o nome mais longo ("São José dos Pinhais" antes de "Pinhais"), sem
    acento e sem diferenciar maiúsculas. Nome ambíguo (`MUNICIPIOS_AMBIGUOS`)
    só com âncora; nome de rua ou de escola ("Rua Curitiba") não conta.
    Nome igual em dois estados: a UF escrita ao lado ("Palmas/TO"), senão a
    do DDD, senão `uf_preferida` (PR).

    `municipios` é a lista (ou queryset) de onde casar; sem ela, os
    municípios ativos do cadastro.
    """
    texto = texto or ""
    if municipios is None:
        from cadastros.models import Municipio

        municipios = Municipio.objects.filter(ativo=True).select_related("estado")
    indice = _IndiceMunicipios(municipios)
    if not indice.por_chave or not texto.strip():
        return []
    dobrado = dobrar(texto)
    uf_do_ddd = UF_DO_DDD.get(re.sub(r"\D", "", ddd or "")[:2], "")
    candidatos: dict[str, dict] = {}
    for chave, inicio, fim in _municipios_citados(texto, indice):
        antes = dobrado[max(0, inicio - 60):inicio]
        comeco_linha = dobrado.rfind("\n", 0, inicio) + 1
        antes = antes[max(0, len(antes) - (inicio - comeco_linha)):]
        if _R_LOGRADOURO_ANTES.search(antes):
            continue
        uf_escrita = ""
        m = _R_UF_DEPOIS.match(texto[fim:fim + 8])
        if m and m.group(1).isupper() and m.group(1) in _UFS:
            uf_escrita = m.group(1)
        else:
            m = _R_ESTADO_DEPOIS.match(dobrado[fim:fim + 30])
            if m:
                uf_escrita = _UF_POR_NOME[m.group(1)]
        ancorado = bool(uf_escrita) or bool(_R_ANCORA_ANTES.search(antes))
        if chave in MUNICIPIOS_AMBIGUOS or _GRAFIAS.get(chave, chave) in MUNICIPIOS_AMBIGUOS:
            if not ancorado or not texto[inicio:inicio + 1].isupper():
                continue
        comeco, final = _frase(dobrado, inicio, fim)
        opcoes = indice.por_chave[chave]
        escolhido = (
            next((o for o in opcoes if uf_escrita and _uf_do_municipio(o) == uf_escrita), None)
            or next((o for o in opcoes if uf_do_ddd and _uf_do_municipio(o) == uf_do_ddd), None)
            or next((o for o in opcoes if _uf_do_municipio(o) == (uf_preferida or "").upper()), None)
            or (opcoes[0] if not uf_escrita else None)
        )
        if escolhido is None:
            continue
        registro = candidatos.setdefault(
            f"{escolhido.pk}:{_uf_do_municipio(escolhido)}:{escolhido.nome}",
            {"municipio": escolhido, "vezes": 0, "ancorado": False, "evento": False,
             "inicio": inicio, "trecho": _trecho(texto, dobrado, inicio, fim)},
        )
        registro["vezes"] += 1
        if ancorado and not registro["ancorado"]:
            registro["trecho"] = _trecho(texto, dobrado, inicio, fim)
        registro["ancorado"] |= ancorado
        registro["evento"] |= bool(_R_EVENTO.search(dobrado[comeco:final]))

    def pontos(r):
        return 3 * r["ancorado"] + min(r["vezes"] - 1, 2) + r["evento"]

    ordenados = sorted(candidatos.values(), key=lambda r: (-pontos(r), r["inicio"]))
    achados = []
    for r in ordenados:
        municipio = r["municipio"]
        uf = _uf_do_municipio(municipio)
        achados.append(Achado(
            valor=municipio,
            exibir=f"{municipio.nome}/{uf}" if uf else municipio.nome,
            trecho=r["trecho"],
            confianca="A" if r["ancorado"] else "M",
            detalhes={"uf": uf},
        ))
    return achados


def municipio_no_texto(
    texto: str, municipios: Iterable | None = None, *, uf_preferida: str = "PR", ddd: str = ""
) -> Achado | None:
    """O município mais provável do texto (ou None). Ver `municipios_no_texto`."""
    achados = municipios_no_texto(texto, municipios, uf_preferida=uf_preferida, ddd=ddd)
    return achados[0] if achados else None


# ---------------------------------------------------------------------------
# Cadastros por nome ou sinônimo
# ---------------------------------------------------------------------------


def _nome_padrao(objeto) -> str:
    return getattr(objeto, "nome", None) or str(objeto)


def cadastros_no_texto(
    texto: str,
    opcoes: Iterable,
    *,
    sinonimos: dict[str, Any] | None = None,
    rotulo: Callable[[Any], str] = _nome_padrao,
) -> list[Achado]:
    """Os cadastros citados no texto pelo nome ou por um sinônimo.

    `opcoes` é o queryset (ou lista) do cadastro. `sinonimos` diz que termo
    aponta para qual cadastro: {"curso": "Capacitação", "jurídic*":
    "Orientação jurídica"} — o valor é o nome do cadastro (ou o próprio
    objeto); "*" no fim casa o começo da palavra. Plural simples ("palestras")
    também casa. Do mais forte (nome mais longo, mais vezes) ao mais fraco.
    """
    texto = texto or ""
    opcoes = list(opcoes)
    por_chave = {_chave(rotulo(o)): o for o in opcoes}
    padroes = [(chave, False, objeto) for chave, objeto in por_chave.items() if chave]
    for termo, alvo in (sinonimos or {}).items():
        objeto = por_chave.get(_chave(alvo)) if isinstance(alvo, str) else alvo
        chave = _chave(termo.rstrip("*"))
        if objeto is not None and chave:
            padroes.append((chave, termo.endswith("*"), objeto))
    padroes.sort(key=lambda p: -len(p[0]))
    dobrado = dobrar(texto)
    ocupados = _Ocupados()
    achados: dict[int, dict] = {}
    for chave, prefixo, objeto in padroes:
        corpo = r"[^a-z0-9]+".join(re.escape(p) for p in chave.split())
        regex = r"(?<![a-z0-9])" + corpo + (r"[a-z0-9]*" if prefixo else r"(?:s|es)?") + r"(?![a-z0-9])"
        for m in re.finditer(regex, dobrado):
            if not ocupados.livre(m.start(), m.end()):
                continue
            ocupados.marcar(m.start(), m.end())
            registro = achados.setdefault(id(objeto), {
                "objeto": objeto, "vezes": 0, "palavras": 0, "inicio": m.start(),
                "trecho": _trecho(texto, dobrado, m.start(), m.end()),
            })
            registro["vezes"] += 1
            registro["palavras"] = max(registro["palavras"], len(chave.split()))
            registro["inicio"] = min(registro["inicio"], m.start())
    ordenados = sorted(achados.values(), key=lambda r: (-(2 * r["palavras"] + r["vezes"]), r["inicio"]))
    return [Achado(r["objeto"], rotulo(r["objeto"]), r["trecho"], "M") for r in ordenados]


def cadastro_no_texto(
    texto: str,
    opcoes: Iterable,
    *,
    sinonimos: dict[str, Any] | None = None,
    padrao: Any = None,
    rotulo: Callable[[Any], str] = _nome_padrao,
) -> Achado | None:
    """O cadastro mais forte citado no texto; na falta, `padrao` (confiança "B")."""
    opcoes = list(opcoes)
    achados = cadastros_no_texto(texto, opcoes, sinonimos=sinonimos, rotulo=rotulo)
    if achados:
        return achados[0]
    if isinstance(padrao, str):
        padrao = next((o for o in opcoes if _chave(rotulo(o)) == _chave(padrao)), None)
    return Achado(padrao, rotulo(padrao), "", "B") if padrao is not None else None


# ---------------------------------------------------------------------------
# Telefone
# ---------------------------------------------------------------------------

_R_TELEFONE = re.compile(
    r"(?<![\d.,/-])(?:\+\s?55\s?[-.]?\s?|55\s(?=\(?\d{2}))?"
    r"(?:\(\s*0?(?P<ddd1>\d{2})\s*\)|(?<![\d])0?(?P<ddd2>\d{2}))\s*[-.]?\s*"
    r"(?P<parte1>9\s?\d{4}|\d{4})\s*[-.\s]?\s*(?P<parte2>\d{4})(?![\d])"
    r"(?:\s*(?:[,/-]\s*)?(?:ramal|ram\.?|r\.|ext\.?)\s*:?\s*(?P<ramal>\d{1,5}))?",
    re.IGNORECASE,
)
_R_NAO_TELEFONE_ANTES = re.compile(
    r"(?:cpf|rg|cnpj|protocolo|processo|conta|c/c|agencia|ag\.|cep|matricula|inscricao|nf|nota|pis|nis|"
    r"titulo|siape|registro)\W{0,3}(?:n\.?o\.?\s*)?[:.]?\s*$"
)


def telefones_no_texto(texto: str) -> list[Achado]:
    """Os telefones com DDD citados no texto, na ordem em que aparecem.

    Aceita "(43) 3322-1100 ramal 12", "41 99999-0000", "+55 41 9 9999-0000",
    "41999990000". CPF, protocolo e número de conta não viram telefone.
    `detalhes` diz o tipo ("celular" ou "fixo") e o ramal.
    """
    texto = texto or ""
    dobrado = dobrar(texto)
    achados = []
    for m in _R_TELEFONE.finditer(texto):
        ddd = m.group("ddd1") or m.group("ddd2")
        numero = re.sub(r"\D", "", m.group("parte1") + m.group("parte2"))
        digitos = ddd + numero
        if ddd not in UF_DO_DDD or _R_NAO_TELEFONE_ANTES.search(dobrado[max(0, m.start() - 20):m.start()]):
            continue
        if len(digitos) == 11 and numero[0] == "9":
            tipo = "celular"
        elif len(digitos) == 10 and numero[0] in "2345":
            tipo = "fixo"
        else:
            continue
        cru = re.sub(r"\D", "", m.group(0))
        if len(cru) == 11 and cru == digitos and validar_cpf_digitos(cru):
            continue  # onze dígitos colados que formam um CPF válido
        ramal = m.group("ramal") or ""
        formatado = format_telefone(digitos)
        achados.append(Achado(
            valor=formatado,
            exibir=f"{formatado} ramal {ramal}" if ramal else formatado,
            trecho=_trecho(texto, dobrado, m.start(), m.end()),
            confianca="A",
            detalhes={"tipo": tipo, "ramal": ramal, "digitos": digitos},
        ))
    return achados


def telefone_no_texto(texto: str, *, preferir_celular: bool = True) -> Achado | None:
    """O telefone para contato: o primeiro celular; sem celular, o primeiro fixo."""
    achados = telefones_no_texto(texto)
    if preferir_celular:
        celular = next((a for a in achados if a.detalhes["tipo"] == "celular"), None)
        if celular:
            return celular
    return achados[0] if achados else None


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------

_R_PROTOCOLO = re.compile(
    r"\b(?:e-?\s?protocolo|protocolo|protocolad[oa]|processo|sid)\b(?P<vao>[^\d\n]{0,30}?)"
    r"(?<![\d.])(?P<numero>\d{2}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d)(?![.-]?\d)"
)


def protocolo_no_texto(texto: str) -> Achado | None:
    """O número do protocolo (eProtocolo), só quando ancorado.

    "protocolo nº 26.613.666-8", "e-Protocolo 26613666-8", "processo
    26.617.058-0". Número solto não conta (CPF e telefone se parecem), nem o
    que vier depois de "RG" ou "CPF".
    """
    texto = texto or ""
    dobrado = dobrar(texto)
    for m in _R_PROTOCOLO.finditer(dobrado):
        if re.search(r"\b(?:rg|cpf|cnpj|telefone|fone|celular)\b", m.group("vao")):
            continue
        digitos = re.sub(r"\D", "", m.group("numero"))
        formatado = format_protocolo(digitos)
        return Achado(formatado, formatado, _trecho(texto, dobrado, m.start(), m.end()), "A")
    return None


# ---------------------------------------------------------------------------
# Quantidade
# ---------------------------------------------------------------------------

PALAVRAS_PESSOAS = (
    "pessoas", "participantes", "convidados", "servidores", "alunos", "alunas", "estudantes",
    "criancas", "jovens", "adolescentes", "idosos", "professores", "colaboradores", "integrantes",
    "inscritos", "ouvintes", "familias", "moradores", "membros", "funcionarios", "kits", "lanches",
    "publico",
)
_NUMERO = r"(?<![\d.,/])(?P<n>\d{1,3}(?:\.\d{3})+|\d{1,6})(?![\d/]|[.,:]\d|\s*h\b|\s*(?:%|reais|anos|dias|horas))"
_R_QUANTIDADE_ANCORADA = re.compile(
    r"\b(?:publico(?:\s+(?:estimado|previsto|esperado|alvo|total))?|quantidade(?:\s+de\s+(?:pessoas|participantes|publico))?|"
    r"numero\s+de\s+(?:participantes|pessoas|alunos|convidados)|total\s+de\s+(?:participantes|pessoas)|"
    r"estimativa(?:\s+de\s+publico)?)\s*(?:de|:|-|=|e\s+de)?\s*"
    r"(?:cerca\s+de|aproximadamente|aprox\.?|em\s+torno\s+de|ate|mais\s+de|uns|umas)?\s*" + _NUMERO
)


def _quantidades(texto: str, palavras: Iterable[str], *, ancoradas: bool) -> Achado | None:
    texto = texto or ""
    dobrado = dobrar(texto)
    lista = "|".join(sorted({_chave(p) for p in palavras if _chave(p)}, key=len, reverse=True))
    if not lista:
        return None
    direta = re.compile(
        _NUMERO + r"\s*(?:\([^)\n]{1,40}\)\s*)?"
        r"(?:(?!de\b|do\b|da\b|para\b|e\b|a\b|o\b|com\b|em\b|no\b|na\b)[a-z]{3,}\s+)?"
        r"(?:" + lista + r")\b"
    )
    achados = []
    for regex in (direta, _R_QUANTIDADE_ANCORADA) if ancoradas else (direta,):
        for m in regex.finditer(dobrado):
            valor = int(m.group("n").replace(".", ""))
            if 0 < valor <= 100000:
                achados.append((valor, m.start(), m.end()))
    if not achados:
        return None
    valor, inicio, fim = max(achados, key=lambda a: (a[0], -a[1]))
    return Achado(valor, str(valor), _trecho(texto, dobrado, inicio, fim), "M")


def quantidade_no_texto(texto: str, palavras: Iterable[str]) -> Achado | None:
    """Quantidade citada junto de uma das `palavras` ("300 carteiras", "80 (oitenta) CIN").

    Havendo várias, vale a maior (o total costuma ser o maior número).
    """
    return _quantidades(texto, palavras, ancoradas=False)


def quantidade_de_pessoas(texto: str) -> Achado | None:
    """Quantas pessoas o evento terá.

    "120 alunos", "para cerca de 80 participantes", "80 (oitenta)
    convidados", "público estimado: 200". Havendo várias, vale a maior
    ("turmas de 30 alunos, 120 alunos no total").
    """
    return _quantidades(texto, PALAVRAS_PESSOAS, ancoradas=True)
