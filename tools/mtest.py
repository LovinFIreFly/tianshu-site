# -*- coding: utf-8 -*-
"""手机环境真实测试：
   本机起 Flask → Playwright 开 iPhone 视口（手机 UA，会被自动分流到 /m/）→
   走完 登录门页 → 登录 → 五个 tab → 剧本详情 → 预约 sheet 的全流程。
   抓取：JS 报错 / 4xx5xx 请求 / 坏图 / 横向溢出，并逐屏截图到 tools/shots/。
   用法：python tools/mtest.py [--no-login] [--out tools/shots]
"""
import json
import os
import socket
import sys
import threading
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from tianshu import create_app  # noqa: E402
import config  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = os.path.join(BASE, 'tools', 'shots')
os.makedirs(OUT, exist_ok=True)

ACCOUNT = os.environ.get('TS_ACC', 'FireFly')
PASSWORD = os.environ.get('TS_PW', '123123')


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(port):
    app = create_app()
    from waitress import serve
    t = threading.Thread(target=serve, args=(app,), kwargs={'host': '127.0.0.1', 'port': port, 'threads': 6}, daemon=True)
    t.start()
    for _ in range(50):
        time.sleep(0.1)
        try:
            s = socket.socket()
            s.connect(('127.0.0.1', port))
            s.close()
            return
        except OSError:
            continue
    raise RuntimeError('server not up')


def main():
    no_login = '--no-login' in sys.argv
    zine = '--zine' in sys.argv
    settings_path = os.path.join(BASE, 'data', 'settings.json')
    old_settings = None
    if zine and os.path.isfile(settings_path):
        old_settings = open(settings_path, encoding='utf-8').read()
        st = json.loads(old_settings or '{}')
        st['mobileMode'] = 'zine'
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    try:
        run(no_login, zine)
    finally:
        if old_settings is not None:
            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(old_settings)
            print('settings restored')


def run(no_login, zine):
    port = free_port()
    start_server(port)
    base = 'http://127.0.0.1:%d' % port
    print('server:', base, '(mode: %s)' % ('zine' if zine else 'app'))

    problems = []

    with sync_playwright() as pw:
        iphone = pw.devices['iPhone 13']
        browser = pw.chromium.launch()
        ctx = browser.new_context(**iphone, locale='zh-CN')
        page = ctx.new_page()

        page.on('console', lambda m: problems.append('console.%s: %s' % (m.type, m.text)) if m.type == 'error' else None)
        page.on('pageerror', lambda e: problems.append('pageerror: %s' % e))
        page.on('response', lambda r: problems.append('http %s %s' % (r.status, r.url))
                if r.status >= 400 and '/m/' in r.url else None)
        page.on('requestfailed', lambda r: problems.append('reqfail %s %s' % (r.url, r.failure))
                if '/m/' in r.url else None)

        def shot(name):
            page.screenshot(path=os.path.join(OUT, name + '.png'), full_page=False)
            print('  shot:', name)

        def overflow():
            w = page.evaluate('document.documentElement.scrollWidth')
            v = page.evaluate('window.innerWidth')
            if w > v + 1:
                problems.append('H-OVERFLOW %d>%d on %s' % (w, v, page.url))
                return True
            return False

        def broken_imgs():
            bad = page.evaluate("""
              Array.from(document.images).filter(i=>{
                const r=i.getBoundingClientRect();
                return (!i.complete||i.naturalWidth===0) && r.bottom>0 && r.top<innerHeight;
              }).map(i=>i.src)
            """)
            if bad:
                problems.append('broken imgs: ' + ', '.join(bad[:5]))
            return bad

        # ---------- 1. 未登录：app 模式分流到 /m/ + 登录门页；zine 模式直出桌面页 ----------
        page.goto(base + '/', wait_until='networkidle')
        print('landed:', page.url)
        if zine:
            assert '/m' not in page.url, 'zine mode should stay on desktop pages'
            zcss = page.evaluate("!!document.querySelector('link[href*=\"mobile-zine\"]')")
            assert zcss, 'mobile-zine.css not loaded'
            print('zine css loaded')
            shot('00-zine-home')
            overflow()
        else:
            assert '/m' in page.url, 'mobile UA was not redirected to /m/'
        gate = page.locator('#gate')
        if not no_login:
            if zine:
                # zine 模式：登录走桌面 /login 页
                page.goto(base + '/login', wait_until='networkidle')
                page.fill('input[name="account"]', ACCOUNT)
                page.fill('input[name="password"]', PASSWORD)
                with page.expect_response(lambda r: '/login' in r.url) as ri:
                    page.click('button[type="submit"]')
                print('zine login status:', ri.value.status)
                page.goto(base + '/', wait_until='networkidle')
                page.wait_for_timeout(800)
                if '/login' in page.url:
                    problems.append('ZINE LOGIN FAILED: bounced back to %s' % page.url)
                    shot('02-login-failed')
                else:
                    print('logged in OK (zine)')
                    shot('02-logged-in-zine')
            else:
                assert gate.is_visible(), 'login gate should be visible for guest'
                shot('01-gate')
                overflow(); broken_imgs()

                # ---------- 2. 登录 ----------
                with page.expect_response(lambda r: '/login' in r.url) as ri:
                    page.fill('#gate-account', ACCOUNT)
                    page.fill('#gate-pw', PASSWORD)
                    page.click('#gate [data-action="submit-login"]')
                resp = ri.value
                print('login status:', resp.status)
                page.wait_for_timeout(1500)
                me_raw = page.evaluate("fetch('/m/api/me',{credentials:'same-origin'}).then(r=>r.text())")
                print('me after login:', me_raw[:200])
                if gate.is_visible():
                    err = page.locator('#gate-err').text_content()
                    problems.append('LOGIN FAILED: gate still visible, err=%r status=%s' % (err, resp.status))
                    shot('02-login-failed')
                else:
                    print('logged in OK')
                    shot('02-logged-in')

        # ---------- 3. 主要页面逐个截屏 ----------
        if zine:
            for name, path in [('home', '/'), ('scripts', '/scripts'), ('comm', '/comm'), ('me', '/me')]:
                page.goto(base + path, wait_until='networkidle')
                page.wait_for_timeout(600)
                shot('10-zine-' + name)
                overflow()
                broken_imgs()
        else:
            for tab in ['home', 'scripts', 'carpool', 'talk', 'me']:
                page.click('.tab[data-tab="%s"]' % tab)
                page.wait_for_timeout(700)
                shot('10-' + tab)
                overflow()
                broken_imgs()

        # ---------- 4. 剧本详情 ----------
        if zine:
            page.goto(base + '/scripts', wait_until='networkidle')
            card = page.locator('.scard a, .scard, a[href*="/script/"]').first
            if card.count():
                card.click()
                page.wait_for_timeout(1200)
                shot('20-zine-script')
                overflow()
                broken_imgs()
        else:
            page.click('.tab[data-tab="scripts"]')
            page.wait_for_timeout(500)
            rows = page.locator('.srow')
            if rows.count():
                rows.first.click()
                page.wait_for_timeout(900)
                shot('20-script-sheet')
                overflow()
                fav_btn = page.locator('#sheet [data-action="toggle-fav"]')
                if fav_btn.count():
                    fav_btn.first.click()
                    page.wait_for_timeout(800)
                    print('  fav toggled ->', fav_btn.first.text_content())
                book_btn = page.locator('#sheet [data-action="open-book"]')
                if book_btn.count():
                    book_btn.first.click()
                    page.wait_for_timeout(700)
                    shot('21-book-sheet')
                    overflow()
                    page.keyboard.press('Escape')
                    page.wait_for_timeout(300)

        # ---------- 4b. 我的：改期 / 评价 sheet（仅 /m 站有；有数据才点） ----------
        if not zine:
            page.click('.tab[data-tab="me"]')
            page.wait_for_timeout(600)
            rs = page.locator('[data-action="open-resched"]')
            if rs.count():
                rs.first.click()
                page.wait_for_timeout(600)
                shot('22-resched-sheet')
                page.keyboard.press('Escape')
                page.wait_for_timeout(300)
            rv = page.locator('[data-action="open-review"]')
            if rv.count():
                rv.first.click()
                page.wait_for_timeout(600)
                shot('23-review-sheet')
                page.keyboard.press('Escape')

        # ---------- 5. 桌面端登录页顺带验证（电脑端账号密码问题） ----------
        if not zine:
            page2 = ctx.new_page()
            page2.set_viewport_size({'width': 1280, 'height': 800})
            page2.goto(base + '/login', wait_until='networkidle')
            page2.fill('input[name="account"]', ACCOUNT)
            page2.fill('input[name="password"]', PASSWORD)
            with page2.expect_response(lambda r: '/login' in r.url) as ri2:
                page2.click('button[type="submit"]')
            print('desktop login status:', ri2.value.status, '->', page2.url)
            if 'login' in page2.url:
                flash = page2.locator('.flash, .alerts, [class*=flash]').first
                problems.append('DESKTOP LOGIN FAILED url=%s flash=%r' % (page2.url, flash.text_content() if flash.count() else ''))
            page2.screenshot(path=os.path.join(OUT, '30-desktop-login.png'))

        browser.close()

    print('\n===== RESULT =====')
    if problems:
        for p in problems:
            print('  [!]', p)
        sys.exit(1)
    print('all clean. screenshots in tools/shots/')


if __name__ == '__main__':
    main()
