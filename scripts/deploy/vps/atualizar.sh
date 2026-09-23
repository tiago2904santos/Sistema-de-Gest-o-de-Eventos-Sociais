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
# Dois jeitos de receber o código novo:
#  - um pacote (tar.gz) vindo do deploy automático, passado como 1º argumento
#    — o jeito que funciona mesmo quando a pasta não é um clone do Git (o
#    sistema foi copiado à mão para o VPS);
#  - sem pacote, o git pull de sempre, se a pasta for um clone.
PACOTE="${1:-}"
if [ -n "$PACOTE" ]; then
  # Guarda o código atual antes de trocar: é o que permite voltar atrás.
  # Fora do pacote: ambiente virtual, estáticos gerados e caches.
  tar -czf "$RAIZ/backups/codigo-pre-deploy-$(date +%F-%H%M).tgz" \
    --exclude=./.venv --exclude=./staticfiles --exclude='*/__pycache__' -C "$APP" .
  # Por cima do que existe: .env, .venv e o que não está no repositório ficam.
  tar -xzf "$PACOTE" -C "$APP"
  chown -R eventos:eventos "$APP"
  rm -f "$PACOTE"
elif [ -d "$APP/.git" ]; then
  sudo -u eventos git status --short | head -20
  sudo -u eventos git pull --ff-only
else
  echo "FALHOU: $APP não é um clone do Git e nenhum pacote de código foi enviado."
  exit 1
fi

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
