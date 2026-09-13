param(
    [string]$TaskName = "TradingExness-Autonomy"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Launcher = Join-Path $Repo ".cursor\collab\start-autonomy.ps1"
if (-not (Test-Path $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Launcher + '"'
) -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "Installed startup task: $TaskName"
