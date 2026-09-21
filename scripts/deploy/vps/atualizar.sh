#!/bin/bash
# Atualiza o sistema no VPS. Para em qualquer erro: um deploy pela metade é
# pior que um deploy que não aconteceu.
set -euo pipefail

RAIZ=/var/www/eventos-sociais
APP=$RAIZ/app
PY=$APP/.venv/bin/python

echo "== backup antes de tudo"
sudo -u eventos pg_dump eventos_sociais > "$RAIZ/backups/pre-deploy-$(date +%F-%H%M).sql"

echo "== código"
cd "$APP"
sudo -u eventos git pull --ff-only

echo "== dependências"
sudo -u eventos .venv/bin/pip install -q -r requirements.txt gunicorn

echo "== migrações"
sudo -u eventos "$PY" manage.py migrate --noinput

echo "== estáticos"
sudo -u eventos "$PY" manage.py collectstatic --noinput

echo "== checagem antes de reiniciar"
sudo -u eventos "$PY" manage.py check --deploy

echo "== serviços"
systemctl restart eventos-sociais
sleep 3
systemctl is-active --quiet eventos-sociais || { echo "FALHOU: site não subiu"; journalctl -u eventos-sociais -n 30 --no-pager; exit 1; }

echo "== pronto"
