# -*- coding: utf-8 -*-
"""把从线上（云端）拉回来的真图挂回本地库。

两步：
  1) 抓线上 /scripts 页面，解析出 剧本 id -> /img/cover/xxx.jpg 的对应关系
  2) 写回 data/scripts.json：给对应剧本填上 cover，并把缺的图按 id 补一份
     （本地库里还有别的剧本没有真图时，复用拉回来的图，避免又变 1x1 占位）

用法：python tools/use_live_imgs.py
"""
import json
import os
import re
import shutil
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')
IMG = os.path.join(BASE, 'data', 'img')
HOST = 'https://tianshu.lovinfirefly.cn'
UA = {'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')}


def live_map():
    """线上：剧本 id -> 封面路径"""
    out = {}
    try:
        req = urllib.request.Request(HOST + '/scripts', headers=UA)
        html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'ignore')
    except Exception as e:
        print('scan failed:', e)
        return out
    # 卡片：<a class="pcard3__cover" href="/scripts/1"> <img src="/img/cover/xxx.jpg"
    for m in re.finditer(r'href="/scripts/(\d+)"[^>]*>\s*<img[^>]+src="(/img/cover/[\w.\-]+)"', html):
        out[m.group(1)] = m.group(2)
    # 兜底：按出现顺序，只要 href 和 img 在同一段里
    if not out:
        for m in re.finditer(r'/scripts/(\d+)"', html):
            seg = html[m.end():m.end() + 400]
            g = re.search(r'/img/cover/[\w.\-]+', seg)
            if g:
                out[m.group(1)] = g.group(0)
    return out


def load(fn):
    p = os.path.join(DATA, fn)
    return json.load(open(p, encoding='utf-8')), p


def main():
    m = live_map()
    print('live covers: %s' % m)
    if not m:
        print('no live cover found; nothing to do')
        return
    scripts, path = load('scripts.json')
    rows = scripts if isinstance(scripts, list) else (scripts.get('scripts') or [])
    live_files = [v for v in m.values() if os.path.isfile(os.path.join(IMG, v.replace('/img/', '')))]

    changed = 0
    for s in rows:
        sid = str(s.get('id'))
        if sid in m:
            s['cover'] = m[sid]
            changed += 1
            print('  script %-6s -> %s' % (sid, m[sid]))
        elif not s.get('cover') and live_files:
            # 本地多出来的剧本没有真图，就复用一张，别留空
            pick = live_files[int(sid or '0', 10) % len(live_files)] if (sid or '').isdigit() else live_files[0]
            s['cover'] = pick
            changed += 1
            print('  script %-6s -> %s (复用)' % (sid, pick))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)
    print('scripts updated: %d, saved to %s' % (changed, path))

    # 头像：线上那张也给第一个用户用上（本地头像都是占位）
    av = [f for f in os.listdir(os.path.join(IMG, 'avatar'))
          if os.path.getsize(os.path.join(IMG, 'avatar', f)) > 20000]
    # 优先用从云端拉回来的那张（.jpg），其次才是本地生成的
    av.sort(key=lambda f: (not f.lower().endswith('.jpg'), f))
    if av:
        users, upath = load('users.json')
        ulist = users if isinstance(users, list) else (users.get('users') or [])
        for u in ulist[:1]:
            prof = u.setdefault('profile', {})
            prof['avatar'] = '/img/avatar/' + av[0]
            print('  avatar ->', prof['avatar'])
        with open(upath, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        print('users updated')


if __name__ == '__main__':
    main()
