"""Passa a bateria pelo leitor de verdade e compara com o gabarito.

Uso no terminal (banco de desenvolvimento, sem gravar nada — tudo roda numa
transação desfeita no fim)::

    python manage.py avaliar_leitura            # todos os módulos
    python manage.py avaliar_leitura solicitacoes --erros

No teste (`test_bateria.py`) o mesmo `avaliar` roda no banco de testes.

Para cada caso: lê o e-mail como a tela lê (arquivo .eml ou texto colado),
com o relógio parado em `caso.agora`; confere a triagem (o módulo certo em
1º) e cada campo do `esperado` contra o `preenchimento.py` do módulo.
"""

from __future__ import annotations

import importlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.db.models import Model

from . import AUSENTE, Caso, Contem, UmDe

MODULOS = ("solicitacoes", "demandas_eventos", "coffee_break", "atendimento_imprensa", "publicacoes")
_FUSO = ZoneInfo("America/Sao_Paulo")
_PASTA = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Casos e cadastros
# ---------------------------------------------------------------------------


def carregar(modulos=MODULOS) -> tuple[list[Caso], dict]:
    """Os casos dos módulos pedidos e a união dos CADASTROS de cada arquivo."""
    casos, cadastros = [], {}
    for modulo in modulos:
        try:
            arquivo = importlib.import_module(f"{__package__}.casos_{modulo}")
        except ModuleNotFoundError:
            continue
        casos.extend(arquivo.CASOS)
        for tipo, nomes in getattr(arquivo, "CADASTROS", {}).items():
            cadastros.setdefault(tipo, [])
            cadastros[tipo].extend(n for n in nomes if n not in cadastros[tipo])
    return casos, cadastros


def preparar_banco(cadastros: dict) -> None:
    """Municípios do PR e de SC (IBGE) e os cadastros que os casos citam."""
    from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao

    regiao = Regiao.objects.order_by("pk").first() or Regiao.objects.create(nome="Região da bateria")
    ufs = {"PR": ("Paraná", 41), "SC": ("Santa Catarina", 42)}
    lista = json.loads((_PASTA / "municipios.json").read_text(encoding="utf-8"))
    for sigla, (nome_uf, codigo) in ufs.items():
        estado = Estado.objects.filter(sigla=sigla).first() or Estado.objects.create(sigla=sigla, nome=nome_uf, codigo_ibge=codigo)
        if not estado.ativo:
            Estado.objects.filter(pk=estado.pk).update(ativo=True)
        existentes = set(Municipio.objects.filter(estado=estado).values_list("nome", flat=True))
        ibge_usados = set(Municipio.objects.exclude(codigo_ibge=None).values_list("codigo_ibge", flat=True))
        Municipio.objects.bulk_create([
            Municipio(nome=nome, estado=estado, regiao=regiao, codigo_ibge=None if ibge in ibge_usados else ibge,
                      capital=(nome in ("Curitiba", "Florianópolis")))
            for nome, ibge in lista[sigla] if nome not in existentes
        ])
    criadores = {
        "orgao": lambda nome: OrgaoResponsavel.objects.get_or_create(nome=nome),
    }
    try:
        from demandas_eventos.models import Palestrante, Tema

        criadores["tema"] = lambda nome: Tema.objects.get_or_create(nome=nome)
        criadores["palestrante"] = lambda nome: Palestrante.objects.get_or_create(nome=nome)
    except ImportError:  # pragma: no cover
        pass
    try:
        from atendimento_imprensa.models import Veiculo

        criadores["veiculo"] = lambda nome: Veiculo.objects.get_or_create(nome=nome)
    except ImportError:  # pragma: no cover
        pass
    try:
        from publicacoes.models import Unidade

        criadores["unidade"] = lambda nome: Unidade.objects.get_or_create(nome=nome)
    except ImportError:  # pragma: no cover
        pass
    for tipo, nomes in cadastros.items():
        criar = criadores.get(tipo)
        if criar is None:
            raise ValueError(f"Cadastro desconhecido na bateria: {tipo}")
        for nome in nomes:
            criar(nome)


# ---------------------------------------------------------------------------
# Comparação
# ---------------------------------------------------------------------------


def _chave(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().replace("–", "-").replace("—", "-").split())


def normalizar(valor):
    """O valor sugerido num formato comparável com o gabarito."""
    if valor is None:
        return None
    if isinstance(valor, Model):
        if valor.__class__.__name__ == "Estado":
            return valor.sigla
        return getattr(valor, "nome", None) or str(valor)
    if isinstance(valor, datetime):
        local = valor.astimezone(_FUSO) if valor.tzinfo else valor
        return local.strftime("%Y-%m-%d %H:%M")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (list, tuple, set)) or hasattr(valor, "__iter__") and not isinstance(valor, (str, bytes, dict)):
        return [normalizar(v) for v in valor]
    return valor


def confere(esperado, obtido) -> bool:
    """O valor normalizado bate com o gabarito?"""
    if isinstance(esperado, UmDe):
        return any(confere(opcao, obtido) for opcao in esperado.opcoes)
    if obtido is None or obtido == "" or obtido == []:
        return False
    if isinstance(esperado, Contem):
        alvo = " ".join(map(str, obtido)) if isinstance(obtido, list) else str(obtido)
        return _chave(esperado.trecho) in _chave(alvo)
    if isinstance(esperado, (list, tuple)):
        if not isinstance(obtido, list):
            obtido = [obtido]
        return sorted(_chave(v) for v in esperado) == sorted(_chave(v) for v in obtido)
    if isinstance(esperado, bool):
        return obtido is esperado or _chave(obtido) in (("1", "true", "sim") if esperado else ("0", "false", "nao"))
    if isinstance(esperado, int):
        try:
            return int(str(obtido).replace(".", "")) == esperado
        except ValueError:
            return False
    if isinstance(esperado, str) and len(esperado) == 10 and esperado[4] == "-" and isinstance(obtido, str) and len(obtido) == 16:
        return obtido[:10] == esperado  # data esperada, sugerido data e hora
    return _chave(esperado) == _chave(obtido)


@dataclass
class Falha:
    caso: str
    campo: str
    esperado: object
    obtido: object
    confianca: str = ""
    trecho: str = ""
    nota: str = ""

    @property
    def tipo(self) -> str:
        if self.campo == "(triagem)":
            return "triagem"
        if self.esperado is AUSENTE:
            return "inventou"
        if self.obtido in (None, "", []):
            return "faltou"
        return "errou"

    def linha(self) -> str:
        extra = f" [{self.confianca}]" if self.confianca else ""
        trecho = f"\n        trecho: {self.trecho[:160]}" if self.trecho else ""
        return f"{self.caso:>9} {self.campo:<26} {self.tipo:<8} esperado={self.esperado!r} obtido={self.obtido!r}{extra}{trecho}"


@dataclass
class Relatorio:
    casos: int = 0
    campos: int = 0
    falhas: list[Falha] = field(default_factory=list)
    por_campo: dict = field(default_factory=dict)  # (modulo, campo) -> [acertos, total]
    triagem: list[int] = field(default_factory=lambda: [0, 0])

    @property
    def acertos(self) -> int:
        return self.campos - sum(1 for f in self.falhas if f.campo != "(triagem)")

    def resumo(self) -> str:
        linhas = [f"Casos: {self.casos} | campos conferidos: {self.campos} | acertos: {self.acertos} "
                  f"({100 * self.acertos / max(self.campos, 1):.1f}%) | triagem: {self.triagem[0]}/{self.triagem[1]}"]
        tipos = {}
        for f in self.falhas:
            tipos[f.tipo] = tipos.get(f.tipo, 0) + 1
        if tipos:
            linhas.append("Falhas por tipo: " + ", ".join(f"{t}={n}" for t, n in sorted(tipos.items())))
        piores = sorted(((a / t, m, c, a, t) for (m, c), (a, t) in self.por_campo.items() if a < t))
        for taxa, modulo, campo, a, t in piores:
            linhas.append(f"  {modulo:<22} {campo:<26} {a}/{t} ({100 * taxa:.0f}%)")
        return "\n".join(linhas)


def _mensagem(caso: Caso):
    from core.leitura.mensagem import ler_mensagem, ler_texto_colado

    if caso.formato == "eml":
        return ler_mensagem(f"{caso.id}.eml", caso.texto.encode("utf-8"))
    if caso.formato == "texto":
        return ler_texto_colado(caso.texto)
    raise ValueError(f"{caso.id}: formato desconhecido {caso.formato!r}")


def avaliar_caso(caso: Caso, relatorio: Relatorio) -> None:
    from django.utils import timezone

    from core.leitura.triagem import triar_mensagem

    agora = datetime.strptime(caso.agora, "%Y-%m-%d %H:%M").replace(tzinfo=_FUSO)
    preenchimento = importlib.import_module(f"{caso.modulo}.preenchimento")
    relatorio.casos += 1
    with mock.patch.object(timezone, "now", return_value=agora):
        try:
            mensagem = _mensagem(caso)
            sugestoes = preenchimento.sugestoes(mensagem, None)
            destinos = triar_mensagem(mensagem)
        except Exception as erro:  # o leitor não pode quebrar com e-mail nenhum
            relatorio.falhas.append(Falha(caso.id, "(exceção)", "", f"{type(erro).__name__}: {erro}", nota=caso.nota))
            relatorio.campos += len(caso.esperado)
            for campo in caso.esperado:
                par = relatorio.por_campo.setdefault((caso.modulo, campo), [0, 0])
                par[1] += 1
            return
    relatorio.triagem[1] += 1
    primeiro = destinos[0].modulo if destinos else None
    if primeiro == caso.modulo:
        relatorio.triagem[0] += 1
    else:
        relatorio.falhas.append(Falha(caso.id, "(triagem)", caso.modulo, [f"{d.modulo}:{d.pontos:g}" for d in destinos[:3]], nota=caso.nota))
    for campo, esperado in caso.esperado.items():
        relatorio.campos += 1
        par = relatorio.por_campo.setdefault((caso.modulo, campo), [0, 0])
        par[1] += 1
        sugestao = sugestoes.get(campo)
        if esperado is AUSENTE:
            if sugestao is None or sugestao.confianca == "B":
                par[0] += 1
            else:
                relatorio.falhas.append(Falha(caso.id, campo, AUSENTE, normalizar(sugestao.valor), sugestao.confianca, sugestao.trecho, caso.nota))
            continue
        obtido = normalizar(sugestao.valor) if sugestao is not None else None
        if confere(esperado, obtido):
            par[0] += 1
        else:
            relatorio.falhas.append(Falha(caso.id, campo, esperado, obtido, getattr(sugestao, "confianca", ""),
                                          getattr(sugestao, "trecho", ""), caso.nota))


def avaliar(casos) -> Relatorio:
    relatorio = Relatorio()
    for caso in casos:
        avaliar_caso(caso, relatorio)
    return relatorio
