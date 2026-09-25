"""Leitura de documentos que chegam de fora: processos do eProtocolo e e-mails.

Tudo aqui é puro (sem banco): recebe bytes ou texto e devolve o que achou.
Quem grava são os apps (prestação de contas, termos, coffee break, demandas),
a partir do que este pacote leu. Nenhum dado sai do servidor.
"""
