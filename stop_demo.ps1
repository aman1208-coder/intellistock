$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeFile = Join-Path $root '.devtunnels\demo-processes.json'
if (-not (Test-Path $runtimeFile)) {
    Write-Output 'No demo process record found; no processes were stopped.'
    exit 0
}

$records = Get-Content $runtimeFile -Raw | ConvertFrom-Json
if ($records -is [System.Array] -and $records.Count -eq 1 -and $records[0] -is [System.Array]) {
    $records = $records[0]
}
$skipped = $false
foreach ($record in $records) {
    $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
    if (-not $process) {
        continue
    }
    if ($process.StartTime.ToUniversalTime().Ticks -ne [long]$record.StartedAtTicks) {
        Write-Warning "Skipping PID $($record.Id): it is no longer the process started by this demo."
        $skipped = $true
        continue
    }
    Stop-Process -Id $record.Id -Force
    Write-Output "Stopped demo $($record.Name) process (PID $($record.Id))."
}

if (-not $skipped) {
    Remove-Item -Path $runtimeFile
    Write-Output 'Demo process record removed.'
}
