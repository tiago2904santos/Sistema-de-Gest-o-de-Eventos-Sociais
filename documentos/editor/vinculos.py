"""Ponte entre o editor e cada domínio que tem documento editável.

Um vínculo sabe carregar o objeto, dizer quem pode editá-lo, entregar o
formulário que valida (o mesmo do cadastro — as regras de negócio moram
nele, e o editor não as duplica), montar as opções dos campos de escolha e
dar a versão que o controle de concorrência compara.
"""

from __future__ import annotations

from django.forms.models import model_to_dict

from documentos.services.types import DocumentoTipo


class VinculoOficio:
    tipo = DocumentoTipo.OFICIO

    # O que mais muda quando um campo muda — as consequências que o `save()`
    # e o `clean()` do formulário calculam a partir dele. O editor grava o
    # campo pedido e estes; nada além.
    DERIVADOS = {
        "servidores": ("servidores_termo_autorizacao", "diarias_quantidade_servidores"),
    }

    def carregar(self, pk):
        from viagens_oficios.selectors import get_oficio_by_id

        return get_oficio_by_id(pk)

    def pode_ver(self, usuario) -> bool:
        from viagens_cadastros.permissions import pode_acessar

        return pode_acessar(usuario)

    def pode_editar(self, usuario, oficio) -> bool:
        from viagens_cadastros.permissions import pode_editar_cadastros

        return pode_editar_cadastros(usuario) and not oficio.cancelado

    def versao(self, oficio) -> str:
        return oficio.atualizado_em.isoformat() if oficio.atualizado_em else ""

    def form(self, oficio, dados=None):
        from viagens_oficios.forms import OficioDocumentoForm

        return OficioDocumentoForm(dados, instance=oficio)

    def folha(self, oficio, usuario) -> str:
        """O documento no modo editor: o mesmo HTML que o iframe da prévia
        mostra, e a única montagem dele (a rota da folha também passa aqui).

        Volta junto da resposta de gravação, para a folha se atualizar sem uma
        segunda viagem ao servidor e sem o piscar de recarregar o iframe.
        """
        from documentos.editor.campos import marcacao
        from documentos.services.document_context import contexto_do_oficio
        from documentos.services.pdf_renderer import renderizar_html

        # Só quem pode editar vê os trechos marcados; o registro decide quais.
        campos = marcacao(self.tipo) if self.pode_editar(usuario, oficio) else {}
        contexto = contexto_do_oficio(oficio, modo="editor", campos_editaveis=campos)
        return renderizar_html(self.tipo, contexto, modo="editor")

    def dados_atuais(self, oficio) -> dict:
        """O ofício inteiro como o formulário o receberia: o PATCH troca só as
        partes pedidas e o resto vai como está, para as regras de `clean()`
        enxergarem o conjunto."""
        from viagens_oficios.forms import OficioDocumentoForm

        dados = model_to_dict(oficio, fields=OficioDocumentoForm.Meta.fields)
        for nome, valor in list(dados.items()):
            if isinstance(valor, list):  # muitos-para-muitos vem como instâncias
                dados[nome] = [getattr(item, "pk", item) for item in valor]
            elif valor is None:
                dados[nome] = ""
        return dados

    def gravar(self, form, nomes):
        """Persiste só os campos pedidos e os derivados deles.

        O formulário já validou e já aplicou na instância o que passou
        (`construct_instance`), inclusive o que o `save()` do domínio deriva;
        aqui vai ao banco apenas o recorte deste campo. Um dado antigo inválido
        em outro campo não muda nem trava — continua como está, e é aviso.
        """
        from django.db import transaction

        validado = form.save(commit=False)
        campos = set(nomes)
        for nome in nomes:
            campos.update(self.DERIVADOS.get(nome, ()))
        muitos = {campo.name for campo in validado._meta.many_to_many}
        simples = sorted(campos - muitos)
        # A instância validada carrega, em memória, tudo o que o formulário
        # recalculou (inclusive o que não se pede aqui). Grava-se a partir de
        # uma cópia fresca do banco, com só o recorte copiado: o que vai ao
        # banco e o que a auditoria vê são a mesma coisa.
        objeto = type(validado)._base_manager.get(pk=validado.pk)
        for nome in simples:
            setattr(objeto, nome, getattr(validado, nome))
        with transaction.atomic():
            objeto.save(update_fields=simples + ["atualizado_em"])
            for nome in sorted(campos & muitos):
                getattr(objeto, nome).set(form.cleaned_data.get(nome, []))
        return objeto

    def opcoes(self, parte, form, valor):
        """Opções de uma parte de escolha, prontas para os componentes globais."""
        if parte.nome == "servidores":
            from viagens_oficios.form_context import _opcoes_servidores

            escolhidos = {str(v) for v in (valor or [])}
            opcoes = _opcoes_servidores(form)
            for opcao in opcoes:
                opcao["selecionado"] = opcao["valor"] in escolhidos
            return opcoes
        campo = form.fields[parte.nome]
        return [{"valor": str(chave), "rotulo": str(rotulo)} for chave, rotulo in campo.choices if chave != ""]


VINCULOS = {DocumentoTipo.OFICIO: VinculoOficio()}


def vinculo_do_tipo(tipo):
    try:
        return VINCULOS.get(DocumentoTipo(tipo))
    except ValueError:
        return None
