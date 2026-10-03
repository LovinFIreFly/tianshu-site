# 重启本地站点（8099）：杀旧进程 → 后台拉起新的 → 自检 /health
$conn = Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
  $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $conn.OwningProcess)
  Write-Host ("停止旧服务 PID=" + $p.ProcessId)
  Stop-Process -Id $conn.OwningProcess -Force
  Start-Sleep -Seconds 1
} else {
  Write-Host "8099 没有在跑的服务"
}
Start-Process -FilePath "python" -ArgumentList "app.py --port 8099 --no-browser" -WorkingDirectory "C:\Users\junbo\Desktop\网站" -WindowStyle Hidden
Start-Sleep -Seconds 4
try {
  $r = Invoke-WebRequest -Uri http://127.0.0.1:8099/health -UseBasicParsing -TimeoutSec 6
  Write-Host ("HEALTH " + $r.StatusCode)
} catch { Write-Host "HEALTH FAIL：$($_.Exception.Message)" }
