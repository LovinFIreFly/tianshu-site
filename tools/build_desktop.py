# -*- coding: utf-8 -*-
"""
把 desktop.py 打包成 Windows 的 exe（店里电脑双击就能用，不用装 Python）
=============================================================================
    python tools/build_desktop.py

做完这几件事：
  ① 装打包依赖（pywebview = 开窗口，pyinstaller = 打包）
  ② 把 icon-512.png 转成 icon.ico（没装 Pillow 就跳过，不影响）
  ③ PyInstaller 出 exe → 复制到 tianshu/static/app/（网站上的「电脑版下载」指它）
  ④ 用 --check 自测一下 exe 能不能起来

中间文件丢在 _build / _dist（下划线开头，.gitignore 已经挡住）。
产物约 20–40MB；第一次打包两三分钟。

为什么不写成 .ps1：Windows PowerShell 会按 GBK 读 .ps1，
里面的中文会把字符串引号搞坏（这个坑本仓库踩过）—— 逻辑放 .py 里最稳。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = 'https://mirrors.aliyun.com/pypi/simple/'
ICON_PNG = os.path.join(ROOT, 'tianshu', 'static', 'icons', 'icon-512.png')
ICON_ICO = os.path.join(ROOT, 'tianshu', 'static', 'icons', 'icon.ico')
APP_DIR = os.path.join(ROOT, 'tianshu', 'static', 'app')
EXE_NAME = 'tianshu-desktop'


def run(cmd, **kw):
    print('   $ %s' % ' '.join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=ROOT, **kw)


def pip(*pkgs):
    r = run([sys.executable, '-m', 'pip', 'install', '-q', '-i', MIRROR] + list(pkgs))
    if r.returncode != 0:                       # 连不上镜像就退回默认源
        r = run([sys.executable, '-m', 'pip', 'install', '-q'] + list(pkgs))
    return r.returncode == 0


def main():
    print('① 装打包依赖（pywebview / pyinstaller）…')
    pip('--upgrade', 'pip')
    pip('pywebview', 'pyinstaller')
    probe = subprocess.run([sys.executable, '-c', 'import webview, PyInstaller'],
                           cwd=ROOT, capture_output=True)
    if probe.returncode != 0:
        print('   [X] 依赖没装上，检查网络/代理')
        print(probe.stderr.decode('utf-8', 'replace')[-600:])
        return 1
    print('   依赖就绪')

    print('② 准备图标…')
    if os.path.exists(ICON_PNG):
        try:
            from PIL import Image
            Image.open(ICON_PNG).save(ICON_ICO, sizes=[(16, 16), (32, 32), (48, 48),
                                                       (64, 64), (128, 128), (256, 256)])
            print('   icon.ico 好了')
        except ImportError:
            print('   （没装 Pillow，跳过图标 —— 不影响打包）')
        except Exception as e:
            print('   （图标没转成：%s，跳过）' % e)

    print('③ 打包（第一次两三分钟，别关窗口）…')
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
           '--name', EXE_NAME, '--distpath', '_dist', '--workpath', '_build',
           '--specpath', '_build', '--collect-all', 'webview',
           '--hidden-import', 'clr', '--hidden-import', 'clr_loader']
    if os.path.exists(ICON_ICO):
        cmd += ['--icon', ICON_ICO]
    cmd.append('desktop.py')
    if run(cmd).returncode != 0:
        print('   [X] 打包失败，看上面的报错')
        return 1

    exe = os.path.join(ROOT, '_dist', EXE_NAME + '.exe')
    if not os.path.exists(exe):
        print('   [X] 没找到产物 %s' % exe)
        return 1

    print('④ 自测（--check 只测连通性，不开窗口）…')
    try:
        r = subprocess.run([exe, '--check'], cwd=ROOT, capture_output=True, timeout=60)
        print('   退出码 %d（0 = 正常起来过）' % r.returncode)
        out = (r.stdout or b'').decode('utf-8', 'replace').strip()
        if out:
            print('   ' + out.replace('\n', '\n   '))
    except subprocess.TimeoutExpired:
        print('   超时（可能被杀毒软件拦着扫），先跳过')

    print('⑤ 复制到网站目录（供下载）…')
    os.makedirs(APP_DIR, exist_ok=True)
    dest = os.path.join(APP_DIR, EXE_NAME + '.exe')
    shutil.copy2(exe, dest)
    print('   好了：%s（%.1f MB）' % (dest, os.path.getsize(dest) / 1024 / 1024))
    print('')
    print('双击这个 exe 就能用。它打开线上站；店里断网时自动退回本机服务')
    print('（前提是本机 8000 在跑：python app.py --no-browser）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
