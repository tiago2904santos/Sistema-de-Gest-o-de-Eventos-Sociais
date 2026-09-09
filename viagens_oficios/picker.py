"""Utilitários para seleção de ofícios e preservação dos valores do formulário."""

from __future__ import annotations

from django.forms.models import ModelChoiceIteratorValue


# Teto do que a busca devolve numa tacada. Não é paginação: o seletor é para
# encontrar um ofício, e quem digita algo que casa com mais de 30 refina a busca
# em vez de rolar. O teto mora no servidor porque o cliente não é confiável.
LIMITE_BUSCA = 30


def _como_pk(valor):
    """Aceita pk cru ou instância.

    `ModelMultipleChoiceField` num `ModelForm` recebe `initial` de
    `model_to_dict`, e para campo M2M isso são **instâncias**, não pks
    (`ManyToManyField.value_from_object`). Para FK são pks. Os dois caminhos
    passam por aqui.
    """
    return getattr(valor, "pk", valor)


def pks_ja_escolhidos(form, nome_do_campo):
    """Os pks que o formulário já tem selecionados, como lista de strings.

    Quando o formulário está *bound* — re-render depois de erro de validação — a
    escolha está em `form.data`, não em `initial`. Sem ler de lá, o que a pessoa
    acabou de escolher sumiria da tela junto com a mensagem de erro.
    """
    if form.is_bound:
        dados = form.data
        chave = form.add_prefix(nome_do_campo)
        brutos = dados.getlist(chave) if hasattr(dados, "getlist") else [dados.get(chave)]
    else:
        bruto = form.initial.get(nome_do_campo)
        brutos = list(bruto) if isinstance(bruto, (list, tuple, set)) else [bruto]
    return [str(_como_pk(valor)) for valor in brutos if str(_como_pk(valor) or "").isdigit()]


def oficios_ja_escolhidos(form, nome_do_campo):
    """Ofícios selecionados, respeitando os filtros do campo."""
    campo = form.fields[nome_do_campo]
    pks = pks_ja_escolhidos(form, nome_do_campo)
    return campo.queryset.filter(pk__in=pks) if pks else campo.queryset.none()


def renderizar_so_os_escolhidos(form, nome_do_campo):
    """Renderiza opções selecionadas preservando o queryset de validação."""
    campo = form.fields[nome_do_campo]
    escolhas = []
    if getattr(campo, "empty_label", None) is not None:
        escolhas.append(("", campo.empty_label))
    escolhas += [
        (ModelChoiceIteratorValue(oficio.pk, oficio), campo.label_from_instance(oficio))
        for oficio in oficios_ja_escolhidos(form, nome_do_campo)
    ]
    campo.widget.choices = escolhas


def dados_do_option(oficio, *, resumo, rotulo, decorar=False):
    """Dados de apresentação de uma opção de ofício."""
    dados = {
        "texto": rotulo(oficio),
        "search": " ".join(
            parte for parte in [resumo.get("search_text") or "", str(oficio.pk)] if parte
        ),
    }
    if decorar:
        protocolo = oficio.protocolo or ""
        assunto = oficio.assunto or ""
        dados["main"] = rotulo(oficio)
        dados["meta"] = " - ".join(parte for parte in [protocolo, assunto] if parte)
    return dados
