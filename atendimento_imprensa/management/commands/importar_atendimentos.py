"""Importa o histórico do "Relatório de atendimento <ano>.xlsx".

Uso:
    python manage.py importar_atendimentos caminho/planilha.xlsx --usuario tiago
    python manage.py importar_atendimentos caminho/planilha.xlsx --usuario tiago --dry-run

Cada aba é um mês com o mesmo cabeçalho. Transacional e idempotente: a
chave (aba + data + horário + jornalista + início do pedido + nº da
repetição) faz uma segunda execução atualizar em vez de duplicar.

Particularidades tratadas:
- veículos com grafias diferentes ("Uol"/"UOL", "Metrópoles"/"Metropoles")
  viram um único cadastro, com a primeira grafia encontrada;
- responsáveis com apelidos ("João P"/"João Pedro", "Gabi") são unificados;
  lixo de célula (datas, "Planilhas", "Upgrade") vira vazio;
- deadline em texto quebrado ("21//08/26", "31/09/26") vira vazio e a
  linha ganha um aviso;
- "OK" = atendido; as demais situações da planilha têm equivalente direto.
"""

import collections
import datetime as dt

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from atendimento_imprensa.models import (
    Atendimento,
    Responsavel,
    SituacaoAtendimento,
    Veiculo,
)
from core.planilhas import (
    chave_compacta,
    chave_importacao,
    como_data,
    limpa,
    limpa_multilinha,
    linha_vazia,
    norm,
    parse_hora,
    vazio,
)

COLUNAS = {
    "data": 0,
    "horario": 1,
    "jornalista": 2,
    "veiculo": 3,
    "contato": 4,
    "pedido": 5,
    "situacao": 6,
    "responsavel": 7,
    "deadline": 8,
    "horario_resposta": 9,
    "responsavel_resposta": 10,
    "fonte": 11,
    "inicio_pedido": 12,
    "final_pedido": 13,
    "andamento": 14,
    "resposta": 15,
}

APELIDOS = {
    "joao pedro": "João P",
    "jp": "João P",
    "gabi": "Gabriela",
    "natalia": "Natália",
    "nati": "Natália",
}

# Conteúdo que aparece na coluna de responsável mas não é ninguém.
LIXO_RESPONSAVEL = {"e", "planilhas", "upgrade", "-", "￼"}

SITUACOES = {
    "ok": SituacaoAtendimento.ATENDIDO,
    "atendido": SituacaoAtendimento.ATENDIDO,
    "aguardando fonte": SituacaoAtendimento.AGUARDANDO_FONTE,
    "aguardando produtora": SituacaoAtendimento.AGUARDANDO_PRODUTORA,
    "nao responder": SituacaoAtendimento.NAO_RESPONDER,
    "em andamento": SituacaoAtendimento.EM_ANDAMENTO,
    "em andamento - texto": SituacaoAtendimento.EM_ANDAMENTO_TEXTO,
    "em andamento - video": SituacaoAtendimento.EM_ANDAMENTO_VIDEO,
    "proximo mes": SituacaoAtendimento.PROXIMO_MES,
    "aguardar nova solicitacao": SituacaoAtendimento.AGUARDAR_NOVA_SOLICITACAO,
}


def _celula(linha, nome):
    indice = COLUNAS[nome]
    return linha[indice] if indice < len(linha) else None


def _texto(valor, limite=None):
    if isinstance(valor, (dt.datetime, dt.date, dt.time)):
        return ""
    texto = limpa(valor)
    if vazio(texto):
        return ""
    return texto[:limite] if limite else texto


def situacao_da_planilha(valor):
    texto = norm(valor).replace("–", "-").replace("—", "-")
    texto = " ".join(texto.split())
    if texto in SITUACOES:
        return SITUACOES[texto]
    for chave, situacao in SITUACOES.items():
        if texto.startswith(chave):
            return situacao
    return None


class Command(BaseCommand):
    help = "Importa o Relatório de atendimento à imprensa da ASCOM (planilha .xlsx)."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", help="Caminho da planilha .xlsx")
        parser.add_argument(
            "--usuario", required=True, help="Username do criador dos registros"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Simula sem gravar no banco"
        )

    def handle(self, *args, **opts):
        try:
            import openpyxl
        except ImportError:  # pragma: no cover
            raise CommandError("openpyxl não está instalado (pip install openpyxl).")

        User = get_user_model()
        try:
            self.usuario = User.objects.get(username=opts["usuario"])
        except User.DoesNotExist:
            raise CommandError(f"Usuário '{opts['usuario']}' não existe.")
        try:
            wb = openpyxl.load_workbook(opts["xlsx_path"], data_only=True)
        except FileNotFoundError:
            raise CommandError(f"Planilha não encontrada: {opts['xlsx_path']}")

        self.resumo = collections.Counter()
        self.avisos = []
        self.responsaveis = {}
        self.veiculos = {}

        with transaction.atomic():
            for ws in wb.worksheets:
                self._importar_aba(ws)
            if opts["dry_run"]:
                transaction.set_rollback(True)

        for aviso in self.avisos[:60]:
            self.stdout.write(self.style.WARNING(aviso))
        if len(self.avisos) > 60:
            self.stdout.write(self.style.WARNING(f"... e mais {len(self.avisos) - 60} avisos."))
        prefixo = "[dry-run] " if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixo}Atendimentos: {self.resumo['criados']} criados, "
                f"{self.resumo['atualizados']} atualizados, "
                f"{self.resumo['ignorados']} linhas ignoradas; "
                f"{len(self.responsaveis)} integrantes e {len(self.veiculos)} veículos."
            )
        )

    # -- cadastros ---------------------------------------------------------

    def _responsavel(self, valor):
        nome = _texto(valor, 100)
        if not nome or norm(nome) in LIXO_RESPONSAVEL or nome.startswith("Faça upgrade"):
            return None
        if any(c.isdigit() for c in nome):  # "12h29", datas coladas na coluna
            return None
        nome = limpa(nome.split("/")[0])
        nome = APELIDOS.get(norm(nome), nome)
        chave = norm(nome)
        if chave not in self.responsaveis:
            obj = Responsavel.objects.filter(nome__iexact=nome).first()
            if obj is None:
                obj = Responsavel.objects.create(nome=nome)
            self.responsaveis[chave] = obj
        return self.responsaveis[chave]

    def _veiculo(self, valor):
        if isinstance(valor, (int, float)):
            return None  # número solto na coluna de veículo não é um veículo
        nome = _texto(valor, 150)
        chave = chave_compacta(nome)
        if not nome or not chave or chave.isdigit():
            return None
        if not self.veiculos:
            # Índice inicial: grafias sem espaço/acento já cadastradas.
            for existente in Veiculo.objects.all():
                self.veiculos.setdefault(chave_compacta(existente.nome), existente)
        if chave not in self.veiculos:
            self.veiculos[chave] = Veiculo.objects.create(nome=nome)
        return self.veiculos[chave]

    # -- linhas -------------------------------------------------------------

    def _importar_aba(self, ws):
        linhas = list(ws.iter_rows(values_only=True))
        if not linhas:
            return
        cabecalho = [norm(c) for c in linhas[0]]
        if not any("pedido" in c for c in cabecalho if c):
            self.avisos.append(f"Aba '{ws.title}' sem cabeçalho reconhecido — ignorada.")
            return
        repeticoes = collections.Counter()
        for numero, linha in enumerate(linhas[1:], start=2):
            if linha_vazia(linha):
                continue
            data = como_data(_celula(linha, "data"))
            jornalista = _texto(_celula(linha, "jornalista"), 150)
            pedido = limpa_multilinha(_celula(linha, "pedido"))
            if not data or not (jornalista or pedido):
                self.resumo["ignorados"] += 1
                self.avisos.append(
                    f"{ws.title} linha {numero}: sem data, jornalista ou pedido — ignorada."
                )
                continue
            horario_bruto = _celula(linha, "horario")
            base = (
                ws.title,
                data.isoformat(),
                limpa(horario_bruto) if not isinstance(horario_bruto, float) else str(horario_bruto),
                jornalista,
                pedido[:120],
            )
            repeticoes[base] += 1
            chave = chave_importacao(*base, str(repeticoes[base]))
            self._importar_linha(
                ws.title, numero, linha, data, jornalista or "Não informado", pedido, chave
            )

    def _importar_linha(self, aba, numero, linha, data, jornalista, pedido, chave):
        situacao = situacao_da_planilha(_celula(linha, "situacao"))
        if situacao is None:
            bruto = norm(_celula(linha, "situacao"))
            if bruto:
                self.avisos.append(
                    f"{aba} linha {numero}: situação '{bruto}' desconhecida — marcada como em andamento."
                )
            situacao = SituacaoAtendimento.EM_ANDAMENTO

        deadline_bruto = _celula(linha, "deadline")
        deadline = como_data(deadline_bruto)
        if deadline is None and not vazio(deadline_bruto) and parse_hora(deadline_bruto) is None:
            self.avisos.append(
                f"{aba} linha {numero}: deadline '{limpa(deadline_bruto)}' ilegível — deixado vazio."
            )
        if deadline and deadline < data:
            self.avisos.append(
                f"{aba} linha {numero}: deadline ({deadline:%d/%m}) anterior ao pedido "
                f"({data:%d/%m}) — mantido como está."
            )

        campos = {
            "data": data,
            "horario": parse_hora(_celula(linha, "horario")),
            "jornalista": jornalista,
            "veiculo": self._veiculo(_celula(linha, "veiculo")),
            "contato": _texto(_celula(linha, "contato"), 150),
            "pedido": pedido or "(pedido não registrado)",
            "situacao": situacao,
            "responsavel": self._responsavel(_celula(linha, "responsavel")),
            "deadline": deadline,
            "horario_resposta": parse_hora(_celula(linha, "horario_resposta")),
            "responsavel_resposta": self._responsavel(_celula(linha, "responsavel_resposta")),
            "fonte": limpa_multilinha(_celula(linha, "fonte")),
            "inicio_pedido": limpa_multilinha(_celula(linha, "inicio_pedido")),
            "final_pedido": limpa_multilinha(_celula(linha, "final_pedido")),
            "andamento": limpa_multilinha(_celula(linha, "andamento")),
            "resposta": limpa_multilinha(_celula(linha, "resposta")),
        }
        for nome in ("fonte", "inicio_pedido", "final_pedido", "andamento", "resposta"):
            if vazio(campos[nome]):
                campos[nome] = ""
        existente = Atendimento.objects.filter(chave_importacao=chave).first()
        if existente:
            for nome, valor in campos.items():
                setattr(existente, nome, valor)
            existente.save()
            self.resumo["atualizados"] += 1
        else:
            Atendimento.objects.create(
                chave_importacao=chave, criado_por=self.usuario, **campos
            )
            self.resumo["criados"] += 1
