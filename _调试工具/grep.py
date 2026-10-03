# -*- coding: utf-8 -*-
"""UTF-8 安全的内容搜索（findstr 对中文不可靠）"""
import os, sys

root = r"C:\Users\junbo\Desktop\网站\tianshu"
kw = sys.argv[1]
exts = ('.html', '.py', '.js', '.css')

hits = 0
for dirpath, _, files in os.walk(root):
    if '__pycache__' in dirpath:
        continue
    for fn in files:
        if not fn.endswith(exts):
            continue
        p = os.path.join(dirpath, fn)
        try:
            with open(p, encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if kw in line:
                        hits += 1
                        print('%s:%d: %s' % (p.replace(root, ''), i, line.rstrip()[:160]))
        except Exception:
            pass
print('--- 命中 %d 处 ---' % hits)
