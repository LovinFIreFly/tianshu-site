# -*- coding: utf-8 -*-
"""
================================================================
  甜薯剧本杀 · 本地 Python 版（看得懂、改得动）
================================================================
【这是什么】
  把你线上那套「Cloudflare 云函数 + JSON 数据」的逻辑，用 Python 重写了一份，
  在你自己的电脑上跑起来。运行后浏览器打开 http://localhost:8000
  看到的就是和你线上网站一模一样的界面，但所有数据都在你电脑的 data 文件夹里。

【怎么运行（3 步）】
  1. 安装 Python：到 python.org 下载 Python 3，安装时务必勾选
     "Add python.exe to PATH"（把 Python 加进环境变量）
  2. 双击本文件；或在本文件夹按住 Shift + 右键 →「在此处打开 PowerShell」，输入：
        python app.py
  3. 浏览器打开：  http://localhost:8000

【内置账号（第一次运行自动创建，密码都是 123123）】
  超级管理员  FireFly
  管理员      FireFly2
  DM         dm测试
  客户       调试debug

【想改东西，看哪里】
  · 价格 / 定金比例 / 免费取消时限 → 用管理员登录网页后台直接改（存进 data/settings.json）
  · 账号、预约、剧本等具体数据      → 直接改 data/ 里的 .json 文件，记事本就能编辑
  · 经营规则（算价、扣信用分、分成） → 看下面【6. 业务逻辑】那一段，每块都有中文注释
  · 换个端口号（8000 被占用时）     → 改下面的 PORT

【重要提醒】
  这只是「本地版」，你在这里怎么改都不会影响线上网站；
  线上仍然由 Cloudflare 上那份代码负责，两边数据互不相通。
================================================================
"""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ================================================================
# 1. 基本配置（这些数字可以放心改）
# ================================================================
PORT = 8000                                       # 网页地址的端口
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')          # 所有数据都存在这里
IMG_DIR = os.path.join(DATA_DIR, 'img')            # 上传的图片存在这里

TOKEN_DAYS = 7                                     # 登录有效期（天），和线上一致
MAX_IMG_BYTES = 700 * 1024                         # 单张图片大小上限（700KB）

# 默认经营参数：第一次运行会写进 data/settings.json，之后在网页后台改的就是它
DEFAULT_SETTINGS = {
    "reviewsEnabled": True,     # 前台是否展示评分
    "dmRate": 0.10,             # DM 分成比例（10%）
    "dmFee": 20,                # 指定 DM 的加价（元/人）
    "depositRatio": 0.30,       # 定金比例（总价的 30%）
    "freeCancelHours": 24,      # 开场前多少小时内取消算「临期取消」
    "lateCancelPenalty": 2,     # 临期取消扣多少信用分
    "notice": "",               # 首页公告
    "carTags": ["不跳车", "准时到场", "新手友好", "硬核玩家"],
}

# ================================================================
# 2. 小工具函数（读写文件、加密、令牌、限流）
# ================================================================
def now_ms():
    """当前时间（毫秒），和 JavaScript 用的时间单位一致"""
    return int(time.time() * 1000)


_LOCK = threading.RLock()          # 多人同时访问时，防止两个请求同时写坏同一个文件


def data_path(key):
    return os.path.join(DATA_DIR, key + '.json')


def read_json(key):
    """读 data/<key>.json；文件不存在时返回 None（前端会显示「暂无数据」）"""
    p = data_path(key)
    if not os.path.exists(p):
        return None
    with _LOCK:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print('[读取失败] %s：%s' % (key, e))
            return None


def write_json(key, obj):
    """写 data/<key>.json
    先写临时文件再改名，这样即使写到一半断电，也不会把原来的数据写坏。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    p, tmp = data_path(key), data_path(key) + '.tmp'
    with _LOCK:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)


def read_list(key):
    """读一个数组型数据（账号、预约…），拿不到就当空数组"""
    v = read_json(key)
    return v if isinstance(v, list) else []


def hash_password(pw):
    """把密码加密后存起来（绝不存明文）
    用的是 PBKDF2-SHA256 + 随机盐 + 10 万次迭代，和线上完全一致，
    所以你从线上导出的数据，在本地也能直接登录。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), 100000)
    return 'pbkdf2$100000$%s$%s' % (salt, dk.hex())


def legacy_hash(p):
    """线上老账号用的弱哈希（只为兼容，登录成功会被自动升级）"""
    h = 5381
    for ch in p:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return 'h' + format(h, 'x')


def verify_password(pw, stored):
    """校验密码：新格式走 PBKDF2，老格式走弱哈希"""
    s = str(stored or '')
    if s.startswith('pbkdf2$'):
        try:
            _, iterations, salt, _h = s.split('$')
            dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), int(iterations))
            calc = 'pbkdf2$%s$%s$%s' % (iterations, salt, dk.hex())
            return hmac.compare_digest(calc, s)
        except Exception:
            return False
    return legacy_hash(pw) == s


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')


def _b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


_SECRET = None


def server_secret():
    """本机签名密钥：首次运行自动生成，保存在 data/secret.key
    （用它给登录令牌签名，别人伪造不了——就是"防篡改"的核心）"""
    global _SECRET
    if _SECRET is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(os.path.join(DATA_DIR, 'secret.key')):
            with open(os.path.join(DATA_DIR, 'secret.key'), 'w', encoding='utf-8') as f:
                f.write(secrets.token_hex(32))
        with open(os.path.join(DATA_DIR, 'secret.key'), 'r', encoding='utf-8') as f:
            _SECRET = f.read().strip()
    return _SECRET


def make_token(user):
    """生成登录令牌（前端把它存在浏览器里，每次请求带上来）"""
    role = 'super' if (user.get('super') is True or user.get('role') == 'super') else (user.get('role') or 'user')
    payload = {'phone': user.get('phone', ''), 'username': user.get('username', ''), 'role': role,
               'exp': now_ms() + TOKEN_DAYS * 86400000}
    p = _b64e(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    sig = _b64e(hmac.new(server_secret().encode('utf-8'), p.encode('utf-8'), hashlib.sha256).digest())
    return p + '.' + sig


def read_token(tok):
    """校验令牌：签名不对或已过期 → 返回 None（也就是"没登录"）"""
    try:
        p, s = str(tok or '').split('.')
        calc = _b64e(hmac.new(server_secret().encode('utf-8'), p.encode('utf-8'), hashlib.sha256).digest())
        if not hmac.compare_digest(calc, s):
            return None
        obj = json.loads(_b64d(p).decode('utf-8'))
        if not obj.get('exp') or obj['exp'] < now_ms():
            return None
        return obj
    except Exception:
        return None


_RL = {}          # 限流记录：{"键": [每次访问的时间]}


def rate(key, limit, window_ms):
    """简单的限流：同一个 key 在 window_ms 毫秒内最多访问 limit 次
    作用是防止有人疯狂试密码 / 刷验证码（线上也有这一层，规则一样）"""
    t = now_ms()
    arr = [x for x in _RL.get(key, []) if t - x < window_ms]
    if len(arr) >= limit:
        _RL[key] = arr
        return False
    arr.append(t)
    _RL[key] = arr
    return True


def rate_peek(key, window_ms):
    """只查看次数，不计数（用于"只统计失败次数"的登录限流）"""
    t = now_ms()
    arr = [x for x in _RL.get(key, []) if t - x < window_ms]
    _RL[key] = arr
    return len(arr)


def clean_text(t, max_len=500):
    """清洗用户输入：去掉控制字符、限制长度（防注入/超长内容）"""
    s = '' if t is None else str(t)
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    return s[:max_len]


def public_user(u):
    """对外展示用的人（只有昵称/头像/性别/年龄段，绝不含手机号）
    —— 线上也是这么做的，保护客户隐私"""
    p = u.get('profile') or {}
    return {
        'username': u.get('username', ''),
        'role': 'super' if u.get('super') is True else (u.get('role') or 'user'),
        'profile': {'nick': p.get('nick', ''), 'avatar': p.get('avatar', '🎭'),
                    'gender': p.get('gender', ''), 'ageBucket': age_bucket(p.get('age'))},
    }


def self_user(u):
    """本人可见的完整档案（含信用分；但永远不含密码）"""
    out = {k: v for k, v in u.items() if k != 'password'}
    out.setdefault('credit', 100)
    out.setdefault('creditLogs', [])
    out.setdefault('profile', {'avatar': '🎭', 'nick': '', 'gender': '', 'age': None})
    out['role'] = 'super' if u.get('super') is True else (u.get('role') or 'user')
    return out


def age_bucket(age):
    """把年龄变成"年龄段"，这样拼车时能看到"25-30岁"，但看不到具体年龄"""
    try:
        n = int(age)
    except Exception:
        return ''
    if n <= 18:
        return '18岁及以下'
    if n <= 24:
        return '18-24'
    if n <= 30:
        return '25-30'
    if n <= 35:
        return '31-35'
    if n <= 45:
        return '36-45'
    return '45岁以上'


def get_settings():
    """读经营参数（网页后台改的就是它，读不到就用默认值）"""
    s = read_json('settings')
    out = dict(DEFAULT_SETTINGS)
    if isinstance(s, dict):
        out.update(s)
    return out


def day_label(ts):
    """把时间戳变成「9月24日 周四」这种看得懂的说法"""
    d = time.localtime((ts or 0) / 1000)
    week = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][d.tm_wday]
    return '%d月%d日 %s' % (d.tm_mon, d.tm_mday, week)


# ================================================================
# 3. 首次运行：创建内置账号和默认设置
# ================================================================
SEED_USERS = [
    ('13552158081', 'FireFly', 'super', True),
    ('18732303179', 'FireFly2', 'admin', False),
    ('12345678901', 'dm测试', 'dm', False),
    ('13800000000', '调试debug', 'user', False),
]


def seed_if_empty():
    """第一次运行时自动准备好账号和设置，保证你能直接登录体验"""
    os.makedirs(IMG_DIR, exist_ok=True)
    server_secret()
    if read_json('users') is None:
        t = now_ms()
        users = []
        for i, (phone, name, role, is_super) in enumerate(SEED_USERS):
            users.append({
                'phone': phone, 'username': name, 'email': '', 'role': role, 'super': is_super,
                'password': hash_password('123123'), 'credit': 100, 'creditLogs': [],
                'profile': {'avatar': '🎭', 'nick': name, 'gender': '', 'age': None},
                'first': t + i, 'last': t + i, 'invite': 'TS%04d' % (i + 1),
                'banned': False, 'banReason': '',
            })
        write_json('users', users)
        print('[初始化] 已创建 %d 个内置账号（密码都是 123123）' % len(users))
    if read_json('settings') is None:
        write_json('settings', DEFAULT_SETTINGS)
        print('[初始化] 已创建默认经营参数 data/settings.json')


# ================================================================
# 4. 业务小逻辑（通知、车队、统计）
# ================================================================
def notify(phone, title, text, kind='system'):
    """给某人发一条站内通知（会出现在他网页上的「消息中心」）"""
    lst = read_list('notices')
    lst.insert(0, {'id': now_ms() + secrets.randbelow(1000), 'title': title, 'text': text,
                   'at': now_ms(), 'to': [phone], 'by': '系统', 'readBy': [], 'kind': kind})
    write_json('notices', lst[:500])


def push_log(who, role, text):
    """记一条操作日志（管理端「操作日志」里能看到谁干了什么）"""
    lst = read_list('logs')
    lst.insert(0, {'id': now_ms(), 'by': who, 'role': role, 'text': text, 'at': now_ms()})
    write_json('logs', lst[:500])


def find_user(phone):
    for u in read_list('users'):
        if str(u.get('phone')) == str(phone):
            return u
    return None


def player_range(script):
    """从「4-6人」这种文字里解析出最少/最多人数"""
    m = re.search(r'(\d+)\s*[-~到]\s*(\d+)', str(script.get('players') or ''))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d+)', str(script.get('players') or ''))
    return (int(m.group(1)), int(m.group(1))) if m else (1, 8)


def car_pool(me_phone=''):
    """拼车大厅的数据：车主 + 已上车的人
    注意：只返回昵称/性别/年龄段，不含手机号 —— 客户之间互相看不到手机号（隐私保护）"""
    bookings = read_list('bookings')
    users = {str(u.get('phone')): u for u in read_list('users')}
    t0 = int(time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d'))) * 1000
    out = []
    for ob in bookings:
        if not (ob.get('carNew') is True and ob.get('status') == 'booked' and (ob.get('ts') or 0) >= t0):
            continue
        mates = [b for b in bookings if not b.get('carNew') and b.get('carOwner') == ob.get('username')
                 and b.get('sid') == ob.get('sid') and b.get('ts') == ob.get('ts')
                 and b.get('time') == ob.get('time') and b.get('status') != 'cancelled']
        joined = (ob.get('players') or 1) + sum((b.get('players') or 1) for b in mates)
        members = []
        for b in [ob] + mates:
            a = users.get(str(b.get('phone')), {})
            p = a.get('profile') or {}
            members.append({'username': b.get('username') or a.get('username') or '玩家',
                            'gender': p.get('gender', ''), 'ageBucket': age_bucket(p.get('age')),
                            'players': b.get('players') or 1})
        out.append({'id': 'own-%s' % ob.get('id'), 'sid': ob.get('sid'), 'ts': ob.get('ts'),
                    'time': ob.get('time'), 'owner': ob.get('username') or '玩家',
                    'tags': ob.get('carTags') or [], 'joined': joined,
                    'cap': ob.get('carCap') or 8, 'min': ob.get('carMin') or 4,
                    'need': max(0, (ob.get('carMin') or 4) - joined), 'reserved': ob.get('reserved') or 0,
                    'members': members,
                    'mine': bool(me_phone and any(str(b.get('phone')) == str(me_phone) for b in [ob] + mates))})
    out.sort(key=lambda c: (c.get('ts') or 0, str(c.get('time'))))
    return out


def agg_summary(me_phone=''):
    """首页/剧本页要用的统计：评分、每场人数、拼车队列、人气榜
    （公开数据，谁都能看，但不含任何人的手机号）"""
    bookings, reviews = read_list('bookings'), read_list('reviews')
    stats = {}

    def bucket(sid):
        return stats.setdefault(str(sid), {'plays': 0, 'sum': 0.0, 'n': 0})

    for b in bookings:
        if b.get('status') != 'cancelled':
            bucket(b.get('sid'))['plays'] += 1
    for r in reviews:
        if not r.get('hidden'):
            s = bucket(r.get('sid'))
            s['sum'] += float(r.get('rating') or 0)
            s['n'] += 1
    script_stats = {k: {'plays': v['plays'],
                        'rating': round(v['sum'] / v['n'], 1) if v['n'] else 0,
                        'ratingCount': v['n']} for k, v in stats.items()}
    session_join = {}
    for b in bookings:
        if b.get('status') != 'cancelled' and b.get('sessionId'):
            k = str(b['sessionId'])
            session_join[k] = session_join.get(k, 0) + (b.get('players') or 1)
    hot = [{'sid': k, 'plays': v['plays'], 'rating': v['rating']} for k, v in script_stats.items()]
    hot.sort(key=lambda x: -x['plays'])
    my_coupons = []
    if me_phone:
        my_coupons = [{'id': c.get('id'), 'amount': c.get('amount'), 'minAmount': c.get('minAmount'), 'exp': c.get('exp')}
                      for c in read_list('coupons')
                      if not c.get('used') and (c.get('all') or str(c.get('phone')) == str(me_phone))
                      and (not c.get('exp') or c.get('exp') > now_ms())]
    return {'scriptStats': script_stats, 'sessionJoin': session_join,
            'carPool': car_pool(me_phone), 'hotRank': hot[:10], 'myCoupons': my_coupons}


# ================================================================
# 5. 预约与订单（★ 最核心的一段，改规则就改这里）
# ================================================================
def create_booking(user, body):
    """【下单】创建预约 + 自动生成「待付定金」订单
    为什么要放服务端算？—— 因为金额如果由浏览器算，别人按 F12 就能把 288 元改成 1 元。
    所以：价格、定金、优惠券、余位、角色占用，全部在这里算和校验，前端改不了。"""
    st = get_settings()
    scripts = read_list('scripts')
    sc = next((s for s in scripts if str(s.get('id')) == str(body.get('sid'))), None)
    if not sc:
        return {'error': '剧本不存在（先让管理员登录一次，剧本会自动同步到本地）'}, 404
    if sc.get('onSale') is False:
        return {'error': '该剧本已下架'}, 400
    ts = int(body.get('ts') or 0)
    tm = str(body.get('time') or '19:00')
    if not ts:
        return {'error': '请选择日期'}, 400
    lo, hi = player_range(sc)
    players = max(1, min(hi, int(body.get('players') or lo)))
    mode = '包车' if body.get('mode') == '包车' else '拼车'

    # ① 如果这一天这个时段店里已经排了场次，就检查还能不能坐下（防超卖）
    session_id = 0
    bookings = read_list('bookings')
    ses = next((x for x in read_list('sessions')
                if str(x.get('sid')) == str(sc.get('id')) and x.get('ts') == ts
                and x.get('time') == tm and x.get('status') == 'open'), None)
    if ses:
        used = sum((b.get('players') or 1) for b in bookings
                   if b.get('sessionId') == ses.get('id') and b.get('status') != 'cancelled')
        left = (ses.get('cap') or 99) - used
        if left < players:
            return {'error': '该场次仅剩 %d 个位置，请调整人数或换个时段' % max(0, left)}, 409
        session_id = ses.get('id')

    # ② 线上选角：只有管理员给这个剧本开了「可提前选角」才允许
    role = ''
    if sc.get('allowRolePick') is True:
        role = clean_text(body.get('role'), 20)
        if role:
            names = [r.get('name') for r in (sc.get('roles') or [])]
            if names and role not in names:
                return {'error': '角色不存在'}, 400
            # 同一个剧本、同一天、同一时段，同一个角色只能被一个人选走
            taken = any(str(b.get('sid')) == str(sc.get('id')) and b.get('ts') == ts and b.get('time') == tm
                        and b.get('role') == role and b.get('status') != 'cancelled' for b in bookings)
            if taken:
                return {'error': '角色「%s」已被选走，换一个吧' % role}, 409

    # ③ 优惠券
    coupon = None
    if body.get('couponId'):
        coupon = next((c for c in read_list('coupons')
                       if str(c.get('id')) == str(body.get('couponId')) and not c.get('used')
                       and (c.get('all') or str(c.get('phone')) == str(user.get('phone')))
                       and (not c.get('exp') or c.get('exp') > now_ms())), None)
        if not coupon:
            return {'error': '优惠券不可用'}, 400

    # ④ 算钱：单价 = 剧本价 +（指定 DM 的加价）；总价 = 单价 × 人数
    price = (float(sc.get('price') or 0)) + (float(st['dmFee']) if body.get('dmPhone') else 0)
    amount = price * players
    deposit = round(amount * float(st['depositRatio']))          # 定金 = 总价 × 定金比例
    if coupon:
        deposit = max(0, deposit - int(coupon.get('amount') or 0))

    bid = now_ms() + secrets.randbelow(90)
    booking = {'id': bid, 'phone': user.get('phone'), 'username': user.get('username'),
               'sid': sc.get('id'), 'title': sc.get('title'), 'emoji': sc.get('emoji', '🎭'),
               'g': sc.get('g', ''), 'day': day_label(ts), 'ts': ts, 'time': tm,
               'players': players, 'price': price, 'status': 'booked', 'mode': mode,
               'carNew': mode == '拼车', 'carOwner': user.get('username') if mode == '拼车' else None,
               'carCap': hi, 'carMin': min(lo, players), 'carTags': [], 'reserved': 0,
               'sessionId': session_id, 'dmPhone': clean_text(body.get('dmPhone'), 20), 'role': role,
               'verifyCode': '%06d' % secrets.randbelow(1000000),       # 到店核销码
               'couponId': coupon.get('id') if coupon else 0, 'createdAt': now_ms()}
    order = {'id': now_ms() + 91, 'bid': bid, 'phone': user.get('phone'), 'username': user.get('username'),
             'title': sc.get('title'), 'day': booking['day'], 'ts': ts, 'time': tm, 'players': players,
             'price': price, 'amount': amount, 'deposit': deposit,
             'couponId': coupon.get('id') if coupon else 0, 'status': 'unpaid', 'channel': 'demo',
             'createdAt': now_ms(), 'paidAt': 0, 'refundAt': 0, 'tradeNo': ''}

    bookings.append(booking)
    write_json('bookings', bookings)
    pays = read_list('pays')
    pays.append(order)
    write_json('pays', pays)
    if coupon:                                   # 券用掉了就标记一下，不能重复用
        coupons = read_list('coupons')
        for c in coupons:
            if str(c.get('id')) == str(coupon.get('id')):
                c['used'], c['usedAt'], c['usedBy'] = True, now_ms(), user.get('phone')
        write_json('coupons', coupons)
    notify(user.get('phone'), '待支付定金',
           '《%s》%s %s 已锁定座位，请在 30 分钟内支付定金 ¥%s。' % (sc.get('title'), booking['day'], tm, deposit),
           'pay')
    return {'ok': True, 'booking': booking, 'order': order}, 200


def order_act(user, body, is_staff):
    """【订单】支付 / 退款
    规则：能不能退、退多少、要不要扣信用分，全部由服务端判断（前端说了不算）"""
    st = get_settings()
    pays = read_list('pays')
    order = next((o for o in pays if str(o.get('id')) == str(body.get('id'))), None)
    if not order:
        return {'error': '订单不存在'}, 404
    if str(order.get('phone')) != str(user.get('phone')) and not is_staff:
        return {'error': '无权操作该订单'}, 403
    bookings = read_list('bookings')
    booking = next((b for b in bookings if b.get('id') == order.get('bid')), None)
    action = str(body.get('action') or '')

    if action == 'pay':
        if order.get('status') != 'unpaid':
            return {'error': '该订单当前不可支付'}, 400
        order['status'] = 'paid'
        order['paidAt'] = now_ms()
        order['tradeNo'] = 'DEMO%d' % now_ms()
        write_json('pays', pays)
        notify(order.get('phone'), '定金已支付 ✅',
               '《%s》定金 ¥%s 已确认，座位锁定，等你来玩～' % (order.get('title'), order.get('deposit')), 'pay')
        return {'ok': True, 'status': 'paid'}, 200

    if action == 'refund':
        if order.get('status') not in ('paid', 'unpaid'):
            return {'error': '该订单不可退款'}, 400
        # 距离开场还有几个小时？够不够「免费取消」的时限？
        hours = ((booking.get('ts') or 0) - now_ms()) / 3600000 if booking else 999
        free = hours >= float(st['freeCancelHours'])
        if not free and not is_staff:
            return {'error': '距离开场不足 %s 小时，按门店规则定金不退。如需特殊处理请联系门店。' % st['freeCancelHours'],
                    'needConfirm': True}, 200
        order['status'] = 'refunded' if free else 'closed'
        order['refundAt'] = now_ms()
        order['refundAmount'] = order.get('deposit') if free else 0
        write_json('pays', pays)
        if booking:
            booking['status'] = 'cancelled'
            booking['cancelAt'] = now_ms()
            booking['cancelBy'] = 'staff' if is_staff else 'user'
            write_json('bookings', bookings)
            # 临期取消：按门店规则扣信用分（改规则就改这里 / 或改 settings.json 的 lateCancelPenalty）
            if not free and not is_staff and int(st['lateCancelPenalty']) > 0:
                users = read_list('users')
                for u in users:
                    if str(u.get('phone')) == str(order.get('phone')):
                        before = int(u.get('credit', 100))
                        after = max(0, before - int(st['lateCancelPenalty']) * 10)
                        u['credit'] = after
                        logs = u.get('creditLogs') or []
                        logs.insert(0, {'id': now_ms(), 'delta': after - before,
                                        'reason': '临期取消（未达免费取消时限）', 'by': '系统', 'at': now_ms()})
                        u['creditLogs'] = logs[:100]
                        notify(u.get('phone'), '信用分变动',
                               '因临期取消，信用分 %d → %d 分。按时到场完成开本可逐步恢复。' % (before, after), 'credit')
                write_json('users', users)
        notify(order.get('phone'), '退款已处理' if free else '取消已登记',
               ('《%s》定金 ¥%s 已退回，预约已取消。' % (order.get('title'), order.get('deposit'))) if free
               else ('《%s》预约已取消（超出免费取消时限，定金不退）。' % order.get('title')), 'pay')
        return {'ok': True, 'refunded': free, 'amount': order.get('deposit') if free else 0}, 200

    return {'error': '未知操作'}, 400


def car_action(user, body, action):
    """【拼车】上车 / 退出 / 候补 / 聊天 / 设置车队标签"""
    phone, name = user.get('phone'), user.get('username')
    bookings = read_list('bookings')
    owner_id = str(body.get('carId') or '').replace('own-', '')
    ob = next((b for b in bookings if str(b.get('id')) == owner_id and b.get('carNew') is True), None)
    if not ob:
        return {'error': '车队已失效'}, 404

    def mates():
        return [b for b in bookings if not b.get('carNew') and b.get('carOwner') == ob.get('username')
                and b.get('sid') == ob.get('sid') and b.get('ts') == ob.get('ts')
                and b.get('time') == ob.get('time') and b.get('status') != 'cancelled']

    in_car = any(str(b.get('phone')) == str(phone) and b.get('sid') == ob.get('sid') and b.get('ts') == ob.get('ts')
                 and b.get('time') == ob.get('time') and b.get('status') != 'cancelled' for b in bookings)

    if action == 'join':
        if in_car:
            return {'error': '你已在该车队中'}, 409
        joined = (ob.get('players') or 1) + sum((b.get('players') or 1) for b in mates())
        if (ob.get('carCap') or 8) - joined - (ob.get('reserved') or 0) < 1:
            return {'error': '车位已满，可加入候补队列'}, 409
        rec = {'id': now_ms(), 'phone': phone, 'username': name, 'sid': ob.get('sid'), 'title': ob.get('title'),
               'emoji': ob.get('emoji'), 'g': ob.get('g'), 'day': ob.get('day'), 'ts': ob.get('ts'),
               'time': ob.get('time'), 'players': 1, 'price': ob.get('price'), 'status': 'booked',
               'mode': '拼车', 'carNew': False, 'carOwner': ob.get('username'),
               'sessionId': ob.get('sessionId') or 0, 'dmPhone': '', 'role': '', 'verifyCode': '',
               'createdAt': now_ms()}
        bookings.append(rec)
        write_json('bookings', bookings)
        notify(ob.get('phone'), '有人加入你的车队',
               '%s 加入了《%s》%s %s 的车队。' % (name, ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        if joined + 1 >= (ob.get('carMin') or 4):          # 够最低人数了 → 通知所有人「成局」
            for x in [ob] + mates() + [rec]:
                if x.get('phone'):
                    notify(x.get('phone'), '车队已成局 🎉',
                           '《%s》%s %s 已达最低成局人数，准时到场哦～' % (ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        return {'ok': True}, 200

    if action == 'quit':
        if not in_car:
            return {'error': '你不在该车队中'}, 400
        for b in bookings:
            if (str(b.get('phone')) == str(phone) and not b.get('carNew')
                    and b.get('carOwner') == ob.get('username') and b.get('sid') == ob.get('sid')
                    and b.get('ts') == ob.get('ts') and b.get('time') == ob.get('time')
                    and b.get('status') == 'booked'):
                b['status'], b['cancelAt'] = 'cancelled', now_ms()
        write_json('bookings', bookings)
        notify(ob.get('phone'), '有人退出车队',
               '%s 退出了《%s》%s %s 的车队。' % (name, ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        # 候补队列：一有空位，自动通知排在最前面的人
        wl = sorted([x for x in read_list('waitlist') if x.get('carId') == body.get('carId')],
                    key=lambda x: x.get('at') or 0)
        if wl:
            notify(wl[0].get('phone'), '车队有空位啦 🚗',
                   '《%s》%s %s 出现空位，快去上车！' % (ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        return {'ok': True, 'waitNotified': bool(wl)}, 200

    if action == 'wait':
        wl = read_list('waitlist')
        if any(x.get('carId') == body.get('carId') and str(x.get('phone')) == str(phone) for x in wl):
            return {'ok': True, 'already': True,
                    'position': len([x for x in wl if x.get('carId') == body.get('carId')])}, 200
        wl.append({'id': now_ms(), 'carId': body.get('carId'), 'phone': phone, 'username': name, 'at': now_ms()})
        write_json('waitlist', wl)
        return {'ok': True, 'position': len([x for x in wl if x.get('carId') == body.get('carId')])}, 200

    if action == 'msg':
        txt = clean_text(body.get('text'), 120)
        if not txt:
            return {'error': '内容不能为空'}, 400
        msgs = read_list('carmsgs')
        msgs.append({'id': now_ms(), 'carId': body.get('carId'), 'by': name, 'phone': phone,
                     'text': txt, 'at': now_ms()})
        write_json('carmsgs', msgs[-3000:])
        return {'ok': True}, 200

    if action == 'tags':
        if str(ob.get('phone')) != str(phone) and not user.get('_staff'):
            return {'error': '仅车主可设置车队标签'}, 403
        tags = [clean_text(t, 8) for t in (body.get('tags') or [])][:4] if isinstance(body.get('tags'), list) else []
        for b in bookings:
            if b.get('id') == ob.get('id'):
                b['carTags'] = tags
        write_json('bookings', bookings)
        return {'ok': True, 'tags': tags}, 200

    return {'error': '未知操作'}, 400


# ================================================================
# 6. 网页接口（前端页面就是通过 /api/... 跟这里对话的）
# ================================================================
# 哪些数据只有员工（管理员/DM）能读：里面含手机号等隐私
STAFF_ONLY_READ = {'users', 'bookings', 'pays', 'messages', 'favs', 'logs', 'badwords',
                   'dmleave', 'wants', 'waitlist', 'coupons', 'settles'}
# 哪些数据只有员工能整体覆盖写
STAFF_ONLY_WRITE = {'bookings', 'pays', 'logs', 'notices', 'sessions', 'rooms', 'scripts',
                    'settings', 'taglib', 'badwords', 'dmleave', 'coupons', 'wants', 'waitlist', 'settles'}
# 登录后就能写的（客户留言、评价、发帖、车队聊天、收藏、自己的账号资料）
LOGIN_WRITE = {'messages', 'reviews', 'posts', 'carmsgs', 'favs', 'users'}
# 账号表里"不许被前端随便改"的字段（防刷信用分 / 防自己给自己提权）
PROTECT_FIELDS = ('role', 'super', 'password', 'credit', 'creditLogs', 'banned', 'banReason',
                  'openid', 'first', 'invite', 'phone', 'username', 'email', 'oldPhone')

CAPTCHAS = {}       # 人机验证题：{id: {'a': 答案, 'exp': 过期时间}}
DEMO_CODE = '1234'  # 本地版通用验证码（方便你自己测试；线上版会真的发短信/邮件）


def gen_captcha():
    """出一道算术人机验证题（防机器人刷注册/发验证码）"""
    a, b = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
    cid = secrets.token_hex(8)
    CAPTCHAS[cid] = {'a': str(a + b), 'exp': now_ms() + 300000}
    return {'id': cid, 'q': '%d + %d = ?' % (a, b)}


def check_captcha(cid, ans):
    c = CAPTCHAS.pop(str(cid or ''), None)
    if not c or c['exp'] < now_ms():
        return False
    return str(ans or '').strip() == c['a']


def check_code(target, purpose, code):
    """校验验证码；本地版为了方便，直接输 1234 也算通过"""
    code = str(code or '').strip()
    if not code:
        return False
    if code == DEMO_CODE:
        return True
    codes = read_list('codes')
    for c in codes:
        if (str(c.get('target')) == str(target) and c.get('purpose') == purpose
                and str(c.get('code')) == code and not c.get('used') and (c.get('exp') or 0) > now_ms()):
            c['used'] = True
            write_json('codes', codes)
            return True
    return False


def role_of(u):
    if u.get('super') is True or u.get('role') == 'super':
        return 'super'
    return u.get('role') or 'user'


class Handler(BaseHTTPRequestHandler):
    server_version = 'TianshuLocal/1.0'

    # ---------- 基础收发 ----------
    def log_message(self, fmt, *args):
        pass                                     # 不刷屏（想看访问日志可把这两行删掉）

    def _send(self, body, status=200, ctype='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,x-app-key,x-auth')
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except Exception:
                pass

    def _json(self, obj, status=200):
        self._send(obj, status)

    def _body(self):
        try:
            n = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(n) if n else b''
            return json.loads(raw.decode('utf-8')) if raw else {}
        except Exception:
            return {}

    def _tok(self):
        return read_token(self.headers.get('x-auth'))

    def _staff(self):
        """是不是员工（管理员/超级管理员）"""
        t = self._tok()
        if t and t.get('role') in ('admin', 'super'):
            return True
        return bool(self.headers.get('x-app-key')) and self.headers.get('x-app-key') == server_secret()

    # ---------- 跨域预检 ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,PUT,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,x-app-key,x-auth')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    # ============ 读数据（浏览器打开页面时大量用它） ============
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, qs = u.path, urllib.parse.parse_qs(u.query)
        if not path.startswith('/api/'):
            return self._static(path)
        parts = [p for p in path[5:].split('/') if p]
        token, staff = self._tok(), self._staff()
        phone = str(token.get('phone')) if token else ''

        # 健康检查：浏览器和运维用它确认"服务活着"
        if parts[:1] == ['health']:
            return self._json({'ok': True, 'mode': 'local-python'})

        # 我是谁（刷新页面时靠它恢复登录态）
        if parts[:1] == ['verify']:
            if not token:
                return self._json({'ok': False, 'error': '令牌无效或已过期'}, 401)
            me = find_user(token.get('phone'))
            if not me:
                return self._json({'ok': False, 'error': '账号不存在'}, 404)
            if me.get('banned'):
                return self._json({'ok': False, 'error': '该账号已被限制使用：' + (me.get('banReason') or '')}, 403)
            return self._json({'ok': True, 'user': self_user(me)})

        # 人机验证题
        if parts[:1] == ['captcha']:
            return self._json(gen_captcha())

        # 读某个数据文件：/api/data/预约… 含隐私的只有员工能读
        if parts[:1] == ['data'] and len(parts) > 1:
            key = parts[1].replace('.json', '')
            if key in STAFF_ONLY_READ and not staff:
                return self._json({'error': '该数据仅员工可读'}, 403)
            val = read_json(key)
            if val is None:
                return self._json(None, 404)
            if key == 'users' and isinstance(val, list):
                val = [{k: v for k, v in x.items() if k != 'password'} for x in val]   # 密码永远不下发
            if key == 'notices' and isinstance(val, list) and not staff:
                val = [dict(x, to=None) for x in val
                       if not x.get('to') or phone in [str(p) for p in (x.get('to') or [])]]
            return self._json(val)

        # 我的数据（客户只能拿到自己的）
        if parts[:1] == ['my'] and len(parts) > 1:
            if not token:
                return self._json({'error': '请先登录'}, 401)
            kind = parts[1]
            if kind == 'bookings':
                return self._json(sorted([b for b in read_list('bookings') if str(b.get('phone')) == phone],
                                         key=lambda x: -(x.get('id') or 0)))
            if kind == 'orders':
                return self._json(sorted([o for o in read_list('pays') if str(o.get('phone')) == phone],
                                         key=lambda x: -(x.get('id') or 0)))
            if kind == 'messages':
                return self._json(sorted([m for m in read_list('messages') if str(m.get('phone')) == phone],
                                         key=lambda x: -(x.get('createdAt') or 0)))
            if kind == 'notices':
                out = [dict(n, to=None) for n in read_list('notices')
                       if not n.get('to') or phone in [str(p) for p in (n.get('to') or [])]]
                return self._json(out[:100])
            if kind == 'coupons':
                return self._json(sorted([c for c in read_list('coupons')
                                          if c.get('all') or str(c.get('phone')) == phone],
                                         key=lambda x: -(x.get('id') or 0)))
            if kind == 'favs':
                for rec in read_list('favs'):
                    if isinstance(rec, dict) and str(rec.get('phone')) == phone:
                        return self._json(rec.get('sids') or [])
                return self._json([])
            if kind == 'carmsgs':
                cid = (qs.get('carId') or [''])[0]
                msgs = [dict(m, phone=None) for m in read_list('carmsgs') if str(m.get('carId')) == str(cid)]
                return self._json(msgs[-60:])
            return self._json({'error': 'not found'}, 404)

        # 公开统计（评分/余位/车队/榜单，不含手机号）
        if parts[:2] == ['agg', 'summary']:
            return self._json(agg_summary(phone))

        # 公开名册（昵称/头像/性别/年龄段）
        if parts[:1] == ['roster']:
            if not token:
                return self._json({'error': '请先登录'}, 401)
            return self._json([public_user(x) for x in read_list('users') if not x.get('banned')])

        # 图片（上传后的图片就从这个地址读）
        if parts[:1] == ['img'] and len(parts) >= 3:
            rel = os.path.join('img', *parts[1:])
            full = os.path.normpath(os.path.join(DATA_DIR, rel))
            if not full.startswith(DATA_DIR) or not os.path.isfile(full):
                return self._send(b'not found', 404, 'text/plain')
            with open(full, 'rb') as f:
                ext = full.rsplit('.', 1)[-1].lower()
                ctype = {'png': 'image/png', 'gif': 'image/gif', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}.get(ext, 'image/webp')
                return self._send(f.read(), 200, ctype)

        return self._json({'error': 'not found'}, 404)

    # ============ 整份覆盖写数据（后台保存、同步用） ============
    def do_PUT(self):
        u = urllib.parse.urlparse(self.path)
        parts = [p for p in u.path[5:].split('/') if p] if u.path.startswith('/api/') else []
        if parts[:1] != ['data'] or len(parts) < 2:
            return self._json({'error': 'not found'}, 404)
        key = parts[1].replace('.json', '')
        token, staff = self._tok(), self._staff()
        payload = self._body()

        if key in STAFF_ONLY_WRITE and not staff:
            return self._json({'error': '该数据仅员工可写'}, 403)
        if key in LOGIN_WRITE and not token:
            return self._json({'error': '请先登录后再操作'}, 403)

        # 账号表的护栏：客户只能改自己，且受保护字段一律保持原值
        if key == 'users' and isinstance(payload, list):
            cloud = read_list('users')
            by_phone = {str(x.get('phone')): x for x in cloud}
            if not staff:
                mine = next((x for x in payload if str(x.get('phone')) == str(token.get('phone'))), None)
                if not mine:
                    return self._json({'error': '只能修改自己的账号信息'}, 403)
                out = []
                for o in cloud:
                    if str(o.get('phone')) != str(token.get('phone')):
                        out.append(o)
                    else:
                        m = dict(o)
                        m.update({k: v for k, v in mine.items() if k not in PROTECT_FIELDS})
                        out.append(m)
                payload = out
            else:
                out = []
                for x in payload:
                    o = by_phone.get(str(x.get('phone')))
                    if not o:
                        continue                             # 新增账号请走注册
                    m = dict(o)
                    m.update(x)
                    for f in PROTECT_FIELDS:                  # 受保护字段还原成云端原值
                        m[f] = o.get(f)
                    for f in ('role', 'super', 'credit', 'creditLogs', 'banned', 'banReason'):   # 员工可以改这些
                        if f in x:
                            m[f] = x[f]
                    m['password'] = x.get('password') or o.get('password')
                    out.append(m)
                payload = out
            # 防呆：不允许把账号表写空或砍掉一半（避免本地缓存异常把账号全清掉）
            junk = len([x for x in payload if not str(x.get('phone') or '')])
            if junk:
                return self._json({'error': '提交中有 %d 条缺少手机号的非法账号记录，已拒绝写入' % junk}, 400)
            if len(cloud) >= 2 and len(payload) < len(cloud) / 2:
                return self._json({'error': '本次提交会删除一半以上账号，为安全已拒绝'}, 409)

        # 日志署名由服务端决定，谁也没法冒充别人
        if key == 'logs' and isinstance(payload, list):
            me = find_user(token.get('phone')) if token else None
            who = (me or {}).get('username') or '本机'
            role = role_of(me) if me else 'user'
            payload = [dict(x, by=who, role=role, at=x.get('at') or now_ms()) for x in payload[:500]]

        write_json(key, payload)
        return self._json({'ok': True, 'key': key})

    # ============ 各种"动作"接口 ============
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        parts = [p for p in u.path[5:].split('/') if p] if u.path.startswith('/api/') else []
        if not parts:
            return self._json({'error': 'not found'}, 404)
        b = self._body()
        ip = self.client_address[0]
        token, staff = self._tok(), self._staff()
        user = find_user(token.get('phone')) if token else None
        head = parts[0]
        act = parts[1] if len(parts) > 1 else ''

        # ---------- 登录 ----------
        if head == 'login':
            ipk = 'loginf:ip:' + ip
            if rate_peek(ipk, 600000) >= 20:
                return self._json({'ok': False, 'error': '同一网络登录失败次数过多，请 10 分钟后再试'}, 429)
            acc, pw = str(b.get('account') or '').strip(), str(b.get('password') or '')
            if not acc or not pw:
                return self._json({'ok': False, 'error': '请填写账号与密码'}, 400)
            akk = 'loginf:acc:%s:%s' % (ip, acc.lower())
            if rate_peek(akk, 600000) >= 8:
                return self._json({'ok': False, 'error': '该账号密码错误次数过多，请 10 分钟后再试'}, 429)

            def fail():
                rate(ipk, 9999, 600000)
                rate(akk, 9999, 600000)

            users = read_list('users')
            me = next((x for x in users if str(x.get('phone')) == acc or str(x.get('username')) == acc), None)
            if not me:
                fail()
                return self._json({'ok': False, 'error': '账号不存在'}, 404)
            if me.get('banned'):
                return self._json({'ok': False, 'error': '该账号已被限制使用：' + (me.get('banReason') or '违反门店规则')}, 403)
            if not verify_password(pw, me.get('password')):
                fail()
                return self._json({'ok': False, 'error': '密码错误'}, 401)
            if not str(me.get('password') or '').startswith('pbkdf2$'):
                me['password'] = hash_password(pw)          # 老弱哈希自动升级
            me['last'] = now_ms()
            write_json('users', users)
            push_log(me.get('username'), role_of(me), '登录（本地版）')
            return self._json({'ok': True, 'token': make_token(me),
                               'user': {'phone': me.get('phone'), 'username': me.get('username'), 'role': role_of(me)}})

        # ---------- 发验证码 ----------
        if head == 'code' and act == 'send':
            if not rate('send:' + ip, 30, 600000):
                return self._json({'ok': False, 'error': '请求过于频繁，请稍后再试'}, 429)
            target = str(b.get('phone') or b.get('email') or '')
            if not target:
                return self._json({'ok': False, 'error': '请先填写手机号或邮箱'}, 400)
            need_cap = rate_peek('sendfast:' + ip, 3600000) > 6      # 发得越多越可能被要求人机验证
            rate('sendfast:' + ip, 9999, 3600000)
            if need_cap and not check_captcha(b.get('captchaId'), b.get('captchaAnswer')):
                return self._json({'ok': False, 'error': '需要人机验证', 'needCaptcha': True}, 400)
            code = '%06d' % secrets.randbelow(1000000)
            codes = [c for c in read_list('codes') if (c.get('exp') or 0) > now_ms()]
            codes.append({'id': now_ms(), 'target': target, 'purpose': str(b.get('purpose') or 'login'),
                          'code': code, 'exp': now_ms() + 300000, 'used': False})
            write_json('codes', codes[-300:])
            print('[验证码] 发给 %s 的验证码是 %s（本地版不真发短信，也可直接用 %s）' % (target, code, DEMO_CODE))
            return self._json({'ok': True, 'sent': True, 'channel': 'email' if b.get('email') else 'sms',
                               'devCode': code})

        # ---------- 注册 ----------
        if head == 'register':
            if not rate('reg:' + ip, 12, 3600000):
                return self._json({'ok': False, 'error': '注册过于频繁，请稍后再试'}, 429)
            phone_ = str(b.get('phone') or '').strip()
            email_ = str(b.get('email') or '').strip().lower()
            name_ = clean_text(b.get('username'), 20)
            pw_ = str(b.get('password') or '')
            if not re.match(r'^1\d{10}$', phone_):
                return self._json({'ok': False, 'error': '请输入 11 位手机号'}, 400)
            if len(pw_) < 6:
                return self._json({'ok': False, 'error': '密码至少 6 位'}, 400)
            if not name_:
                return self._json({'ok': False, 'error': '请填写昵称'}, 400)
            if not check_captcha(b.get('captchaId'), b.get('captchaAnswer')):
                return self._json({'ok': False, 'error': '人机验证失败，请重试', 'needCaptcha': True}, 400)
            if not check_code(phone_, 'register', b.get('code')):
                return self._json({'ok': False, 'error': '验证码不正确'}, 400)
            users = read_list('users')
            if any(str(x.get('phone')) == phone_ for x in users):
                return self._json({'ok': False, 'error': '该手机号已注册，请直接登录'}, 409)
            if any(x.get('username') == name_ for x in users):
                return self._json({'ok': False, 'error': '用户名已被占用，换一个吧'}, 409)
            invite = 'TS' + secrets.token_hex(3).upper()
            newbie = {'phone': phone_, 'username': name_, 'email': email_, 'role': 'user', 'super': False,
                      'password': hash_password(pw_), 'credit': 100, 'creditLogs': [],
                      'profile': {'avatar': '🎭', 'nick': name_, 'gender': '', 'age': None},
                      'first': now_ms(), 'last': now_ms(), 'invite': invite, 'banned': False}
            users.append(newbie)
            write_json('users', users)
            # 邀请返利：填了别人的邀请码 → 双方各得一张 10 元券
            inviter = next((x for x in users if x.get('invite') and x.get('invite') == str(b.get('invite') or '').strip()), None)
            if inviter:
                coupons = read_list('coupons')
                for who in (newbie, inviter):
                    coupons.append({'id': now_ms() + secrets.randbelow(999), 'phone': who.get('phone'),
                                    'amount': 10, 'minAmount': 0, 'kind': 'deposit',
                                    'exp': now_ms() + 90 * 86400000, 'used': False, 'from': '邀请返利'})
                write_json('coupons', coupons)
                notify(inviter.get('phone'), '邀请成功 🎁', '你邀请的 %s 已注册，赠送你一张 10 元券！' % name_, 'coupon')
            return self._json({'ok': True, 'token': make_token(newbie),
                               'user': {'phone': phone_, 'username': name_, 'role': 'user'}, 'invite': invite})

        # ---------- 下面这些都要先登录 ----------
        if head in ('booking', 'order', 'car', 'fav', 'msg', 'review', 'post', 'want', 'upload', 'account') and not token:
            return self._json({'error': '请先登录'}, 401)
        if user and user.get('banned'):
            return self._json({'error': '账号已被限制使用：' + (user.get('banReason') or '违反门店规则')}, 403)

        if head == 'booking' and act == 'create':
            if not rate('bk:' + ip, 60, 3600000):
                return self._json({'error': '操作过于频繁，请稍后再试'}, 429)
            res, code = create_booking(user, b)
            return self._json(res, code)

        if head == 'booking' and act == 'cancel':
            bookings = read_list('bookings')
            hit = next((x for x in bookings if str(x.get('id')) == str(b.get('id')) and str(x.get('phone')) == str(user.get('phone'))), None)
            if not hit:
                return self._json({'error': '预约不存在'}, 404)
            hit['status'], hit['cancelAt'], hit['cancelBy'] = 'cancelled', now_ms(), 'user'
            write_json('bookings', bookings)
            pays = read_list('pays')                     # 未支付的订单顺手关掉
            for o in pays:
                if o.get('bid') == hit.get('id') and o.get('status') == 'unpaid':
                    o['status'] = 'closed'
            write_json('pays', pays)
            return self._json({'ok': True})

        if head == 'order' and act == 'act':
            res, code = order_act(user, b, staff)
            return self._json(res, code)

        if head == 'car':
            user2 = dict(user, _staff=staff)
            res, code = car_action(user2, b, act)
            return self._json(res, code)

        # ---------- 收藏（想玩）----------
        if head == 'fav' and act == 'toggle':
            sid = str(b.get('sid'))
            favs = read_list('favs')
            rec = next((x for x in favs if isinstance(x, dict) and str(x.get('phone')) == str(user.get('phone'))), None)
            if not rec:
                rec = {'phone': user.get('phone'), 'sids': []}
                favs.append(rec)
            rec['sids'] = [str(s) for s in (rec.get('sids') or [])]
            if sid in rec['sids']:
                rec['sids'] = [s for s in rec['sids'] if s != sid]
            else:
                rec['sids'].append(sid)
            write_json('favs', favs)
            return self._json({'ok': True, 'favs': rec['sids']})

        # ---------- 给门店留言 ----------
        if head == 'msg' and act == 'create':
            text = clean_text(b.get('text'), 500)
            if not text:
                return self._json({'error': '内容不能为空'}, 400)
            msgs = read_list('messages')
            msgs.append({'id': now_ms(), 'phone': user.get('phone'), 'username': user.get('username'),
                         'cat': clean_text(b.get('cat'), 10) or '💡 建议', 'text': text, 'status': 'pending',
                         'reply': '', 'repliedBy': '', 'createdAt': now_ms()})
            write_json('messages', msgs)
            return self._json({'ok': True})

        # ---------- 写评价（可匿名）----------
        if head == 'review' and act == 'create':
            rv = read_list('reviews')
            rv.append({'id': now_ms(), 'sid': b.get('sid'), 'bid': b.get('bid'),
                       'rating': max(1, min(5, int(b.get('rating') or 5))),
                       'text': clean_text(b.get('text'), 800),
                       'dims': b.get('dims') if isinstance(b.get('dims'), dict) else {},
                       'reply': '', 'likes': [],
                       'username': '匿名玩家' if b.get('anonymous') else user.get('username'),
                       'anonymous': bool(b.get('anonymous')), 'createdAt': now_ms()})
            write_json('reviews', rv)
            return self._json({'ok': True})

        # ---------- 社区发帖 ----------
        if head == 'post' and act == 'create':
            posts = read_list('posts')
            posts.insert(0, {'id': now_ms(), 'type': str(b.get('type') or 'diary'),
                             'title': clean_text(b.get('title'), 60), 'text': clean_text(b.get('text'), 2000),
                             'imgs': (b.get('imgs') or [])[:9], 'username': user.get('username'),
                             'at': now_ms(), 'likes': [], 'phone': user.get('phone')})
            write_json('posts', posts[:2000])
            return self._json({'ok': True})

        # ---------- 帖子点赞 ----------
        if head == 'post' and act == 'like':
            posts = read_list('posts')
            for p in posts:
                if str(p.get('id')) == str(b.get('id')):
                    likes = [str(x) for x in (p.get('likes') or [])]
                    me_p = str(user.get('phone'))
                    if me_p in likes:
                        likes.remove(me_p)
                    else:
                        likes.append(me_p)
                    p['likes'] = likes
            write_json('posts', posts)
            return self._json({'ok': True})

        # ---------- 发布拼车需求 + 自动撮合 ----------
        if head == 'want' and act == 'create':
            wants = read_list('wants')
            me = {'id': now_ms(), 'phone': user.get('phone'), 'username': user.get('username'),
                  'sid': b.get('sid'), 'ts': b.get('ts'), 'time': str(b.get('time') or '19:00'),
                  'players': int(b.get('players') or 1), 'note': clean_text(b.get('note'), 100),
                  'status': 'open', 'at': now_ms()}
            # 找同剧本、同一天、同时段、别人发的需求 → 互相通知（这就是"智能撮合"）
            matched = [w for w in wants if w.get('status') == 'open' and str(w.get('sid')) == str(me['sid'])
                       and w.get('ts') == me['ts'] and w.get('time') == me['time']
                       and str(w.get('phone')) != str(me['phone'])]
            wants.append(me)
            write_json('wants', wants)
            for w in matched:
                notify(w.get('phone'), '找到同好 🎯',
                       '%s 也想玩这场的《%s》，%s %s，去拼车大厅组队吧' % (user.get('username'), b.get('sid'), day_label(me['ts']), me['time']), 'car')
            if matched:
                notify(user.get('phone'), '已匹配到 %d 位同好 🎯' % len(matched),
                       '、'.join(w.get('username') for w in matched) + ' 也想玩这场的同一时段', 'car')
            return self._json({'ok': True, 'matched': [{'username': w.get('username'), 'players': w.get('players')} for w in matched]})

        # ---------- 上传图片（存到 data/img/ 里，不再塞进网页）----------
        if head == 'upload':
            if not rate('up:' + ip, 40, 3600000):
                return self._json({'error': '上传过于频繁，请稍后再试'}, 429)
            m = re.match(r'^data:(image/(?:webp|jpeg|png|gif));base64,([A-Za-z0-9+/=]+)$', str(b.get('data') or ''))
            if not m:
                return self._json({'error': '只支持 webp / jpg / png / gif'}, 400)
            raw = base64.b64decode(m.group(2))
            if len(raw) > MAX_IMG_BYTES:
                return self._json({'error': '图片过大（请小于 700KB）'}, 400)
            ym = time.strftime('%Y%m')
            os.makedirs(os.path.join(IMG_DIR, ym), exist_ok=True)
            fname = '%s-%s.%s' % (ym, secrets.token_hex(6), m.group(1).split('/')[1])
            with open(os.path.join(IMG_DIR, ym, fname), 'wb') as f:
                f.write(raw)
            return self._json({'ok': True, 'url': '/api/img/%s/%s' % (ym, fname), 'size': len(raw)})

        # ---------- 账号安全：改密码 / 换手机号 / 注销 ----------
        if head == 'account' and act == 'pwd':
            pw_new = str(b.get('password') or '')
            if len(pw_new) < 6:
                return self._json({'error': '密码至少 6 位'}, 400)
            if not check_code(user.get('email') or user.get('phone'), 'reset', b.get('code')):
                return self._json({'error': '验证码不正确'}, 400)
            users = read_list('users')
            for x in users:
                if str(x.get('phone')) == str(user.get('phone')):
                    x['password'] = hash_password(pw_new)
            write_json('users', users)
            push_log(user.get('username'), role_of(user), '修改了密码')
            return self._json({'ok': True})

        if head == 'account' and act == 'phone':
            newp = str(b.get('newPhone') or '').strip()
            if not re.match(r'^1\d{10}$', newp):
                return self._json({'error': '请输入正确的手机号'}, 400)
            if any(str(x.get('phone')) == newp for x in read_list('users')):
                return self._json({'error': '该手机号已被其他账号使用'}, 409)
            if not check_code(newp, 'bind', b.get('code')):
                return self._json({'error': '验证码不正确'}, 400)
            old = str(user.get('phone'))
            users = read_list('users')
            for x in users:
                if str(x.get('phone')) == old:
                    x['oldPhone'] = old
                    x['phone'] = newp
            write_json('users', users)
            for key, field in (('bookings', 'phone'), ('pays', 'phone'), ('messages', 'phone'),
                               ('notices', 'to'), ('coupons', 'phone'), ('wants', 'phone')):
                rows = read_json(key)
                if isinstance(rows, list):
                    changed = False
                    for r in rows:
                        if isinstance(r, dict) and field in r:
                            if isinstance(r[field], list):
                                if old in [str(v) for v in r[field]]:
                                    r[field] = [newp if str(v) == old else v for v in r[field]]
                                    changed = True
                            elif str(r[field]) == old:
                                r[field] = newp
                                changed = True
                    if changed:
                        write_json(key, rows)
            push_log(user.get('username'), role_of(user), '换绑手机号 %s → %s' % (old, newp))
            return self._json({'ok': True, 'phone': newp})

        if head == 'account' and act == 'delete':
            if not check_code(user.get('email') or user.get('phone'), 'delete', b.get('code')):
                return self._json({'error': '验证码不正确'}, 400)
            me_p = str(user.get('phone'))
            write_json('users', [x for x in read_list('users') if str(x.get('phone')) != me_p])
            for key in ('bookings', 'pays', 'messages', 'coupons', 'wants'):
                write_json(key, [x for x in read_list(key) if str(x.get('phone')) != me_p])
            write_json('favs', [x for x in read_list('favs') if str(x.get('phone')) != me_p])
            push_log(user.get('username'), role_of(user), '注销了账号（数据已删除）')
            return self._json({'ok': True})

        # ---------- 追加合并（客户没权限整份覆盖，就用这个安全地加自己那条）----------
        if head == 'append' and act:
            key = act.replace('.json', '')
            if key in ('bookings', 'pays') and not staff:
                return self._json({'error': '该数据仅员工可写（客户请用预约接口）'}, 403)
            if key in STAFF_ONLY_WRITE and not staff:
                return self._json({'error': '需要管理员权限'}, 403)
            items = b.get('items') if isinstance(b.get('items'), list) else []
            kf = 'phone' if key == 'users' else 'id'
            cur = read_list(key)
            by_id = {str(x.get(kf)): x for x in cur}
            for it in items[:500]:
                if not isinstance(it, dict) or it.get(kf) is None:
                    continue
                o = by_id.get(str(it.get(kf)))
                if key == 'users':
                    if not o:
                        if not staff:
                            continue                     # 新增账号要走注册
                        by_id[str(it.get(kf))] = it
                    else:
                        if not staff and str(it.get(kf)) != str((token or {}).get('phone')):
                            continue                     # 客户只能改自己那条
                        m = dict(o)
                        m.update({k: v for k, v in it.items() if k not in PROTECT_FIELDS})
                        by_id[str(it.get(kf))] = m
                else:
                    by_id[str(it.get(kf))] = {**o, **it} if o else it
            write_json(key, list(by_id.values())[:5000])
            return self._json({'ok': True, 'merged': len(by_id)})

        # ---------- 删除记录 ----------
        if head == 'remove' and act:
            if not staff:
                return self._json({'error': '需要管理员权限'}, 403)
            key = act.replace('.json', '')
            ids = [str(x) for x in (b.get('ids') or [])]
            kf = 'phone' if key == 'users' else 'id'
            kept = [x for x in read_list(key) if str(x.get(kf)) not in ids]
            write_json(key, kept)
            return self._json({'ok': True, 'removed': len(ids)})

        return self._json({'error': 'not found'}, 404)

    # ============ 把 index.html 等静态文件发给浏览器 ============
    def _static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        rel = urllib.parse.unquote(path).lstrip('/')
        full = os.path.normpath(os.path.join(BASE_DIR, rel))
        if not full.startswith(BASE_DIR) or not os.path.isfile(full):      # 防越权读别的文件
            return self._send(b'404 Not Found', 404, 'text/plain; charset=utf-8')
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or full.endswith(('.js', '.json', '.webmanifest', '.svg')):
            ctype += '; charset=utf-8'
        with open(full, 'rb') as f:
            return self._send(f.read(), 200, ctype)


# ================================================================
# 7. 启动
# ================================================================
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    seed_if_empty()
    os.makedirs(IMG_DIR, exist_ok=True)
    print('=' * 60)
    print(' 甜薯剧本杀 · 本地 Python 版已启动')
    print(' 网页地址： http://localhost:%d' % PORT)
    print(' 数据目录： %s' % DATA_DIR)
    print(' 内置账号： FireFly（超管）/ FireFly2（管理员）/ dm测试（DM）/ 调试debug（客户）')
    print('           密码都是 123123')
    print(' 停止运行： 在这个窗口按 Ctrl + C')
    print('=' * 60)
    httpd = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)      # 只允许本机访问，更安全
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止。你的数据都在 data 文件夹里，不会丢。')


if __name__ == '__main__':
    main()
