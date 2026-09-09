"""
Resolução do assunto documental do ofício (rótulos e linhas de assunto).

A linha de assunto **não** deve reutilizar `oficio.assunto` (campo livre do
wizard), para evitar textos de demonstração como `[DEMO OFICIO]` no documento.

Regras:
- **Data do ofício** = `oficio.data_criacao` (date).
- **Primeira saída** = `get_primeira_saida_oficio` (datetime aware → comparação
  em data no fuso configurado).
- Se `data_criacao` < data da primeira saída → **Autorização**; caso contrário
  → **Convalidação**. Sem primeira saída utilizável, assume-se **Autorização**
  (comportamento conservador alinhado ao legado).
- **Retificado**: quando `retificado_documento` é verdadeiro **e** a regra por
  datas seria Autorização (documento emitido antes da viagem). Se a regra já
  for Convalidação, o marcador de retificação é ignorado.
- **Complementar**: quando `complementar_documento` é verdadeiro (marcador
  explícito do usuário, independente da data de emissão). Os dois marcadores
  são mutuamente exclusivos — ver `oficios/services.py`.

`assunto_termo` (usado na frase fixa do ofício "solicito {assunto_termo} e
medidas para a concessão de diárias...") **nunca** pode ser outra coisa além
de "autorização" ou "convalidação" — os marcadores de Retificado/Complementar
só afetam `assunto_oficio`/`assunto_rotulo` (o rótulo entre parênteses),
nunca o termo da frase.
"""

from __future__ import annotations

from datetime import date
from datetime import datetime

from django.utils import timezone

from viagens_oficios.justificativas_services import get_primeira_saida_oficio

from .models import Oficio

ASSUNTO_AUTORIZACAO = "Solicitação de autorização e concessão de diárias."
ASSUNTO_CONVALIDACAO = "Solicitação de convalidação e concessão de diárias."


def _data_criacao(oficio: Oficio) -> date:
    d0 = oficio.data_criacao
    if isinstance(d0, datetime):
        return d0.date()
    return d0


def resolver_assunto_oficio(oficio: Oficio) -> dict[str, str]:
    """
    Devolve chaves estáveis para templates: `assunto_linha`, `assunto_oficio`,
    `assunto_termo` e `assunto_rotulo` (igual a `assunto_oficio`).
    """
    primeira = get_primeira_saida_oficio(oficio)
    d0_date = _data_criacao(oficio)

    if primeira is None:
        base_autorizacao = True
    else:
        s_local = primeira.astimezone(timezone.get_current_timezone()).date()
        base_autorizacao = d0_date < s_local

    complementar = bool(getattr(oficio, "complementar_documento", False))
    if complementar:
        termo = "autorização" if base_autorizacao else "convalidação"
        return {
            "assunto_linha": ASSUNTO_AUTORIZACAO if base_autorizacao else ASSUNTO_CONVALIDACAO,
            "assunto_oficio": "(Complementar)",
            "assunto_termo": termo,
            "assunto_rotulo": "(Complementar)",
        }

    retificado = bool(getattr(oficio, "retificado_documento", False))
    if retificado and base_autorizacao:
        return {
            "assunto_linha": ASSUNTO_AUTORIZACAO,
            "assunto_oficio": "(Retificado)",
            "assunto_termo": "autorização",
            "assunto_rotulo": "(Retificado)",
        }

    if base_autorizacao:
        return {
            "assunto_linha": ASSUNTO_AUTORIZACAO,
            "assunto_oficio": "(Autorização)",
            "assunto_termo": "autorização",
            "assunto_rotulo": "(Autorização)",
        }

    return {
        "assunto_linha": ASSUNTO_CONVALIDACAO,
        "assunto_oficio": "(Convalidação)",
        "assunto_termo": "convalidação",
        "assunto_rotulo": "(Convalidação)",
    }
