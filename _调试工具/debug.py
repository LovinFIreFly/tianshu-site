# -*- coding: utf-8 -*-
"""甜薯剧本杀 网站自动化调试脚本（Playwright + 本地 Chromium）
用法：python debug.py
输出：控制台报错、网络请求状态（尤其 GitHub API 403/500）、各步骤截图
"""
import pathlib, traceback
from playwright.sync_api import sync_playwright

PAGE_URL = pathlib.Path(r"C:\Users\junbo\Desktop\网站\index.html").as_uri()
CHROME = r"C:\Users\junbo\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
OUT = pathlib.Path(r"C:\Users\junbo\Desktop\网站\_调试工具")

logs, net, steps = [], [], []


def log(msg):
    steps.append(msg)
    print("[STEP]", msg, flush=True)


def shot(page, name):
    try:
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    except Exception as e:
        logs.append(("shot-error", f"{name}: {e}"))


def run():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: logs.append((m.type, m.text[:300])))
        page.on("pageerror", lambda e: logs.append(("pageerror", str(e)[:300])))
        page.on("requestfailed", lambda r: net.append(("FAILED", r.url[:120], str(r.failure)[:80])))
        page.on("response", lambda r: net.append((r.status, r.url[:120])) if "github" in r.url else None)

        page.goto(PAGE_URL)
        page.wait_for_timeout(6500)   # 等首轮云端同步 + 15s 轮询触发一次
        log("打开首页")
        shot(page, "01-home")

        # 注册一个新账号
        try:
            page.click('[data-action="go-login"]')
            page.click('[data-action="go-register"]')
            page.fill("#reg-phone", "13900001234")
            page.click('[data-action="send-code"][data-t="reg"]')
            page.fill("#reg-code", "1234")
            page.fill("#reg-name", "测试小明")
            page.fill("#reg-pwd", "123456")
            page.fill("#reg-pwd2", "123456")
            page.fill("#reg-invite", "TIANSHU")
            page.click('[data-action="do-register"]')
            page.wait_for_timeout(1500)
            log("注册账号 测试小明")
            shot(page, "02-after-register")
        except Exception:
            logs.append(("register-error", traceback.format_exc()[:300]))

        # 预约：拼车单开一辆车
        try:
            page.wait_for_selector(".juben", timeout=5000)
            page.click(".juben")
            page.wait_for_timeout(600)
            page.click('[data-action="pick-new"]')
            page.wait_for_timeout(300)
            page.click('[data-action="try-book"]')
            page.wait_for_timeout(500)
            page.click('[data-action="submit-book"]')
            page.wait_for_timeout(1500)
            log("完成一次预约（拼车单开）")
            shot(page, "03-booked")
        except Exception:
            logs.append(("book-error", traceback.format_exc()[:300]))

        # 管理员：内置账号登录
        try:
            page.evaluate("openModal('modal-admin')")
            page.fill("#adm-user", "admin")
            page.fill("#adm-pass", "admin123")
            page.click('[data-action="adm-login"]')
            page.wait_for_timeout(1200)
            log("管理员登录")
            shot(page, "04-admin-dash")
        except Exception:
            logs.append(("admin-login-error", traceback.format_exc()[:300]))

        # 预约管理：核销到场 → 确认完成
        try:
            page.click('[data-action="adm-tab"][data-t="bookings"]')
            page.wait_for_timeout(800)
            shot(page, "05-admin-bookings")
            page.click('[data-action="adm-done"]')
            page.wait_for_timeout(400)
            page.click('[data-action="confirm-yes"]')
            page.wait_for_timeout(800)
            log("核销到场")
            page.click('[data-action="adm-finish"]')
            page.wait_for_timeout(400)
            page.click('[data-action="confirm-yes"]')
            page.wait_for_timeout(800)
            log("确认完成")
            shot(page, "06-admin-finished")
        except Exception:
            logs.append(("admin-ops-error", traceback.format_exc()[:300]))

        # 评分管理：开关 + 查看
        try:
            page.click('[data-action="adm-tab"][data-t="reviews"]')
            page.wait_for_timeout(800)
            shot(page, "07-admin-reviews")
            page.click('[data-action="toggle-reviews"]')
            page.wait_for_timeout(800)
            log("切换评分开关")
            page.click('[data-action="toggle-reviews"]')
            page.wait_for_timeout(600)
        except Exception:
            logs.append(("reviews-error", traceback.format_exc()[:300]))

        # 剧本管理：打开编辑表单
        try:
            page.click('[data-action="adm-tab"][data-t="scripts"]')
            page.wait_for_timeout(600)
            page.click('[data-action="sc-edit"]')
            page.wait_for_timeout(700)
            shot(page, "08-script-form")
            page.click('[data-action="close-modal"][data-modal="modal-script"]')
            log("剧本编辑表单")
        except Exception:
            logs.append(("script-error", traceback.format_exc()[:300]))

        # 回到客户端：确认评价弹窗
        try:
            page.click('[data-action="adm-home"]')
            page.wait_for_timeout(500)
            page.fill("#in-acc", "测试小明")
            page.fill("#in-pwd", "123456")
            page.click('[data-action="do-login"]')
            page.wait_for_timeout(2500)
            has_review = page.locator("#modal-review.show").count() > 0
            log("客户登录，评价弹窗出现：" + str(has_review))
            shot(page, "09-user-review")
            if has_review:
                page.click('[data-action="rv-star"][data-n="5"]')
                page.fill("#rv-text", "DM 超棒，剧情很戳！")
                page.click('[data-action="submit-review"]')
                page.wait_for_timeout(1500)
                log("提交评价")
                shot(page, "10-after-review")
        except Exception:
            logs.append(("review-error", traceback.format_exc()[:300]))

        # 详情页评分展示
        try:
            page.wait_for_selector(".juben", timeout=5000)
            page.click(".juben")
            page.wait_for_timeout(900)
            shot(page, "11-detail-score")
            log("打开剧本详情")
        except Exception:
            logs.append(("detail-error", traceback.format_exc()[:300]))

        b.close()

    print("\n===== 控制台 / 页面报错 =====")
    for t, m in logs:
        print(f"[{t}] {m}")
    print("\n===== GitHub 相关请求状态 =====")
    for row in net:
        print(row)
    print("\n===== 步骤 =====")
    for s in steps:
        print(" -", s)


if __name__ == "__main__":
    run()
