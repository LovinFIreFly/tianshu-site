cd "C:\Users\junbo\Desktop\网站"
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$env:PYTHONIOENCODING = "utf-8"
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
Start-Process -FilePath $py -ArgumentList "app.py --no-browser" -WindowStyle Hidden -RedirectStandardOutput _s.log
Start-Sleep 8

Write-Host "=== 渲染检查（新骨架 + 新首页） ==="
& $py -c @"
import urllib.request, http.cookiejar
B='http://127.0.0.1:8000'
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def get(u): return op.open(urllib.request.Request(B+u, headers={'User-Agent':'Mozilla/5.0'}), timeout=10).read().decode('utf-8')
for u in ['/','/scripts','/car','/me','/login','/comm']:
    try:
        h=get(u); print('  %-8s 200  site-nav=%s  sec-head=%s' % (u, 'site-nav' in h, 'sec-head' in h if u=='/' else '-'))
    except Exception as e:
        print('  %-8s ERR %s' % (u, str(e)[:50]))
"@

Write-Host "=== 业务自检 ==="
$o = & $py tools/smoke_test.py 2>&1 | Out-String
(($o -split "`n") | Select-Object -Last 2 | Out-String).Trim()
($o -split "`n") | Where-Object { $_ -match '\[!!\]' } | Select-Object -First 6

Remove-Item detect.ps1, detect2.ps1, deploy.ps1, _s.log -Force -ErrorAction SilentlyContinue
Write-Host "=== 提交 ==="
$env:Path = "C:\Program Files\Git\cmd;" + $env:Path
git add -A
git -c user.name="LovinFireFly" -c user.email="lovinfirefly@users.noreply.github.com" commit -m "原创新站骨架重建：①base.html 全新玻璃导航(.site-nav/.nav-row/.brand/.tab-dock) ②style.css 重写导航/页脚/手机栏+新增影院hero/区块标题/行列表组件 ③noir/riso 皮肤适配新骨架 ④home.html 重写为沉浸影院结构" 2>&1 | Out-String | Select-String -Pattern "changed|insert|file|nothing"
Write-Host "=== 推送 ==="
$ok=$false
for($i=1;$i -le 5;$i++){
  $r=git push 2>&1 | Out-String
  if($r -match 'python-rewrite -> python-rewrite'){"  推送成功 [OK]";$ok=$true;break}
  "  第 $i 次重试...";Start-Sleep 5
}
if(-not $ok){$r2=git -c http.proxy=http://127.0.0.1:12000 push 2>&1|Out-String; if($r2 -match 'python-rewrite -> python-rewrite'){"  代理推送成功"}else{"  推送失败，请手动 git push"}}
git --no-pager log --oneline -1
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
