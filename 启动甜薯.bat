@echo off
chcp 65001 >nul
title 甜薯剧本杀 · 本地服务
cd /d "%~dp0"

REM 若服务已在跑则直接开浏览器
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8099/health >nul 2>&1
if not errorlevel 1 (
  start "" http://127.0.0.1:8099/
  goto :eof
)

echo 正在启动甜薯剧本杀本地服务（首次启动需几秒）...
start "甜薯服务" /min python app.py
timeout /t 5 >nul
start "" http://127.0.0.1:8099/

echo.
echo 已为你打开浏览器。本窗口可最小化，但请不要关闭它（关闭即停止服务）。
echo 如需停止服务，直接关闭名为「甜薯服务」的后台窗口即可。
pause
