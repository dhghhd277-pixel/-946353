param(
    [switch]$Debug
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$checkScript = Join-Path $PSScriptRoot 'check_single_worker.ps1'
$pidFile = Join-Path $root 'BOT.pid'
$lockFile = Join-Path $root 'BOT.lock'

if (-not (Test-Path $python)) {
    Write-Error "Venv python not found: $python`nCreate venv and install requirements first."
    exit 1
}

if (-not (Test-Path $checkScript)) {
    Write-Error "Singleton check script not found: $checkScript"
    exit 1
}

function Get-BotProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like '*-m bot*' -or
                $_.CommandLine -like "*$root*" -or
                $_.CommandLine -like '*bot\__main__.py*' -or
                $_.CommandLine -like '*bot/__main__.py*' -or
                $_.CommandLine -like '*__main__.py.DISK*'
            )
        } |
        Select-Object ProcessId, Name, ExecutablePath, CommandLine
}

Write-Host "[BOTZD] Root: $root"

$targets = @(Get-BotProcesses)
if ($targets.Count -gt 0) {
    Write-Host "[BOTZD] Found running bot-related python processes:" -ForegroundColor Yellow
    $targets | Format-Table -AutoSize

    Write-Host "[BOTZD] Stopping..." -ForegroundColor Yellow
    foreach ($p in $targets) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host "[BOTZD] Stopped PID $($p.ProcessId)"
        } catch {
            Write-Host "[BOTZD] Could not stop PID $($p.ProcessId): $($_.Exception.Message)" -ForegroundColor Red
        }
    }

    Start-Sleep -Milliseconds 600
} else {
    Write-Host "[BOTZD] No bot-related python processes found."
}

# Remove stale pid/lock markers so the next worker can publish fresh ones.
try {
    if (Test-Path $pidFile) {
        Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
        Write-Host "[BOTZD] Removed stale BOT.pid" -ForegroundColor DarkGray
    }
} catch {}
try {
    if (Test-Path $lockFile) {
        Remove-Item -Force -ErrorAction SilentlyContinue $lockFile
        Write-Host "[BOTZD] Removed stale BOT.lock" -ForegroundColor DarkGray
    }
} catch {}

# Environment for current PowerShell session
if ($Debug) {
    $env:BOT_DEBUG = '1'
    Write-Host "[BOTZD] BOT_DEBUG=1" -ForegroundColor Cyan
}
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONWARNINGS = 'ignore'

Push-Location $root
try {
    Write-Host "[BOTZD] Starting bot (async): $python -u -m bot" -ForegroundColor Green
    $p = Start-Process -FilePath $python -ArgumentList @('-u', '-m', 'bot') -WorkingDirectory $root -NoNewWindow -PassThru
    Write-Host "[BOTZD] Launched PID: $($p.Id)" -ForegroundColor DarkGray
} finally {
    Pop-Location
}

# Note:
# On Windows, Python virtual environments may show a launcher + worker process.
# Treat BOT.pid + singleton_trace.log as the source of truth.

Start-Sleep -Seconds 4
Write-Host "[BOTZD] Checking singleton..." -ForegroundColor Cyan

$code = 1
for ($i = 0; $i -lt 12; $i++) {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $checkScript
        $code = $LASTEXITCODE
    } catch {
        $code = 1
    }
    if ($code -eq 0) { break }
    Start-Sleep -Seconds 1
}

if ($code -ne 0) {
    Write-Host "[BOTZD] FAIL - singleton check failed (exit=$code)." -ForegroundColor Red
    exit 1
}

Write-Host "[BOTZD] OK - single worker confirmed." -ForegroundColor Green

try {
    if (Test-Path $pidFile) {
        $workerPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($workerPid) {
            Write-Host "[BOTZD] Worker PID (BOT.pid): $workerPid" -ForegroundColor Cyan
        }
    }
} catch {}

try {
    $ps = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -and ($_.CommandLine -like '*bot\\__main__.py*' -or $_.CommandLine -like '*-m bot*') } |
        Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
    if ($ps) {
        Write-Host "[BOTZD] Bot-related python processes:" -ForegroundColor Yellow
        $ps | Format-Table -AutoSize
    }
    if (Test-Path $lockFile) {
        Write-Host "[BOTZD] Lock file exists: $lockFile" -ForegroundColor DarkGray
    }
} catch {}
