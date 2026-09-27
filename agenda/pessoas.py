"""Quem está em cada compromisso — e o que é "meu" numa viagem.

A viagem não guarda quem a criou (``ModeloTemporal`` só tem os carimbos de
data), então "Só o que eu criei" escondia todas as viagens sem avisar. Duas
respostas, somadas:

- **criei**: a trilha de auditoria registra a criação da viagem, do ofício
  e do roteiro com o usuário — é de lá que vem "quem registrou";
- **estou escalado**: com o usuário ligado ao seu cadastro de servidor
  (``User.servidor``), a viagem é minha se eu estou na equipe de um ofício,
  sou o motorista, ou apareço num termo ou numa ordem de serviço.

A lista de pessoas de cada compromisso vai ao calendário em
``extendedProps.pessoas`` e alimenta o filtro "Pessoa" e a escala.
"""

from __future__ import annotations

from django.db.models import Prefetch

_MODELOS_DE_VIAGEM = ("viagens_viagem.viagem", "viagens_oficios.oficio", "viagens_roteiros.roteiro")


def criacoes_de(usuario) -> dict[str, set[str]]:
    """Ids (como texto) de viagens, ofícios e roteiros que a pessoa criou."""
    from auditoria.models import RegistroAuditoria

    saida: dict[str, set[str]] = {m: set() for m in _MODELOS_DE_VIAGEM}
    if not getattr(usuario, "pk", None):
        return saida
    registros = RegistroAuditoria.objects.filter(
        usuario=usuario, acao=RegistroAuditoria.Acao.CRIACAO, modelo__in=_MODELOS_DE_VIAGEM,
    ).values_list("modelo", "objeto_id")
    for modelo, objeto_id in registros:
        saida[modelo].add(str(objeto_id))
    return saida


def prefetch_equipes(consulta):
    """As relações que `equipe_da_viagem` lê, trazidas de uma vez."""
    from viagens_oficios.models import Oficio
    from viagens_ordens.models import OrdemServico
    from viagens_termos.models import TermoAutorizacao

    return consulta.prefetch_related(
        # `to_attr`: a situação da viagem (agenda.situacao) pré-carrega as mesmas
        # relações sem filtro; atributos próprios evitam o choque entre as duas.
        Prefetch("oficios", queryset=Oficio.objects.filter(cancelado=False).only("id", "viagem_id", "motorista_id").prefetch_related("servidores").select_related("motorista"), to_attr="equipe_oficios"),
        Prefetch("termos_autorizacao", queryset=TermoAutorizacao.objects.filter(cancelado=False).only("id", "viagem_id").prefetch_related("servidores"), to_attr="equipe_termos"),
        Prefetch("ordens_servico", queryset=OrdemServico.objects.filter(cancelado=False).only("id", "viagem_id").prefetch_related("servidores"), to_attr="equipe_ordens"),
        "roteiros",
    )


def _escalados(viagem, atributo, relacao):
    """O pré-carregado de `prefetch_equipes`, ou a consulta direta (sem cancelados)."""
    pre = getattr(viagem, atributo, None)
    return pre if pre is not None else getattr(viagem, relacao).filter(cancelado=False)


def equipe_da_viagem(viagem) -> tuple[list[str], set[int]]:
    """Nomes (motorista primeiro) e pks dos servidores escalados na viagem."""
    nomes: dict[int, str] = {}
    motoristas: set[int] = set()
    for o in _escalados(viagem, "equipe_oficios", "oficios"):
        if o.motorista_id:
            nomes.setdefault(o.motorista_id, o.motorista.nome)
            motoristas.add(o.motorista_id)
        for s in o.servidores.all():
            nomes.setdefault(s.pk, s.nome)
    for grupo in (_escalados(viagem, "equipe_termos", "termos_autorizacao"), _escalados(viagem, "equipe_ordens", "ordens_servico")):
        for doc in grupo:
            for s in doc.servidores.all():
                nomes.setdefault(s.pk, s.nome)
    ordenados = sorted(nomes.items(), key=lambda par: (par[0] not in motoristas, par[1]))
    return [nome for _, nome in ordenados], set(nomes)


def viagem_e_minha(viagem, *, criacoes: dict[str, set[str]], servidor_pk, escalados: set[int]) -> bool:
    """Criei (viagem, ofício ou roteiro) ou estou escalado."""
    if servidor_pk and servidor_pk in escalados:
        return True
    if str(viagem.pk) in criacoes["viagens_viagem.viagem"]:
        return True
    if any(str(o.pk) in criacoes["viagens_oficios.oficio"] for o in viagem.oficios.all()):
        return True
    return any(str(r.pk) in criacoes["viagens_roteiros.roteiro"] for r in viagem.roteiros.all())
