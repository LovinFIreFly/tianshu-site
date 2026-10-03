# -*- coding: utf-8 -*-
"""体检 B：强制切到「一代界面」(ui_ver=1)，把所有 GET 路由跑一遍，揪出模板缺失/字段缺失的 500。"""
import os, re, sys, traceback

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app, business
from tianshu.db import db

app = create_app()
app.config['TESTING'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True
business.ui_ver = lambda: '1'      # 强制一代

ROLES = [('游客', None), ('客户', '调试debug'), ('DM', 'dm测试'), ('超管', 'FireFly')]
phone_of = {u.get('username'): u.get('phone') for u in db.rows('users')}
sid = str((db.rows('scripts') or [{}])[0].get('id', 1))


def fill(rule):
    p = re.sub(r'<int:[a-zA-Z_]+>', '1', rule)
    p = re.sub(r'<sid>', sid, p)
    p = re.sub(r'<username>', 'FireFly', p)
    p = re.sub(r'<[^>]+>', '1', p)
    return p


for label, uname in ROLES:
    c = app.test_client()
    with c.session_transaction() as s:
        if uname:
            s['phone'] = phone_of.get(uname)
        else:
            s.pop('phone', None)
    print('\n===== 一代界面 / %s =====' % label)
    for r in app.url_map.iter_rules():
        if 'GET' not in r.methods or r.rule.startswith(('/static', '/m/')):
            continue
        path = fill(r.rule)
        try:
            resp = c.get(path, follow_redirects=False)
            if resp.status_code >= 400:
                print('  %s  %s' % (resp.status_code, path))
                if resp.status_code == 500:
                    try:
                        c.get(path)
                    except Exception:
                        tb = traceback.format_exc().splitlines()
                        print('      ' + tb[-1])
        except Exception:
            tb = traceback.format_exc().splitlines()
            print('  EXC  %-38s %s' % (path, tb[-1]))
