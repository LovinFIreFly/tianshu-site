# -*- coding: utf-8 -*-
"""从线上站点把 /img/ 下的图拉回本地 data/img/（只拉比本地大、且确实像张图的）。

用法：
    python tools/pull_live_imgs.py                 # 默认 https://tianshu.lovinfirefly.cn
    python tools/pull_live_imgs.py https://你的域名
"""
import json
import os
import re
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_args = [a for a in sys.argv[1:] if not a.startswith('--')]
HOST = (_args[0] if _args else 'https://tianshu.lovinfirefly.cn').rstrip('/')
IMG = os.path.join(BASE, 'data', 'img')

# 用电脑 UA：手机 UA 会被站点的手机分流钩子拦到 /m/（拿回来的是 HTML 不是图）
UA = {'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')}

# 从 data/*.json 里收集所有 /img/ 引用，去重
refs = set()
pat = re.compile(r'/img/([a-z]+)/([\w.\-]+\.(?:png|jpg|jpeg|webp|gif))', re.I)
for fn in os.listdir(os.path.join(BASE, 'data')):
    if fn.endswith('.json'):
        refs |= set(pat.findall(open(os.path.join(BASE, 'data', fn), encoding='utf-8').read()))

# 线上库引用的文件名可能和本地不同：抓站点页面里真实出现的 /img/ 路径
if '--scan' in sys.argv:
    for path in ('/', '/scripts', '/comm', '/me', '/car'):
        try:
            req = urllib.request.Request(HOST + path, headers=UA)
            html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'ignore')
        except Exception as e:
            print('  scan %s: %s' % (path, e))
            continue
        found = pat.findall(html)
        print('  scan %-9s -> %d refs' % (path, len(found)))
        refs |= set(found)

print('refs: %d, host: %s' % (len(refs), HOST))
ok = fail = skip = 0
for sub, name in sorted(refs):
    url = '%s/img/%s/%s' % (HOST, sub, name)
    dst = os.path.join(IMG, sub, name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    local = os.path.getsize(dst) if os.path.isfile(dst) else 0
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
    except Exception as e:
        print('  FAIL %-30s %s' % (name, e))
        fail += 1
        continue
    if len(data) <= 2000:
        print('  tiny %-30s %d bytes (线上也是占位图，跳过)' % (name, len(data)))
        skip += 1
        continue
    if len(data) <= local:
        print('  same %-30s %d <= local %d' % (name, len(data), local))
        skip += 1
        continue
    with open(dst, 'wb') as f:
        f.write(data)
    print('  GOT  %-30s %5d -> %6d bytes' % (name, local, len(data)))
    ok += 1

print('\ngot %d, tiny/same %d, fail %d' % (ok, skip, fail))
