# 甜薯剧本杀 - 推送重试脚本（Windows / PowerShell）
# ---------------------------------------------------------------------------
# 连 GitHub 经常超时/被重置（代理一断就推不动），手动一条条试很烦。
# 这个脚本按顺序换路，第一条通了就停：
#   1) 直连 GitHub   2) 本机代理(默认 127.0.0.1:12000)   3) 国内镜像 ghproxy / gh-proxy
# 用法：powershell -ExecutionPolicy Bypass -File tools\push.ps1 [-Branch 分支] [-Proxy 代理]
param(
    [string]$Branch = 'python-rewrite',
    [string]$Proxy  = 'http://127.0.0.1:12000'
)

$ErrorActionPreference = 'Continue'
$Repo = 'https://github.com/LovinFireFly/tianshu-site.git'
$Mirrors = @(
    'https://ghproxy.com/https://github.com/LovinFireFly/tianshu-site.git',
    'https://gh-proxy.com/https://github.com/LovinFireFly/tianshu-site.git'
)

function Try-Push {
    param([string]$Url, [string]$ViaProxy, [string]$Label)

    $gitArgs = @('push')
    if ($ViaProxy) { $gitArgs = @('-c', ('http.proxy=' + $ViaProxy)) + $gitArgs }
    $gitArgs += @($Url, ($Branch + ':' + $Branch))

    Write-Host ('  尝试：' + $Label) -ForegroundColor DarkGray
    $out = (& git @gitArgs 2>&1 | Out-String)
    if ($out -match ($Branch + ' -> ' + $Branch) -or $out -match 'up-to-date') {
        Write-Host ('  OK 推送成功（' + $Label + '）') -ForegroundColor Green
        return $true
    }
    # 用正则取错：不用 -split `n（转义在这个环境里会被吃掉，导致脚本解析失败）
    $line = [regex]::Match($out, 'fatal:[^
]*').Value
    if (-not $line) { $line = [regex]::Match($out, '(Failed|timed out|Connection was reset)[^
]*').Value }
    if (-not $line) { $line = 'unknown error' }
    Write-Host ('  FAIL ' + $line) -ForegroundColor DarkYellow
    return $false
}

Write-Host ('推送分支：' + $Branch) -ForegroundColor Cyan

if (Try-Push -Url $Repo -ViaProxy '' -Label '直连 GitHub') { exit 0 }
if ($Proxy -and (Try-Push -Url $Repo -ViaProxy $Proxy -Label ('代理 ' + $Proxy))) { exit 0 }
foreach ($m in $Mirrors) {
    if (Try-Push -Url $m -ViaProxy '' -Label ('镜像 ' + $m)) { exit 0 }
}

Write-Host ''
Write-Host '四条路都不通。备选：' -ForegroundColor Red
Write-Host '  1) 等网络恢复再跑一次本脚本'
Write-Host '  2) git bundle create update.bundle HEAD  → 拷到能联网的机器再推'
Write-Host '  3) 只把改动的文件 scp 到服务器（见 README「推送慢/连不上 GitHub 时的兜底办法」）'
exit 1
