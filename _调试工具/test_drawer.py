# -*- coding: utf-8 -*-
"""复现：手机端管理后台点「☰ 全部」抽屉出不来的问题
登录 FireFly → 手机 UA + 窄屏打开 /admin → 点 #adm-open-drawer → 检查抽屉状态
"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099"
CHROME = r"C:\Users\junbo\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True)
    ctx = b.new_context(user_agent=MOBILE_UA, viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    page.on("console", lambda m: print("  [console]", m.type, m.text[:120]))
    page.on("pageerror", lambda e: print("  [pageerror]", str(e)[:200]))

    page.goto(BASE + "/login", wait_until="load")
    page.fill("input[name='account']", "FireFly")
    page.fill("input[name='password']", "123123")
    page.click("button[type='submit']")
    page.wait_for_timeout(1000)

    page.goto(BASE + "/admin", wait_until="load")
    page.wait_for_timeout(800)
    print("页面:", page.url)
    print("html data-device:", page.evaluate("document.documentElement.getAttribute('data-device')"))

    drawer = page.locator("#adm-drawer")
    mask = page.locator("#adm-drawer-mask")
    btn = page.locator("#adm-open-drawer")
    print("☰ 按钮可见:", btn.is_visible(), " 抽屉存在:", drawer.count())

    def snap(tag):
        info = page.evaluate("""() => {
            const d = document.getElementById('adm-drawer');
            if (!d) return {missing: true};
            const cs = getComputedStyle(d);
            const r = d.getBoundingClientRect();
            return {hidden: d.hidden, cls: d.className, display: cs.display,
                    transform: cs.transform, pos: cs.position, z: cs.zIndex,
                    rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                    sideZ: getComputedStyle(d.closest('.adm-side')).zIndex,
                    sidePos: getComputedStyle(d.closest('.adm-side')).position};
        }""")
        print(tag, info)
        return info

    snap("点击前:")
    btn.click()
    page.wait_for_timeout(600)
    info = snap("点击后:")
    print("抽屉可见性 is_visible:", drawer.is_visible())
    print("遮罩可见性:", mask.is_visible())
    page.screenshot(path=r"C:\Users\junbo\Desktop\网站\_调试工具\drawer_open.png")
    b.close()
