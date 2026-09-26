"""Resultados do Plano de Trabalho: o que foi realizado de cada atividade.

Depois do evento, a coordenação lança os números (CIN emitidas, orientações,
atendimentos) uma vez. Eles viram o relatório final do plano e a sugestão
dos campos "Objetivo da participação" e "Conclusão" do Relatório Técnico das
prestações de contas dos ofícios da mesma viagem — sem redigitar.
"""

from __future__ import annotations

from django.db import transaction

from .models import PlanoTrabalho, ResultadoAtividade


def atividades_do_plano(plano):
    """As atividades previstas (no plano de vários eventos, a união de todos)."""
    from .services import _atividades_combinadas_multi, _atividades_selecionadas_ordenadas

    if plano.is_multi_evento and plano.pk:
        return _atividades_combinadas_multi(plano)
    return _atividades_selecionadas_ordenadas(plano)


def linhas_de_resultado(plano):
    """[{atividade, realizado, observacao}] na ordem das atividades previstas.

    Resultado lançado para atividade que depois saiu do plano continua na
    lista: o número foi realizado e não some por causa de uma edição.
    """
    existentes = {r.atividade_id: r for r in plano.resultados.select_related("atividade")}
    linhas = []
    for atividade in atividades_do_plano(plano):
        resultado = existentes.pop(atividade.pk, None)
        linhas.append({
            "atividade": atividade,
            "realizado": resultado.realizado if resultado else None,
            "observacao": resultado.observacao if resultado else "",
        })
    for resultado in existentes.values():
        linhas.append({
            "atividade": resultado.atividade,
            "realizado": resultado.realizado,
            "observacao": resultado.observacao,
        })
    return linhas


def _inteiro(valor):
    texto = str(valor or "").strip().replace(".", "")
    if not texto:
        return None
    try:
        numero = int(texto)
    except ValueError as exc:
        raise ValueError(f"\"{valor}\" não é um número inteiro.") from exc
    if numero < 0:
        raise ValueError("O realizado não pode ser negativo.")
    return numero


@transaction.atomic
def salvar_resultados(plano, dados) -> list[str]:
    """Grava {atividade_pk: (realizado, observacao)}; devolve os erros.

    Linha sem número e sem observação apaga o resultado: é o jeito de
    desfazer um lançamento.
    """
    erros = []
    permitidas = {a.pk: a for a in atividades_do_plano(plano)}
    permitidas.update({r.atividade_id: r.atividade for r in plano.resultados.select_related("atividade")})
    for atividade_pk, (realizado, observacao) in dados.items():
        atividade = permitidas.get(atividade_pk)
        if atividade is None:
            continue
        try:
            numero = _inteiro(realizado)
        except ValueError as exc:
            erros.append(f"{atividade.nome}: {exc}")
            continue
        observacao = (observacao or "").strip()
        if numero is None and not observacao:
            ResultadoAtividade.objects.filter(plano=plano, atividade=atividade).delete()
            continue
        ResultadoAtividade.objects.update_or_create(
            plano=plano, atividade=atividade,
            defaults={"realizado": numero, "observacao": observacao},
        )
    return erros


def _linha_texto(linha):
    partes = [linha["atividade"].nome]
    if linha["realizado"] is not None:
        partes.append(f": {linha['realizado']}")
    texto = "".join(partes)
    if linha["observacao"]:
        texto += f" ({linha['observacao']})"
    return f"• {texto}"


def _lancadas(plano):
    return [l for l in linhas_de_resultado(plano) if l["realizado"] is not None or l["observacao"]]


def texto_do_relatorio(plano) -> str:
    """O relatório final do plano: onde, quando, o que foi realizado e a conclusão."""
    from .services import _municipio_display

    lancadas = _lancadas(plano)
    if not lancadas:
        return ""
    cabecalho = f"Plano de Trabalho {plano.numero_formatado}"
    if plano.programa_display:
        cabecalho += f" — {plano.programa_display}"
    linhas = [
        cabecalho,
        f"Local: {_municipio_display(plano)}. Período: {plano.periodo_display}.",
        "",
        "Resultados alcançados:",
        *[_linha_texto(l) for l in lancadas],
    ]
    total = sum(l["realizado"] or 0 for l in lancadas)
    if total:
        linhas.append(f"Total de atendimentos registrados: {total}.")
    if (plano.consideracao_final or "").strip():
        linhas += ["", plano.consideracao_final.strip()]
    return "\n".join(linhas)


def plano_com_resultados_da_viagem(viagem):
    """O plano ativo da viagem que tem resultados lançados (o mais recente)."""
    if viagem is None:
        return None
    return (
        PlanoTrabalho.objects.filter(viagem=viagem, cancelado=False, resultados__isnull=False)
        .distinct()
        .order_by("-atualizado_em", "-pk")
        .first()
    )


def sugestao_para_rt(oficio) -> dict:
    """{"atividade", "conclusao"} para o RT da prestação do ofício, ou {}.

    Vem do plano da mesma viagem com resultados lançados. Só sugestão: a tela
    do RT usa como valor inicial dos campos ainda vazios.
    """
    from .services import _municipio_display

    plano = plano_com_resultados_da_viagem(getattr(oficio, "viagem", None))
    if plano is None:
        return {}
    lancadas = _lancadas(plano)
    atividades = "; ".join(l["atividade"].nome for l in lancadas)
    onde = _municipio_display(plano)
    objetivo = f"Participação na ação em {onde}"
    if plano.programa_display:
        objetivo += f" ({plano.programa_display})"
    objetivo += f", com as atividades: {atividades}."
    realizados = [f"{l['atividade'].nome}: {l['realizado']}" for l in lancadas if l["realizado"] is not None]
    conclusao = ""
    if realizados:
        conclusao = f"Foram realizados: {'; '.join(realizados)}."
    if (plano.consideracao_final or "").strip():
        conclusao = f"{conclusao} {plano.consideracao_final.strip()}".strip()
    return {"atividade": objetivo, "conclusao": conclusao}
