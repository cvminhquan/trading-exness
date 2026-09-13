param(
    [switch]$NoReviewService,
    [switch]$NoReviewWatcher,
    [switch]$DryRunRunner
)

$ErrorActionPreference = "Stop"

foreach ($name in @("REVIEW_WEBHOOK_SECRET", "OPENAI_API_KEY")) {
    $value = [Environment]::GetEnvironmentVariable($name, "User")
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Python = (Get-Command python -ErrorAction Stop).Source
$Runner = Join-Path $Repo ".cursor\collab\cursor-task-runner.py"
$ReviewWatcher = Join-Path $Repo ".cursor\collab\repo-watcher.ps1"
$ReviewService = Join-Path $Repo ".cursor\review-service\review_service_agent.py"
$StateDir = Join-Path $Repo ".cursor\collab\runner-state"
$LauncherLog = Join-Path $StateDir "launcher.log"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Write-LauncherLog([string]$Message) {
    $stamp = (Get-Date).ToUniversalTime().ToString("o")
    Add-Content -Path $LauncherLog -Value "[$stamp] $Message"
}

function Test-CommandLine([string]$Needle) {    return [bool](Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($Needle)
    } | Select-Object -First 1)
}

if (-not $NoReviewService -and -not (Test-CommandLine "review_service_agent.py")) {
    Start-Process -FilePath $Python -ArgumentList @($ReviewService) -WorkingDirectory $Repo -WindowStyle Hidden
    Write-LauncherLog "review_service_started"
} else {
    Write-LauncherLog "review_service_already_running_or_disabled"
}

if (-not $NoReviewWatcher -and -not (Test-CommandLine "repo-watcher.ps1")) {
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", $ReviewWatcher
    ) -WorkingDirectory $Repo -WindowStyle Hidden
    Write-LauncherLog "review_watcher_started"
} else {
    Write-LauncherLog "review_watcher_already_running_or_disabled"
}

if (-not (Test-CommandLine "cursor-task-runner.py")) {
    $runnerArgs = @($Runner)
    if ($DryRunRunner) { $runnerArgs += "--dry-run" }
    Start-Process -FilePath $Python -ArgumentList $runnerArgs -WorkingDirectory $Repo -WindowStyle Hidden
    Write-LauncherLog "cursor_runner_started dryRun=$DryRunRunner"
} else {
    Write-LauncherLog "cursor_runner_already_running"
}