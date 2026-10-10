"""精确定位横向溢出：找 scrollWidth > clientWidth 的那个具体元素。"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
SRC = os.path.join(HERE, 'data')
tmp = tempfile.mkdtemp(prefix='ts_d2_'); DST = os.path.join(tmp, 'data')
shutil.copytree(SRC, DST); os.environ['TS_DATA_DIR'] = DST
from tianshu.security import hash_password
PHONE, PW = '13800000000', 'smoke123456'
uf = os.path.join(DST, 'users.json'); us = json.load(open(uf, encoding='utf-8'))
me = next((u for u in us if str(u.get('phone')) == PHONE), None)
if me is None:
    me = {'id': 'u-d2', 'phone': PHONE, 'username': 'd2'}; us.append(me)
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
              const res = [];
              // 从 html 往下走，找第一个"自身溢出但没被裁"的祖先链
              function walk(el, depth) {
                if (depth > 14) return;
                const cs = getComputedStyle(el);
                const clipped = (cs.overflowX === 'hidden' || cs.overflowX === 'clip' || cs.overflowX === 'auto' || cs.overflowX === 'scroll');
                if (el.scrollWidth > el.clientWidth + 2 && !clipped && el.clientWidth > 0) {
                  res.push({tag: el.tagName.toLowerCase(),
                            cls: (el.className && el.className.toString().slice(0,50)) || '',
                            sw: el.scrollWidth, cw: el.clientWidth,
                            ox: cs.overflowX, pos: cs.position});
                }
                for (const c of el.children) walk(c, depth + 1);
              }
              walk(document.documentElement, 0);
              return {sw: document.documentElement.scrollWidth,
                      vw: document.documentElement.clientWidth,
                      hits: res.slice(0, 10)};
            }''')
            print('=== ui=%s  scrollW=%s  clientW=%s' % (ui, out['sw'], out['vw']))
            for h in out['hits']:
                print('    %-7s .%-50s sw=%-5s cw=%-5s ox=%s' % (h['tag'], h['cls'], h['sw'], h['cw'], h['ox']))
        ctx.close(); br.close()
finally:
    srv.terminate()
shutil.rmtree(tmp, ignore_errors=True)
