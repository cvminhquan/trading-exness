$ErrorActionPreference = "Stop"
$Repo = "C:\Users\Quan\OneDrive\Desktop\trading-exness"
$Service = Join-Path $Repo ".cursor\review-service\review_service_agent.py"

Write-Host "Cau hinh AI reviewer (key se khong duoc in ra man hinh)."
$secure = Read-Host "Nhap OPENAI_API_KEY" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plain)) { throw "API key rong" }
    [Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $plain, "User")
}
finally {
    if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    $plain = $null
    $secure = $null
}

$model = Read-Host "Model [gpt-5.6-sol]"
if ([string]::IsNullOrWhiteSpace($model)) { $model = "gpt-5.6-sol" }
[Environment]::SetEnvironmentVariable("REVIEW_AI_MODEL", $model, "User")

Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*review_service_agent.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$env:OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
$env:REVIEW_AI_MODEL = [Environment]::GetEnvironmentVariable("REVIEW_AI_MODEL", "User")
$env:REVIEW_WEBHOOK_SECRET = [Environment]::GetEnvironmentVariable("REVIEW_WEBHOOK_SECRET", "User")
Start-Process python -ArgumentList @($Service) -WorkingDirectory $Repo -WindowStyle Hidden
Start-Sleep 2
$health = Invoke-RestMethod "http://127.0.0.1:8765/health"
Write-Host ("AI configured: " + $health.aiConfigured + "; model: " + $health.model)
