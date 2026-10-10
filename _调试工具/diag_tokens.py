"""量关键元素的 computed color / font，确认令牌是否生效。"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
SRC = os.path.join(HERE, 'data')
tmp = tempfile.mkdtemp(prefix='ts_d4_'); DST = os.path.join(tmp, 'data')
shutil.copytree(SRC, DST); os.environ['TS_DATA_DIR'] = DST
from tianshu.security import hash_password
PHONE, PW = '13800000000', 'smoke123456'
uf = os.path.join(DST, 'users.json'); us = json.load(open(uf, encoding='utf-8'))
me = next((u for u in us if str(u.get('phone')) == PHONE), None)
if me is None:
    me = {'id': 'u-d4', 'phone': PHONE, 'username': 'd4'}; us.append(me)
me['password'] = hash_password(PW); me['role'] = 'admin'; me['roles'] = ['admin']
json.dump(us, open(uf, 'w', encoding='utf-8'), ensure_ascii=False)
s = socket.socket(); s.bind(('127.0.0.1', 0)); PORT = s.getsockname()[1]; s.close()
env = dict(os.environ); env['TS_DATA_DIR'] = DST
srv = subprocess.Popen([sys.executable, '-u', '-c',
    'import sys; sys.path.insert(0, r"%s"); from tianshu import create_app;'
    'create_app().run(host="127.0.0.1", port=%d, debug=False, use_reloader=False)' % (HERE, PORT)],
    cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
for _ in range(80):
    try:
        socket.create_connection(('127.0.0.1', PORT), 0.4).close(); break
    except OSError:
        time.sleep(0.35)
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 1440, 'height': 900})
        pg = ctx.new_page()
        pg.goto('http://127.0.0.1:%d/login' % PORT, wait_until='load')
        pg.fill('input[name="account"]', PHONE); pg.fill('input[name="password"]', PW)
        pg.click('button[type="submit"], input[type="submit"]'); pg.wait_for_timeout(1200)
        for ui in ('4', '5', '6', '7', '8'):
            pg.goto('http://127.0.0.1:%d/?ui=%s' % (PORT, ui), wait_until='load')
            pg.wait_for_timeout(700)
            out = pg.evaluate('''() => {
              const g = (sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const cs = getComputedStyle(el);
                return {color: cs.color, bg: cs.backgroundColor, font: cs.fontFamily.slice(0,32),
                        fs: cs.fontSize, ta: cs.textAlign};
              };
              const root = getComputedStyle(document.documentElement);
              return {
                bodyColor: getComputedStyle(document.body).color,
                bodyBg: getComputedStyle(document.body).backgroundColor,
                varIvory: root.getPropertyValue('--pr-ivory') || root.getPropertyValue('--bk-ink') || root.getPropertyValue('--fi-ink') || root.getPropertyValue('--fl-silver') || root.getPropertyValue('--nb-pencil'),
                title: g('.dhero__title'),
                count: g('.count3'),
                lead: g('.dhero__lead'),
                secTitle: g('.dsec__title')
              };
            }''')
            print('=== ui=%s' % ui)
            for k, v in out.items():
                print('   %-10s %s' % (k, v))
        ctx.close(); br.close()
finally:
    srv.terminate()
shutil.rmtree(tmp, ignore_errors=True)
