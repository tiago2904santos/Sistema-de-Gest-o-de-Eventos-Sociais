# Auditoria estática — 58 achados

Gerado em 2026-09-29T13:38:23-03:00.

| Severidade | Qtde |
|---|---|
| P2 | 23 |
| P3 | 23 |
| P4 | 12 |

| Categoria | Qtde |
|---|---|
| ACCESSIBILITY | 9 |
| ARCHITECTURE | 1 |
| CONSISTENCY | 6 |
| MAINTAINABILITY | 5 |
| SECURITY | 24 |
| VISUAL | 13 |

## P0–P2

- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/agenda-extras.css`) 1 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/agenda-google.css`) 3 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/agenda.css`) 2 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/design-system.css`) 6 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/ds-v32-bridge.css`) 20 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/ds-v32.css`) 4 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/pages/viagens-documento.css`) 1 ocorrência(s)
- **P2 · ACCESSIBILITY** — Foco do teclado removido (outline: none) (`static/css/viagens-planos.css`) 1 ocorrência(s)
- **P2 · SECURITY** — DEBUG ligado quando a variável não existe (`config/settings.py`) DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1": um servidor sem .env sobe em modo debug.
- **P2 · SECURITY** — View isenta de CSRF (revisar) (`viagens_prestacoes/campo_views.py`) Aceitável só para webhooks com verificação de assinatura.
- **P2 · VISUAL** — Token usado sem definição: --accent (`--accent`) 
- **P2 · VISUAL** — Token usado sem definição: --font-size-sm (`--font-size-sm`) 
- **P2 · VISUAL** — Token usado sem definição: --paper (`--paper`) 
- **P2 · VISUAL** — Token usado sem definição: --paper-ink (`--paper-ink`) 
- **P2 · VISUAL** — Token usado sem definição: --radius-field (`--radius-field`) 
- **P2 · VISUAL** — Token usado sem definição: --shadow-soft (`--shadow-soft`) 
- **P2 · VISUAL** — Token usado sem definição: --space-1 (`--space-1`) 
- **P2 · VISUAL** — Token usado sem definição: --space-2 (`--space-2`) 
- **P2 · VISUAL** — Token usado sem definição: --space-3 (`--space-3`) 
- **P2 · VISUAL** — Token usado sem definição: --surface (`--surface`) 
- **P2 · VISUAL** — Token usado sem definição: --surface-rail (`--surface-rail`) 
- **P2 · VISUAL** — Token usado sem definição: --text-muted (`--text-muted`) 
- **P2 · VISUAL** — Token usado sem definição: --text-strong (`--text-strong`) 
