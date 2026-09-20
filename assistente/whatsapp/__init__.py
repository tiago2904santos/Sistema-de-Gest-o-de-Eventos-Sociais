"""Canal WhatsApp — a porta de entrada, e nada além disso.

O orquestrador já era agnóstico de canal antes deste pacote existir: recebe
texto e devolve texto. Aqui só se traduz o formato da Cloud API para isso, o
que é o motivo de o canal ser a menor parte do trabalho — e de um segundo
canal custar quase nada.
"""
