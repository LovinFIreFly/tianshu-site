# -*- coding: utf-8 -*-
"""手机 UA 遍历：确认手机端（/m 独立站）不会出现 403/500"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099"
CHROME = r"C:\Users\junbo\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

bad = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True)
    ctx = b.new_context(user_agent=MOBILE_UA, viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    page.on("response", lambda r: bad.append((r.status, r.url, r.request.method))
            if r.status >= 400 and 'static' not in r.url else None)

    page.goto(BASE + "/login", wait_until="load")
    page.fill("input[name='account']", "FireFly")
    page.fill("input[name='password']", "123123")
    page.click("button[type='submit']")
    page.wait_for_timeout(1200)
    print("手机端登录后：", page.url)

    for path in ['/', '/m/', '/scripts', '/me', '/car', '/comm', '/notice']:
        try:
            page.goto(BASE + path, wait_until="load", timeout=15000)
            print('  %-12s -> %s' % (path, page.url))
        except Exception as e:
            print('  %-12s 异常 %s' % (path, str(e)[:80]))
    b.close()

print('\n--- 4xx/5xx ---')
for s, u, m in bad:
    print(' ', s, m, u)
print('共', len(bad), '条')
