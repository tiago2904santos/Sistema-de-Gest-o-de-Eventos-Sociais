"""Carimbo do número de solicitação no ofício que voltou assinado do eProtocolo.

O ofício que o sistema gera já sai com os números numa coluna própria
(`col_solicitacao`). O que volta do eProtocolo vem com essa coluna em branco — o número
só existe depois de protocolar —, e é esse o documento que a prestação passou a exigir.
Aqui os números são desenhados sobre ele.

**Onde desenhar** não é chutado nem perguntado: o sistema gera o mesmo ofício com os
números (`gerar_oficio_prestacao_pdf`), lê onde cada um caiu e transporta a posição para
o PDF assinado. O transporte é feito por ÂNCORA — o nome do servidor, que existe nos dois
documentos —, e não por coordenada absoluta: assim o cabeçalho de protocolo, a margem
diferente ou a página de assinatura que o eProtocolo acrescenta deslocam âncora e número
juntos, e a conta continua valendo.

**O texto não é guardado.** Cada carimbo aponta para um `PrestacaoServidor` e o número
sai de `numero_solicitacao` na hora de desenhar. Corrigir o número no cadastro refaz o
carimbo; não há duas cópias para divergirem.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field
from io import BytesIO
from pathlib import Path
from django.db import transaction
from .arquivos import atomico_com_arquivos

from django.core.files.base import ContentFile

from core.errors import capture
from documentos.services.pdf_overlay import PdfOverlayError
from documentos.services.pdf_overlay import desenhar_overlay

from .models import CarimboSolicitacao

#: Corpo padrão quando a referência não diz qual era, em fração da altura da página.
#: 0.012 de uma A4 dá ~10pt, o corpo da tabela de servidores do ofício.
TAMANHO_PADRAO = 0.012


class CarimboError(Exception):
    """Erro amigável exibido ao usuário."""


# ─────────────────────────────────────────────────────────────────
# Leitura de onde cada texto está no PDF
# ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Fragmento:
    """Um pedaço de texto e onde ele foi desenhado, em pontos.

    `y` vem como o PDF entrega — medido de baixo. A conversão para a fração medida do
    topo, que é a convenção do navegador e do `pdf_overlay`, acontece só no fim, em
    `_para_posicao`.
    """

    pagina: int
    texto: str
    x: float
    y: float
    corpo: float
    largura_pagina: float
    altura_pagina: float
    #: Onde a página começa em y. O eProtocolo acrescenta a faixa do rodapé embaixo
    #: (mediabox a partir de −40), então "dentro da página" não é `0 ≤ y`.
    base_pagina: float = 0.0

    @property
    def dentro_da_pagina(self) -> bool:
        folga = 1.0
        return (
            -folga <= self.x <= self.largura_pagina + folga
            and self.base_pagina - folga <= self.y <= self.base_pagina + self.altura_pagina + folga
        )


@dataclass
class Linha:
    """Fragmentos que saíram na mesma altura, na ordem em que aparecem.

    Existe porque o extrator quebra o texto em pedaços arbitrários: um nome com três
    palavras pode vir em três fragmentos. Procurar o nome fragmento a fragmento não
    acha nada; procurar na linha inteira acha, e o primeiro fragmento dela é a âncora.
    """

    pagina: int
    y: float
    fragmentos: list[Fragmento] = field(default_factory=list)

    @property
    def texto(self) -> str:
        ordenados = sorted(self.fragmentos, key=lambda f: f.x)
        return " ".join(f.texto for f in ordenados)

    @property
    def inicio(self) -> Fragmento:
        return min(self.fragmentos, key=lambda f: f.x)


def _normalizar(texto: str) -> str:
    """Caixa alta, sem acento e sem espaço repetido.

    O nome no documento passa por `format_document_display` (capitalização legível),
    então comparar com `servidor.nome` cru nunca casaria.
    """
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    normalizado = re.sub(r"\s+", " ", sem_acento).strip().upper()
    return re.sub(r"\s*([-/])\s*", r"\1", normalizado)


def ler_fragmentos(pdf_bytes: bytes) -> list[Fragmento]:
    """Todo texto do PDF, com a coordenada em que foi desenhado.

    Devolve vazio para PDF sem camada de texto (imagem escaneada) — não é erro, é o
    caso em que o posicionamento automático não tem como funcionar e a tela de ajuste
    assume.
    """
    from pypdf import PdfReader

    achados: list[Fragmento] = []
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:
                capture(exc, "prestacoes.carimbo.decrypt")

        for indice, page in enumerate(reader.pages):
            largura = float(page.mediabox.width)
            altura = float(page.mediabox.height)
            base = float(page.mediabox.bottom)

            def visitor(texto, cm, tm, _font_dict, corpo, _indice=indice, _l=largura, _a=altura, _b=base):
                limpo = str(texto or "").strip()
                if not limpo:
                    return
                # Composição CTM × matriz de texto: o gerador de PDF pode aplicar uma
                # transformação na página inteira, e ler só `tm` daria a coordenada no
                # espaço do texto, não na página.
                x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
                y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
                escala = abs(cm[3] * tm[3]) or 1.0
                achados.append(
                    Fragmento(
                        pagina=_indice,
                        texto=limpo,
                        x=x,
                        y=y,
                        corpo=float(corpo or 0) * escala,
                        largura_pagina=_l,
                        altura_pagina=_a,
                        base_pagina=_b,
                    )
                )

            page.extract_text(visitor_text=visitor)
    except Exception as exc:
        capture(exc, "prestacoes.carimbo.ler_fragmentos")
        return []
    return achados


def agrupar_em_linhas(fragmentos: list[Fragmento]) -> list[Linha]:
    """Junta fragmentos que saíram na mesma altura da mesma página.

    A tolerância acompanha o corpo da fonte: em texto de 10pt, dois fragmentos a 3pt de
    distância vertical são a mesma linha; num título de 20pt, não seriam.
    """
    linhas: list[Linha] = []
    for frag in sorted(fragmentos, key=lambda f: (f.pagina, -f.y, f.x)):
        tolerancia = max(1.5, (frag.corpo or 10.0) * 0.4)
        alvo = None
        for linha in reversed(linhas):
            if linha.pagina != frag.pagina:
                break
            if abs(linha.y - frag.y) <= tolerancia:
                alvo = linha
                break
        if alvo is None:
            alvo = Linha(pagina=frag.pagina, y=frag.y)
            linhas.append(alvo)
        alvo.fragmentos.append(frag)
    return linhas


def _procurar(linhas: list[Linha], agulha: str) -> Linha | None:
    """Primeira linha cujo texto contém a agulha, já normalizados os dois lados."""
    alvo = _normalizar(agulha)
    if not alvo:
        return None
    for linha in linhas:
        if alvo in _normalizar(linha.texto):
            return linha
    return None


def _fragmento_do_texto(linha, texto):
    """O Word pode dividir número e hífens em fragmentos separados na mesma linha."""
    alvo = _normalizar(texto)
    fragmentos = sorted(linha.fragmentos, key=lambda f: f.x)
    for i, frag in enumerate(fragmentos):
        primeiro = _normalizar(frag.texto)
        if alvo in primeiro:
            return frag
        if primeiro and alvo.startswith(primeiro):
            acumulado = primeiro
            for proximo in fragmentos[i + 1:]:
                acumulado = _normalizar(acumulado + " " + proximo.texto)
                if alvo in acumulado:
                    return frag
    return None


# ─────────────────────────────────────────────────────────────────
# De onde o número deve sair
# ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Posicao:
    """Onde desenhar, na convenção do navegador: fração, origem no topo-esquerdo."""

    pagina: int
    x: float
    y: float
    tamanho: float
    #: `True` quando a âncora não foi achada no PDF assinado e a coordenada da
    #: referência foi copiada crua — provavelmente certa, mas sem confirmação.
    incerta: bool = False


def _para_posicao(frag: Fragmento, *, x: float, y: float, incerta: bool) -> Posicao:
    altura = frag.altura_pagina or 1.0
    largura = frag.largura_pagina or 1.0
    return Posicao(
        pagina=frag.pagina,
        x=max(0.0, min(1.0, x / largura)),
        # Do topo, não de baixo: é assim que a tela mede e que o `pdf_overlay` espera.
        y=max(0.0, min(1.0, (altura - y) / altura)),
        tamanho=(frag.corpo / altura) if frag.corpo else TAMANHO_PADRAO,
        incerta=incerta,
    )


def posicoes_automaticas(prestacao, pdf_assinado: bytes) -> dict[int, Posicao]:
    """Onde cada número de solicitação deve cair no PDF assinado.

    A chave é o `pk` do `PrestacaoServidor`. Servidor sem número, ou cujo número não foi
    achado na referência, fica de fora — quem chama trata isso como pendência, não como
    falha. Âncora que não se acha (ou que não dá para confiar) levanta `CarimboError`:
    nunca se copia coordenada às cegas. O upload usa `_posicoes_e_falhas`, que em vez
    de recusar manda esses servidores para o ajuste manual.
    """
    posicoes, falhas = _posicoes_e_falhas(prestacao, pdf_assinado)
    if falhas:
        raise CarimboError(next(iter(falhas.values())))
    return posicoes


def _paginas_com_texto_em_form(pdf_bytes: bytes) -> set[int]:
    """Páginas cujo texto (ou parte dele) está dentro de um Form XObject.

    É como o eProtocolo "embrulha" a página que devolve. O pypdf lê o form com a
    matriz zerada, então as coordenadas do texto de dentro não são as da página.
    """
    import re as _re

    from pypdf import PdfReader

    def tem_texto(recursos, profundidade) -> bool:
        try:
            recursos = recursos.get_object() if recursos is not None else None
            xobjetos = recursos.get("/XObject") if recursos is not None else None
            if xobjetos is None:
                return False
            for referencia in xobjetos.get_object().values():
                objeto = referencia.get_object()
                if objeto.get("/Subtype") != "/Form":
                    continue
                if _re.search(rb"(?<![A-Za-z])BT(?![A-Za-z])", objeto.get_data() or b""):
                    return True
                if profundidade < 3 and tem_texto(objeto.get("/Resources"), profundidade + 1):
                    return True
        except Exception:
            return False
        return False

    try:
        leitor = PdfReader(BytesIO(pdf_bytes))
        if getattr(leitor, "is_encrypted", False):
            leitor.decrypt("")
        return {i for i, pagina in enumerate(leitor.pages) if tem_texto(pagina.get("/Resources"), 0)}
    except Exception as exc:
        capture(exc, "prestacoes.carimbo.forms")
        return set()


def _ocorrencias(linhas: list[Linha], pagina: int, nome: str) -> int:
    alvo = _normalizar(nome)
    return sum(
        1
        for linha in linhas
        if linha.pagina == pagina
        for frag in linha.fragmentos
        if alvo in _normalizar(frag.texto)
    )


def _nome_dentro_de_bloco(linhas: list[Linha], pagina: int, nome: str) -> bool:
    """O nome aparece, nesta página, dentro de um bloco de texto "achatado".

    Página "embrulhada" pelo eProtocolo (o conteúdo num Form XObject com o Y
    invertido — lacuna L2): o pypdf lê o form com a matriz zerada, então as
    coordenadas de dentro saem trocadas, e depois devolve o texto inteiro do form
    num fragmento só, de várias linhas. Achar o nome ali é o sinal de que nenhuma
    coordenada desta página serve de âncora — a posição calculada cairia no lugar
    errado sem erro nenhum.
    """
    alvo = _normalizar(nome)
    for linha in linhas:
        if linha.pagina != pagina:
            continue
        for frag in linha.fragmentos:
            if ("\n" in frag.texto or len(frag.texto) > len(nome) + 160) and alvo in _normalizar(frag.texto):
                return True
    return False


def _posicoes_e_falhas(prestacao, pdf_assinado: bytes) -> tuple[dict[int, Posicao], dict[int, str]]:
    """(posições achadas, {ps.pk: motivo} dos que precisam de ajuste manual).

    Falha é âncora não achada (PDF escaneado, nome grafado de outro jeito) ou achada
    num lugar em que não dá para confiar: fora da página, ou dentro de página
    embrulhada (`_nome_dentro_de_bloco`). Nos dois casos o servidor NÃO recebe
    posição — o número não é desenhado — e vai para "Ajustar posição".
    """
    from .services import gerar_oficio_prestacao_pdf

    servidores = [
        ps
        for ps in prestacao.servidores_prestacao.select_related("servidor").all()
        if str(ps.numero_solicitacao or "").strip()
    ]
    if not servidores:
        return {}, {}

    try:
        referencia = gerar_oficio_prestacao_pdf(prestacao)
    except Exception as exc:
        capture(exc, "prestacoes.carimbo.referencia", prestacao_id=prestacao.pk)
        return {}, {}

    linhas_ref = agrupar_em_linhas(ler_fragmentos(referencia))
    linhas_dest = agrupar_em_linhas(ler_fragmentos(pdf_assinado))
    if not linhas_ref:
        return {}, {}
    embrulhadas = _paginas_com_texto_em_form(pdf_assinado) if linhas_dest else set()

    posicoes: dict[int, Posicao] = {}
    falhas: dict[int, str] = {}
    for ps in servidores:
        numero = str(ps.numero_solicitacao or "").strip()
        nome = getattr(ps.servidor, "nome", "") or ""

        linha_numero = _procurar(linhas_ref, numero)
        if linha_numero is None:
            continue
        alvo = _fragmento_do_texto(linha_numero, numero)
        if alvo is None:
            falhas[ps.pk] = "Não foi possível localizar o início do número na referência."
            continue

        ancora_ref = _procurar(linhas_ref, nome)
        ancora_dest = _procurar(linhas_dest, nome) if linhas_dest else None
        if ancora_ref is None or ancora_dest is None:
            falhas[ps.pk] = f"Não foi possível localizar a âncora do servidor {nome} no PDF. O carimbo não foi aplicado."
            continue

        # O deslocamento entre a âncora e o número é o que se transporta. Se o
        # eProtocolo empurrou a página inteira, os dois andaram junto.
        dx = alvo.x - ancora_ref.inicio.x
        dy = alvo.y - ancora_ref.inicio.y
        base = ancora_dest.inicio
        destino = Fragmento(
            pagina=base.pagina, texto=numero, x=base.x + dx, y=base.y + dy, corpo=base.corpo,
            largura_pagina=base.largura_pagina, altura_pagina=base.altura_pagina, base_pagina=base.base_pagina,
        )
        # Na página embrulhada, o texto de dentro do form aparece duas vezes (lido com a
        # matriz errada e devolvido de novo, inteiro, na saída do form): o nome repetido
        # ali é o sinal de que a âncora não serve.
        embrulhada = base.pagina in embrulhadas and _ocorrencias(linhas_dest, base.pagina, nome) >= 2
        if (
            not base.dentro_da_pagina
            or not destino.dentro_da_pagina
            or embrulhada
            or _nome_dentro_de_bloco(linhas_dest, base.pagina, nome)
        ):
            falhas[ps.pk] = (
                f"A posição do número de {nome} não pôde ser conferida neste PDF "
                "(página recomposta pelo eProtocolo). O carimbo não foi aplicado."
            )
            continue
        posicoes[ps.pk] = _para_posicao(base, x=destino.x, y=destino.y, incerta=False)

    return posicoes, falhas


# ─────────────────────────────────────────────────────────────────
# Desenho
# ─────────────────────────────────────────────────────────────────

@dataclass
class ResultadoCarimbo:
    """O que o carimbo fez. A view traduz em `messages`."""

    carimbados: int = 0
    sem_numero: list[str] = field(default_factory=list)
    sem_posicao: list[str] = field(default_factory=list)
    incertos: int = 0
    erro: str = ""

    @property
    def ok(self) -> bool:
        return not self.erro

    @property
    def precisa_ajuste(self) -> bool:
        return bool(self.incertos or self.sem_posicao)


def _bytes_do_arquivo(campo) -> bytes:
    if not campo:
        raise CarimboError("O anexo não tem arquivo para carimbar.")
    campo.open("rb")
    try:
        return campo.read()
    finally:
        campo.close()


def carimbar(anexo) -> ResultadoCarimbo:
    """Redesenha o anexo a partir do cru, com as posições já guardadas.

    Não recalcula posição: usa o que está em `CarimboSolicitacao`. É o caminho do
    recarimbo — número corrigido, posição ajustada à mão — e por isso parte SEMPRE do
    `arquivo_original`. Partir do carimbado empilharia um número sobre o outro.
    """
    carimbos = list(
        anexo.carimbos.select_related("servidor_prestacao__servidor").all()
    )
    if not carimbos:
        return ResultadoCarimbo()

    try:
        origem = _bytes_do_arquivo(anexo.arquivo_para_carimbar)
    except CarimboError as exc:
        return ResultadoCarimbo(erro=str(exc))

    resultado = ResultadoCarimbo()
    por_pagina: dict[int, list[tuple[CarimboSolicitacao, str]]] = {}
    for carimbo in carimbos:
        numero = str(carimbo.servidor_prestacao.numero_solicitacao or "").strip()
        if not numero:
            resultado.sem_numero.append(
                getattr(carimbo.servidor_prestacao.servidor, "nome", "") or "—"
            )
            continue
        por_pagina.setdefault(int(carimbo.pagina), []).append((carimbo, numero))

    if not por_pagina:
        return resultado

    def desenho_da_pagina(itens):
        def desenhar(c, medidas):
            for carimbo, numero in itens:
                corpo = max(4.0, float(carimbo.tamanho or TAMANHO_PADRAO) * medidas.altura)
                c.setFont("Helvetica", corpo)
                c.setFillColorRGB(0, 0, 0)
                # `drawString` assenta na linha de base, que é onde a referência mediu
                # o número — por isso a altura da caixa é zero aqui.
                c.drawString(medidas.x_pdf(carimbo.x), medidas.y_pdf(carimbo.y), numero)

        return desenhar

    try:
        conteudo = desenhar_overlay(
            origem,
            {pagina: desenho_da_pagina(itens) for pagina, itens in por_pagina.items()},
        )
    except PdfOverlayError as exc:
        return ResultadoCarimbo(erro=str(exc), sem_numero=resultado.sem_numero)

    _gravar_carimbado(anexo, conteudo)
    resultado.carimbados = sum(len(itens) for itens in por_pagina.values())
    return resultado


@atomico_com_arquivos
def _gravar_carimbado(anexo, conteudo: bytes) -> None:
    """Substitui `arquivo` pelo carimbado, apagando o arquivo anterior.

    O nome é derivado do `pk`, e não do arquivo enviado: sem isso cada recarimbo
    deixaria um `_XyZ.pdf` novo no disco, e são muitos por prestação.
    """
    anterior = anexo.arquivo.name if anexo.arquivo else ""
    nome = f"oficio_assinado_carimbado_{anexo.pk}.pdf"
    anexo.arquivo.save(nome, ContentFile(conteudo), save=False)
    anexo.save(update_fields=["arquivo"])
    if anterior and anterior != anexo.arquivo.name:
        try:
            transaction.on_commit(lambda: anexo.arquivo.storage.delete(anterior))
        except Exception as exc:
            capture(exc, "prestacoes.carimbo.apagar_anterior", anexo_id=anexo.pk)


@atomico_com_arquivos
def preparar_e_carimbar(anexo, *, prestacao) -> ResultadoCarimbo:
    """Caminho do upload: guarda o cru, descobre as posições e desenha.

    Posição ajustada à mão é preservada — o automático já errou naquele ponto uma vez, e
    reescrever por cima devolveria o erro que o usuário corrigiu. Servidor cuja posição
    não se descobre com segurança (PDF escaneado, página embrulhada pelo eProtocolo) sai
    em `sem_posicao`, sem carimbo: o anexo fica, e a tela manda "Ajustar posição".
    """
    try:
        cru = _bytes_do_arquivo(anexo.arquivo)
    except CarimboError as exc:
        return ResultadoCarimbo(erro=str(exc))

    if not anexo.arquivo_original:
        nome = Path(anexo.nome_original or anexo.arquivo.name or "oficio.pdf").name
        anexo.arquivo_original.save(nome, ContentFile(cru), save=False)
        anexo.save(update_fields=["arquivo_original"])

    # Âncora que não se acha (escaneado) ou não se confirma (página embrulhada) não
    # recusa o upload: o servidor fica sem posição e o operador ajusta à mão.
    posicoes, _falhas = _posicoes_e_falhas(prestacao, cru)
    manuais = {
        c.servidor_prestacao_id
        for c in anexo.carimbos.filter(ajustado_manualmente=True)
    }
    for ps_pk, posicao in posicoes.items():
        if ps_pk in manuais:
            continue
        CarimboSolicitacao.objects.update_or_create(
            anexo=anexo,
            servidor_prestacao_id=ps_pk,
            defaults={
                "pagina": posicao.pagina,
                "x": posicao.x,
                "y": posicao.y,
                "tamanho": posicao.tamanho,
                "ajustado_manualmente": False,
            },
        )

    resultado = carimbar(anexo)
    resultado.incertos = sum(
        1 for p in posicoes.values() if p.incerta and p.pagina is not None
    )
    posicionados = set(posicoes) | manuais
    for ps in prestacao.servidores_prestacao.select_related("servidor").all():
        nome = getattr(ps.servidor, "nome", "") or "—"
        if not str(ps.numero_solicitacao or "").strip():
            if nome not in resultado.sem_numero:
                resultado.sem_numero.append(nome)
        elif ps.pk not in posicionados:
            resultado.sem_posicao.append(nome)
    return resultado


@dataclass
class ResultadoAjuste:
    """O que a tela de ajuste gravou."""

    erro: str = ""
    posicoes_gravadas: int = 0


def salvar_posicoes(anexo, posicoes) -> ResultadoAjuste:
    """Grava as posições vindas da tela e redesenha o anexo a partir do cru.

    Marca `ajustado_manualmente` em tudo que passa por aqui: a partir deste ponto o
    cálculo automático não pode mais reescrever a posição, senão o próximo upload
    devolveria o erro que o operador acabou de corrigir.

    `posicoes` é `{servidor_prestacao_pk: (pagina, x, y, tamanho)}`, já convertido pela
    view — a validação de forma é dela; a de FAIXA é daqui, porque é o desenho que não
    aceita coordenada fora da página.
    """
    import math
    from pypdf import PdfReader
    paginas = len(PdfReader(BytesIO(_bytes_do_arquivo(anexo.arquivo_para_carimbar))).pages)
    permitidos = set(anexo.prestacao.servidores_prestacao.values_list("pk", flat=True))
    for ps_pk, (pagina, x, y, tamanho) in posicoes.items():
        if ps_pk not in permitidos or not 0 <= pagina < paginas:
            return ResultadoAjuste(erro="Servidor ou página inválida; refaça o ajuste.")
        if not all(math.isfinite(v) for v in (x, y, tamanho)) or not (0 <= x <= 1 and 0 <= y <= 1 and 0 < tamanho <= 1):
            return ResultadoAjuste(erro="Posição fora da página; refaça o ajuste.")
    gravadas = 0
    for ps_pk, (pagina, x, y, tamanho) in posicoes.items():
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) or tamanho <= 0:
            return ResultadoAjuste(erro="Posição fora da página; refaça o ajuste.")
        CarimboSolicitacao.objects.update_or_create(
            anexo=anexo,
            servidor_prestacao_id=ps_pk,
            defaults={
                "pagina": max(0, int(pagina)),
                "x": x,
                "y": y,
                "tamanho": tamanho,
                "ajustado_manualmente": True,
            },
        )
        gravadas += 1

    resultado = carimbar(anexo)
    return ResultadoAjuste(erro=resultado.erro, posicoes_gravadas=gravadas)


def caixas_para_ajuste(prestacao, anexo) -> list[dict]:
    """Uma caixa por servidor, com a posição atual ou o palpite inicial.

    Servidor sem carimbo ainda cai perto da coluna de solicitação (75% da largura), que
    é onde ela fica no ofício — melhor do que o canto da página, mas é palpite: quem
    decide é o arraste.
    """
    carimbos = {c.servidor_prestacao_id: c for c in anexo.carimbos.all()}
    caixas = []
    for ps in prestacao.servidores_prestacao.select_related("servidor").all():
        carimbo = carimbos.get(ps.pk)
        caixas.append(
            {
                "ps_pk": ps.pk,
                "nome": ps.servidor.nome,
                "numero": str(ps.numero_solicitacao or "").strip(),
                "pagina": carimbo.pagina if carimbo else 0,
                "x": carimbo.x if carimbo else 0.75,
                "y": carimbo.y if carimbo else 0.35,
                "tamanho": carimbo.tamanho if carimbo else TAMANHO_PADRAO,
                "posicionado": carimbo is not None,
            }
        )
    return caixas


def anexo_do_oficio_assinado(prestacao):
    """O anexo carimbável da prestação, ou `None`."""
    from .models import PrestacaoDocumentoAnexo

    return (
        prestacao.documentos_anexos.filter(
            tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO
        )
        .order_by("-criado_em", "-pk")
        .first()
    )


@atomico_com_arquivos
def _posicionar_pendentes(anexo, prestacao) -> int:
    """Grava a posição de quem tem número e ainda não tem carimbo neste anexo.

    Quem já tem carimbo (automático ou ajustado à mão) não é tocado: o recarimbo só
    precisa redesenhar com o número novo. Devolve quantas posições gravou.
    """
    com_carimbo = set(anexo.carimbos.values_list("servidor_prestacao_id", flat=True))
    pendentes = {
        ps.pk
        for ps in prestacao.servidores_prestacao.all()
        if str(ps.numero_solicitacao or "").strip() and ps.pk not in com_carimbo
    }
    if not pendentes:
        return 0
    cru = _bytes_do_arquivo(anexo.arquivo_para_carimbar)
    if not anexo.arquivo_original:
        # Antes do primeiro carimbo o arquivo é o cru: guardá-lo é o que permite
        # redesenhar depois sem empilhar números.
        nome = Path(anexo.nome_original or anexo.arquivo.name or "oficio.pdf").name
        anexo.arquivo_original.save(nome, ContentFile(cru), save=False)
        anexo.save(update_fields=["arquivo_original"])
    posicoes, _falhas = _posicoes_e_falhas(prestacao, cru)
    gravadas = 0
    for ps_pk, posicao in posicoes.items():
        if ps_pk not in pendentes:
            continue
        CarimboSolicitacao.objects.get_or_create(
            anexo=anexo,
            servidor_prestacao_id=ps_pk,
            defaults={"pagina": posicao.pagina, "x": posicao.x, "y": posicao.y, "tamanho": posicao.tamanho},
        )
        gravadas += 1
    return gravadas


def recarimbar_prestacao(prestacao) -> ResultadoCarimbo | None:
    """Redesenha o ofício assinado da prestação, se houver um anexado.

    Chamado depois que um número de solicitação muda. Sem anexo, não há o que fazer — e
    isso é o caso comum, então sai barato.

    m080: o ofício costuma voltar do eProtocolo ANTES das solicitações, e aí o anexo
    entra sem carimbo nenhum. O servidor que ganha número depois recebe a posição aqui
    (`_posicionar_pendentes`); o que não se acha fica para o "Ajustar posição".
    """
    anexo = anexo_do_oficio_assinado(prestacao)
    if anexo is None:
        return None
    try:
        _posicionar_pendentes(anexo, prestacao)
        if not anexo.carimbos.exists():
            return None
        return carimbar(anexo)
    except Exception as exc:
        capture(exc, "prestacoes.carimbo.recarimbar", prestacao_id=prestacao.pk)
        return None
