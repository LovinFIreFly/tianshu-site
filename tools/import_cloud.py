# -*- coding: utf-8 -*-
"""
老数据搬家：把线上那份（Cloudflare 仓库 LovinFireFly/tianshu-data）导进本地 data/

两种拿法，任选一种：

  ① 下载 ZIP（推荐，不用 Token）
     GitHub 打开仓库 → Code → Download ZIP → 解压
     然后：
        python tools/import_cloud.py --dir "C:\\Users\\junbo\\Downloads\\tianshu-data-main"

  ② 直接拉（仓库是私有的，要先设 Token）
        set GITHUB_TOKEN=ghp_你的token
        python tools/import_cloud.py --remote

它会先把你现在的 data/ 备份一份（data_备份-时间戳/），再逐份导入，
最后打印对照表：每份多少条、补了哪些字段、哪些看不懂就跳过。
身份证级别的操作，导坏了也能回滚。
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DATA_DIR, SETTINGS_DEFAULT          # noqa: E402

REPO = 'LovinFireFly/tianshu-data'
BRANCH = 'main'

# 要搬的文件（key 就是 data/<key>.json）
KEYS = ['users', 'scripts', 'bookings', 'pays', 'sessions', 'rooms', 'coupons', 'notices',
        'reviews', 'posts', 'messages', 'favs', 'logs', 'settles', 'wants', 'carmsgs', 'settings']

# 数组型的（settings 是对象，单独处理）
LIST_KEYS = [k for k in KEYS if k != 'settings']

report = []


def load_from_dir(folder, key):
    p = os.path.join(folder, key + '.json')
    if not os.path.exists(p):
        return None
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_from_remote(key):
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print('没设置 GITHUB_TOKEN 环境变量，没法从私有仓库拉。改用 --dir 吧')
        sys.exit(1)
    url = 'https://api.github.com/repos/%s/contents/%s.json?ref=%s' % (REPO, key, BRANCH)
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github.raw',
        'User-Agent': 'tianshu-import'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print('  拉 %s.json 失败：%s' % (key, e))
        return None


# ---------------------------------------------------------------- 字段补齐
def fix_users(rows):
    out = []
    for u in rows:
        if not u.get('phone'):
            report.append('  · 跳过 1 个没手机号的账号记录')
            continue
        u.setdefault('username', u.get('phone'))
        u.setdefault('email', '')
        u.setdefault('role', 'super' if u.get('super') else 'user')
        u.setdefault('super', False)
        u.setdefault('credit', 100)
        u.setdefault('creditLogs', [])
        u.setdefault('invite', '')
        u.setdefault('first', u.get('last') or 0)
        u.setdefault('last', u.get('first') or 0)
        u.setdefault('banned', False)
        if not isinstance(u.get('profile'), dict):
            u['profile'] = {'avatar': '🎭', 'nick': u.get('username'), 'gender': '', 'age': None}
        out.append(u)
    return out


def fix_scripts(rows):
    out = []
    for i, s in enumerate(rows, 1):
        s.setdefault('id', i)
        s.setdefault('title', '未命名剧本')
        s.setdefault('emoji', '🎭')
        s.setdefault('tags', [])
        s.setdefault('players', '6人')
        s.setdefault('dur', '约4小时')
        s.setdefault('diff', 3)
        s.setdefault('price', 128)
        s.setdefault('desc', '')
        s.setdefault('type', '盒装')
        s.setdefault('onSale', True)
        s.setdefault('allowRolePick', False)
        s.setdefault('roles', [])
        s.setdefault('img', '')
        out.append(s)
    return out


def fix_bookings(rows, deposit_ratio):
    out = []
    for b in rows:
        if b.get('status') not in ('booked', 'arrived', 'done', 'cancelled'):
            b['status'] = 'booked'
        players = int(b.get('players') or 1)
        price = float(b.get('price') or 0)
        b.setdefault('amount', round(price * players))
        if not b.get('deposit'):
            b['deposit'] = round(float(b['amount']) * deposit_ratio)
        if not b.get('verifyCode') and b['status'] != 'cancelled':
            b['verifyCode'] = '%06d' % ((int(time.time()) + int(b.get('id') or 0)) % 1000000)
        b.setdefault('emoji', '🎭')
        b.setdefault('mode', '拼车' if b.get('carNew') else '包车')
        b.setdefault('createdAt', b.get('ts') or 0)
        out.append(b)
    return out


def fix_pays(rows):
    out = []
    for o in rows:
        o.setdefault('amount', o.get('deposit'))
        o.setdefault('status', 'paid' if o.get('paidAt') else 'unpaid')
        o.setdefault('channel', 'demo')
        o.setdefault('createdAt', o.get('ts') or 0)
        out.append(o)
    return out


def fix_sessions(rows):
    for s in rows:
        s.setdefault('status', 'open')
        s.setdefault('cap', 6)
        s.setdefault('roomId', '')
        s.setdefault('dm', '')
    return rows


def fix_rooms(rows):
    for i, r in enumerate(rows, 1):
        r.setdefault('id', i)
        r.setdefault('name', '房间%d' % i)
        r.setdefault('cap', 6)
        r.setdefault('dev', '')
    return rows


def fix_generic(rows):
    """其余的表：补个 id 就行，别的不动"""
    for i, x in enumerate(rows):
        if isinstance(x, dict):
            x.setdefault('id', int(time.time() * 1000) + i)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', help='从下载解压出来的文件夹导入')
    ap.add_argument('--remote', action='store_true', help='直接从 GitHub 拉（要 GITHUB_TOKEN）')
    ap.add_argument('--keep', action='store_true', help='不备份现有 data/（默认会备份）')
    args = ap.parse_args()
    if not args.dir and not args.remote:
        print(__doc__)
        return

    # ① 备份现有数据（万一手滑）
    if os.path.isdir(DATA_DIR) and not args.keep:
        bak = os.path.join(ROOT, 'data_备份-%s' % time.strftime('%Y%m%d-%H%M%S'))
        shutil.copytree(DATA_DIR, bak)
        print('已备份现有数据到：%s' % os.path.basename(bak))
    os.makedirs(DATA_DIR, exist_ok=True)

    # ② 先把 settings 读出来（算定金比例要用）
    raw = {}
    for key in KEYS:
        data = load_from_dir(args.dir, key) if args.dir else load_from_remote(key)
        if data is not None:
            raw[key] = data
    settings = dict(SETTINGS_DEFAULT)
    if isinstance(raw.get('settings'), dict):
        settings.update(raw['settings'])
    ratio = float(settings.get('depositRatio') or 0.3)

    # ③ 逐份套字段、写盘
    counts = {}
    for key in LIST_KEYS:
        data = raw.get(key)
        if not isinstance(data, list):
            continue
        if key == 'users':
            rows = fix_users(data)
        elif key == 'scripts':
            rows = fix_scripts(data)
        elif key == 'bookings':
            rows = fix_bookings(data, ratio)
        elif key == 'pays':
            rows = fix_pays(data)
        elif key == 'sessions':
            rows = fix_sessions(data)
        elif key == 'rooms':
            rows = fix_rooms(data)
        else:
            rows = fix_generic(data)
        with open(os.path.join(DATA_DIR, key + '.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        counts[key] = len(rows)

    with open(os.path.join(DATA_DIR, 'settings.json'), 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)
    counts['settings'] = 1

    # ④ 对照表
    print('\n导入结果：')
    for k in KEYS:
        if k in counts:
            print('  %-10s %s 条' % (k, counts[k]))
    if report:
        print('说明：')
        for line in report:
            print(line)
    print('\n搞定。现在双击「启动本地网站」，用原来的账号密码登录试试。')


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
    main()
