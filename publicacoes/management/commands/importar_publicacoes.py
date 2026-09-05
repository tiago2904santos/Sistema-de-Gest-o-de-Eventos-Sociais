"""Importa o histórico do "Relatório de Publicações <ano>.xlsx".

Uso:
    python manage.py importar_publicacoes caminho/planilha.xlsx --usuario tiago
    python manage.py importar_publicacoes caminho/planilha.xlsx --usuario tiago --dry-run

Cada aba é um mês, com o mesmo cabeçalho. O comando é transacional e
idempotente: a chave de importação (aba + data + título + nº da repetição)
faz uma segunda execução atualizar em vez de duplicar.

Particularidades tratadas:
- horários "17h03" / "16h" viram TimeField; "-" e textos livres viram vazio;
- "Jornalista", "Revisão" e "Galeria" viram cadastros de equipe (apelidos
  conhecidos são unificados; nomes compostos "A/B" ficam com A e a
  composição vai para o andamento);
- "Publicado na AEN?" às vezes traz o link em vez de SIM/NÃO — o link vai
  para o campo próprio e a marcação fica como "Sim";
- status "OK" = publicada; sem status mas com link/data = publicada.
"""

import collections

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.planilhas import (
    canonizar_unidade,
    chave_importacao,
    como_data,
    limpa,
    limpa_multilinha,
    linha_vazia,
    norm,
    parse_hora,
    sim_nao,
    vazio,
)
from publicacoes.models import Publicacao, Responsavel, StatusPublicacao, Unidade

COLUNAS = {
    "data": 0,
    "jornalista": 1,
    "unidade": 2,
    "fonte": 3,
    "inicio": 4,
    "titulo": 5,
    "status": 6,
    "andamento": 7,
    "edicao": 8,
    "data_publicacao": 9,
    "revisao": 10,
    "galeria": 11,
    "horario_publicacao": 12,
    "bitly": 13,
    "sesp": 14,
    "aen": 15,
    "link_site": 16,
    "link_aen": 17,
}

# Apelidos e grafias que apontam para a mesma pessoa da equipe.
APELIDOS = {
    "manu": "Manoela",
    "gabi": "Gabriela",
    "gabrielle": "Gabriela",
    "natalia": "Nati",
    "jp": "João P",
}

STATUS = {
    "ok": StatusPublicacao.PUBLICADA,
    "publicada": StatusPublicacao.PUBLICADA,
    "cancelada": StatusPublicacao.CANCELADA,
    "cancelado": StatusPublicacao.CANCELADA,
    "em andamento": StatusPublicacao.EM_ANDAMENTO,
    "pendente": StatusPublicacao.PENDENTE,
}


def _celula(linha, nome):
    indice = COLUNAS[nome]
    return linha[indice] if indice < len(linha) else None


def nome_responsavel(valor):
    """(nome principal, texto original) — "Kevin/Gabriela" -> ("Kevin", ...)."""
    texto = limpa(valor)
    if vazio(texto) or norm(texto) in {"pendente"}:
        return "", ""
    principal = limpa(texto.split("/")[0])
    principal = APELIDOS.get(norm(principal), principal)
    return principal, texto


class Command(BaseCommand):
    help = "Importa o Relatório de Publicações da ASCOM (planilha .xlsx)."

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
        self.unidades = {}

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
                f"{prefixo}Publicações: {self.resumo['criados']} criadas, "
                f"{self.resumo['atualizados']} atualizadas, "
                f"{self.resumo['ignorados']} linhas ignoradas; "
                f"{len(self.responsaveis)} integrantes e {len(self.unidades)} unidades."
            )
        )

    # -- cadastros ---------------------------------------------------------

    def _responsavel(self, valor):
        nome, original = nome_responsavel(valor)
        if not nome:
            return None, original
        chave = norm(nome)
        if chave not in self.responsaveis:
            obj = Responsavel.objects.filter(nome__iexact=nome).first()
            if obj is None:
                obj = Responsavel.objects.create(nome=nome)
            self.responsaveis[chave] = obj
        return self.responsaveis[chave], original

    def _unidade(self, valor):
        nome = canonizar_unidade(valor)
        if vazio(nome):
            return None
        chave = norm(nome)
        if chave not in self.unidades:
            obj = Unidade.objects.filter(nome__iexact=nome).first()
            if obj is None:
                obj = Unidade.objects.create(nome=nome)
            self.unidades[chave] = obj
        return self.unidades[chave]

    # -- linhas -------------------------------------------------------------

    def _importar_aba(self, ws):
        linhas = list(ws.iter_rows(values_only=True))
        if not linhas:
            return
        cabecalho = [norm(c) for c in linhas[0]]
        if not any("titulo" in c for c in cabecalho if c):
            self.avisos.append(f"Aba '{ws.title}' sem cabeçalho reconhecido — ignorada.")
            return
        repeticoes = collections.Counter()
        for numero, linha in enumerate(linhas[1:], start=2):
            if linha_vazia(linha):
                continue
            data = como_data(_celula(linha, "data"))
            titulo = limpa(_celula(linha, "titulo"))
            if not data or not titulo:
                self.resumo["ignorados"] += 1
                self.avisos.append(
                    f"{ws.title} linha {numero}: sem data ou título — ignorada."
                )
                continue
            base = (ws.title, data.isoformat(), titulo)
            repeticoes[base] += 1
            chave = chave_importacao(*base, str(repeticoes[base]))
            self._importar_linha(ws.title, numero, linha, data, titulo, chave)

    def _importar_linha(self, aba, numero, linha, data, titulo, chave):
        jornalista, jornalista_original = self._responsavel(_celula(linha, "jornalista"))
        if jornalista is None:
            jornalista, _ = self._responsavel("Não informado")
        revisao, revisao_original = self._responsavel(_celula(linha, "revisao"))
        galeria, galeria_original = self._responsavel(_celula(linha, "galeria"))

        andamento = limpa_multilinha(_celula(linha, "andamento"))
        notas = []
        for rotulo, principal, original in (
            ("Jornalista", jornalista, jornalista_original),
            ("Revisão", revisao, revisao_original),
            ("Galeria", galeria, galeria_original),
        ):
            if principal is not None and "/" in original:
                notas.append(f"{rotulo} na planilha: {original}")
        if notas:
            andamento = "\n".join(filter(None, [andamento, *notas]))

        aen_bruto = _celula(linha, "aen")
        link_site = limpa(_celula(linha, "link_site"))
        link_aen = limpa(_celula(linha, "link_aen"))
        # Coluna "Link PCPR" vazia e "Link AEN" com endereço da PCPR: era o
        # link do site que escorregou uma coluna.
        if not link_site and "policiacivil.pr.gov.br" in link_aen:
            link_site, link_aen = link_aen, ""
        publicado_aen = sim_nao(aen_bruto)
        if isinstance(aen_bruto, str) and aen_bruto.strip().lower().startswith("http"):
            publicado_aen = True
            if not link_aen:
                link_aen = limpa(aen_bruto)

        status_bruto = norm(_celula(linha, "status"))
        status = STATUS.get(status_bruto)
        data_publicacao = como_data(_celula(linha, "data_publicacao"))
        if status is None:
            if status_bruto:
                self.avisos.append(
                    f"{aba} linha {numero}: status '{status_bruto}' desconhecido."
                )
            status = (
                StatusPublicacao.PUBLICADA
                if (data_publicacao or link_site)
                else StatusPublicacao.PENDENTE
            )
        if status == StatusPublicacao.PUBLICADA and not data_publicacao:
            data_publicacao = data
        if data_publicacao and data_publicacao < data:
            self.avisos.append(
                f"{aba} linha {numero}: publicação ({data_publicacao:%d/%m}) anterior à "
                f"pauta ({data:%d/%m}) — ajustada para a data da pauta."
            )
            data_publicacao = data

        campos = {
            "data": data,
            "jornalista": jornalista,
            "unidade": self._unidade(_celula(linha, "unidade")),
            "fonte": limpa(_celula(linha, "fonte"))[:200]
            if not vazio(_celula(linha, "fonte"))
            else "",
            "inicio_pauta": parse_hora(_celula(linha, "inicio")),
            "titulo": titulo[:300],
            "status": status,
            "andamento": andamento,
            "colocada_edicao": parse_hora(_celula(linha, "edicao")),
            "data_publicacao": data_publicacao,
            "horario_publicacao": parse_hora(_celula(linha, "horario_publicacao")),
            "revisao": revisao,
            "galeria_fotos": galeria,
            "bitly_grupos": sim_nao(_celula(linha, "bitly")),
            "enviado_sesp": sim_nao(_celula(linha, "sesp")),
            "publicado_aen": publicado_aen,
            "link_site": link_site[:500],
            "link_aen": link_aen[:500],
        }
        existente = Publicacao.objects.filter(chave_importacao=chave).first()
        if existente:
            for nome, valor in campos.items():
                setattr(existente, nome, valor)
            existente.save()
            self.resumo["atualizados"] += 1
        else:
            Publicacao.objects.create(
                chave_importacao=chave, criado_por=self.usuario, **campos
            )
            self.resumo["criados"] += 1
