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


@dataclass(frozen=True)
class CampoEditavel:
    chave: str
    rotulo: str
    partes: tuple[Parte, ...]
    ajuda: str = ""

    @property
    def nomes(self) -> tuple[str, ...]:
        return tuple(parte.nome for parte in self.partes)

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
)

REGISTRO: dict[DocumentoTipo, dict[str, CampoEditavel]] = {
    DocumentoTipo.OFICIO: {campo.chave: campo for campo in CAMPOS_OFICIO},
}


def campos_do_tipo(tipo) -> dict[str, CampoEditavel]:
    return REGISTRO.get(tipo, {})


def campo(tipo, chave: str) -> CampoEditavel | None:
    return campos_do_tipo(tipo).get(chave)


def marcacao(tipo) -> dict[str, dict]:
    """O que a folha recebe em `campos_editaveis`: chave, rótulo e se o trecho
    se digita na folha — a tag `{% editavel %}` decide pela presença da chave e
    marca o que é digitável para o navegador abrir o cursor ali."""
    marcados = {}
    for chave, definicao in campos_do_tipo(tipo).items():
        dados = {"rotulo": definicao.rotulo, "digitavel": definicao.digitavel}
        if definicao.digitavel:
            # Qual campo o trecho grava e se aceita mais de uma linha: o
            # navegador precisa dos dois para gravar sem adivinhar.
            dados["parte"] = definicao.partes[0].nome
            dados["multilinha"] = definicao.partes[0].tipo == "texto_longo"
        marcados[chave] = dados
    return marcados
