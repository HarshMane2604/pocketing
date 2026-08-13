$ErrorActionPreference = 'Stop'
$taskName = 'Pocketing Service'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$shortcuts = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Pocketing.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Startup')) 'Pocketing.lnk')
)
foreach ($shortcut in $shortcuts) {
    if (Test-Path -LiteralPath $shortcut -PathType Leaf) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}

Write-Host 'Pocketing startup entries were removed. Notes and configuration were preserved.'
