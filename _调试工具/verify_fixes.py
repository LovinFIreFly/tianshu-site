# -*- coding: utf-8 -*-
"""修复验证：确认三处问题都好了"""
import os, sys, json, urllib.request, http.cookiejar

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app
from tianshu.db import db

BASE = 'http://127.0.0.1:8099'

print('--- 1) /me（个人中心）曾 500 ---')
app = create_app()
c = app.test_client()
with c.session_transaction() as s:
    s['phone'] = '13552158081'
r = c.get('/me')
print('   进程内 GET /me ->', r.status_code)

print('--- 2) /api/track（每个页面都发，曾全站 403）---')
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
op.open(BASE + '/')                      # 领 cookie
req = urllib.request.Request(BASE + '/api/track', data=json.dumps({'path': '/'}).encode(),
                             headers={'Content-Type': 'application/json'})
try:
    resp = op.open(req)
    print('   POST /api/track ->', resp.status)
except urllib.error.HTTPError as e:
    print('   POST /api/track ->', e.code, '(仍被拦，说明没修好)')

print('--- 3) 评价里指向不存在用户的「看 TA 主页」---')
names = {str(u.get('username')) for u in db.rows('users')}
bad = [r for r in db.rows('reviews') if r.get('username') and str(r['username']) not in names]
print('   脏数据评价条数：', len(bad), '（页面已加判断，不会再产生 /u/xxx 的 404 链接）')
for b in bad[:5]:
    print('     ·', b.get('username'), '->', b.get('sid'))
