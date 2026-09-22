"""Traz as atividades do Plano de Trabalho para os serviços da solicitação.

As duas listas dizem a mesma coisa com grafias diferentes ("Confecção da
carteira de identidade nacional (CIN)" x "Confecção da Carteira de Identidade
Nacional (CIN)"), e o que é oferecido no evento nasce no Plano de Trabalho.
Aqui o Plano de Trabalho manda: o serviço correspondente passa a ter a grafia
de lá — sem perder o vínculo com as solicitações já feitas, porque o registro
é o mesmo — e o que só existe no PT é criado.

Serviço que não tem correspondente no PT permanece e é apenas relatado: pode
estar em uso numa solicitação antiga.

No VPS as atividades vieram do GV TODAS EM MAIÚSCULAS. Nome de serviço é
texto de tela, não grito: nome inteiro em maiúsculas vira frase normal, com
as siglas preservadas (CIN, NOC).

    python manage.py sincronizar_servicos_pt [--commit]
"""

import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db import transaction

from cadastros.models import Servico
from viagens_planos.models import AtividadePlanoTrabalho


def chave(texto):
    """Nome comparável: sem acento, sem pontuação, minúsculo."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto).split())


def _combina(chave_pt, chave_servico):
    """Mesma coisa dita de dois jeitos: igual ou um contendo o outro inteiro."""
    if chave_pt == chave_servico:
        return True
    maior, menor = sorted((chave_pt, chave_servico), key=len, reverse=True)
    return f" {menor} " in f" {maior} "


SIGLAS = {"CIN", "NOC", "PCPR", "PC", "BO", "CNH", "ASCOM", "DP", "SESP"}


def nome_apresentavel(nome):
    """"UNIDADE MÓVEL (ÔNIBUS)" -> "Unidade móvel (ônibus)"; o resto passa igual."""
    if any(c.islower() for c in nome):
        return nome
    palavras = []
    for palavra in nome.split(" "):
        nu = palavra.strip("()").strip(".,;:")
        if nu in SIGLAS:
            palavras.append(palavra)
        else:
            palavras.append(palavra.lower())
    texto = " ".join(palavras)
    for i, c in enumerate(texto):
        if c.isalpha():
            return texto[:i] + c.upper() + texto[i + 1:]
    return texto


class Command(BaseCommand):
    help = "Sincroniza os serviços da solicitação com as atividades do Plano de Trabalho."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit", action="store_true",
            help="Grava. Sem isso, apenas relata o que faria.",
        )

    def handle(self, commit, **_opcoes):
        servicos = list(Servico.objects.all())
        restantes = {s.pk: s for s in servicos}
        renomeados, criados, iguais = [], [], 0

        for atividade in AtividadePlanoTrabalho.objects.order_by("nome"):
            nome_pt = nome_apresentavel(atividade.nome)
            alvo = chave(nome_pt)
            achado = next(
                (s for s in servicos if s.pk in restantes and _combina(alvo, chave(s.nome))),
                None,
            )
            if achado is None:
                criados.append(nome_pt)
                continue
            restantes.pop(achado.pk)
            if achado.nome != nome_pt:
                renomeados.append((achado.nome, nome_pt, achado))
            else:
                iguais += 1

        if commit:
            with transaction.atomic():
                for _antes, depois, servico in renomeados:
                    servico.nome = depois
                    servico.save(update_fields=["nome", "atualizado_em"])
                for nome in criados:
                    Servico.objects.create(nome=nome)

        for antes, depois, _servico in renomeados:
            self.stdout.write(f"renomeado: {antes} → {depois}")
        for nome in criados:
            self.stdout.write(self.style.SUCCESS(f"criado: {nome}"))
        for servico in restantes.values():
            self.stdout.write(
                self.style.WARNING(f"sem atividade no PT (mantido): {servico.nome}")
            )
        self.stdout.write(
            f"{iguais} já iguais, {len(renomeados)} renomeados, {len(criados)} criados, "
            f"{len(restantes)} sem correspondência."
        )
        if not commit:
            self.stdout.write(self.style.WARNING("Ensaio: nada foi gravado (use --commit)."))
