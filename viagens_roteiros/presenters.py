"""Como o roteiro se apresenta na lista.

Portado do Gerenciador de Viagens na Meta 2 de paridade. A origem monta a
linha num presenter próprio, e as palavras do selo temporal são as dela: é por
esse selo que se acha o roteiro de agora numa lista de roteiros reaproveitáveis.
Trazê-las aproximadas seria mudar o que o operador lê.
"""

from django.utils import timezone

from django.utils.formats import number_format


def rotulo_cidade(municipio) -> str:
    """"Curitiba/PR" — a unidade federativa distingue homônimos entre estados."""
    if not municipio:
        return "—"
    sigla = getattr(getattr(municipio, "estado", None), "sigla", "")
    return f"{municipio.nome}/{sigla}" if sigla else municipio.nome


def titulo_da_rota(roteiro) -> str:
    """Sede e destinos na ordem: é o que identifica o roteiro na lista.

    A volta à sede não entra: repetir a sede no fim só alonga o título.
    """
    sede = rotulo_cidade(roteiro.origem_municipio)
    destinos = [
        rotulo_cidade(trecho.destino_municipio)
        for trecho in roteiro.trechos.all()
        if trecho.destino_municipio_id
    ]
    if len(destinos) > 1 and destinos[-1] == sede:
        destinos = destinos[:-1]
    if destinos:
        return " → ".join([sede, *destinos])
    return sede if sede != "—" else f"Roteiro #{roteiro.pk}"


def periodo_do_roteiro(roteiro):
    """(início, fim) do deslocamento.

    O editor grava as datas nos trechos e deixa `saida_dt`/`retorno_chegada_dt`
    do roteiro vazios; sem eles, o período vem da primeira saída e da última
    chegada dos trechos (a lista já traz os trechos pré-carregados).
    """
    inicio = roteiro.saida_dt
    fim = roteiro.retorno_chegada_dt
    if not inicio or not fim:
        trechos = list(roteiro.trechos.all())
        saidas = [t.saida_dt for t in trechos if t.saida_dt]
        chegadas = [t.chegada_dt or t.saida_dt for t in trechos if t.chegada_dt or t.saida_dt]
        inicio = inicio or (min(saidas) if saidas else None)
        fim = fim or (max(chegadas) if chegadas else None)
    return inicio, fim or inicio


def selo_temporal(roteiro):
    """Quanto falta, em andamento, ou quanto tempo passou.

    Palavras e limites vêm da origem sem arredondar: "falta 1 dia" no singular,
    "começa hoje", "foi ontem". O tom acompanha os selos já existentes no
    design system daqui.
    """
    inicio, fim = periodo_do_roteiro(roteiro)
    if not inicio:
        return None, "neutro"
    hoje = timezone.localdate()
    inicio_data = timezone.localtime(inicio).date() if timezone.is_aware(inicio) else inicio.date()
    fim_data = inicio_data
    if fim:
        fim_data = timezone.localtime(fim).date() if timezone.is_aware(fim) else fim.date()
    if hoje < inicio_data:
        dias = (inicio_data - hoje).days
        return ("falta 1 dia" if dias == 1 else f"faltam {dias} dias"), "aguardando"
    if inicio_data <= hoje <= fim_data:
        return ("começa hoje" if hoje == inicio_data else "em andamento"), "em_andamento"
    dias = (hoje - fim_data).days
    if dias == 0:
        return "foi hoje", "atendido"
    if dias == 1:
        return "foi ontem", "atendido"
    return f"há {dias} dias", "atendido"


def _data_local(valor):
    if not valor:
        return None
    return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()


def periodo_display(roteiro) -> str:
    inicio, fim = periodo_do_roteiro(roteiro)
    inicio_data, fim_data = _data_local(inicio), _data_local(fim)
    if not inicio_data and not fim_data:
        return "—"
    esquerda = f"{inicio_data:%d/%m/%Y}" if inicio_data else "—"
    direita = f"{fim_data:%d/%m/%Y}" if fim_data else "—"
    return f"{esquerda} a {direita}"


def trechos_display(roteiro) -> str:
    quantidade = len(roteiro.trechos.all())
    return "1 trecho" if quantidade == 1 else f"{quantidade} trechos"


def valor_display(roteiro) -> str:
    if roteiro.valor_diarias is None:
        return "—"
    # Moeda pela localização do Django: f-string sairia com ponto decimal.
    return f"R$ {number_format(roteiro.valor_diarias, decimal_pos=2, force_grouping=True)}"


# Depois disso o "há N dias" deixa de ajudar a achar o roteiro de agora.
DIAS_CHIP_PASSADO = 45


def chip_da_lista(roteiro, selo, tom):
    """Chip ao lado da rota: o próprio selo, sumindo 45 dias após o fim.

    Cancelado continua visível — é estado, não tempo.
    """
    if not selo or roteiro.cancelado:
        return selo, tom
    _, fim = periodo_do_roteiro(roteiro)
    fim_data = _data_local(fim)
    if fim_data and (timezone.localdate() - fim_data).days > DIAS_CHIP_PASSADO:
        return None, tom
    return selo, tom


def linha_da_lista(roteiro, *, editar_url, excluir_url):
    """Tudo o que a linha da lista mostra, resolvido de uma vez."""
    selo, tom = selo_temporal(roteiro)
    if roteiro.cancelado:
        selo, tom = "Cancelado", "cancelada"
    return {
        "roteiro": roteiro,
        "titulo": titulo_da_rota(roteiro),
        "selo": selo,
        "selo_tom": tom,
        "chip": chip_da_lista(roteiro, selo, tom)[0],
        "periodo": periodo_display(roteiro),
        "trechos": trechos_display(roteiro),
        "valor": valor_display(roteiro),
        "resumo_diarias": roteiro.resumo_diarias or "",
        "servidores": roteiro.quantidade_servidores,
        "icone": "document" if roteiro.solicitacao_id else "map-pin",
        "editar_url": editar_url,
        "excluir_url": excluir_url,
    }
