$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$backendDir = Join-Path $projectRoot 'backend'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'
$logDir = Join-Path $backendDir 'logs'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python environment not found at $python. Run install-startup.ps1 first."
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Set-Location -LiteralPath $backendDir

# Keep this wrapper in the foreground so Task Scheduler can restart the service.
# Uvicorn writes normal lifecycle messages to stderr, so use native-process
# redirection instead of letting PowerShell treat those messages as failures.
$stdoutLog = Join-Path $logDir 'memory-inbox.log'
$stderrLog = Join-Path $logDir 'memory-inbox-error.log'
$process = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8010') `
    -WorkingDirectory $backendDir `
    -NoNewWindow `
    -PassThru `
    -Wait `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

exit $process.ExitCode
