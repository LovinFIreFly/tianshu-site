# -*- coding: utf-8 -*-
"""在进程内复现 500 页面并打印真实堆栈（不用起服务）"""
import os, sys, traceback

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app          # noqa: E402
from tianshu.business import get_settings, ui_ver   # noqa: E402

app = create_app()
app.config['TESTING'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True

print('ui_ver =', ui_ver(), '| mobileMode =', get_settings().get('mobileMode'))

c = app.test_client()
with c.session_transaction() as s:
    s['phone'] = '13552158081'      # FireFly（超管）

for path in ['/me', '/', '/scripts', '/admin', '/admin/settings', '/dm']:
    print('\n=== GET', path, '===')
    try:
        r = c.get(path)
        print('  status:', r.status_code)
        if r.status_code >= 400:
            print('  body head:', r.get_data(as_text=True)[:400])
    except Exception:
        traceback.print_exc()
