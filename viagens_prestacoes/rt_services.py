"""Persistência do relatório técnico e do valor de diária por servidor.

`BE-14` fatia 1. Estas três funções moravam em `rt_views.py` como helpers privados
(`_salvar_diaria_overrides`, `_salvar_rt_autosave`) e gravavam **fora de transação**:
o laço de diárias fazia um `UPDATE` por servidor, e uma falha no terceiro deixava os
dois primeiros gravados. É dinheiro por servidor.

**O que a transação aqui não faz, e é de propósito.** Uma diária **recusada pela regra**
continua não desfazendo o texto do RT já gravado — `salvar_diarias_recebidas` devolve os
erros em `ResultadoSalvarRT.erros` em vez de levantar exceção, então a transação commita
normalmente. A decisão está em `rt_views.py` desde antes desta fatia:

    Salvar automaticamente um valor que a regra proíbe seria pior que devolver
    erro: ninguém revisa o que salvou sozinho.

`viagens_prestacoes/test_rt_transacao_be14.py` trava as duas metades: a que a transação
tem de garantir (falha no meio do laço não deixa meia gravação) e a que ela não pode
revogar (texto do RT sobrevive à diária recusada).

A regra do valor continua em `services.aplicar_diaria_recebida` — ela já estava no lugar
certo. O que muda é que quem fecha o laço e grava passa a ser service, não view.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field

from django.db import transaction

from core.autosave import filter_allowed_fields
from core.normalizers import normalize_spaces

from .forms import CAMPOS_CUSTEIO_COM_OUTRO
from .forms import OUTRO_VALUE
from .forms import get_custeio_valores_fixos
from .models import PrestacaoServidor
from .models import RelatorioTecnico
from .services import aplicar_diaria_recebida
from .services import marcar_servidor_em_preenchimento
from .services import marcar_servidores_pendentes

#: Campos do RT que o autosave aceita. Estavam escritos duas vezes, palavra por
#: palavra, em `rt_servidor_autosave` e `rt_autosave`.
CAMPOS_AUTOSAVE_RT = frozenset(
    {
        "diaria",
        "translado",
        "combustivel",
        "passagem",
        "translado_outro",
        "combustivel_outro",
        "passagem_outro",
        "motivo",
        "atividade",
        "conclusao",
        "medidas",
        "info_complementares",
    }
)

#: Qual status marcar depois de gravar. É a **única** diferença entre as duas rotas de
#: autosave do RT, e passá-la explicitamente é o que a torna visível: a rota por servidor
#: marca só o servidor da URL; a por relatório marca a equipe pendente inteira.
ESCOPO_SERVIDOR = "servidor"
ESCOPO_EQUIPE = "equipe"

_CAMPO_DIARIA = re.compile(r"^ps-(\d+)-diaria_valor_override$")


@dataclass(frozen=True)
class ResultadoSalvarRT:
    """O que a gravação do RT fez. A view traduz isto em `messages` ou em JSON.

    `erros` é **retorno, não exceção**: um valor de diária recusado pela regra não
    derruba o resto do formulário, e é por isso que a transação em volta commita.
    """

    erros: dict[str, list[str]] = field(default_factory=dict)
    texto_gravado: bool = False
    servidores_gravados: int = 0

    @property
    def ok(self) -> bool:
        return not self.erros


def obter_ou_criar_relatorio_tecnico(prestacao) -> RelatorioTecnico:
    """O RT da prestação, criado na primeira visita à tela.

    Fica no service e não em `selectors.py` porque `get_or_create` **grava**
    (`docs/PADRAO_SELECTORS.md`: selector é consulta). Era o único acesso de manager
    que sobrava em `rt_views.py` junto com o do laço de diárias.
    """
    relatorio, _ = RelatorioTecnico.objects.get_or_create(prestacao=prestacao)
    return relatorio


@transaction.atomic
def salvar_diarias_recebidas(prestacao, campos) -> ResultadoSalvarRT:
    """Grava `ps-<pk>-diaria_valor_override` para os servidores presentes em `campos`.

    Atômica porque grava **em laço**, um `UPDATE` por servidor: sem ela, uma falha no
    meio deixa parte da equipe com o valor novo e parte com o antigo, sem nada na tela
    dizendo qual é qual.
    """
    atualizacoes = {}
    for nome, valor in campos.items():
        match = _CAMPO_DIARIA.match(str(nome or ""))
        if match:
            atualizacoes[int(match.group(1))] = normalize_spaces(valor or "")
    if not atualizacoes:
        return ResultadoSalvarRT()

    erros: dict[str, list[str]] = {}
    gravados = 0
    servidores = PrestacaoServidor.objects.filter(
        pk__in=atualizacoes.keys(), prestacao=prestacao
    )
    for servidor_prestacao in servidores:
        texto = atualizacoes.get(servidor_prestacao.pk, "")
        anterior = (
            servidor_prestacao.diaria_valor_override,
            servidor_prestacao.diaria_valor_override_observacao,
        )
        problemas = aplicar_diaria_recebida(servidor_prestacao, texto)
        if problemas:
            # Não grava nada deste servidor: um valor recusado não pode virar meia
            # gravação. O autosave devolve o erro no nome do campo, e a tela mostra ao
            # lado do input que o operador acabou de digitar.
            erros[f"ps-{servidor_prestacao.pk}-diaria_valor_override"] = problemas
            continue
        atual = (
            servidor_prestacao.diaria_valor_override,
            servidor_prestacao.diaria_valor_override_observacao,
        )
        if atual != anterior:
            servidor_prestacao.save(
                update_fields=[
                    "diaria_valor_override",
                    "diaria_valor_override_observacao",
                    "atualizado_em",
                ]
            )
            gravados += 1
    return ResultadoSalvarRT(erros=erros, servidores_gravados=gravados)


def _aplicar_campos_do_rt(relatorio: RelatorioTecnico, campos) -> bool:
    """Escreve em memória os campos aceitos e persiste numa gravação só."""
    if not campos:
        return False
    com_outro = {item[0] for item in CAMPOS_CUSTEIO_COM_OUTRO}
    update_fields = set()
    for campo, valor in campos.items():
        if campo.endswith("_outro"):
            base = campo.removesuffix("_outro")
            if base in com_outro:
                texto = normalize_spaces(valor or "")
                if texto:
                    setattr(relatorio, base, texto)
                    update_fields.add(base)
            continue
        if campo in com_outro:
            texto = normalize_spaces(valor or "")
            if texto == OUTRO_VALUE:
                continue
            if texto in get_custeio_valores_fixos(campo):
                setattr(relatorio, campo, texto)
                update_fields.add(campo)
            continue
        setattr(relatorio, campo, normalize_spaces(valor or ""))
        update_fields.add(campo)
    if not update_fields:
        return False
    relatorio.save(update_fields=[*update_fields, "atualizado_em"])
    return True


def _marcar(prestacao, servidor_prestacao, escopo) -> None:
    if escopo == ESCOPO_SERVIDOR:
        marcar_servidor_em_preenchimento(servidor_prestacao)
    else:
        marcar_servidores_pendentes(prestacao)


@transaction.atomic
def salvar_rt_do_autosave(
    relatorio: RelatorioTecnico,
    prestacao,
    *,
    fields,
    dirty_fields,
    escopo,
    servidor_prestacao=None,
) -> ResultadoSalvarRT:
    """Texto do RT, valores de diária e marcação de status, numa transação só.

    Recebe o payload já interpretado (`fields`/`dirty_fields`), nunca o `request` —
    `docs/PADRAO_SERVICES.md:20`. Os dois recortes são os que as views faziam:
    `filter_allowed_fields` para o texto (só o que é permitido **e** está sujo) e os
    nomes sujos crus para as diárias, que vêm com prefixo `ps-<pk>-`.

    `escopo` escolhe o que marcar: `ESCOPO_SERVIDOR` para a rota por servidor,
    `ESCOPO_EQUIPE` para a rota por relatório. As duas rotas sempre marcaram coisas
    diferentes; o parâmetro só torna isso explícito.
    """
    texto = _aplicar_campos_do_rt(
        relatorio, filter_allowed_fields(fields, dirty_fields, CAMPOS_AUTOSAVE_RT)
    )
    diarias = salvar_diarias_recebidas(
        prestacao, {nome: fields.get(nome) for nome in dirty_fields}
    )
    if diarias.erros:
        return ResultadoSalvarRT(erros=diarias.erros, texto_gravado=texto)
    if dirty_fields:
        _marcar(prestacao, servidor_prestacao, escopo)
    return ResultadoSalvarRT(
        texto_gravado=texto, servidores_gravados=diarias.servidores_gravados
    )


@transaction.atomic
def salvar_rt_do_formulario(
    form, prestacao, *, campos_diaria, servidor_prestacao
) -> ResultadoSalvarRT:
    """Caminho sem JS: o `ModelForm` do RT e as diárias na mesma transação.

    O form já validou; aqui só se grava. Recebe o form, não o `request` — a view
    continua dona de montar e validar (`docs/PADRAO_SERVICES.md:20`).
    """
    form.save()
    diarias = salvar_diarias_recebidas(prestacao, campos_diaria)
    marcar_servidor_em_preenchimento(servidor_prestacao)
    return ResultadoSalvarRT(
        erros=diarias.erros,
        texto_gravado=True,
        servidores_gravados=diarias.servidores_gravados,
    )


# ---------------------------------------------------------------------------
# m097 — o RT começa com o que o sistema já tem.
# ---------------------------------------------------------------------------

#: Os textos do RT que se sugerem, copiam e viram modelo.
CAMPOS_TEXTO_RT = ("motivo", "atividade", "conclusao", "medidas", "info_complementares")


def _juntar(*textos) -> str:
    return "\n\n".join(t.strip() for t in textos if (t or "").strip())


def plano_da_prestacao(prestacao):
    """O plano de trabalho da mesma viagem do ofício (o mais recente, não cancelado)."""
    viagem_id = getattr(prestacao.oficio, "viagem_id", None)
    if not viagem_id:
        return None
    from viagens_planos.models import PlanoTrabalho

    return (
        PlanoTrabalho.objects.filter(viagem_id=viagem_id, cancelado=False)
        .order_by("-atualizado_em", "-pk")
        .first()
    )


def sugestoes_iniciais_rt(prestacao) -> dict[str, str]:
    """Textos sugeridos para o RT a partir do ofício, da viagem e do plano de trabalho.

    - descrição do evento: o motivo do ofício; sem ele, a contextualização do plano;
    - objetivo da participação: o objetivo da viagem; sem ele, metas e atividades do plano;
    - conclusão: as considerações finais do plano.

    Só sugestão: a tela usa como valor inicial dos campos vazios, e nada é gravado
    até o operador salvar ou editar.
    """
    oficio = prestacao.oficio
    viagem = oficio.viagem if getattr(oficio, "viagem_id", None) else None
    plano = plano_da_prestacao(prestacao)
    sugestoes = {
        "motivo": (oficio.motivo or "").strip() or (plano.contextualizacao.strip() if plano else ""),
        "atividade": ((viagem.descricao or "").strip() if viagem else "")
        or (_juntar(plano.metas, plano.atividades) if plano else ""),
        "conclusao": (plano.consideracao_final or "").strip() if plano else "",
    }
    return {campo: texto for campo, texto in sugestoes.items() if texto}


def rts_para_copiar(prestacao, limite: int = 10) -> list[dict]:
    """RTs de outras prestações do mesmo evento (viagem) ou do mesmo destino, com texto.

    Os do mesmo evento vêm primeiro; depois os que dividem algum município de
    destino, dos mais recentes para os mais antigos.
    """
    from django.db.models import Q

    oficio = prestacao.oficio
    filtro = Q()
    viagem_id = getattr(oficio, "viagem_id", None)
    if viagem_id:
        filtro |= Q(prestacao__oficio__viagem_id=viagem_id)
    destinos = []
    if getattr(oficio, "roteiro_id", None):
        destinos = list(oficio.roteiro.destinos.values_list("municipio_id", flat=True))
    if destinos:
        filtro |= Q(prestacao__oficio__roteiro__destinos__municipio_id__in=destinos)
    if not filtro:
        return []
    tem_texto = Q()
    for campo in CAMPOS_TEXTO_RT:
        tem_texto |= ~Q(**{campo: ""})
    candidatos = (
        RelatorioTecnico.objects.filter(filtro)
        .filter(tem_texto)
        .exclude(prestacao=prestacao)
        .select_related("prestacao__oficio")
        .distinct()
        .order_by("-atualizado_em", "-pk")[: limite * 3]
    )
    mesmos_evento = []
    mesmo_destino = []
    for rt in candidatos:
        outro = rt.prestacao.oficio
        mesmo = bool(viagem_id) and outro.viagem_id == viagem_id
        item = {
            "id": rt.pk,
            "rotulo": f"Ofício {outro.numero_formatado} · {'mesmo evento' if mesmo else 'mesmo destino'}",
            "textos": {campo: getattr(rt, campo) or "" for campo in CAMPOS_TEXTO_RT},
        }
        (mesmos_evento if mesmo else mesmo_destino).append(item)
    return (mesmos_evento + mesmo_destino)[:limite]


def criar_modelo_do_campo(campo: str, nome: str, texto: str):
    """Grava o texto atual de um campo do RT como modelo reutilizável (m097).

    O nome repetido no mesmo campo ganha um número, em vez de sobrescrever o
    modelo de outra pessoa. Levanta `ValueError` com a mensagem para o operador.
    """
    from .models import ModeloTextoRelatorioTecnico

    campos = dict(ModeloTextoRelatorioTecnico.CAMPO_CHOICES)
    if campo not in campos:
        raise ValueError("Campo do relatório inválido.")
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Escreva o texto antes de salvar como modelo.")
    base = normalize_spaces(nome or "")[:110] or f"Modelo de {campos[campo].lower()}"
    nome_final = base
    sufixo = 2
    while ModeloTextoRelatorioTecnico.objects.filter(campo=campo, nome=nome_final).exists():
        nome_final = f"{base} ({sufixo})"
        sufixo += 1
    return ModeloTextoRelatorioTecnico.objects.create(campo=campo, nome=nome_final, texto=texto)
