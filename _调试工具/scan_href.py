# -*- coding: utf-8 -*-
"""扫描模板里所有"可疑"的 href：不是 / 开头、不是 http/#/{{/javascript 的相对或中文链接"""
import os, re

root = r"C:\Users\junbo\Desktop\网站\tianshu\templates"
pat = re.compile(r'href\s*=\s*"([^"]*)"')
ok_prefix = ('/', 'http', '#', '{{', 'javascript', 'mailto', 'tel')

found = 0
for dirpath, _, files in os.walk(root):
    for fn in files:
        if not fn.endswith('.html'):
            continue
        p = os.path.join(dirpath, fn)
        with open(p, encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                for m in pat.finditer(line):
                    v = m.group(1).strip()
                    if not v or v.startswith(ok_prefix):
                        continue
                    found += 1
                    print('%s:%d  href="%s"' % (os.path.relpath(p, root), i, v))
print('--- 可疑 href %d 条 ---' % found)
