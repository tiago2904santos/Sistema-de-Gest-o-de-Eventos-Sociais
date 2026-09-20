"""Política de acesso do assistente — que é, de propósito, a de ninguém.

O assistente não tem grupo, perfil nem módulo próprio: ele empresta a
permissão de quem está conversando. Este arquivo existe só para dar nome ao
que já está decidido em ``viagens_cadastros.permissions`` e deixar explícito
que aqui não se inventa regra de acesso.

Por que não criar um grupo "ASSISTENTE": um usuário que consulta pelas telas
passaria a escrever pelo chat, e a auditoria mostraria a ação no nome dele sem
que ele pudesse tê-la feito sozinho. A pergunta "o que o assistente pode
fazer?" tem uma resposta só — o que aquela pessoa já podia.
"""

from viagens_cadastros.permissions import (
    pode_acessar as pode_consultar_viagens,
    pode_editar_cadastros,
)

# Preparar viagem grava Viagem, Roteiro, Ofício e Termo. Quem só tem o módulo
# consulta; escrever exige VIAGENS_GESTOR ou VIAGENS_OPERADOR, igual às telas.
pode_preparar_documentos = pode_editar_cadastros

__all__ = ["pode_consultar_viagens", "pode_preparar_documentos"]
