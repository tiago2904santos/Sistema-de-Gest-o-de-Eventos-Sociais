# Princípios

1. **Clareza institucional** — o sistema produz documentos oficiais; a interface deve ser sóbria, legível e previsível.
2. **Uma forma de fazer cada coisa** — um componente por necessidade; variações por parâmetro, não por cópia.
3. **Acessível por padrão (WCAG 2.2 AA)** — contraste, foco visível e teclado não são opcionais.
4. **Denso sem ser apertado** — telas de trabalho (listas, formulários longos) priorizam informação, com hierarquia clara.
5. **Tokens antes de valores** — nenhum valor literal de cor, fonte, raio, sombra ou z-index fora de `tokens/`.
6. **Estados completos** — todo componente e página define default, vazio, erro, carregando, sem permissão e conteúdo longo.
7. **Evidência** — mudança visual só se aprova com antes/depois e catracas verdes (`docs/agent/design-review-loop.md`).
