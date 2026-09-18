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
def editavel(context, campo):
    """Marca o trecho para o editor. O que é texto sai como campo de digitação
    da própria folha (`contenteditable`), para se escrever no documento como
    num editor de texto; o que é escolha, alternância ou busca em registros
    segue clicável, com o controle que o tipo pede."""
    if context.get("modo") != "editor":
        return ""
    campos = context.get("campos_editaveis") or {}
    dados = campos.get(campo)
    if dados is None:
        return ""
    if dados.get("digitavel"):
        # `plaintext-only` mantém o texto sem formatação colada de fora; onde o
        # navegador não o conhece, cai em `true` e a colagem é limpa no script.
        return format_html(
            'data-doc-campo="{}" data-doc-parte="{}" data-doc-digitavel="{}"'
            ' class="doc-editavel doc-editavel--texto"'
            ' contenteditable="plaintext-only" spellcheck="true"',
            campo,
            dados.get("parte") or campo,
            "varias" if dados.get("multilinha") else "uma",
        )
    return format_html('data-doc-campo="{}" class="doc-editavel" tabindex="0"', campo)


def _editando(context):
    return context.get("modo") == "editor" and bool(context.get("edicao"))


@register.simple_tag(takes_context=True)
def bloco(context, chave):
    """Parágrafo do modelo: texto padrão do registro (documentos/editor/blocos.py)
    ou o override gravado. Chave fora do registro não rende nada."""
    dados = (context.get("blocos") or {}).get(chave)
    if dados is None:
        return ""
    texto = dados.get("conteudo")
    if texto is None:
        texto = dados.get("padrao", "")
    if _editando(context):
        # Parágrafo do modelo é texto puro: escreve-se nele direto na folha.
        atributos = format_html(
            ' data-doc-bloco="{}" data-doc-digitavel="varias"'
            ' class="doc-bloco doc-editavel doc-editavel--texto"'
            ' contenteditable="plaintext-only" spellcheck="true"',
            chave,
        )
        if dados.get("editado"):
            atributos += mark_safe(' data-doc-override="1"')
    else:
        atributos = mark_safe(' class="doc-bloco"')
    return format_html("<p{}>{}</p>", atributos, linhas(texto))


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
