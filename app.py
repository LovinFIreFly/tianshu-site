# -*- coding: utf-8 -*-
"""
甜薯剧本杀 · 纯 Python 版（Flask 服务端渲染，没有前端框架）

作者：甜薯（junbo）

    python app.py                 启动，浏览器自动开 http://localhost:8000
    python app.py --lan           同一 WiFi 的手机也能访问（测试手机端用）
    python app.py --port 8081     换端口
    python app.py --no-browser    不自动开浏览器
    python app.py --stats         看数据统计（不改任何东西）
    python app.py --backup        把 data 打包成 zip（改数据之前先跑）

结构（改东西照这个找）：
    config.py             配置：端口、经营参数默认值、内置账号
    tianshu/db.py         数据层：数据全在 data/*.json
    tianshu/security.py   密码、登录态、权限装饰器
    tianshu/business.py   ★ 业务规则：算价 / 定金 / 退款 / 拼车 / 信用分 / 核销
    tianshu/views/        路由：public(公开页) · user(客户) · admin(后台)
    tianshu/templates/    页面模板（改文案、排版在这里）
    tianshu/static/       样式表 + 少量脚本

版本流水（别删，换我自己回头看）：
  · 最早是个 index.html 单文件 + Cloudflare 云函数，前端一座山，越改越不敢动
  · 9 月下决定推倒重来：HTML 挪进 legacy/ 存档，只留 Python，页面由服务端渲染
  · 好处：一个页面一个模板文件，改哪块点哪块；坏处：翻页会整页刷新（接受）
  · 待办：DM 结算自动算分成；评价/社区/留言还没搬过来（分阶段做）
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# ---- 依赖：缺啥补啥（首次运行会等十几秒，pip 源是清华的） ----
NEED = {'flask': 'Flask', 'waitress': 'waitress'}


def _ensure_deps():
    missing = []
    for mod, pkg in NEED.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print('首次运行，先装运行库：%s …' % '、'.join(missing))
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q'] + missing)
        print('装好了')


_ensure_deps()

import waitress                                        # noqa: E402
from tianshu import create_app                          # noqa: E402
from tianshu.db import db                               # noqa: E402
from tianshu.business import now_ms                     # noqa: E402
import config                                           # noqa: E402

app = create_app()


# ---- 小工具：给自己用的，不是给客人用的 ----
def show_stats():
    """--stats：看一眼库里有多少东西、账号都是谁"""
    def n(key):
        v = db.read(key)
        return len(v) if isinstance(v, list) else (1 if isinstance(v, dict) else 0)

    print('数据目录：%s' % config.DATA_DIR)
    for label, key in (('账号', 'users'), ('剧本', 'scripts'), ('预约', 'bookings'), ('订单', 'pays'),
                       ('场次', 'sessions'), ('评价', 'reviews'), ('优惠券', 'coupons'),
                       ('通知', 'notices'), ('日志', 'logs')):
        print('  %-6s %s' % (label, n(key)))
    users = db.rows('users')
    if users:
        print('账号明细：')
        for u in users:
            role = '超管' if u.get('super') else u.get('role')
            print('  %-12s %-13s %-5s 信用 %s' % (u.get('username'), u.get('phone'), role, u.get('credit', 100)))


def do_backup():
    """--backup：把 data 打包成 zip 放项目目录（手改数据前先跑一次）"""
    import shutil
    if not os.path.isdir(config.DATA_DIR):
        print('还没有 data 文件夹（没启动过？），没什么可备份的')
        return
    name = os.path.join(config.BASE_DIR, '备份-%s' % time.strftime('%Y%m%d-%H%M'))
    shutil.make_archive(name, 'zip', config.DATA_DIR)
    print('已备份：%s.zip' % name)


def lan_ip():
    """本机在 WiFi 里的地址（手机要用它访问你电脑）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))         # 不会真发数据，只是让系统挑出正在用的网卡
        return s.getsockname()[0]
    except Exception:
        return ''
    finally:
        s.close()


def pick_port(host, start):
    """端口被占就往后找。注意别加 SO_REUSEADDR —— Windows 上它会"抢到"别人的端口，
    看着像空闲其实不是（踩过）"""
    for p in range(start, start + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start


def banner(port, lan=''):
    line = '─' * 54
    print('┌' + line + '┐')
    print('│ 甜薯剧本杀 · Python 版已启动')
    print('│ 电脑上打开   http://localhost:%d' % port)
    if lan:
        print('│ 手机上打开   http://%s:%d  （手机连同一个 WiFi）' % (lan, port))
    else:
        print('│ 手机也能看   把 config.py 里 LAN_MODE 改成 True 再重启')
    print('│ 数据目录     %s' % config.DATA_DIR)
    print('│ 账号         FireFly / FireFly2 / dm测试 / 调试debug（密码都 123123）')
    print('│ 停止         在这个窗口按 Ctrl + C')
    print('└' + line + '┘')
    print('这个窗口要一直开着，网页才打得开。')


def main():
    for arg, attr in (('--lan', 'LAN_MODE'), ('--no-browser', None)):
        if arg in sys.argv and attr:
            setattr(config, attr, True)
        elif arg in sys.argv:
            config.OPEN_BROWSER = False
    if '--port' in sys.argv:
        try:
            config.PORT = int(sys.argv[sys.argv.index('--port') + 1])
        except Exception:
            pass
    if '--stats' in sys.argv:
        show_stats()
        return
    if '--backup' in sys.argv:
        do_backup()
        return

    host = '0.0.0.0' if config.LAN_MODE else '127.0.0.1'
    port = pick_port(host, config.PORT)
    if port != config.PORT:
        print('提示：%d 被占用了（可能已经开着一个窗口），这次用 %d' % (config.PORT, port))
    lan = lan_ip() if config.LAN_MODE else ''
    banner(port, lan)
    if config.OPEN_BROWSER:
        threading.Timer(1.2, lambda: webbrowser.open('http://localhost:%d' % port)).start()
    try:
        server = waitress.create_server(app, host=host, port=port, threads=8)
        server.run()
    except KeyboardInterrupt:
        print('\n已停止。数据都在 data 文件夹里，不会丢。')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('启动出错：%s' % e)
        if sys.stdin and sys.stdin.isatty():
            input('\n按回车关闭窗口…')
