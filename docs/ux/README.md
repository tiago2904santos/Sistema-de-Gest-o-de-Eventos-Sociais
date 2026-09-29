# UX

- Auditoria manual mais recente: [../auditoria-pratica-2026-09-29.md](../auditoria-pratica-2026-09-29.md) (5 pontos transversais: linha não clicável, foco invisível, dia da semana da agenda, contraste, páginas de erro).
- Auditoria visual anterior (capturas por módulo): `../auditoria-visual-2026-09-02/`.
- Problemas abertos com severidade: [../agent/memory/known-problems.md](../agent/memory/known-problems.md).
- Arquétipos e regras por tipo de página: [../design-system/page-archetypes.md](../design-system/page-archetypes.md).

## Checklist heurístico por página (usar com `audit-page.mjs`)

1. O objetivo principal da página é óbvio em 5 segundos? Uma ação primária?
2. Estados: vazio, vazio filtrado, erro, carregando, sem permissão, conteúdo longo.
3. A ação mais comum custa um clique (ex.: abrir registro)?
4. Rótulos e mensagens em linguagem do usuário; erros dizem como resolver.
5. Teclado: ordem lógica, foco visível, Esc fecha, Enter envia.
6. Celular: sem rolagem horizontal, alvos ≥ 44px, tabela vira lista.
7. Consistência: mesmo componente para a mesma coisa em todos os módulos.
