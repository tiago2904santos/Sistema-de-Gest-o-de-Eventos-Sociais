"""Importa as solicitações da planilha "Solicitações - Eventos Sociais" (CSV).

Uso:
    python manage.py importar_planilha caminho/planilha.csv --usuario Tiago
    python manage.py importar_planilha caminho/planilha.csv --usuario Tiago --limpar

--limpar apaga todas as solicitações e os cadastros de apoio (tipos de evento,
serviços, equipes, órgãos e unidades móveis) antes de importar.
Estados, regiões, municípios e usuários são preservados.
"""

import csv
import re
import unicodedata
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cadastros.models import (
    Equipe,
    Municipio,
    OrgaoResponsavel,
    Servico,
    TipoEvento,
    UnidadeMovel,
)
from solicitacoes.models import (
    AcaoHistorico,
    DecisaoDG,
    HistoricoSolicitacao,
    SolicitacaoEvento,
    SolicitacaoEventoEquipe,
    SolicitacaoEventoServico,
    StatusSolicitacao,
    TipoOperacao,
)

ANO_PADRAO = 2026

# A planilha marca "veículo de exposição" numa coluna própria; no sistema isso
# virou um serviço como os outros.
NOME_SERVICO_VIATURAS = "Exposição de viaturas antigas e modernas"

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

STATUS_MAP = {
    "ATENDIDO": StatusSolicitacao.ATENDIDA,
    "NÃO ATENDER": StatusSolicitacao.NAO_ATENDIDA,
    "EVENTO CANCELADO": StatusSolicitacao.CANCELADA,
    "DEFERIDO EM ANDAMENTO": StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
    "EM ANÁLISE": StatusSolicitacao.AGUARDANDO_DESPACHO,
    "": StatusSolicitacao.AGUARDANDO_DESPACHO,
}

DECISAO_MAP = {
    "ATENDER": DecisaoDG.ATENDER,
    "NÃO ATENDER": DecisaoDG.NAO_ATENDER,
    "EVENTO CANCELADO": DecisaoDG.CANCELADO,
    "VERIFICAR": DecisaoDG.PENDENTE,
    "": DecisaoDG.PENDENTE,
}

# Grafias da planilha -> (nome oficial do município, complemento p/ local).
# Chaves na forma normalizada de _norm(): minúsculas e sem acentos.
MUNICIPIO_FIX = {
    "pinhias": ("Pinhais", ""),
    "telemaco borba": ("Telêmaco Borba", ""),
    "santa terezinha do itaipu": ("Santa Terezinha de Itaipu", ""),
    "batel - curitiba": ("Curitiba", "Batel"),
    "socavao": ("Castro", "Socavão"),
    "santo antonio da platina": ("Santo Antônio da Platina", ""),
    "santa tereza do oeste": ("Santa Tereza do Oeste", ""),
}

VAZIOS = {"", "--", "---", "----", "-------", "--------", "---------", "----------", "?", "??", "não", "nao", "a definir"}


def _limpa(texto):
    return re.sub(r"\s+", " ", (texto or "").strip())


def _norm(texto):
    texto = _limpa(texto).lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _vazio(texto):
    return _norm(texto) in VAZIOS


def _resolver_motorista(nome):
    """Servidor que dirige, criado sob demanda a partir do nome da planilha.

    A busca usa o nome já em maiúsculas porque é assim que ``Servidor.save()``
    grava: procurar pelo texto original faria cada reimportação tentar criar de
    novo o mesmo servidor e esbarrar na unicidade do nome.
    """
    from viagens_cadastros.models import Cargo, Servidor

    nome = _limpa(nome).upper()
    if not nome:
        return None
    servidor = Servidor.objects.filter(nome=nome).first()
    if servidor is not None:
        return servidor
    cargo, _ = Cargo.objects.get_or_create(nome="MOTORISTA")
    return Servidor.objects.create(nome=nome, cargo=cargo)


def _parse_data_solicitacao(texto):
    """"18/05" ou "12/3" -> date no ano padrão."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", _limpa(texto))
    if not m:
        return None
    dia, mes = int(m.group(1)), int(m.group(2))
    ano = int(m.group(3)) if m.group(3) else ANO_PADRAO
    if ano < 100:
        ano += 2000
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _parse_periodo_evento(texto, mes_planilha):
    """Interpreta "31/07 a 09/08", "07 e 08/08", "6 a 8/8", "11/08",
    "16 à 18/04/2027", "14 a 16" (usa o mês da planilha)... -> (inicio, fim)."""
    bruto = _limpa(texto)
    if not bruto or _norm(bruto) in VAZIOS:
        return None, None

    ano = ANO_PADRAO
    m_ano = re.search(r"/(\d{4})", bruto)
    if m_ano:
        ano = int(m_ano.group(1))

    mes_padrao = MESES.get(_norm(mes_planilha))

    # Pares dia[/mês] separados por "a", "à", "e" ou "-"
    partes = re.findall(r"(\d{1,2})(?:/(\d{1,2}))?", re.sub(r"/\d{4}", "", bruto))
    if not partes:
        return None, None

    datas = []
    # O mês costuma aparecer só no último termo ("6 a 8/8"): propaga de trás
    # para frente quando ausente.
    meses_conhecidos = [int(m) if m else None for _, m in partes]
    ultimo_mes = None
    for i in range(len(meses_conhecidos) - 1, -1, -1):
        if meses_conhecidos[i] is not None:
            ultimo_mes = meses_conhecidos[i]
        elif ultimo_mes is not None:
            meses_conhecidos[i] = ultimo_mes
    for (dia, _), mes in zip(partes, meses_conhecidos):
        mes = mes or mes_padrao
        if not mes:
            return None, None
        try:
            datas.append(date(ano, int(mes), int(dia)))
        except ValueError:
            return None, None

    inicio, fim = min(datas), max(datas)
    return inicio, fim


def _parse_int_inicial(texto):
    m = re.match(r"^(\d+)", _limpa(texto))
    return int(m.group(1)) if m else None


class Command(BaseCommand):
    help = "Importa solicitações da planilha de eventos sociais (CSV exportado do Google Sheets)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Caminho do arquivo CSV")
        parser.add_argument("--usuario", required=True, help="Username do criador das solicitações")
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Apaga solicitações e cadastros de apoio antes de importar",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        try:
            usuario = User.objects.get(username=opts["usuario"])
        except User.DoesNotExist:
            raise CommandError(f"Usuário '{opts['usuario']}' não existe.")

        with open(opts["csv_path"], encoding="utf-8-sig", newline="") as fh:
            linhas = list(csv.reader(fh))
        if not linhas:
            raise CommandError("CSV vazio.")
        registros = linhas[1:]

        if opts["limpar"]:
            self._limpar_banco()

        avisos = []
        criadas = 0
        for n, r in enumerate(registros, start=2):
            criadas += self._importar_linha(n, r, usuario, avisos)

        self.stdout.write(self.style.SUCCESS(f"{criadas} solicitações importadas."))
        for aviso in avisos:
            self.stdout.write(self.style.WARNING(aviso))

    def _limpar_banco(self):
        totais = {
            "solicitações": SolicitacaoEvento.objects.count(),
        }
        SolicitacaoEvento.objects.all().delete()
        for modelo in (TipoEvento, Servico, Equipe, OrgaoResponsavel, UnidadeMovel):
            totais[modelo._meta.verbose_name_plural] = modelo.objects.count()
            modelo.objects.all().delete()
        resumo = ", ".join(f"{v} {k}" for k, v in totais.items() if v)
        self.stdout.write(self.style.WARNING(f"Limpeza: {resumo or 'nada a apagar'}."))

    def _resolver_municipio(self, bruto, avisos, linha):
        texto = (bruto or "").strip()
        if not texto or _vazio(texto):
            return None, ""
        partes = [p.strip() for p in re.split(r"[\n/]", texto) if p.strip()]
        candidato_multilinha = _limpa(" ".join(partes))
        complemento = ""

        # Nome quebrado em duas linhas ("Santa Tereza\ndo Oeste")?
        chave = _norm(candidato_multilinha)
        if chave in MUNICIPIO_FIX:
            nome, complemento = MUNICIPIO_FIX[chave]
        else:
            municipio = Municipio.objects.filter(nome__iexact=candidato_multilinha).first()
            if municipio:
                return municipio, ""
            nome = partes[0]
            complemento = " / ".join(partes[1:])
            chave = _norm(nome)
            if chave in MUNICIPIO_FIX:
                nome, extra = MUNICIPIO_FIX[chave]
                complemento = " / ".join(filter(None, [extra, complemento]))

        municipio = Municipio.objects.filter(nome__iexact=_limpa(nome)).first()
        if municipio is None:
            avisos.append(f"Linha {linha}: município '{texto}' não encontrado — ficou em branco.")
        return municipio, complemento

    def _importar_linha(self, linha, r, usuario, avisos):
        (
            situacao, data_solic, mes_evento, data_evento, solicitante, cargo,
            contato, tipo_evento, descricao, unidade_movel, motorista,
            veiculo_exp, municipio_txt, _regiao, orgao, equipe_txt, qtd_serv,
            tipo_op, qtd_cin, despacho, obs_dg, equipe_escalada, balanco,
            _atendimentos,
        ) = [c.strip() for c in r]

        status = STATUS_MAP.get(situacao.upper())
        if status is None:
            avisos.append(f"Linha {linha}: situação '{situacao}' desconhecida — usado 'Aguardando despacho'.")
            status = StatusSolicitacao.AGUARDANDO_DESPACHO

        municipio, local = self._resolver_municipio(municipio_txt, avisos, linha)

        data_inicio, data_fim = _parse_periodo_evento(data_evento, mes_evento)
        if data_inicio is None and not _vazio(data_evento):
            avisos.append(f"Linha {linha}: data do evento '{_limpa(data_evento)}' não interpretada — ficou em branco.")

        obs_partes = [obs_dg.strip()]
        if equipe_escalada.strip():
            obs_partes.append(f"Equipe escalada: {_limpa(equipe_escalada)}")
        if balanco.strip():
            obs_partes.append(f"Balanço do evento: {_limpa(balanco)}")

        tem_unidade = not _vazio(unidade_movel)
        unidade_designada = None
        if tem_unidade and _norm(unidade_movel) != "a definir":
            unidade_designada = UnidadeMovel.objects.get_or_create(nome=_limpa(unidade_movel))[0]

        solicitacao = SolicitacaoEvento(
            status=status,
            data_solicitacao=_parse_data_solicitacao(data_solic) or date(ANO_PADRAO, 1, 1),
            data_inicio_evento=data_inicio,
            data_fim_evento=data_fim,
            municipio=municipio,
            tipo_evento=(
                TipoEvento.objects.get_or_create(nome=_limpa(tipo_evento))[0]
                if not _vazio(tipo_evento) else None
            ),
            solicitante_nome=_limpa(solicitante)[:150],
            solicitante_cargo_unidade=_limpa(cargo)[:255],
            contato=_limpa(contato)[:100],
            orgao_responsavel=(
                OrgaoResponsavel.objects.get_or_create(nome=_limpa(orgao))[0]
                if not _vazio(orgao) else None
            ),
            unidade_movel=tem_unidade,
            unidade_movel_designada=unidade_designada,
            local_evento=local[:255],
            descricao_complementar=descricao.strip(),
            tipo_operacao=(
                TipoOperacao.EXTRAJORNADA
                if "extrajornada" in _norm(tipo_op) else TipoOperacao.DIARIA
            ),
            quantidade_cin=_parse_int_inicial(qtd_cin) if not _vazio(qtd_cin) else None,
            motorista=(
                _resolver_motorista(_limpa(motorista))
                if not _vazio(motorista) else None
            ),
            decisao_dg=DECISAO_MAP.get(despacho.upper(), DecisaoDG.PENDENTE),
            observacoes_dg="\n".join(p for p in obs_partes if p),
            criado_por=usuario,
        )
        solicitacao.save()

        if _norm(veiculo_exp) == "sim":
            servico_viaturas = Servico.objects.filter(
                nome__iexact=NOME_SERVICO_VIATURAS
            ).first()
            if servico_viaturas is None:
                servico_viaturas = Servico.objects.create(nome=NOME_SERVICO_VIATURAS)
            SolicitacaoEventoServico.objects.get_or_create(
                solicitacao=solicitacao, servico=servico_viaturas
            )

        equipes = [e for e in (_limpa(p) for p in equipe_txt.split("/")) if e and not _vazio(e)]
        qtd_total = _parse_int_inicial(qtd_serv) if re.fullmatch(r"\d+", _limpa(qtd_serv)) else None
        obs_qtd = "" if qtd_total is not None or _vazio(qtd_serv) else _limpa(qtd_serv)[:255]
        for i, nome in enumerate(equipes):
            SolicitacaoEventoEquipe.objects.create(
                solicitacao=solicitacao,
                equipe=Equipe.objects.get_or_create(nome=nome)[0],
                quantidade_servidores=qtd_total if i == 0 else None,
                observacao=obs_qtd if i == 0 else "",
            )
        if not equipes and (qtd_total is not None or obs_qtd):
            # Sem equipe identificada: preserva a quantidade no próprio registro.
            SolicitacaoEvento.objects.filter(pk=solicitacao.pk).update(
                quantidade_servidores=qtd_total
            )

        # Uma linha de histórico explica por que as etapas do fluxo não têm
        # data: o registro nasceu na planilha, não no sistema.
        HistoricoSolicitacao.objects.create(
            solicitacao=solicitacao,
            usuario=usuario,
            acao=AcaoHistorico.IMPORTACAO,
            status_novo=solicitacao.status,
            observacao=f"Linha {linha} da planilha de eventos sociais.",
        )
        return 1
