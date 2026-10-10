"""真实浏览器验证（v2）：造已知密码的 admin，Playwright 走真登录，
再逐 ui 打开页面，收集 console 错误 / 页面异常 / 截图 / 几何。"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根（脚本放在 _调试工具/ 下）
sys.path.insert(0, HERE)

SRC = os.path.join(HERE, 'data')
tmp = tempfile.mkdtemp(prefix='ts_shot_')
DST = os.path.join(tmp, 'data')
if os.path.isdir(SRC):
    shutil.copytree(SRC, DST)
else:
    os.makedirs(DST)
os.environ['TS_DATA_DIR'] = DST

PHONE = '13800000000'
PASSWORD = 'smoke123456'

# 造/覆盖一个已知密码的 admin（要 hash_password，所以先 import）
from tianshu.security import hash_password  # noqa: E402

uf = os.path.join(DST, 'users.json')
users = []
if os.path.exists(uf):
    with open(uf, 'r', encoding='utf-8') as f:
        users = json.load(f)
me = None
for u in users:
    if str(u.get('phone')) == PHONE:
        me = u
        break
if me is None:
    me = {'id': 'u-shot', 'phone': PHONE, 'username': 'shot'}
    users.append(me)
me['password'] = hash_password(PASSWORD)
me['role'] = 'admin'
me['roles'] = ['admin']
me.setdefault('profile', {})['nick'] = '截图'
with open(uf, 'w', encoding='utf-8') as f:
    json.dump(users, f, ensure_ascii=False)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = free_port()
env = dict(os.environ)
env['TS_DATA_DIR'] = DST
srv = subprocess.Popen(
    [sys.executable, '-u', '-c',
     'import sys; sys.path.insert(0, r"%s"); from tianshu import create_app;'
     'create_app().run(host="127.0.0.1", port=%d, debug=False, use_reloader=False)'
     % (HERE, PORT)],
    cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

for _ in range(80):
    try:
        socket.create_connection(('127.0.0.1', PORT), 0.4).close()
        break
    except OSError:
        time.sleep(0.35)
else:
    srv.terminate()
    print('服务起不来')
    sys.exit(1)

OUT = os.path.join(HERE, '_shots_gen3')
os.makedirs(OUT, exist_ok=True)

from playwright.sync_api import sync_playwright  # noqa: E402

UIS = [('3', 'rail'), ('4', 'open'), ('5', 'playhouse'), ('6', 'casefile'),
       ('7', 'film'), ('8', 'noticeboard')]
problems = []

try:
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 1440, 'height': 900})
        pg = ctx.new_page()

        # 真登录
        pg.goto('http://127.0.0.1:%d/login' % PORT, wait_until='load')
        pg.fill('input[name="account"]', PHONE)
        pg.fill('input[name="password"]', PASSWORD)
        pg.click('button[type="submit"], input[type="submit"]')
        pg.wait_for_timeout(1400)
        got = pg.evaluate('document.body.innerText.slice(0,80)')
        print('登录后页面片段:', got.replace('\n', ' / ')[:80])

        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append('PAGEERROR: %s' % e))

        for ui, name in UIS:
            errs.clear()
            pg.goto('http://127.0.0.1:%d/?ui=%s' % (PORT, ui), wait_until='load')
            pg.wait_for_timeout(1200)
            pg.evaluate('window.scrollTo(0, document.body.scrollHeight*0.42)')
            pg.wait_for_timeout(800)
            pg.evaluate('window.scrollTo(0, 0)')
            pg.wait_for_timeout(500)
            pg.screenshot(path=os.path.join(OUT, '%s-d.png' % name))
            geo = pg.evaluate('''() => {
              const m = document.querySelector('.v3main');
              return {ui: document.documentElement.getAttribute('data-ui'),
                      docW: document.documentElement.scrollWidth,
                      mainW: m ? Math.round(m.getBoundingClientRect().width) : -1};
            }''')
            print('%-12s %s  %s' % (name, geo, ('ERR:' + str(errs[:2])) if errs else 'ok'))
            if errs:
                problems.append((name, errs[:3]))
        ctx.close()
        br.close()
finally:
    srv.terminate()

print('\n===== JS 错误 =====')
print(' 无' if not problems else '')
for p in problems:
    print(' ', p)
shutil.rmtree(tmp, ignore_errors=True)
