# -*- coding: utf-8 -*-
"""验证后台两项修复（本地自检）：
1) 懒加载面板的内联脚本会执行了 —— 点用户卡片能弹出档案弹窗；
2) 数据面板标题行注入了「清空记录」按钮。"""
import io
import sys

from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:8099'

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1440, 'height': 900})

    pg.goto(BASE + '/login')
    pg.fill('input[name=account]', 'FireFly')
    pg.fill('input[name=password]', '123123')
    pg.click('button[type=submit]')
    pg.wait_for_load_state('networkidle')

    pg.goto(BASE + '/admin')
    pg.wait_for_load_state('networkidle')

    # ① 切到「用户」面板（懒加载）→ 点第一张用户卡 → 弹窗应能打开
    pg.click('.adm-navi [data-tab="users"]')
    pg.wait_for_timeout(600)
    card = pg.query_selector('.cust-card')
    print('用户卡存在:', bool(card))
    if card:
        card.click()
        pg.wait_for_timeout(300)
        shown = pg.evaluate("document.getElementById('cust-mask').classList.contains('show')")
        name = pg.evaluate("document.getElementById('c-name').textContent")
        ava = pg.evaluate("document.getElementById('c-ava').innerHTML.slice(0, 60)")
        print('弹窗打开:', shown, '| 档案名:', name, '| 头像HTML:', ava)
        pg.keyboard.press('Escape')

    # ② 切到「预约」面板（懒加载）→ 标题行应有「清空记录」按钮
    pg.click('.adm-navi [data-tab="bookings"]')
    pg.wait_for_timeout(600)
    print('预约面板清空按钮:', bool(pg.query_selector('.tabpane[data-tab="bookings"] .js-purge')))

    # ③ 切到「话术库」→ 分类胶囊应是就地筛选的 button（不是跳网址的 a）
    pg.click('.adm-navi [data-tab="talktips"]')
    pg.wait_for_timeout(600)
    print('话术库胶囊是按钮:', bool(pg.query_selector('.tabpane[data-tab="talktips"] [data-filter="cat"] button[data-show]')))
    b.close()
