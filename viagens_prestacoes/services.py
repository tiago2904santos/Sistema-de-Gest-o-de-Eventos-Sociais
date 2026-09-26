from __future__ import annotations

from decimal import Decimal
from decimal import ROUND_HALF_UP
from io import BytesIO
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from viagens_cadastros.selectors import build_configuracao_context
from core.normalizers import normalize_spaces
from core.deletion import excluir_com_protecao
from core.errors import capture
from core.utils.dinheiro import ValorMonetarioInvalido
from core.utils.dinheiro import parse_valor_monetario
from documentos.services.facade import build_default_facade
from documentos.services.adapters.docxtpl_render import render_docx_bytes
from documentos.services.adapters.libreoffice_pdf import convert_docx_to_pdf_libreoffice
from documentos.services.adapters.word_pdf import convert_docx_to_pdf_word_com
from documentos.services.exceptions import DocumentValidationError
from documentos.services.formatters import format_city_uf
from documentos.services.formatters import format_currency_br
from documentos.services.formatters import format_document_display
from documentos.services.libreoffice_resolve import resolve_libreoffice_binary
from documentos.services.pdf_engine import build_pdf_unavailable_message
from documentos.services.pdf_engine import resolve_pdf_engine
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo
from documentos.services.timing import track_document_generation
from viagens_oficios.assunto_oficio import resolver_assunto_oficio
from viagens_oficios.documents import build_canonical_document_payload
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context

from .diario_services import alteracoes_datas_horarios_roteiro
from .diario_services import alteracoes_motorista_viatura_e_exigencia
from .diario_services import diferencas_entre_roteiros
from .diario_services import roteiro_efetivo
from .diario_services import sincronizar_trechos
from .forms import DEFAULT_CUSTEIO_VALUES
from .models import DiarioBordo
from .models import PrestacaoDocumentoAnexo
from .models import PrestacaoServidor
from .models import RelatorioTecnico


def excluir_modelo_texto(instance) -> None:
    excluir_com_protecao(instance)

_MESES = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _data_extenso(dt) -> str:
    return f"{dt.day} de {_MESES[dt.month]} de {dt.year}"


def _as_local_date(dt):
    if dt is None:
        return None
    if hasattr(dt, "date"):
        if timezone.is_aware(dt):
            return timezone.localtime(dt).date()
        return dt.date()
    return dt


def _data_retorno_oficio(oficio):
    # A prestação/relatório pode manter em memória uma instância de Ofício
    # anterior à edição do roteiro. Releia a relação para que o documento use
    # sempre a data efetivamente persistida, inclusive em workers assíncronos.
    persisted = None
    if getattr(oficio, "pk", None):
        persisted = (
            type(oficio).objects
            .select_related("roteiro")
            .filter(pk=oficio.pk)
            .first()
        )
    roteiro = getattr(persisted or oficio, "roteiro", None)
    if roteiro is None:
        return None

    dt = (
        getattr(roteiro, "retorno_chegada_dt", None)
        or getattr(roteiro, "chegada_dt", None)
        or getattr(roteiro, "retorno_saida_dt", None)
    )
    if dt:
        return _as_local_date(dt)

    trecho = roteiro.trechos.order_by("-chegada_dt", "-ordem", "-pk").first()
    if trecho and trecho.chegada_dt:
        return _as_local_date(trecho.chegada_dt)
    return None


def _add_dias_uteis(data, quantidade: int):
    """Dias úteis pulando fins de semana e feriados (m094: `core.feriados`)."""
    from core.feriados import somar_dias_uteis

    return somar_dias_uteis(data, quantidade)


def _data_relatorio_tecnico(oficio):
    hoje = timezone.localdate()
    retorno = _data_retorno_oficio(oficio)
    if retorno is None:
        return hoje
    limite = _add_dias_uteis(retorno, 3)
    if hoje < retorno:
        return retorno
    return min(hoje, limite)


def _sede() -> str:
    from viagens_cadastros.models import ConfiguracaoSistema
    return ConfiguracaoSistema.atual().cidade_endereco or ""


def _diaria_por_servidor(roteiro) -> Decimal | None:
    """A F2 persiste o total da equipe: o RT precisa do valor individual."""
    if roteiro and roteiro.valor_diarias:
        if not roteiro.quantidade_servidores:
            raise DocumentValidationError("Informe o efetivo do cálculo das diárias.")
        return Decimal(roteiro.valor_diarias) / roteiro.quantidade_servidores
    return None


def _diaria_por_servidor_legado(roteiro, total_servidores: int) -> Decimal | None:
    """O valor dividido que este módulo produzia antes da correção.

    Serve só para reconhecer um `RelatorioTecnico.diaria` preenchido
    automaticamente naquela época e substituí-lo — sem isso, o texto errado já
    gravado sobreviveria à correção, porque deixa de bater com o padrão atual.
    """
    valor = _diaria_por_servidor(roteiro)
    if valor is None:
        return None
    return valor / Decimal(total_servidores or 1)


def diaria_inicial_do_oficio(prestacao) -> str:
    """Diária por servidor conforme o roteiro original do ofício (sem ajustes)."""
    try:
        oficio = prestacao.oficio
        valor = _diaria_por_servidor(getattr(oficio, "roteiro", None))
        if valor is not None:
            return format_currency_br(valor)
    except Exception as exc:
        capture(exc, "prestacoes.diaria_prevista", oficio_id=oficio.pk)
    return ""


def diaria_inicial_da_prestacao(prestacao) -> str:
    """Diária por servidor calculada a partir do roteiro efetivo (ajustado, se houver)."""
    try:
        valor = _diaria_por_servidor(roteiro_efetivo(prestacao))
        if valor is not None:
            return format_currency_br(valor)
    except Exception as exc:
        capture(exc, "prestacoes.diaria_efetiva", prestacao_id=prestacao.pk)
    return ""


def _diarias_automaticas_legadas(prestacao) -> set[str]:
    """Textos que o preenchimento automático antigo poderia ter gravado."""
    try:
        total_servidores = prestacao.oficio.servidores.count() or 1
        if total_servidores == 1:
            return set()
        roteiros = (getattr(prestacao.oficio, "roteiro", None), roteiro_efetivo(prestacao))
        valores = set()
        for roteiro in roteiros:
            valor = _diaria_por_servidor_legado(roteiro, total_servidores)
            if valor is not None:
                valores.add(normalize_spaces(format_currency_br(valor)))
        return valores
    except Exception as exc:
        capture(exc, "prestacoes.diaria_legada", prestacao_id=prestacao.pk)
        return set()


def _ajustes_roteiro_itens(prestacao) -> list[str]:
    """Itens de alteração do roteiro (datas/horários + diária) desta prestação."""
    copia = prestacao.roteiro_ajustado
    original = getattr(prestacao.oficio, "roteiro", None)
    if copia is None or original is None or not diferencas_entre_roteiros(original, copia):
        return []

    itens = list(alteracoes_datas_horarios_roteiro(prestacao))

    diaria_oficio = diaria_inicial_do_oficio(prestacao)
    diaria_ajustada = diaria_inicial_da_prestacao(prestacao)
    if diaria_oficio and diaria_ajustada and diaria_oficio != diaria_ajustada:
        itens.append(f"a diária (por servidor) passou de {diaria_oficio} para {diaria_ajustada}")
    return itens


def descricao_ajustes_prestacao(prestacao) -> str:
    """Texto-prévia das alterações para ``Informações complementares`` do RT.

    Apenas motorista vindo de outro ofício abre o pedido de justificativa. As
    demais trocas e ajustes são registrados como informação objetiva.
    """
    itens, exige_justificativa = alteracoes_motorista_viatura_e_exigencia(prestacao)
    itens = list(itens)
    itens += _ajustes_roteiro_itens(prestacao)
    if not itens:
        return ""
    corpo = "; ".join(itens)
    corpo = corpo[:1].upper() + corpo[1:]
    sufixo = ". Justificativa: " if exige_justificativa else "."
    return f"{corpo}{sufixo}"


def valor_diaria_liberado(servidor_prestacao) -> Decimal | None:
    """Quanto foi liberado para este servidor, arredondado como no documento.

    É o teto do que ele pode ter recebido. Arredondado antes de comparar
    porque o valor do roteiro pode ter mais casas do que o documento mostra —
    sem isso, digitar exatamente o valor impresso seria recusado.
    """
    prestacao = servidor_prestacao.prestacao
    valor = _diaria_por_servidor(roteiro_efetivo(prestacao))
    if valor is None:
        return None
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def diaria_recebida_display(servidor_prestacao) -> str:
    """Número e anotação remontados, como o operador digitou e o documento imprime."""
    valor = servidor_prestacao.diaria_valor_override
    if valor is None:
        return normalize_spaces(servidor_prestacao.diaria_valor_override_observacao or "")
    partes = [
        format_currency_br(valor),
        normalize_spaces(servidor_prestacao.diaria_valor_override_observacao or ""),
    ]
    return " ".join(parte for parte in partes if parte)


def aplicar_diaria_recebida(servidor_prestacao, texto) -> list[str]:
    """Interpreta o texto digitado e grava valor + observação. Devolve os erros.

    Um único campo na tela, duas colunas no banco: o operador continua
    escrevendo "R$ 87,00 (saque)" e o servidor é quem separa. Devolver a lista
    de erros em vez de levantar exceção é o que permite ao autosave responder
    campo a campo sem derrubar o resto do formulário.
    """
    try:
        valor, observacao = parse_valor_monetario(texto)
    except ValorMonetarioInvalido:
        return [
            "Informe um valor em reais, como \u201cR$ 87,00\u201d. "
            "Se precisar explicar a diferença, escreva depois do valor: "
            "\u201cR$ 87,00 (saque)\u201d."
        ]

    if valor is not None and valor <= 0:
        return ["O valor recebido precisa ser maior que zero."]

    if valor is not None:
        liberado = valor_diaria_liberado(servidor_prestacao)
        if liberado is not None and valor > liberado:
            return [
                f"O valor recebido não pode passar do liberado "
                f"({format_currency_br(liberado)}). O servidor pode receber "
                "menos — no saque o caixa não entrega centavos —, nunca mais."
            ]

    servidor_prestacao.diaria_valor_override = valor
    servidor_prestacao.diaria_valor_override_observacao = observacao
    return []


def marcar_servidor_em_preenchimento(servidor_prestacao) -> None:
    """Sai de "pendente" quando o operador digita a primeira coisa do servidor."""
    if servidor_prestacao is not None:
        servidor_prestacao.marcar_em_preenchimento()


@transaction.atomic
def marcar_servidores_pendentes(prestacao) -> None:
    """O mesmo, para toda a equipe ainda pendente do ofício.

    `BE-14`: grava **em laço**, um `UPDATE` por servidor. Sem a transação, uma falha no
    quinto deixa os quatro primeiros com o status trocado e o resto não — e essa metade
    não se conserta sozinha na gravação seguinte, porque quem já saiu de "pendente" deixa
    de entrar no filtro.

    Este par morava em `view_common.py`, onde nenhuma varredura de `*views*.py` o
    encontrava: o arquivo não tem "views" no nome (`NOVO-101`).
    """
    if prestacao is None:
        return
    for servidor_prestacao in prestacao.servidores_prestacao.filter(
        status=PrestacaoServidor.STATUS_PENDENTE
    ):
        servidor_prestacao.marcar_em_preenchimento()


def relatorio_tecnico_default_values(prestacao) -> dict:
    values = dict(DEFAULT_CUSTEIO_VALUES)
    diaria = diaria_inicial_da_prestacao(prestacao)
    if diaria:
        values["diaria"] = diaria
    info = descricao_ajustes_prestacao(prestacao)
    if info:
        values["info_complementares"] = info
    return values


def garantir_campos_padrao_relatorio_tecnico(relatorio: RelatorioTecnico) -> list[str]:
    prestacao = relatorio.prestacao
    defaults = relatorio_tecnico_default_values(prestacao)
    valor_default_oficio = normalize_spaces(diaria_inicial_do_oficio(prestacao))
    valores_automaticos_legados = _diarias_automaticas_legadas(prestacao)

    update_fields = []
    for campo in ("diaria", "translado", "combustivel", "passagem", "info_complementares"):
        valor_padrao = (defaults.get(campo) or "").strip()
        if not valor_padrao:
            continue
        valor_atual = normalize_spaces(getattr(relatorio, campo, "") or "")

        deve_atualizar = not valor_atual
        if campo == "diaria" and valor_atual and (
            valor_atual == valor_default_oficio
            or valor_atual in valores_automaticos_legados
        ):
            # Ainda é o valor automático anterior (não editado manualmente):
            # sincroniza com o novo valor ajustado do roteiro. `legados` cobre o
            # texto dividido pela equipe que a versão anterior gravava sozinha.
            deve_atualizar = valor_atual != normalize_spaces(valor_padrao)

        if campo == "info_complementares" and valor_atual and not valor_padrao.endswith("Justificativa:"):
            # Corrige somente a prévia automática antiga, que terminava no
            # marcador vazio. Qualquer justificativa realmente digitada pelo
            # usuário continua intocada.
            valor_automatico_legado = normalize_spaces(f"{valor_padrao} Justificativa:")
            deve_atualizar = valor_atual == valor_automatico_legado

        if deve_atualizar:
            setattr(relatorio, campo, valor_padrao)
            update_fields.append(campo)

    if update_fields:
        relatorio.save(update_fields=[*update_fields, "atualizado_em"])
    return update_fields


def _endereco_institucional(inst: dict) -> str:
    logradouro = format_document_display(inst.get("logradouro"))
    numero = str(inst.get("numero") or "").strip()
    bairro = format_document_display(inst.get("bairro"))
    cidade = str(inst.get("cidade_endereco") or "").strip()
    uf = str(inst.get("uf") or "").strip().upper()
    cidade_uf = format_city_uf(f"{cidade}/{uf}") if cidade and uf else format_document_display(cidade) or uf
    cep = str(inst.get("cep_formatado") or inst.get("cep") or "").strip()
    cep_label = f"CEP {cep}" if cep else ""
    return ", ".join(part for part in (logradouro, numero, bairro, cidade_uf, cep_label) if part)


def _upper_header_value(value: object) -> str:
    return str(value or "").strip().upper()


def _assunto_relatorio_tecnico(oficio) -> str:
    try:
        termo = resolver_assunto_oficio(oficio).get("assunto_termo") or ""
    except Exception as exc:
        capture(exc, "prestacoes.assunto_relatorio_tecnico", oficio_id=oficio.pk)
        termo = ""
    if termo:
        return termo[:1].upper() + termo[1:]

    assunto = str(oficio.assunto or "").strip()
    assunto_upper = assunto.upper()
    if assunto_upper == "AUTORIZACAO":
        return "Autorização"
    if assunto_upper == "CONVALIDACAO":
        return "Convalidação"
    return format_document_display(assunto)


def build_relatorio_tecnico_context(relatorio: RelatorioTecnico, servidor_prestacao) -> dict:
    pc = relatorio.prestacao
    oficio = pc.oficio
    servidor = servidor_prestacao.servidor
    # Número e observação voltam a ser uma string só na hora de imprimir:
    # o documento continua saindo "R$80,00 (saque)", como sempre saiu.
    diaria_override = diaria_recebida_display(servidor_prestacao)
    data_rt = _data_relatorio_tecnico(oficio)
    inst = build_configuracao_context()
    defaults = relatorio_tecnico_default_values(pc)

    divisao_cabecalho = _upper_header_value(inst.get("divisao"))
    unidade_cabecalho = _upper_header_value(inst.get("unidade"))
    unidade_rodape = (
        format_document_display(inst.get("divisao"))
        or format_document_display(inst.get("unidade"))
        or format_document_display(inst.get("nome_orgao"))
    )

    return {
        "oficio": oficio.numero_formatado,
        "assunto_oficio": _assunto_relatorio_tecnico(oficio),
        "sede": format_document_display(inst.get("cidade_endereco") or _sede()),
        "data_atual_extenso": _data_extenso(data_rt),
        "divisao": divisao_cabecalho,
        "unidade_cabecalho": unidade_cabecalho,
        "unidade_rodape": unidade_rodape,
        "endereco": _endereco_institucional(inst),
        "telefone": inst.get("telefone_formatado") or inst.get("telefone") or "",
        "email": str(inst.get("email") or "").strip().lower(),
        "nome_servidor": servidor.nome,
        "cpf_servidor": servidor.cpf_formatado,
        "diaria": diaria_override or normalize_spaces(relatorio.diaria or "") or defaults.get("diaria", ""),
        "translado": normalize_spaces(relatorio.translado or "") or defaults.get("translado", ""),
        "combustivel": normalize_spaces(relatorio.combustivel or "") or defaults.get("combustivel", ""),
        "passagem": normalize_spaces(relatorio.passagem or "") or defaults.get("passagem", ""),
        "motivo": relatorio.motivo or oficio.motivo or "",
        "atividade": relatorio.atividade,
        "conclusao": relatorio.conclusao,
        "medidas": relatorio.medidas,
        "info_complementares": relatorio.info_complementares,
    }


def gerar_relatorio_tecnico_documento(relatorio, servidor_prestacao, formato):
    garantir_campos_padrao_relatorio_tecnico(relatorio)
    from documentos.services.document_blocks import conteudo_documental

    context = build_relatorio_tecnico_context(relatorio, servidor_prestacao)
    # Os textos do modelo reescritos no editor entram no PDF e na chave do cache.
    payload = dict(context, documento=conteudo_documental(DocumentoTipo.RELATORIO_TECNICO, relatorio.prestacao))
    return build_default_facade().gerar(
        tipo=DocumentoTipo.RELATORIO_TECNICO, formato=formato, payload=payload,
        docxtpl_context=context, docx_template_path="relatorio-tecnico.docx",
        reference=f"{relatorio.prestacao.oficio.numero_formatado.replace('/', '-')}_{servidor_prestacao.servidor_id}",
        prestacao_id=relatorio.prestacao_id, oficio_id=relatorio.prestacao.oficio_id,
        servidor_id=servidor_prestacao.servidor_id,
    )


def gerar_relatorio_tecnico_docx(relatorio: RelatorioTecnico, servidor_prestacao) -> bytes:
    return gerar_relatorio_tecnico_documento(relatorio, servidor_prestacao, DocumentoFormato.DOCX).conteudo


def gerar_relatorio_tecnico_pdf(relatorio: RelatorioTecnico, servidor_prestacao) -> bytes:
    return gerar_relatorio_tecnico_documento(relatorio, servidor_prestacao, DocumentoFormato.PDF).conteudo


def nome_arquivo_rt(relatorio: RelatorioTecnico, servidor, formato: str = "docx") -> str:
    from . import filenames as naming

    nome = servidor.nome.replace(" ", "_").upper()
    oficio = relatorio.prestacao.oficio.numero_formatado.replace("/", "-")
    ext = "pdf" if formato == "pdf" else "docx"
    # Nome baixado pelo usuário p/ anexar em outros sistemas: sem acentos.
    return f"{naming.nome_arquivo_ascii(f'RT_{nome}_OFICIO_{oficio}')}.{ext}"


def _pdf_bytes_from_file_field(field, label: str) -> bytes:
    if not field:
        raise DocumentValidationError(f"Anexe o arquivo: {label}.")
    name = str(getattr(field, "name", "") or "")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        with field.open("rb") as arquivo:
            return arquivo.read()
    if suffix in {".png", ".jpg", ".jpeg"}:
        with field.open("rb") as arquivo:
            return _image_bytes_to_pdf(arquivo.read())
    raise DocumentValidationError(f"Formato inválido em {label}. Use PDF, PNG, JPG ou JPEG.")


def pdf_do_anexo(anexo, label: str) -> bytes:
    """O anexo como entra num pacote (pacote final, "Baixar documentos"): em PDF.

    O diário de bordo sai sempre em pé — em paisagem quando o conteúdo é paisagem,
    nunca de cabeça para baixo. O que passou pelo importador ou pelo anexo manual já
    foi gravado girado (com o cru em `arquivo_original`); o anexo antigo, sem o cru,
    é endireitado aqui, na saída, sem mexer no arquivo guardado.
    """
    conteudo = _pdf_bytes_from_file_field(anexo.arquivo, label)
    if anexo.tipo == PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO and not anexo.arquivo_original:
        from .importacao.montagem import diario_em_pe

        conteudo, _ = diario_em_pe(conteudo, ocr=False)
    return conteudo


def anexos_ordenados(anexos_qs, tipo):
    """Os anexos do `tipo` na ordem do pacote (ver `models.ordenacao_dos_anexos`)."""
    from .models import ordenacao_dos_anexos

    return anexos_qs.filter(tipo=tipo).order_by(*ordenacao_dos_anexos(tipo))


def _pdf_parts_from_anexos(anexos_qs, label: str, legacy_field=None) -> list[tuple[str, bytes]]:
    """Todos os anexos do queryset, na ordem em que ele vem (ver `anexos_ordenados`)."""
    parts = []
    seen = set()
    for index, anexo in enumerate(anexos_qs, start=1):
        name = str(getattr(anexo.arquivo, "name", "") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append((f"{label} {index}", pdf_do_anexo(anexo, label)))

    legacy_name = str(getattr(legacy_field, "name", "") or "") if legacy_field is not None else ""
    if legacy_name and legacy_name not in seen:
        parts.append((label, _pdf_bytes_from_file_field(legacy_field, label)))

    if not parts:
        raise DocumentValidationError(f"Anexe o arquivo: {label}.")
    return parts


def _pdf_parts_from_anexos_opcional(anexos_qs, label: str) -> list[tuple[str, bytes]]:
    """Como ``_pdf_parts_from_anexos``, mas retorna ``[]`` quando não há anexos."""
    parts = []
    seen = set()
    for index, anexo in enumerate(anexos_qs, start=1):
        name = str(getattr(anexo.arquivo, "name", "") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append((f"{label} {index}", pdf_do_anexo(anexo, label)))
    return parts


def _image_bytes_to_pdf(content: bytes) -> bytes:
    """A imagem anexada como PDF (a conversão mora em `core.leitura.pdf.imagem_para_pdf`).

    Numa folha A4 e em pé: a foto do celular é desvirada pela etiqueta EXIF, como o
    importador já faz (`como_pdf`). Sem isso, o comprovante fotografado em pé entrava
    deitado no pacote.
    """
    from core.leitura.pdf import ImagemInvalida
    from core.leitura.pdf import imagem_para_pdf

    try:
        return imagem_para_pdf(content, corrigir_exif=True)
    except ImagemInvalida as exc:
        raise DocumentValidationError(str(exc)) from exc


def _append_pdf(writer, pdf_bytes: bytes, label: str) -> None:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if getattr(reader, "is_encrypted", False):
            reader.decrypt("")
        if not reader.pages:
            raise DocumentValidationError(f"O PDF de {label} não possui páginas.")
        for page in reader.pages:
            writer.add_page(page)
    except DocumentValidationError:
        raise
    except Exception as exc:
        raise DocumentValidationError(f"Não foi possível ler o PDF de {label}.") from exc


def _merge_pdf_parts(parts: list[tuple[str, bytes]]) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for label, content in parts:
        _append_pdf(writer, content, label)
    output = BytesIO()
    writer.write(output)
    writer.close()
    return output.getvalue()


def _solicitacoes_do_oficio(prestacao) -> dict[int, str]:
    solicitacoes = {}
    try:
        for ps in prestacao.servidores_prestacao.all():
            numero = str(ps.numero_solicitacao or "").strip()
            if numero:
                solicitacoes[ps.servidor_id] = numero
    except Exception as exc:
        capture(exc, "prestacoes.solicitacoes_por_servidor", prestacao_id=prestacao.pk)
    return solicitacoes


def gerar_oficio_prestacao_documento(prestacao, formato: DocumentoFormato) -> bytes:
    oficio = prestacao.oficio
    payload = build_canonical_document_payload(oficio, DocumentoTipo.OFICIO)
    docxtpl = build_oficio_docxtpl_context(
        oficio,
        solicitacoes_por_servidor=_solicitacoes_do_oficio(prestacao),
    )
    reference = oficio.numero_formatado.replace("/", "-")
    doc = build_default_facade().gerar(
        tipo=DocumentoTipo.OFICIO,
        formato=formato,
        payload=payload,
        reference=reference,
        docxtpl_context=docxtpl,
        oficio_id=oficio.pk, prestacao_id=prestacao.pk,
    )
    return doc.conteudo


def gerar_oficio_prestacao_pdf(prestacao) -> bytes:
    return gerar_oficio_prestacao_documento(prestacao, DocumentoFormato.PDF)


def pendencias_consolidado(servidor_prestacao) -> list[str]:
    """O que ainda falta, na Etapa 3, para o PDF final deste servidor fechar.

    São as três condições que `gerar_prestacao_consolidado_pdf` cobra e que não
    têm substituto gerado pelo sistema: o número da solicitação, o despacho
    assinado (do ofício, compartilhado) e o comprovante de saque deste servidor.
    Ofício, RT e diário não entram porque, sem o assinado, o pacote usa a versão
    que o próprio sistema gera.

    Existe para o fechamento poder DIZER o que falta antes de o operador clicar
    (`NOVO-20260824-133423-10943c04a7c5`): a tela calculava `numero_ok`, não
    usava em lugar nenhum, e o clique no download caía numa página de espera que
    prometia um arquivo que nunca vinha.
    """
    prestacao = servidor_prestacao.prestacao
    pendencias = []

    if not str(servidor_prestacao.numero_solicitacao or "").strip():
        pendencias.append(
            "Informe o número da solicitação deste servidor, acima.",
        )

    tem_despacho = prestacao.documentos_anexos.filter(
        tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO,
    ).exists() or bool(getattr(prestacao.despacho_assinado, "name", ""))
    if not tem_despacho:
        pendencias.append("Anexe o despacho assinado do ofício, acima.")

    tem_comprovante = servidor_prestacao.documentos_anexos.filter(
        tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
    ).exists()
    if not tem_comprovante:
        pendencias.append(
            "Anexe o comprovante de saque/transferência deste servidor, acima.",
        )

    return pendencias


def pendencias_para_finalizar(servidor_prestacao) -> list[str]:
    """O que falta para dar a prestação deste servidor por concluída (m092).

    Mais do que o pacote final cobra (`pendencias_consolidado`): diário e RT
    preenchidos (ou assinados), o número carimbado no ofício assinado e a soma dos
    comprovantes igual à diária. Não bloqueia: a tela pede "Finalizar mesmo assim"
    com uma justificativa.
    """
    from .completude import diario_completo, rt_completo

    prestacao = servidor_prestacao.prestacao
    pendencias = list(pendencias_consolidado(servidor_prestacao))
    if not diario_completo(prestacao):
        pendencias.append("Preencha o km de todos os trechos do diário de bordo, ou anexe o diário assinado.")
    if not rt_completo(servidor_prestacao):
        pendencias.append("Escreva a descrição, o objetivo e a conclusão do relatório técnico, ou anexe o RT assinado.")

    from .carimbo_services import anexo_do_oficio_assinado

    oficio = anexo_do_oficio_assinado(prestacao)
    if oficio is not None and str(servidor_prestacao.numero_solicitacao or "").strip():
        if not oficio.carimbos.filter(servidor_prestacao=servidor_prestacao).exists():
            pendencias.append("O número de solicitação não está carimbado no ofício assinado: use “Ajustar posição do número”.")

    comprovantes = list(servidor_prestacao.documentos_anexos.filter(tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE))
    esperado = servidor_prestacao.diaria_valor_override
    if esperado is None:
        esperado = valor_diaria_liberado(servidor_prestacao)
    if comprovantes and esperado is not None and all(a.valor is not None for a in comprovantes):
        soma = sum((a.valor for a in comprovantes), Decimal("0"))
        if soma != esperado:
            pendencias.append(
                f"Os comprovantes somam {format_currency_br(soma)}, e a diária deste servidor é {format_currency_br(esperado)}."
            )
    return pendencias


@track_document_generation("prestacao_gerar_consolidado_pdf")
def gerar_prestacao_consolidado_pdf(servidor_prestacao) -> bytes:
    """Pacote final de um servidor: ofício + despacho (compartilhados) + RT do
    servidor + diário (compartilhado) + comprovante do servidor.

    Quando os documentos assinados foram anexados na Etapa 3 (RT assinado do
    servidor e diário de bordo assinado do motorista), eles têm prioridade sobre
    a versão gerada/assinada eletronicamente pelo sistema."""
    prestacao = servidor_prestacao.prestacao

    # Uma lista só para as duas pontas: o que o fechamento mostra é exatamente o que
    # a geração cobra. Antes o número era conferido aqui e os anexos só estouravam
    # lá dentro, com o texto de máquina do montador ("Anexe o arquivo: despacho
    # assinado do ofício."), a três chamadas de distância.
    pendencias = pendencias_consolidado(servidor_prestacao)
    if pendencias:
        raise DocumentValidationError(" ".join(pendencias))

    diario, _ = DiarioBordo.objects.get_or_create(prestacao=prestacao)
    sincronizar_trechos(diario)

    from .documentos_oficiais import pdf_db_gerado
    from .documentos_oficiais import pdf_rt_gerado
    from .models import ORDEM_DOCUMENTOS_PRESTACAO

    compartilhados = prestacao.documentos_anexos.all()
    individuais = servidor_prestacao.documentos_anexos.all()

    def oficio_parts():
        enviados = _pdf_parts_from_anexos_opcional(
            anexos_ordenados(compartilhados, PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO),
            "ofício assinado",
        )
        return enviados or [("ofício", gerar_oficio_prestacao_pdf(prestacao))]

    def despacho_parts():
        # Todos os despachos, cada um com a sua folha de assinatura, na ordem do processo.
        return _pdf_parts_from_anexos(
            anexos_ordenados(compartilhados, PrestacaoDocumentoAnexo.TIPO_DESPACHO),
            "despacho assinado do ofício",
            legacy_field=prestacao.despacho_assinado,
        )

    def rt_parts():
        # RT assinado anexado pelo servidor tem prioridade sobre a versão gerada.
        enviados = _pdf_parts_from_anexos_opcional(
            anexos_ordenados(individuais, PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO),
            "relatório técnico assinado",
        )
        return enviados or [("relatório técnico", pdf_rt_gerado(servidor_prestacao))]

    def db_parts():
        # Diário de bordo assinado é anexado no card do motorista (nível ofício).
        enviados = _pdf_parts_from_anexos_opcional(
            anexos_ordenados(compartilhados, PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO),
            "diário de bordo assinado",
        )
        return enviados or [("diário de bordo", pdf_db_gerado(prestacao))]

    def comprovante_parts():
        # Todos os comprovantes do servidor, pela data da operação.
        return _pdf_parts_from_anexos(
            anexos_ordenados(individuais, PrestacaoDocumentoAnexo.TIPO_COMPROVANTE),
            "comprovante de saque/transferência",
        )

    montadores = {
        PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO: oficio_parts,
        PrestacaoDocumentoAnexo.TIPO_DESPACHO: despacho_parts,
        PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO: rt_parts,
        PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO: db_parts,
        PrestacaoDocumentoAnexo.TIPO_COMPROVANTE: comprovante_parts,
    }
    return _merge_pdf_parts([parte for tipo in ORDEM_DOCUMENTOS_PRESTACAO for parte in montadores[tipo]()])


def nome_arquivo_prestacao_consolidado(servidor_prestacao) -> str:
    """Nome do PDF consolidado da prestação, no formato acordado com o usuário:

    ``Prestação solicitação {nº solicitação} Ofício {nº-ano} {primeiro nome}
    {destino} {data do evento}.pdf``.

    Destino e data do evento vêm dos mesmos helpers de exibição do ofício
    (derivados do roteiro), garantindo consistência com o que aparece na tela.
    Partes vazias (ex.: sem roteiro) são omitidas. Diferente da nomeação usada
    no Drive, este nome é o do arquivo baixado pelo usuário (para anexar em
    outros sistemas) — por isso vai sem acentos nem caracteres especiais,
    já que alguns desses sistemas externos rejeitam nomes acentuados.
    """
    from . import filenames as naming
    from .presenters import _data_evento_display_oficio
    from .presenters import _destino_display_oficio

    oficio = servidor_prestacao.prestacao.oficio
    numero_solicitacao = str(servidor_prestacao.numero_solicitacao or "").strip()
    oficio_num = oficio.numero_formatado.replace("/", "-")
    nome = naming.primeiro_nome(servidor_prestacao.servidor)
    destino = _destino_display_oficio(oficio)
    data_evento = _data_evento_display_oficio(oficio)

    partes = ["Prestação"]
    if numero_solicitacao:
        partes.append(f"solicitação {numero_solicitacao}")
    partes.append(f"Ofício {oficio_num}")
    if nome:
        partes.append(nome)
    if destino:
        partes.append(destino)
    if data_evento:
        partes.append(data_evento)
    ext = "pdf"
    return f"{naming.nome_arquivo_ascii(' '.join(partes))}.{ext}"


def dados_eprotocolo_prestacao(servidor_prestacao) -> dict:
    """Os dados para protocolar a prestação de contas no eProtocolo, prontos para colar (m052).

    No molde do painel do ofício (`viagens_oficios.services.dados_eprotocolo`) e do
    Coffee Break: campos curtos com Copiar e o detalhamento numa caixa. Valores e
    prazos são os mesmos que a Etapa 3 usa (diária liberada, soma dos comprovantes,
    prazo com feriados de `prazos.prazo_para_prestar`).
    """
    from core.utils.masks import format_protocolo
    from viagens_oficios.campos_modelo import valores_do_oficio

    from .prazos import prazo_para_prestar

    ps = servidor_prestacao
    oficio = ps.prestacao.oficio
    valores = valores_do_oficio(oficio)
    servidor = ps.servidor
    nome = servidor.nome
    cpf = getattr(servidor, "cpf_formatado", "") or ""
    numero = oficio.numero_formatado if oficio.numero else ""
    protocolo = format_protocolo(oficio.protocolo) or ""
    solicitacao = str(ps.numero_solicitacao or "").strip()

    liberado = valor_diaria_liberado(ps)
    comprovantes = [
        a.valor
        for a in ps.documentos_anexos.filter(tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE)
        if a.valor is not None
    ]
    recebido = ps.diaria_valor_override
    if recebido is None and comprovantes:
        recebido = sum(comprovantes, Decimal("0"))
    liberado_txt = format_currency_br(liberado) if liberado is not None else ""
    recebido_txt = format_currency_br(recebido) if recebido is not None else ""

    def data(valor):
        return f"{valor:%d/%m/%Y}" if valor else ""

    partes = [f"PRESTAÇÃO DE CONTAS DE DIÁRIAS - OFÍCIO Nº {numero}" if numero else "PRESTAÇÃO DE CONTAS DE DIÁRIAS"]
    if solicitacao:
        partes.append(f"SOLICITAÇÃO Nº {solicitacao}")
    partes.append(f"SERVIDOR: {nome.upper()}")
    if valores["destino"]:
        partes.append(f"DESTINO: {valores['destino']}")
    if valores["periodo"]:
        partes.append(f"PERÍODO: {valores['periodo']}")
    if recebido_txt or liberado_txt:
        partes.append(f"VALOR: {recebido_txt or liberado_txt}")

    def campo(rotulo, valor):
        return {"rotulo": rotulo, "valor": valor, "copiar": valor}

    return {
        "campos": [
            campo("Interessado", nome),
            campo("CPF", cpf),
            campo("Assunto", "Prestação de contas de diárias"),
            campo("Protocolo do ofício", protocolo),
            campo("Nº/Ano do ofício", numero),
            campo("Nº da solicitação", solicitacao),
            campo("Destino", valores["destino"]),
            campo("Período da viagem", valores["periodo"]),
            campo("Diária liberada", liberado_txt),
            campo("Valor recebido", recebido_txt),
            campo("Liberação das diárias", data(ps.data_liberacao_diarias)),
            campo("Prazo limite de saque", data(ps.prazo_limite_saque)),
            campo("Prestar contas até", data(prazo_para_prestar(ps.prazo_limite_saque))),
        ],
        "textos": [
            {"id": "eprotocolo-prestacao-detalhamento", "rotulo": "Detalhamento", "texto": " - ".join(partes), "linhas": 3},
        ],
    }
