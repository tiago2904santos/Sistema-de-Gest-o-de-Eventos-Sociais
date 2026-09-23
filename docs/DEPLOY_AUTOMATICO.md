# Deploy automático na VPS (GitHub Actions)

Depois que um PR entra no `main` e o CI passa, o workflow **Deploy VPS**
(`.github/workflows/deploy-vps.yml`) entra na VPS por SSH e roda
`scripts/deploy/vps/atualizar.sh` — backup do banco, `git pull`,
dependências, migrações, estáticos, checagem e reinício. Se algo falha, o
script para e o GitHub marca o deploy em vermelho (e manda e-mail).

Também dá para disparar à mão: **Actions › Deploy VPS › Run workflow**.

Enquanto os secrets abaixo não existirem, o workflow só avisa e não faz nada.

## Configurar (uma vez)

Os passos 1 e 3 são no Mac (Terminal). O 2 é na VPS — pelo console web do
painel da hospedagem, se o SSH não estiver à mão. O 4 é no GitHub.

### 1. Criar a chave de deploy (Mac)

```bash
ssh-keygen -t ed25519 -N "" -C "deploy-github" -f ~/.ssh/deploy_eventos
```

Isso cria dois arquivos: `~/.ssh/deploy_eventos` (privada — vai para o
GitHub) e `~/.ssh/deploy_eventos.pub` (pública — vai para a VPS). É uma chave
só para o deploy: dá para revogar sem mexer em nenhuma outra.

Mostrar a pública, para copiar:

```bash
cat ~/.ssh/deploy_eventos.pub
```

### 2. Autorizar a chave na VPS

**Hostinger (a VPS atual, `srv1775737.hstgr.cloud`):** hPanel › VPS ›
Configurações › **Chaves SSH** › adicionar chave, com o nome
`github-actions-deploy`, colando a linha do `.pub`. O painel instala a chave
no `root`. Se já existir uma chave com esse nome e você não tiver a privada
dela, apague a antiga e cadastre a nova.

Em outro provedor, no terminal da VPS (console web do painel ou `ssh root@IP`):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'COLE_AQUI_A_LINHA_DO_.pub' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Conferir, do Mac:

```bash
ssh -i ~/.ssh/deploy_eventos root@srv1775737.hstgr.cloud echo ok
```

Tem de responder `ok` sem pedir senha.

### 3. Pegar a identidade da VPS (Mac)

```bash
ssh-keyscan srv1775737.hstgr.cloud
```

Copie as linhas que aparecerem (começam com o IP). Elas garantem que o GitHub
está falando com a sua VPS e não com outra máquina no caminho.

### 4. Cadastrar os secrets no GitHub

No repositório: **Settings › Secrets and variables › Actions › New
repository secret**, um de cada vez:

| Nome | Valor |
| --- | --- |
| `VPS_HOST` | o IP ou o nome da VPS — hoje `srv1775737.hstgr.cloud` |
| `VPS_SSH_KEY` | a chave **privada** inteira — saída de `cat ~/.ssh/deploy_eventos`, das linhas `-----BEGIN` até `-----END` |
| `VPS_KNOWN_HOSTS` | as linhas do passo 3 |
| `VPS_USER` | só se não for `root` |
| `VPS_PORT` | só se o SSH não for na porta 22 |

Para copiar a privada direto para a área de transferência no Mac:

```bash
pbcopy < ~/.ssh/deploy_eventos
```

### 5. Testar

**Actions › Deploy VPS › Run workflow**. Em verde, o log termina em
`== pronto`.

## Se precisar revogar

Apague a linha `deploy-github` do `~/.ssh/authorized_keys` na VPS e o secret
`VPS_SSH_KEY` no GitHub.
