# -*- coding: utf-8 -*-
"""全站路由体检：用 4 种身份（游客/客户/DM/超管）把所有 GET 路由跑一遍，
把 500 的真实堆栈、403/404 全部列出来。"""
import os, re, sys, traceback

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app      # noqa: E402
from tianshu.db import db           # noqa: E402

app = create_app()
app.config['TESTING'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True

ROLES = [
    ('游客', None),
    ('客户', '调试debug'),
    ('DM', 'dm测试'),
    ('超管', 'FireFly'),
]

phone_of = {}
for u in db.rows('users'):
    phone_of[u.get('username')] = u.get('phone')

# 真实存在的 id，避免用假 id 制造假 404
sid = str((db.rows('scripts') or [{}])[0].get('id', 1))
bid = str((db.rows('bookings') or [{}])[0].get('id', 1))
rid = str((db.rows('reviews') or [{}])[0].get('id', 1))

rules = []
for r in app.url_map.iter_rules():
    # ⚠️ 注意：'/m' 会误伤 /me（个人中心），必须用 '/m/'
    if 'GET' not in r.methods or r.rule.startswith(('/static', '/m/')):
        continue
    rules.append(r.rule)

def fill(rule):
    p = rule
    p = re.sub(r'<int:[a-zA-Z_]+>', '1', p)
    p = re.sub(r'<sid>', sid, p)
    p = re.sub(r'<bid>', bid, p)
    p = re.sub(r'<rid>', rid, p)
    p = re.sub(r'<username>', 'FireFly', p)
    p = re.sub(r'<[^>]+>', '1', p)
    return p

bad = {}
for label, uname in ROLES:
    c = app.test_client()
    with c.session_transaction() as s:
        s['phone'] = phone_of.get(uname) if uname else None
        if s['phone'] is None:
            s.pop('phone', None)
    print('\n========== %s ==========' % label)
    for rule in rules:
        path = fill(rule)
        try:
            r = c.get(path, follow_redirects=False)
            st = r.status_code
            if st >= 400:
                bad.setdefault((st, path, label), 0)
                bad[(st, path, label)] += 1
                print('  %s  %-40s %s' % (st, path, rule))
                if st == 500:
                    # 再取一次，让异常抛出来看堆栈
                    try:
                        c.get(path)
                    except Exception:
                        tb = traceback.format_exc().splitlines()
                        print('      ' + tb[-1])
                        for ln in tb:
                            if 'templates' in ln or 'views' in ln or 'business' in ln:
                                print('      ' + ln.strip())
        except Exception:
            tb = traceback.format_exc().splitlines()
            print('  EXC  %-40s %s' % (path, tb[-1]))

print('\n===== 汇总（去重）=====')
for (st, path, label) in sorted(bad):
    print(' %s  %-38s [%s]' % (st, path, label))
