"""Gera a régua inicial; não substitui nem sobrescreve provas visuais."""

import json
from collections import Counter
from pathlib import Path


PASTA = Path(__file__).resolve().parents[1] / "docs" / "paridade"


def correspondencia(app, nome):
    alvo, params = None, {}
    motivo = "Correspondência técnica; conteúdo, estados e comportamento ainda aguardam comparação visual."
    if app == "cadastros":
        if nome == "index":
            alvo = "viagens_cadastros:index"
        elif nome in {"configuracao", "configuracao_aba"}:
            alvo = "viagens_oficios:institucional"
            motivo = "Formulário genérico, sem as abas da origem; assinantes em catálogo separado. PT/OS na tela de origem: decisão de escopo pendente."
        elif nome.startswith("estado"):
            motivo = "Não há CRUD público de estados. O admin não substitui esta tela."
        elif nome == "api_consulta_cep":
            motivo = "Não existe endpoint de consulta de CEP na configuração institucional."
        elif nome.startswith("cidade"):
            if nome == "cidades_export_csv":
                motivo = "Exportação CSV de cidades não localizada."
            else:
                alvo = "cadastros:novo" if nome == "cidade_create" else "cadastros:lista"
                params = {"slug": "municipios"}
                motivo = "Cadastro correspondente, mas restrito ao administrador de Eventos. Permissão, campos, inclusão rápida e mensagens ainda divergem."
        else:
            tipos = {"unidade": "unidades", "cargo": "cargos", "combustiv": "combustiveis", "servidor": "servidores", "viatura": "viaturas"}
            tipo = next(k for k in tipos if nome.startswith(k))
            acao = "lista" if nome.endswith("_index") else "novo" if nome.endswith("_create") else "excluir" if nome.endswith("_delete") else "editar"
            alvo, params = "viagens_cadastros:" + acao, {"slug": tipos[tipo]}
            motivo = "Lista/formulário genéricos; conferir composição, campos, busca, paginação, ações e mensagens."
            if nome.endswith("_set_default"):
                motivo = "Padrão pode ser alterado no formulário; falta a ação direta da listagem com o contrato da origem."
    elif app == "roteiros":
        nomes = {"index": "lista", "novo": "novo", "roteiro-autosave-create": "autosave_novo", "calcular_diarias": "previa_diarias", "trechos_estimar": "estimar_trecho", "calcular_rota": "calcular_rota", "calcular_rota_preview": "calcular_rota", "roteiro-autosave": "autosave", "editar": "editar", "excluir": "excluir"}
        if nome in nomes:
            alvo = "viagens_roteiros:" + nomes[nome]
            motivo = "F2 tem composição específica e caracterização. Preservar o que está certo; fidelidade visual ainda não certificada nesta tarefa."
        else:
            motivo = "Não há API de cidades por estado; o destino usa opções locais dependentes. Conferir equivalência do comportamento."
    elif app == "oficios":
        if "ordem_servico" in nome:
            return None, {}, "Geração/prévia de ordem de serviço: fora do escopo expresso do pedido. Pontos de entrada em telas mistas ainda dependem de decisão.", True
        if "modelo" in nome:
            acao = "catalogo" if nome.endswith("_index") else "catalogo_novo" if nome.endswith("_create") else "catalogo_editar"
            alvo, params = "viagens_oficios:" + acao, {"tipo": "motivos"}
            motivo = "Catálogo genérico; inclusão rápida, padrão, exclusão, estados e textos precisam de paridade."
        elif nome in {"index", "novo", "detalhe", "editar"}:
            alvo = "viagens_oficios:" + {"index": "lista"}.get(nome, nome)
            motivo = "Tabela/formulário genéricos; faltam composição em cartões e blocos próprios das etapas."
        elif nome in {"excluir", "cancelar", "retificar", "marcar_complementar"}:
            alvo, params = "viagens_oficios:acao", {"acao": "complementar" if nome == "marcar_complementar" else nome}
            motivo = "Ação de domínio existe; conferir posição, confirmação, permissão e mensagens."
        elif nome in {"dados_viajantes", "transporte", "wizard_roteiro", "wizard_justificativa"}:
            alvo = "viagens_oficios:editar"
            motivo = "Campos concentrados no formulário genérico; a etapa dedicada e seus comportamentos não estão reproduzidos."
        elif nome in {"wizard_resumo", "wizard_documentos"}:
            alvo = "viagens_oficios:editar"
            motivo = "Detalhe reúne informações/documentos; não reproduz conferência e resumo como etapas próprias."
        elif nome in {"baixar_documento", "baixar_justificativa_documento"}:
            alvo, params = "viagens_oficios:gerar", {"tipo": "justificativa" if "justificativa" in nome else "oficio"}
            motivo = "Núcleo de geração existe, com entrada POST. Conferir contrato de download, nova aba, disponibilidade e erros."
        elif nome in {"oficio_pdf_inline", "justificativa_pdf_inline"}:
            alvo = "viagens_oficios:preview_artefato"
            motivo = "Prévia por UUID de artefato; falta entrada por ofício/tipo com os mesmos estados."
        else:
            motivo = "Endpoint não localizado; permanece pendência da Meta 3: " + nome + "."
    elif app == "justificativas":
        if nome.startswith("legacy_"):
            motivo = "Alias legado a decidir; há dois padrões de exclusão idênticos na origem e o último fica sombreado. Não corrigir nem dispensar sem autorização."
        elif nome in {"index", "api_buscar_oficios", "justificativa_delete"}:
            motivo = "Tela/endpoint de justificativas aplicadas ausente; existem apenas campo no ofício e catálogo de modelos."
        else:
            acao = "catalogo" if nome == "modelos_index" else "catalogo_novo" if nome == "modelo_create" else "catalogo_editar"
            alvo, params = "viagens_oficios:" + acao, {"tipo": "justificativas"}
            motivo = "Catálogo genérico sem comprovação de inclusão rápida, padrão, confirmação e mensagens iguais."
    elif app == "termos":
        nomes = {"index": "lista", "novo": "novo", "editar": "editar", "excluir": "acao", "termo_cadastro_downloads": "detalhe", "termo_cadastro_pdf_inline": "preview", "termo_cadastro_generico_pdf_inline": "preview", "termo_cadastro_viatura_pdf_inline": "preview", "termo_cadastro_servidor_pdf_inline": "preview_servidor", "baixar_termo_cadastro_pdf": "lote", "baixar_termo_cadastro_docx": "lote", "baixar_termo_cadastro_viatura": "lote", "baixar_termo_cadastro_generico": "lote", "baixar_termo_cadastro_servidor": "gerar"}
        oficios = {"preview_termo_oficio": "detalhe", "termo_servidor_pdf_inline": "preview_artefato", "baixar_termo_servidor": "termo", "baixar_termos_todos_pdf": "termos_lote", "baixar_termo_lote_zip": "termos_lote"}
        if nome in nomes:
            alvo = "viagens_termos:" + nomes[nome]
            if nome == "excluir":
                params = {"acao": "excluir"}
            motivo = "Correspondência parcial: formulário/lista genéricos, prévia HTML e modos/lotes sem prova de equivalência ao PDF e à composição da origem."
        elif nome in oficios:
            alvo = "viagens_oficios:" + oficios[nome]
            motivo = "Fluxo relacionado disponível no ofício; conferir prévia por servidor, modos, PDF consolidado versus ZIP, nomes e estados."
        elif "assinado_anexar" in nome:
            alvo = "viagens_oficios:assinatura_artefato"
            motivo = "Anexação por UUID disponível; faltam pontos de entrada por termo/ofício, servidor e modalidade."
        elif nome == "api_buscar_oficios":
            motivo = "Busca remota de ofícios para o cadastro de termos não localizada."
        else:
            raise ValueError(nome)
    elif app == "prestacoes_contas":
        if nome == "card_menus":
            motivo = "Menu contextual por cartão e seu endpoint não existem no destino."
        else:
            namespace = "viagens_assinaturas" if nome in {"assinatura_landing", "assinatura_concluido", "assinatura_identidade", "assinatura_assinar", "assinatura_pdf_origem"} else "viagens_prestacoes"
            alvo = namespace + ":" + nome
            motivo = "Endpoint portado na F5. Templates, cartões, estados, ações e mensagens ainda exigem prova visual; testes de domínio não certificam a tela."
    else:
        raise ValueError(app)
    return alvo, params, motivo, False


def main():
    origem = json.loads((PASTA / "rotas-origem.json").read_text(encoding="utf-8"))
    destino = {r["nome"]: r for r in json.loads((PASTA / "rotas-destino.json").read_text(encoding="utf-8"))}
    saida = PASTA / "mapeamento.json"
    if saida.exists() and any(r.get("prova_visual") or r.get("observacao_visual") for r in json.loads(saida.read_text(encoding="utf-8"))):
        raise SystemExit("O inventário já tem provas; atualize-o preservando a revisão manual.")
    registros = []
    for app, pacote in origem.items():
        for rota in pacote["rotas"]:
            alvo, params, motivo, fora = correspondencia(app, rota["nome"])
            if alvo and alvo not in destino:
                raise ValueError(f"Rota destino inexistente: {alvo}")
            registros.append({
                "id": app + ":" + rota["nome"], "origem": "/" + app.replace("_", "-") + "/" + rota["padrao"],
                "arquivo_origem": pacote["arquivo"], "linha_origem": rota["linha"], "callback_origem": rota["callback"],
                "destino": alvo, "padrao_destino": destino[alvo]["padrao"] if alvo else None, "parametros": params,
                "situacao": "fora de escopo" if fora else "existe e está incompleta" if alvo else "não existe",
                "motivo": motivo, "prova_visual": None,
            })
    saida.write_text(json.dumps(registros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(len(registros), dict(Counter(r["situacao"] for r in registros)))


if __name__ == "__main__":
    main()
