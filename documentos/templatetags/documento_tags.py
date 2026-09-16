"""Tags dos templates de documento (prévia A4 e PDF).

`{% editavel "campo" %}` liga um trecho ao campo do model de onde ele veio.
No modo `editor` emite os atributos que o editor documental lê; no modo `pdf`
não emite nada — o mesmo template serve aos dois. Só marca campos que estão
em `campos_editaveis` (o registro explícito do backend decide, nunca o
template).

`{% bloco "chave" %}texto padrão{% endbloco %}` é um parágrafo documental: o
texto padrão vem do template; se houver override gravado em `blocos`, vale o
override. No modo editor o parágrafo leva a chave, para ser editado.

`|linhas` troca quebras de linha por `<br>` com o texto escapado — os textos
calculados do documento (colunas de servidor, custeio, roteiro) usam `\\n`.
"""

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def editavel(context, campo):
    if context.get("modo") != "editor":
        return ""
    campos = context.get("campos_editaveis") or {}
    if campo not in campos:
        return ""
    return format_html('data-doc-campo="{}" class="doc-editavel" tabindex="0"', campo)


@register.tag(name="bloco")
def bloco_tag(parser, token):
    try:
        _, chave = token.split_contents()
    except ValueError as exc:
        raise template.TemplateSyntaxError("{% bloco %} exige a chave do bloco") from exc
    nodelist = parser.parse(("endbloco",))
    parser.delete_first_token()
    return BlocoNode(chave.strip("\"'"), nodelist)


class BlocoNode(template.Node):
    def __init__(self, chave, nodelist):
        self.chave = chave
        self.nodelist = nodelist

    def render(self, context):
        padrao = self.nodelist.render(context).strip()
        blocos = context.get("blocos") or {}
        atual = blocos.get(self.chave)
        texto = atual["conteudo"] if atual and atual.get("conteudo") is not None else padrao
        atributos = ""
        if context.get("modo") == "editor":
            atributos = format_html(' data-doc-bloco="{}" class="doc-bloco doc-editavel" tabindex="0"', self.chave)
            if atual and atual.get("editado"):
                atributos += mark_safe(' data-doc-override="1"')
        else:
            atributos = mark_safe(' class="doc-bloco"')
        return format_html("<p{}>{}</p>", atributos, linhas(texto))


@register.filter(name="linhas", is_safe=True)
def linhas(valor):
    texto = "" if valor is None else str(valor)
    return mark_safe("<br>".join(escape(parte) for parte in texto.split("\n")))
