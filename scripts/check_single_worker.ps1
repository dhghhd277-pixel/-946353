param(
    [int]$TailLines = 2000,
    [int]$SkewSeconds = 5
)

$ErrorActionPreference = 'Stop'

function Fail([string]$Message, [int]$Code = 1) {
    Write-Host $Message
    exit $Code
}

try {
    $root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
} catch {
    $root = (Get-Location).Path
}

$pidPath = Join-Path $root 'BOT.pid'
$tracePath = Join-Path $root 'singleton_trace.log'

if (-not (Test-Path $pidPath)) {
    Fail "BOTZD: BOT.pid not found ($pidPath). Bot is not running or has not reached singleton guard yet." 2
}

$pidText = (Get-Content $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $pidText) {
    Fail "BOTZD: BOT.pid is empty ($pidPath)." 2
}

[int]$workerPid = 0
if (-not [int]::TryParse(($pidText.Trim()), [ref]$workerPid) -or $workerPid -le 0) {
    Fail "BOTZD: BOT.pid does not contain a valid PID: '$pidText'." 2
}

$workerProc = Get-Process -Id $workerPid -ErrorAction SilentlyContinue
if (-not $workerProc) {
    Fail "BOTZD: PID from BOT.pid is not running: $workerPid" 3
}

$startUtc = $workerProc.StartTime.ToUniversalTime()
$sinceUtc = $startUtc.AddSeconds(-[math]::Abs($SkewSeconds))

Write-Host "BOTZD: worker pid=$workerPid start_utc=$($startUtc.ToString('s'))Z"
try {
    Write-Host "BOTZD: worker exe=$($workerProc.Path)"
} catch {
    # ignore
}

# Confirm the singleton TCP port is actually held (strong guard).
try {
    $tnc = Test-NetConnection -ComputerName '127.0.0.1' -Port 48123 -WarningAction SilentlyContinue
    if (-not $tnc.TcpTestSucceeded) {
        Fail "BOTZD: singleton port 48123 is NOT listening (TcpTestSucceeded=False). Worker may have failed before acquiring port guard." 6
    }
    Write-Host "BOTZD: singleton port 48123 is listening."
} catch {
    # If Test-NetConnection is unavailable (older PowerShell), don't hard-fail.
    Write-Host "BOTZD: WARNING: could not verify singleton port 48123 ($($_.Exception.Message))."
}

# Always show worker command line via WMI/CIM (more reliable than guessing patterns)
try {
    $w = Get-CimInstance Win32_Process -Filter "ProcessId=$workerPid" -ErrorAction SilentlyContinue
    if ($w -and $w.CommandLine) {
        Write-Host "BOTZD: worker cmd=$($w.CommandLine)"
    }
} catch {
    # ignore
}

# Show bot-related python processes (informational)
try {
    $allPy = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -and ($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.CommandLine }

    $botLikeRegex = '(^|\s)-m\s+bot(\s|$)|bot[\\/]+__main__\.py'
    $botProcs = @($allPy | Where-Object { $_.CommandLine -match $botLikeRegex })

    if ($botProcs -and $botProcs.Count -gt 0) {
        Write-Host "BOTZD: bot-like python processes: $($botProcs.Count)"
        $botProcs | Sort-Object ProcessId | Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine |
            Format-Table -AutoSize | Out-String -Width 400 | Write-Host
    } else {
        Write-Host "BOTZD: no bot-like python processes found (unexpected if the bot is running)."
    }
} catch {
    # ignore
}

if (-not (Test-Path $tracePath)) {
    Fail "BOTZD: singleton_trace.log not found ($tracePath)." 4
}

$lines = Get-Content $tracePath -Tail $TailLines -ErrorAction SilentlyContinue
if (-not $lines) {
    Fail "BOTZD: singleton_trace.log is empty." 4
}

# Parse lines like:
# 2026-02-07T10:11:12Z event=main_enter pid=9368 ppid=... name=... exe=... argv=[...]
$events = foreach ($line in $lines) {
    if ($line -match '^(?<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+event=(?<event>\S+)\s+pid=(?<pid>\d+)') {
        try {
            $ts = [DateTime]::ParseExact($Matches.ts, "yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
            [PSCustomObject]@{
                TsUtc = $ts.ToUniversalTime()
                Event = $Matches.event
                Pid = [int]$Matches.pid
                Raw = $line
            }
        } catch {
            # ignore
        }
    }
}

$recent = $events | Where-Object { $_.TsUtc -ge $sinceUtc }

$workerMain = $recent | Where-Object { $_.Pid -eq $workerPid -and $_.Event -eq 'main_enter' }
if (-not $workerMain) {
    Write-Host "BOTZD: recent events (since_utc=$($sinceUtc.ToString('s'))Z):"
    ($recent | Sort-Object TsUtc | Select-Object TsUtc,Event,Pid,Raw | Format-Table -AutoSize | Out-String -Width 400) | Write-Host
    Fail "BOTZD: main_enter not found for worker PID=$workerPid in singleton_trace.log (within ~$(($startUtc - $sinceUtc).TotalSeconds) seconds)." 5
}

$otherWorkers = $recent | Where-Object { $_.Event -eq 'main_enter' -and $_.Pid -ne $workerPid } | Sort-Object TsUtc
if ($otherWorkers) {
    Write-Host "BOTZD: WARNING: other main_enter events detected after worker start:" 
    ($otherWorkers | Select-Object TsUtc,Event,Pid,Raw | Format-Table -AutoSize | Out-String -Width 400) | Write-Host
    Fail "BOTZD: multiple workers suspected (main_enter for different PIDs)." 1
}

Write-Host "BOTZD: OK - single worker confirmed (pid=$workerPid)."
exit 0
