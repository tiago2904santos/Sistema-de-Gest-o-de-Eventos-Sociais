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
python manage.py seed_initial_data
python manage.py createsuperuser
python manage.py runserver
```

## Dados iniciais e municípios

- `python manage.py seed_initial_data` — idempotente; cria os grupos de perfil
  (SOLICITANTE, ANALISTA, GESTOR_DG, ADMINISTRADOR), tipos de evento, serviços,
  órgãos, equipes e uma amostra de municípios do PR por mesorregião do IBGE.
- `python manage.py importar_municipios <arquivo.csv>` — carga completa dos 399
  municípios do Paraná a partir de um CSV oficial (colunas `nome;regiao`,
  separador `;`, UTF-8). Fonte recomendada: lista de municípios do IBGE ou o
  dataset institucional da PCPR com o mapeamento de regiões.

## Perfis e workflow

O fluxo é RASCUNHO → ENVIADA → EM_ANALISE → AGUARDANDO_DESPACHO →
ATENDIDA/NAO_ATENDIDA/CANCELADA (decisão da DG). As transições são
centralizadas em `solicitacoes/services.py` e a política de acesso em
`solicitacoes/permissions.py` (grupos do Django; superusuário ignora
restrições). Cada ação relevante gera `HistoricoSolicitacao`; ações
administrativas de cadastros geram `LogAuditoria`.

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
