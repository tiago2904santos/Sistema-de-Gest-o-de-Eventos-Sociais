"""
Configurações do projeto Sistema de Gestão de Eventos Sociais.

Variáveis de ambiente são carregadas a partir do arquivo `.env` na raiz
do projeto (veja `.env.example`).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Segurança
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "inseguro-somente-para-desenvolvimento-troque-em-producao",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

if not DEBUG and SECRET_KEY.startswith("inseguro-"):
    raise RuntimeError("Defina DJANGO_SECRET_KEY antes de iniciar em produção.")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    if os.environ.get("DJANGO_TRUST_PROXY_HTTPS", "0") == "1":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Aplicações
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps do projeto
    "core",
    "accounts",
    "cadastros",
    "solicitacoes",
    "dashboard",
    "agenda",
    "auditoria",
    "coffee_break",
    "demandas_eventos",
    "publicacoes",
    "atendimento_imprensa",
    "viagens_cadastros",
    "viagens_roteiros",
    "documentos",
    "viagens_oficios",
    "viagens_termos",
    "viagens_viagem",
    "viagens_ordens",
    "viagens_planos",
    "viagens_prestacoes",
    "migracao_legado",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serve os estáticos direto do app em produção (waitress).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Requisição corrente em thread-local: a auditoria por signals lê o
    # usuário e o caminho daqui, sem acoplamento com as views.
    "core.middleware.RequisicaoAtualMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Depois da autenticação e das mensagens: precisa de request.user.
    "accounts.middleware.TrocaDeSenhaObrigatoriaMiddleware",
    # Bloqueio de módulos restritos (Setor ↔ Modulo) direto no backend.
    "accounts.modulos.AutorizacaoPorModuloMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.perfis",
                "core.context_processors.notificacoes",
                "accounts.context_processors.modulos",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Banco de dados
#
# PostgreSQL configurado via variáveis de ambiente (veja `.env.example`).
# Quando POSTGRES_DB não estiver definido, usa SQLite como fallback de
# desenvolvimento para o projeto funcionar imediatamente.
# ---------------------------------------------------------------------------

if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

# A origem só é conectada pelos comandos de migração. Nem o servidor nem a
# suíte precisam de credenciais do GV. O PostgreSQL impõe somente leitura.
if os.environ.get("LEGADO_DB_NAME"):
    DATABASES["legado"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["LEGADO_DB_NAME"],
        "USER": os.environ.get("LEGADO_DB_USER", ""),
        "PASSWORD": os.environ.get("LEGADO_DB_PASSWORD", ""),
        "HOST": os.environ.get("LEGADO_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("LEGADO_DB_PORT", "5432"),
        "OPTIONS": {"options": "-c default_transaction_read_only=on -c statement_timeout=60000"},
        "CONN_MAX_AGE": 0,
    }

DATABASE_ROUTERS = ["migracao_legado.origem.RouterLegado"]

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
# Depois do login, o usuário cai no portal de módulos (hub).
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True

# ---------------------------------------------------------------------------
# Arquivos estáticos
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# E-mail (notificações)
#
# Sem EMAIL_HOST definido, usa o backend de console (mensagens no terminal),
# que é seguro para desenvolvimento. Em produção, configure via .env.
# ---------------------------------------------------------------------------

if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    # TLS (porta 587) é o padrão; use EMAIL_USE_SSL=1 para servidores na 465.
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "0") == "1"
    EMAIL_USE_TLS = (
        not EMAIL_USE_SSL and os.environ.get("EMAIL_USE_TLS", "1") == "1"
    )
    # Não deixa uma requisição presa se o servidor de e-mail não responder.
    EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "eventos-sociais@localhost"
)

STATIC_URL = "static/"

STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG:
    # Nome com hash em cada arquivo estático (cache-busting): o navegador
    # dos usuários nunca fica com CSS/JS antigo depois de uma atualização.
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# Anexos das solicitações. O download passa por uma view com checagem de
# permissão (solicitacoes.views.baixar_anexo) — não exponha MEDIA_URL
# diretamente no servidor web.
MEDIA_URL = "media/"

# Pasta dos arquivos enviados e gerados. Um ambiente de ensaio (a cópia da carga
# do GV) aponta a sua com MEDIA_ROOT, para não misturar arquivos com o dev.
MEDIA_ROOT = Path(os.environ["MEDIA_ROOT"]) if os.environ.get("MEDIA_ROOT") else BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Rotas (módulo Viagens)
#
# O cálculo de rota do editor de roteiro usa o OpenRouteService no servidor.
# Sem a chave, o mapa continua no ar e o botão "Calcular rota" explica o que
# falta — nenhuma outra tela depende disso.
# ---------------------------------------------------------------------------

OPENROUTESERVICE_API_KEY = os.environ.get("OPENROUTESERVICE_API_KEY", "")
ROUTE_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("ROUTE_REQUEST_TIMEOUT_SECONDS", "12")
)
# Município do percurso sem coordenadas é buscado no OpenStreetMap na hora.
# Nos testes fica desligado: nada de rede durante a suíte.
GEOCODIFICAR_SOB_DEMANDA = sys.argv[1:2] != ["test"]

# Núcleo documental síncrono. Motores nativos são opcionais e sondados sob demanda.
DOCUMENTOS_DEFAULT_PDF_ENGINE = os.environ.get("DOCUMENTOS_DEFAULT_PDF_ENGINE", "auto")
DOCUMENTOS_LIBREOFFICE_BINARY = os.environ.get("DOCUMENTOS_LIBREOFFICE_BINARY", "")
# Último recurso do PDF: texto corrido, transliterado, sem o layout oficial.
# Ligado só em desenvolvimento, como no sistema de origem. Em produção, um
# documento degradado em silêncio é pior que a falha — ninguém percebe antes de
# protocolar. Para assumir o risco conscientemente: DOCUMENTOS_SIMPLE_PDF_FALLBACK=1.
DOCUMENTOS_SIMPLE_PDF_FALLBACK = (
    os.environ.get("DOCUMENTOS_SIMPLE_PDF_FALLBACK", "1" if DEBUG else "0") == "1"
)
DOCUMENTOS_PDF_AUTO_FALLBACK = os.environ.get("DOCUMENTOS_PDF_AUTO_FALLBACK", "0") == "1"
DOCUMENTOS_PERSIST_ARTEFATOS = True
DOCUMENTOS_ARTIFACT_CACHE = True
DOCUMENTOS_GENERATOR_VERSION = "eventos-f3-1"
# Tipos cujo PDF nasce do HTML institucional (WeasyPrint), sem DOCX no caminho.
# Os demais seguem a cadeia antiga até migrarem.
DOCUMENTOS_PDF_HTML_NATIVO = ("oficio", "termo_autorizacao", "justificativa", "ordem_servico", "plano_trabalho", "relatorio_tecnico", "diario_bordo")
# Contingência de desenvolvimento: sem o runtime GTK, o PDF de um tipo HTML nativo
# cai na cadeia antiga em vez de falhar. Em produção fica desligada — o PDF não
# deve nascer do DOCX por acidente.
DOCUMENTOS_PDF_HTML_FALLBACK_DOCX = os.environ.get("DOCUMENTOS_PDF_HTML_FALLBACK_DOCX", "1" if DEBUG else "0") == "1"
