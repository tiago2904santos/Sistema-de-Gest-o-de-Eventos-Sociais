---
name: research-technical
description: Pesquisa técnica com fonte: documentação oficial atual, mudanças de versão, vulnerabilidades, decisões de tecnologia. (Também é a skill 'technical-research' da missão.)
---

# research-technical

Pesquisa técnica com fonte: documentação oficial atual, mudanças de versão, vulnerabilidades, decisões de tecnologia. (Também é a skill 'technical-research' da missão.)

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Primeiro o que já está instalado: leia o código/docstring da versão exata (`.venv/lib/python3.14/site-packages/<pacote>`, `node_modules/<pacote>`) — é a fonte mais fiel da API em uso.
2. Depois documentação oficial atual: Context7 (quando conectado; ver manual-connections) ou `WebFetch` na doc oficial da versão (docs.djangoproject.com/en/6.1/, playwright.dev, developer.mozilla.org, w3.org/WAI).
3. `WebSearch` só para: mudança recente, vulnerabilidade, comparação de alternativas, erro obscuro.
4. Registrar a resposta com link e versão; decisões viram entrada em `docs/agent/memory/decisions.md`.

## Saída

Resposta curta + fontes (URL/arquivo:linha + versão). Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

"Django 6.1 tem template partials?" → ler `django/template/defaulttags.py`/docs 6.1 → sim, `{% partialdef %}` → citar.

## Se falhar

Sem rede (egress bloqueado) → use só o código instalado e diga que a doc externa não foi consultada.

## Pronto quando

Nenhuma afirmação de API sem fonte verificável.
