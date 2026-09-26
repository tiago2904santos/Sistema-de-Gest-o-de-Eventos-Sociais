"""Virada de exercício: os lotes do novo ano a partir dos do ano que termina.

Todo ano cada contrato ganha um lote novo (Lote 1 – 2026, Lote 1 – 2027…)
com a mesma lista de municípios, orientações e especificações, mudando só a
quantidade e o empenho. O assistente copia os lotes vigentes do ano, pede a
quantidade e o empenho de cada um e, se pedido, encerra os do ano anterior.

Enquanto os dois anos ficam vigentes, a escolha do lote pelo município já
prefere o do exercício da data do evento (`services.EscolhaDeLotes`).
"""

from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from . import services
from .models import LoteCoffeeBreak


def exercicio_de_origem():
    """O maior exercício (numérico) entre os lotes vigentes; None sem lotes."""
    anos = [int(e) for e in LoteCoffeeBreak.objects.filter(ativo=True).values_list("exercicio", flat=True) if e.isdigit()]
    return max(anos) if anos else None


def lotes_de_origem(ano):
    return list(
        LoteCoffeeBreak.objects.filter(ativo=True, exercicio=str(ano))
        .select_related("contrato__fornecedor")
        .prefetch_related("contrato__aditivos", "municipios")
        .order_by("contrato__numero", "numero")
    )


def impedimento(lote, destino):
    """Por que o lote não pode ir para o ano `destino` ("" quando pode)."""
    if LoteCoffeeBreak.objects.filter(contrato=lote.contrato, numero=lote.numero, exercicio=str(destino)).exists():
        return f"O Lote {lote.numero} ({destino}) deste contrato já existe."
    fim = services.fim_da_vigencia(lote.contrato)
    if fim and fim < date(destino, 1, 1):
        return f"Contrato vencido em {fim:%d/%m/%Y}: providencie o aditivo de prorrogação antes."
    return ""


def aviso_de_vigencia(lote, destino):
    """A vigência acaba durante o ano novo: o lote pode ser criado, com aviso."""
    fim = services.fim_da_vigencia(lote.contrato)
    if fim and date(destino, 1, 1) <= fim < date(destino, 12, 31):
        return f"O contrato vai até {fim:%d/%m/%Y}: o lote de {destino} só cobre eventos até lá."
    return ""


class LinhaViradaForm(forms.Form):
    lote = forms.IntegerField(widget=forms.HiddenInput)
    criar = forms.BooleanField(required=False)
    quantidade_total = forms.IntegerField(min_value=1, required=False)
    empenho = forms.CharField(max_length=30, required=False)
    valor_empenho = forms.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=0)

    def clean(self):
        dados = super().clean()
        if dados.get("criar") and not dados.get("quantidade_total"):
            self.add_error("quantidade_total", "Informe a quantidade do novo exercício.")
        return dados


ViradaFormSet = forms.formset_factory(LinhaViradaForm, extra=0)


def iniciais(lotes, destino):
    return [
        {"lote": lote.pk, "criar": not impedimento(lote, destino), "quantidade_total": lote.quantidade_total}
        for lote in lotes
    ]


@transaction.atomic
def abrir_exercicio(linhas, destino, desativar_anteriores=False):
    """Cria os lotes do ano `destino` das linhas marcadas; devolve os criados.

    Cada linha: o lote de origem e o que o formulário trouxe (quantidade,
    empenho e valor do empenho). Copia municípios, a lista original,
    orientações e especificações técnicas.
    """
    criados = []
    for origem, dados in linhas:
        motivo = impedimento(origem, destino)
        if motivo:
            raise ValidationError(f"{origem.rotulo_curto} — {origem.contrato.numero}: {motivo}")
        novo = LoteCoffeeBreak.objects.create(
            contrato=origem.contrato,
            numero=origem.numero,
            exercicio=str(destino),
            quantidade_total=dados["quantidade_total"],
            empenho=(dados.get("empenho") or "").strip(),
            valor_empenho=dados.get("valor_empenho"),
            municipios_texto=origem.municipios_texto,
            orientacoes=origem.orientacoes,
            especificacoes_tecnicas=origem.especificacoes_tecnicas,
            observacoes=f"Aberto na virada do exercício a partir do {origem.rotulo_curto}.",
            ativo=True,
        )
        novo.municipios.set(origem.municipios.all())
        criados.append(novo)
        if desativar_anteriores:
            origem.ativo = False
            origem.save(update_fields=["ativo", "atualizado_em"])
    return criados
