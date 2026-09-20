"""Interpretador que usa a API da Anthropic — opcional, e só para entender.

O modelo recebe o catálogo de ferramentas e escolhe uma, com os argumentos.
Nada além disso: ele não vê o banco, não recebe resultado de consulta e não
decide se a ação acontece — nem se quem pediu pode fazê-la. A permissão é
checada depois, em ``Ferramenta.executar``, e um erro dele é um parâmetro
errado que aparece no resumo antes de qualquer gravação.

Por que uma chamada só, sem laço de agente: o trabalho aqui é roteamento, não
raciocínio de várias etapas. Uma chamada por mensagem mantém o custo previsível
e a latência compatível com quem espera resposta no chat. `effort="low"` pela
mesma razão — escolher entre oito ferramentas não é problema difícil.

Sem a biblioteca instalada ou sem chave, este adaptador não é escolhido: a
fábrica em ``__init__`` cai no determinístico, que não custa nada.
"""

from __future__ import annotations

import json

from .base import AdaptadorLLM, Intencao

INSTRUCAO = (
    "Você roteia pedidos de um sistema de gestão de viagens da administração "
    "pública para uma ferramenta. Escolha no máximo uma ferramenta e preencha "
    "os parâmetros com o que a pessoa disse, sem inventar nome, data ou lugar "
    "que ela não tenha mencionado. Nomes de pessoas e municípios devem ser "
    "copiados como ela falou — quem os identifica no cadastro é o sistema, "
    "não você. Se o pedido não corresponder a nenhuma ferramenta, não chame "
    "nenhuma e explique em uma frase o que ficou faltando."
)

TIPOS = {"texto": "string", "inteiro": "integer", "data": "string", "booleano": "boolean"}


def _esquema(ferramenta):
    propriedades, obrigatorios = {}, []
    for parametro in ferramenta.parametros:
        propriedades[parametro.nome] = {
            "type": TIPOS.get(parametro.tipo, "string"),
            "description": parametro.descricao
            + (" (formato aaaa-mm-dd)" if parametro.tipo == "data" else ""),
        }
        if parametro.obrigatorio:
            obrigatorios.append(parametro.nome)
    return {
        "name": ferramenta.nome,
        "description": ferramenta.descricao,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": propriedades,
            "required": obrigatorios,
            "additionalProperties": False,
        },
    }


class InterpretadorAnthropic(AdaptadorLLM):
    nome = "anthropic"
    remoto = True

    def __init__(self, *, api_key: str, modelo: str = "claude-opus-5", fallbacks: bool = True):
        import anthropic

        self._anthropic = anthropic
        self._cliente = anthropic.Anthropic(api_key=api_key)
        self._modelo = modelo
        self._fallbacks = fallbacks

    def _chamar(self, mensagem, ferramentas):
        comum = dict(
            model=self._modelo,
            max_tokens=4096,
            system=INSTRUCAO,
            output_config={"effort": "low"},
            tools=[_esquema(f) for f in ferramentas],
            messages=[{"role": "user", "content": mensagem}],
        )
        if not self._fallbacks:
            return self._cliente.messages.create(**comum)
        try:
            return self._cliente.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **comum,
            )
        except self._anthropic.BadRequestError:
            # Conta sem o beta de fallback: a recusa é do parâmetro, não do
            # pedido — repetir sem ele é melhor que devolver erro a quem
            # perguntou.
            return self._cliente.messages.create(**comum)

    def interpretar(self, texto: str, *, ferramentas, usuario) -> Intencao:
        resposta = self._chamar(texto, ferramentas)
        if resposta.stop_reason == "refusal":
            return Intencao(explicacao="O modelo recusou interpretar este pedido.")

        for bloco in resposta.content:
            if bloco.type != "tool_use":
                continue
            # A entrada vem como objeto do SDK; passa por JSON para não
            # depender do escape que o modelo usou (ver skill claude-api).
            argumentos = json.loads(json.dumps(bloco.input))
            if bloco.name == "preparar_viagem":
                return Intencao(ferramenta=bloco.name, campos=argumentos)
            return Intencao(ferramenta=bloco.name, argumentos=argumentos)

        texto_resposta = " ".join(b.text for b in resposta.content if b.type == "text")
        return Intencao(explicacao=texto_resposta.strip() or "Não reconheci o pedido.")
