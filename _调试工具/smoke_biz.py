# -*- coding: utf-8 -*-
"""体检 F：业务函数烟雾测试 —— 用真实数据把 business 里的函数都跑一遍，
专门抓"碰到某类数据就炸"的隐藏 Bug（比如除零、None 参与运算、字段缺失）"""
import os, sys, inspect, traceback

sys.path.insert(0, r"C:\Users\junbo\Desktop\网站")
os.environ.setdefault('TS_DATA_DIR', r"C:\Users\junbo\Desktop\网站\data")

from tianshu import create_app, business
from tianshu.db import db

app = create_app()
problems = []

with app.app_context():
    scripts = db.rows('scripts')
    users = db.rows('users')
    bookings = db.rows('bookings')

    # 1) 逐个剧本：人数区间 / 算价 / 评分
    for sc in scripts:
        for fn_name in ('player_range', 'script_rating', 'reviews_of'):
            fn = getattr(business, fn_name, None)
            if not callable(fn):
                continue
            try:
                try:
                    fn(sc)
                except TypeError:
                    fn(sc.get('id'))
            except Exception as e:
                problems.append('%s(%s): %s' % (fn_name, sc.get('title'), e))
                print('  ✗ %s(%s) -> %s' % (fn_name, sc.get('title'), e))

    # 2) 逐个用户：收藏分组 / 角色 / 通知
    for u in users[:10]:
        for fn_name in ('fav_groups', 'roles_of', 'role_of', 'unread_count', 'my_notices'):
            fn = getattr(business, fn_name, None)
            if not callable(fn):
                continue
            try:
                fn(u)
            except TypeError:
                pass
            except Exception as e:
                problems.append('%s(%s): %s' % (fn_name, u.get('username'), e))
                print('  ✗ %s(%s) -> %s' % (fn_name, u.get('username'), e))

    # 3) 无参函数：全站统计类
    for name in dir(business):
        if name.startswith('_'):
            continue
        fn = getattr(business, name)
        if not callable(fn) or inspect.isclass(fn):
            continue
        try:
            sig = inspect.signature(fn)
            if any(p.default is inspect.Parameter.empty and p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                   for p in sig.parameters.values()):
                continue          # 需要必填参数，跳过
            fn()
        except TypeError:
            pass
        except Exception as e:
            problems.append('%s(): %s' % (name, e))
            print('  ✗ %s() -> %s: %s' % (name, type(e).__name__, e))

print('\n===== 结果 =====')
print('业务函数异常：%d 处' % len(problems))
for p in problems:
    print(' -', p)
