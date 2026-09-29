"""Seed determinístico por cenário.

Tudo que aqui nasce é reproduzível: gerador pseudoaleatório com semente fixa,
datas ancoradas em ``ANCORA`` (não em "hoje"), nomes e números previsíveis.
Os testes de UI congelam o relógio do navegador na mesma âncora.

Cenários (``--scenario``):

=================  ==========================================================
empty              só a base (grupos, módulos, cadastros, usuários de papel)
small              3 registros por entidade principal
normal             25 por entidade — o dia a dia
large              300 por entidade — paginação, filtros, ordenação
very_large         3.000 solicitações/ofícios — desempenho de listas
edge_case          todos os status, cancelados, datas-limite, textos longos,
                   campos opcionais vazios e dados "inválidos" gravados por
                   fora do formulário (como chegam de importações/legado)
long_text          só textos longos (quebra de layout)
missing_data       só opcionais vazios (estados "não informado")
invalid_data       só dados que o formulário recusaria
=================  ==========================================================

``error`` e ``permission_denied`` não são dados: são estados de runtime. Erro de
rede/servidor é simulado no Playwright (``page.route`` abortando requisições);
permissão negada usa o usuário ``lab.sem_modulo``, criado em todo cenário.

Todos os usuários de papel usam a senha ``LAB_PASSWORD`` — só existe em banco de
desenvolvimento (o comando recusa rodar com DEBUG desligado).
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

ANCORA = date(2026, 9, 15)
LAB_PASSWORD = "Lab@2026!seguro"
SEMENTE = 20260915

CENARIOS = {
    "empty": 0, "small": 3, "normal": 25, "large": 300, "very_large": 3000,
    "edge_case": 12, "long_text": 6, "missing_data": 6, "invalid_data": 6,
}

TEXTO_LONGO = (
    "Evento institucional de atendimento à comunidade com emissão de carteiras de identidade, "
    "orientação jurídica, palestras de prevenção e apoio psicossocial, em parceria com a prefeitura, "
    "o Ministério Público e entidades da sociedade civil organizada — descrição propositalmente longa "
    "para verificar quebra de linha, truncamento e overflow em tabelas, cartões e documentos gerados. "
) * 3
NOME_LONGO = "Maria Aparecida dos Santos Albuquerque de Oliveira Figueiredo Cavalcanti e Souza"

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Giovana", "Heitor", "Isabela", "João",
         "Karina", "Lucas", "Mariana", "Nicolas", "Olívia", "Paulo", "Quésia", "Rafael", "Sofia", "Tiago"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento",
              "Lima", "Araújo", "Ferreira", "Carvalho", "Gomes", "Martins", "Rocha", "Ribeiro"]

# (username, grupos, módulos, superusuário, deve_trocar_senha)
PAPEIS = [
    ("lab.admin", [], "*", True, False),
    ("lab.gestor_dg", ["GESTOR_DG"], [], False, False),
    ("lab.administrador", ["ADMINISTRADOR"], [], False, False),
    ("lab.solicitante", ["SOLICITANTE"], [], False, False),
    ("lab.viagens_gestor", ["VIAGENS_GESTOR"], ["VIAGENS"], False, False),
    ("lab.viagens_operador", ["VIAGENS_OPERADOR"], ["VIAGENS"], False, False),
    ("lab.viagens_leitor", [], ["VIAGENS"], False, False),
    ("lab.ascom", [], ["ASCOM_DEMANDAS_EVENTOS", "ASCOM_ATENDIMENTO_IMPRENSA", "ASCOM_COFFEE_BREAK", "ASCOM_PUBLICACOES"], False, False),
    ("lab.sem_modulo", [], [], False, False),
    ("lab.troca_senha", ["SOLICITANTE"], [], False, True),
]


class Semeador:
    def __init__(self, cenario: str, stdout=None):
        if cenario not in CENARIOS:
            raise ValueError(f"Cenário desconhecido: {cenario}. Opções: {', '.join(CENARIOS)}")
        self.cenario = cenario
        self.n = CENARIOS[cenario]
        self.rng = random.Random(SEMENTE)
        self.out = stdout
        self.relatorio: dict[str, int | str] = {}
        self.longo = cenario in {"edge_case", "long_text"}
        self.faltando = cenario in {"edge_case", "missing_data"}
        self.invalido = cenario in {"edge_case", "invalid_data"}

    # -- utilidades -------------------------------------------------------
    def log(self, msg):
        if self.out:
            self.out.write(msg)

    def nome(self, i):
        if self.longo and i % 3 == 0:
            return NOME_LONGO
        return f"{NOMES[i % len(NOMES)]} {SOBRENOMES[(i * 7) % len(SOBRENOMES)]}"

    def texto(self, i, curto="Atendimento à comunidade"):
        if self.longo:
            return TEXTO_LONGO
        if self.faltando and i % 2 == 0:
            return ""
        return f"{curto} #{i + 1}"

    def dia(self, delta):
        return ANCORA + timedelta(days=delta)

    def dt(self, delta_dias, hora=8):
        return timezone.make_aware(datetime.combine(self.dia(delta_dias), time(hora, 0)))

    @staticmethod
    def caber(objs):
        """Corta textos no max_length do campo: texto longo testa layout, não o banco."""
        for obj in objs:
            for f in obj._meta.concrete_fields:
                limite = getattr(f, "max_length", None)
                valor = getattr(obj, f.attname, None)
                if limite and isinstance(valor, str) and len(valor) > limite:
                    setattr(obj, f.attname, valor[: limite - 1] + "…")
        return objs

    def escolher(self, seq, i):
        return seq[i % len(seq)] if seq else None

    # -- base -------------------------------------------------------------
    def base(self):
        import io
        call_command("seed_initial_data", verbosity=0, stdout=io.StringIO())
        from accounts.models import Modulo, Setor
        from viagens_cadastros.models import Cargo, Combustivel, TabelaDiaria, Unidade

        User = get_user_model()
        modulos = {m.codigo: m for m in Modulo.objects.all()}
        for username, grupos, mods, superuser, troca in PAPEIS:
            u, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@lab.invalid"})
            u.first_name = username.split(".")[1].replace("_", " ").title()
            u.last_name = "Lab"
            u.is_superuser = u.is_staff = superuser
            u.deve_trocar_senha = troca
            u.set_password(LAB_PASSWORD)
            u.save()
            u.groups.set([Group.objects.get_or_create(name=g)[0] for g in grupos])
            if mods:
                codigos = list(modulos) if mods == "*" else mods
                setor, _ = Setor.objects.get_or_create(nome=f"Setor Lab {'-'.join(sorted(codigos))[:60]}", defaults={"sigla": "LAB"})
                setor.modulos.set([modulos[c] for c in codigos if c in modulos])
                u.setores.set([setor])
            else:
                u.setores.clear()
        for nome in ("DELEGADO DE POLÍCIA", "INVESTIGADOR", "ESCRIVÃO", "AGENTE", "MOTORISTA", "PAPILOSCOPISTA"):
            Cargo.objects.get_or_create(nome=nome)
        for nome in ("GASOLINA", "ETANOL", "DIESEL", "FLEX"):
            Combustivel.objects.get_or_create(nome=nome)
        for nome in ("DIVISÃO DE COMUNICAÇÃO SOCIAL", "INSTITUTO DE IDENTIFICAÇÃO", "DELEGACIA-GERAL"):
            Unidade.objects.get_or_create(nome=nome)
        for faixa, v in ((TabelaDiaria.Faixa.INTERIOR, "290.55"), (TabelaDiaria.Faixa.CAPITAL, "371.26"), (TabelaDiaria.Faixa.BRASILIA, "431.10")):
            if not TabelaDiaria.objects.filter(faixa=faixa, vigencia_inicio=date(2026, 1, 1)).exists():
                valor = Decimal(v)
                TabelaDiaria.objects.create(
                    faixa=faixa, vigencia_inicio=date(2026, 1, 1), valor_24h=valor,
                    valor_15=(valor * Decimal("0.15")).quantize(Decimal("0.01")),
                    valor_30=(valor * Decimal("0.30")).quantize(Decimal("0.01")),
                )
        self.relatorio["usuarios_de_papel"] = len(PAPEIS)

    # -- domínios ---------------------------------------------------------
    def eventos_sociais(self):
        from cadastros.models import Municipio, OrgaoResponsavel, TipoEvento
        from solicitacoes.models import SolicitacaoEvento

        User = get_user_model()
        autor = User.objects.get(username="lab.solicitante")
        municipios = list(Municipio.objects.order_by("nome"))
        tipos = list(TipoEvento.objects.order_by("nome"))
        orgaos = list(OrgaoResponsavel.objects.order_by("nome"))
        status = [c[0] for c in SolicitacaoEvento._meta.get_field("status").choices]
        objs = []
        for i in range(self.n):
            mun = self.escolher(municipios, i)
            inicio = self.dia((i % 60) - 20)
            fim = inicio + timedelta(days=i % 3)
            # Data final antes da inicial NÃO entra: a constraint `periodo_evento_valido`
            # defende isso no banco (descoberta registrada em docs/agent/memory).
            objs.append(SolicitacaoEvento(
                status=status[i % len(status)] if (self.cenario == "edge_case" or i % 5) else "RASCUNHO",
                data_solicitacao=inicio - timedelta(days=15),
                data_inicio_evento=inicio, data_fim_evento=fim,
                municipio=None if (self.faltando and i % 3 == 0) else mun,
                regiao=None if (self.faltando and i % 3 == 0) else getattr(mun, "regiao", None),
                tipo_evento=self.escolher(tipos, i), orgao_responsavel=self.escolher(orgaos, i),
                solicitante_nome=self.nome(i), solicitante_cargo_unidade="" if self.faltando else "Delegacia de Polícia",
                contato="" if self.faltando else f"(41) 9{8000 + i:04d}-{i % 10000:04d}",
                local_evento=self.texto(i, "Ginásio municipal"), endereco="" if self.faltando else f"Rua das Flores, {100 + i}",
                descricao_complementar=self.texto(i, "Descrição"),
                quantidade_servidores=(0 if self.invalido and i % 4 == 2 else 2 + i % 6),
                quantidade_cin=(i * 13) % 400,
                criado_por=autor,
            ))
        SolicitacaoEvento.objects.bulk_create(self.caber(objs), batch_size=500)
        self.relatorio["solicitacoes_evento"] = len(objs)

    def viagens_cadastros(self):
        from viagens_cadastros.models import Cargo, Combustivel, Servidor, Unidade, Viatura

        cargos = list(Cargo.objects.order_by("nome"))
        unidades = list(Unidade.objects.order_by("nome"))
        combs = list(Combustivel.objects.order_by("nome"))
        qtd = max(self.n, 4 if self.n else 0)
        servidores = []
        for i in range(qtd):
            cpf = f"{(SEMENTE + i * 7919) % 10**11:011d}"
            if self.invalido and i % 3 == 0:
                cpf = "11111111111"  # CPF de dígitos repetidos (inválido)
            servidores.append(Servidor(
                nome=self.nome(i).upper(), cargo=None if (self.faltando and i % 2 == 0) else self.escolher(cargos, i),
                cpf="" if (self.faltando and i % 2 == 1) else cpf,
                rg="" if self.faltando else f"{1000000 + i}", telefone="" if self.faltando else f"4199{i:07d}"[:11],
                unidade=self.escolher(unidades, i),
                status="COMPLETO" if not self.faltando else "RASCUNHO",
            ))
        # CPF único: só grava os que não colidem (o de dígitos repetidos entra uma vez).
        vistos = set()
        filtrados = []
        for s in servidores:
            if s.cpf and s.cpf in vistos:
                s.cpf = ""
            vistos.add(s.cpf)
            filtrados.append(s)
        Servidor.objects.bulk_create(self.caber(filtrados), batch_size=500, ignore_conflicts=True)
        viaturas = []
        for i in range(qtd):
            letras = "".join(chr(65 + (i * k) % 26) for k in (1, 3, 5))
            viaturas.append(Viatura(
                placa=f"{letras}{i % 10}{chr(65 + i % 26)}{(i * 37) % 100:02d}",
                modelo="" if self.faltando else self.escolher(["GOL 1.6", "SPIN LTZ", "HILUX SRV", "SPRINTER 415"], i),
                combustivel=self.escolher(combs, i), tipo=self.escolher(["CARACTERIZADA", "DESCARACTERIZADA"], i),
                unidade=self.escolher(unidades, i),
            ))
        Viatura.objects.bulk_create(self.caber(viaturas), batch_size=500, ignore_conflicts=True)
        self.relatorio["servidores"] = Servidor.objects.count()
        self.relatorio["viaturas"] = Viatura.objects.count()

    def viagens_documentos(self):
        from cadastros.models import Municipio
        from viagens_cadastros.models import Servidor, Unidade, Viatura
        from viagens_oficios.models import Oficio
        from viagens_roteiros.models import Roteiro, RoteiroDestino, RoteiroTrecho

        servidores = list(Servidor.objects.order_by("pk"))
        viaturas = list(Viatura.objects.order_by("pk"))
        unidades = list(Unidade.objects.order_by("pk"))
        municipios = list(Municipio.objects.order_by("nome"))
        if not municipios:
            return
        curitiba = next((m for m in municipios if m.nome.lower() == "curitiba"), municipios[0])
        status_oficio = [c[0] for c in Oficio._meta.get_field("status").choices]
        qtd_docs = min(self.n, 1500)
        inicio_numero = (Oficio.objects.filter(ano=ANCORA.year).order_by("-numero").values_list("numero", flat=True).first() or 0) + 1
        for i in range(qtd_docs):
            with transaction.atomic():
                roteiro = Roteiro.objects.create(
                    origem_municipio=curitiba, saida_dt=self.dt(i % 40 - 10, 7), chegada_dt=self.dt(i % 40 - 10, 11),
                    retorno_saida_dt=self.dt(i % 40 - 8, 14), retorno_chegada_dt=self.dt(i % 40 - 8, 18),
                    quantidade_servidores=1 + i % 4, observacoes=self.texto(i, "Roteiro"),
                    status="FINALIZADO" if i % 3 else "RASCUNHO",
                    cancelado=(self.cenario == "edge_case" and i % 5 == 4),
                )
                destino = self.escolher(municipios, i + 1)
                RoteiroDestino.objects.create(roteiro=roteiro, municipio=destino, ordem=1)
                RoteiroTrecho.objects.create(roteiro=roteiro, ordem=1, sentido="IDA", origem_municipio=curitiba, destino_municipio=destino,
                                             saida_dt=roteiro.saida_dt, chegada_dt=roteiro.chegada_dt)
                RoteiroTrecho.objects.create(roteiro=roteiro, ordem=2, sentido="RETORNO", origem_municipio=destino, destino_municipio=curitiba,
                                             saida_dt=roteiro.retorno_saida_dt, chegada_dt=roteiro.retorno_chegada_dt)
                oficio = Oficio.objects.create(
                    numero=inicio_numero + i, ano=ANCORA.year, data_criacao=self.dia(-(i % 90)),
                    protocolo="" if self.faltando else f"{ANCORA.year}{inicio_numero + i:05d}",
                    protocolo_origem="MANUAL", assunto=self.texto(i, "Ofício de viagem")[:200],
                    motivo=self.texto(i, "Participação em evento institucional"),
                    status=status_oficio[i % len(status_oficio)], roteiro=roteiro,
                    solicitante=self.escolher(unidades, i), viatura=None if self.faltando else self.escolher(viaturas, i),
                    motorista=self.escolher(servidores, i + 2), assinante=self.escolher(servidores, i + 1),
                    cancelado=(self.cenario == "edge_case" and i % 7 == 6),
                )
                equipe = [servidores[(i + k) % len(servidores)] for k in range(1 + i % 3)] if servidores else []
                oficio.servidores.add(*equipe)
        self.relatorio["roteiros"] = Roteiro.objects.count()
        self.relatorio["oficios"] = Oficio.objects.count()

    def ascom(self):
        from atendimento_imprensa.models import Atendimento, Veiculo
        from atendimento_imprensa.models import Responsavel as RespImprensa
        from demandas_eventos.models import DemandaEvento
        from publicacoes.models import Publicacao, Responsavel, Unidade

        User = get_user_model()
        autor = User.objects.get(username="lab.ascom")
        jornalistas = [Responsavel.objects.get_or_create(nome=n)[0] for n in ("Jornalista A", "Jornalista B", "Jornalista C")]
        unidades = [Unidade.objects.get_or_create(nome=n)[0] for n in ("Delegacia-Geral", "Instituto de Identificação")]
        veiculos = [Veiculo.objects.get_or_create(nome=n)[0] for n in ("RPC", "Band PR", "Gazeta do Povo", "CBN Curitiba")]
        resp_imp = [RespImprensa.objects.get_or_create(nome=n)[0] for n in ("Assessor 1", "Assessor 2")]
        st_pub = [c[0] for c in Publicacao._meta.get_field("status").choices]
        st_dem = [c[0] for c in DemandaEvento._meta.get_field("status").choices]
        ev_dem = [c[0] for c in DemandaEvento._meta.get_field("evento").choices]
        st_at = [c[0] for c in Atendimento._meta.get_field("situacao").choices]
        n = min(self.n, 2000)
        Publicacao.objects.bulk_create(self.caber([Publicacao(
            data=self.dia(-(i % 120)), jornalista=self.escolher(jornalistas, i), unidade=self.escolher(unidades, i),
            titulo=(TEXTO_LONGO[:250] if self.longo else f"Pauta institucional {i + 1}"), status=st_pub[i % len(st_pub)],
            andamento=self.texto(i, "Em apuração"), criado_por=autor,
        ) for i in range(n)]), batch_size=500)
        DemandaEvento.objects.bulk_create(self.caber([DemandaEvento(
            solicitante=self.nome(i), data_solicitacao=self.dia(-(i % 60)), status=st_dem[i % len(st_dem)],
            evento=ev_dem[i % len(ev_dem)], data_inicio_evento=self.dia(i % 45),
            descricao=self.texto(i, "Palestra sobre prevenção"), email="" if self.faltando else f"contato{i}@exemplo.invalid",
            criado_por=autor,
        ) for i in range(n)]), batch_size=500)
        Atendimento.objects.bulk_create(self.caber([Atendimento(
            data=self.dia(-(i % 30)), jornalista=self.nome(i), veiculo=self.escolher(veiculos, i),
            pedido=self.texto(i, "Pedido de entrevista") or "Pedido", situacao=st_at[i % len(st_at)],
            responsavel=self.escolher(resp_imp, i), criado_por=autor,
        ) for i in range(n)]), batch_size=500)
        self.relatorio["publicacoes"] = Publicacao.objects.count()
        self.relatorio["demandas_eventos"] = DemandaEvento.objects.count()
        self.relatorio["atendimentos_imprensa"] = Atendimento.objects.count()

    def coffee_break(self):
        from coffee_break.models import ContratoCoffeeBreak, Fornecedor, LoteCoffeeBreak, SolicitacaoCoffeeBreak
        from cadastros.models import Municipio

        if not self.n:
            return
        User = get_user_model()
        autor = User.objects.get(username="lab.ascom")
        forn, _ = Fornecedor.objects.get_or_create(razao_social="Buffet Laboratório LTDA", defaults={"cnpj": "00000000000191", "nome_curto": "Buffet Lab"})
        contrato, _ = ContratoCoffeeBreak.objects.get_or_create(fornecedor=forn, numero="001/2026", defaults={
            "vigencia_inicio": date(2026, 1, 1), "vigencia_fim": date(2026, 12, 31), "quantidade_contratada": 100000,
            "valor_unitario": Decimal("12.50")})
        lote, _ = LoteCoffeeBreak.objects.get_or_create(contrato=contrato, numero=1, exercicio="2026", defaults={"quantidade_total": 100000})
        municipios = list(Municipio.objects.order_by("nome"))
        SolicitacaoCoffeeBreak.objects.bulk_create(self.caber([SolicitacaoCoffeeBreak(
            lote=lote, descricao_evento=self.texto(i, "Coffee break do evento") or "Coffee break", quantidade=20 + (i * 17) % 300,
            data_solicitacao=self.dia(-(i % 40)), data_inicio_evento=self.dia(i % 40), municipio=self.escolher(municipios, i),
            cancelada=(self.cenario == "edge_case" and i % 6 == 5), criado_por=autor,
        ) for i in range(min(self.n, 2000))]), batch_size=500)
        self.relatorio["coffee_break_solicitacoes"] = SolicitacaoCoffeeBreak.objects.count()

    # -- orquestração -----------------------------------------------------
    def executar(self):
        etapas = [self.base]
        if self.n:
            etapas += [self.eventos_sociais, self.viagens_cadastros, self.viagens_documentos, self.ascom, self.coffee_break]
        erros = {}
        for etapa in etapas:
            try:
                with transaction.atomic():
                    etapa()
                self.log(f"  ✓ {etapa.__name__}")
            except Exception as exc:  # registra e segue: o relatório diz o que faltou
                erros[etapa.__name__] = f"{type(exc).__name__}: {exc}"
                self.log(f"  ✗ {etapa.__name__}: {exc}")
        marcar_estado(self.cenario, self.relatorio, erros)
        return self.relatorio, erros


def marcar_estado(cenario, relatorio, erros):
    from django.core.cache import cache
    cache.set("agent_lab:seed", {"scenario": cenario, "counts": relatorio, "errors": erros,
                                  "anchor": ANCORA.isoformat(), "seeded_at": timezone.now().isoformat()}, None)


def estado_atual():
    """Resumo do banco para a sonda de saúde (não depende do cache)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return {
        "lab_users": User.objects.filter(username__startswith="lab.").count(),
        "anchor": ANCORA.isoformat(),
    }
