@echo off
title 甜薯剧本杀 本地版
cd /d "%~dp0"
echo ============================================================
echo   甜薯剧本杀 - 本地版启动中，请稍等 2~3 秒...
echo   网页会自动打开： http://localhost:8000
echo   这个窗口要一直开着，关掉窗口就等于关闭本地网站
echo ============================================================
echo.
set PY=
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py
if not defined PY goto nopython
echo 正在启动，请不要关闭这个窗口...
echo.
%PY% app.py
echo.
echo 本地网站已停止（数据都保存在 data 文件夹里，不会丢）
pause
exit /b
:nopython
echo [X] 没有找到 Python
echo     请到 python.org 下载安装，安装时务必勾选 "Add python.exe to PATH"
echo.
pause
