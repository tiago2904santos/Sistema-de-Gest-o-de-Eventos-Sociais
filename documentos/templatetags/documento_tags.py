"""Tags dos templates de documento (prévia A4 e PDF).

`{% editavel "campo" %}` liga um trecho ao campo do model de onde ele veio.
No modo `editor` emite os atributos que o editor documental lê; no modo `pdf`
não emite nada — o mesmo template serve aos dois. Só marca campos que estão
em `campos_editaveis` (o registro explícito do backend decide, nunca o
template).

`{% bloco "chave" %}` é um parágrafo documental: o texto padrão vem do
registro (documentos/editor/blocos.py) já resolvido em `blocos`; se houver
override gravado, vale o override. Com edição ligada, o parágrafo leva a
chave, para ser editado. `{% ponto_de_quebra "chave" %}` é onde uma quebra
de página pode existir; ativa em `quebras`, vira a quebra.

`|linhas` troca quebras de linha por `<br>` com o texto escapado — os textos
calculados do documento (colunas de servidor, custeio, roteiro) usam `\\n`.
"""

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def editavel(context, campo, objeto=None, classe=""):
    """Marca o trecho para o editor. O que é texto sai como campo de digitação
    da própria folha (`contenteditable`), para se escrever no documento como
    num editor de texto; o que é escolha, alternância ou busca em registros
    segue clicável, com o controle que o tipo pede.

    `objeto` é o id do registro do trecho quando há vários da mesma espécie
    (a linha de um servidor da equipe). A origem vai junto: o navegador guarda
    a versão de cada registro para o controle de concorrência.

    `classe` são as classes do próprio elemento: a tag as emite junto das
    suas (um elemento não pode ter dois atributos `class`). O que a tag emite
    começa com espaço: escrita colada ao nome do elemento (`<td{% editavel %}>`),
    o PDF sai com a marcação de sempre."""
    propria = format_html(' class="{}"', classe) if classe else ""
    if context.get("modo") != "editor":
        return propria
    campos = context.get("campos_editaveis") or {}
    dados = campos.get(campo)
    if dados is None:
        return propria
    extra = f" {classe}" if classe else ""
    extras = format_html(' data-doc-origem="{}"', dados.get("origem") or "oficio")
    if objeto not in (None, ""):
        extras += format_html(' data-doc-objeto="{}"', objeto)
    if dados.get("digitavel"):
        # `plaintext-only` mantém o texto sem formatação colada de fora; onde o
        # navegador não o conhece, cai em `true` e a colagem é limpa no script.
        return format_html(
            ' data-doc-campo="{}" data-doc-parte="{}" data-doc-digitavel="{}"{}'
            ' class="doc-editavel doc-editavel--texto{}"'
            ' contenteditable="plaintext-only" spellcheck="true"',
            campo,
            dados.get("parte") or campo,
            "varias" if dados.get("multilinha") else "uma",
            extras,
            extra,
        )
    return format_html(' data-doc-campo="{}"{} class="doc-editavel{}" tabindex="0"', campo, extras, extra)


class TrechoNode(template.Node):
    def __init__(self, campo, objeto, nodelist):
        self.campo, self.objeto, self.nodelist = campo, objeto, nodelist

    def render(self, context):
        conteudo = self.nodelist.render(context)
        campo = self.campo.resolve(context)
        objeto = self.objeto.resolve(context) if self.objeto is not None else None
        atributos = editavel(context, campo, objeto)
        if not atributos:
            return conteudo
        return format_html("<span{}>{}</span>", atributos, mark_safe(conteudo))


@register.tag
def trecho(parser, token):
    """`{% trecho "campo" [objeto] %}texto{% endtrecho %}`: no editor, o texto
    vira um trecho marcado (um `<span>` com os atributos de `editavel`); fora
    dele — no PDF, ou campo que quem vê não edita —, sai só o texto, sem
    elemento a mais: o PDF continua idêntico ao que era."""
    partes = token.split_contents()
    if len(partes) not in (2, 3):
        raise template.TemplateSyntaxError("trecho recebe o campo e, opcionalmente, o id do registro.")
    nodelist = parser.parse(("endtrecho",))
    parser.delete_first_token()
    campo = parser.compile_filter(partes[1])
    objeto = parser.compile_filter(partes[2]) if len(partes) == 3 else None
    return TrechoNode(campo, objeto, nodelist)


@register.simple_tag(takes_context=True)
def vazio(context, rotulo):
    """No editor, o lugar de um dado que ainda não existe (unidade, nome do
    destinatário...): um texto cinza para ter onde clicar e preencher. No PDF,
    nada — o documento sai como sempre saiu."""
    if context.get("modo") != "editor" or not context.get("campos_editaveis"):
        return ""
    return format_html('<span class="doc-vazio">{}</span>', rotulo)


def _editando(context):
    return context.get("modo") == "editor" and bool(context.get("edicao"))


def _texto_do_bloco(texto, negrito_ate):
    """O texto com quebras em <br>; com `negrito_ate`, o começo até o primeiro
    `negrito_ate` (inclusive) sai em negrito — o vocativo "Senhor Delegado,"."""
    if negrito_ate and negrito_ate in texto:
        inicio, _, resto = texto.partition(negrito_ate)
        return format_html("<strong>{}</strong>{}", linhas(inicio + negrito_ate), linhas(resto))
    return linhas(texto)


@register.simple_tag(takes_context=True)
def bloco(context, chave, classe="", assunto=None, negrito_ate="", padrao=None, elemento="p", base=True):
    """Parágrafo do modelo: texto padrão do registro (documentos/editor/blocos.py)
    ou o override gravado. Chave fora do registro não rende nada — a menos que
    o template dê um `padrao`, para trechos comuns a documentos que não
    registram o bloco (a linha da secretaria no cabeçalho de todos).

    `classe` junta classes do documento ao parágrafo; `assunto` preenche o
    marcador `{assunto}` do texto; `negrito_ate` põe o começo em negrito;
    `elemento` troca o parágrafo por um trecho na linha (`span`) ou um título;
    `base=False` deixa só as classes do documento (sem o estilo genérico de
    `.doc-bloco`), para o texto sair como o elemento que ele substitui."""
    if elemento not in ("p", "span", "h1", "h2"):
        elemento = "p"
    dados = (context.get("blocos") or {}).get(chave)
    extra = f" {classe}" if classe else ""
    propria = ("doc-bloco" + extra) if base else classe
    if dados is None:
        if padrao is None:
            return ""
        return format_html('<{} class="{}">{}</{}>', elemento, propria, linhas(padrao), elemento)
    texto = dados.get("conteudo")
    if texto is None:
        texto = dados.get("padrao", "")
    if assunto is not None:
        texto = texto.replace("{assunto}", str(assunto))
    if _editando(context):
        # Parágrafo do modelo é texto puro: escreve-se nele direto na folha.
        atributos = format_html(
            ' data-doc-bloco="{}" data-doc-digitavel="varias"'
            ' class="{} doc-editavel doc-editavel--texto"'
            ' contenteditable="plaintext-only" spellcheck="true"',
            chave, propria,
        )
        if dados.get("editado"):
            atributos += mark_safe(' data-doc-override="1"')
    elif not propria and elemento == "span":
        # Trecho na linha sem classe própria, fora do editor: só o texto.
        return _texto_do_bloco(texto, negrito_ate)
    else:
        atributos = format_html(' class="{}"', propria) if propria else ""
    return format_html("<{}{}>{}</{}>", elemento, atributos, _texto_do_bloco(texto, negrito_ate), elemento)


@register.simple_tag(takes_context=True)
def ponto_de_quebra(context, chave):
    """Onde o template admite uma quebra de página. Ativa, é a quebra (no PDF
    vira página nova); no editor, inativa é uma fenda onde se pode inserir."""
    ativa = chave in (context.get("quebras") or ())
    if _editando(context):
        if ativa:
            return format_html('<div class="doc-quebra" data-doc-quebra="{}" data-doc-quebra-ativa="1" tabindex="0" title="Remover a quebra de página"></div>', chave)
        return format_html('<div class="doc-quebra-slot" data-doc-quebra="{}" tabindex="0" title="Inserir quebra de página aqui"></div>', chave)
    return mark_safe('<div class="doc-quebra"></div>') if ativa else ""


@register.filter(name="linhas", is_safe=True)
def linhas(valor):
    texto = "" if valor is None else str(valor)
    return mark_safe("<br>".join(escape(parte) for parte in texto.split("\n")))


@register.simple_tag
def documento_embutido(chave, pk, titulo, variante=""):
    """O documento para o visualizador do formulário
    (`documentos/editor/_visualizador.html`), numa lista de um:
    `{% documento_embutido "ordem_servico" ordem.pk "Ordem de serviço" as documentos %}`."""
    from documentos.editor.pagina import cartao

    return [cartao(chave, pk, titulo, variante)] if pk else []
