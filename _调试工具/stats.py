# -*- coding: utf-8 -*-
"""项目体检：统计各目录文件数/代码行数，找出核心模块与最大文件"""
import os

root = r"C:\Users\junbo\Desktop\网站"
skip = {'.git', '__pycache__', 'node_modules', 'android', '.codebuddy', 'legacy', 'deploy', 'data'}

rows = []
for dirpath, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in skip]
    rel = os.path.relpath(dirpath, root)
    if rel == '.':
        rel = '(根目录)'
    py = [f for f in files if f.endswith('.py')]
    html = [f for f in files if f.endswith('.html')]
    if not (py or html):
        continue
    n_lines = 0
    for f in py:
        try:
            with open(os.path.join(dirpath, f), encoding='utf-8') as fh:
                n_lines += sum(1 for _ in fh)
        except Exception:
            pass
    rows.append((rel, len(py), len(html), n_lines))

rows.sort(key=lambda r: -r[3])
print('%-40s %6s %6s %8s' % ('目录', 'py', 'html', 'py行数'))
for rel, p, h, l in rows:
    print('%-40s %6d %6d %8d' % (rel, p, h, l))

print('\n最大 Python 文件：')
big = []
for dirpath, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in skip]
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(dirpath, f)
            try:
                with open(p, encoding='utf-8') as fh:
                    big.append((sum(1 for _ in fh), os.path.relpath(p, root)))
            except Exception:
                pass
big.sort(reverse=True)
for n, p in big[:10]:
    print('  %6d  %s' % (n, p))
