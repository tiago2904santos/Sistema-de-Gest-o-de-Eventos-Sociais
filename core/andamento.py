"""Andamento por status, no desenho das Palestras e das Solicitações de evento.

O status não é um campo solto do formulário: anda por ações registradas, cada
uma com a anotação de andamento, e a tela mostra as etapas num stepper. Cada
módulo descreve o seu fluxo com um :class:`Fluxo` e usa as mesmas telas
(`components/v32/andamento_*.html`).
"""

from dataclasses import dataclass, field


@dataclass
class Fluxo:
    choices: list  # [(valor, rótulo)] do TextChoices
    dicas: dict  # valor -> o que o status quer dizer (cartão de escolha)
    icones: dict  # valor -> ícone
    etapas: list  # [(título, {valores})], na ordem do fluxo
    encerrados: set = field(default_factory=set)  # saídas fora do stepper (cancelada...)
    concluido: str = ""  # o status que conclui todas as etapas

    def rotulo(self, valor):
        return dict(self.choices).get(valor, valor)

    def opcoes(self, atual, escolhido=""):
        """Os cartões do próximo status: todos, menos o atual."""
        return [
            {
                "valor": valor,
                "rotulo": rotulo,
                "dica": self.dicas.get(valor, ""),
                "icone": self.icones.get(valor, "activity"),
                "marcado": valor == escolhido,
            }
            for valor, rotulo in self.choices
            if valor != atual
        ]

    def passos(self, atual):
        """O stepper: concluídas, a atual (com o rótulo do status) e as que faltam."""
        indice = next((i for i, (_, grupo) in enumerate(self.etapas) if atual in grupo), None)
        saida = []
        for i, (titulo, grupo) in enumerate(self.etapas):
            if atual == self.concluido or (indice is not None and i < indice):
                estado = "concluido"
            elif i == indice:
                estado = "atual"
            else:
                estado = "pendente"
            # Status que é pausa dentro de uma etapa aparece com o próprio nome.
            rotulo = self.rotulo(atual) if i == indice and len(grupo) > 1 else titulo
            saida.append({"titulo": rotulo, "estado": estado})
        return saida


def contexto(fluxo, atual, *, url, ultima_anotacao="", rotulo_status="Novo status",
             erro="", escolhido="", texto="", placeholder="", ajuda=""):
    """O que as telas `components/v32/andamento_*.html` recebem."""
    return {
        "andamento": {
            "url": url,
            "etapas": fluxo.passos(atual),
            "atual": atual,
            "atual_rotulo": fluxo.rotulo(atual),
            "encerrado": atual in fluxo.encerrados,
            "ultima_anotacao": ultima_anotacao,
            "opcoes": fluxo.opcoes(atual, escolhido),
            "rotulo_status": rotulo_status,
            "erro": erro,
            "texto": texto,
            "placeholder": placeholder,
            "ajuda": ajuda,
        }
    }
