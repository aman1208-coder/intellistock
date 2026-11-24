$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$runtimeDir = Join-Path $root '.devtunnels'
$runtimeFile = Join-Path $runtimeDir 'demo-processes.json'

if (Test-Path $runtimeFile) {
    throw 'A demo process record already exists. Run stop_demo.ps1 before starting another demo.'
}

$portOwners = @{}
$netstat = netstat -ano -p tcp
foreach ($port in @(8000, 5173, 5174)) {
    $connections = @($netstat | Where-Object { $_ -match (":$port\s+.*LISTENING\s+\d+\s*$") })
    if ($connections) {
        $portOwners[$port] = $connections
    }
}
if ($portOwners.Count -gt 0) {
    $ports = ($portOwners.Keys | Sort-Object) -join ', '
    throw "Required demo port(s) already have a listener: $ports. No existing process was stopped."
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$python = (Get-Command python -ErrorAction Stop).Source
$node = (Get-Command node.exe -ErrorAction Stop).Source
$viteCli = Join-Path $frontend 'node_modules\vite\bin\vite.js'
if (-not (Test-Path $viteCli)) {
    throw 'Frontend dependencies are missing; run npm install in frontend first.'
}

Push-Location $backend
try {
    & $python -m scripts.create_demo_users
    if ($LASTEXITCODE -ne 0) {
        throw 'Demo user provisioning failed.'
    }
}
finally {
    Pop-Location
}

$started = [System.Collections.Generic.List[object]]::new()
function Save-ProcessRecord {
    $started | ConvertTo-Json -Depth 4 | Set-Content -Path $runtimeFile -Encoding utf8
}
function Start-TrackedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $stdout = Join-Path $runtimeDir "$Name.out.log"
    $stderr = Join-Path $runtimeDir "$Name.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Start-Sleep -Milliseconds 250
    if ($process.HasExited) {
        throw "$Name exited during startup. Check its local log in .devtunnels."
    }
    $started.Add([pscustomobject]@{
        Name = $Name
        Id = $process.Id
        StartedAtTicks = $process.StartTime.ToUniversalTime().Ticks
    })
    Save-ProcessRecord
}

try {
    Start-TrackedProcess -Name 'backend' -FilePath $python -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--no-access-log') -WorkingDirectory $backend
    Start-TrackedProcess -Name 'admin' -FilePath $node -Arguments @("`"$viteCli`"", '--host', '0.0.0.0', '--port', '5173') -WorkingDirectory $frontend
    Start-TrackedProcess -Name 'member' -FilePath $node -Arguments @("`"$viteCli`"", '--host', '0.0.0.0', '--port', '5174') -WorkingDirectory $frontend

    Start-Sleep -Seconds 5
    $ready = $true
    foreach ($record in $started) {
        $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if (-not $process -or $process.StartTime.ToUniversalTime().Ticks -ne $record.StartedAtTicks) {
            $ready = $false
            break
        }
    }
    if (-not $ready) {
        throw 'A demo service exited during startup. Check its local log in .devtunnels.'
    }
    Write-Output 'Demo service processes are running on ports 8000, 5173, and 5174.'
}
catch {
    foreach ($record in $started) {
        $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if ($process -and $process.StartTime.ToUniversalTime().Ticks -eq $record.StartedAtTicks) {
            Stop-Process -Id $record.Id -Force
        }
    }
    if (Test-Path $runtimeFile) {
        Remove-Item -Path $runtimeFile
    }
    throw
}
