# Backup do banco eventos_sociais (PostgreSQL).
#
# - Lê host/porta/usuário/senha do .env do projeto (nunca no código).
# - Gera dump no formato custom (-Fc), compacto e restaurável com pg_restore.
# - Grava em <projeto>\backups\ (pasta sincronizada pelo OneDrive = cópia na nuvem).
# - Mantém os últimos 30 dias de dumps; apaga os mais antigos.
# - Registra cada execução em backups\backup.log.
#
# Execução manual:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup\backup_banco.ps1
#
# A tarefa agendada "Backup eventos_sociais" roda este script diariamente
# (veja scripts\backup\README.md).

$ErrorActionPreference = "Stop"

$projeto = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pastaBackups = Join-Path $projeto "backups"
$log = Join-Path $pastaBackups "backup.log"
$diasRetencao = 30

$pgDump = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

function Registrar($mensagem) {
    $linha = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $mensagem
    Add-Content -Path $log -Value $linha -Encoding utf8
    Write-Host $linha
}

if (-not (Test-Path $pastaBackups)) {
    New-Item -ItemType Directory -Path $pastaBackups | Out-Null
}

try {
    # Variáveis de conexão a partir do .env do projeto.
    $envArquivo = Join-Path $projeto ".env"
    if (-not (Test-Path $envArquivo)) { throw "Arquivo .env não encontrado em $projeto" }
    $config = @{}
    foreach ($linha in Get-Content $envArquivo) {
        if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $valor = $Matches[2].Trim().Trim('"').Trim("'")
            $config[$Matches[1]] = $valor
        }
    }
    foreach ($chave in @("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")) {
        if (-not $config[$chave]) { throw "Variável $chave ausente no .env" }
    }
    $dbHost = if ($config["POSTGRES_HOST"]) { $config["POSTGRES_HOST"] } else { "localhost" }
    $dbPorta = if ($config["POSTGRES_PORT"]) { $config["POSTGRES_PORT"] } else { "5432" }

    if (-not (Test-Path $pgDump)) { throw "pg_dump não encontrado em $pgDump" }

    $carimbo = Get-Date -Format "yyyy-MM-dd_HHmm"
    $destino = Join-Path $pastaBackups ("{0}_{1}.dump" -f $config["POSTGRES_DB"], $carimbo)

    $env:PGPASSWORD = $config["POSTGRES_PASSWORD"]
    try {
        & $pgDump -h $dbHost -p $dbPorta -U $config["POSTGRES_USER"] `
            -d $config["POSTGRES_DB"] -Fc --no-password -f $destino
        if ($LASTEXITCODE -ne 0) { throw "pg_dump terminou com código $LASTEXITCODE" }
    }
    finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    }

    $tamanho = "{0:N0} KB" -f ((Get-Item $destino).Length / 1KB)
    Registrar "OK: $(Split-Path $destino -Leaf) ($tamanho)"

    # Rotação: remove dumps além do período de retenção.
    $limite = (Get-Date).AddDays(-$diasRetencao)
    $antigos = Get-ChildItem $pastaBackups -Filter "*.dump" |
        Where-Object { $_.LastWriteTime -lt $limite }
    foreach ($arquivo in $antigos) {
        Remove-Item $arquivo.FullName -Force
        Registrar "Rotacao: removido $($arquivo.Name)"
    }
}
catch {
    # Dump incompleto não serve para restauração.
    if ($destino -and (Test-Path $destino)) { Remove-Item $destino -Force }
    Registrar "ERRO: $($_.Exception.Message)"
    exit 1
}
