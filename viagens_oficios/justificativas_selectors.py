from .models import Justificativa, ModeloJustificativa

def get_or_none_justificativa_by_oficio(oficio):
    return Justificativa.objects.filter(oficio=oficio).select_related("modelo").first()

def listar_modelos_justificativa():
    return ModeloJustificativa.objects.filter(ativo=True).order_by("ordem", "nome")
