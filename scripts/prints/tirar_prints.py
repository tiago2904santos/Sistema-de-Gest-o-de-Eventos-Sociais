"""Tira prints das telas do sistema com o Chromium do Playwright.

Serve para mostrar uma mudança a quem não está com o sistema aberto: entra
com um usuário, visita cada caminho e salva um PNG por tela.

    python scripts/prints/tirar_prints.py --base http://127.0.0.1:8021 \
        --usuario admin --senha ... --saida prints/ / /solicitacoes/ /agenda/

Sem caminhos, tira as telas principais. `--celular` usa a largura de um
telefone em vez da de um monitor.
"""

import argparse
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

TELAS_PADRAO = [
    "/",
    "/dashboard/",
    "/solicitacoes/",
    "/agenda/",
    "/coffee-break/",
    "/cadastros/",
    "/relatorios/",
]


def nome_do_arquivo(caminho: str) -> str:
    nome = re.sub(r"[^a-zA-Z0-9]+", "-", caminho).strip("-")
    return (nome or "inicio") + ".png"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("caminhos", nargs="*", default=TELAS_PADRAO)
    parser.add_argument("--base", default="http://127.0.0.1:8021")
    parser.add_argument("--usuario", default=os.environ.get("PRINTS_USUARIO"))
    parser.add_argument("--senha", default=os.environ.get("PRINTS_SENHA"))
    parser.add_argument("--saida", default="prints")
    parser.add_argument("--celular", action="store_true")
    args = parser.parse_args()

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    tela = {"width": 390, "height": 844} if args.celular else {"width": 1440, "height": 900}

    opcoes = {}
    if executavel := os.environ.get("PRINTS_CHROMIUM"):
        opcoes["executable_path"] = executavel
    # O Chromium não lê HTTPS_PROXY sozinho; sem isso, prints de fora da
    # máquina (o VPS) falham em ambientes que só saem pelo proxy.
    if proxy := os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        opcoes["proxy"] = {"server": proxy, "bypass": "localhost,127.0.0.1"}
    if argumentos := os.environ.get("PRINTS_CHROMIUM_ARGS"):
        opcoes["args"] = argumentos.split()

    with sync_playwright() as p:
        navegador = p.chromium.launch(**opcoes)
        pagina = navegador.new_page(viewport=tela, locale="pt-BR")

        if args.usuario:
            pagina.goto(f"{args.base}/conta/entrar/")
            pagina.fill("#id_username", args.usuario)
            pagina.fill("#id_password", args.senha or "")
            pagina.click("button[type=submit]")
            pagina.wait_for_load_state("networkidle")

        for caminho in args.caminhos:
            resposta = pagina.goto(args.base + caminho)
            pagina.wait_for_load_state("networkidle")
            arquivo = saida / nome_do_arquivo(caminho)
            pagina.screenshot(path=str(arquivo), full_page=True)
            status = resposta.status if resposta else "?"
            print(f"{status}  {caminho}  ->  {arquivo}")

        navegador.close()


if __name__ == "__main__":
    main()
