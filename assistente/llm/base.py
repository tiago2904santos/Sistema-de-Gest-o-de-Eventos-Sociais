"""O contrato que todo interpretador cumpre — e o que ele não pode fazer.

Um adaptador recebe texto e devolve uma ``Intencao``: o **nome** de uma
ferramenta e os **valores** dos parâmetros. Só isso. Ele não consulta o banco,
não grava nada, não escolhe se a ação acontece. Quem executa é o orquestrador,
depois de checar permissão e, se for o caso, pedir confirmação.

É esse recorte que torna o modelo de linguagem trocável. O adaptador
determinístico (regex sobre o cadastro real) e um adaptador de API cumprem o
mesmo contrato, então trocar um pelo outro é mudar uma linha de configuração —
e o sistema continua funcionando, com menos conversa, se não houver nenhum.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Intencao:
    """O que o interpretador entendeu, ainda sem nada ter acontecido."""

    ferramenta: str | None = None
    argumentos: dict = field(default_factory=dict)
    # Campos do preenchimento conversado, quando a intenção é montar algo:
    # vêm como texto cru e ainda precisam ser resolvidos contra o cadastro.
    campos: dict = field(default_factory=dict)
    explicacao: str = ""

    @property
    def entendida(self) -> bool:
        return bool(self.ferramenta)


class AdaptadorLLM:
    """Interface dos interpretadores. Implementações em irmãos deste módulo."""

    nome = "base"
    # Um adaptador que custa dinheiro se anuncia, para a tela poder avisar.
    remoto = False

    def interpretar(self, texto: str, *, ferramentas, usuario) -> Intencao:
        raise NotImplementedError
