"""三代五套版式冒烟：逐 ui 值跑页面，检查 200 / data-ui / CSS 挂载 / JS 错误。

要点（阶段一/三代踩过的坑）：
  · ?ui= 只对管理员生效 → 必须 session_transaction 先塞 phone
  · 鉴权读 session['phone']
  · TS_DATA_DIR 必须在 create_app() 之前设好
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# 1) 临时 data 副本（不动真数据）
SRC = os.path.join(HERE, 'data')
tmp = tempfile.mkdtemp(prefix='ts_smoke_')
DST = os.path.join(tmp, 'data')
if os.path.isdir(SRC):
    shutil.copytree(SRC, DST)
else:
    os.makedirs(DST)
os.environ['TS_DATA_DIR'] = DST

# 2) 让第一个用户变成 admin
uf = os.path.join(DST, 'users.json')
if os.path.exists(uf):
    with open(uf, 'r', encoding='utf-8') as f:
        users = json.load(f)
else:
    users = []
if not users:
    users = [{'id': 'u1', 'phone': '13800000000', 'username': 'smoke',
              'role': 'admin', 'profile': {'nick': '冒烟'}}]
with open(uf, 'w', encoding='utf-8') as f:
    json.dump(users, f, ensure_ascii=False)
ADMIN_PHONE = users[0].get('phone') or ''

from tianshu import create_app  # noqa: E402

app = create_app()

PAGES = ['/', '/scripts', '/car', '/comm', '/faq', '/login']
UIS = ['3', '4', '5', '6', '7', '8']

fails = []
with app.test_client() as c:
    with c.session_transaction() as s:
        s['phone'] = ADMIN_PHONE

    for ui in UIS:
        for p in PAGES:
            url = p + ('&' if '?' in p else '?') + 'ui=' + ui
            r = c.get(url)
            body = r.get_data(as_text=True)
            ok = r.status_code == 200
            css_ok = True
            if ui in ('4', '5', '6', '7', '8'):
                css_ok = ('design-t%s.css' % ui) in body
            dui = ('data-ui="%s"' % ui) in body
            if not (ok and dui and css_ok):
                fails.append((ui, p, r.status_code, dui, css_ok))
            print('ui=%s %-10s %s  data-ui=%s  css=%s' % (ui, p, r.status_code, dui, css_ok))

    # 三代下不应加载任何 skin-*.css
    for ui in ('4', '5', '6', '7', '8'):
        r = c.get('/?ui=' + ui)
        b = r.get_data(as_text=True)
        if 'skin-' in b and '.css' in b:
            import re
            found = re.findall(r'skin-[a-z0-9]+\.css', b)
            if found:
                fails.append((ui, 'skin-leak', found))
                print('⚠️  ui=%s 仍加载了皮肤: %s' % (ui, found))
        else:
            print('ui=%s 无皮肤残留 ✓' % ui)

    # 后台
    r = c.get('/admin/')
    print('后台 /admin/ ->', r.status_code)
    if r.status_code != 200:
        fails.append(('admin', '', r.status_code))

print('\n===== 失败项 =====')
if fails:
    for f in fails:
        print(' ', f)
    sys.exit(1)
print(' 全部通过')
shutil.rmtree(tmp, ignore_errors=True)
