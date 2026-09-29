# Observabilidade do produto

**Hoje**: logs do Django/waitress em `logs/` (produção local), e-mail de erro não configurado, sem APM/Sentry,
rotinas diárias disparadas no primeiro acesso (middleware). Auditoria de negócio via `RegistroAuditoria`.

**Recomendado (não instalado)**: `LOGGING` estruturado (JSON) com request-id; Sentry (plano gratuito) ou
GlitchTip self-hosted para exceções; `/saude/` público mínimo (DB + migrações) para o monitor da VPS;
métrica de tempo das gerações de documento (motor escolhido, duração, falhas).
