$ErrorActionPreference = 'Stop'
$taskName = 'Memory Inbox Service'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$shortcuts = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Memory Inbox.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory Inbox.lnk')
)
foreach ($shortcut in $shortcuts) {
    if (Test-Path -LiteralPath $shortcut -PathType Leaf) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}

Write-Host 'Memory Inbox startup entries were removed. Notes and configuration were preserved.'
