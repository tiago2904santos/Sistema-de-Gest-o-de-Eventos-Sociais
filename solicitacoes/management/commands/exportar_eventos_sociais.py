"""Exporta as solicitações de evento para levar a outro ambiente.

Os dois bancos (dev e VPS) nasceram separados: o mesmo município tem id
diferente em cada um. Por isso nada aqui sai por id — cada vínculo viaja pelo
nome que o identifica (município + UF, serviço, equipe, usuário...) e o
`importar_eventos_sociais` resolve os ids do outro lado.

    python manage.py exportar_eventos_sociais eventos.json [--media pasta.zip]
"""

import json
import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand

from solicitacoes.models import SolicitacaoEvento


def _usuario(user):
    if user is None:
        return None
    return {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "password": user.password,  # hash; ninguém precisa trocar de senha
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "deve_trocar_senha": user.deve_trocar_senha,
        "grupos": sorted(g.name for g in user.groups.all()),
        "setores": sorted(s.nome for s in user.setores.all()),
    }


def _municipio(municipio):
    if municipio is None:
        return None
    return {"nome": municipio.nome, "uf": municipio.estado.sigla}


CAMPOS_SIMPLES = [
    "status", "data_solicitacao", "data_inicio_evento", "data_fim_evento",
    "solicitante_nome", "solicitante_cargo_unidade", "contato",
    "unidade_movel", "local_evento", "descricao_complementar",
    "quantidade_servidores", "tipo_operacao", "quantidade_cin",
    "decisao_dg", "observacoes_dg", "decidido_em", "criado_em", "atualizado_em",
]


class Command(BaseCommand):
    help = "Exporta solicitações de evento (e o que elas referenciam) para JSON."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", type=Path)
        parser.add_argument(
            "--media", type=Path, default=None,
            help="Zip com os anexos, para copiar junto com o JSON.",
        )

    def handle(self, arquivo, media, **_opcoes):
        consulta = (
            SolicitacaoEvento.objects.select_related(
                "municipio__estado", "regiao", "tipo_evento", "orgao_responsavel",
                "unidade_movel_designada", "motorista", "criado_por", "decidido_por",
            )
            .prefetch_related(
                "itens_servico__servico", "itens_equipe__equipe",
                "historico__usuario", "anexos__enviado_por",
            )
            .order_by("pk")
        )
        usuarios, registros, anexos = {}, [], []

        def anotar(user):
            if user is not None and user.username not in usuarios:
                usuarios[user.username] = _usuario(user)
            return user.username if user else None

        for s in consulta:
            registros.append(
                {
                    **{campo: _valor(getattr(s, campo)) for campo in CAMPOS_SIMPLES},
                    "referencia": s.pk,
                    "municipio": _municipio(s.municipio),
                    "regiao": s.regiao.nome if s.regiao_id else None,
                    "tipo_evento": s.tipo_evento.nome if s.tipo_evento_id else None,
                    "orgao_responsavel": (
                        s.orgao_responsavel.nome if s.orgao_responsavel_id else None
                    ),
                    "unidade_movel_designada": (
                        s.unidade_movel_designada.nome
                        if s.unidade_movel_designada_id else None
                    ),
                    "motorista": s.motorista.nome if s.motorista_id else None,
                    "criado_por": anotar(s.criado_por),
                    "decidido_por": anotar(s.decidido_por),
                    "servicos": [
                        {"nome": i.servico.nome, "observacao": i.observacao}
                        for i in s.itens_servico.all()
                    ],
                    "equipes": [
                        {
                            "nome": i.equipe.nome,
                            "quantidade_servidores": i.quantidade_servidores,
                            "observacao": i.observacao,
                        }
                        for i in s.itens_equipe.all()
                    ],
                    "historico": [
                        {
                            "acao": h.acao,
                            "status_anterior": h.status_anterior,
                            "status_novo": h.status_novo,
                            "observacao": h.observacao,
                            "criado_em": _valor(h.criado_em),
                            "usuario": anotar(h.usuario),
                        }
                        for h in s.historico.all()
                    ],
                    "anexos": [
                        {
                            "arquivo": a.arquivo.name,
                            "nome_original": a.nome_original,
                            "tamanho": a.tamanho,
                            "criado_em": _valor(a.criado_em),
                            "enviado_por": anotar(a.enviado_por),
                        }
                        for a in s.anexos.all()
                    ],
                }
            )
            anexos.extend(a.arquivo.name for a in s.anexos.all())

        conteudo = {"usuarios": list(usuarios.values()), "solicitacoes": registros}
        arquivo.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(registros)} solicitações e {len(usuarios)} usuários em {arquivo}."
            )
        )

        if media and anexos:
            from django.conf import settings

            raiz = Path(settings.MEDIA_ROOT)
            with zipfile.ZipFile(media, "w", zipfile.ZIP_DEFLATED) as zip_:
                for nome in anexos:
                    caminho = raiz / nome
                    if caminho.exists():
                        zip_.write(caminho, nome)
                    else:
                        self.stderr.write(f"anexo ausente no disco: {nome}")
            self.stdout.write(self.style.SUCCESS(f"{len(anexos)} anexos em {media}."))


def _valor(valor):
    return valor.isoformat() if hasattr(valor, "isoformat") else valor
