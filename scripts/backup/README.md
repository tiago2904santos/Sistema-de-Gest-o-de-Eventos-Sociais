# Backup do banco de dados

Backup diário automático do banco PostgreSQL `eventos_sociais`.

## Como funciona

- A tarefa agendada do Windows **"Backup eventos_sociais"** roda todo dia às
  **12:30** (ou assim que o computador ligar, se estava desligado no horário).
- Ela executa `scripts\backup\backup_banco.ps1`, que:
  - lê a conexão do `.env` do projeto (a senha nunca fica no script);
  - gera um dump compactado (`pg_dump -Fc`) em `backups\` na raiz do projeto —
    pasta sincronizada pelo OneDrive, então cada backup também sobe para a nuvem;
  - mantém os últimos **30 dias** e apaga dumps mais antigos;
  - registra cada execução (sucesso ou erro) em `backups\backup.log`.

## Backup manual

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts/backup/backup_banco.ps1"
```

## Restaurar um backup

Com o PostgreSQL rodando, em um banco vazio (troque o nome do arquivo pelo
dump desejado):

```bash
"C:/Program Files/PostgreSQL/18/bin/pg_restore.exe" -h localhost -U postgres -d eventos_sociais --clean --if-exists "backups/eventos_sociais_2026-08-30_0103.dump"
```

- `--clean --if-exists` recria os objetos por cima dos existentes — use para
  voltar o banco atual a um ponto anterior.
- Para restaurar em um banco novo: crie-o antes
  (`createdb -U postgres eventos_sociais_restaurado`) e aponte o `-d` para ele.
- Depois de restaurar, rode as migrations para garantir que o schema está no
  ponto do código: `python manage.py migrate`.

## Conferir a tarefa agendada

Abra o **Agendador de Tarefas** do Windows e procure "Backup eventos_sociais",
ou verifique pelo PowerShell:

```bash
powershell -NoProfile -Command "Get-ScheduledTaskInfo -TaskName 'Backup eventos_sociais' | Select-Object LastRunTime, LastTaskResult, NextRunTime"
```

`LastTaskResult = 0` significa que o último backup terminou sem erro. O
histórico completo fica em `backups\backup.log`.
