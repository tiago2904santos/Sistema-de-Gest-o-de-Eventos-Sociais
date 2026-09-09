"""QA-06 — a mitigação da PYSEC-2026-3412 precisa ser provada por comportamento.

Portado do GV: as referências a pip-audit abaixo descrevem o CI de origem.
Aqui o motor é opcional e não foi adicionada nenhuma exceção de auditoria.

O `pip-audit` do CI (`tests.yml`) **ignora essa CVE** citando este arquivo como
justificativa. A versão original do teste era:

    self.assertIn("presentational_hints=False", inspect.getsource(...))

Isso prova que a string existe no código-fonte da função, não que o documento
gerado ignora atributo de apresentação do HTML. Um refactor que movesse a flag
para um dict de kwargs, ou que abrisse um segundo caminho de renderização sem
ela, passaria no teste e regrediria a mitigação — enquanto o CI continuaria
ignorando a CVE em nome dele.

## Por que não se compara byte de PDF aqui

Duas tentativas anteriores compararam a saída em bytes (e depois por digest).
As duas reprovaram no CI e passaram localmente, e a segunda trouxe a explicação
porque tinha uma asserção separada para isso:

    duas renderizações idênticas deram documentos diferentes — o WeasyPrint
    deixou de ser determinístico neste ambiente

**A saída em bytes do WeasyPrint não é reproduzível no runner** — nem entre duas
chamadas iguais, no mesmo processo. E é intermitente: a mesma suíte passou numa
execução e reprovou na seguinte. Qualquer comparação de bytes, digest ou tamanho
é, portanto, inutilizável: ou reprova sozinha, ou passa vazia (todo
`assertNotEqual` entre bytes vira verdadeiro por acidente).

Este arquivo não serializa PDF nenhum. Ele olha o **estilo computado** da árvore
de caixas do WeasyPrint, que é onde a dica de apresentação age e onde o resultado
é determinístico: com as dicas ligadas, `bgcolor="#ff0000"` vira fundo vermelho na
`<table>` e `color="#00ff00"` vira texto verde no `<font>`; desligadas, fundo
transparente e texto preto. É literalmente o que a CVE explora.
"""

from __future__ import annotations

import contextlib
from unittest import mock

import unittest

# O import é guardado porque o WeasyPrint depende de bibliotecas NATIVAS (Pango,
# GDK-Pixbuf) que a máquina de desenvolvimento Windows tipicamente não tem — e um
# módulo de teste que estoura no import derruba a coleta da suíte inteira com ERROR,
# não com skip. No CI, que instala as bibliotecas e é onde este gate justifica o
# ignore da CVE no `pip-audit`, o import funciona e os testes RODAM.
try:
    import weasyprint
except (ImportError, OSError):  # OSError: as .dll do Pango ausentes no Windows
    weasyprint = None

from django.test import SimpleTestCase

from documentos.services.adapters.weasyprint_pdf import render_pdf_bytes_weasyprint

# HTML que só um atacante escreveria: atributos de apresentação em vez de CSS.
HTML_COM_DICAS_DE_APRESENTACAO = """
<html><body>
  <table bgcolor="#ff0000" border="3" width="500">
    <tr><td><font color="#00ff00" size="7" face="Courier">conteúdo</font></td></tr>
  </table>
</body></html>
"""

VERMELHO = (1.0, 0.0, 0.0, 1.0)
VERDE = (0.0, 1.0, 0.0, 1.0)
TRANSPARENTE = (0.0, 0.0, 0.0, 0.0)
PRETO = (0.0, 0.0, 0.0, 1.0)


def _cores_por_tag(documento):
    """`{tag: {"fundo": {...}, "texto": {...}}}` do estilo computado de cada caixa."""
    cores: dict[str, dict[str, set]] = {}

    def andar(caixa):
        estilo = getattr(caixa, "style", None)
        tag = getattr(caixa, "element_tag", None)
        if estilo is not None and tag:
            registro = cores.setdefault(tag, {"fundo": set(), "texto": set()})
            registro["fundo"].add(tuple(estilo["background_color"]))
            registro["texto"].add(tuple(estilo["color"]))
        for filha in getattr(caixa, "children", ()) or ():
            andar(filha)

    for pagina in documento.pages:
        andar(pagina._page_box)
    return cores


@contextlib.contextmanager
def _espiar_render(*, forcar_hints=None):
    """Observa a chamada real e o que ela produz, sem serializar PDF.

    O adaptador faz `from weasyprint import HTML` **dentro** da função, então o
    alvo do patch é `weasyprint.HTML`, não um atributo do módulo adaptador.

    Além de registrar os kwargs, o espião roda `render()` no mesmo objeto e com o
    mesmo `presentational_hints` que o `write_pdf` vai usar. `render()` é a etapa
    de layout — a que aplica (ou não) a dica de apresentação — e para nela evita a
    serialização, que é a parte não determinística.
    """
    chamadas: list[dict] = []
    HTMLOriginal = weasyprint.HTML

    class HTMLEspiao(HTMLOriginal):
        def write_pdf(self, *args, **kwargs):
            if forcar_hints is not None:
                kwargs["presentational_hints"] = forcar_hints
            hints = kwargs.get("presentational_hints", False)
            chamadas.append(
                {
                    "presentational_hints": hints,
                    "cores": _cores_por_tag(
                        self.render(
                            stylesheets=kwargs.get("stylesheets"),
                            presentational_hints=hints,
                        )
                    ),
                }
            )
            return super().write_pdf(*args, **kwargs)

    with mock.patch.object(weasyprint, "HTML", HTMLEspiao):
        yield chamadas


@unittest.skipUnless(
    weasyprint is not None,
    "WeasyPrint sem bibliotecas nativas; motor opcional também no CI.",
)
class WeasyPrintSecurityTests(SimpleTestCase):
    def _render(self, *, forcar_hints=None):
        with _espiar_render(forcar_hints=forcar_hints) as chamadas:
            # O que está sob teste é o adaptador, não o motor de template.
            with mock.patch(
                "documentos.services.adapters.weasyprint_pdf.render_to_string",
                return_value=HTML_COM_DICAS_DE_APRESENTACAO,
            ):
                render_pdf_bytes_weasyprint(
                    html_template_name="irrelevante.html",
                    context={},
                    stylesheet_paths=(),
                )
        self.assertEqual(len(chamadas), 1, msg=f"esperava uma renderização, houve {len(chamadas)}")
        return chamadas[0]

    def test_o_adaptador_desliga_as_dicas_na_chamada_real(self):
        """Substitui o `inspect.getsource`: lê o argumento que de fato chegou ao WeasyPrint.

        Mover a flag para um dict de kwargs continua passando — como deve. Abrir um
        caminho de renderização que não a passe reprova aqui.
        """
        chamada = self._render()

        self.assertIs(
            chamada["presentational_hints"],
            False,
            msg=f"o adaptador chamou write_pdf com {chamada['presentational_hints']!r}",
        )

    def test_o_documento_gerado_ignora_bgcolor_e_color_do_html(self):
        """A asserção que sustenta a CVE, no estilo computado do documento real."""
        cores = self._render()["cores"]

        self.assertNotIn(
            VERMELHO,
            cores["table"]["fundo"],
            msg="o `bgcolor` do HTML pintou a tabela — a mitigação regrediu",
        )
        self.assertNotIn(
            VERDE,
            cores["font"]["texto"],
            msg="o `color` do HTML pintou o texto — a mitigação regrediu",
        )
        self.assertEqual(cores["table"]["fundo"], {TRANSPARENTE})
        self.assertEqual(cores["font"]["texto"], {PRETO})

    def test_com_as_dicas_ligadas_o_html_de_teste_pinta_de_verdade(self):
        """Guarda contra o teste virar vácuo.

        Se o HTML de teste deixar de exercitar as dicas, ou se a flag deixar de ter
        efeito, este teste reprova antes que o de cima passe por vazio.
        """
        cores = self._render(forcar_hints=True)["cores"]

        self.assertIn(VERMELHO, cores["table"]["fundo"])
        self.assertIn(VERDE, cores["font"]["texto"])
