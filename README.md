# Sistema de Gestão de Eventos Sociais

Sistema institucional para gestão de solicitações de eventos sociais, construído
com Django, PostgreSQL e Django Templates, seguindo um design system próprio.

## Stack

- Python 3.14 / Django 6.1
- PostgreSQL (via variáveis de ambiente; SQLite como fallback de desenvolvimento)
- HTML + CSS + JS leve (Django Templates, sem framework de front-end)

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # ajuste as credenciais do PostgreSQL
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Estrutura

| App            | Responsabilidade                                        |
| -------------- | ------------------------------------------------------- |
| `core`         | Layout base, página inicial, utilidades compartilhadas   |
| `accounts`     | Usuário customizado, login/logout                        |
| `cadastros`    | Tabelas de apoio (tipos de evento, serviços, equipes...) |
| `solicitacoes` | Solicitações de eventos sociais e seus vínculos          |
| `dashboard`    | Visão geral e indicadores                                |
| `auditoria`    | Registro de ações relevantes                             |

Templates ficam em `templates/` (layouts, components e pages) e os arquivos de
design system em `static/css`, `static/js`, `static/img` e `static/icons`.
