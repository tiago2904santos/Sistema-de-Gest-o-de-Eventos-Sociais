# Memória de engenharia do agente

Arquivos curtos, uma entrada por item, **datados** e com **evidência** (arquivo, teste, relatório).
Ler antes de trabalhar; escrever no mesmo commit da mudança que gerou o aprendizado.

| Arquivo | Registra |
|---|---|
| [decisions.md](decisions.md) | Decisões tomadas (o quê, por quê, alternativas) — as grandes viram ADR em `docs/architecture/adr/` |
| [discoveries.md](discoveries.md) | Fatos descobertos sobre o sistema que não estão óbvios no código |
| [corrections.md](corrections.md) | Erros do próprio agente e como não repetir |
| [known-problems.md](known-problems.md) | Problemas abertos do produto, com severidade e evidência |
| [approved-patterns.md](approved-patterns.md) | Padrões validados para reutilizar |
| [rejected-patterns.md](rejected-patterns.md) | O que foi tentado/considerado e rejeitado, e por quê |
| [lessons-learned.md](lessons-learned.md) | Lições gerais de processo |

Formato de entrada: `- **AAAA-MM-DD · título** — texto. Evidência: <caminho>.`
