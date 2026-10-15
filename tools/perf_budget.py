# -*- coding: utf-8 -*-
"""前端体积预算检查（可挂 CI）。

看的是**每个静态资源 gzip 后的体积**，超过预算就标 OVER；
带 --strict 时只要有超预算就以退出码 1 结束（CI 用它卡住"悄悄胖回去"）。

⚠️ 2026-10-15 起：CSS/JS 由 /assets/ 端点**交付时去注释/缩进**（见 tianshu/assets.py）。
本项目的注释是文档资产（设计来由 + 踩坑记录），中文注释几乎压不动 —— 实测占 CSS gzip 的一半。
所以预算卡的是**真正发到浏览器的"min"列**；raw 列只作参考。

用法：
    python tools/perf_budget.py
    python tools/perf_budget.py --strict
"""
import os
import sys
import gzip
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'tianshu', 'static')

# 直接按文件路径加载 tianshu/assets.py —— 不能 `from tianshu.assets import ...`：
# 那会先执行 tianshu/__init__.py（里面 import flask），而 CI 的 size 任务不装依赖，会直接 ImportError。
_spec = importlib.util.spec_from_file_location('_ts_assets', os.path.join(ROOT, 'tianshu', 'assets.py'))
_assets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_assets)
strip_css, strip_js = _assets.strip_css, _assets.strip_js

# 预算（KB，gzip 后，"min"列）：按交付体积实测 + ~8% 余量设定，用来卡"悄悄胖回去"。
BUDGET = {
    'js/unseen.js':            21.0,
    'js/unseen-field.js':      10.0,
    'js/unseen-dust.js':        6.0,   # 首屏浮尘粒子场（canvas 2D，零依赖）
    'js/vitals.js':             2.0,
    'js/csrf.js':               1.5,
    'js/vendor/lenis.min.js':   5.0,
    'js/vendor/gsap.min.js':   30.0,
    'js/vendor/ScrollTrigger.min.js': 19.0,
    'js/vendor/SplitText.min.js':      4.0,
    'css/unseen.css':          22.0,
    'css/lenis.css':            0.5,
}
# 首屏"必须下载"的壳层合计预算（gzip 后，min 列）
SHELL_BUDGET_KB = 114.0

# 首屏媒体（已压缩，不 gzip；按原始大小算）。当前首屏用静态图，不放视频。
MEDIA_BUDGET = {
    'media/hero.webp': 120.0,   # LCP 图
    'media/hero.jpg':  220.0,   # 老格式兜底
}


def gz(data):
    return len(gzip.compress(data, 6))


def raw_and_min(path):
    """返回 (raw_bytes, min_bytes)：min 模拟 /assets/ 交付（css/js 去注释缩进）。"""
    with open(path, 'rb') as fh:
        data = fh.read()
    text = data.decode('utf-8', 'replace')
    if path.endswith('.css'):
        text = strip_css(text)
    elif path.endswith('.js'):
        text = strip_js(text)
    return data, text.encode('utf-8')


def main():
    strict = '--strict' in sys.argv
    over = False
    print('%-34s %8s %9s %9s %9s' % ('asset', 'raw', 'raw-gz', 'min-gz', 'budget'))
    print('-' * 74)
    total = 0
    for rel, budget in BUDGET.items():
        path = os.path.join(STATIC, rel)
        if not os.path.exists(path):
            print('%-34s %8s' % (rel, 'MISSING'))
            continue
        raw, mn = raw_and_min(path)
        rg, mg = gz(raw), gz(mn)
        total += mg
        flag = '  <== OVER' if mg / 1024.0 > budget else ''
        if flag:
            over = True
        print('%-34s %7.1fK %8.1fK %8.1fK %8.1fK%s' % (
            rel, len(raw) / 1024.0, rg / 1024.0, mg / 1024.0, budget, flag))
    print('-' * 74)
    tot = total / 1024.0
    tflag = '  <== OVER' if tot > SHELL_BUDGET_KB else ''
    if tflag:
        over = True
    print('%-34s %18s %8.1fK %8.1fK%s' % ('TOTAL (min gzip)', '', tot, SHELL_BUDGET_KB, tflag))
    for rel, budget in MEDIA_BUDGET.items():
        path = os.path.join(STATIC, rel)
        if not os.path.exists(path):
            continue
        raw = os.path.getsize(path) / 1024.0
        flag = '  <== OVER' if raw > budget else ''
        if flag:
            over = True
        print('%-34s %7.1fK %9s %9s %8.1fK%s' % (rel, raw, '', '', budget, flag))
    if over:
        print('\n有资源超出预算。' + ('（--strict）' if strict else ''))
        if strict:
            sys.exit(1)
    else:
        print('\n全部在预算内。')


if __name__ == '__main__':
    main()
