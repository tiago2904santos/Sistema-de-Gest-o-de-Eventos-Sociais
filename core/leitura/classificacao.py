"""Que documento é este: classificação pelo texto da primeira página.

As regras saíram dos modelos que o próprio sistema imprime
(`templates/documentos/pdf/*.html`, `documentos/resources/*`,
`documentos/editor/blocos.py`, `coffee_break/editor.py`), dos dois
processos reais de pagamento do Coffee Break e dos comprovantes dos bancos
mais comuns. Cada tipo tem sinais com peso; os pesos de um tipo se somam
como probabilidades independentes (1 − Π(1 − p)), o tipo de maior soma
vence e a confiança cai quando outro tipo também pontuou alto.

O texto extraído de PDF vem fora de ordem (no despacho do eProtocolo a
palavra "DESPACHO" sai no fim; na capa, o valor antes do rótulo), então as
regras procuram "contém", e só algumas olham o topo. Tudo roda sobre o
texto normalizado (maiúsculas, sem acento), linha a linha preservada.

O nome do arquivo (marcador do eProtocolo, "Documento: X.pdf" da folha de
assinatura, nome do upload) é pista fraca: desempata e salva página sem
texto, mas não vence o texto.
"""

from __future__ import annotations

import re
import unicodedata

from .texto import normalizar

__all__ = [
    "CAPA", "OFICIO", "DESPACHO", "JUSTIFICATIVA", "TERMO_AUTORIZACAO", "RT", "DIARIO_BORDO",
    "COMPROVANTE", "ORDEM_SERVICO", "PLANO_TRABALHO", "NOTA_FISCAL", "CERTIFICO", "CERTIDAO",
    "CONTRATO", "ADITIVO", "NOTA_EMPENHO", "NOTA_LIQUIDACAO", "EMAIL", "DESCONHECIDO",
    "TIPOS", "ROTULOS", "TIPOS_CONTINUOS", "classificar", "texto_para_regras",
]

CAPA = "capa"
OFICIO = "oficio"
DESPACHO = "despacho"
JUSTIFICATIVA = "justificativa"
TERMO_AUTORIZACAO = "termo_autorizacao"
RT = "rt"
DIARIO_BORDO = "diario_bordo"
COMPROVANTE = "comprovante"
ORDEM_SERVICO = "ordem_servico"
PLANO_TRABALHO = "plano_trabalho"
NOTA_FISCAL = "nota_fiscal"
CERTIFICO = "certifico"
CERTIDAO = "certidao"
CONTRATO = "contrato"
ADITIVO = "aditivo"
NOTA_EMPENHO = "nota_empenho"
NOTA_LIQUIDACAO = "nota_liquidacao"
EMAIL = "email"
DESCONHECIDO = "desconhecido"

#: Nome para a tela, na ordem de desempate (o primeiro vence o empate).
ROTULOS = {
    CAPA: "Capa do processo",
    DESPACHO: "Despacho",
    NOTA_LIQUIDACAO: "Nota de liquidação",
    NOTA_EMPENHO: "Nota de empenho",
    NOTA_FISCAL: "Nota fiscal",
    CERTIFICO: "Certifico digital",
    RT: "Relatório técnico",
    DIARIO_BORDO: "Diário de bordo",
    TERMO_AUTORIZACAO: "Termo de autorização",
    OFICIO: "Ofício",
    JUSTIFICATIVA: "Justificativa",
    ORDEM_SERVICO: "Ordem de serviço",
    PLANO_TRABALHO: "Plano de trabalho",
    COMPROVANTE: "Comprovante bancário",
    CERTIDAO: "Certidão",
    ADITIVO: "Termo aditivo",
    CONTRATO: "Contrato",
    EMAIL: "E-mail",
    DESCONHECIDO: "Não identificado",
}
TIPOS = tuple(ROTULOS)

#: Tipos em que toda página repete o cabeçalho (e por isso casa com as
#: regras): páginas seguidas do mesmo tipo são o mesmo documento. Nos
#: outros, o título só está na primeira página, e uma nova página do mesmo
#: tipo é outro documento (dois RTs seguidos, um por servidor).
TIPOS_CONTINUOS = frozenset({DIARIO_BORDO, NOTA_FISCAL, CONTRATO, ADITIVO})

#: Quanto do texto as regras olham (a primeira página basta; o resto é ruído).
LIMITE_TEXTO = 4000
#: O "topo" da página, para títulos.
TOPO = 600
#: Abaixo desta soma, o documento é DESCONHECIDO (uma palavra solta não classifica;
#: uma pista de nome de arquivo, sozinha, ainda sim — com confiança baixa).
MINIMO = 0.35

_ANCORADA = re.compile(r"(?<![\\\[])[$^]")  # ^ ou $ de verdade (não "[^…]" nem "\$")

_OF_NUM = r"OF(?:ICIO|\.)\s*(?:N\s*[O°.]*\s*)?:?\s*\d{1,4}\s*/\s*\d{4}"


def _r(padrao: str, flags: int = 0):
    return re.compile(padrao, re.MULTILINE | flags)


# (tipo, regex, peso, onde: "texto" | "topo" | "inicio", descrição da evidência)
_REGRAS: tuple[tuple[str, re.Pattern, float, str, str], ...] = (
    # Capa do volume do eProtocolo.
    (CAPA, _r(r"FOLHA 1\b.{0,80}PROTOCOLO:", re.S), 0.6, "topo", "cabeçalho “Folha 1 / Protocolo:”"),
    (CAPA, _r(r"ORGAO CADASTRO:"), 0.8, "texto", "campo “Órgão Cadastro”"),
    (CAPA, _r(r"PALAVRAS-CHAVE:.{0,300}N[O°]/ANO|N[O°]/ANO.{0,300}PALAVRAS-CHAVE", re.S), 0.5, "texto", "campos “Nº/Ano” e “Palavras-chave”"),
    # Ofício: Viagens (oficio.html/.docx) e Coffee Break (coffee_break/editor.py).
    (OFICIO, _r(rf"^(?!.*ASSUNTO:)(?!.*\bREF(?:ERENTE|\.)? AO\b).*?\b{_OF_NUM}"), 0.75, "topo", "título “Ofício nº/ano”"),
    (OFICIO, _r(r"SOLICITO (?:A )?(?:AUTORIZACAO|CONVALIDACAO) E MEDIDAS PARA A CONCESSAO DE DIARIAS"), 0.9, "texto", "“solicito autorização/convalidação … diárias”"),
    (OFICIO, _r(r"SOLICITACAO DE (?:AUTORIZACAO|CONVALIDACAO) E CONCESSAO DE DIARIAS"), 0.8, "texto", "assunto “Solicitação de … concessão de diárias”"),
    (OFICIO, _r(r"\((?:AUTORIZACAO|CONVALIDACAO|COMPLEMENTAR|RETIFICADO)\)"), 0.3, "topo", "rótulo do assunto do ofício"),
    (OFICIO, _r(r"N[O°] SOLICITACAO.{0,5}\(?CENTRAL DE VIAGENS"), 0.5, "texto", "coluna “Nº solicitação (Central de Viagens)”"),
    (OFICIO, _r(r"PCPR PROTOCOLO N"), 0.4, "texto", "“PCPR Protocolo n.º”"),
    (OFICIO, _r(r"SERVICOS DE COFFEE BREAK FORAM DEVIDAMENTE ENTREGUES"), 0.6, "texto", "texto do ofício do Coffee Break"),
    (OFICIO, _r(r"ENCAMINHO, EM ANEXO, (?:A|AS) NOTAS? FISCA"), 0.4, "texto", "“Encaminho, em anexo, a(s) nota(s) fiscal(is)”"),
    (OFICIO, _r(r"^(?:EXCELENTISSIMO SENHOR|SENHOR DELEGADO)"), 0.25, "texto", "vocativo de ofício"),
    # Despacho criado dentro do eProtocolo.
    (DESPACHO, _r(r"PROTOCOLO:\s*\d{2}\.?\d{3}\.?\d{3}-\d\s*ASSUNTO:"), 0.7, "texto", "cabeçalho “Protocolo / Assunto” do eProtocolo"),
    (DESPACHO, _r(r"^DESPACHO$"), 0.6, "texto", "título “DESPACHO”"),
    (DESPACHO, _r(r"\bDESPACHO\b"), 0.3, "texto", "palavra “despacho”"),
    (DESPACHO, _r(r"INTERESSADO:"), 0.2, "texto", "campo “Interessado”"),
    (DESPACHO, _r(r"^(?:AO|A|AOS|AS) [A-Z0-9/ -]{2,40},$"), 0.2, "texto", "destino “Ao …,”"),
    # Justificativa (justificativa.html/.docx).
    (JUSTIFICATIVA, _r(r"^JUSTIFICATIVA$"), 0.85, "topo", "título “Justificativa”"),
    (JUSTIFICATIVA, _r(r"\bJUSTIFICATIVA\b"), 0.35, "topo", "palavra “justificativa” no topo"),
    # Termo de autorização (termo_autorizacao*.docx, blocos.py).
    (TERMO_AUTORIZACAO, _r(r"TERMO DE AUTORIZACAO"), 0.9, "texto", "título “Termo de autorização”"),
    (TERMO_AUTORIZACAO, _r(r"MANIFESTO O INTERESSE EM PARTICIPAR"), 0.8, "texto", "“manifesto o interesse em participar”"),
    (TERMO_AUTORIZACAO, _r(r"AUTORIZACAO DA CHEFIA"), 0.4, "texto", "“Autorização da chefia”"),
    # Relatório técnico (relatorio_tecnico.html, relatorio-tecnico.docx).
    (RT, _r(r"RELATORIO TECNICO DE VIAGEM"), 0.95, "texto", "título “Relatório técnico de viagem”"),
    (RT, _r(r"REF\.? AO OFICIO\s*(?:N\s*[O°.]*\s*)?\d{1,4}\s*/\s*\d{4}"), 0.55, "texto", "“Ref. ao Ofício”"),
    (RT, _r(r"VALORES UTILIZADOS NA VIAGEM"), 0.7, "texto", "“Valores utilizados na viagem”"),
    (RT, _r(r"DIARIA:.{0,80}TRANSLADO:", re.S), 0.5, "texto", "tabela “Diária / Translado”"),
    (RT, _r(r"OBJETIVO DA PARTICIPACAO|MEDIDAS A SEREM ADOTADAS"), 0.4, "texto", "seções do relatório"),
    # Diário de bordo (diario_bordo.html/.xlsx, A4 deitado).
    (DIARIO_BORDO, _r(r"FICHA INDIVIDUAL DO VEICULO"), 0.95, "texto", "“Ficha individual do veículo”"),
    (DIARIO_BORDO, _r(r"DIARIO DE BORDO"), 0.8, "texto", "título “Diário de bordo”"),
    (DIARIO_BORDO, _r(r"REFERENTE AO OFICIO:"), 0.5, "texto", "“Referente ao Ofício:”"),
    (DIARIO_BORDO, _r(r"E-?PROTOCOLO:"), 0.3, "texto", "“E-protocolo:”"),
    (DIARIO_BORDO, _r(r"NECESSIDADE DE ABASTECIMENTO"), 0.7, "texto", "coluna “Necessidade de abastecimento”"),
    (DIARIO_BORDO, _r(r"KM \(?(?:INICIAL|FINAL)\)?"), 0.6, "texto", "colunas “KM (inicial/final)”"),
    (DIARIO_BORDO, _r(r"PLACA (?:OFICIAL|RESERVADA):"), 0.4, "texto", "“Placa oficial / reservada”"),
    # Comprovante bancário.
    (COMPROVANTE,
     # O "DE" pode vir estragado pelo OCR de foto ("COMPROVANTE DI TRANSFERENCIA").
     _r(r"COMPROVANTE (?:[A-Z]{1,3} )?(?:TRANSFERENCIA|PIX|SAQUE|PAGAMENTO|DEPOSITO|TED|DOC|OPERACAO|TRANSACAO)"),
     0.9, "texto", "título “Comprovante de …”"),
    (COMPROVANTE, _r(r"RECIBO (?:DO |DE )?(?:SAQUE|TRANSFERENCIA|PAGAMENTO|DEPOSITO)"), 0.85, "texto",
     "título “Recibo de …”"),
    (COMPROVANTE, _r(r"\bPIX (?:ENVIADO|RECEBIDO|REALIZADO|EFETUADO|AGENDADO)\b|\bTRANSFERENCIA PIX\b"), 0.8, "texto",
     "“Pix enviado/realizado”"),
    (COMPROVANTE,
     _r(r"\bSAQUE (?:EFETUADO|REALIZADO|EM TERMINAL|NO TERMINAL|AUTOATENDIMENTO|CARTAO|COM CARTAO)"
        r"|VALOR (?:DO )?SAQUE|SAQUE DIGITAL|SAQUE SEM CARTAO"),
     0.75, "texto", "saque em terminal"),
    (COMPROVANTE,
     _r(r"TRANSFERENCIA (?:ENTRE CONTAS|REALIZADA|EFETUADA|ENVIADA|AGENDADA)"
        r"|\bTED\b.{0,40}(?:REALIZAD|EFETUAD|ENVIAD)|\bDOC\b.{0,40}(?:REALIZAD|EFETUAD)"),
     0.7, "texto", "transferência realizada"),
    (COMPROVANTE,
     _r(r"TRANSFERIDO PARA|DATA DA TRANSFERENCIA|DATA DO SAQUE|CARTAO DE CREDITO PARA CONTA"),
     0.7, "texto", "transferência do cartão / data da operação"),
    (COMPROVANTE, _r(r"\bPIX\b.{0,200}(?:VALOR|CHAVE)|(?:VALOR|CHAVE).{0,200}\bPIX\b", re.S), 0.45, "texto",
     "Pix com valor/chave"),
    (COMPROVANTE,
     _r(r"AUTENTICACAO|ID DA TRANSACAO|ID/TRANSACAO|\bE2E\b|END TO END|CODIGO DA TRANSACAO|\bNSU\b|CONTROLE:"),
     0.3, "texto", "autenticação bancária"),
    (COMPROVANTE, _r(r"FAVORECIDO|RECEBEDOR|QUEM RECEBEU|DADOS DO RECEBEDOR|DESTINO"), 0.25, "texto",
     "favorecido/recebedor"),
    (COMPROVANTE, _r(r"\b(?:PAGADOR|QUEM PAGOU|SACADOR|CLIENTE|CORRENTISTA|ORIGEM)\b"), 0.15, "texto",
     "pagador/cliente"),
    (COMPROVANTE,
     _r(r"BANCO DO BRASIL|CAIXA ECONOMICA|\bITAU\b|BRADESCO|SANTANDER|NUBANK|NU PAGAMENTOS|SICREDI|SICOOB"
        r"|BANCO INTER|\bC6 BANK|MERCADO PAGO|PICPAY|BANRISUL|PAGBANK"),
     0.15, "texto", "nome de banco"),
    # Ordem de serviço (ordem_servico.html/.docx; coffee_break_ordem_servico.html).
    (ORDEM_SERVICO, _r(r"ORDEM DE SERVICO\s*(?:N\s*[O°.]*\s*)?:?\s*\d"), 0.85, "topo", "título “Ordem de serviço nº”"),
    (ORDEM_SERVICO, _r(r"^DETERMINO$|\bDETERMINO\b"), 0.4, "texto", "“Determino”"),
    (ORDEM_SERVICO, _r(r"NO USO DAS ATRIBUICOES QUE ME FORAM CONFERIDAS"), 0.3, "texto", "“no uso das atribuições”"),
    (ORDEM_SERVICO, _r(r"DETALHAMENTO DO PEDIDO:|RESPONSAVEL PELO RECEBIMENTO:"), 0.4, "texto", "campos da OS do Coffee Break"),
    # Plano de trabalho.
    (PLANO_TRABALHO, _r(r"PLANO DE TRABALHO\s*N"), 0.9, "topo", "título “Plano de trabalho nº”"),
    (PLANO_TRABALHO, _r(r"BREVE CONTEXTUALIZACAO"), 0.6, "texto", "seção “Breve contextualização”"),
    (PLANO_TRABALHO, _r(r"METAS ESTABELECIDAS|RECURSOS NECESSARIOS|COORDENADOR DO EVENTO"), 0.35, "texto", "seções do plano"),
    # Nota fiscal (DANFE, NFS-e).
    (NOTA_FISCAL, _r(r"DOCUMENTO AUXILIAR DA\s*NOTA FISCAL"), 0.9, "texto", "“Documento auxiliar da nota fiscal eletrônica”"),
    (NOTA_FISCAL, _r(r"\bDANFE\b"), 0.75, "texto", "DANFE"),
    (NOTA_FISCAL, _r(r"\bNFS-?E\b|NOTA FISCAL (?:ELETRONICA )?DE SERVICOS?"), 0.75, "texto", "NFS-e"),
    (NOTA_FISCAL, _r(r"\bNF-?E\b"), 0.35, "texto", "NF-e"),
    (NOTA_FISCAL, _r(r"CHAVE DE ACESSO"), 0.35, "texto", "chave de acesso"),
    # Certifico digital (Coffee Break).
    (CERTIFICO, _r(r"CERTIFICO DIGITAL"), 0.95, "texto", "título “Certifico digital”"),
    (CERTIFICO, _r(r"\bATESTO\b.{0,80}DEVIDAMENTE EXECUTAD", re.S), 0.6, "texto", "“Atesto que os serviços…”"),
    # Certidões de regularidade.
    (CERTIDAO, _r(r"\bCERTIDAO (?:NEGATIVA|POSITIVA|CONJUNTA|DE REGULARIDADE|DE DEBITOS)"), 0.8, "topo", "título de certidão"),
    (CERTIDAO, _r(r"CERTIFICADO DE\s*REGULARIDADE DO FGTS|REGULARIDADE DO EMPREGADOR"), 0.85, "texto", "certificado de regularidade do FGTS"),
    (CERTIDAO, _r(r"CND-?CIDADAO|CNDT\b|DEBITOS TRABALHISTAS|DIVIDA ATIVA DA UNIAO|DIVIDA ATIVA ESTADUAL"), 0.6, "texto", "órgão emissor de certidão"),
    (CERTIDAO, _r(r"\bCERTIDAO\b"), 0.3, "topo", "palavra “certidão” no topo"),
    # Contrato e termo aditivo.
    (ADITIVO, _r(r"TERMO ADITIVO AO CONTRATO"), 0.85, "topo", "“Termo aditivo ao contrato”"),
    (ADITIVO, _r(r"TERMO DE APOSTILAMENTO"), 0.7, "topo", "“Termo de apostilamento” (tratado como aditivo)"),
    (ADITIVO, _r(r"^(?!.*ASSUNTO:).{0,80}\bTERMO ADITIVO N"), 0.5, "topo", "cabeçalho “Termo aditivo nº”"),
    (ADITIVO, _r(r"\bCONTRATANTE:"), 0.15, "texto", "“Contratante:”"),
    (CONTRATO, _r(r"^(?!.*ASSUNTO:).{0,80}\bCONTRATO\W{0,6}(?:N\s*[O°.]*\s*:?\s*)?\d+/\d{4}"), 0.5, "topo", "cabeçalho “Contrato nº”"),
    (CONTRATO, _r(r"\bCONTRATANTE:"), 0.35, "texto", "“Contratante:”"),
    (CONTRATO, _r(r"\bCONTRATAD[OA]\b"), 0.25, "texto", "“Contratado(a)”"),
    (CONTRATO, _r(r"\bCLAUSULA (?:PRIMEIRA|1)"), 0.3, "texto", "“Cláusula primeira”"),
    # Nota de empenho e de liquidação (SIAFIC-PR).
    (NOTA_EMPENHO, _r(r"^.{0,120}NOTA DE EMPENHO", re.S), 0.95, "inicio", "título “Nota de empenho”"),
    (NOTA_EMPENHO, _r(r"\b\d{4}NE\d{6}\b"), 0.35, "texto", "nº de empenho (AAAANE…)"),
    (NOTA_LIQUIDACAO, _r(r"^.{0,120}NOTA DE LIQUIDACAO", re.S), 0.95, "inicio", "título “Nota de liquidação”"),
    (NOTA_LIQUIDACAO, _r(r"\b\d{4}NL\d{6}\b"), 0.45, "texto", "nº de liquidação (AAAANL…)"),
    # E-mail impresso (Outlook/Gmail).
    (EMAIL, _r(r"^(?:DE|FROM):\s*.{0,80}@"), 0.45, "topo", "linha “De:” com endereço"),
    (EMAIL, _r(r"^(?:PARA|TO):\s*"), 0.3, "topo", "linha “Para:”"),
    (EMAIL, _r(r"^(?:ENVIADO|ENVIADA|SENT|DATE)(?: EM)?:"), 0.35, "topo", "linha “Enviado em:”"),
    (EMAIL, _r(r"^(?:ASSUNTO|SUBJECT):"), 0.2, "topo", "linha “Assunto:”"),
    (EMAIL, _r(r"^GMAIL - |\bGMAIL\b.{0,40}<?[\w.+-]+@|OUTLOOK"), 0.4, "topo", "cabeçalho do Gmail/Outlook"),
)

# Pistas pelo nome do arquivo (marcador do eProtocolo, folha de assinatura).
_PISTAS_NOME: tuple[tuple[str, re.Pattern, float], ...] = (
    (CAPA, re.compile(r"CONTRA ?CAPA|^CAPA\b"), 0.6),
    (ADITIVO, re.compile(r"ADITIVO"), 0.35),
    (CONTRATO, re.compile(r"CONTRATO"), 0.3),
    (CERTIFICO, re.compile(r"CERTIFICO"), 0.4),
    (NOTA_FISCAL, re.compile(r"^NF|NOTA ?FISCAL|DANFE|NFS ?E"), 0.35),
    (NOTA_EMPENHO, re.compile(r"\d{4} ?NE ?\d{6}|EMPENHO"), 0.4),
    (NOTA_LIQUIDACAO, re.compile(r"\d{4} ?NL ?\d{6}|^LIQ|LIQUIDACAO"), 0.4),
    (DESPACHO, re.compile(r"DESPACHO"), 0.4),
    (OFICIO, re.compile(r"^OF(?:ICIO)?[ ._-]*\d|^OFICIO"), 0.35),
    (RT, re.compile(r"\bRT\b|RELATORIO"), 0.35),
    (DIARIO_BORDO, re.compile(r"DIARIO|BORDO"), 0.35),
    (TERMO_AUTORIZACAO, re.compile(r"TERMO.{0,5}AUTORIZ"), 0.4),
    (JUSTIFICATIVA, re.compile(r"JUSTIFICATIVA"), 0.4),
    (ORDEM_SERVICO, re.compile(r"ORDEM ?(?:DE )?SERVICO|^OS[ ._-]*\d"), 0.35),
    (PLANO_TRABALHO, re.compile(r"PLANO ?(?:DE )?TRABALHO|^PT[ ._-]*\d"), 0.35),
    (COMPROVANTE, re.compile(r"COMPROV|RECIBO|\bPIX\b|\bTED\b|SAQUE|TRANSF"), 0.35),
    (CERTIDAO, re.compile(r"CERTIDAO|\bCND|FGTS|TRABALHISTA|MUNICIPAL|ESTADUAL|FEDERAL"), 0.3),
    (EMAIL, re.compile(r"\.(?:EML|MSG)$|E-?MAIL"), 0.4),
)

_ORDEM = {tipo: posicao for posicao, tipo in enumerate(TIPOS)}

#: Tipo que, com sinal forte (≥ 0.8), tira o outro da disputa: o aditivo é
#: sobre um contrato, a liquidação cita o empenho, o certifico cita a nota.
_ENGLOBA = {
    ADITIVO: (CONTRATO,),
    NOTA_LIQUIDACAO: (NOTA_EMPENHO,),
    CERTIFICO: (NOTA_FISCAL,),
}


def texto_para_regras(texto: str) -> str:
    """O texto como as regras o veem: cada linha normalizada, linhas vazias fora."""
    linhas = (normalizar(linha) for linha in str(texto or "")[: LIMITE_TEXTO * 2].splitlines())
    return "\n".join(linha for linha in linhas if linha)[:LIMITE_TEXTO]


def _nome_para_regras(titulo: str) -> str:
    nome = unicodedata.normalize("NFKD", str(titulo or ""))
    nome = "".join(c for c in nome if not unicodedata.combining(c)).upper()
    nome = re.sub(r"^\s*\d+\s*-\s*", "", nome)  # "12 - " do marcador do eProtocolo
    nome = re.sub(r"\.PDF$", "", nome.strip())
    return re.sub(r"[_\s]+", " ", nome).strip()


def classificar(texto_primeira_pagina: str, titulo: str = "") -> tuple[str, float, list[str]]:
    """(tipo, confiança de 0 a 1, evidências) do documento.

    `texto_primeira_pagina` é o corpo da primeira página de conteúdo (sem a
    moldura do eProtocolo); `titulo`, o nome do arquivo quando houver. Sem
    sinal nenhum, devolve `(DESCONHECIDO, 0.0, [])`.
    """
    texto = texto_para_regras(texto_primeira_pagina)
    # Regra com ^ ou $ olha linha a linha; as outras, o texto corrido — uma
    # frase quebrada em duas linhas ("TERMO ADITIVO AO / CONTRATO") tem de casar.
    por_linha = {"texto": texto, "topo": texto[:TOPO], "inicio": texto[:200]}
    corrido = {chave: valor.replace("\n", " ") for chave, valor in por_linha.items()}
    faltas: dict[str, float] = {}
    evidencias: dict[str, list[str]] = {}

    def marcar(tipo, peso, evidencia):
        faltas[tipo] = faltas.get(tipo, 1.0) * (1.0 - peso)
        evidencias.setdefault(tipo, []).append(evidencia)

    for tipo, regra, peso, onde, descricao in _REGRAS:
        alvo = (por_linha if _ANCORADA.search(regra.pattern) else corrido)[onde]
        if regra.search(alvo):
            marcar(tipo, peso, descricao)

    nome = _nome_para_regras(titulo)
    if nome:
        for tipo, regra, peso in _PISTAS_NOME:
            if regra.search(nome):
                marcar(tipo, peso, f"nome do arquivo “{str(titulo).strip()[:80]}”")
                break  # uma pista de nome só: "CONTRATO…TERMOADITIVO" é aditivo

    if not faltas:
        return DESCONHECIDO, 0.0, []
    pontos = {tipo: 1.0 - falta for tipo, falta in faltas.items()}
    for tipo, englobados in _ENGLOBA.items():
        if pontos.get(tipo, 0.0) >= 0.8:
            for englobado in englobados:
                pontos.pop(englobado, None)
    ordenados = sorted(pontos.items(), key=lambda item: (-item[1], _ORDEM.get(item[0], 99)))
    tipo, melhor = ordenados[0]
    segundo = ordenados[1][1] if len(ordenados) > 1 else 0.0
    if melhor < MINIMO:
        return DESCONHECIDO, round(melhor, 2), evidencias[tipo]
    # A soma probabilística comprime perto de 1: a margem se mede no que falta
    # a cada um. Empate técnico derruba a confiança pela metade.
    confianca = melhor * (1.0 - 0.5 * (1.0 - melhor) / max(1.0 - segundo, 1e-6))
    return tipo, round(confianca, 2), evidencias[tipo]
