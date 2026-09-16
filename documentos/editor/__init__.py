"""Editor documental: o que a prévia A4 deixa editar e como isso volta ao
model.

`campos.py` é o registro explícito — só o que está lá entra na folha marcado
e passa pela API. `vinculos.py` é a ponte com cada domínio (carregar o
objeto, o formulário que valida, quem pode editar, a versão para o controle
de concorrência). `api.py` é a view única: GET devolve o painel do campo com
os componentes globais; PATCH grava pelo formulário do domínio e responde
com a versão nova.
"""
