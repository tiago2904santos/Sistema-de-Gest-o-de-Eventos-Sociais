import unicodedata

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from viagens_cadastros.models import AssinaturaConfiguracao, ConfiguracaoSistema, Servidor, Unidade, setor_de_viagens
from viagens_cadastros.permissions import acesso_ao_modulo, eh_gestor_viagens, pode_editar_cadastros  # noqa: F401
from .view_helpers import campos_v32

ConfiguracaoForm = forms.modelform_factory(ConfiguracaoSistema, exclude=['chave', 'setor', 'sede', 'cidade_sede_padrao', 'nome_chefia', 'cargo_chefia', 'legado_origem', 'legado_pk'])


class ConfiguracaoInstitucionalForm(ConfiguracaoForm):
    """Tudo o que os documentos puxam da instituição, incluindo quem assina.

    A instância é a configuração do setor de quem edita. Os assinantes não são
    do setor: ficam na configuração global e valem para todos. Os documentos só
    leem o primeiro assinante ativo de cada tipo
    (`docxtpl_context._assinatura_nome_cargo`), então o assinante é um campo
    por documento em vez de uma lista ordenada.
    """
    assina_oficio = forms.ModelChoiceField(Servidor.objects.none(), required=False, label='Assina os ofícios')
    assina_justificativa = forms.ModelChoiceField(Servidor.objects.none(), required=False, label='Assina as justificativas')

    ASSINANTES = {'assina_oficio': AssinaturaConfiguracao.OFICIO, 'assina_justificativa': AssinaturaConfiguracao.JUSTIFICATIVA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servidores = Servidor.objects.select_related('cargo').order_by('nome')
        for campo, tipo in self.ASSINANTES.items():
            self.fields[campo].queryset = servidores
            atual = self._assinante_ativo(tipo)
            if not self.is_bound and atual:
                self.initial[campo] = atual.servidor_id
        self.fields['destinatario_oficio'].queryset = servidores
        self.fields['unidade'].queryset = Unidade.objects.order_by('nome')

    def _assinante_ativo(self, tipo):
        return ConfiguracaoSistema.get_singleton().assinaturas.filter(tipo=tipo, ativo=True).order_by('ordem').first()

    @transaction.atomic
    def save(self, commit=True):
        # A sede não é escolhida: é o município da cidade e UF do endereço (vindos do CEP).
        self.instance.cidade_sede_padrao = municipio_do_endereco(self.cleaned_data.get('cidade_endereco'), self.cleaned_data.get('uf'))
        configuracao = super().save(commit=commit)
        if commit:
            for campo, tipo in self.ASSINANTES.items():
                self._gravar_assinante(tipo, self.cleaned_data.get(campo))
        return configuracao

    def _gravar_assinante(self, tipo, servidor):
        global_ = ConfiguracaoSistema.get_singleton()
        ativos = list(global_.assinaturas.filter(tipo=tipo, ativo=True).order_by('ordem'))
        if servidor is None:
            # Sem assinante o documento sai sem nome: desativa, sem apagar o histórico.
            for linha in ativos:
                linha.ativo = False
                linha.save()
            return
        if ativos:
            if ativos[0].servidor_id != servidor.pk:
                ativos[0].servidor = servidor
                ativos[0].save()
            return
        ordem = (global_.assinaturas.filter(tipo=tipo).aggregate(m=Max('ordem'))['m'] or 0) + 1
        AssinaturaConfiguracao.objects.create(configuracao=global_, tipo=tipo, servidor=servidor, ordem=ordem)


# Rótulo, largura e comportamento de cada campo na tela. Tipo "text" é o input
# comum; máscara e caixa alta são ligadas por `js/viagens-cadastros.js`.
CAMPOS_DA_CONFIGURACAO = {
    'nome_orgao': {'label': 'Nome do órgão', 'placeholder': 'Ex.: POLÍCIA CIVIL DO PARANÁ', 'uppercase': True},
    'sigla_orgao': {'label': 'Sigla', 'placeholder': 'Ex.: PCPR', 'uppercase': True, 'maxlength': 20},
    'unidade': {'label': 'Unidade emissora', 'pesquisavel': True, 'placeholder': 'Buscar unidade...'},
    'cep': {'label': 'CEP', 'placeholder': '00000-000', 'inputmode': 'numeric', 'maxlength': 9, 'mascara': 'cep'},
    'logradouro': {'label': 'Logradouro', 'placeholder': 'Rua, avenida, praça...', 'uppercase': True},
    'numero': {'label': 'Número', 'uppercase': True, 'maxlength': 20},
    'bairro': {'label': 'Bairro', 'uppercase': True},
    'cidade_endereco': {'label': 'Cidade', 'uppercase': True},
    'uf': {'label': 'UF', 'placeholder': 'PR', 'uppercase': True, 'maxlength': 2},
    'telefone': {'label': 'Telefone', 'placeholder': '(41) 0000-0000', 'mascara': 'telefone', 'inputmode': 'tel', 'maxlength': 15, 'autocomplete': 'tel'},
    'ramal': {'label': 'Ramal', 'inputmode': 'numeric', 'maxlength': 20},
    'email': {'label': 'E-mail', 'tipo': 'email', 'placeholder': 'unidade@pc.pr.gov.br', 'autocomplete': 'email'},
    'destinatario_oficio': {'label': 'Servidor destinatário', 'pesquisavel': True, 'placeholder': 'Buscar servidor...', 'ajuda': ''},
    'destinatario_oficio_nome': {'label': 'Nome', 'uppercase': True},
    'destinatario_oficio_cargo': {'label': 'Cargo', 'uppercase': True},
    'destinatario_oficio_unidade': {'label': 'Unidade', 'uppercase': True},
    'assina_oficio': {'pesquisavel': True, 'placeholder': 'Buscar servidor...', 'ajuda': 'Sem assinante, o ofício sai sem nome no fim.'},
    'assina_justificativa': {'pesquisavel': True, 'placeholder': 'Buscar servidor...', 'ajuda': 'Sem assinante, a justificativa sai sem nome no fim.'},
    'prazo_justificativa_dias': {'label': 'Antecedência mínima (dias)', 'tipo': 'number', 'min': 0, 'step': 1, 'obrigatorio': True},
}


def _sem_acentos(valor):
    return unicodedata.normalize('NFKD', str(valor or '')).encode('ascii', 'ignore').decode().strip().casefold()


def municipio_do_endereco(cidade, uf):
    """Município do cadastro base com o nome e a UF do endereço, sem ligar para acentos e caixa."""
    from cadastros.models import Municipio

    alvo, sigla = _sem_acentos(cidade), str(uf or '').strip().upper()
    if not alvo or not sigla:
        return None
    for municipio in Municipio.objects.filter(estado__sigla=sigla).only('pk', 'nome'):
        if _sem_acentos(municipio.nome) == alvo:
            return municipio
    return None


def _campos_da_configuracao(form):
    campos = {}
    for campo in campos_v32(form):
        if campo['tipo'] == 'input':
            campo['tipo'] = campo.get('input_tipo') or 'text'
        campo.update(CAMPOS_DA_CONFIGURACAO.get(campo['name'], {}))
        if campo['name'] in ('assina_oficio', 'assina_justificativa', 'destinatario_oficio'):
            servidores = form.fields[campo['name']].queryset
            campo['opcoes'] = [{'valor': str(s.pk), 'rotulo': f"{s.nome} — {s.cargo.nome}" if s.cargo_id else s.nome} for s in servidores]
        if campo['name'] == 'cep' and campo['valor'] and not form.is_bound:
            campo['valor'] = form.instance.cep_formatado
        campos[campo['name']] = campo
    return campos


# Os catálogos de motivo e de modelo de justificativa são cadastros de viagens
# (Meta 3): lista, modal, "usar como padrão" e exclusão com diálogo, no padrão
# fixado pela Meta 1. As rotas antigas deste app continuam respondendo.
CATALOGOS_CADASTRO = {
    'motivos': 'motivos-oficio',
    'justificativas': 'modelos-justificativa',
}


def _catalogo_de_cadastro(request, slug, pk=None, novo=False):
    from viagens_cadastros import views as cadastros

    if request.method == 'POST':
        if request.POST.get('acao') == 'excluir' and pk:
            return cadastros.excluir(request, slug, pk)
        return cadastros.editar(request, slug, pk)
    if pk is None and not novo:
        return cadastros.lista(request, slug)
    # Novo e editar abrem a lista já com o modal (sem redirecionar): é o que
    # o contrato das rotas deste app sempre respondeu.
    cadastros._exigir_edicao(request)
    config = cadastros._config(slug)
    instancia = get_object_or_404(config['model'], pk=pk) if pk else None
    modal = cadastros._contexto_modal(slug, config, config['form'](instance=instancia), instancia)
    return cadastros._lista_catalogo(request, slug, modal)


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def catalogo(request, tipo, pk=None, novo=False):
    if tipo in CATALOGOS_CADASTRO:
        return _catalogo_de_cadastro(request, CATALOGOS_CADASTRO[tipo], pk, novo)
    if tipo != 'assinaturas':
        raise Http404
    # Os assinantes passaram a ser campos da tela de configurações.
    if not eh_gestor_viagens(request.user):
        raise PermissionDenied
    return redirect(reverse('viagens_oficios:institucional') + '#assinaturas')


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def institucional(request):
    if not eh_gestor_viagens(request.user):
        raise PermissionDenied
    # O setor vem da lotação de quem está logado; ninguém escolhe a unidade.
    setor = setor_de_viagens(request.user)
    configuracao = ConfiguracaoSistema.do_setor(setor)
    form = ConfiguracaoInstitucionalForm(request.POST or None, instance=configuracao)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Configurações salvas. Os próximos documentos já saem com os dados novos.')
        return redirect('viagens_oficios:institucional')
    titulo = 'Configurações dos documentos'
    return render(request, 'pages/viagens_oficios/configuracoes.html', {
        'titulo': titulo, 'form': form, 'campos': _campos_da_configuracao(form), 'setor': setor,
        'atualizado_em': configuracao.atualizado_em,
        'breadcrumb': [{'label': 'Ofícios', 'url': reverse('viagens_oficios:lista')}, {'label': titulo}],
        'url_voltar': reverse('viagens_oficios:lista'),
    })
