# -*- coding: utf-8 -*-
"""体检 C：找出"会 POST 但没有 CSRF 令牌来源"的模板 —— 这类页面提交必 403。

判定：模板里有 method=post 的表单，但既没有引 csrf.js、也没继承带了 csrf.js 的骨架。
"""
import os, re

root = r"C:\Users\junbo\Desktop\网站\tianshu\templates"

CSRF_BASES = {'base.html', 'auth_base.html', 'layout_v1.html', 'auth_v1.html'}
form_re = re.compile(r'<form[^>]*>', re.IGNORECASE)
method_re = re.compile(r'method\s*=\s*["\']?post', re.IGNORECASE)
extends_re = re.compile(r'\{%\s*extends\s*[\'"]([^\'"]+)[\'"]')
include_re = re.compile(r'\{%\s*include\s*[\'"]([^\'"]+)[\'"]')

risky = []
for dirpath, _, files in os.walk(root):
    for fn in files:
        if not fn.endswith('.html'):
            continue
        p = os.path.join(dirpath, fn)
        with open(p, encoding='utf-8') as f:
            src = f.read()
        if not any(method_re.search(m) for m in form_re.findall(src)):
            continue                       # 没有 POST 表单，跳过
        if 'csrf.js' in src:
            continue                       # 自己引了脚本，安全
        ext = extends_re.search(src)
        base = ext.group(1) if ext else ''
        inc = include_re.findall(src)
        safe = base in CSRF_BASES or any(os.path.basename(i) in CSRF_BASES for i in inc)
        if not safe:
            risky.append((os.path.relpath(p, root), base or '(无 extends)'))

print('--- 有 POST 表单但拿不到 CSRF 令牌的模板（提交会 403）---')
for f, base in risky:
    print('  %-40s extends=%s' % (f, base))
print('共 %d 个' % len(risky))
