# -*- coding: utf-8 -*-
"""扫描 data/*.json 里引用的 /img/ 路径，列出磁盘上缺失的文件，并生成占位清单"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')
missing = []
seen = set()

pat = re.compile(r'/img/([a-z]+)/([\w.\-]+\.(?:png|jpg|jpeg|webp|gif))', re.I)

for fn in os.listdir(DATA):
    if not fn.endswith('.json'):
        continue
    raw = open(os.path.join(DATA, fn), encoding='utf-8').read()
    for m in pat.finditer(raw):
        sub, name = m.group(1), m.group(2)
        rel = os.path.join('data', 'img', sub, name)
        if rel in seen:
            continue
        seen.add(rel)
        if not os.path.isfile(os.path.join(BASE, rel)):
            missing.append((fn, sub, name))

print('missing: %d' % len(missing))
for fn, sub, name in missing:
    print('  %-12s /img/%s/%s' % (fn, sub, name))
