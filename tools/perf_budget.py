# -*- coding: utf-8 -*-
"""前端体积预算检查（可挂 CI）。

看的是**每个静态资源 gzip 后**的体积，超过预算就标 OVER；
带 --strict 时只要有超预算就以退出码 1 结束（CI 用它卡住"悄悄胖回去"）。

用法：
    python tools/perf_budget.py
    python tools/perf_budget.py --strict

数值单位 KB（gzip 后）。预算按当前实测 + 余量设定；
改设计/引库导致超预算时，应先想清楚"这几十 KB 换到了什么"，再决定改预算还是改实现。
"""
import os
import sys
import gzip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'tianshu', 'static')

# 预算（KB，gzip 后）：按当前实测 + 约 8% 余量设定，用来卡"悄悄胖回去"。
BUDGET = {
    'js/unseen.js':            21.0,
    'js/unseen-field.js':      10.0,
    'js/vitals.js':             2.0,
    'js/csrf.js':               1.5,
    'js/vendor/lenis.min.js':   5.0,
    'js/vendor/gsap.min.js':   30.0,
    'js/vendor/ScrollTrigger.min.js': 19.0,
    'js/vendor/SplitText.min.js':      4.0,
    # v18 去 AI 味续改：新增 --sec-y 留白令牌、text-wrap balance/pretty、
    # .kicker 角色比喻小句等真实规则 → gzip +1.0K。这是有意的功能增量，不是悄悄胖回去，
    # 所以把预算同步提到 22.0K（仍留 ~5% 余量）。若继续增长，应转为"先删旧规则再加新规则"。
    'css/unseen.css':          22.0,
    'css/lenis.css':            0.5,
}
# 首屏"必须下载"的壳层合计预算（gzip 后）
SHELL_BUDGET_KB = 108.0

# 首屏媒体（已压缩，不 gzip；按原始大小算）。当前首屏用静态图，不放视频。
MEDIA_BUDGET = {
    'media/hero.webp': 120.0,   # LCP 图
    'media/hero.jpg':  220.0,   # 老格式兜底
}


def gz(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    return len(data), len(gzip.compress(data, 6))


def main():
    strict = '--strict' in sys.argv
    over = False
    print('%-34s %9s %9s %9s' % ('asset', 'raw', 'gzip', 'budget'))
    print('-' * 66)
    total = 0
    for rel, budget in BUDGET.items():
        path = os.path.join(STATIC, rel)
        if not os.path.exists(path):
            print('%-34s %9s' % (rel, 'MISSING'))
            continue
        raw, g = gz(path)
        total += g
        flag = ''
        if g / 1024.0 > budget:
            flag = '  <== OVER'
            over = True
        print('%-34s %8.1fK %8.1fK %8.1fK%s' % (rel, raw / 1024.0, g / 1024.0, budget, flag))
    print('-' * 66)
    tot = total / 1024.0
    tflag = ''
    if tot > SHELL_BUDGET_KB:
        tflag = '  <== OVER'
        over = True
    print('%-34s %18.1fK %8.1fK%s' % ('TOTAL (gzip)', tot, SHELL_BUDGET_KB, tflag))
    # 首屏媒体（不 gzip）
    for rel, budget in MEDIA_BUDGET.items():
        path = os.path.join(STATIC, rel)
        if not os.path.exists(path):
            continue
        raw = os.path.getsize(path) / 1024.0
        flag = ''
        if raw > budget:
            flag = '  <== OVER'
            over = True
        print('%-34s %8.1fK %9s %8.1fK%s' % (rel, raw, '', budget, flag))
    if over:
        print('\n有资源超出预算。' + ('（--strict）' if strict else ''))
        if strict:
            sys.exit(1)


if __name__ == '__main__':
    main()
