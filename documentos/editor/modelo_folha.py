"""A folha da tela de modelos (m057): o documento de um tipo montado como sai
de verdade — cabeçalho, brasão, tabelas, layout —, com cada bloco do modelo
(documentos/editor/blocos.py) editável no lugar.

A folha sai do documento mais recente do tipo que quem administra vê; sem
nenhum que se possa montar, de um exemplo sintético, com nomes que dizem ser
de exemplo. Os blocos entram na folha como marcas (caracteres de uso
privado, que o escape não toca e os filtros de texto não mudam) e, depois de
montada, cada marca vira o trecho editável: o texto do modelo, com os campos
automáticos como etiquetas. Assim vale igual para os templates de Viagens
(`{% bloco %}`, `{% texto_modelo %}`) e para os do Coffee Break (`b.chave`),
sem mexer neles. O que não é bloco (dados, tabelas) aparece como sai, sem
edição.

O Coffee Break registra como monta as suas folhas em `MONTADORES`.
"""

from __future__ import annotations

import logging
import re

from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from documentos.editor.blocos import blocos_do_tipo
from documentos.services import modelos_texto
from documentos.services.types import DocumentoTipo

logger = logging.getLogger(__name__)

MARCA = re.compile("(\\d+)")

# Valor do tipo → função(tipo, usuario, marcas) que devolve {"html", "origem",
# "sintetico"}. Os tipos de Viagens usam `_montar_viagens`.
MONTADORES = {}

# Só na folha da tela de modelos: onde se escreve, as etiquetas dos campos e
# o indicador de texto personalizado.
CSS_DA_FOLHA = """
[data-mod-bloco] { outline: 1px dashed transparent; outline-offset: 2px; border-radius: 2px; cursor: text;
  transition: outline-color .15s, background-color .15s; }
[data-mod-bloco]:hover { outline-color: rgba(37, 99, 235, .55); background-color: rgba(37, 99, 235, .04); }
[data-mod-bloco]:focus { outline: 2px solid #2563eb; background-color: rgba(37, 99, 235, .06); }
[data-mod-bloco]:empty::before { content: attr(data-mod-rotulo) " (vazio: volta ao texto padrão do sistema)"; color: #9ca3af; font-style: italic; }
.mod-chip { display: inline-block; padding: 0 .35em; margin: 0 .08em; border: 1px solid #c7d2fe; border-radius: 4px;
  background: #e0e7ff; color: #1e3a8a; font-size: .92em; line-height: 1.25; white-space: nowrap; cursor: default;
  user-select: all; -webkit-user-select: all; text-indent: 0; }
.mod-chip--negrito { font-weight: 700; }
.mod-indicador { position: absolute; z-index: 50; width: 16px; height: 16px; padding: 0; border: 2px solid #fff;
  border-radius: 50%; background: #d97706; box-shadow: 0 1px 3px rgba(0, 0, 0, .35); cursor: pointer; }
.mod-indicador:hover, .mod-indicador:focus { background: #b45309; outline: 2px solid #2563eb; }
"""


def _valor(tipo) -> str:
    return str(getattr(tipo, "value", tipo))


def html_editavel(bloco, texto: str) -> str:
    """O texto do bloco para editar: escapado, quebras em <br> e cada campo
    que o bloco aceita como etiqueta não editável com o nome legível. Um
    marcador que o bloco não aceita fica como texto, à vista."""
    campos = {c["chave"]: c for c in modelos_texto.campos_do_bloco(bloco)}
    partes, inicio = [], 0

    def texto_puro(trecho):
        return "<br>".join(str(escape(linha)) for linha in trecho.split("\n"))

    for achado in modelos_texto.MARCADOR.finditer(texto or ""):
        partes.append(texto_puro(texto[inicio:achado.start()]))
        inicio = achado.end()
        campo = campos.get(achado.group(1))
        if campo is None:
            partes.append(texto_puro(achado.group(0)))
            continue
        partes.append(str(format_html(
            '<span class="mod-chip{}" contenteditable="false" data-mod-campo="{}" title="{}">{}</span>',
            " mod-chip--negrito" if campo["negrito"] else "", campo["chave"], campo["rotulo"], campo["nome"],
        )))
    partes.append(texto_puro((texto or "")[inicio:]))
    return mark_safe("".join(partes))


def trecho_editavel(bloco, texto: str, alterado: bool, elemento: str = "span") -> str:
    return format_html(
        '<{} class="mod-bloco" data-mod-bloco="{}" data-mod-rotulo="{}"{} contenteditable="true" spellcheck="true">{}</{}>',
        elemento, bloco.chave, bloco.rotulo, mark_safe(' data-mod-alterado="1"') if alterado else "",
        html_editavel(bloco, texto), elemento,
    )


def folha(tipo, usuario) -> dict:
    """A folha do tipo, com os blocos editáveis: `html`, `origem` (de que
    documento ou exemplo ela foi montada), `sintetico` e `na_folha` (as
    chaves dos blocos que aparecem nela)."""
    blocos = blocos_do_tipo(tipo)
    chaves = list(blocos)
    marcas = {chave: f"{indice}" for indice, chave in enumerate(chaves)}
    montar = MONTADORES.get(_valor(tipo), _montar_viagens)
    resultado = dict(montar(tipo, usuario, marcas))
    vigentes = modelos_texto.textos_vigentes(tipo)
    textos = {chave: vigentes.get(chave, bloco.padrao) for chave, bloco in blocos.items()}
    na_folha = []

    def no_corpo(achado):
        chave = chaves[int(achado.group(1))]
        if chave not in na_folha:
            na_folha.append(chave)
        return trecho_editavel(blocos[chave], textos[chave], chave in vigentes)

    def na_cabeca(achado):  # o <title>: só o texto
        return str(escape(textos[chaves[int(achado.group(1))]]))

    html = resultado["html"]
    corte = html.find("<body")
    cabeca, corpo = (html[:corte], html[corte:]) if corte >= 0 else ("", html)
    html = MARCA.sub(na_cabeca, cabeca) + MARCA.sub(no_corpo, corpo)
    html = html.replace("</head>", f"<style>{CSS_DA_FOLHA}</style></head>", 1)
    resultado.update(html=html, na_folha=na_folha)
    return resultado


# ---- Viagens --------------------------------------------------------------


def _montar_com_marcas(tipo, contexto, marcas) -> str:
    """A folha de Viagens a partir do contexto do documento, com as marcas no
    lugar do texto de cada bloco e sem as marcações dos editores."""
    from documentos.services.pdf_renderer import renderizar_html

    contexto = dict(contexto, campos_editaveis={}, edicao=False, versao_editada=None, quebras=set())
    blocos = dict(contexto.get("blocos") or {})
    for chave, marca in marcas.items():
        blocos[chave] = {"conteudo": marca, "padrao": marca, "editado": False}
    contexto["blocos"] = blocos
    return renderizar_html(tipo, contexto, modo="editor")


def _recentes(modelo, **filtros):
    return modelo.objects.filter(**filtros).order_by("-atualizado_em", "-pk")[:3]


def _candidatos(tipo):
    """Os documentos mais recentes do tipo: (chave do vínculo, pk, variante)."""
    from viagens_oficios.models import Justificativa, Oficio
    from viagens_ordens.models import OrdemServico
    from viagens_planos.models import PlanoTrabalho
    from viagens_prestacoes.models import DiarioBordo, PrestacaoServidor, RelatorioTecnico
    from viagens_termos.models import TermoAutorizacao

    if tipo == DocumentoTipo.OFICIO:
        return [("oficio", o.pk, "") for o in _recentes(Oficio, cancelado=False)]
    if tipo == DocumentoTipo.JUSTIFICATIVA:
        return [("justificativa", j.oficio_id, "") for j in _recentes(Justificativa, oficio__cancelado=False)]
    if tipo == DocumentoTipo.TERMO_AUTORIZACAO:
        return [("termo_autorizacao", t.pk, "") for t in _recentes(TermoAutorizacao, cancelado=False)]
    if tipo == DocumentoTipo.ORDEM_SERVICO:
        return [("ordem_servico", o.pk, "") for o in _recentes(OrdemServico, cancelado=False)]
    if tipo == DocumentoTipo.PLANO_TRABALHO:
        return [("plano_trabalho", p.pk, "") for p in _recentes(PlanoTrabalho, cancelado=False)]
    if tipo in (DocumentoTipo.RELATORIO_TECNICO, DocumentoTipo.DIARIO_BORDO):
        modelo = RelatorioTecnico if tipo == DocumentoTipo.RELATORIO_TECNICO else DiarioBordo
        candidatos = []
        for registro in _recentes(modelo, prestacao__oficio__cancelado=False):
            ps = PrestacaoServidor.objects.filter(prestacao_id=registro.prestacao_id).order_by("pk").first()
            if ps is not None:
                candidatos.append((_valor(tipo), ps.pk, ""))
        return candidatos
    return []


def _montar_viagens(tipo, usuario, marcas) -> dict:
    from documentos.editor.vinculos import VINCULOS

    for chave, pk, variante in _candidatos(tipo):
        vinculo = VINCULOS.get(chave)
        if vinculo is None or not vinculo.pode_ver(usuario):
            break
        try:
            objeto = vinculo.carregar(pk, variante)
            html = _montar_com_marcas(tipo, vinculo.contexto(objeto, modo="editor", campos_editaveis={}), marcas)
        except Exception:  # documento incompleto não impede a tela: tenta o próximo, ou o exemplo
            logger.warning("Folha do modelo %s: %s %s não montou", _valor(tipo), chave, pk, exc_info=True)
            continue
        subtitulo = vinculo.subtitulo(objeto)
        origem = vinculo.rotulo(objeto) + (f" · {subtitulo}" if subtitulo else "")
        return {"html": html, "origem": origem, "sintetico": False}
    from documentos.services.document_context import contexto_de_payload

    payload, tx = exemplo_de_viagens(tipo)
    contexto = contexto_de_payload(tipo, payload, tx, modo="editor", edicao=False)
    return {"html": _montar_com_marcas(tipo, contexto, marcas), "origem": "Exemplo com dados fictícios", "sintetico": True}


_UNIDADE = "UNIDADE DE EXEMPLO"
_RODAPE = {"unidade_rodape": "Unidade de Exemplo", "endereco": "Rua de Exemplo, 100 - Cidade Exemplo/PR",
           "telefone": "(41) 0000-0000", "email": "exemplo@exemplo.pr.gov.br"}


def exemplo_de_viagens(tipo) -> tuple[dict, dict]:
    """(payload, textos) de um documento de exemplo, sem banco: nomes que
    dizem ser de exemplo."""
    if tipo == DocumentoTipo.OFICIO:
        tx = {
            "oficio": "000/2026", "assunto_oficio": "(Autorização)", "assunto_linha": "Solicitação de autorização e concessão de diárias.",
            "assunto_termo": "autorização", "data_do_oficio": "01/01/2026", "unidade": "UNIDADE DE EXEMPLO",
            "orgao_destino": "Órgão de destino de exemplo", "protocolo": "00.000.000-0",
            "col_servidor": "SERVIDOR DE EXEMPLO UM\nSERVIDOR DE EXEMPLO DOIS", "col_rgcpf": "000.000.000-00\n000.000.000-00",
            "col_cargo": "Cargo de exemplo\nCargo de exemplo", "col_solicitacao": "1\n2", "destinos_bloco": "Cidade Exemplo/PR",
            "diarias_x": "1 x 100%", "diaria": "R$ 0,00 (valor de exemplo)",
            "col_ida_saida": "Saída Sede Exemplo/PR: 01/01/2026 08:00", "col_ida_chegada": "Chegada Cidade Exemplo/PR: 01/01/2026 12:00",
            "col_volta_saida": "Saída Cidade Exemplo/PR: 02/01/2026 15:00", "col_volta_chegada": "Chegada Sede Exemplo/PR: 02/01/2026 19:00",
            "viatura": "Viatura de exemplo", "placa": "EXE-0000", "motorista_formatado": "MOTORISTA DE EXEMPLO",
            "combustivel": "Gasolina", "tipo_viatura": "Caracterizada", "armamento": "Não",
            "custo": "( X ) UNIDADE - DPC (diárias e combustível custeados pela DPC).\n(   ) OUTRA INSTITUIÇÃO\n(   ) ÔNUS LIMITADOS AOS PRÓPRIOS VENCIMENTOS",
            "motivo": "Motivo de exemplo da viagem.", "nome_chefia": "CHEFIA DE EXEMPLO", "cargo_chefia": "Cargo da chefia de exemplo",
            "unidade_cabecalho": _UNIDADE, "nome_destinatario": "DESTINATÁRIO DE EXEMPLO", "cargo_destinatario": "Cargo de exemplo",
            "equipe": [
                {"nome": "SERVIDOR DE EXEMPLO UM", "cpf": "000.000.000-00", "cargo": "Cargo de exemplo", "solicitacao": "1"},
                {"nome": "SERVIDOR DE EXEMPLO DOIS", "cpf": "000.000.000-00", "cargo": "Cargo de exemplo", "solicitacao": "2"},
            ],
            **_RODAPE,
        }
        payload = {"institucional": {"cidade_endereco": "Cidade Exemplo"},
                   "oficio": {"numero_formatado": "000/2026", "motivo": tx["motivo"]}, "justificativa": {"exigida": False}}
        return payload, tx
    if tipo == DocumentoTipo.TERMO_AUTORIZACAO:
        return {"termo": {"variante": "completo_com_viatura"}}, {
            "unidade": _UNIDADE, "unidade_rodape": "Unidade de Exemplo - Rua de Exemplo, 100 - Cidade Exemplo/PR",
            "nome_servidor": "SERVIDOR DE EXEMPLO", "cpf_servidor": "000.000.000-00", "telefone": "(41) 00000-0000",
            "lotacao": "Unidade de exemplo", "data_do_evento": "no dia 1º de janeiro de 2026", "destino": "Cidade Exemplo/PR",
            "viatura": "Viatura de exemplo", "placa": "EXE-0000", "combustivel": "Gasolina",
        }
    if tipo == DocumentoTipo.JUSTIFICATIVA:
        return {}, {
            "unidade": _UNIDADE, "unidade_rodape": _RODAPE["unidade_rodape"], "sede": "Cidade Exemplo",
            "data_extenso": "1º de janeiro de 2026", "justificativa": "Texto de exemplo da justificativa.\n\nSegundo parágrafo de exemplo.",
            "assinante_justificativa": "CHEFIA DE EXEMPLO", "cargo_assinante_justificativa": "Cargo da chefia de exemplo",
        }
    if tipo == DocumentoTipo.ORDEM_SERVICO:
        return {}, {
            "ordem_de_servico": "000/2026", "unidade_abreviado": "EXEMPLO", "unidade": _UNIDADE, **_RODAPE,
            "nome_chefia": "CHEFIA DE EXEMPLO", "cargo_chefia": "Cargo da chefia de exemplo",
            "equipe_deslocamento": "dos servidores de exemplo", "destino": "Cidade Exemplo/PR",
            "data_extenso": "no dia 1º de janeiro de 2026", "motivo": "Motivo de exemplo", "tipo_necessidade": "PADRAO",
            "referencia": "Diligências", "determinacao": "O deslocamento da equipe abaixo relacionada:",
            "competencias_equipe": [], "justificativas": [], "finalidade": "Finalidade de exemplo.",
            "sede": "Cidade Exemplo", "data_atual_extenso": "1º de janeiro de 2026",
        }
    if tipo == DocumentoTipo.PLANO_TRABALHO:
        return {}, {
            "numero_plano_trabalho": "00/2026/EXEMPLO", "unidade": _UNIDADE, **_RODAPE,
            "contextualizacao": "Contextualização de exemplo.", "metas": "• Meta de exemplo", "atividades": "• Atividade de exemplo",
            "recursos_necessarios": "• Recurso de exemplo", "data_evento": "dia 1º de janeiro de 2026", "destinos": "Cidade Exemplo/PR",
            "horario_de_atendimento": "09:00 até 17:00", "efetivos": "2 servidores de exemplo", "unidade_movel": "",
            "valor_do_plano": "Valor total: R$ 0,00 (valor de exemplo).", "valor_blocos": [],
            "coordenacao": "Coordenação de exemplo.", "consideracao_final": "Considerações de exemplo.", "sede": "Cidade Exemplo",
            "data_extenso": "1º de janeiro de 2026", "nome_chefia": "CHEFIA DE EXEMPLO", "cargo_chefia": "Cargo da chefia de exemplo",
            "is_multi_evento": False, "eventos": [],
        }
    if tipo == DocumentoTipo.RELATORIO_TECNICO:
        tx = {
            "oficio": "000/2026", "sede": "Cidade Exemplo", "data_atual_extenso": "1º de janeiro de 2026",
            "unidade_cabecalho": _UNIDADE, **_RODAPE, "nome_servidor": "SERVIDOR DE EXEMPLO", "cpf_servidor": "000.000.000-00",
            "diaria": "R$ 0,00", "translado": "Não houve", "combustivel": "", "passagem": "Não houve",
            "motivo": "Descrição de exemplo do evento.", "atividade": "Objetivo de exemplo.", "conclusao": "Conclusão de exemplo.",
            "medidas": "", "info_complementares": "",
        }
        return tx, tx
    if tipo == DocumentoTipo.DIARIO_BORDO:
        return {
            "header": {
                "divisao": "DIVISÃO DE EXEMPLO", "unidade_cabecalho": _UNIDADE, "oficio_motorista": "000", "ano": "2026",
                "protocolo_motorista": "00.000.000-0", "viatura": "Viatura de exemplo", "combustivel": "GASOLINA", "placa": "EXE0000",
                "placa_reservada": "", "motorista": "MOTORISTA DE EXEMPLO", "cpf_motorista": "000.000.000-00",
            },
            "trechos": [{
                "data_saida": "01/01/2026", "hora_saida": "08:00", "km_inicial": 1000, "data_chegada": "01/01/2026",
                "hora_chegada": "12:00", "km_final": 1200, "origem": "SEDE EXEMPLO", "destino": "CIDADE EXEMPLO",
                "abastecimento": "(   ) Sim   ( X ) Não",
            }],
        }, None
    raise ValueError(f"Sem exemplo para {_valor(tipo)}")
