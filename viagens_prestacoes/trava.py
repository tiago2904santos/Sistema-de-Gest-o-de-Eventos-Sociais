"""Prestação finalizada fica só para leitura até alguém clicar em "Reabrir" (m092).

As rotas que gravam (autosave, anexar, remover, carimbo, diário, RT) passam por
`travar_se_finalizada`, aplicada em `urls.py`. O que é do servidor trava quando
ele está finalizado; o que é compartilhado pela equipe (despacho, ofício, diário,
RT) só quando a equipe inteira está — a prestação é individual, e o colega que
ainda não prestou contas precisa desses documentos.
"""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from core.retorno import voltar_para

MENSAGEM = "Prestação finalizada — reabra para editar."

#: Rotas do próprio servidor (`ps_pk`): travam com ele finalizado.
DO_SERVIDOR = {
    "prestacao_servidor_solicitacao_autosave",
    "prestacao_servidor_arquivo_autosave",
    "prestacao_servidor_assinado_anexar",
    "pacote_revisar",
}
#: Rotas do que a equipe compartilha: travam com todos finalizados.
DA_EQUIPE = {
    "prestacao_arquivo_autosave",
    "prestacao_despacho_assinado_anexar",
    "prestacao_oficio_assinado_anexar",
    "prestacao_carimbo_ajustar",
    "rt_servidor",
    "rt_servidor_autosave",
    "rt_autosave",
    "rt_criar",
    "diario_servidor",
    "diario_servidor_autosave",
    "diario_autosave",
    "diario_criar",
    "diario_editar_roteiro",
    "diario_servidor_editar_roteiro",
    "diario_motorista",
    "diario_servidor_motorista",
}
#: Remover/restaurar um anexo: depende de ele ser do servidor ou da equipe.
DO_ANEXO = {"prestacao_documento_delete", "prestacao_documento_restaurar"}
ROTAS = DO_SERVIDOR | DA_EQUIPE | DO_ANEXO


def equipe_finalizada(prestacao) -> bool:
    servidores = prestacao.servidores_prestacao.all()
    return servidores.exists() and not servidores.filter(finalizada=False).exists()


def _travada(nome, kwargs) -> bool:
    from .models import DiarioBordo, PrestacaoContas, PrestacaoDocumentoAnexo, PrestacaoServidor, RelatorioTecnico

    if nome in DO_ANEXO:
        anexo = PrestacaoDocumentoAnexo.todos.filter(pk=kwargs.get("anexo_pk"), prestacao_id=kwargs.get("pc_pk")).select_related("servidor_prestacao", "prestacao").first()
        if anexo is None:
            return False
        if anexo.servidor_prestacao_id:
            return anexo.servidor_prestacao.finalizada
        return equipe_finalizada(anexo.prestacao)
    if "ps_pk" in kwargs:
        ps = PrestacaoServidor.objects.filter(pk=kwargs["ps_pk"]).select_related("prestacao").first()
        if ps is None:
            return False
        return ps.finalizada if nome in DO_SERVIDOR else equipe_finalizada(ps.prestacao)
    prestacao = None
    if "pc_pk" in kwargs:
        prestacao = PrestacaoContas.objects.filter(pk=kwargs["pc_pk"]).first()
    elif nome == "rt_autosave":
        prestacao = getattr(RelatorioTecnico.objects.filter(pk=kwargs.get("pk")).select_related("prestacao").first(), "prestacao", None)
    elif nome == "diario_autosave":
        prestacao = getattr(DiarioBordo.objects.filter(pk=kwargs.get("pk")).select_related("prestacao").first(), "prestacao", None)
    return bool(prestacao) and equipe_finalizada(prestacao)


def travar_se_finalizada(view, nome):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method == "POST" and _travada(nome, kwargs):
            if "autosave" in nome or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "message": MENSAGEM, "error": MENSAGEM}, status=409)
            messages.error(request, MENSAGEM)
            return redirect(voltar_para(request, reverse("viagens_prestacoes:index")))
        return view(request, *args, **kwargs)

    return wrapper
