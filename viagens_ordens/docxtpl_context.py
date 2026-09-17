"""Contexto docxtpl do modelo de Ordem de Serviço — porte fiel de
`ordens_servico/docxtpl_context.py` da origem.

O que mudou: `cadastros.Cidade` virou `cadastros.Municipio` e a configuração
não tem área. Os textos de cada tipo de necessidade são os mesmos, letra por
letra: entram no documento assinado.
"""

from __future__ import annotations

from datetime import date
from itertools import groupby
from typing import Any

from django.utils import timezone

from documentos.services.formatters import format_document_display
from viagens_cadastros.selectors import build_configuracao_context
from viagens_oficios.docxtpl_context import _assinatura_nome_cargo, _build_endereco, _build_sede

from .models import OrdemServico

_MESES = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def _fmt_extenso(d: date) -> str:
    return f"{d.day} de {_MESES[d.month]} de {d.year}"


def _periodo_extenso(inicio: date | None, fim: date | None) -> str:
    if not inicio:
        return ""
    if not fim or fim == inicio:
        return f"no dia {_fmt_extenso(inicio)}"
    if inicio.month == fim.month and inicio.year == fim.year:
        return f"nos dias {inicio.day} a {fim.day} de {_MESES[inicio.month]} de {inicio.year}"
    return f"nos dias {_fmt_extenso(inicio)} a {_fmt_extenso(fim)}"


def _destinos_display(ordem: OrdemServico) -> str:
    destinos = list(ordem.destinos.select_related("estado").order_by("nome"))
    if not destinos:
        return ""
    # O documento é para leitura e assinatura: o nome sai capitalizado, como o
    # resto do módulo faz com o nome do servidor e o motivo.
    nomes = [format_document_display(d.nome) or str(d.nome) for d in destinos]
    partes = [f"{nome}/{d.estado.sigla}" if d.estado_id else nome for d, nome in zip(destinos, nomes, strict=True)]
    if len(partes) == 1:
        return partes[0]
    if len(partes) == 2:
        return f"{partes[0]} e {partes[1]}"
    *primeiros, ultimo = partes
    return f"{', '.join(primeiros)} e {ultimo}"


_CARGO_STOPWORDS = {"de", "da", "do", "das", "dos", "e"}


def _is_acronym(word: str) -> bool:
    """ADM, DPC, PC... — palavra curta toda em maiúsculas ASCII.

    Preposições e conjunções (DE, DA, DO...) ficam de fora: os cargos vêm em
    caixa alta do banco e, sem isso, "AGENTE DE POLICIA" ganhava um "DE" maiúsculo.
    """
    clean = "".join(c for c in word if c.isalpha())
    if not clean or clean.lower() in _CARGO_STOPWORDS:
        return False
    return clean.isascii() and clean.isupper() and len(clean) <= 5


def _pluralize_pt(word: str) -> str:
    """Plural simples do primeiro substantivo (espera entrada em minúsculas)."""
    if not word:
        return word
    if word.endswith("ão"):
        return word[:-2] + "ões"
    last = word[-1]
    if last in "aeiouáéíóúàâêîôûãõ":
        return word + "s"
    if last == "l" and len(word) >= 2:
        prev = word[-2]
        return word[:-1] + ("is" if prev in "aeiouáéíóúàâêîôûãõ" else "eis")
    if last in ("r", "z", "n"):
        return word + "es"
    if last == "m":
        return word[:-1] + "ns"
    if last == "s":
        return word
    return word + "s"


def _cargo_display(nome: str, *, plural: bool) -> str:
    """'AGENTE DE POLICIA' -> 'agentes de policia' (plural) ou 'agente de policia'."""
    tokens = nome.split()
    result = []
    for i, tok in enumerate(tokens):
        if _is_acronym(tok):
            result.append(tok)
        elif i == 0 and plural:
            result.append(_pluralize_pt(tok.lower()))
        else:
            result.append(tok.lower())
    return " ".join(result)


def _equipe_deslocamento(ordem: OrdemServico) -> str:
    servidores = list(ordem.servidores.select_related("cargo").order_by("cargo__nome", "nome"))
    if not servidores:
        return "da equipe"

    _SEM_CARGO = "\xff"

    def cargo_key(s):
        return s.cargo.nome if s.cargo_id else _SEM_CARGO

    partes = []
    for cargo_nome, grupo in groupby(sorted(servidores, key=cargo_key), key=cargo_key):
        membros = list(grupo)
        nomes = [format_document_display(s.nome) or str(s.nome) for s in membros]
        n = len(nomes)
        lista = ", ".join(nomes[:-1]) + f" e {nomes[-1]}" if n > 1 else nomes[0]
        is_first = not partes
        if cargo_nome == _SEM_CARGO:
            partes.append(lista)
            continue
        if n == 1:
            # O primeiro grupo usa a contração "do"; os demais, "o".
            artigo = "do" if is_first else "o"
            partes.append(f"{artigo} {_cargo_display(cargo_nome, plural=False)} {nomes[0]}")
        else:
            artigo = "dos" if is_first else "os"
            partes.append(f"{artigo} {_cargo_display(cargo_nome, plural=True)} {lista}")

    if not partes:
        return "da equipe"
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + f" e {partes[-1]}"


def _nome_servidor(servidor) -> str:
    if not servidor:
        return ""
    return format_document_display(servidor.nome) or str(servidor.nome)


def _competencia(servidor, texto: str) -> str:
    nome = _nome_servidor(servidor)
    if not nome:
        return ""
    return f"{nome} - {texto}"


def _competencias_transporte(ordem: OrdemServico) -> list[str]:
    return [
        item
        for item in [
            _competencia(
                ordem.motorista_equipe,
                "conduzir o veículo oficial durante os deslocamentos de ida e retorno, zelando pela segurança da equipe e apoiando a movimentação necessária à execução da atividade",
            ),
            _competencia(
                ordem.tecnico_equipe,
                "prestar suporte técnico à operação dos equipamentos, acompanhando montagem, funcionamento, conferência e recolhimento dos materiais utilizados",
            ),
            _competencia(
                ordem.apoio_montagem,
                "auxiliar na carga, descarga, montagem, organização dos materiais e adequação do local para a realização da atividade",
            ),
            _competencia(
                ordem.apoio_escolta,
                "prestar apoio à escolta e à segurança do deslocamento, orientando acessos, estacionamento e movimentação do veículo e da equipe",
            ),
        ]
        if item
    ]


def _servidores_por_funcao(ordem: OrdemServico, funcao: str) -> list:
    funcoes = {str(k): v for k, v in (ordem.funcoes_servidores or {}).items()}
    servidor_ids = [int(sid) for sid, valor in funcoes.items() if valor == funcao and sid.isdigit()]
    if not servidor_ids:
        return []
    posicao = {sid: indice for indice, sid in enumerate(servidor_ids)}
    servidores = [s for s in ordem.servidores.all() if s.pk in posicao]
    return sorted(servidores, key=lambda s: posicao[s.pk])


def _lista_nomes(servidores) -> str:
    nomes = [n for n in (_nome_servidor(s) for s in servidores) if n]
    if len(nomes) <= 1:
        return nomes[0] if nomes else ""
    return ", ".join(nomes[:-1]) + f" e {nomes[-1]}"


def _competencia_grupo(servidores, texto: str) -> str:
    nomes = _lista_nomes(servidores)
    if not nomes:
        return ""
    separador = " – " if len(servidores) == 1 else ": "
    return f"{nomes}{separador}{texto}"


def _competencias_caminhao(ordem: OrdemServico) -> list[str]:
    destino = _destinos_display(ordem) or "município de destino"
    textos = [
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_CONDUCAO),
            "conduzir a Unidade Móvel (caminhão), realizando o deslocamento desde o local onde o veículo estiver estacionado até o município de destino e, ao término das atividades, o retorno ao local de guarda do veículo, computando-se todo o percurso. Caberá, ainda, prestar apoio às atividades de instalação, posicionamento, operação e desmontagem da estrutura da Unidade Móvel.",
        ),
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_TECNICO),
            "prestar apoio técnico na instalação, configuração, testes e operação dos equipamentos de informática, rede lógica, comunicação e demais sistemas utilizados durante os atendimentos. Deverá deslocar-se antecipadamente ao local do evento para verificar as condições de fornecimento de energia elétrica, conectividade de internet e infraestrutura necessária ao funcionamento da Unidade Móvel, considerando que, em razão da dinâmica da operação, não foi possível a realização de visita técnica prévia.",
        ),
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_APOIO),
            f"realizar a escolta e o apoio operacional da Unidade Móvel durante todo o deslocamento entre Curitiba e {destino}, bem como no retorno, computando-se todo o trajeto. Deverá auxiliar na montagem, organização, manutenção operacional e desmontagem dos equipamentos da Unidade Móvel.",
        ),
    ]
    return [texto for texto in textos if texto]


def _competencias_microonibus(ordem: OrdemServico) -> list[str]:
    textos = [
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_CONDUCAO),
            "conduzir o micro-ônibus oficial durante os deslocamentos de ida e retorno, zelando pela segurança da equipe e dos passageiros",
        ),
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_TECNICO),
            "prestar suporte técnico à operação dos equipamentos e acompanhar a organização dos materiais utilizados na atividade",
        ),
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_APOIO),
            "prestar apoio operacional à equipe, auxiliando na organização, montagem, escolta e movimentação necessárias à realização da atividade",
        ),
    ]
    return [texto for texto in textos if texto]


def _competencias_cerimonial(ordem: OrdemServico) -> list[str]:
    textos = [
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_COORDENACAO),
            "conduzir o veículo oficial durante o deslocamento de ida e retorno, bem como coordenar as atividades de Cerimonial, supervisionando os procedimentos protocolares, a recepção das autoridades, a composição do dispositivo de honra e a execução do roteiro oficial",
        ),
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_APOIO),
            "prestar apoio às atividades de Cerimonial, auxiliando na organização do ambiente, recepção das autoridades e execução dos procedimentos protocolares",
        ),
        _competencia_grupo(
            _servidores_por_funcao(ordem, OrdemServico.FUNCAO_PREPARACAO),
            "auxiliar na preparação da solenidade, conferência dos materiais, organização dos espaços e demais atividades necessárias à realização do evento",
        ),
    ]
    dinamicas = [texto for texto in textos if texto]
    if dinamicas:
        return dinamicas
    # Sem função na equipe, valem os papéis fixos das OS antigas.
    return [
        item
        for item in [
            _competencia(
                ordem.coordenador_cerimonial,
                "conduzir o veículo oficial durante o deslocamento de ida e retorno, bem como coordenar as atividades de Cerimonial, supervisionando os procedimentos protocolares, a recepção das autoridades, a composição do dispositivo de honra e a execução do roteiro oficial",
            ),
            _competencia(
                ordem.apoio_cerimonial,
                "prestar apoio às atividades de Cerimonial, auxiliando na organização do ambiente, recepção das autoridades e execução dos procedimentos protocolares",
            ),
            _competencia(
                ordem.apoio_preparacao,
                "auxiliar na preparação da solenidade, conferência dos materiais, organização dos espaços e demais atividades necessárias à realização do evento",
            ),
        ]
        if item
    ]


def _texto_modelo(ordem: OrdemServico, motivo: str) -> dict[str, object]:
    tipo = ordem.tipo_necessidade or OrdemServico.TIPO_PADRAO
    destino = _destinos_display(ordem) or "destino informado"
    motivo_doc = motivo or "atuação na atividade institucional designada"
    periodo = _periodo_extenso(ordem.data_evento_inicio, ordem.data_evento_fim)

    textos = {
        "referencia": "Diligências",
        "determinacao": (
            f"O deslocamento {_equipe_deslocamento(ordem)} para o município de {destino}, "
            f"{periodo}, para realizar {motivo_doc}."
        ),
        "justificativas": [],
        "competencias_equipe": [],
        "finalidade": "A presente Ordem de Serviço tem por finalidade garantir a execução da atividade designada, com observância às normas administrativas aplicáveis.",
    }

    if tipo == OrdemServico.TIPO_OPERACAO_RETORNO_POSTERIOR:
        textos.update({
            "referencia": "Deslocamento - Operação policial com um dia posterior",
            "determinacao": (
                f"O deslocamento {_equipe_deslocamento(ordem)} para o município de {destino}, "
                f"{periodo}, para atuação em operação policial relacionada a {motivo_doc}."
            ),
            "justificativas": [
                "A concessão de um dia posterior justifica-se pelo fato de que as atividades planejadas para a operação policial abrangem desde a produção de material jornalístico durante o briefing e o acompanhamento do cumprimento dos mandados judiciais, até a prestação de assessoria de imprensa pós-operação, incluindo a condução de entrevistas coletivas e o atendimento às demandas dos veículos de comunicação. Diante disso, evidencia-se a necessidade de permanência da equipe policial na referida localidade mesmo após a conclusão das diligências operacionais.",
            ],
            "finalidade": "A presente Ordem de Serviço tem por finalidade assegurar a cobertura jornalística, a assessoria de imprensa e o atendimento às demandas de comunicação vinculadas à operação policial.",
        })
    elif tipo == OrdemServico.TIPO_CAMINHAO:
        competencias_caminhao = _competencias_caminhao(ordem)
        if not competencias_caminhao:
            return textos
        textos.update({
            "referencia": "Deslocamento - Caminhão de apoio",
            "determinacao": (
                f"O deslocamento da equipe abaixo relacionada para o município de {destino}, "
                f"{periodo}, para apoio logístico com caminhão em {motivo_doc}, observadas as atribuições a seguir:"
            ),
            "competencias_equipe": competencias_caminhao,
            "justificativas": [
                "O deslocamento do caminhão com dois dias de antecedência faz-se necessário para viabilizar o traslado, descarga, montagem, conferência técnica e adequação dos materiais e equipamentos no local do evento.",
                "A permanência por dois dias posteriores ao evento justifica-se pela necessidade de desmontagem, conferência, acondicionamento, carregamento dos materiais e retorno do veículo com segurança, preservando os bens públicos utilizados.",
            ],
            "finalidade": "A presente Ordem de Serviço tem por finalidade garantir o planejamento, a execução e a desmobilização do apoio logístico prestado com caminhão.",
        })
    elif tipo == OrdemServico.TIPO_MICROONIBUS:
        competencias_microonibus = _competencias_microonibus(ordem) or _competencias_transporte(ordem)
        textos.update({
            "referencia": "Deslocamento - Micro-ônibus",
            "determinacao": (
                f"O deslocamento da equipe abaixo relacionada para o município de {destino}, "
                f"{periodo}, para apoio logístico com micro-ônibus em {motivo_doc}, observadas as atribuições a seguir:"
            ),
            "competencias_equipe": competencias_microonibus,
            "justificativas": [
                "O micro-ônibus será utilizado para transporte e apoio logístico da equipe, observando-se o cronograma da atividade, sem necessidade de deslocamento com dois dias de antecedência ou permanência por dois dias posteriores ao evento.",
            ],
            "finalidade": "A presente Ordem de Serviço tem por finalidade garantir o transporte, a organização e o apoio logístico necessários à realização da atividade.",
        })
    elif tipo == OrdemServico.TIPO_CERIMONIAL_ANTECIPADO:
        textos.update({
            "referencia": "Deslocamento - Equipe de Cerimonial",
            "determinacao": (
                f"O deslocamento da equipe abaixo relacionada para o município de {destino}, "
                f"{periodo}, para atuação na organização e realização de {motivo_doc}, observadas as atribuições a seguir:"
            ),
            "competencias_equipe": _competencias_cerimonial(ordem),
            "justificativas": [
                "O deslocamento da equipe com dois dias de antecedência faz-se necessário, sendo o primeiro destinado ao deslocamento até o município do evento e o segundo à organização dos trabalhos, em razão da inexistência de visita técnica prévia.",
                "A permanência da equipe permitirá verificar a estrutura do local, sistema de sonorização, disposição do palco, púlpito, bandeiras, autoridades e convidados, decoração, acessos e demais aspectos logísticos, possibilitando os ajustes necessários para assegurar a adequada realização da solenidade.",
            ],
            "finalidade": "A presente Ordem de Serviço tem por finalidade garantir o planejamento, a organização e a execução das atividades de Cerimonial, assegurando o cumprimento das normas de protocolo e a realização do evento institucional com eficiência e observância aos padrões da Polícia Civil do Paraná.",
        })

    return textos


def build_os_docxtpl_context(ordem: OrdemServico) -> dict[str, Any]:
    inst = build_configuracao_context()

    def _txt(v: object) -> str:
        return str(v or "").strip()

    sigla = _txt(inst.get("sigla_orgao"))
    unidade_campo = _txt(inst.get("unidade"))
    nome_orgao = _txt(inst.get("nome_orgao"))
    divisao = _txt(inst.get("divisao"))
    unidade = unidade_campo or nome_orgao or sigla

    nome_chefia, cargo_chefia = _assinatura_nome_cargo(inst, "ORDEM_SERVICO", fallback_geral=False)

    numero_str = f"{ordem.numero:03d}/{ordem.ano}" if ordem.numero and ordem.ano else str(ordem.pk or "—")

    motivo = format_document_display(_txt(ordem.motivo)) if _txt(ordem.motivo) else ""
    textos_modelo = _texto_modelo(ordem, motivo)

    return {
        "ordem_de_servico": numero_str,
        "unidade_abreviado": sigla or unidade,
        "nome_chefia": format_document_display(nome_chefia) if nome_chefia else "",
        "cargo_chefia": format_document_display(cargo_chefia) if cargo_chefia else "",
        "divisao_capitalize": format_document_display(divisao).title() if divisao else "",
        # Em caixa alta, direto do banco — sem `format_document_display`.
        "divisao": divisao,
        "unidade": unidade,
        "unidade_rodape": unidade,
        "destino": _destinos_display(ordem),
        "data_extenso": _periodo_extenso(ordem.data_evento_inicio, ordem.data_evento_fim),
        "motivo": motivo,
        "equipe_deslocamento": _equipe_deslocamento(ordem),
        "tipo_necessidade": ordem.tipo_necessidade or OrdemServico.TIPO_PADRAO,
        "tipo_necessidade_label": ordem.get_tipo_necessidade_display(),
        "referencia": textos_modelo["referencia"],
        "determinacao": textos_modelo["determinacao"],
        "justificativas": textos_modelo["justificativas"],
        "competencias_equipe": textos_modelo["competencias_equipe"],
        "finalidade": textos_modelo["finalidade"],
        "sede": _build_sede(inst),
        "data_atual_extenso": _fmt_extenso(timezone.localdate()),
        "endereco": _build_endereco(inst),
        "telefone": _txt(inst.get("telefone_formatado") or inst.get("telefone")),
        "email": (_txt(inst.get("email")) or "").lower(),
    }
