import json, os, shutil, socket, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
SRC = os.path.join(HERE, 'data')
tmp = tempfile.mkdtemp(prefix='ts_css_'); DST = os.path.join(tmp, 'data')
shutil.copytree(SRC, DST); os.environ['TS_DATA_DIR'] = DST
from tianshu.security import hash_password
PHONE, PW = '13800000000', 'smoke123456'
uf = os.path.join(DST, 'users.json'); us = json.load(open(uf, encoding='utf-8'))
me = next((u for u in us if str(u.get('phone')) == PHONE), None)
if me is None:
    me = {'id': 'u-x', 'phone': PHONE, 'username': 'x'}; us.append(me)
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
reqs = []
try:
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 1440, 'height': 900})
        pg = ctx.new_page()
        pg.on('response', lambda r: reqs.append((r.status, r.url.split('/')[-1])) if '.css' in r.url else None)
        pg.goto('http://127.0.0.1:%d/login' % PORT, wait_until='load')
        pg.fill('input[name="account"]', PHONE); pg.fill('input[name="password"]', PW)
        pg.click('button[type="submit"], input[type="submit"]'); pg.wait_for_timeout(1200)
        reqs.clear()
        pg.goto('http://127.0.0.1:%d/?ui=4' % PORT, wait_until='load')
        pg.wait_for_timeout(900)
        print('CSS 请求：')
        for st, u in reqs:
            print('   %s  %s' % (st, u))
        out = pg.evaluate('''() => {
          const el = document.querySelector('.ticker3 .count3');
          const cs = el ? getComputedStyle(el) : null;
          // 找出所有包含 .count3 的规则
          const hits = [];
          for (const sh of document.styleSheets) {
            let rules; try { rules = sh.cssRules; } catch(e) { continue; }
            if (!rules) continue;
            for (const r of rules) {
              if (r.selectorText && r.selectorText.indexOf('count3') > -1) {
                hits.push({sheet: (sh.href||'').split('/').pop(),
                           sel: r.selectorText, color: r.style.color || ''});
              }
            }
          }
          return {color: cs ? cs.color : 'no el',
                  bkInk: getComputedStyle(document.documentElement).getPropertyValue('--bk-ink'),
                  hits: hits.slice(0,20)};
        }''')
        print('\ncount3 computed color:', out['color'], ' --bk-ink:', out['bkInk'])
        print('命中规则：')
        for h in out['hits']:
            print('   %-22s %-46s %s' % (h['sheet'], h['sel'], h['color']))
        ctx.close(); br.close()
finally:
    srv.terminate()
shutil.rmtree(tmp, ignore_errors=True)
