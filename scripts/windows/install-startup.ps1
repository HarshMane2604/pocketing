$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'
$runner = Join-Path $PSScriptRoot 'start-pocketing.ps1'
$launcher = Join-Path $PSScriptRoot 'open-pocketing.ps1'
$taskName = 'Pocketing Service'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    python -m venv (Join-Path $backendDir '.venv')
}
& $python -m pip install -r (Join-Path $backendDir 'requirements.txt')

Push-Location $frontendDir
try {
    if (Test-Path -LiteralPath (Join-Path $frontendDir 'package-lock.json')) {
        npm ci
    } else {
        npm install
    }
    npm run build
} finally {
    Pop-Location
}

$powershell = (Get-Command powershell.exe).Source
$taskArguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`""
$action = New-ScheduledTaskAction -Execute $powershell -Argument $taskArguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650) -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Runs the local Pocketing API, PWA, WebSocket, and messaging bridges.' -Force | Out-Null

$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$startup = [Environment]::GetFolderPath('Startup')
$icon = Join-Path $frontendDir 'public\icons\app-icon.svg'

foreach ($shortcutPath in @(
    (Join-Path $desktop 'Pocketing.lnk'),
    (Join-Path $startup 'Pocketing.lnk')
)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
    $shortcut.WorkingDirectory = $projectRoot
    if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = $icon }
    $shortcut.Save()
}

Start-ScheduledTask -TaskName $taskName
Write-Host 'Pocketing is installed. It will run and open automatically at Windows login.'
Write-Host 'Desktop shortcut created: Pocketing'
