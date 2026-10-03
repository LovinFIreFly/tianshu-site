# -*- coding: utf-8 -*-
"""体检 E：真实的写操作全流程（登录 → 预约 → 后台核销 → 完成 → 客户评价），
任何一步 4xx/5xx 或异常都打印出来（在进程内跑，带 CSRF 令牌）"""
import os, sys, traceback, time

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app
from tianshu.db import db

app = create_app()
app.config['TESTING'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True


def client():
    c = app.test_client()
    c.get('/')
    return c


def token(c):
    """从测试客户端的 cookie jar 里取 csrf 令牌"""
    for cookie in getattr(c, '_cookies', {}).values():
        for ck in (cookie.values() if hasattr(cookie, 'values') else [cookie]):
            if getattr(ck, 'key', None) == 'csrf':
                return ck.value
    # 兜底：直接从首页响应头里读
    r = c.get('/')
    for h in r.headers.getlist('Set-Cookie') if hasattr(r.headers, 'getlist') else []:
        if h.startswith('csrf='):
            return h.split(';')[0].split('=', 1)[1]
    return ''


def post(c, path, data, note=''):
    data = dict(data)
    data.setdefault('_csrf', token(c))
    try:
        r = c.post(path, data=data, follow_redirects=False)
        flag = 'OK ' if r.status_code < 400 else 'BAD'
        print('  [%s] %s %-28s -> %s' % (flag, note, path, r.status_code))
        if r.status_code >= 400:
            print('       body:', r.get_data(as_text=True)[:200].replace('\n', ' '))
        return r
    except Exception:
        print('  [EXC] %s %s' % (note, path))
        traceback.print_exc()
        return None


def login(c, account, pw='123123'):
    return post(c, '/login', {'account': account, 'password': pw}, '登录%s' % account)


print('=== 1. 客户登录 + 预约 ===')
c = client()
login(c, '调试debug')
sid = (db.rows('scripts') or [{}])[0].get('id')
day = time.strftime('%Y-%m-%d', time.localtime(time.time() + 86400))
post(c, '/book', {'sid': sid, 'ts_day': day, 'time': '19:00', 'players': '2', 'mode': 'car'}, '提交预约')
print('  预约数：', len(db.rows('bookings')))

print('\n=== 2. 客户本人的页面 ===')
for p in ['/me', '/booking', '/car']:
    try:
        r = c.get(p)
        print('  %s -> %s' % (p, r.status_code))
    except Exception:
        print('  %s -> EXC' % p)
        traceback.print_exc()

print('\n=== 3. 超管：后台核销 / 完成 / 评价开关 ===')
a = client()
login(a, 'FireFly')
for p in ['/admin', '/admin?tab=bookings', '/admin?tab=reviews', '/admin?tab=users', '/dm']:
    try:
        r = a.get(p)
        print('  %s -> %s' % (p, r.status_code))
    except Exception:
        print('  %s -> EXC' % p)
        traceback.print_exc()

bid = None
for b in db.rows('bookings'):
    if b.get('status') == 'booked':
        bid = b.get('id')
        break
if bid:
    post(a, '/admin/verify', {'bid': bid}, '核销到场')
    post(a, '/admin/complete', {'bid': bid}, '确认完成') if any(
        r.rule == '/admin/complete' for r in app.url_map.iter_rules()) else print('  (无 /admin/complete 路由)')

print('\n=== 4. 客户评价 ===')
c2 = client()
login(c2, '调试debug')
if bid:
    post(c2, '/review/%s' % bid, {'rating': '5', 'text': '测试评价'}, '提交评价')

print('\n=== 5. 所有 POST 路由清单（人工核对用）===')
for r in app.url_map.iter_rules():
    if 'POST' in r.methods and not r.rule.startswith('/static'):
        print('  ', r.rule)
