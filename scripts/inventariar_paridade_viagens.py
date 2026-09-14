"""Extrai o mapa de URLs sem importar nem executar código do GV.

Uso: python -X utf8 scripts/inventariar_paridade_viagens.py --origem PASTA
O JSON é uma fotografia técnica; não certifica a paridade visual.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path


APPS = ("cadastros", "roteiros", "oficios", "justificativas", "termos", "prestacoes_contas")


def extrair_rotas(caminho):
    texto = caminho.read_text(encoding="utf-8")
    tree = ast.parse(texto)
    rotas = []
    # Percorre somente listas atribuídas a urlpatterns, mantendo inclusive
    # padrões duplicados/sombreados. Não conta chamadas path fora do registro.
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "urlpatterns" for t in node.targets):
            value = node.value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "urlpatterns":
            value = node.value
        if value is None:
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            raise ValueError(f"Registro dinâmico exige inspeção manual: {caminho}:{node.lineno}")
        for call in value.elts:
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id not in {"path", "re_path"}:
                raise ValueError(f"Rota não reconhecida: {caminho}:{call.lineno}")
            nome = next(ast.literal_eval(k.value) for k in call.keywords if k.arg == "name")
            rotas.append({"nome": nome, "padrao": ast.literal_eval(call.args[0]), "callback": ast.unparse(call.args[1]), "linha": call.lineno})
    return rotas


def fotografar(origem):
    resultado = {}
    for app in APPS:
        path = origem / app / "urls.py"
        resultado[app] = {
            "arquivo": f"{app}/urls.py",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rotas": extrair_rotas(path),
        }
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origem", type=Path, required=True)
    parser.add_argument("--saida", type=Path, default=Path("docs/paridade/rotas-origem.json"))
    args = parser.parse_args()
    origem = args.origem.resolve()
    saida = args.saida.resolve()
    if saida.is_relative_to(origem):
        parser.error("A saída não pode ficar dentro do GV.")
    dados = fotografar(origem)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({app: len(dados[app]["rotas"]) for app in APPS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
