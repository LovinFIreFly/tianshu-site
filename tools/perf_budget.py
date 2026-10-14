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
    'css/unseen.css':          20.0,
    'css/lenis.css':            0.5,
}
# 首屏"必须下载"的壳层合计预算（gzip 后）
SHELL_BUDGET_KB = 108.0


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
    if over:
        print('\n有资源超出预算。' + ('（--strict）' if strict else ''))
        if strict:
            sys.exit(1)


if __name__ == '__main__':
    main()
