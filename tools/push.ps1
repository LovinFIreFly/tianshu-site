# 甜薯剧本杀 · 推送重试脚本（Windows / PowerShell）
# ---------------------------------------------------------------------------
# 为什么需要它：连 GitHub 经常超时/被重置（代理一断就推不动），一次推不上就得手动试。
# 这个脚本按顺序换路，**第一条通了就停**：
#   ① 直连 GitHub
#   ② 走本机代理（默认 127.0.0.1:12000，你的加速器端口）
#   ③ 走国内镜像（ghproxy.com / gh-proxy.com，把 GitHub 请求转发一遍）
# 用法：PowerShell 里
#   powershell -ExecutionPolicy Bypass -File tools\push.ps1
#   powershell -ExecutionPolicy Bypass -File tools\push.ps1 -Branch python-rewrite
#   powershell -ExecutionPolicy Bypass -File tools\push.ps1 -Proxy http://127.0.0.1:7890
param(
    [string]$Branch = 'python-rewrite',
    [string]$Proxy = 'http://127.0.0.1:12000'
)

$ErrorActionPreference = 'Continue'
$Repo = 'https://github.com/LovinFireFly/tianshu-site.git'
$Mirrors = @(
    'https://ghproxy.com/https://github.com/LovinFireFly/tianshu-site.git',
    'https://gh-proxy.com/https://github.com/LovinFireFly/tianshu-site.git'
)

function Try-Push([string]$Url, [string]$ViaProxy, [string]$Label) {
    $args = @('push')
    if ($ViaProxy) { $args = @('-c', "http.proxy=$ViaProxy") + $args }
    $args += @($Url, "$Branch`:$Branch")
    Write-Host "  尝试：$Label" -ForegroundColor DarkGray
    $out = & git @args 2>&1 | Out-String
    if ($out -match "$Branch -> $Branch" -or $out -match 'up-to-date' -or $out -match 'Everything up-to-date') {
        Write-Host "  ✔ 推送成功（$Label）" -ForegroundColor Green
        return $true
    }
    Write-Host ("  ✘ 失败：" + (($out -split "`n") | Where-Object { $_ -match 'fatal|Failed|timed out|reset' } | Select-Object -First 1)) -ForegroundColor DarkYellow
    return $false
}

Write-Host "推送分支：$Branch" -ForegroundColor Cyan

if (Try-Push $Repo '' '直连 GitHub') { exit 0 }
if ($Proxy -and (Try-Push $Repo $Proxy "本机代理 $Proxy")) { exit 0 }
foreach ($m in $Mirrors) {
    if (Try-Push $m '' "国内镜像 $m") { exit 0 }
}

Write-Host ''
Write-Host '四条路都不通。备选方案：' -ForegroundColor Red
Write-Host '  1) 等网络恢复再跑一次本脚本'
Write-Host '  2) 用 U 盘/网盘：git bundle create update.bundle HEAD  → 拷到别处推'
Write-Host '  3) 只把改了的文件传服务器（不用 git）：见 README「推不动时的兜底办法」'
exit 1
