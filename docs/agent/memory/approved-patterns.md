# Padrões aprovados

- **Evidência antes de opinião** — conclusão visual só com captura/diff/axe/DOM. Ferramentas: `audit-page.mjs`, `visual-compare.mjs`.
- **Catraca** para dívidas medidas (a11y, overflow, visuais): registrar o estado, proibir piora, apertar ao corrigir.
- **Seed determinístico por cenário** (`agent_seed --scenario`) + relógio ancorado; nunca dado aleatório para reproduzir bug de UI.
- **UI Lab** (`/_lab/`): componente real, isolado, em cada estado; alvo de visual e axe por componente. Novo componente = novos espécimes em `agent_lab/specimens.py`.
- **Teste de caracterização antes de mexer em regra de dinheiro/documento** (já é regra do Plano Mestre — manter).
- **Um formato de achado** (`docs/agent/audit-finding.schema.json`) para toda auditoria, estática ou de runtime.
- **Regressões conhecidas como `test.fail()`** com o motivo: o teste documenta o bug e acusa quando ele for corrigido.
- **Checkpoint git + commits pequenos**; entrega por branch, nunca direto em `main`.
