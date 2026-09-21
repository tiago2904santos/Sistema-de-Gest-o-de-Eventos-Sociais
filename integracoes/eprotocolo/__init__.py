"""Integração com o eProtocolo (Paraná) — barramento ``spi-servicos``.

Portado do Gerenciador de Viagens, com o transporte reescrito em ``urllib``:
o projeto não tem ``requests`` no ``requirements.txt`` e não é por aqui que
ele vai ganhar uma dependência — o cálculo de rota e o canal do WhatsApp já
seguem essa regra.

Camadas, de baixo para cima:

    settings.py    → leitura da configuração (``settings.EPROTOCOLO``)
    exceptions.py  → hierarquia de erros (status HTTP nunca sobe cru)
    client.py      → transporte (token, cabeçalhos, timeout, mascaramento)
    schemas.py     → caminhos dos endpoints e o resultado normalizado
    mocks.py       → respostas determinísticas para dev/teste/sem credencial
    mappers.py     → nossos documentos → payload do eProtocolo
    services.py    → uma função por operação de negócio

Quem chama de fora conversa com ``services`` — nunca com o ``client``.
"""
