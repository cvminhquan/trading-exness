$Repo = "C:\Users\Quan\OneDrive\Desktop\trading-exness"
$Task = Join-Path $Repo ".cursor\collab\current-task.md"
$Marker = Join-Path $Repo ".cursor\collab\review-request.json"
$Log = Join-Path $Repo ".cursor\collab\watcher.log"
$WebhookUrl = "http://127.0.0.1:8765/webhook/review"
$IntervalSeconds = 30
$lastSignature = ""

function Write-WatcherLog([string]$Message) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $Log -Value "[$stamp] $Message"
}

function Get-Phase([string]$Content) {
    $match = [regex]::Match($Content, '(?m)^Phase:\s*(.+)$')
    if ($match.Success) { return $match.Groups[1].Value.Trim() }
    return "UNKNOWN"
}

function Send-ReviewEvent([string]$Json) {
    $headers = @{}
    $bodyBytes = [Text.Encoding]::UTF8.GetBytes($Json)
    $secret = [Environment]::GetEnvironmentVariable("REVIEW_WEBHOOK_SECRET", "User")
    if ($secret) {
        $hmac = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($secret))
        try {
            $signature = ([BitConverter]::ToString($hmac.ComputeHash($bodyBytes))).Replace("-", "").ToLowerInvariant()
            $headers["X-Review-Signature"] = $signature
        } finally { $hmac.Dispose() }
    }
    return Invoke-RestMethod -Method Post -Uri $WebhookUrl -ContentType "application/json; charset=utf-8" -Headers $headers -Body $bodyBytes -TimeoutSec 10
}
Write-WatcherLog "watcher_started interval=${IntervalSeconds}s webhook=$WebhookUrl"

while ($true) {
    try {
        if (-not (Test-Path $Task)) {
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }
        $content = Get-Content -Raw -Encoding UTF8 -Path $Task
        if ($content -notmatch '(?m)^Status:\s*IMPLEMENTED\s*$') {
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        $hash = (Get-FileHash -Algorithm SHA256 -Path $Task).Hash
        if ($hash -eq $lastSignature) {
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        $payload = [ordered]@{
            event = "REVIEW_REQUESTED"
            detectedAt = (Get-Date).ToUniversalTime().ToString("o")
            repo = "cvminhquan/trading-exness"
            phase = Get-Phase $content
            status = "IMPLEMENTED"
            taskFile = ".cursor/collab/current-task.md"
            taskSha256 = $hash
        }
        $json = $payload | ConvertTo-Json -Compress
        $payload | ConvertTo-Json | Set-Content -Path $Marker -Encoding UTF8

        $response = Send-ReviewEvent $json
        $lastSignature = $hash
        Write-WatcherLog "review_webhook accepted=$($response.accepted) duplicate=$($response.duplicate) sha256=$hash"
    }
    catch {
        Write-WatcherLog "watcher_error $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $IntervalSeconds
}
