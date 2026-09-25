"""Importar o processo do eProtocolo na prestação de contas de Viagens.

O operador solta o PDF inteiro do processo (volume do eProtocolo) na lista de
prestações, de ofícios ou de termos de autorização, ou no ⋮ de um ofício ou de
um termo. O sistema:

1. **analisa** (`analise.analisar`, sem gravar, fora da transação): lê o
   processo com `core.leitura`, descobre de qual prestação ele é e o destino de
   cada documento — ofício, despacho(s) com a folha de assinatura, RT de cada
   servidor, diário de bordo (girado para paisagem em pé) e comprovantes (de
   quem, valor, data e operação);
2. **registra** (`entrada.registrar_importacao`): guarda o PDF como veio e o
   plano em `ImportacaoProcesso` (auditoria, "aplicar de novo", hash contra
   importar duas vezes o mesmo arquivo);
3. **aplica** (`aplicacao.aplicar_importacao`, atômico): sozinho quando a
   identificação é segura e todo documento tem destino certo; senão depois da
   conferência na tela, já preenchida, com um clique em "Aplicar".

Os documentos que o sistema gerou e que voltam assinados — ofício,
justificativa, termo de cada servidor e ordem de serviço — vão também para a
versão assinada do documento deles (`documentos`, `artefatos`), a mesma do
"Anexar assinado" das listas. PDF só com termos (escaneados juntos, sem a
moldura do eProtocolo) é separado e distribuído por servidor.

Nenhum dado sai do servidor: leitura por regras + pypdf, OCR só com tesseract
local, se houver.
"""

from .analise import analisar
from .aplicacao import ImportacaoRecusada
from .aplicacao import ResultadoImportacao
from .aplicacao import aplicar_importacao
from .entrada import aplicar_escolhas
from .entrada import descartar
from .entrada import hash_do_arquivo
from .entrada import importacao_do_mesmo_arquivo
from .entrada import limite_de_bytes
from .entrada import reanalisar
from .entrada import registrar_importacao
from .entrada import validar_arquivo_do_processo
from .plano import Plano

__all__ = [
    "analisar",
    "aplicar_escolhas",
    "aplicar_importacao",
    "descartar",
    "hash_do_arquivo",
    "importacao_do_mesmo_arquivo",
    "ImportacaoRecusada",
    "limite_de_bytes",
    "Plano",
    "reanalisar",
    "registrar_importacao",
    "ResultadoImportacao",
    "validar_arquivo_do_processo",
]
