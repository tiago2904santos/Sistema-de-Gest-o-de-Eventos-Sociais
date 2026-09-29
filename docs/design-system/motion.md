# Movimento

**Hoje**: `--motion: 130ms cubic-bezier(.2,0,.2,1)` usado em transições de cor/fundo/opacidade. Bom e contido.

**Regra v4**: `motion.duration.fast` (130ms) para estados; 200ms para abrir/fechar painéis; nada acima de 300ms.
Respeitar `prefers-reduced-motion: reduce` (desligar deslocamentos). Os testes visuais desligam animações.
