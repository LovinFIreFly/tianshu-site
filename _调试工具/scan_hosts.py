# -*- coding: utf-8 -*-
"""检查上一步那些片段的"宿主页面"：谁 include 了它们，宿主有没有 extends base（含 csrf.js）"""
import os, re

root = r"C:\Users\junbo\Desktop\网站\tianshu\templates"
CSRF_BASES = {'base.html', 'auth_base.html', 'layout_v1.html', 'auth_v1.html'}
extends_re = re.compile(r'\{%\s*extends\s*[\'"]([^\'"]+)[\'"]')

targets = ['_scripts_grid.html', 'panel_backup.html', 'panel_bookings.html', 'panel_dash.html',
           'panel_dm.html', 'panel_guides.html', 'panel_invoices.html', 'panel_messages.html',
           'panel_notice.html', 'panel_orders.html', 'panel_reports.html', 'panel_reviews.html',
           'panel_scripts.html', 'panel_sessions.html', 'panel_talktips.html', 'panel_users.html',
           'panel_credit.html', 'panel_growth.html', 'panel_msgs.html', 'panel_today.html']

hosts = {}
for dirpath, _, files in os.walk(root):
    for fn in files:
        if not fn.endswith('.html'):
            continue
        p = os.path.join(dirpath, fn)
        with open(p, encoding='utf-8') as f:
            src = f.read()
        for t in targets:
            if t in src and ('include' in src or 'import' in src):
                m = re.search(r'\{%\s*(?:include|import)\s*[\'"][^\'"]*' + re.escape(t), src)
                if m:
                    hosts.setdefault(t, set()).add(os.path.relpath(p, root))

print('片段 -> 宿主页面（宿主 extends）')
for t in targets:
    hs = hosts.get(t)
    if not hs:
        print('  %-24s 没有被任何页面 include（可能是死文件/只在 py 里 render）' % t)
        continue
    for h in hs:
        with open(os.path.join(root, h), encoding='utf-8') as f:
            s2 = f.read()
        e = extends_re.search(s2)
        ok = (e.group(1) in CSRF_BASES) if e else ('csrf.js' in s2)
        print('  %-24s <- %-28s extends=%-16s %s' % (t, h, (e.group(1) if e else '无'),
                                                     'OK' if ok else '**缺令牌**'))
