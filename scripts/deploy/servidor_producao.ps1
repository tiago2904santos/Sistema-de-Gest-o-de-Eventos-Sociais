# Servidor de PRODUÇÃO local do Sistema de Gestão de Eventos Sociais.
#
# Sobe o app com waitress (servidor WSGI) em modo produção, acessível na
# rede local pela porta 8000:
#   - DEBUG desligado e hosts permitidos = esta máquina (nome + IP atual);
#   - estáticos coletados com hash (WhiteNoise) a cada inicialização;
#   - segredos continuam vindo do .env (a definição de variável aqui só
#     sobrepõe o modo de execução — load_dotenv não sobrescreve o ambiente).
#
# Executado pela tarefa agendada "Sistema eventos_sociais (producao)" no
# logon do usuário. Para rodar manualmente:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy\servidor_producao.ps1

$ErrorActionPreference = "Stop"

$projeto = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = Join-Path $projeto ".venv\Scripts\python.exe"
$waitress = Join-Path $projeto ".venv\Scripts\waitress-serve.exe"
$logs = Join-Path $projeto "logs"
$log = Join-Path $logs "producao.log"
$porta = 8000

if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }

function Registrar($mensagem) {
    $linha = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $mensagem
    Add-Content -Path $log -Value $linha -Encoding utf8
}

Set-Location $projeto

# Modo produção: sobrepõe o DJANGO_DEBUG=1 do .env de desenvolvimento.
$env:DJANGO_DEBUG = "0"

# Hosts aceitos: localhost + nome desta máquina + IPs atuais da rede.
$nomes = @("localhost", "127.0.0.1", $env:COMPUTERNAME.ToLower())
try {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -notlike "169.*" -and $_.IPAddress -ne "127.0.0.1" } |
        ForEach-Object { $_.IPAddress }
    $nomes += $ips
} catch {}
$env:DJANGO_ALLOWED_HOSTS = ($nomes | Select-Object -Unique) -join ","

Registrar "Iniciando: hosts=$($env:DJANGO_ALLOWED_HOSTS) porta=$porta"

# Estáticos com hash para o WhiteNoise servir com cache correto.
& $python manage.py collectstatic --noinput | Out-Null
if ($LASTEXITCODE -ne 0) {
    Registrar "ERRO: collectstatic falhou ($LASTEXITCODE)"
    exit 1
}

# Migrations pendentes aplicadas antes de subir (deploy de nova versão).
& $python manage.py migrate --noinput | Out-Null
if ($LASTEXITCODE -ne 0) {
    Registrar "ERRO: migrate falhou ($LASTEXITCODE)"
    exit 1
}

Registrar "Servidor no ar em http://$($env:COMPUTERNAME.ToLower()):$porta"
& $waitress --listen="0.0.0.0:$porta" --threads=8 config.wsgi:application
Registrar "Servidor encerrado (codigo $LASTEXITCODE)"
