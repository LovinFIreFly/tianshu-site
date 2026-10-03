# -*- coding: utf-8 -*-
"""甜薯网站体检脚本：登录 FireFly 后遍历全站页面 + 跑关键操作，抓出所有 4xx/5xx
用法：python crawl.py   （先确保 python app.py 已启动，端口在 BASE 里改）"""
import re, pathlib, traceback
from collections import deque
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099"
CHROME = r"C:\Users\junbo\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
OUT = pathlib.Path(r"C:\Users\junbo\Desktop\网站\_调试工具")
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

bad = []      # (status, url, method)
errors = []   # 页面 JS 报错
seen = set()


def rec(status, url, method='GET'):
    if status >= 400:
        bad.append((status, url, method))
        print("  !! %s %s %s" % (status, method, url), flush=True)


def run():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, user_agent=DESKTOP_UA)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.on("console", lambda m: errors.append("console." + m.type + ": " + m.text[:200])
                if m.type in ("error",) else None)
        page.on("response", lambda r: rec(r.status, r.url, r.request.method))

        # ---------- 登录 ----------
        page.goto(BASE + "/login", wait_until="networkidle")
        page.fill("input[name='account']", "FireFly")
        page.fill("input[name='password']", "123123")
        page.click("button[type='submit']")
        page.wait_for_timeout(1500)
        print("登录后落在：", page.url, flush=True)
        page.screenshot(path=str(OUT / "s_login.png"))

        # ---------- 遍历全站链接 ----------
        q = deque(["/"])
        visited = 0
        while q and visited < 90:
            path = q.popleft()
            if path in seen:
                continue
            seen.add(path)
            url = BASE + path
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                visited += 1
                if r is not None:
                    rec(r.status, url)
                if r and r.status >= 400:
                    continue
                for href in page.eval_on_selector_all(
                        "a[href]", "els => els.map(e => e.getAttribute('href'))"):
                    if not href or href.startswith(("http", "#", "javascript", "mailto", "tel")):
                        continue
                    href = href.split("#")[0]
                    if href.startswith("/") and href not in seen:
                        q.append(href)
            except Exception as e:
                errors.append("goto %s: %s" % (path, str(e)[:120]))
        print("遍历页面数：", visited, flush=True)

        # ---------- 关键写操作（POST）----------
        def try_post(desc, fn):
            try:
                fn()
                page.wait_for_timeout(1200)
                print("  写操作：%s -> %s" % (desc, page.url), flush=True)
            except Exception:
                errors.append("POST %s: %s" % (desc, traceback.format_exc()[:200]))

        # 预约：随便找一个剧本详情页，提交预约表单
        try_post("预约下单", lambda: (
            page.goto(BASE + "/scripts", wait_until="domcontentloaded"),
            page.click("a[href^='/script/']"),
            page.wait_for_timeout(800),
            (page.click("form[action*='book'] button[type='submit']")
             if page.locator("form[action*='book'] button[type='submit']").count()
             else page.click("button:has-text('预约')")),
        ))

        # 后台：几个常用页面
        for path in ("/admin", "/admin/bookings", "/admin/scripts", "/admin/settings",
                     "/admin/users", "/admin/sessions"):
            try:
                r = page.goto(BASE + path, wait_until="domcontentloaded", timeout=15000)
                rec(r.status, BASE + path)
            except Exception as e:
                errors.append("admin %s: %s" % (path, str(e)[:120]))

        # DM 工作台
        for path in ("/dm", "/dm/today"):
            try:
                r = page.goto(BASE + path, wait_until="domcontentloaded", timeout=15000)
                rec(r.status, BASE + path)
            except Exception as e:
                errors.append("dm %s: %s" % (path, str(e)[:120]))

        page.screenshot(path=str(OUT / "s_last.png"))
        b.close()

    print("\n===== 4xx / 5xx 汇总 =====")
    seen_err = set()
    for s, u, m in bad:
        key = (s, re.sub(r"\d+", "N", u))
        if key in seen_err:
            continue
        seen_err.add(key)
        print(" %s  %-6s %s" % (s, m, u))
    print("\n===== 页面报错 =====")
    for e in dict.fromkeys(errors):
        print(" -", e)


if __name__ == "__main__":
    run()
