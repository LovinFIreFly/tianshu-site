# -*- coding: utf-8 -*-
"""体检 D（浏览器实测）：登录后逐页检查
   1) 页面里有 POST 表单吗
   2) 引了 csrf.js 吗
   3) 表单里真的被塞进 _csrf 了吗
   任何"有表单没令牌"的页面，提交一定 403。
"""
import pathlib
from collections import deque
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099"
CHROME = r"C:\Users\junbo\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

JS = """() => {
  const hasForm = !!document.querySelector('form[method="post"], form:not([method])');
  const forms = Array.from(document.querySelectorAll('form'));
  const postForms = forms.filter(f => (f.getAttribute('method')||'').toLowerCase() === 'post');
  const missing = postForms.filter(f => !f.querySelector('input[name="_csrf"]')).length;
  return {
    hasScript: !!document.querySelector('script[src*="csrf.js"]'),
    postForms: postForms.length,
    missingToken: missing,
    cookie: !!document.cookie.match(/csrf=/)
  };
}"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True)
    ctx = b.new_context(user_agent=UA)
    page = ctx.new_page()

    page.goto(BASE + "/login")
    page.fill("input[name='account']", "FireFly")
    page.fill("input[name='password']", "123123")
    page.click("button[type='submit']")
    page.wait_for_timeout(1200)

    q = deque(["/", "/admin", "/dm", "/me", "/m/"])
    seen = set()
    risky = []
    while q and len(seen) < 80:
        path = q.popleft()
        if path in seen:
            continue
        seen.add(path)
        try:
            r = page.goto(BASE + path, wait_until="load", timeout=15000)
            if not r or r.status >= 400:
                continue
            info = page.evaluate(JS)
            if info["postForms"] and (not info["hasScript"] or info["missingToken"]):
                risky.append((path, info))
                print("⚠️  %-32s 表单%s 缺令牌%s 脚本=%s cookie=%s"
                      % (path, info["postForms"], info["missingToken"], info["hasScript"], info["cookie"]))
            for href in page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.getAttribute('href'))"):
                if href and href.startswith("/") and href.split("#")[0] not in seen:
                    q.append(href.split("#")[0])
        except Exception:
            pass

    print("\n检查页面数：%d，风险页面：%d" % (len(seen), len(risky)))

    # 实测一次真实的写操作：改门店公告（无害、可还原）
    page.goto(BASE + "/admin/settings", wait_until="load")
    try:
        before = page.input_value("textarea[name='notice']") if page.locator("textarea[name='notice']").count() else ""
        if page.locator("textarea[name='notice']").count():
            page.fill("textarea[name='notice']", before)
            page.click("button[type='submit']")
            page.wait_for_timeout(1200)
            print("后台保存公告 ->", page.url)
    except Exception as e:
        print("后台保存测试异常：", str(e)[:120])

    b.close()
