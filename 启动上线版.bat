@echo off
title 甜薯剧本杀 上线版（本地服务 + Cloudflare 隧道）
cd /d "%~dp0"
echo ============================================================
echo   这个窗口做两件事：
echo     1) 在本机跑网站（http://localhost:8000）
echo     2) 用 Cloudflare 隧道把它挂到公网
echo.
echo   两种模式，本脚本自动判断：
echo     [固定域名] 配过隧道（%%USERPROFILE%%\.cloudflared\config.yml）就走这个，
echo                网址永远是你自己的域名（例如 https://tianshu.lovinfirefly.cn）
echo     [临时网址] 还没配，就打印一个 https://xxxx.trycloudflare.com，
echo                发给朋友能马上用，但每次重启都会变
echo.
echo   注意：隧道一开，拿到网址的人就能访问，后台密码别外传。
echo   想关掉：直接关这个窗口（网站和公网入口一起停）。
echo ============================================================
echo.
set PY=
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py
if not defined PY goto nopython

rem --- 起本地服务（新窗口，方便单独看日志）---
start "甜薯本地服务" cmd /k "%PY% app.py --no-browser"
echo 本地服务已在新窗口启动，等 3 秒...
timeout /t 3 >nul

rem --- 起公网隧道：有配置文件就用固定域名，没有就用临时网址 ---
where cloudflared >nul 2>nul
if errorlevel 1 goto notunnel
if not exist "%USERPROFILE%\.cloudflared\config.yml" goto quick
echo.
echo [固定域名模式] 读 %USERPROFILE%\.cloudflared\config.yml，按里面配好的域名对外服务。
echo.
cloudflared tunnel run
goto end

:quick
echo.
echo [临时网址模式] 还没配固定域名，下面会出现一个 https://xxxx.trycloudflare.com，
echo 把它发给朋友就能用（每次重启都会变）。
echo 想固定成自己的域名：看 README「部署」第 1 节，四条命令配一次就够。
echo.
cloudflared tunnel --url http://localhost:8000
goto end

:notunnel
echo.
echo [X] 没找到 cloudflared（Cloudflare 隧道的程序）
echo     装它：在 PowerShell 里跑一行：
echo         winget install --id Cloudflare.cloudflared -e
echo     装完再双击本文件即可。
echo.
echo   （本地服务已经在另一个窗口跑着，你现在就能用 http://localhost:8000）
pause

:nopython
echo [X] 没有找到 Python，先装 Python 再回来
pause
goto end

:end
