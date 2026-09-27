# -*- coding: utf-8 -*-
"""
标签页与页面速度自检

后台/我的这些页面现在都是「一个网址 + 标签切换」，这个脚本把每个标签挨个点一遍，
顺便报出每个页面的响应时间（怀疑慢的时候跑它，一眼看出是哪一页拖后腿）。

用法：
    python app.py --no-browser           # 另开一个窗口起服务
    python tools/tabcheck.py             # 本窗口跑检查（默认连 8000 端口）
    set BASE=http://127.0.0.1:8121       # 服务在别的端口就设一下这个环境变量
"""
import http.cookiejar
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('BASE', 'http://127.0.0.1:8000')

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass


def login(account, password):
    """登录并返回一个带 cookie 的连接（相当于浏览器窗口）"""
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(urllib.request.Request(BASE + '/login', method='POST',
                                   data=urllib.parse.urlencode({'account': account, 'password': password}).encode()),
            timeout=10).read()
    return op


def get(op, path):
    t0 = time.time()
    try:
        r = op.open(BASE + path, timeout=15)
        return r.status, r.read(), (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read(), (time.time() - t0) * 1000


def main():
    print('目标：%s\n' % BASE)
    adm = login('FireFly', '123123')

    print('=== 后台（一个网址 /admin?tab=）===')
    for tab, name in [('dash', '概览'), ('sessions', '排期'), ('bookings', '预约'), ('users', '客户'),
                      ('reviews', '评价'), ('messages', '留言'), ('scripts', '剧本'), ('orders', '订单'),
                      ('guides', '学本'), ('notice', '通知'), ('dm', 'DM结算'), ('backup', '备份'),
                      ('reports', '举报'), ('logs', '日志')]:
        s, b, ms = get(adm, '/admin?tab=' + tab)
        ok = 'tabbar' in b.decode('utf-8', 'replace')          # 有没有渲染出标签栏
        print('  %-8s %-4s %5.0fms %6.1fKB  标签栏:%s' % (name, s, ms, len(b) / 1024, 'OK' if ok else '缺'))

    print('\n=== 我的（一个网址 /me?tab=）===')
    for tab, name in [('bookings', '我的预约'), ('orders', '订单'), ('coupons', '券'),
                      ('notices', '消息'), ('profile', '资料')]:
        s, b, ms = get(adm, '/me?tab=' + tab)
        print('  %-8s %-4s %5.0fms %6.1fKB' % (name, s, ms, len(b) / 1024))

    dm = login('dm测试', '123123')
    print('\n=== DM 工作台（/dm?tab=）===')
    for tab, name in [('today', '今日'), ('credit', '我的客人'), ('guides', '学本资料')]:
        s, b, ms = get(dm, '/dm?tab=' + tab)
        print('  %-8s %-4s %5.0fms %6.1fKB' % (name, s, ms, len(b) / 1024))

    print('\n=== 客户常逛的页面 ===')
    for u in ('/', '/scripts', '/car', '/comm'):
        s, b, ms = get(adm, u)
        print('  %-9s %-4s %5.0fms %6.1fKB' % (u, s, ms, len(b) / 1024))

    print('\n=== 旧网址还能不能开（当书签用）===')
    for u in ('/admin/bookings', '/admin/users', '/dm/credit'):
        s, b, ms = get(adm, u)
        print('  %-18s %s' % (u, s))

    print('\n看数字的方法：<100ms 正常；某一页明显比别人慢很多，就把那页后面的数据量报给我。')


if __name__ == '__main__':
    main()
