@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   甜薯剧本杀 - 本地版启动中...
echo   浏览器稍后会自动打开 http://localhost:8000
echo   想停止运行：关掉这个黑窗口，或按 Ctrl + C
echo ============================================================
set PY=
rem ① 优先用正式安装的 Python 3.12（推荐）
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
rem ② 其次是系统 PATH 里的 python / py
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (where py >nul 2>nul && set PY=py)
rem ③ 最后的备用（安装助手附带的那份）
if not defined PY if exist "C:\Users\junbo\.workbuddy\binaries\python\versions\3.14.3\python.exe" set PY="C:\Users\junbo\.workbuddy\binaries\python\versions\3.14.3\python.exe"
if not defined PY (
  echo [x] 没有找到 Python。
  echo     请到 python.org 下载安装，安装时务必勾选 "Add python.exe to PATH"
  pause
  exit /b
)
start "" cmd /c "timeout /t 3 >nul & start "" http://localhost:8000"
%PY% app.py
echo.
echo 本地网站已停止。数据都保存在 data 文件夹里，不会丢。
pause
