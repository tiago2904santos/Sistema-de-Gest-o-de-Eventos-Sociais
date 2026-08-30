# Deploy local (rede da unidade)

O sistema roda em modo produção nesta máquina, servido pelo **waitress**
na porta **8000**, e fica acessível aos colegas da mesma rede em:

- **http://sambook2-tiago:8000** (nome da máquina — preferido, não muda)
- http://192.168.1.106:8000 (IP atual — pode mudar com o DHCP)

## Como funciona

- A tarefa agendada **"Sistema eventos_sociais (producao)"** inicia o
  servidor no logon do usuário e o reinicia até 3 vezes se ele cair.
- Ela executa `scripts\deploy\servidor_producao.ps1`, que a cada subida:
  - liga o modo produção (`DJANGO_DEBUG=0`) e libera os hosts da máquina
    (nome + IPs atuais), sem alterar o `.env` de desenvolvimento;
  - roda `collectstatic` (estáticos com hash servidos pelo WhiteNoise —
    ninguém fica com CSS/JS antigo em cache) e `migrate`;
  - sobe o waitress em `0.0.0.0:8000` com 8 threads.
- Log de inicialização em `logs\producao.log`.
- O servidor de desenvolvimento continua separado, na porta 8021 e com
  DEBUG ligado — os dois convivem.

## Publicar uma nova versão

Reinicie a tarefa (ela mesma coleta estáticos e aplica migrations):

```bash
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'Sistema eventos_sociais (producao)'; Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }; Start-ScheduledTask -TaskName 'Sistema eventos_sociais (producao)'"
```

## Liberar o acesso dos colegas (uma vez, como administrador)

O firewall do Windows bloqueia conexões de outras máquinas até existir a
regra de entrada. Abra o PowerShell **como administrador** e rode:

```bash
powershell -NoProfile -Command "New-NetFirewallRule -DisplayName 'Sistema eventos_sociais (porta 8000)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Domain,Private"
```

(`-Profile Domain,Private` mantém a porta fechada em redes públicas.)

## Limitações deste deploy

- O sistema fica no ar enquanto esta máquina estiver ligada e o usuário
  logado (a tarefa é de logon).
- Sem HTTPS: ok para rede interna; obrigatório resolver antes de expor
  fora dela. Quando houver servidor institucional, migre o banco (backup
  em `backups\`), copie o projeto, ajuste o `.env` e reaproveite este
  mesmo script.
