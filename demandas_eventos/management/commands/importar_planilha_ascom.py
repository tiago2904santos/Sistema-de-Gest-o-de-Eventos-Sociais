"""Importa o histórico de Palestras e Eventos da ASCOM sem duplicar registros."""

import hashlib
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from accounts.models import Setor
from cadastros.models import Municipio
from demandas_eventos.models import (
    AcaoHistoricoDemanda,
    DemandaEvento,
    Palestrante,
    RespostaPadrao,
    StatusDemanda,
    Tema,
    TipoEventoPalestra,
)
from demandas_eventos.horarios import extrair_horarios
from demandas_eventos.planilha import canal_e_protocolo, chave as chave_nome, palestrantes_do_texto, telefone_e_email
from demandas_eventos.services import registrar_historico


def _texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _chave(valor):
    valor = unicodedata.normalize("NFKD", _texto(valor)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", valor.upper()).strip()


def _data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = _texto(valor)
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


STATUS = {
    "PENDENTE": StatusDemanda.PENDENTE,
    "AGUARDANDO RETORNO": StatusDemanda.AGUARDANDO_RETORNO,
    "EM ANDAMENTO": StatusDemanda.EM_ANDAMENTO,
    "EVENTO AGENDADO": StatusDemanda.EVENTO_AGENDADO,
    "PALESTRA AGENDADA": StatusDemanda.EVENTO_AGENDADO,
    "ATENDIDA": StatusDemanda.ATENDIDA,
    "SOL ATENDIDA": StatusDemanda.ATENDIDA,
    "NAO ATENDER": StatusDemanda.CANCELADA,
    "CANCELADA": StatusDemanda.CANCELADA,
}


def _evento(valor):
    """A coluna "Evento" (ou "Tipo de Evento") nos três tipos da ASCOM."""
    chave = _chave(valor)
    if "PALESTRA" in chave:
        return TipoEventoPalestra.PALESTRA
    if "COMUNIDADE" in chave:
        return TipoEventoPalestra.PCPR_NA_COMUNIDADE
    return TipoEventoPalestra.EVENTO


_DIA_MES = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_DIAS_MES = re.compile(r"(?<![/\d])\b(\d{1,2})\s*(?:a|à|e|até)\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", re.I)
_HORA = re.compile(r"\b\d{1,2}\s*(?:h|:)\s*\d{0,2}", re.I)


def _periodo(valor, referencia):
    """(início, fim, texto) da coluna "Data do evento".

    A planilha mistura datas de verdade com "13/05 e 14/05", "06/03 a 08/03"
    ou "À definir". Dia/mês sem ano ganha o ano da solicitação (ou o
    seguinte, quando a data cairia antes do pedido). O texto só fica quando
    diz mais que as datas — um horário, "à definir".
    """
    data = _data(valor) if isinstance(valor, (date, datetime)) else None
    if data:
        return data, None, ""
    texto = _texto(valor)
    datas = []
    # "27 à 31/07", "18 e 19/04/2023": o primeiro dia herda o mês do último.
    achados = [
        (primeiro, mes, ano) for primeiro, _, mes, ano in _DIAS_MES.findall(texto)
    ] + _DIA_MES.findall(texto)
    for dia, mes, ano in achados:
        try:
            ano_num = int(ano) if ano else referencia.year
            if ano and ano_num < 100:
                ano_num += 2000
            candidata = date(ano_num, int(mes), int(dia))
            if not ano and candidata < referencia - timedelta(days=60):
                candidata = date(ano_num + 1, int(mes), int(dia))
            datas.append(candidata)
        except ValueError:
            continue
    if not datas:
        return None, None, texto
    inicio, fim = min(datas), max(datas)
    # O que sobra sem as datas costuma ser o horário ("10h30 e 14h00"):
    # fica só ele. Se sobrar outro número ("DE 12 A"), o texto inteiro fica,
    # porque as datas não disseram tudo.
    sobra = re.sub(r"^(?:[\s,;:\-–]|(?:às|as|a|e|das)\b)+", "", _DIA_MES.sub(" ", _DIAS_MES.sub(" ", texto)), flags=re.I)
    sobra = re.sub(r"\s+", " ", sobra).strip(" ,;:-–")
    if re.search(r"\d", _HORA.sub("", sobra)):
        sobra = texto
    return inicio, (fim if fim != inicio else None), sobra


def _publico(valor):
    """(quantidade, texto que sobrou) da coluna de público."""
    texto = _texto(valor)
    if not texto:
        return None, ""
    try:
        numero = float(texto)
        return (int(numero), "") if numero >= 0 else (None, texto)
    except ValueError:
        numeros = [int(n) for n in re.findall(r"\d+", texto)]
        if numeros and "+" in texto:
            return sum(numeros), texto
        return None, texto


MAPAS = {
    "2022": {
        "data_solicitacao": "Data", "solicitante": "Solicitante", "contato": "Contato",
        "tipo": "Evento", "tema": "TEMA", "pedido": "Pedido/Contato",
        "periodo": "Data do evento", "status": "Status da demanda",
        "responsavel": "Responsável pelo atendimento", "andamento": "Andamento",
        "servidor": "Servidor", "unidade": "Unidade", "publico": "Público",
        "briefing": "Briefing", "materia": "Texto publicado na página",
    },
    "2023": {
        "data_solicitacao": "Data", "solicitante": "Solicitante", "contato": "Contato",
        "tipo": "Evento", "organizacao": "Responsável pela organização", "tema": "TEMA",
        "pedido": "Pedido/Contato", "periodo": "Data do evento", "status": "Status da demanda",
        "responsavel": "Responsável pelo atendimento", "andamento": "Andamento",
        "servidor": "Servidor", "unidade": "Unidade", "publico": "Público",
        "briefing": "Briefing", "materia": "Texto publicado na página",
    },
    "2024": {
        "data_solicitacao": "Data da Solicitação", "tipo": "Tipo de Evento",
        "canal": "Por onde foi solicitado", "tema": "Tema", "status": "Status da demanda",
        "andamento": "Andamento", "periodo": "Data do evento", "solicitante": "Solicitante",
        "contato": "Contato", "municipio": "Município", "pedido": "Pedido/Contato",
        "servidor": "Servidor", "unidade": "Unidade", "publico": "Público",
        "briefing": "Breafing Palestra", "materia": "Matéria no Site",
        "responsavel": "Responsável pelo Atendimento",
    },
    "2025": {
        "data_solicitacao": "Data da Solicitação", "tipo": "EVENTO",
        "canal": "Por onde foi solicitado", "tema": "Tema", "publico": "Quantidade de público",
        "status": "Status da demanda", "andamento": "Andamento", "municipio": "Município",
        "periodo": "Data do evento", "solicitante": "Solicitante", "contato": "Contato",
        "assunto": "ASSUNTO E-MAIL", "pedido": "Pedido/Contato", "servidor": "Servidor",
    },
    "2026": {
        "municipio": "MUNICIPIO", "periodo": "DATA DO EVENTO E HORA (PERÍODO)",
        "tipo": "EVENTO", "status": "STATUS DA DEMANDA", "andamento": "ANDAMENTO",
        "informacoes": "INFORMAÇÕES PRÉVIAS", "solicitante": "SOLICITANTE",
        "contato": "CONTATO", "data_solicitacao": "DATA DA SOLICITAÇÃO",
        "canal": "FOI SOLICITADO VIA:", "descricao": "DESCRIÇÃO",
        "publico": "QUANTIDADE DE PÚBLICO", "assunto": "ASSUNTO E-MAIL",
        "pedido": "PEDIDO/CONTATO",
    },
}


class Command(BaseCommand):
    help = "Importa a planilha Palestras e Eventos ASCOM (.xlsx)"

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--dry-run", action="store_true", help="Valida sem persistir")

    @transaction.atomic
    def handle(self, *args, **options):
        caminho = Path(options["arquivo"])
        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        ascom = Setor.objects.filter(sigla="ASCOM").first()
        if not ascom:
            raise CommandError("O setor ASCOM não está cadastrado. Aplique as migrations da fundação.")

        workbook = load_workbook(caminho, data_only=True, read_only=False)
        resumo = {"demandas": 0, "palestrantes": 0, "temas": 0, "respostas": 0, "ignoradas": 0, "avisos": 0}
        try:
            self._importar_temas(workbook, resumo)
            self._importar_palestrantes(workbook, resumo)
            self._importar_respostas(workbook, resumo)
            for aba, mapa in MAPAS.items():
                if aba in workbook.sheetnames:
                    self._importar_demandas(workbook[aba], aba, mapa, ascom, resumo)
        finally:
            workbook.close()

        if options["dry_run"]:
            transaction.set_rollback(True)
            prefixo = "Dry-run concluído"
        else:
            prefixo = "Importação concluída"
        self.stdout.write(self.style.SUCCESS(prefixo + ": " + ", ".join(f"{k}={v}" for k, v in resumo.items())))

    def _importar_temas(self, workbook, resumo):
        """A aba TEMAS é a lista inteira: o que não está nela sai.

        A aba não tem cabeçalho — a primeira linha já é um tema. Um tema que
        sai e estava numa palestra deixa o nome em "Informações prévias".
        """
        self.temas = {}
        if "TEMAS" not in workbook.sheetnames:
            self.temas = {_chave(t.nome): t for t in Tema.objects.all()}
            return
        for (valor,) in workbook["TEMAS"].iter_rows(values_only=True, max_col=1):
            nome = _texto(valor)
            if not nome or _chave(nome) in self.temas:
                continue
            tema = next((t for t in Tema.objects.all() if _chave(t.nome) == _chave(nome)), None)
            if not tema:
                tema = Tema.objects.create(nome=nome)
                resumo["temas"] += 1
            self.temas[_chave(nome)] = tema
        if not self.temas:
            return
        manter = [t.pk for t in self.temas.values()]
        for tema in Tema.objects.exclude(pk__in=manter):
            for demanda in DemandaEvento.objects.filter(temas=tema):
                demanda.informacoes_previas = "\n".join(
                    parte for parte in [demanda.informacoes_previas.strip(), f"Tema: {tema.nome}"] if parte
                )
                demanda.save(update_fields=["informacoes_previas", "atualizado_em"])
            tema.delete()
            resumo["temas_removidos"] = resumo.get("temas_removidos", 0) + 1

    def palestrantes_por_nome(self):
        if not hasattr(self, "_palestrantes_por_nome"):
            self._palestrantes_por_nome = {}
            for p in Palestrante.objects.all():
                self._palestrantes_por_nome.setdefault(chave_nome(p.nome), p)
        return self._palestrantes_por_nome

    def _importar_palestrantes(self, workbook, resumo):
        if "PALESTRANTES" not in workbook.sheetnames:
            return
        ws = workbook["PALESTRANTES"]
        headers = {_chave(c.value): i for i, c in enumerate(ws[1]) if c.value}
        for valores in ws.iter_rows(min_row=2, values_only=True):
            nome = _texto(valores[headers.get("SERVIDOR", -1)]) if "SERVIDOR" in headers else ""
            if not nome:
                continue
            lotacao = _texto(valores[headers.get("LOTACAO", -1)]) if "LOTACAO" in headers else ""
            defaults = {
                "municipio_texto": _texto(valores[headers.get("MUNICIPIO", -1)]) if "MUNICIPIO" in headers else "",
                "divisao": _texto(valores[headers.get("DIVISAO", -1)]) if "DIVISAO" in headers else "",
                "contato": _texto(valores[headers.get("CONTATO", -1)]) if "CONTATO" in headers else "",
                "email": _texto(valores[headers.get("E MAIL", -1)]) if "E MAIL" in headers else "",
                "tema_abordagem": (_texto(valores[headers.get("TEMA DE ABORDAGEM", -1)]) if "TEMA DE ABORDAGEM" in headers else "")[:300],
            }
            palestrante, criado = Palestrante.objects.update_or_create(nome=nome, lotacao=lotacao, defaults=defaults)
            resumo["palestrantes"] += int(criado)

    def _importar_respostas(self, workbook, resumo):
        nome_aba = next((n for n in workbook.sheetnames if _chave(n) == "REPOSTAS PADRAO"), None)
        if not nome_aba:
            return
        for tipo, mensagem, *_ in workbook[nome_aba].iter_rows(min_row=2, values_only=True):
            tipo, mensagem = _texto(tipo), _texto(mensagem)
            if not tipo or not mensagem:
                continue
            _, criado = RespostaPadrao.objects.update_or_create(tipo=tipo, defaults={"mensagem": mensagem})
            resumo["respostas"] += int(criado)

    def _importar_demandas(self, ws, aba, mapa, ascom, resumo):
        headers = {_chave(c.value): i for i, c in enumerate(ws[1]) if c.value}

        def obter(valores, campo):
            cabecalho = mapa.get(campo)
            indice = headers.get(_chave(cabecalho)) if cabecalho else None
            return valores[indice] if indice is not None and indice < len(valores) else None

        for numero, valores in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            solicitante = _texto(obter(valores, "solicitante"))
            tipo_nome = _texto(obter(valores, "tipo"))
            pedido = _texto(obter(valores, "pedido"))
            if not any((solicitante, tipo_nome, pedido)):
                continue
            data_solicitacao = _data(obter(valores, "data_solicitacao"))
            if not data_solicitacao:
                resumo["avisos"] += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"{aba}, linha {numero}: data da solicitação inválida; linha ignorada."
                    )
                )
                continue
            # Só vale tema da aba TEMAS; o texto livre da coluna fica em
            # "Informações prévias", para não virar tema novo.
            tema_nome = _texto(obter(valores, "tema"))
            tema = self.temas.get(_chave(tema_nome)) if tema_nome else None
            municipio_nome = _texto(obter(valores, "municipio"))
            municipio = Municipio.objects.filter(nome__iexact=municipio_nome).first() if municipio_nome else None
            inicio, fim, periodo_texto = _periodo(obter(valores, "periodo"), data_solicitacao)
            hora_inicio, hora_fim, periodo_texto = extrair_horarios(periodo_texto)
            if hora_fim:
                # Um horário só na tela: o término fica escrito na observação.
                periodo_texto = " ".join(x for x in (f"até {hora_fim:%H:%M}", periodo_texto) if x)
            publico, publico_texto = _publico(obter(valores, "publico"))
            status_original = _chave(obter(valores, "status"))
            status = STATUS.get(status_original, StatusDemanda.PENDENTE)
            if status_original and status_original not in STATUS:
                resumo["avisos"] += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"{aba}, linha {numero}: status '{status_original}' não reconhecido; "
                        "importado como Pendente."
                    )
                )
            # Colunas dos anos anteriores que o formulário não tem mais: o
            # conteúdo vai para "Informações prévias", com o nome da coluna.
            sobras = [
                ("Tema", tema_nome if tema_nome and not tema else ""),
                ("Tipo de evento", tipo_nome if _evento(tipo_nome) == TipoEventoPalestra.EVENTO and _chave(tipo_nome) != "EVENTO" else ""),
                ("Quantidade de público", publico_texto),
                ("Responsável pela organização", _texto(obter(valores, "organizacao"))),
                ("Responsável pelo atendimento", _texto(obter(valores, "responsavel"))),
                ("Unidade", _texto(obter(valores, "unidade"))),
                ("Briefing", _texto(obter(valores, "briefing"))),
                ("Matéria no site", _texto(obter(valores, "materia"))),
            ]
            canal, protocolo, canal_sobra = canal_e_protocolo(_texto(obter(valores, "canal")))
            if canal_sobra:
                sobras.append(("Foi solicitado via", canal_sobra))
            telefone, email, contato_sobra = telefone_e_email(_texto(obter(valores, "contato")))
            servidor_texto = _texto(obter(valores, "servidor"))
            palestrantes = palestrantes_do_texto(servidor_texto, self.palestrantes_por_nome())
            informacoes = "\n".join(
                parte
                for parte in [_texto(obter(valores, "informacoes"))]
                + [f"{rotulo}: {valor}" for rotulo, valor in sobras if valor]
                if parte
            )
            identidade = "|".join([aba, str(numero), str(data_solicitacao), solicitante, tipo_nome, pedido[:100]])
            chave = hashlib.sha256(identidade.encode("utf-8")).hexdigest()
            defaults = {
                "municipio": municipio,
                "municipio_texto": "" if municipio else municipio_nome,
                "data_inicio_evento": inicio,
                "data_fim_evento": fim,
                "hora_inicio": hora_inicio,
                "periodo_evento_texto": periodo_texto[:200],
                "evento": _evento(tipo_nome),
                "status": status,
                "andamento": _texto(obter(valores, "andamento")),
                "informacoes_previas": informacoes,
                "solicitante": solicitante or "Não informado",
                "telefone": telefone,
                "email": email,
                "contato": contato_sobra[:300],
                "data_solicitacao": data_solicitacao,
                "canal_solicitacao": canal,
                "protocolo": protocolo,
                "descricao": _texto(obter(valores, "descricao")),
                "quantidade_publico": publico,
                "assunto_email": _texto(obter(valores, "assunto"))[:300],
                "pedido_contato": pedido,
                "servidor": "" if palestrantes else servidor_texto[:300],
                "origem_importacao": f"{aba}:linha {numero}",
            }
            demanda, criada = DemandaEvento.objects.update_or_create(chave_importacao=chave, defaults=defaults)
            demanda.setores.set([ascom])
            demanda.temas.set([tema] if tema else [])
            demanda.palestrantes.set(palestrantes)
            if criada:
                registrar_historico(
                    demanda,
                    None,
                    AcaoHistoricoDemanda.CRIACAO,
                    f"Importada de {demanda.origem_importacao}.",
                    status_novo=demanda.status,
                )
            resumo["demandas" if criada else "ignoradas"] += 1
