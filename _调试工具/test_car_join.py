# -*- coding: utf-8 -*-
"""复现「我要上车点了没用」：
登录 FireFly → 拼车大厅 → 进第一辆车详情 → 点「我要上车」→
抓 POST 响应码、flash 文案、上车前后成员数。只用于本地自检。"""
import io
import sys

from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = 'http://127.0.0.1:8099'

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()

    pg.goto(BASE + '/login')
    pg.fill('input[name=account]', 'FireFly')
    pg.fill('input[name=password]', '123123')
    pg.click('button[type=submit]')
    pg.wait_for_load_state('networkidle')
    print('登录后 URL:', pg.url)

    pg.goto(BASE + '/car')
    link = pg.query_selector('a[href^="/car/"]')
    if not link:
        print('大厅没有车，没法测（先造一辆再跑）')
        sys.exit(0)
    href = link.get_attribute('href')
    print('进车详情:', href)
    pg.goto(BASE + href)
    print('上车前成员数:', pg.locator('.sheet3__row').count())

    # 若上一轮测试已把 FireFly 上进这辆车（按钮是「临时跳车」），先跳出来再测上车
    quit_btn = pg.query_selector('form[action*="/quit"] button')
    if quit_btn:
        quit_btn.click()
        pg.wait_for_load_state('networkidle')
        pg.goto(BASE + href)
        print('已先跳出（测试残留），成员数回到:', pg.locator('.sheet3__row').count())

    btn = pg.query_selector('form[action*="/join"] button')
    if not btn:
        print('页面上没有「我要上车」按钮（可能已在车上 / 满员 / 已截止）')
        sys.exit(0)
    btn.click()
    pg.wait_for_load_state('networkidle')
    print('点击后落在:', pg.url)
    print('flash 文案:', pg.locator('.flash').all_text_contents())

    pg.goto(BASE + href)
    print('上车后成员数:', pg.locator('.sheet3__row').count())
    print('详情页按钮现在是什么:',
          pg.locator('form[action*="quit"] button, form[action*="join"] button').all_text_contents())
    b.close()
