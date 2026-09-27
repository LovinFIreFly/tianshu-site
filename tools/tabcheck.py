# -*- coding: utf-8 -*-
"""
单页结构自检：确认「一个网址里切面板」真的成立

检查三件事：
  ① /admin、/dm、/me 每页里到底装了几个面板（data-tab / tabpane 数量对不对）
  ② 页面里有没有偷偷留着的子网址（<a href="?tab=..."> 这种，一个都不该有）
  ③ 老网址（/admin/bookings）是不是 302 转回 /admin#bookings
顺便把每个页面的响应时间报出来（怀疑慢的时候跑它）

用法：
    python app.py --no-browser        # 另开一个窗口起服务
    python tools/tabcheck.py          # 本窗口跑；端口不是 8000 就设 BASE 环境变量
"""
import http.cookiejar
import os
import re
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

fails = []


def check(name, ok, note=''):
    print('  %s %-34s %s' % ('[OK]' if ok else '[!!]', name, note))
    if not ok:
        fails.append(name)


def login(account, password):
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.open(urllib.request.Request(BASE + '/login', method='POST',
                                   data=urllib.parse.urlencode({'account': account, 'password': password}).encode()),
            timeout=15).read()
    op._jar = jar                   # 留给 peek() 用（不跟着跳转的时候要带上登录 cookie）
    return op


def get(op, path):
    t0 = time.time()
    try:
        r = op.open(BASE + path, timeout=20)
        return r.status, r.read().decode('utf-8', 'replace'), (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), (time.time() - t0) * 1000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def peek(op, path):
    """不跟着跳转，看看它给我们指哪儿去"""
    op2 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(op._jar), NoRedirect())
    try:
        r = op2.open(BASE + path, timeout=15)
        return r.status, r.headers.get('Location', '')
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Location', '') if e.headers else ''


def main():
    print('目标：%s\n' % BASE)
    adm = login('FireFly', '123123')

    print('=== 后台 /admin：14 个面板装在一页里 ===')
    s, html, ms = get(adm, '/admin')
    panes = re.findall(r'class="tabpane[^"]*"\s+data-tab="([a-z]+)"', html)
    check('/admin 能打开', s == 200, '%dms  %dKB' % (ms, len(html) / 1024))
    check('装了 14 个面板', len(panes) == 14, '实际 %d 个：%s' % (len(panes), '、'.join(panes)))
    check('标签是按钮不是链接（不留子网址）', 'data-tabs="admin"' in html and
          not re.search(r'<a[^>]+href="\?tab=', html))
    check('页面里有切换脚本', '/static/js/tabs.js' in html)
    check('默认只亮第一个面板', html.count('class="tabpane on"') == 1)
    # 各面板的标题得真的在页里（别只是空壳 div）——注意空库时页面本来就小，不能按体积判断
    for text in ('预约管理', '操作日志', '客户', '结算'):
        check('面板内容在页里：%s' % text, text in html)

    print('\n=== 老网址还能用（302 转到 /admin#标签）===')
    for old, want in [('/admin/bookings', '#bookings'), ('/admin/users', '#users'),
                      ('/admin/logs', '#logs'), ('/admin/messages', '#messages')]:
        code, loc = peek(adm, old)
        check('%s → %s' % (old, want), code in (301, 302, 303, 308) and loc.endswith(want),
              '%s %s' % (code, loc))

    print('\n=== DM /dm：4 个面板 ===')
    dm = login('dm测试', '123123')
    s, html, ms = get(dm, '/dm')
    check('/dm 能打开', s == 200, '%dms  %dKB' % (ms, len(html) / 1024))
    check('装了 4 个面板', len(re.findall(r'class="tabpane[^"]*"\s+data-tab=', html)) == 4,
          '今日 / 我的客人 / 我的成长 / 学本资料')

    print('\n=== 我的 /me：5 个面板 ===')
    s, html, ms = get(adm, '/me')
    check('/me 能打开', s == 200, '%dms  %dKB' % (ms, len(html) / 1024))
    check('装了 5 个面板', len(re.findall(r'class="tabpane[^"]*"\s+data-tab=', html)) == 5)
    # 各栏的内容都在页里（不是空壳）。有数据和没数据时显示的不一样，两种都认
    for name, ok in (('预约栏', '还没有预约记录' in html or '到店报这个码' in html),
                     ('订单栏', '还没有订单' in html or '待付定金' in html),
                     ('券栏', '抵扣券' in html or '还没有券' in html),
                     ('留言栏', '给店家留言' in html),
                     ('资料栏', '账号安全' in html and '我的邀请码' in html)):
        check('「我的」%s有内容' % name, ok)

    print('\n=== 客户常逛的页面（速度）===')
    for u in ('/', '/scripts', '/car', '/comm'):
        s, b, ms = get(adm, u)
        check(u, s == 200, '%dms  %dKB' % (ms, len(b) / 1024))

    print('')
    if fails:
        print('有 %d 项没过：%s' % (len(fails), '、'.join(fails)))
        return 1
    print('全部通过 —— 后台/DM/我的 都是一个网址，点标签不再产生子网址。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
