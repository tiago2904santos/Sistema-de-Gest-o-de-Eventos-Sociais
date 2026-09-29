# Teste de paridade (legado → novo)

Para cada página/módulo migrado:

```text
comportamento atual ─▶ documentar ─▶ implementar ─▶ testar ─▶ comparar ─▶ aprovar
```

| Aspecto | Como comparar | Ferramenta |
|---|---|---|
| Dados exibidos | mesmo seed, mesmo relógio; texto visível das duas versões igual (ordem e conteúdo) | Playwright `innerText` por região + diff |
| Ações/permissões | mesma matriz papel × ação (lab.admin … lab.sem_modulo) | `tests/e2e/permissions.spec.ts` como modelo |
| Cálculos | testes de caracterização existentes (diárias, numeração) inalterados e verdes | `manage.py test viagens_roteiros …` |
| Documentos | goldens DOCX/PDF inalterados | `documentos/tests/test_golden_templates.py` |
| Integrações | mock do eProtocolo, mesmos payloads | testes de `viagens_oficios` |
| UX | antes/depois lado a lado + diff; axe e responsivo **iguais ou melhores** (catracas) | `audit-page.mjs --label antes/depois` + `visual-compare.mjs` |

## Receita

```bash
npm run agent:reset -- --scenario normal
node tests/tools/audit-page.mjs --path /viagens/oficios/ --role viagensGestor --label antes --viewports desktop,tablet,mobile
# … migra a página (flag/rota nova) e reinicia o servidor do lab …
node tests/tools/audit-page.mjs --path /viagens/oficios/ --role viagensGestor --label depois --viewports desktop,tablet,mobile
node tests/tools/visual-compare.mjs reports/audit/viagens-oficios-antes reports/audit/viagens-oficios-depois
```

Aprovação exige: nenhum achado P0/P1 novo; axe `critical+serious` ≤ antes; sem overflow novo; texto/dados iguais
(ou diferença intencional registrada em `docs/agent/memory/decisions.md`).
