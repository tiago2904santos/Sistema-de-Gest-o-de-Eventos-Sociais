"""Aplicação do plano: os documentos do processo viram anexos da prestação.

Tudo ou nada (`transacao_de_arquivos`): uma falha no meio desfaz as linhas e
apaga os arquivos criados; os anexos antigos só perdem o arquivo depois do
commit. A leitura pesada já aconteceu na análise — aqui só se recorta, gira e
grava.

**Semântica de gravação** (a mesma dos endpoints de anexar, feita explícita):

- ofício, despacho(s) e diário são do ofício: substituem os do mesmo tipo da
  prestação. Vários despachos entram todos, na ordem do processo, cada um com a
  sua folha de assinatura;
- RT e comprovantes são de um servidor: substituem os daquele servidor. Os
  comprovantes entram todos, cada um com valor, data e operação;
- status: documento compartilhado marca a equipe (`marcar_servidores_pendentes`),
  individual marca o servidor (`marcar_servidor_em_preenchimento`) — nunca
  finaliza nada;
- o ofício assinado é carimbado com os números de solicitação num savepoint
  próprio: `CarimboError` vira aviso ("ajuste a posição do nº da solicitação"),
  não derruba a importação;
- o diário sai girado (paisagem em pé), com o recorte cru em `arquivo_original`;
- achado pelo nº/ano, o ofício sem protocolo oficial recebe o protocolo real lido
  (origem MANUAL), e o resultado diz isso;
- convalidação: o resultado avisa se faltar RT de alguém ou o diário;
- documentos gerados pelo sistema (`artefatos`): o ofício assinado vira também a
  versão assinada do documento do ofício; justificativa, termos (um por
  servidor) e ordem de serviço vão para a versão assinada do documento deles —
  gerando antes o PDF que ainda não existia. Sem prestação (termo avulso, sem
  ofício), só os termos são gravados.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field

from django.core.files.base import ContentFile
from django.utils import timezone

from core.errors import capture
from core.utils.masks import format_protocolo

from ..anexo_services import remover_anexos_do_tipo
from ..arquivos import transacao_de_arquivos
from ..models import OPERACAO_CHOICES
from ..models import ORDEM_DOCUMENTOS_PRESTACAO
from ..models import ImportacaoProcesso
from ..models import PrestacaoContas
from ..models import PrestacaoDocumentoAnexo as Anexo
from ..services import marcar_servidor_em_preenchimento
from ..services import marcar_servidores_pendentes
from .montagem import descrever_paginas
from .montagem import recortar_documento
from .plano import DESTINO_JUSTIFICATIVA
from .plano import DESTINO_ORDEM_SERVICO
from .plano import DESTINO_TERMO
from .plano import IGNORAR
from .plano import ROTULO_DESTINO
from .plano import ItemPlano
from .plano import Plano

__all__ = ["ImportacaoRecusada", "ResultadoImportacao", "aplicar_importacao", "resumo_da_importacao"]

_OPERACOES = {valor for valor, _ in OPERACAO_CHOICES}


class ImportacaoRecusada(Exception):
    """O plano não pode ser aplicado como está (mensagem para a tela)."""


@dataclass
class ResultadoImportacao:
    """O que foi gravado, para a mensagem da tela e para `ImportacaoProcesso.resultado`.

    `anexos` são os anexos da prestação; `documentos`, as versões assinadas dos
    documentos gerados (ofício, justificativa, termos, OS), uma por documento que
    recebeu. `resumo_documentos` é a frase deles, ao lado do `resumo` da prestação.
    """

    resumo: str = ""
    avisos: list[str] = field(default_factory=list)
    anexos: list[dict] = field(default_factory=list)
    protocolo_gravado: str = ""
    documentos: list[dict] = field(default_factory=list)
    resumo_documentos: str = ""
    #: Anexos que já existiam e foram trocados pelos do processo (desfazer não os devolve).
    substituidos: int = 0

    def para_json(self) -> dict:
        return {
            "resumo": self.resumo,
            "avisos": list(self.avisos),
            "anexos": list(self.anexos),
            "protocolo_gravado": self.protocolo_gravado,
            "documentos": list(self.documentos),
            "resumo_documentos": self.resumo_documentos,
            "substituidos": self.substituidos,
        }


# ─────────────────────────────────────────────────────────────────
# Conferências antes de gravar
# ─────────────────────────────────────────────────────────────────

def _conferir_plano(plano: Plano, prestacao: PrestacaoContas | None, equipe: dict, *, termo=None) -> None:
    from .artefatos import servidores_com_termo

    if prestacao is not None and prestacao.oficio.cancelado:
        raise ImportacaoRecusada("O ofício desta prestação está cancelado: não recebe documentos.")
    if termo is not None and termo.cancelado:
        raise ImportacaoRecusada(f"O Termo #{termo.pk} está cancelado: não recebe documentos.")
    pendencias = plano.pendencias
    if pendencias:
        raise ImportacaoRecusada(" ".join(pendencias))
    com_termo = None
    for item in plano.itens:
        if item.individual and item.servidor_prestacao_id not in equipe:
            raise ImportacaoRecusada(
                f"Documento {item.ordem}: o servidor escolhido não é da equipe desta prestação."
            )
        if (item.entra or item.vai_para_documento) and not item.paginas:
            raise ImportacaoRecusada(f"Documento {item.ordem}: sem páginas.")
        if prestacao is None and (item.entra or item.destino == DESTINO_JUSTIFICATIVA):
            raise ImportacaoRecusada(f"Documento {item.ordem}: sem prestação nem ofício para recebê-lo.")
        if item.destino == DESTINO_TERMO:
            if com_termo is None:
                com_termo = {s.pk for s in servidores_com_termo(prestacao.oficio if prestacao else None, termo)}
            if item.servidor_id not in com_termo:
                raise ImportacaoRecusada(
                    f"Documento {item.ordem}: o servidor escolhido não tem termo nesta viagem."
                )
        if item.destino == DESTINO_ORDEM_SERVICO:
            from viagens_ordens.models import OrdemServico

            if not OrdemServico.objects.filter(pk=item.ordem_servico_id, cancelado=False).exists():
                raise ImportacaoRecusada(f"Documento {item.ordem}: a ordem de serviço escolhida não existe ou está cancelada.")
    oficios = [item for item in plano.itens if item.destino == Anexo.TIPO_OFICIO_ASSINADO]
    if len(oficios) > 1:
        raise ImportacaoRecusada(
            "Mais de um documento marcado como ofício assinado: deixe um só (os outros, “Não entra”)."
        )


# ─────────────────────────────────────────────────────────────────
# Gravação
# ─────────────────────────────────────────────────────────────────

def _ler_arquivo(importacao) -> bytes:
    from core.leitura.pdf import como_pdf

    importacao.arquivo.open("rb")
    try:
        return como_pdf(importacao.arquivo.read())
    finally:
        importacao.arquivo.close()


def _nome_original(item: ItemPlano, protocolo: str) -> str:
    """O nome que a tela mostra para o anexo: o arquivo original no eProtocolo, quando se sabe."""
    titulo = (item.titulo or "").strip()
    if titulo:
        return titulo[:255]
    rotulo = ROTULO_DESTINO.get(item.destino, "Documento")
    folhas = descrever_paginas(item.paginas)
    origem = f" do processo {format_protocolo(protocolo) or protocolo}" if protocolo else ""
    return f"{rotulo}{origem} (folhas {folhas}).pdf"[:255]


def _criar_anexo(prestacao, importacao, item: ItemPlano, pdf: bytes, *, servidor_prestacao, protocolo: str) -> Anexo:
    anexo = Anexo(
        prestacao=prestacao,
        servidor_prestacao=servidor_prestacao,
        tipo=item.destino,
        nome_original=_nome_original(item, protocolo),
        importacao=importacao,
        paginas_origem=descrever_paginas(item.paginas),
    )
    if item.destino == Anexo.TIPO_COMPROVANTE:
        valor = item.valor_decimal
        anexo.valor = valor if valor is not None and valor > 0 else None
        anexo.data_operacao = item.data_operacao
        anexo.operacao = item.operacao if item.operacao in _OPERACOES else ""
    base = f"{item.destino}_{protocolo or 'processo'}_{item.ordem}"
    anexo.arquivo.save(f"{base}.pdf", ContentFile(recortar_documento(pdf, item.paginas, item.rotacoes_finais)), save=False)
    if item.girado:
        # O recorte como estava no processo: é dele que se refaz o giro.
        anexo.arquivo_original.save(f"{base}_cru.pdf", ContentFile(recortar_documento(pdf, item.paginas)), save=False)
    anexo.save()
    return anexo


def _carimbar(anexo, prestacao) -> list[str]:
    """Carimba os números de solicitação num savepoint; o erro vira aviso."""
    from ..carimbo_services import CarimboError
    from ..carimbo_services import preparar_e_carimbar

    try:
        with transacao_de_arquivos():
            resultado = preparar_e_carimbar(anexo, prestacao=prestacao)
    except CarimboError as exc:
        return [f"Ofício anexado sem o nº da solicitação ({exc}): ajuste a posição do nº da solicitação em “Ajustar posição”."]
    avisos = []
    if resultado.erro:
        avisos.append(f"Ofício anexado, mas o carimbo falhou: {resultado.erro} Ajuste a posição do nº da solicitação em “Ajustar posição”.")
    if resultado.sem_posicao:
        avisos.append(
            "Ajuste a posição do nº da solicitação de " + ", ".join(resultado.sem_posicao)
            + " em “Ajustar posição” (não deu para achar o lugar com segurança)."
        )
    if resultado.sem_numero:
        avisos.append(
            "Sem número de solicitação, e por isso fora do carimbo: " + ", ".join(resultado.sem_numero)
            + ". Preencha o número e o ofício é recarimbado sozinho."
        )
    return avisos


def _gravar_protocolo(oficio, protocolo: str) -> str:
    """Grava o protocolo real lido no ofício sem protocolo oficial. Devolve o formatado, ou ""."""
    from viagens_oficios.models import Oficio

    oficio = Oficio.objects.get(pk=oficio.pk)
    if not protocolo or oficio.protocolo == protocolo:
        return ""
    if oficio.protocolo and oficio.protocolo_origem not in Oficio.PROTOCOLO_ORIGENS_NAO_OFICIAIS:
        return ""
    anterior = format_protocolo(oficio.protocolo) or oficio.protocolo
    oficio.protocolo = protocolo
    oficio.protocolo_origem = Oficio.PROTOCOLO_ORIGEM_MANUAL
    oficio.protocolo_situacao = ""
    oficio.protocolo_criado_em = None
    oficio.save(update_fields=["protocolo", "protocolo_origem", "protocolo_situacao", "protocolo_criado_em", "atualizado_em"])
    formatado = format_protocolo(protocolo) or protocolo
    return f"{formatado} (no lugar de {anterior}, que não era oficial)" if anterior else formatado


def _avisos_de_convalidacao(prestacao) -> list[str]:
    """Na convalidação, RT e diário vêm no mesmo processo: avisa o que faltou."""
    from viagens_oficios.assunto_oficio import resolver_assunto_oficio

    try:
        termo = resolver_assunto_oficio(prestacao.oficio)["assunto_termo"]
    except Exception as exc:  # roteiro incompleto: sem como saber, sem aviso
        capture(exc, "prestacoes.importacao.convalidacao", level=logging.WARNING, prestacao_id=prestacao.pk)
        return []
    if termo != "convalidação":
        return []
    avisos = []
    sem_rt = [
        ps.servidor.nome
        for ps in prestacao.servidores_prestacao.select_related("servidor").order_by("pk")
        if not ps.documentos_anexos.filter(tipo=Anexo.TIPO_RT_ASSINADO).exists()
    ]
    if sem_rt:
        avisos.append(f"Convalidação: falta o relatório técnico assinado de {', '.join(sem_rt)}.")
    if not prestacao.documentos_anexos.filter(tipo=Anexo.TIPO_DB_ASSINADO).exists():
        avisos.append("Convalidação: falta o diário de bordo assinado.")
    return avisos


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {plural}" if n != 1 else singular


def resumo_da_importacao(protocolo: str, oficio, criados: list[tuple[ItemPlano, Anexo]]) -> str:
    """"Processo 26.613.666-8 importado na prestação do Ofício 12/2026: ofício, 2 despachos, …"."""
    por_tipo: dict[str, list[tuple[ItemPlano, Anexo]]] = {}
    for item, anexo in criados:
        por_tipo.setdefault(anexo.tipo, []).append((item, anexo))
    partes = []
    for tipo in ORDEM_DOCUMENTOS_PRESTACAO:
        lista = por_tipo.get(tipo) or []
        if not lista:
            continue
        if tipo == Anexo.TIPO_OFICIO_ASSINADO:
            partes.append("ofício")
        elif tipo == Anexo.TIPO_DESPACHO:
            partes.append(_plural(len(lista), "despacho", "despachos"))
        elif tipo == Anexo.TIPO_RT_ASSINADO:
            servidores = len({anexo.servidor_prestacao_id for _, anexo in lista})
            partes.append(f"RT de {servidores} servidor" + ("es" if servidores != 1 else ""))
        elif tipo == Anexo.TIPO_DB_ASSINADO:
            girado = any(item.girado for item, _ in lista)
            partes.append(_plural(len(lista), "diário", "diários") + (" (girado)" if girado else ""))
        elif tipo == Anexo.TIPO_COMPROVANTE:
            partes.append(_plural(len(lista), "1 comprovante", "comprovantes"))
    cabeca = f"Processo {format_protocolo(protocolo) or protocolo}" if protocolo else "Processo"
    return f"{cabeca} importado na prestação do Ofício {oficio.numero_formatado}: {', '.join(partes)}."


def _e_lista(nomes: list[str]) -> str:
    """"A", "A e B", "A, B e C"."""
    nomes = list(dict.fromkeys(n for n in nomes if n))
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def resumo_dos_documentos(documentos: list[dict]) -> str:
    """"Versões assinadas anexadas: ofício, justificativa, termos de A e B, Ordem de Serviço 05/2026."."""

    def partes(lista: list[dict]) -> list[str]:
        saida = []
        destinos = [d["destino"] for d in lista]
        if Anexo.TIPO_OFICIO_ASSINADO in destinos:
            saida.append("ofício")
        if DESTINO_JUSTIFICATIVA in destinos:
            saida.append("justificativa")
        servidores = [d.get("servidor", "") for d in lista if d["destino"] == DESTINO_TERMO]
        if servidores:
            unicos = list(dict.fromkeys(servidores))
            saida.append(("termo de " if len(unicos) == 1 else "termos de ") + _e_lista(unicos))
        saida.extend(dict.fromkeys(d["alvo"] for d in lista if d["destino"] == DESTINO_ORDEM_SERVICO))
        return saida

    novos = partes([d for d in documentos if not d.get("repetido")])
    repetidos = partes([d for d in documentos if d.get("repetido")])
    frases = []
    if novos:
        frases.append(f"Versões assinadas anexadas: {', '.join(novos)}.")
    if repetidos:
        frases.append(f"Já estavam anexados: {', '.join(repetidos)}.")
    return " ".join(frases)


def _anexar_documentos(plano: Plano, pdf: bytes, *, prestacao, termo) -> tuple[list[dict], list[str]]:
    """As versões assinadas: ofício, justificativa, termos e OS. Devolve (documentos, avisos)."""
    from viagens_cadastros.models import Servidor
    from viagens_ordens.models import OrdemServico

    from .artefatos import alvos_da_justificativa
    from .artefatos import alvos_da_ordem
    from .artefatos import alvos_do_oficio
    from .artefatos import alvos_do_termo
    from .artefatos import anexar_nos_alvos

    oficio = prestacao.oficio if prestacao is not None else None
    documentos: list[dict] = []
    avisos: list[str] = []
    for item in plano.itens:
        if not item.vai_para_documento:
            continue
        servidor = None
        if item.destino == Anexo.TIPO_OFICIO_ASSINADO:
            alvos = alvos_do_oficio(oficio) if oficio is not None else []
        elif item.destino == DESTINO_JUSTIFICATIVA:
            alvos = alvos_da_justificativa(oficio) if oficio is not None else []
        elif item.destino == DESTINO_TERMO:
            servidor = Servidor.objects.get(pk=item.servidor_id)
            alvos = alvos_do_termo(servidor, oficio=oficio, termo=termo)
        else:
            alvos = alvos_da_ordem(OrdemServico.objects.get(pk=item.ordem_servico_id))
        if not alvos:
            continue
        conteudo = recortar_documento(pdf, item.paginas, item.rotacoes_finais)
        anexados, avisos_do_item = anexar_nos_alvos(alvos, conteudo, _nome_original(item, plano.protocolo))
        avisos.extend(avisos_do_item)
        for anexado in anexados:
            documentos.append({
                "ordem": item.ordem,
                "destino": item.destino,
                "alvo": anexado.alvo.rotulo,
                "artefato": anexado.artefato_id,
                "gerado": anexado.gerado,
                "repetido": anexado.repetido,
                "url": anexado.alvo.url_pagina,
                "servidor": servidor.nome if servidor is not None else "",
            })
    return documentos, avisos


def _remover_da_importacao(importacao: ImportacaoProcesso) -> None:
    from ..anexo_services import _apagar_arquivo_apos_commit

    if importacao.pk is None:
        return
    anteriores = Anexo.objects.filter(importacao=importacao)
    for anexo in anteriores:
        for campo in (anexo.arquivo, anexo.arquivo_original):
            if campo:
                _apagar_arquivo_apos_commit(campo)
    anteriores.delete()


def so_comprovantes(plano: Plano) -> bool:
    """O plano só grava comprovantes (a foto ou o PDF de um comprovante)."""
    gravados = [item for item in plano.itens if item.destino != IGNORAR]
    return bool(gravados) and all(item.destino == Anexo.TIPO_COMPROVANTE for item in gravados)


def aplicar_importacao(importacao: ImportacaoProcesso, *, plano: Plano | None = None) -> ResultadoImportacao:
    """Grava o plano (o da importação, ou o editado na conferência): anexos da
    prestação e versões assinadas dos documentos gerados.

    Levanta `ImportacaoRecusada` antes de gravar qualquer coisa se o plano estiver
    incompleto. Qualquer outra falha desfaz tudo: nenhum anexo novo, nenhuma versão
    assinada nova, nenhum arquivo órfão, e o que já estava anexado intacto.
    """
    plano = plano or Plano.de_json(importacao.plano)
    if not plano.tem_registro:
        raise ImportacaoRecusada("Escolha a prestação de contas deste processo.")
    prestacao = None
    if plano.prestacao_id:
        try:
            prestacao = PrestacaoContas.objects.select_related("oficio").get(pk=plano.prestacao_id)
        except PrestacaoContas.DoesNotExist as exc:
            raise ImportacaoRecusada("A prestação escolhida não existe mais.") from exc
    termo = None
    if plano.termo_id:
        from viagens_termos.models import TermoAutorizacao

        termo = TermoAutorizacao.objects.select_related("oficio").filter(pk=plano.termo_id).first()
        if termo is None:
            raise ImportacaoRecusada("O termo escolhido não existe mais.")
    equipe = {ps.pk: ps for ps in prestacao.servidores_prestacao.select_related("servidor")} if prestacao else {}
    _conferir_plano(plano, prestacao, equipe, termo=termo)
    pdf = _ler_arquivo(importacao)

    # (tipo, servidor) → itens, na ordem do processo.
    grupos: dict[tuple[str, int | None], list[ItemPlano]] = {}
    for item in plano.itens:
        if item.entra:
            grupos.setdefault((item.destino, item.servidor_prestacao_id if item.individual else None), []).append(item)

    # Só comprovantes (fotos avulsas): somam-se aos que o servidor já tem. O
    # processo inteiro traz todos, e aí substitui.
    acrescentar = so_comprovantes(plano)
    resultado = ResultadoImportacao()
    with transacao_de_arquivos():
        if acrescentar:
            # "Aplicar de novo" troca só o que esta mesma importação tinha gravado.
            _remover_da_importacao(importacao)
        criados: list[tuple[ItemPlano, Anexo]] = []
        for tipo in ORDEM_DOCUMENTOS_PRESTACAO:
            for (destino, ps_id), itens in grupos.items():
                if destino != tipo:
                    continue
                servidor_prestacao = equipe.get(ps_id) if ps_id else None
                if not (acrescentar and tipo == Anexo.TIPO_COMPROVANTE):
                    resultado.substituidos += remover_anexos_do_tipo(
                        prestacao, tipo=tipo, servidor_prestacao=servidor_prestacao,
                        todos_do_tipo=servidor_prestacao is None,
                    )
                for item in itens:
                    anexo = _criar_anexo(
                        prestacao, importacao, item, pdf, servidor_prestacao=servidor_prestacao, protocolo=plano.protocolo,
                    )
                    criados.append((item, anexo))

        compartilhado = any(anexo.servidor_prestacao_id is None for _, anexo in criados)
        if compartilhado:
            marcar_servidores_pendentes(prestacao)
        for ps_id in dict.fromkeys(anexo.servidor_prestacao_id for _, anexo in criados if anexo.servidor_prestacao_id):
            marcar_servidor_em_preenchimento(equipe[ps_id])

        oficio_anexo = next((anexo for _, anexo in criados if anexo.tipo == Anexo.TIPO_OFICIO_ASSINADO), None)
        if oficio_anexo is not None:
            resultado.avisos.extend(_carimbar(oficio_anexo, prestacao))

        if prestacao is not None and plano.protocolo_para_gravar:
            resultado.protocolo_gravado = _gravar_protocolo(prestacao.oficio, plano.protocolo_para_gravar)
            if resultado.protocolo_gravado:
                resultado.avisos.insert(0, f"Protocolo {resultado.protocolo_gravado} gravado no Ofício {prestacao.oficio.numero_formatado}.")

        if criados:
            resultado.avisos.extend(_avisos_de_convalidacao(prestacao))

        # O ofício assinado (sem o carimbo, que é da prestação), a justificativa, os termos e a OS.
        resultado.documentos, avisos_documentos = _anexar_documentos(plano, pdf, prestacao=prestacao, termo=termo)
        resultado.avisos.extend(avisos_documentos)
        if not criados and not resultado.documentos:
            raise ImportacaoRecusada(" ".join(avisos_documentos) or "Nenhum documento do processo pôde ser gravado.")

        resultado.resumo_documentos = resumo_dos_documentos(resultado.documentos)
        if criados:
            resultado.resumo = resumo_da_importacao(plano.protocolo, prestacao.oficio, criados)
        else:
            cabeca = f"Processo {format_protocolo(plano.protocolo) or plano.protocolo}" if plano.protocolo else "Arquivo"
            resultado.resumo = f"{cabeca} importado. {resultado.resumo_documentos}".strip()
            resultado.resumo_documentos = ""
        resultado.anexos = [
            {
                "id": anexo.pk,
                "ordem": item.ordem,
                "tipo": anexo.tipo,
                "nome": anexo.nome_original,
                "servidor": equipe[anexo.servidor_prestacao_id].servidor.nome if anexo.servidor_prestacao_id else "",
            }
            for item, anexo in criados
        ]

        importacao.plano = plano.para_json()
        importacao.prestacao = prestacao
        importacao.oficio = prestacao.oficio if prestacao is not None else (termo.oficio if termo is not None and termo.oficio_id else None)
        importacao.situacao = ImportacaoProcesso.SITUACAO_APLICADA
        importacao.aplicado_em = timezone.now()
        importacao.resultado = resultado.para_json()
        importacao.save(update_fields=["plano", "prestacao", "oficio", "situacao", "aplicado_em", "resultado"])
    return resultado
