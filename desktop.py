# -*- coding: utf-8 -*-
"""
甜薯剧本杀 · 电脑版（Windows 桌面壳）
=============================================================================
就是"套壳"：开一个自己的窗口，里面装网站 —— 跟手机那个壳 App 一个思路。

    python desktop.py                     # 开线上站（默认）
    python desktop.py --local             # 开本机的服务（http://127.0.0.1:8000）
    python desktop.py --url https://...   # 指到别的地址（比如内网测试机）
    python desktop.py --check             # 只测一下线上通不通，不开窗口

打包成 exe（双击就能用，不用装 Python）：
    powershell -ExecutionPolicy Bypass -File tools\\build_desktop.ps1
产物在 dist/ 里，脚本会顺手复制到 tianshu/static/app/ 供网站下载。

依赖：pywebview（Windows 上走系统自带的 WebView2 / Edge 内核，不用装浏览器）。
没装 pywebview 也不会报错退出 —— 退回用默认浏览器打开，功能一样，只是没有独立窗口。
"""
import argparse
import os
import sys
import urllib.request

SITE = os.environ.get('TIANSHU_SITE', 'https://tianshu.lovinfirefly.cn')
LOCAL = 'http://127.0.0.1:8000'
APP_NAME = '甜薯剧本杀'


def ping(url, timeout=4):
    """/health 是网站自带的健康检查：通不通、是不是这套程序，一下就知道"""
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/health', timeout=timeout) as r:
            return r.status == 200 and b'python-only' in r.read()
    except Exception:
        return False


def pick_url(args):
    """选打开哪个地址：
       ① --url 指定的
       ② --local 强制本机
       ③ 默认线上；**线上连不上就看本机有没有在跑**（店里断网时至少能开本地那份），
          两边都没有就直接开线上 —— 让 WebView 自己显示"打不开"，比转圈强。"""
    if args.url:
        return args.url, '你指定的地址'
    if args.local:
        return LOCAL, '本机服务'
    if ping(SITE):
        return SITE, '线上站'
    if ping(LOCAL, timeout=2):
        return LOCAL, '本机服务（线上连不上，退回本机）'
    return SITE, '线上站（刚才没连上，先开着看看）'


def main():
    ap = argparse.ArgumentParser(description='甜薯剧本杀 · 电脑版')
    ap.add_argument('--url', default='', help='要打开的网址')
    ap.add_argument('--local', action='store_true', help='打开本机 http://127.0.0.1:8000')
    ap.add_argument('--check', action='store_true', help='只测连通性，不开窗口')
    args = ap.parse_args()

    if args.check:
        for name, url in (('线上', SITE), ('本机', LOCAL)):
            print('%-4s %-40s %s' % (name, url, '通' if ping(url) else '不通'))
        return

    url, why = pick_url(args)
    print('%s · 正在打开：%s（%s）' % (APP_NAME, url, why))

    try:
        import webview
    except ImportError:
        print('这台机器没有 pywebview（打包成 exe 的版本自带，不影响）。')
        print('先用默认浏览器打开同一个地址 —— 功能一样，只是没有独立窗口。')
        import webbrowser
        webbrowser.open(url)
        return

    win = webview.create_window(
        APP_NAME, url,
        width=1180, height=840, min_size=(360, 560),
        text_select=True,                      # 允许选中文字（客人要复制核销码/微信号）
    )

    # 打开新标签的链接（比如小客服的链接）交给系统浏览器，别在壳里乱蹦
    def _new_window(u):
        if u:
            import webbrowser
            webbrowser.open(u)
        return False

    try:
        win.events.new_window += _new_window
    except Exception:
        pass

    icon = None
    for cand in (os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'tianshu', 'static', 'icons', 'icon.ico'),
                 os.path.join(getattr(sys, '_MEIPASS', ''), 'icon.ico')):
        if cand and os.path.exists(cand):
            icon = cand
            break
    try:
        webview.start(icon=icon)
    except TypeError:                          # 老版本 pywebview 不认 icon 参数
        webview.start()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('启动出错：%s' % e)
        try:
            if sys.stdin and sys.stdin.isatty():
                input('\n按回车关闭…')
        except Exception:
            pass
