# -*- coding: utf-8 -*-
import os, sys, traceback

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app
from tianshu.db import db

app = create_app()
print('路由里有 /me 吗：', any(r.rule == '/me' for r in app.url_map.iter_rules()))
for r in app.url_map.iter_rules():
    if 'me' in r.rule and 'static' not in r.rule:
        print('   ', r.rule, sorted(r.methods))

app.config['TESTING'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True
c = app.test_client()
with c.session_transaction() as s:
    s['phone'] = '13552158081'
try:
    r = c.get('/me')
    print('/me status:', r.status_code)
except Exception:
    traceback.print_exc()

# 看看 FireFly 的收藏里到底有什么
u = db.one('users', phone='13552158081')
print('FireFly 收藏：', (u or {}).get('fav'))
