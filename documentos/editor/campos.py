"""Registro explícito do que o editor documental pode alterar.

Cada entrada liga um trecho do documento (`{% editavel "chave" %}` no
template) aos campos reais do model de onde ele nasce. Só o que está aqui
entra na folha marcado e passa pela API: chave vinda do navegador que não
esteja no registro é 404, nunca um `setattr`. "Tudo que veio de um campo
real do sistema continua vinculado a esse campo" — o registro é esse vínculo.

O tipo de cada parte decide o componente global do painel (texto, texto
longo, data, escolha, booleano, escolha múltipla). Um trecho tem uma parte
na maioria dos casos e mais de uma quando o texto do documento nasce de
dois campos (custeio e a observação que só existe para outra instituição).

Cada campo diz a sua **origem** — onde o dado mora e, portanto, o que muda
quando se edita no documento (`documentos.editor.vinculos.FONTES`):
`oficio` (o próprio ofício), `marcacao` (retificado/complementar do ofício),
`servidor` (o cadastro do servidor de uma linha da equipe — muda em todos os
documentos dele), `solicitacao` (o número da Central de Viagens, na prestação
de contas) e `configuracao` (a configuração do setor e os assinantes — muda
em todos os documentos). Trecho que é de um registro entre vários (a linha de
um servidor) leva o id dele na folha (`data-doc-objeto`).
"""

from __future__ import annotations

from dataclasses import dataclass

from documentos.services.types import DocumentoTipo

TIPOS_DE_PARTE = ("texto", "texto_longo", "data", "escolha", "booleano", "escolha_multipla")


@dataclass(frozen=True)
class Parte:
    nome: str  # campo real do model, e do formulário do domínio
    tipo: str
    rotulo: str
    ajuda: str = ""
    mascara: str = ""
    linhas: int = 4
    # (parte, valor) que torna esta parte visível no painel; o formulário do
    # domínio continua validando a combinação, o painel só esconde.
    apenas_quando: tuple[str, str] | None = None

    def __post_init__(self):
        if self.tipo not in TIPOS_DE_PARTE:
            raise ValueError(f"Tipo de parte desconhecido: {self.tipo}")


ORIGENS = (
    "oficio", "marcacao", "servidor", "solicitacao", "configuracao", "documento", "viatura", "trecho", "prestacao",
    # Cadastros do Coffee Break que a OS mostra (fornecedor, contrato, lote).
    "fornecedor", "contrato", "lote",
)

# Origens de um registro entre vários: o trecho leva o id dele na folha e não
# entra no menu "Campos" (edita-se na linha a que pertence).
ORIGENS_POR_OBJETO = ("servidor", "solicitacao", "viatura", "trecho")


@dataclass(frozen=True)
class CampoEditavel:
    chave: str
    rotulo: str
    partes: tuple[Parte, ...]
    ajuda: str = ""
    origem: str = "oficio"

    def __post_init__(self):
        if self.origem not in ORIGENS:
            raise ValueError(f"Origem desconhecida: {self.origem}")

    @property
    def nomes(self) -> tuple[str, ...]:
        return tuple(parte.nome for parte in self.partes)

    @property
    def so_links(self) -> bool:
        """Trecho que nasce de uma tela que o balão não reproduz (destinos,
        efetivo, funções da equipe): o balão explica e leva até ela."""
        return not self.partes

    @property
    def digitavel(self) -> bool:
        """O trecho se edita digitando na própria folha, como num editor de
        texto: uma parte só, e de texto.

        O resto precisa de escolha (custeio), de alternância (porte de arma)
        ou de busca em registros do sistema (viajantes) — nada disso se
        digita, e cada um segue pelo seu controle.
        """
        return len(self.partes) == 1 and self.partes[0].tipo in ("texto", "texto_longo")


CAMPOS_OFICIO = (
    CampoEditavel("data_criacao", "Data do ofício", (Parte("data_criacao", "data", "Data do ofício"),)),
    CampoEditavel("protocolo", "Protocolo", (
        Parte("protocolo", "texto", "Protocolo", mascara="protocolo", ajuda="Nove dígitos; a máscara entra ao salvar."),
    )),
    CampoEditavel("motivo", "Motivo da viagem", (Parte("motivo", "texto_longo", "Motivo da viagem", linhas=7),)),
    CampoEditavel("custeio", "Custeio", (
        Parte("custeio", "escolha", "Custeio"),
        Parte("custeio_observacao", "texto", "Observação do custeio", apenas_quando=("custeio", "OUTRA_INSTITUICAO")),
    ), ajuda="O bloco de custos do documento segue esta escolha."),
    CampoEditavel("servidores", "Viajantes", (Parte("servidores", "escolha_multipla", "Viajantes"),),
                  ajuda="A tabela da equipe, o número de diárias por servidor e os termos seguem esta lista."),
    CampoEditavel("porte_transporte_armas", "Porte/trânsito de arma", (
        Parte("porte_transporte_armas", "booleano", "Há porte ou trânsito de arma"),
    )),
    CampoEditavel("marcacao", "Tipo do ofício", (Parte("tipo_documento", "escolha", "Tipo do ofício"),), origem="marcacao",
                  ajuda="Autorização ou convalidação segue a data do ofício e a primeira saída do roteiro; "
                        "aqui se marca se o ofício é retificado ou complementar."),
    CampoEditavel("transporte", "Transporte", (
        Parte("viatura", "escolha", "Viatura cadastrada", ajuda="Sem viatura cadastrada, preencha os dados abaixo."),
        Parte("transporte_modelo_manual", "texto", "Modelo", apenas_quando=("viatura", "")),
        Parte("transporte_placa_manual", "texto", "Placa", apenas_quando=("viatura", "")),
        Parte("transporte_combustivel_manual", "texto", "Combustível", apenas_quando=("viatura", "")),
        Parte("transporte_tipo_manual", "texto", "Tipo (caracterizada, descaracterizada...)", apenas_quando=("viatura", "")),
        # O motorista está na mesma célula do documento: vai no mesmo balão.
        Parte("motorista_modo", "escolha", "Identificação do motorista"),
        Parte("motorista", "escolha", "Servidor motorista", apenas_quando=("motorista_modo", "SERVIDOR")),
        Parte("motorista_manual_nome", "texto", "Nome do motorista", apenas_quando=("motorista_modo", "MANUAL")),
        Parte("motorista_manual_cargo", "texto", "Cargo do motorista", apenas_quando=("motorista_modo", "MANUAL")),
        Parte("motorista_manual_unidade", "texto", "Unidade do motorista", apenas_quando=("motorista_modo", "MANUAL")),
    ), ajuda="Com viatura cadastrada, modelo, placa, combustível e tipo vêm do cadastro dela."),
    CampoEditavel("motorista", "Motorista", (
        Parte("motorista_modo", "escolha", "Identificação do motorista"),
        Parte("motorista", "escolha", "Servidor motorista", apenas_quando=("motorista_modo", "SERVIDOR")),
        Parte("motorista_manual_nome", "texto", "Nome", apenas_quando=("motorista_modo", "MANUAL")),
        Parte("motorista_manual_cargo", "texto", "Cargo", apenas_quando=("motorista_modo", "MANUAL")),
        Parte("motorista_manual_unidade", "texto", "Unidade", apenas_quando=("motorista_modo", "MANUAL")),
        Parte("motorista_oficio_referencia", "texto", "Ofício do motorista (quando é de outro ofício)"),
        Parte("motorista_protocolo_ref", "texto", "Protocolo do motorista (quando é de outro ofício)", mascara="protocolo"),
    )),
    CampoEditavel("roteiro", "Roteiro", (Parte("roteiro", "escolha", "Roteiro do ofício"),),
                  ajuda="Destino, datas, roteiro de ida e de retorno, diárias e valor vêm do roteiro. "
                        "Para mudar trechos e horários, abra o roteiro."),
    # Linhas da equipe: cada uma é o cadastro de um servidor.
    CampoEditavel("servidor_nome", "Nome do servidor", (Parte("nome", "texto", "Nome"),), origem="servidor",
                  ajuda="Muda o cadastro do servidor, em todos os documentos."),
    CampoEditavel("servidor_cpf", "CPF do servidor", (Parte("cpf", "texto", "CPF"),), origem="servidor",
                  ajuda="Muda o cadastro do servidor, em todos os documentos."),
    CampoEditavel("servidor_cargo", "Cargo do servidor", (Parte("cargo", "escolha", "Cargo"),), origem="servidor",
                  ajuda="Muda o cadastro do servidor, em todos os documentos."),
    CampoEditavel("solicitacao", "Nº da solicitação (Central de Viagens)", (Parte("numero_solicitacao", "texto", "Número da solicitação"),),
                  origem="solicitacao", ajuda="Fica na prestação de contas do servidor neste ofício."),
    # Configuração do setor e assinantes: valem para todos os documentos.
    CampoEditavel("config_orgao", "Órgão", (Parte("nome_orgao", "texto", "Nome do órgão"),), origem="configuracao",
                  ajuda="Configuração do setor: muda em todos os documentos."),
    CampoEditavel("config_unidade", "Unidade emissora", (Parte("unidade", "escolha", "Unidade emissora"),), origem="configuracao",
                  ajuda="Origem do ofício e linha da unidade no cabeçalho. Configuração do setor: muda em todos os documentos."),
    CampoEditavel("config_destino", "Destino do ofício", (Parte("destinatario_oficio_unidade", "texto", "Unidade de destino"),),
                  origem="configuracao",
                  ajuda="Quando o roteiro sai do Paraná, o destino é fixo pela regra. Configuração do setor: muda em todos os documentos."),
    CampoEditavel("config_destinatario", "Destinatário", (
        Parte("destinatario_oficio_nome", "texto", "Nome"),
        Parte("destinatario_oficio_cargo", "texto", "Cargo"),
    ), origem="configuracao", ajuda="Configuração do setor: muda em todos os documentos."),
    CampoEditavel("config_assinante", "Quem assina", (Parte("assina_oficio", "escolha", "Assina os ofícios"),), origem="configuracao",
                  ajuda="Nome e cargo saem do cadastro do servidor escolhido. Vale para todos os ofícios."),
    CampoEditavel("config_endereco", "Endereço da unidade", (
        Parte("cep", "texto", "CEP"),
        Parte("logradouro", "texto", "Logradouro"),
        Parte("numero", "texto", "Número"),
        Parte("bairro", "texto", "Bairro"),
        Parte("cidade_endereco", "texto", "Cidade"),
        Parte("uf", "texto", "UF"),
        Parte("telefone", "texto", "Telefone"),
        Parte("email", "texto", "E-mail"),
    ), origem="configuracao", ajuda="Rodapé e cidade do destinatário. Configuração do setor: muda em todos os documentos."),
)

_POR_CHAVE = {campo.chave: campo for campo in CAMPOS_OFICIO}
_CONFIG = "Configuração do setor: muda em todos os documentos."
_CADASTRO_SERVIDOR = "Muda o cadastro do servidor, em todos os documentos."
_CADASTRO_VIATURA = "Muda o cadastro da viatura, em todos os documentos."


def _do_oficio(*chaves):
    return tuple(_POR_CHAVE[chave] for chave in chaves)


def _assinante(nome, rotulo):
    return CampoEditavel(f"config_{nome}", "Quem assina", (Parte(nome, "escolha", rotulo),), origem="configuracao",
                         ajuda="Nome e cargo saem do cadastro do servidor escolhido. " + _CONFIG)


# Cabeçalho e rodapé que todos os documentos da folha institucional dividem.
CAMPOS_COMUNS = _do_oficio("config_orgao", "config_unidade", "config_endereco")

# Linha de um servidor no documento: o cadastro dele.
CAMPOS_DO_SERVIDOR = _do_oficio("servidor_nome", "servidor_cpf", "servidor_cargo") + (
    CampoEditavel("servidor_telefone", "Telefone do servidor", (Parte("telefone", "texto", "Telefone"),), origem="servidor",
                  ajuda=_CADASTRO_SERVIDOR),
    CampoEditavel("servidor_lotacao", "Lotação do servidor", (Parte("unidade", "escolha", "Unidade de lotação"),), origem="servidor",
                  ajuda=_CADASTRO_SERVIDOR),
)

CAMPOS_VIATURA = (
    CampoEditavel("viatura_modelo", "Modelo da viatura", (Parte("modelo", "texto", "Modelo"),), origem="viatura", ajuda=_CADASTRO_VIATURA),
    CampoEditavel("viatura_placa", "Placa da viatura", (Parte("placa", "texto", "Placa"),), origem="viatura", ajuda=_CADASTRO_VIATURA),
    CampoEditavel("viatura_combustivel", "Combustível da viatura", (Parte("combustivel", "escolha", "Combustível"),), origem="viatura",
                  ajuda=_CADASTRO_VIATURA),
)

CAMPOS_TERMO = CAMPOS_COMUNS + CAMPOS_DO_SERVIDOR + CAMPOS_VIATURA + (
    CampoEditavel("termo_periodo", "Data do evento", (
        Parte("data_evento_inicio", "data", "Data inicial"),
        Parte("data_evento_fim", "data", "Data final", ajuda="Vazia, vale a inicial."),
    ), origem="documento", ajuda="Sem data no termo, vale o período do roteiro do ofício vinculado."),
    CampoEditavel("termo_destino", "Destino", (Parte("destino_cidade", "escolha", "Município do destino"),), origem="documento",
                  ajuda="Destinos adicionais e municípios de outro estado se escolhem no cadastro do termo."),
    CampoEditavel("termo_viatura", "Viatura do termo", (Parte("viatura", "escolha", "Viatura"),), origem="documento",
                  ajuda="Sem viatura no termo, vale a do ofício vinculado."),
)

# O termo tirado do ofício: data, destino e viatura são os do próprio ofício.
CAMPOS_TERMO_OFICIO = CAMPOS_COMUNS + CAMPOS_DO_SERVIDOR + _do_oficio("roteiro", "transporte")

CAMPOS_JUSTIFICATIVA = CAMPOS_COMUNS + (
    CampoEditavel("justificativa_texto", "Texto da justificativa", (Parte("texto", "texto_longo", "Texto", linhas=10),),
                  origem="documento", ajuda="Cada linha é um parágrafo do documento."),
    _assinante("assina_justificativa", "Assina as justificativas"),
)

CAMPOS_ORDEM = CAMPOS_COMUNS + (
    CampoEditavel("config_sigla", "Sigla da unidade", (Parte("sigla_orgao", "texto", "Sigla"),), origem="configuracao", ajuda=_CONFIG),
    _assinante("assina_ordem_servico", "Assina as ordens de serviço"),
    CampoEditavel("os_tipo", "Tipo da ordem de serviço", (Parte("tipo_necessidade", "escolha", "Tipo"),), origem="documento",
                  ajuda="A referência, a determinação, as justificativas e a finalidade são o texto do modelo deste tipo."),
    CampoEditavel("os_equipe", "Equipe", (Parte("servidores", "escolha_multipla", "Servidores"),), origem="documento",
                  ajuda="A equipe sai agrupada por cargo. A função de cada um (condução, apoio...) se define na ordem de serviço."),
    CampoEditavel("os_periodo", "Período", (
        Parte("data_evento_inicio", "data", "Data inicial"),
        Parte("data_evento_fim", "data", "Data final", ajuda="Vazia, vale a inicial."),
    ), origem="documento"),
    CampoEditavel("os_motivo", "Motivo", (Parte("motivo", "texto_longo", "Motivo"),), origem="documento"),
    CampoEditavel("os_destinos", "Destinos", (), origem="documento",
                  ajuda="Os municípios de destino se escolhem na ordem de serviço, por estado."),
    CampoEditavel("os_funcoes", "Atribuições da equipe", (), origem="documento",
                  ajuda="As atribuições seguem a função de cada servidor, definida na ordem de serviço."),
)

CAMPOS_PLANO = CAMPOS_COMUNS + (
    _assinante("assina_plano_trabalho", "Assina os planos de trabalho"),
    CampoEditavel("plano_contextualizacao", "Breve contextualização", (Parte("contextualizacao", "texto_longo", "Texto", linhas=8),),
                  origem="documento", ajuda="Apagar o texto volta ao automático, feito do programa e do destino."),
    CampoEditavel("plano_coordenacao", "Coordenador do evento", (Parte("coordenacao", "texto_longo", "Texto", linhas=6),),
                  origem="documento", ajuda="Apagar o texto volta ao automático, feito dos coordenadores do plano."),
    CampoEditavel("plano_consideracoes", "Considerações finais", (Parte("consideracao_final", "texto_longo", "Texto", linhas=6),),
                  origem="documento", ajuda="Apagar o texto volta ao automático."),
    CampoEditavel("plano_periodo", "Datas do evento", (
        Parte("data_evento_inicio", "data", "Data inicial"),
        Parte("data_evento_fim", "data", "Data final"),
    ), origem="documento"),
    CampoEditavel("plano_horario", "Horário de atendimento", (Parte("horario_atendimento", "escolha", "Horário"),), origem="documento"),
    CampoEditavel("plano_atividades", "Atividades", (Parte("atividades_selecionadas", "escolha_multipla", "Atividades"),),
                  origem="documento", ajuda="Atividades, metas, recursos e a unidade móvel saem do catálogo de cada atividade."),
    CampoEditavel("plano_local", "Local", (), origem="documento", ajuda="Os destinos se escolhem no plano de trabalho."),
    CampoEditavel("plano_efetivo", "Efetivo", (), origem="documento", ajuda="O efetivo (cargo, unidade e quantidade) se define no plano."),
    CampoEditavel("plano_valor", "Valor do plano", (), origem="documento",
                  ajuda="O valor vem das diárias: saída e chegada na sede e o efetivo, no plano de trabalho."),
    CampoEditavel("plano_eventos", "Eventos do plano", (), origem="documento",
                  ajuda="Cada evento (data, local, atividades e efetivo) se edita no plano de trabalho."),
)

_RT = "Texto do relatório técnico: vale para toda a equipe desta prestação."
CAMPOS_RELATORIO = CAMPOS_COMUNS + _do_oficio("servidor_nome", "servidor_cpf") + (
    CampoEditavel("rt_diaria", "Diária recebida", (
        Parte("diaria", "texto", "Diária", ajuda="Ex.: “R$ 87,00 (saque)”. Vazio, vale a diária do roteiro."),
    ), origem="prestacao", ajuda="Fica na prestação de contas deste servidor."),
    CampoEditavel("rt_translado", "Translado", (Parte("translado", "texto", "Translado"),), origem="documento", ajuda=_RT),
    CampoEditavel("rt_combustivel", "Combustível", (Parte("combustivel", "texto", "Combustível"),), origem="documento", ajuda=_RT),
    CampoEditavel("rt_passagem", "Passagem", (Parte("passagem", "texto", "Passagem"),), origem="documento", ajuda=_RT),
    CampoEditavel("rt_motivo", "Descrição do evento", (Parte("motivo", "texto_longo", "Descrição do evento"),), origem="documento",
                  ajuda="Vazio, vale o motivo do ofício. " + _RT),
    CampoEditavel("rt_atividade", "Objetivo da participação", (Parte("atividade", "texto_longo", "Objetivo da participação"),),
                  origem="documento", ajuda=_RT),
    CampoEditavel("rt_conclusao", "Conclusão", (Parte("conclusao", "texto_longo", "Conclusão"),), origem="documento", ajuda=_RT),
    CampoEditavel("rt_medidas", "Medidas a serem adotadas", (Parte("medidas", "texto_longo", "Medidas"),), origem="documento", ajuda=_RT),
    CampoEditavel("rt_info", "Informações complementares", (Parte("info_complementares", "texto_longo", "Informações complementares"),),
                  origem="documento", ajuda=_RT),
    CampoEditavel("rt_oficio", "Ofício", (), origem="documento", ajuda="O número é o do ofício desta prestação de contas."),
)

_DIARIO = "Vale só para este diário de bordo; o ofício não muda."
CAMPOS_DIARIO = _do_oficio("config_unidade") + (
    CampoEditavel("diario_motorista", "Motorista", (
        Parte("motorista_modo", "escolha", "Motorista"),
        Parte("motorista_servidor", "escolha", "Servidor do ofício", apenas_quando=("motorista_modo", "SERVIDOR")),
        Parte("motorista_manual_nome", "texto", "Nome", apenas_quando=("motorista_modo", "OUTRO_OFICIO")),
        Parte("motorista_manual_cpf", "texto", "CPF", apenas_quando=("motorista_modo", "OUTRO_OFICIO")),
        Parte("motorista_oficio_referencia", "texto", "Ofício do motorista (número/ano)", apenas_quando=("motorista_modo", "OUTRO_OFICIO")),
        Parte("motorista_protocolo_ref", "texto", "Protocolo do motorista", mascara="protocolo", apenas_quando=("motorista_modo", "OUTRO_OFICIO")),
    ), origem="documento", ajuda="O ofício e o protocolo do diário são os do motorista. " + _DIARIO),
    CampoEditavel("diario_viatura", "Viatura", (
        Parte("viatura_modo", "escolha", "Viatura"),
        Parte("viatura", "escolha", "Viatura cadastrada", apenas_quando=("viatura_modo", "BANCO")),
        Parte("viatura_manual_modelo", "texto", "Modelo", apenas_quando=("viatura_modo", "MANUAL")),
        Parte("viatura_manual_placa", "texto", "Placa", apenas_quando=("viatura_modo", "MANUAL")),
        Parte("viatura_manual_tipo", "escolha", "Tipo", apenas_quando=("viatura_modo", "MANUAL")),
        Parte("viatura_manual_combustivel", "texto", "Combustível", apenas_quando=("viatura_modo", "MANUAL")),
    ), origem="documento", ajuda=_DIARIO),
    CampoEditavel("diario_km", "Quilometragem e abastecimento", (
        Parte("km_inicial", "texto", "KM inicial"),
        Parte("km_final", "texto", "KM final"),
        Parte("abastecimento", "escolha", "Necessidade de abastecimento"),
    ), origem="trecho", ajuda="Do trecho desta linha."),
    CampoEditavel("diario_trechos", "Trechos", (), origem="documento",
                  ajuda="Datas, horas, origem e destino vêm do roteiro ajustado da prestação de contas."),
)

REGISTRO: dict[str, dict[str, CampoEditavel]] = {
    chave: {campo.chave: campo for campo in campos}
    for chave, campos in (
        (DocumentoTipo.OFICIO.value, CAMPOS_OFICIO),
        (DocumentoTipo.TERMO_AUTORIZACAO.value, CAMPOS_TERMO),
        ("termo_oficio", CAMPOS_TERMO_OFICIO),
        (DocumentoTipo.JUSTIFICATIVA.value, CAMPOS_JUSTIFICATIVA),
        (DocumentoTipo.ORDEM_SERVICO.value, CAMPOS_ORDEM),
        (DocumentoTipo.PLANO_TRABALHO.value, CAMPOS_PLANO),
        (DocumentoTipo.RELATORIO_TECNICO.value, CAMPOS_RELATORIO),
        (DocumentoTipo.DIARIO_BORDO.value, CAMPOS_DIARIO),
    )
}


def campos_do_tipo(tipo) -> dict[str, CampoEditavel]:
    """Campos de um vínculo do editor: a chave é o tipo do documento, ou a do
    vínculo quando o tipo tem mais de um (o termo do cadastro e o do ofício)."""
    return REGISTRO.get(getattr(tipo, "value", tipo), {})


def campo(tipo, chave: str) -> CampoEditavel | None:
    return campos_do_tipo(tipo).get(chave)


def marcacao(tipo, origens=None) -> dict[str, dict]:
    """O que a folha recebe em `campos_editaveis`: chave, rótulo e se o trecho
    se digita na folha — a tag `{% editavel %}` decide pela presença da chave e
    marca o que é digitável para o navegador abrir o cursor ali. `origens`
    limita às origens que quem vê pode editar (a configuração é da gestão)."""
    marcados = {}
    for chave, definicao in campos_do_tipo(tipo).items():
        if origens is not None and definicao.origem not in origens:
            continue
        dados = {"rotulo": definicao.rotulo, "digitavel": definicao.digitavel, "origem": definicao.origem}
        if definicao.digitavel:
            # Qual campo o trecho grava e se aceita mais de uma linha: o
            # navegador precisa dos dois para gravar sem adivinhar.
            dados["parte"] = definicao.partes[0].nome
            dados["multilinha"] = definicao.partes[0].tipo == "texto_longo"
        marcados[chave] = dados
    return marcados
