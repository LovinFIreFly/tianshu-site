@echo off
title 甜薯剧本杀 上线版（本地服务 + 公网隧道）
cd /d "%~dp0"
echo ============================================================
echo   这个窗口做两件事：
echo     1) 在本机跑网站（http://localhost:8000）
echo     2) 用 Cloudflare 隧道把它挂到公网（会打印一个 https 网址）
echo.
echo   注意：隧道一开，拿到网址的人就能访问，别把后台密码告诉外人。
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

rem --- 起公网隧道 ---
where cloudflared >nul 2>nul
if errorlevel 1 goto notunnel
echo.
echo 隧道启动中，下面会出现一个 https://xxxx.trycloudflare.com 的网址，
echo 把它发给朋友就能用（这个网址每次重启都会变）。
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
