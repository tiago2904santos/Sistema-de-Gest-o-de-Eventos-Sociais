# Subir o sistema no VPS (Ubuntu)

Roteiro para pôr o sistema num servidor com HTTPS próprio. Para as
atualizações irem sozinhas a cada merge no `main`, veja
`docs/DEPLOY_AUTOMATICO.md`.

O VPS já hospeda o **GV legado**. Nada aqui encosta nele: o sistema novo tem
diretório, banco, usuário de sistema, porta interna e bloco de nginx próprios.
A única coisa compartilhada é o nginx, e mesmo ele por um arquivo separado em
`sites-available`.

> **Antes de começar.** Isto move dados de servidores da PCPR para um servidor
> exposto à internet. O GV já está lá, então o precedente existe — mas a
> decisão é administrativa, não técnica, e é de quem responde pelos dados.

## O que precisa existir antes

| Item | Como conferir |
| --- | --- |
| Acesso SSH ao VPS | `ssh root@SEU_IP` entra sem pedir senha |
| Domínio apontando para o IP | `dig +short seu.dominio.br` devolve o IP do VPS |
| Porta 80 e 443 livres | O GV usa nginx; os blocos convivem por `server_name` |
| ~2 GB de RAM livres | `free -h` — Postgres + Python + WeasyPrint |
| ~5 GB de disco | `df -h /` |

Sem domínio não há HTTPS válido. Um subdomínio do domínio que o GV já usa
resolve, e sai de graça.

## 1. Pacotes do sistema

```bash
apt update
apt install -y python3.12-venv python3-pip postgresql nginx certbot \
  python3-certbot-nginx git \
  libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

As quatro últimas são o GTK de que o WeasyPrint precisa para gerar PDF. Sem
elas o sistema sobe e só quebra na hora de emitir documento — que é o pior
momento para descobrir.

## 2. Usuário e diretórios

```bash
adduser --system --group --home /var/www/eventos-sociais eventos
mkdir -p /var/www/eventos-sociais/{app,media,backups}
chown -R eventos:eventos /var/www/eventos-sociais
```

Usuário próprio, sem shell: se o sistema for comprometido, o GV ao lado não vai
junto.

## 3. Banco

```bash
sudo -u postgres createuser eventos --pwprompt
sudo -u postgres createdb eventos_sociais --owner eventos
```

Guarde a senha para o `.env`. Banco separado do `viagens_prod` do GV, de
propósito: backup, restauração e uma migração errada ficam contidos.

## 4. Código e dependências

```bash
cd /var/www/eventos-sociais/app
sudo -u eventos git clone SEU_REPOSITORIO .
sudo -u eventos python3 -m venv .venv
sudo -u eventos .venv/bin/pip install -r requirements.txt gunicorn
```

`gunicorn` em vez do `waitress` que roda no Windows — mesmo papel, mas é o que
o systemd e o nginx esperam no Linux.

## 5. Configuração

Copie `.env.example` para `.env` e preencha. O que **muda** em relação ao dev:

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=            # gere uma nova; a de dev não vai para produção
DJANGO_ALLOWED_HOSTS=seu.dominio.br
POSTGRES_DB=eventos_sociais
POSTGRES_USER=eventos
POSTGRES_PASSWORD=            # a do passo 3
MEDIA_ROOT=/var/www/eventos-sociais/media
```

> **Não crie um `location /media/` no nginx.** Os anexos das solicitações são
> entregues por uma view que confere permissão antes (`baixar_anexo`); servi-los
> direto pelo nginx passaria por fora dessa checagem e deixaria qualquer pessoa
> com a URL baixar documento de viagem. Os estáticos vão pelo WhiteNoise, que o
> projeto já usa.

```bash
chown eventos:eventos .env && chmod 600 .env
sudo -u eventos .venv/bin/python manage.py migrate
sudo -u eventos .venv/bin/python manage.py collectstatic --noinput
sudo -u eventos .venv/bin/python manage.py createsuperuser
```

## 6. Serviços

Copie os dois arquivos desta pasta:

```bash
cp eventos-sociais.service /etc/systemd/system/
cp nginx-eventos-sociais.conf /etc/nginx/sites-available/eventos-sociais
ln -s /etc/nginx/sites-available/eventos-sociais /etc/nginx/sites-enabled/

systemctl daemon-reload
systemctl enable --now eventos-sociais
nginx -t && systemctl reload nginx
```


## 7. HTTPS

```bash
certbot --nginx -d seu.dominio.br
```

O certbot edita o bloco do nginx e programa a renovação sozinho.


## Atualizar depois

```bash
/var/www/eventos-sociais/app/scripts/deploy/vps/atualizar.sh
```

## Backup

O `scripts/backup/` de hoje é PowerShell, da máquina Windows. No VPS, o
equivalente é um `pg_dump` no cron:

```cron
30 3 * * * sudo -u eventos pg_dump eventos_sociais > /var/www/eventos-sociais/backups/$(date +\%F).sql
```

**Não suba sem backup funcionando.** É a única coisa desta lista que não dá
para consertar depois que faz falta.

## Deploy automático (GitHub Actions)

`.github/workflows/deploy.yml` roda o `atualizar.sh` por SSH toda vez que o CI
passa na `main` (e à mão, em Actions > "Deploy no VPS" > Run workflow).
Precisa, uma vez, de uma chave só para isso:

```bash
# no VPS
ssh-keygen -t ed25519 -N '' -f ~/.ssh/deploy_github -C deploy-github
cat ~/.ssh/deploy_github.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/deploy_github        # conteúdo vai no segredo VPS_SSH_KEY
ssh-keyscan localhost | sed "s/^localhost/SEU_IP/"   # opcional: VPS_KNOWN_HOSTS
```

No GitHub, em Settings > Secrets and variables > Actions, crie `VPS_HOST`
(o IP), `VPS_USER` (`root`) e `VPS_SSH_KEY`. Sem eles o job é pulado, não falha.

## Prints das telas

`scripts/prints/tirar_prints.py` entra no sistema com o Chromium do Playwright
e salva um PNG por tela — útil para mostrar uma mudança sem abrir o sistema:

```bash
pip install playwright && playwright install chromium
python scripts/prints/tirar_prints.py --usuario admin --senha ... /solicitacoes/
```
