from .models import ConfiguracaoSistema

def build_configuracao_context():
    # Dados do setor de quem gera; os assinantes são únicos, na configuração global.
    configuracao = ConfiguracaoSistema.atual()
    cidade_doc = configuracao.cidade_endereco or ""
    assinaturas: dict = {}
    global_ = ConfiguracaoSistema.get_singleton()
    for ass in global_.assinaturas.filter(ativo=True).select_related("servidor__cargo").order_by("tipo", "ordem"):
        assinaturas.setdefault(ass.tipo, []).append({
            "servidor": ass.servidor,
            "nome": ass.servidor.nome if ass.servidor else "",
            "ordem": ass.ordem,
        })
    # Substitutos por período (m114): o documento datado no período sai com o substituto.
    substituicoes = [
        {"tipo": s.tipo, "servidor": s.servidor, "nome": s.servidor.nome, "inicio": s.inicio, "fim": s.fim, "objeto": s}
        for s in global_.substituicoes_assinatura.filter(ativo=True).select_related("servidor__cargo").order_by("-inicio")
    ]
    return {
        "substituicoes": substituicoes,
        "nome_orgao": configuracao.nome_orgao,
        "sigla_orgao": configuracao.sigla_orgao,
        # Campo "divisão" removido do cabeçalho: mantido vazio apenas por
        # compatibilidade com placeholders/consumidores antigos.
        "divisao": "",
        "unidade": configuracao.unidade.nome if configuracao.unidade_id else "",
        "destinatario_oficio": configuracao.destinatario_oficio,
        "destinatario_oficio_nome": configuracao.destinatario_oficio_nome,
        "destinatario_oficio_cargo": configuracao.destinatario_oficio_cargo,
        "destinatario_oficio_unidade": configuracao.destinatario_oficio_unidade,
        # Compatibilidade: placeholders antigos "sede" passam a refletir cidade_endereco.
        "sede": cidade_doc,
        "nome_chefia": configuracao.nome_chefia,
        "cargo_chefia": configuracao.cargo_chefia,
        "cep": configuracao.cep,
        "cep_formatado": configuracao.cep_formatado,
        "logradouro": configuracao.logradouro,
        "numero": configuracao.numero,
        "bairro": configuracao.bairro,
        "cidade_endereco": cidade_doc,
        "uf": configuracao.uf,
        "telefone": configuracao.telefone,
        "telefone_formatado": configuracao.telefone_formatado,
        "email": configuracao.email,
        "cidade_sede_padrao": configuracao.cidade_sede_padrao,
        "prazo_justificativa_dias": configuracao.prazo_justificativa_dias,
        "assinaturas": assinaturas,
    }


def substituto_vigente(inst, tipo, data):
    """O servidor substituto que assina o documento `tipo` datado em `data`,
    ou None: a substituição ativa (do tipo, ou de todos) cujo período contém a
    data. Duas valendo ao mesmo tempo: a mais recente."""
    if data is None:
        return None
    for s in inst.get("substituicoes") or []:
        objeto = s.get("objeto")
        if objeto is not None and objeto.vale_para(tipo) and objeto.vigente_em(data):
            return s.get("servidor")
    return None
