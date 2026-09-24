# -*- coding: utf-8 -*-
"""
甜薯剧本杀 · 本地版（Flask）—— 2026.09 重新整理过一版

作者：甜薯（junbo）
线上跑的是 index.html + Cloudflare Functions 那一套；这里是把同样的逻辑
搬到 Python，数据落成 data/*.json，好处是想看什么直接拿记事本打开就行。

版本流水（给自己留的，别删）：
  · 最早那份是 http.server 手搓的，路由写成一条 if/elif 长龙，加到第十几个接口
    就改得手抖，所以 9 月下决心换成 Flask
  · 换框架时顺手修了个老毛病：订单改完没存回文件（Python 里取出来的列表要存回"同一份"，
    重新读一遍文件是拿不到你刚才改的）
  · 还加过微信登录、拼车候补、优惠券、核销码 —— 都在下面，按块分了
  · 待办：DM 分成比例想做成后台可配（现在还是结算时手填）；data 想加个自动备份

不写代码也能用的读法：
  · 调经营参数  → 搜「配置区」，改那几行；或者在网页后台点着改
  · 有哪些接口  → 启动后开 http://localhost:8000/api/help
  · 钱怎么算的  → 搜「老板最关心」，算价 / 定金 / 退款 / 扣信用分都在那一块
  · 出问题咋办  → 文件最后有「排查小抄」，我平时就照那个查

三句提醒：
  1) 本地版跟线上是两套数据，在这儿怎么试都不会影响店里在用的那个
  2) data/ 里有客人手机号，整个文件夹别往群里发（吃过一次亏）
  3) 依赖第一次运行会自动装；装不上一般是网络问题，重跑一次多半就好
"""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# ============================== 0. 依赖自检 ==============================
NEED = {'flask': 'Flask', 'rich': 'rich', 'waitress': 'waitress'}

# 依赖这块懒得手写，缺啥让它自己补上（第一次运行会等十几秒）
def _ensure_deps():
    """缺库就自动装（第一次运行需要，走的是国内镜像，很快）"""
    missing = []
    for mod, pkg in NEED.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print('首次运行需要安装运行库：%s，正在自动安装，请稍等…' % '、'.join(missing))
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q'] + missing)
        print('运行库安装完成 ✓')


_ensure_deps()

import waitress                                                              # noqa: E402
from flask import Flask, Response, g, jsonify, request, send_from_directory   # noqa: E402
from rich.console import Console                                              # noqa: E402
from rich.panel import Panel                                                  # noqa: E402
from rich.table import Table                                                  # noqa: E402
from werkzeug.exceptions import HTTPException                                 # noqa: E402

# 中文控制台（GBK）打不出表情符号，这里兜底成「?」，绝不让程序因此崩溃
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass

console = Console()

# ============================== 1. 可调设置 ==============================
PORT = 8000                      # 端口
OPEN_BROWSER = True              # 万恶的弹窗
LAN_MODE = False                 # 手机访问：平时用不上，要测手机再开
#   · False（默认）= 只有这台电脑自己能打开 http://localhost:8000（最安全 何意味）
#   · True         = 同一个 WiFi 下的手机也能打开，地址在启动窗口里会显示
#                    （家里/店里测试手机端很好用；测试完建议改回 False）
#   注意：localhost 永远只在"运行本程序的这台电脑"上有效，
#        手机上打开 localhost 会报「ERR_CONNECTION_REFUSED」，这是正常的。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMG_DIR = os.path.join(DATA_DIR, 'img')

TOKEN_DAYS = 7                   # 登录有效期（天）
MAX_IMG_BYTES = 700 * 1024       # 上传图片上限（700KB）
DEMO_CODE = '1234'               # 本地通用验证码（线上会真发短信/邮件）

# 经营参数默认值（首次运行写进 data/settings.json，之后以那个文件为准）
SETTINGS_DEFAULT = {
    "reviewsEnabled": True,      # 前台是否展示评分
    "dmRate": 0.10,              # DM 分成比例（TODO 还没接上去，现在是结算时手填的）
    "dmFee": 20,                 # 指定 DM 的加价（元/人）
    "depositRatio": 0.30,        # 定金比例（总价的 30%）
    "freeCancelHours": 24,       # 开场前 N 小时内取消算「临期」
    "lateCancelPenalty": 2,      # 临期取消扣的信用分
    "notice": "",                # 首页公告
    "carTags": ["不跳车", "准时到场", "新手友好", "硬核玩家"],
}

# 内置账号（用户名 / 手机号 / 角色 / 是否超管）
SEED_USERS = [
    ('FireFly', '13552158081', 'super', True),
    ('FireFly2', '18732303179', 'admin', False),
    ('dm测试', '12345678901', 'dm', False),
    ('调试debug', '13800000000', 'user', False),
]


# ==== 数据层：说白了就是 data/ 下的几个 json，没有数据库 ====
# 想手动改数据？找到对应文件，记事本打开改完保存即可（改前先 python app.py --backup）。
class Store:
    """读写 json 文件的小工具：先写临时文件再改名，断电也不会写坏数据"""

    _lock = threading.RLock()

    @staticmethod
    def path(key):
        return os.path.join(DATA_DIR, key + '.json')

    def read(self, key, default=None):
        p = self.path(key)
        if not os.path.exists(p):
            return default
        with self._lock:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                console.print('[red]读取 %s.json 失败：%s[/]' % (key, e))
                return default

    def write(self, key, obj):
        os.makedirs(DATA_DIR, exist_ok=True)
        p, tmp = self.path(key), self.path(key) + '.tmp'
        with self._lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(obj, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)

    def rows(self, key):
        """读数组型数据（账号、预约…），拿不到就当空数组"""
        v = self.read(key)
        return v if isinstance(v, list) else []

    def update(self, key, fn, limit=None):
        """改一份数组数据：读出 → fn 改 → 写回（一步到位，不用自己写样板代码）"""
        rows = self.rows(key)
        out = fn(rows) or rows
        self.write(key, out[:limit] if limit else out)
        return out


db = Store()

# 哪些数据只有员工能读（含手机号等隐私）
STAFF_ONLY_READ = {'users', 'bookings', 'pays', 'messages', 'favs', 'logs', 'badwords',
                   'dmleave', 'wants', 'waitlist', 'coupons', 'settles'}
# 哪些数据只有员工能整份覆盖写
STAFF_ONLY_WRITE = {'bookings', 'pays', 'logs', 'notices', 'sessions', 'rooms', 'scripts',
                    'settings', 'taglib', 'badwords', 'dmleave', 'coupons', 'wants', 'waitlist', 'settles'}
# 登录后就能写的数据（留言 / 评价 / 社区 / 车队聊天 / 收藏 / 自己的资料）
LOGIN_WRITE = {'messages', 'reviews', 'posts', 'carmsgs', 'favs', 'users'}
# 账号表里「前端不许随便改」的字段（防刷信用分、防自我提权）
PROTECT_FIELDS = ('role', 'super', 'password', 'credit', 'creditLogs', 'banned', 'banReason',
                  'openid', 'first', 'invite', 'phone', 'username', 'email', 'oldPhone')


# ---- 零碎工具：密码、令牌、限流、通知。这些别随手改，改错了全站登不上 ----
def now_ms():
    """当前时间（毫秒），和前端 JavaScript 的时间单位一致"""
    return int(time.time() * 1000)


def hash_password(pw):
    """密码加密存储（PBKDF2-SHA256 + 随机盐 + 10 万次迭代，和线上一致）"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), 100000)
    return 'pbkdf2$100000$%s$%s' % (salt, dk.hex())


def legacy_hash(p):
    """线上老账号用的弱哈希（仅为兼容，登录后会自动升级）"""
    h = 5381
    for ch in p:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return 'h' + format(h, 'x')


def verify_password(pw, stored):
    s = str(stored or '')
    if s.startswith('pbkdf2$'):
        try:
            _, iterations, salt, _ = s.split('$')
            dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), int(iterations))
            return hmac.compare_digest('pbkdf2$%s$%s$%s' % (iterations, salt, dk.hex()), s)
        except Exception:
            return False
    return legacy_hash(pw) == s


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')


def _b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


_SECRET = None


def server_secret():
    """本机签名密钥（data/secret.key，首次运行自动生成）
    用它给登录令牌签名 —— 这就是「别人无法伪造登录」的原理"""
    global _SECRET
    if _SECRET is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        f = os.path.join(DATA_DIR, 'secret.key')
        if not os.path.exists(f):
            with open(f, 'w', encoding='utf-8') as fp:
                fp.write(secrets.token_hex(32))
        with open(f, 'r', encoding='utf-8') as fp:
            _SECRET = fp.read().strip()
    return _SECRET


def make_token(user):
    """生成登录令牌：内容 + 签名。内容谁都能看，但没有密钥就改不了内容"""
    role = 'super' if (user.get('super') is True or user.get('role') == 'super') else (user.get('role') or 'user')
    payload = {'phone': user.get('phone', ''), 'username': user.get('username', ''),
               'role': role, 'exp': now_ms() + TOKEN_DAYS * 86400000}
    p = _b64e(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    sig = _b64e(hmac.new(server_secret().encode('utf-8'), p.encode('utf-8'), hashlib.sha256).digest())
    return p + '.' + sig


def read_token(tok):
    """校验令牌：签名不对或过期 → None（= 没登录）"""
    try:
        p, s = str(tok or '').split('.')
        calc = _b64e(hmac.new(server_secret().encode('utf-8'), p.encode('utf-8'), hashlib.sha256).digest())
        if not hmac.compare_digest(calc, s):
            return None
        obj = json.loads(_b64d(p).decode('utf-8'))
        return None if (not obj.get('exp') or obj['exp'] < now_ms()) else obj
    except Exception:
        return None


_RL = {}          # 限流记录


def rate(key, limit, window_ms):
    """限流：同一个 key 在 window_ms 内最多 limit 次（防暴力试密码 / 刷验证码）"""
    t = now_ms()
    arr = [x for x in _RL.get(key, []) if t - x < window_ms]
    if len(arr) >= limit:
        _RL[key] = arr
        return False
    arr.append(t)
    _RL[key] = arr
    return True


def rate_peek(key, window_ms):
    """只数次数不计数（用于「只统计失败次数」的登录限流）"""
    t = now_ms()
    arr = [x for x in _RL.get(key, []) if t - x < window_ms]
    _RL[key] = arr
    return len(arr)


def clean_text(t, max_len=500):
    """清洗用户输入：去控制字符 + 截断长度"""
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', '' if t is None else str(t))
    return s[:max_len]


def age_bucket(age):
    """年龄 → 年龄段（拼车时能看到「25-30岁」，但看不到具体年龄）"""
    try:
        n = int(age)
    except Exception:
        return ''
    for top, label in ((18, '18岁及以下'), (24, '18-24'), (30, '25-30'), (35, '31-35'), (45, '36-45')):
        if n <= top:
            return label
    return '45岁以上'


WEEK = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def day_label(ts):
    """时间戳 → 「9月24日 周四」"""
    d = time.localtime((ts or 0) / 1000)
    return '%d月%d日 %s' % (d.tm_mon, d.tm_mday, WEEK[d.tm_wday])


def get_settings():
    """经营参数（网页后台改的就是它）"""
    s = db.read('settings')
    out = dict(SETTINGS_DEFAULT)
    if isinstance(s, dict):
        out.update(s)
    return out


def role_of(u):
    if not u:
        return 'guest'
    if u.get('super') is True or u.get('role') == 'super':
        return 'super'
    return u.get('role') or 'user'


def find_user(phone):
    return next((u for u in db.rows('users') if str(u.get('phone')) == str(phone)), None)


def public_user(u):
    """对外展示的人：只有昵称/头像/性别/年龄段（保护隐私，无手机号）"""
    p = u.get('profile') or {}
    return {'username': u.get('username', ''), 'role': role_of(u),
            'profile': {'nick': p.get('nick', ''), 'avatar': p.get('avatar', '🎭'),
                        'gender': p.get('gender', ''), 'ageBucket': age_bucket(p.get('age'))}}


def self_user(u):
    """本人可见的完整档案（含信用分，但永远不含密码）"""
    out = {k: v for k, v in u.items() if k != 'password'}
    out.setdefault('credit', 100)
    out.setdefault('creditLogs', [])
    out.setdefault('profile', {'avatar': '🎭', 'nick': '', 'gender': '', 'age': None})
    out['role'] = role_of(u)
    return out


def notify(phone, title, text, kind='system'):
    """给某人发一条站内通知（会出现在他的消息中心）"""
    rows = db.rows('notices')
    rows.insert(0, {'id': now_ms() + secrets.randbelow(1000), 'title': title, 'text': text,
                    'at': now_ms(), 'to': [phone], 'by': '系统', 'readBy': [], 'kind': kind})
    db.write('notices', rows[:500])


def audit(who, role, text):
    """记一条操作日志（管理端「操作日志」能看到谁干了什么）"""
    rows = db.rows('logs')
    rows.insert(0, {'id': now_ms(), 'by': who or '本机', 'role': role or 'user', 'text': text, 'at': now_ms()})
    db.write('logs', rows[:500])


def seed_if_empty():
    """第一次运行：建好账号与默认设置"""
    os.makedirs(IMG_DIR, exist_ok=True)
    server_secret()
    if db.read('users') is None:
        t = now_ms()
        db.write('users', [{
            'phone': phone, 'username': name, 'email': '', 'role': role, 'super': is_super,
            'password': hash_password('123123'), 'credit': 100, 'creditLogs': [],
            'profile': {'avatar': '🎭', 'nick': name, 'gender': '', 'age': None},
            'first': t + i, 'last': t + i, 'invite': 'TS%04d' % (i + 1), 'banned': False, 'banReason': '',
        } for i, (name, phone, role, is_super) in enumerate(SEED_USERS)])
        console.print('[cyan]已创建 %d 个内置账号（密码都是 123123）[/]' % len(SEED_USERS))
    if db.read('settings') is None:
        db.write('settings', SETTINGS_DEFAULT)


# ============ ★ 老板最关心的一段：钱怎么算、分怎么扣 ============
# 规矩只有一条：所有判断都放服务端。前端（网页）传过来的数字一律不信——
# 之前有人按 F12 把 288 的本改成过 1 块钱，从那以后金额就只认这里算的。
# 放心改：这儿改坏了也只影响本地这份，店里的线上版本不动。

def player_range(script):
    """从「4-6人」里解析出最少/最多人数"""
    m = re.search(r'(\d+)\s*[-~到]\s*(\d+)', str(script.get('players') or ''))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d+)', str(script.get('players') or ''))
    return (int(m.group(1)), int(m.group(1))) if m else (1, 8)


def adjust_credit(phone, delta, reason, who):
    """改信用分（下单取消、DM 调整都走这里，保证一条流水都不漏）"""
    users = db.rows('users')
    me = next((u for u in users if str(u.get('phone')) == str(phone)), None)
    if not me:
        return None, None
    before = int(me.get('credit', 100))
    after = max(0, min(120, before + int(delta)))
    me['credit'] = after
    logs = me.get('creditLogs') or []
    logs.insert(0, {'id': now_ms(), 'delta': after - before, 'reason': reason or '门店调整',
                    'by': who or '系统', 'at': now_ms()})
    me['creditLogs'] = logs[:100]
    db.write('users', users)
    notify(phone, '信用分变动', '信用分 %d → %d 分。原因：%s' % (before, after, reason or '门店调整'), 'credit')
    return before, after


def car_pool(me_phone=''):
    """拼车大厅：车主 + 已上车的人（只含昵称/性别/年龄段，不含手机号）"""
    bookings = db.rows('bookings')
    users = {str(u.get('phone')): u for u in db.rows('users')}
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
            p = (users.get(str(b.get('phone')), {}).get('profile') or {})
            members.append({'username': b.get('username') or '玩家', 'gender': p.get('gender', ''),
                            'ageBucket': age_bucket(p.get('age')), 'players': b.get('players') or 1})
        out.append({'id': 'own-%s' % ob.get('id'), 'sid': ob.get('sid'), 'ts': ob.get('ts'),
                    'time': ob.get('time'), 'owner': ob.get('username') or '玩家',
                    'tags': ob.get('carTags') or [], 'joined': joined,
                    'cap': ob.get('carCap') or 8, 'min': ob.get('carMin') or 4,
                    'need': max(0, (ob.get('carMin') or 4) - joined), 'reserved': ob.get('reserved') or 0,
                    'members': members,
                    'mine': bool(me_phone and any(str(b.get('phone')) == str(me_phone) for b in [ob] + mates))})
    return sorted(out, key=lambda c: (c.get('ts') or 0, str(c.get('time'))))


def agg_summary(me_phone=''):
    """公开统计：评分 / 每场人数 / 拼车队列 / 人气榜 / 我的券（不含任何手机号）"""
    bookings, reviews = db.rows('bookings'), db.rows('reviews')
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
    script_stats = {k: {'plays': v['plays'], 'rating': round(v['sum'] / v['n'], 1) if v['n'] else 0,
                        'ratingCount': v['n']} for k, v in stats.items()}
    session_join = {}
    for b in bookings:
        if b.get('status') != 'cancelled' and b.get('sessionId'):
            k = str(b['sessionId'])
            session_join[k] = session_join.get(k, 0) + (b.get('players') or 1)
    hot = sorted([{'sid': k, 'plays': v['plays'], 'rating': v['rating']} for k, v in script_stats.items()],
                 key=lambda x: -x['plays'])[:10]
    my_coupons = [{'id': c.get('id'), 'amount': c.get('amount'), 'minAmount': c.get('minAmount'), 'exp': c.get('exp')}
                  for c in db.rows('coupons')
                  if not c.get('used') and (c.get('all') or str(c.get('phone')) == str(me_phone))
                  and (not c.get('exp') or c.get('exp') > now_ms())] if me_phone else []
    return {'scriptStats': script_stats, 'sessionJoin': session_join,
            'carPool': car_pool(me_phone), 'hotRank': hot, 'myCoupons': my_coupons}


def create_booking(user, body):
    """★【下单】创建预约 + 生成待付定金订单（返回 (结果, HTTP状态码)）

    为什么金额必须在这里算？
      如果交给浏览器算，别人按 F12 就能把 288 元改成 1 元。
      所以价格 / 定金 / 优惠券 / 余位 / 角色占用，全部在服务端算和校验。
    """
    st = get_settings()
    sc = next((s for s in db.rows('scripts') if str(s.get('id')) == str(body.get('sid'))), None)
    if not sc:
        return {'error': '剧本不存在（让管理员登录一次，剧本会自动同步到本地）'}, 404
    if sc.get('onSale') is False:
        return {'error': '该剧本已下架'}, 400
    ts, tm = int(body.get('ts') or 0), str(body.get('time') or '19:00')
    if not ts:
        return {'error': '请选择日期'}, 400
    lo, hi = player_range(sc)
    players = max(1, min(hi, int(body.get('players') or lo)))
    mode = '包车' if body.get('mode') == '包车' else '拼车'
    bookings = db.rows('bookings')

    # ① 店里这一天这一时段已排了场次 → 检查余位（防超卖）
    ses = next((x for x in db.rows('sessions') if str(x.get('sid')) == str(sc.get('id'))
                and x.get('ts') == ts and x.get('time') == tm and x.get('status') == 'open'), None)
    session_id = 0
    if ses:
        used = sum((b.get('players') or 1) for b in bookings
                   if b.get('sessionId') == ses.get('id') and b.get('status') != 'cancelled')
        left = (ses.get('cap') or 99) - used
        if left < players:
            return {'error': '该场次仅剩 %d 个位置，请调整人数或换个时段' % max(0, left)}, 409
        session_id = ses.get('id')

    # ② 线上选角：只有管理员给这个剧本开了「可提前选角」才允许，且同一角色只能一人选
    role = ''
    if sc.get('allowRolePick') is True:
        role = clean_text(body.get('role'), 20)
        if role:
            names = [r.get('name') for r in (sc.get('roles') or [])]
            if names and role not in names:
                return {'error': '角色不存在'}, 400
            if any(str(b.get('sid')) == str(sc.get('id')) and b.get('ts') == ts and b.get('time') == tm
                   and b.get('role') == role and b.get('status') != 'cancelled' for b in bookings):
                return {'error': '角色「%s」已被选走，换一个吧' % role}, 409

    # ③ 优惠券
    coupon = None
    if body.get('couponId'):
        coupon = next((c for c in db.rows('coupons')
                       if str(c.get('id')) == str(body.get('couponId')) and not c.get('used')
                       and (c.get('all') or str(c.get('phone')) == str(user.get('phone')))
                       and (not c.get('exp') or c.get('exp') > now_ms())), None)
        if not coupon:
            return {'error': '优惠券不可用'}, 400

    # ④ 算钱：单价 = 剧本价 +（指定 DM 的加价）；定金 = 总价 × 定金比例 − 券
    #    定金尾数四舍五入取整 —— 给客人报 229.6 这种数字，前台对账要骂人的
    price = float(sc.get('price') or 0) + (float(st['dmFee']) if body.get('dmPhone') else 0)
    amount = price * players
    deposit = round(amount * float(st['depositRatio']))
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
               'verifyCode': '%06d' % secrets.randbelow(1000000),      # 到店核销码
               'couponId': coupon.get('id') if coupon else 0, 'createdAt': now_ms()}
    order = {'id': now_ms() + 91, 'bid': bid, 'phone': user.get('phone'), 'username': user.get('username'),
             'title': sc.get('title'), 'day': booking['day'], 'ts': ts, 'time': tm, 'players': players,
             'price': price, 'amount': amount, 'deposit': deposit,
             'couponId': coupon.get('id') if coupon else 0, 'status': 'unpaid', 'channel': 'demo',
             'createdAt': now_ms(), 'paidAt': 0, 'refundAt': 0, 'tradeNo': ''}

    db.update('bookings', lambda rows: rows + [booking])
    db.update('pays', lambda rows: rows + [order])
    if coupon:                                   # 券用掉就标记一下，不能重复使用
        db.update('coupons', lambda rows: [dict(c, used=True, usedAt=now_ms(), usedBy=user.get('phone'))
                                           if str(c.get('id')) == str(coupon.get('id')) else c for c in rows])
    notify(user.get('phone'), '待支付定金',
           '《%s》%s %s 已锁定座位，请在 30 分钟内支付定金 ¥%s。' % (sc.get('title'), booking['day'], tm, deposit), 'pay')
    return {'ok': True, 'booking': booking, 'order': order}, 200


def order_action(user, body, is_staff):
    """★【订单】支付 / 退款（能不能退、退多少、扣不扣信用分，全在这里判断）"""
    st = get_settings()
    pays, bookings = db.rows('pays'), db.rows('bookings')      # 先取出来，改完再存回同一份
    order = next((o for o in pays if str(o.get('id')) == str(body.get('id'))), None)
    if not order:
        return {'error': '订单不存在'}, 404
    if str(order.get('phone')) != str(user.get('phone')) and not is_staff:
        return {'error': '无权操作该订单'}, 403
    booking = next((b for b in bookings if b.get('id') == order.get('bid')), None)
    action = str(body.get('action') or '')

    if action == 'pay':
        if order.get('status') != 'unpaid':
            return {'error': '该订单当前不可支付'}, 400
        order.update(status='paid', paidAt=now_ms(), tradeNo='DEMO%d' % now_ms())
        db.write('pays', pays)
        notify(order.get('phone'), '定金已支付 ✅',
               '《%s》定金 ¥%s 已确认，座位锁定，等你来玩～' % (order.get('title'), order.get('deposit')), 'pay')
        return {'ok': True, 'status': 'paid'}, 200

    if action == 'refund':
        if order.get('status') not in ('paid', 'unpaid'):
            return {'error': '该订单不可退款'}, 400
        hours = ((booking.get('ts') or 0) - now_ms()) / 3600000 if booking else 999
        free = hours >= float(st['freeCancelHours'])            # 距离 开场 还有多久 → 够不够免费取消
        if not free and not is_staff:
            return {'error': '距离开场不足 %s 小时，按门店规则定金不退。如需特殊处理请联系门店。'
                             % st['freeCancelHours'], 'needConfirm': True}, 200
        order.update(status='refunded' if free else 'closed', refundAt=now_ms(),
                     refundAmount=order.get('deposit') if free else 0)
        db.write('pays', pays)
        if booking:
            booking.update(status='cancelled', cancelAt=now_ms(), cancelBy='staff' if is_staff else 'user')
            db.write('bookings', bookings)
            if not free and not is_staff and int(st['lateCancelPenalty']) > 0:
                adjust_credit(order.get('phone'), -int(st['lateCancelPenalty']) * 10,
                              '临期取消（未达免费取消时限）', '系统')
        notify(order.get('phone'), '退款已处理' if free else '取消已登记',
               ('《%s》定金 ¥%s 已退回，预约已取消。' % (order.get('title'), order.get('deposit'))) if free
               else ('《%s》预约已取消（超出免费取消时限，定金不退）。' % order.get('title')), 'pay')
        return {'ok': True, 'refunded': free, 'amount': order.get('deposit') if free else 0}, 200

    return {'error': '未知操作'}, 400


def car_action(user, body, action):
    """★【拼车】上车 / 退出 / 候补 / 聊天 / 设置车队标签"""
    phone, name = user.get('phone'), user.get('username')
    owner_id = str(body.get('carId') or '').replace('own-', '')
    bookings = db.rows('bookings')
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
        db.write('bookings', bookings)
        notify(ob.get('phone'), '有人加入你的车队',
               '%s 加入了《%s》%s %s 的车队。' % (name, ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        if joined + 1 >= (ob.get('carMin') or 4):        # 够最低人数 → 通知所有人「成局」
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
                b.update(status='cancelled', cancelAt=now_ms())
        db.write('bookings', bookings)
        notify(ob.get('phone'), '有人退出车队',
               '%s 退出了《%s》%s %s 的车队。' % (name, ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        wl = sorted([x for x in db.rows('waitlist') if x.get('carId') == body.get('carId')],
                    key=lambda x: x.get('at') or 0)
        if wl:                                          # 有候补 → 自动通知排最前面的人
            notify(wl[0].get('phone'), '车队有空位啦 🚗',
                   '《%s》%s %s 出现空位，快去上车！' % (ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        return {'ok': True, 'waitNotified': bool(wl)}, 200

    if action == 'wait':
        wl = db.rows('waitlist')
        if any(x.get('carId') == body.get('carId') and str(x.get('phone')) == str(phone) for x in wl):
            return {'ok': True, 'already': True,
                    'position': len([x for x in wl if x.get('carId') == body.get('carId')])}, 200
        wl.append({'id': now_ms(), 'carId': body.get('carId'), 'phone': phone, 'username': name, 'at': now_ms()})
        db.write('waitlist', wl)
        return {'ok': True, 'position': len([x for x in wl if x.get('carId') == body.get('carId')])}, 200

    if action == 'msg':
        txt = clean_text(body.get('text'), 120)
        if not txt:
            return {'error': '内容不能为空'}, 400
        db.update('carmsgs', lambda rows: rows + [{'id': now_ms(), 'carId': body.get('carId'), 'by': name,
                                                   'phone': phone, 'text': txt, 'at': now_ms()}], 3000)
        return {'ok': True}, 200

    if action == 'tags':
        if str(ob.get('phone')) != str(phone) and not user.get('_staff'):
            return {'error': '仅车主可设置车队标签'}, 403
        tags = [clean_text(t, 8) for t in (body.get('tags') or [])][:4] if isinstance(body.get('tags'), list) else []
        ob['carTags'] = tags
        db.write('bookings', bookings)
        return {'ok': True, 'tags': tags}, 200

    return {'error': '未知操作'}, 400


# ---- 接口（读）：网页一打开就先调这一批 ----
# 附：最早那份是 http.server 手搓的，36 个接口全靠一条 if/elif 长龙判断，
#     加一个接口要改三个地方，改得手抖，9 月才换成现在这样（一个接口一个函数）。
#     老文件还在移动硬盘里，真要对照再翻 —— 别再改回去了。
app = Flask(__name__, static_folder=None)


def tok():
    """本次请求带的登录令牌（没有就是游客）"""
    if not hasattr(g, '_tok'):
        g._tok = read_token(request.headers.get('x-auth'))
        g._me = find_user(g._tok['phone']) if g._tok else None
    return g._tok


def me():
    """当前登录的账号（完整记录，含密码字段，别直接返回给前端）"""
    tok()
    return getattr(g, '_me', None)


def is_staff():
    """是不是员工（管理员 / 超管 / 管理密钥）"""
    t = tok()
    if t and t.get('role') in ('admin', 'super'):
        return True
    key = request.headers.get('x-app-key')
    return bool(key) and key == server_secret()


def body():
    """请求体（JSON）"""
    return request.get_json(silent=True) or {}


def fail(msg, code=400):
    return jsonify({'error': msg}), code


def send(res, code=200):
    """业务函数返回 (数据, 状态码) 时统一用它打包"""
    return (jsonify(res[0]), res[1]) if isinstance(res, tuple) else (jsonify(res), code)


@app.before_request
def _start_timer():
    g.t0 = time.time()


@app.errorhandler(Exception)
def _on_error(e):
    """兜底：任何没预料到的错误都打到控制台（方便你截图给我），
    并给前端一句能看懂的提示，而不是白屏"""
    if isinstance(e, HTTPException):
        return e
    console.print_exception()
    return jsonify(error='服务器内部错误：%s' % e), 500


@app.after_request
def _finish(resp):
    """统一加跨域头 + 在控制台打一行访问日志（方便观察谁在用、有没有报错）"""
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,x-app-key,x-auth'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,OPTIONS'
    path = request.path
    if path.startswith('/api') and path != '/api/health':        # 健康检查太频繁，不打日志
        ms = (time.time() - getattr(g, 't0', time.time())) * 1000
        color = 'green' if resp.status_code < 400 else ('yellow' if resp.status_code < 500 else 'red')
        who = (me() or {}).get('username') or ('员工' if is_staff() else '游客')
        if request.method != 'GET' or resp.status_code >= 400:
            console.print('[%s]%s[/] %-4s %-28s [dim]%5.0fms  %s[/]'
                          % (color, resp.status_code, request.method, path, ms, who))
    return resp


@app.route('/api/<path:_any>', methods=['OPTIONS'])
@app.route('/api', methods=['OPTIONS'])
def _options(_any=None):
    return ('', 204)


@app.get('/api/health')
def api_health():
    """健康检查：确认服务活着"""
    return jsonify(ok=True, mode='local-python', time=day_label(now_ms()))


@app.get('/api/verify')
def api_verify():
    """我是谁：刷新页面时用它恢复登录态"""
    t = tok()
    if not t:
        return jsonify(ok=False, error='令牌无效或已过期'), 401
    u = me()
    if not u:
        return jsonify(ok=False, error='账号不存在'), 404
    if u.get('banned'):
        return jsonify(ok=False, error='该账号已被限制使用：' + (u.get('banReason') or '')), 403
    return jsonify(ok=True, user=self_user(u))


CAPTCHAS = {}      # 人机验证题：{id: 答案}


@app.get('/api/captcha')
def api_captcha():
    """出一道算术人机验证题（防机器人刷注册）"""
    a, b = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
    cid = secrets.token_hex(8)
    CAPTCHAS[cid] = {'a': str(a + b), 'exp': now_ms() + 300000}
    return jsonify(id=cid, q='%d + %d = ?' % (a, b))


def check_captcha(cid, ans):
    c = CAPTCHAS.pop(str(cid or ''), None)
    return bool(c) and c['exp'] > now_ms() and str(ans or '').strip() == c['a']


def check_code(target, purpose, code):
    """校验验证码；本地版为了方便，直接输 1234 也算通过"""
    code = str(code or '').strip()
    if not code:
        return False
    if code == DEMO_CODE:
        return True
    rows = db.rows('codes')
    for c in rows:
        if (str(c.get('target')) == str(target) and c.get('purpose') == purpose and str(c.get('code')) == code
                and not c.get('used') and (c.get('exp') or 0) > now_ms()):
            c['used'] = True
            db.write('codes', rows)          # 用过的验证码不能再用
            return True
    return False


@app.get('/api/data/<key>')
def api_data_get(key):
    """读一整份数据（账号 / 预约 / 剧本 / 场次 …）；含隐私的只有员工能读"""
    key = key.replace('.json', '')
    if key in STAFF_ONLY_READ and not is_staff():
        return fail('该数据仅员工可读', 403)
    val = db.read(key)
    if val is None:
        return jsonify(None), 404
    if key == 'users' and isinstance(val, list):
        val = [{k: v for k, v in u.items() if k != 'password'} for u in val]      # 密码永不下发
    if key == 'notices' and isinstance(val, list) and not is_staff():
        phone = str((me() or {}).get('phone') or '')
        val = [dict(x, to=None) for x in val
               if not x.get('to') or phone in [str(p) for p in (x.get('to') or [])]]
    return jsonify(val)


@app.get('/api/my/<kind>')
def api_my(kind):
    """我的数据：预约 / 订单 / 留言 / 通知 / 券 / 收藏 / 车队聊天（只返回自己的）"""
    u = me()
    if not u:
        return fail('请先登录', 401)
    phone = str(u.get('phone'))
    if kind == 'bookings':
        return jsonify(sorted([b for b in db.rows('bookings') if str(b.get('phone')) == phone],
                              key=lambda x: -(x.get('id') or 0)))
    if kind == 'orders':
        return jsonify(sorted([o for o in db.rows('pays') if str(o.get('phone')) == phone],
                              key=lambda x: -(x.get('id') or 0)))
    if kind == 'messages':
        return jsonify(sorted([m for m in db.rows('messages') if str(m.get('phone')) == phone],
                              key=lambda x: -(x.get('createdAt') or 0)))
    if kind == 'notices':
        return jsonify([dict(n, to=None) for n in db.rows('notices')
                        if not n.get('to') or phone in [str(p) for p in (n.get('to') or [])]][:100])
    if kind == 'coupons':
        return jsonify(sorted([c for c in db.rows('coupons') if c.get('all') or str(c.get('phone')) == phone],
                              key=lambda x: -(x.get('id') or 0)))
    if kind == 'favs':
        rec = next((r for r in db.rows('favs') if isinstance(r, dict) and str(r.get('phone')) == phone), None)
        return jsonify((rec or {}).get('sids') or [])
    if kind == 'carmsgs':
        cid = str(request.args.get('carId') or '')
        msgs = [dict(m, phone=None) for m in db.rows('carmsgs') if str(m.get('carId')) == cid]
        return jsonify(msgs[-60:])
    return fail('not found', 404)


@app.get('/api/agg/summary')
def api_summary():
    """公开统计：评分 / 余位 / 拼车队列 / 人气榜（不含手机号）"""
    return jsonify(agg_summary(str((me() or {}).get('phone') or '')))


@app.get('/api/roster')
def api_roster():
    """公开名册：昵称 / 头像 / 性别 / 年龄段（供拼车显示）"""
    if not tok():
        return fail('请先登录', 401)
    return jsonify([public_user(u) for u in db.rows('users') if not u.get('banned')])


def dm_customers_of(phone):
    """DM 只看得到「自己场次里」的客户（最小权限原则）"""
    mine = [x.get('id') for x in db.rows('sessions') if str(x.get('dm')) == str(phone)]
    users = {str(u.get('phone')): u for u in db.rows('users')}
    out, seen = [], set()
    for b in db.rows('bookings'):
        if b.get('sessionId') in mine or str(b.get('dmPhone')) == str(phone):
            p = str(b.get('phone'))
            if p and p not in seen:
                seen.add(p)
                out.append({'phone': p, 'username': users.get(p, {}).get('username') or b.get('username'),
                            'credit': users.get(p, {}).get('credit', 100)})
    return out


@app.get('/api/dm/customers')
def api_dm_customers():
    """DM 端：我场次里的客户名单"""
    u = me()
    if not u:
        return fail('请先登录', 401)
    return jsonify(dm_customers_of(u.get('phone')))


@app.get('/api/dm/practices')
def api_dm_practices():
    """DM 端：我的练本申请"""
    u = me()
    if not u:
        return fail('请先登录', 401)
    return jsonify([x for x in db.rows('practices')
                    if str(x.get('phone')) == str(u.get('phone')) or is_staff()])


@app.get('/api/dm/profile')
def api_dm_profile():
    """DM 公开资料（段位 / 简介 / 可开本）"""
    u = find_user(request.args.get('phone') or '')
    if not u:
        return jsonify(ok=False, error='该 DM 不存在'), 404
    return jsonify(ok=True, username=u.get('username'),
                   profile=u.get('profile') or {}, dmProfile=u.get('dmProfile') or {})


@app.get('/api/img/<ym>/<name>')
def api_img(ym, name):
    """读取上传的图片"""
    if not re.match(r'^\d{6}$', ym) or not re.match(r'^[\w.-]+$', name):
        return fail('bad path', 400)
    return send_from_directory(os.path.join(IMG_DIR, ym), name)


# ---- 接口（登录注册）：令牌 = 身份证明，7 天过期，过期重新登 ----
@app.post('/api/login')
def api_login():
    """登录：返回令牌（令牌 = 身份证明，前端每次请求都带着它）"""
    ip = request.remote_addr or 'local'
    ip_fail = 'loginf:ip:' + ip
    if rate_peek(ip_fail, 600000) >= 20:
        return jsonify(ok=False, error='同一网络登录失败次数过多，请 10 分钟后再试'), 429
    acc, pw = str(body().get('account') or '').strip(), str(body().get('password') or '')
    if not acc or not pw:
        return jsonify(ok=False, error='请填写账号与密码'), 400
    acc_fail = 'loginf:acc:%s:%s' % (ip, acc.lower())
    if rate_peek(acc_fail, 600000) >= 8:
        return jsonify(ok=False, error='该账号密码错误次数过多，请 10 分钟后再试，或联系门店重置密码'), 429

    users = db.rows('users')
    u = next((x for x in users if str(x.get('phone')) == acc or str(x.get('username')) == acc), None)
    if not u:
        rate(ip_fail, 9999, 600000)
        rate(acc_fail, 9999, 600000)
        return jsonify(ok=False, error='账号不存在'), 404
    if u.get('banned'):
        return jsonify(ok=False, error='该账号已被限制使用：' + (u.get('banReason') or '违反门店规则')), 403
    if not verify_password(pw, u.get('password')):
        rate(ip_fail, 9999, 600000)
        rate(acc_fail, 9999, 600000)
        return jsonify(ok=False, error='密码错误'), 401
    if not str(u.get('password') or '').startswith('pbkdf2$'):
        u['password'] = hash_password(pw)          # 老弱哈希自动升级
    u['last'] = now_ms()
    db.write('users', users)
    audit(u.get('username'), role_of(u), '登录（本地版）')
    return jsonify(ok=True, token=make_token(u),
                   user={'phone': u.get('phone'), 'username': u.get('username'), 'role': role_of(u)})


@app.post('/api/code/send')
def api_code_send():
    """发验证码（本地版不真发短信，验证码会打印在这个窗口里，也可以用 1234）"""
    ip = request.remote_addr or 'local'
    if not rate('send:' + ip, 30, 600000):
        return jsonify(ok=False, error='请求过于频繁，请稍后再试'), 429
    b = body()
    target = str(b.get('phone') or b.get('email') or '')
    if not target:
        return jsonify(ok=False, error='请先填写手机号或邮箱'), 400
    need_cap = rate_peek('sendfast:' + ip, 3600000) > 6      # 发得越多越可能被要求人机验证
    rate('sendfast:' + ip, 9999, 3600000)
    if need_cap and not check_captcha(b.get('captchaId'), b.get('captchaAnswer')):
        return jsonify(ok=False, error='需要人机验证', needCaptcha=True), 400
    code = '%06d' % secrets.randbelow(1000000)
    codes = [c for c in db.rows('codes') if (c.get('exp') or 0) > now_ms()]      # 先清掉过期的
    codes.append({'id': now_ms(), 'target': target, 'purpose': str(b.get('purpose') or 'login'),
                  'code': code, 'exp': now_ms() + 300000, 'used': False})
    db.write('codes', codes[-300:])
    console.print('[yellow]验证码[/] 发给 [b]%s[/] 的是 [b]%s[/]（本地版不真发短信，也可直接用 %s）'
                  % (target, code, DEMO_CODE))
    return jsonify(ok=True, sent=True, channel='email' if b.get('email') else 'sms', devCode=code)


@app.post('/api/register')
def api_register():
    """注册（必须过人机验证；填了别人的邀请码，双方各得一张券）"""
    ip = request.remote_addr or 'local'
    if not rate('reg:' + ip, 12, 3600000):
        return jsonify(ok=False, error='注册过于频繁，请稍后再试'), 429
    b = body()
    phone = str(b.get('phone') or '').strip()
    name = clean_text(b.get('username'), 20)
    pw = str(b.get('password') or '')
    if not re.match(r'^1\d{10}$', phone):
        return jsonify(ok=False, error='请输入 11 位手机号'), 400
    if len(pw) < 6:
        return jsonify(ok=False, error='密码至少 6 位'), 400
    if not name:
        return jsonify(ok=False, error='请填写昵称'), 400
    if not check_captcha(b.get('captchaId'), b.get('captchaAnswer')):
        return jsonify(ok=False, error='人机验证失败，请重试', needCaptcha=True), 400
    if not check_code(phone, 'register', b.get('code')):
        return jsonify(ok=False, error='验证码不正确'), 400
    users = db.rows('users')
    if any(str(x.get('phone')) == phone for x in users):
        return jsonify(ok=False, error='该手机号已注册，请直接登录'), 409
    if any(x.get('username') == name for x in users):
        return jsonify(ok=False, error='用户名已被占用，换一个吧'), 409
    invite = 'TS' + secrets.token_hex(3).upper()
    newbie = {'phone': phone, 'username': name, 'email': str(b.get('email') or '').lower(),
              'role': 'user', 'super': False, 'password': hash_password(pw), 'credit': 100, 'creditLogs': [],
              'profile': {'avatar': '🎭', 'nick': name, 'gender': '', 'age': None},
              'first': now_ms(), 'last': now_ms(), 'invite': invite, 'banned': False, 'banReason': ''}
    users.append(newbie)
    db.write('users', users)
    inviter = next((x for x in users if x.get('invite') and x.get('invite') == str(b.get('invite') or '').strip()), None)
    if inviter:                                     # 邀请返利：双方各得一张券
        for who in (newbie, inviter):
            db.update('coupons', lambda rows: rows.append({
                'id': now_ms() + secrets.randbelow(999), 'phone': who.get('phone'), 'amount': 10,
                'minAmount': 0, 'kind': 'deposit', 'exp': now_ms() + 90 * 86400000,
                'used': False, 'from': '邀请返利'}) or rows)
        notify(inviter.get('phone'), '邀请成功 🎁', '你邀请的 %s 已注册，赠送你一张 10 元券！' % name, 'coupon')
    return jsonify(ok=True, token=make_token(newbie),
                   user={'phone': phone, 'username': name, 'role': 'user'}, invite=invite)


# ---- 接口（客户）：下单、付款、退款、拼车、留言、评价、收藏 ----
def need_login():
    """小助手：需要登录的接口开头调用它，返回响应就表示被拦住了"""
    u = me()
    if not u:
        return fail('请先登录', 401)
    if u.get('banned'):
        return fail('账号已被限制使用：' + (u.get('banReason') or '违反门店规则'), 403)
    return None


@app.post('/api/booking/create')
def api_booking_create():
    """客户下单。算价、余位、选角全在这儿把关（网页传过来什么都不信）"""
    r = need_login()
    if r:
        return r
    if not rate('bk:' + (request.remote_addr or 'local'), 60, 3600000):
        return fail('操作过于频繁，请稍后再试', 429)
    return send(create_booking(me(), body()))


@app.post('/api/booking/cancel')
def api_booking_cancel():
    """客户取消自己的预约（未支付的订单顺手关掉）"""
    r = need_login()
    if r:
        return r
    b = body()
    bookings = db.rows('bookings')
    hit = next((x for x in bookings if str(x.get('id')) == str(b.get('id'))
                and str(x.get('phone')) == str(me().get('phone'))), None)
    if not hit:
        return fail('预约不存在', 404)
    hit.update(status='cancelled', cancelAt=now_ms(), cancelBy='user')
    db.write('bookings', bookings)
    db.update('pays', lambda rows: [dict(o, status='closed') if (o.get('bid') == hit.get('id')
                                                                 and o.get('status') == 'unpaid') else o for o in rows])
    return jsonify(ok=True)


@app.post('/api/order/act')
def api_order_act():
    """订单支付 / 退款（规则全在服务端判断）"""
    r = need_login()
    if r:
        return r
    return send(order_action(me(), body(), is_staff()))


@app.post('/api/order/reschedule')
def api_order_reschedule():
    """客户改期（改到新时段，定金保留；新时段余位不足会被拦下）"""
    r = need_login()
    if r:
        return r
    b = body()
    bookings = db.rows('bookings')
    bk = next((x for x in bookings if str(x.get('id')) == str(b.get('id'))), None)
    if not bk:
        return fail('预约不存在', 404)
    if str(bk.get('phone')) != str(me().get('phone')) and not is_staff():
        return fail('只能改自己的预约', 403)
    new_ts, new_time = int(b.get('ts') or 0), str(b.get('time') or bk.get('time'))
    ses = next((x for x in db.rows('sessions') if str(x.get('sid')) == str(bk.get('sid'))
                and x.get('ts') == new_ts and x.get('time') == new_time and x.get('status') == 'open'), None)
    if ses:
        used = sum((x.get('players') or 1) for x in bookings if x.get('sessionId') == ses.get('id')
                   and x.get('status') != 'cancelled' and x.get('id') != bk.get('id'))
        if (ses.get('cap') or 99) - used < (bk.get('players') or 1):
            return fail('新时段余位不足，换个时间吧', 409)
        bk['sessionId'] = ses.get('id')
    bk.update(ts=new_ts, time=new_time, day=day_label(new_ts),
              rescheduleCount=(bk.get('rescheduleCount') or 0) + 1)
    db.write('bookings', bookings)
    db.update('pays', lambda rows: [dict(o, ts=new_ts, time=new_time, day=bk['day'])
                                    if o.get('bid') == bk.get('id') else o for o in rows])
    notify(bk.get('phone'), '改期成功 📅', '《%s》已改到 %s %s，定金保留。' % (bk.get('title'), bk['day'], new_time), 'booking')
    return jsonify(ok=True)


@app.post('/api/car/<action>')
def api_car(action):
    """拼车动作：join=上车 quit=退出 wait=候补 msg=聊天 tags=车队标签 reserved=预留位"""
    r = need_login()
    if r:
        return r
    u, b = me(), body()
    if action == 'reserved':
        bookings = db.rows('bookings')
        ob = next((x for x in bookings if str(x.get('id')) == str(b.get('carId') or '').replace('own-', '')), None)
        if not ob:
            return fail('车队不存在', 404)
        if str(ob.get('phone')) != str(u.get('phone')) and not is_staff():
            return fail('仅车主可设置预留位', 403)
        ob['reserved'] = max(0, min(3, int(b.get('n') or 0)))
        db.write('bookings', bookings)
        return jsonify(ok=True, reserved=ob['reserved'])
    return send(car_action(dict(u, _staff=is_staff()), b, action))


@app.post('/api/fav/toggle')
def api_fav_toggle():
    """收藏 / 取消收藏剧本"""
    r = need_login()
    if r:
        return r
    sid, phone = str(body().get('sid')), str(me().get('phone'))
    favs = db.rows('favs')
    rec = next((x for x in favs if isinstance(x, dict) and str(x.get('phone')) == phone), None)
    if not rec:
        rec = {'phone': phone, 'sids': []}
        favs.append(rec)
    rec['sids'] = [str(s) for s in (rec.get('sids') or [])]
    rec['sids'] = [s for s in rec['sids'] if s != sid] if sid in rec['sids'] else rec['sids'] + [sid]
    db.write('favs', favs)
    return jsonify(ok=True, favs=rec['sids'])


@app.post('/api/msg/create')
def api_msg_create():
    """给门店留言"""
    r = need_login()
    if r:
        return r
    b, u = body(), me()
    text = clean_text(b.get('text'), 500)
    if not text:
        return fail('内容不能为空', 400)
    db.update('messages', lambda rows: rows + [{
        'id': now_ms(), 'phone': u.get('phone'), 'username': u.get('username'),
        'cat': clean_text(b.get('cat'), 10) or '💡 建议', 'text': text,
        'status': 'pending', 'reply': '', 'repliedBy': '', 'createdAt': now_ms()}])
    return jsonify(ok=True)


@app.post('/api/review/create')
def api_review_create():
    """写评价（可匿名）"""
    r = need_login()
    if r:
        return r
    b, u = body(), me()
    db.update('reviews', lambda rows: rows + [{
        'id': now_ms(), 'sid': b.get('sid'), 'bid': b.get('bid'),
        'rating': max(1, min(5, int(b.get('rating') or 5))), 'text': clean_text(b.get('text'), 800),
        'dims': b.get('dims') if isinstance(b.get('dims'), dict) else {}, 'reply': '', 'likes': [],
        'username': '匿名玩家' if b.get('anonymous') else u.get('username'),
        'anonymous': bool(b.get('anonymous')), 'createdAt': now_ms()}])
    return jsonify(ok=True)


@app.post('/api/post/create')
def api_post_create():
    """社区发帖"""
    r = need_login()
    if r:
        return r
    b, u = body(), me()
    db.update('posts', lambda rows: [{'id': now_ms(), 'type': str(b.get('type') or 'diary'),
                                      'title': clean_text(b.get('title'), 60),
                                      'text': clean_text(b.get('text'), 2000),
                                      'imgs': (b.get('imgs') or [])[:9], 'username': u.get('username'),
                                      'at': now_ms(), 'likes': [], 'phone': u.get('phone')}] + rows, 2000)
    return jsonify(ok=True)


@app.post('/api/post/like')
def api_post_like():
    """帖子点赞 / 取消点赞"""
    r = need_login()
    if r:
        return r
    pid, phone = str(body().get('id')), str(me().get('phone'))

    def toggle(rows):
        for p in rows:
            if str(p.get('id')) == pid:
                likes = [str(x) for x in (p.get('likes') or [])]
                p['likes'] = [x for x in likes if x != phone] if phone in likes else likes + [phone]
        return rows

    db.update('posts', toggle)
    return jsonify(ok=True)


@app.post('/api/want/create')
def api_want_create():
    """发布拼车需求（系统自动撮合同剧本、同时段的其他玩家并互相通知）"""
    r = need_login()
    if r:
        return r
    b, u = body(), me()
    wants = db.rows('wants')
    mine = {'id': now_ms(), 'phone': u.get('phone'), 'username': u.get('username'),
            'sid': b.get('sid'), 'ts': b.get('ts'), 'time': str(b.get('time') or '19:00'),
            'players': int(b.get('players') or 1), 'note': clean_text(b.get('note'), 100),
            'status': 'open', 'at': now_ms()}
    matched = [w for w in wants if w.get('status') == 'open' and str(w.get('sid')) == str(mine['sid'])
               and w.get('ts') == mine['ts'] and w.get('time') == mine['time']
               and str(w.get('phone')) != str(mine['phone'])]
    wants.append(mine)
    db.write('wants', wants)
    for w in matched:
        notify(w.get('phone'), '找到同好 🎯',
               '%s 也想玩《%s》%s %s，去拼车大厅组队吧' % (u.get('username'), b.get('sid'),
                                                       day_label(mine['ts']), mine['time']), 'car')
    if matched:
        notify(u.get('phone'), '已匹配到 %d 位同好 🎯' % len(matched),
               '、'.join(w.get('username') for w in matched) + ' 也想玩这场的同一时段', 'car')
    return jsonify(ok=True, matched=[{'username': w.get('username'), 'players': w.get('players')} for w in matched])


@app.post('/api/want/form')
def api_want_form():
    """店家撮合成团：把几条拼车需求合成一辆车（生成预约与订单并通知大家）"""
    if not is_staff():
        return fail('需要员工权限', 403)
    ids = [str(x) for x in (body().get('ids') or [])]
    wants = db.rows('wants')
    picked = [x for x in wants if str(x.get('id')) in ids and x.get('status') == 'open']
    if not picked:
        return fail('没有可撮合的需求', 404)
    first = picked[0]
    for i, w in enumerate(picked):
        bid = now_ms() + secrets.randbelow(900) + i
        db.update('bookings', lambda rows: rows + [{
            'id': bid, 'phone': w.get('phone'), 'username': w.get('username'), 'sid': w.get('sid'),
            'title': '', 'day': day_label(w.get('ts')), 'ts': w.get('ts'), 'time': w.get('time'),
            'players': w.get('players') or 1, 'price': 0, 'status': 'booked', 'mode': '拼车',
            'carNew': i == 0, 'carOwner': first.get('username'), 'carCap': 8, 'carMin': 4,
            'carTags': [], 'reserved': 0, 'sessionId': 0, 'dmPhone': '', 'role': '',
            'verifyCode': '%06d' % secrets.randbelow(1000000), 'createdAt': now_ms()}])
        db.update('pays', lambda rows: rows + [{
            'id': bid + 1, 'bid': bid, 'phone': w.get('phone'), 'username': w.get('username'),
            'title': w.get('title') or '', 'day': day_label(w.get('ts')), 'ts': w.get('ts'),
            'time': w.get('time'), 'players': w.get('players') or 1, 'price': 0, 'amount': 0,
            'deposit': 0, 'couponId': 0, 'status': 'unpaid', 'channel': 'demo', 'createdAt': now_ms()}])
        notify(w.get('phone'), '门店帮你撮合成团了 🤝',
               '同一场次的玩家已凑齐，%s %s 一起去玩吧！' % (day_label(w.get('ts')), w.get('time')), 'car')
    db.update('wants', lambda rows: [dict(w, status='formed') if str(w.get('id')) in ids else w for w in rows])
    return jsonify(ok=True, created=len(picked))


@app.post('/api/upload')
def api_upload():
    """上传图片（存到 data/img，返回可直接访问的网址；只收 webp/jpg/png/gif）"""
    r = need_login()
    if r:
        return r
    if not rate('up:' + (request.remote_addr or 'local'), 40, 3600000):
        return fail('上传过于频繁，请稍后再试', 429)
    m = re.match(r'^data:(image/(?:webp|jpeg|png|gif));base64,([A-Za-z0-9+/=]+)$', str(body().get('data') or ''))
    if not m:
        return fail('只支持 webp / jpg / png / gif', 400)
    raw = base64.b64decode(m.group(2))
    if len(raw) > MAX_IMG_BYTES:
        return fail('图片过大（请小于 700KB）', 400)
    ym = time.strftime('%Y%m')
    os.makedirs(os.path.join(IMG_DIR, ym), exist_ok=True)
    fname = '%s-%s.%s' % (ym, secrets.token_hex(6), m.group(1).split('/')[1])
    with open(os.path.join(IMG_DIR, ym, fname), 'wb') as f:
        f.write(raw)
    return jsonify(ok=True, url='/api/img/%s/%s' % (ym, fname), size=len(raw))


@app.post('/api/account/<action>')
def api_account(action):
    """账号安全：pwd=改密码 phone=换绑手机号 delete=注销账号（数据一并删除）"""
    r = need_login()
    if r:
        return r
    u, b = me(), body()
    phone = str(u.get('phone'))

    if action == 'pwd':
        pw = str(b.get('password') or '')
        if len(pw) < 6:
            return fail('密码至少 6 位', 400)
        if not check_code(u.get('email') or phone, 'reset', b.get('code')):
            return fail('验证码不正确', 400)
        db.update('users', lambda rows: [dict(x, password=hash_password(pw)) if str(x.get('phone')) == phone else x
                                         for x in rows])
        audit(u.get('username'), role_of(u), '修改了密码')
        return jsonify(ok=True)

    if action == 'phone':
        newp = str(b.get('newPhone') or '').strip()
        if not re.match(r'^1\d{10}$', newp):
            return fail('请输入正确的手机号', 400)
        if any(str(x.get('phone')) == newp for x in db.rows('users')):
            return fail('该手机号已被其他账号使用', 409)
        if not check_code(newp, 'bind', b.get('code')):
            return fail('验证码不正确', 400)
        db.update('users', lambda rows: [dict(x, phone=newp, oldPhone=phone) if str(x.get('phone')) == phone else x
                                         for x in rows])
        for key, field in (('bookings', 'phone'), ('pays', 'phone'), ('messages', 'phone'),
                           ('coupons', 'phone'), ('wants', 'phone'), ('notices', 'to')):
            rows = db.rows(key)
            changed = False
            for x in rows:                        # 把这个账号名下的数据一起迁到新手机号
                if field not in x:
                    continue
                if isinstance(x[field], list):
                    if phone in [str(v) for v in x[field]]:
                        x[field] = [newp if str(v) == phone else v for v in x[field]]
                        changed = True
                elif str(x[field]) == phone:
                    x[field] = newp
                    changed = True
            if changed:
                db.write(key, rows)
        audit(u.get('username'), role_of(u), '换绑手机号 %s → %s' % (phone, newp))
        return jsonify(ok=True, phone=newp)

    if action == 'delete':
        if not check_code(u.get('email') or phone, 'delete', b.get('code')):
            return fail('验证码不正确', 400)
        db.write('users', [x for x in db.rows('users') if str(x.get('phone')) != phone])
        for key in ('bookings', 'pays', 'messages', 'coupons', 'wants', 'favs'):
            db.write(key, [x for x in db.rows(key) if str(x.get('phone')) != phone])
        audit(u.get('username'), role_of(u), '注销了账号（数据已删除）')
        return jsonify(ok=True)

    return fail('未知操作', 404)


# ---- 接口（后台）：核销、充值、发券、拉黑、场次、结算 ----
@app.post('/api/staff/<action>')
def api_staff(action):
    """后台的几个动作：核销 / 拉黑 / 充值 / 发券 / 清空数据 / 场次变更 / 结算标记
    （都是店里天天要点的，加新功能照抄一段，注意别把权限判断删了）"""
    if not is_staff():
        return fail('需要员工权限', 403)
    u, b = me(), body()
    who, my_role = (u or {}).get('username'), role_of(u)

    if action == 'verify':                      # 到店核销：客户出示 6 位码
        code = str(b.get('code') or '').strip()
        bookings = db.rows('bookings')
        hit = next((x for x in bookings if str(x.get('verifyCode')) == code and x.get('status') == 'booked'), None)
        if not hit:
            return fail('核销码无效，或该预约已核销/已取消', 404)
        hit.update(status='arrived', arrivedAt=now_ms(), verifiedBy=who or '员工')
        db.write('bookings', bookings)
        notify(hit.get('phone'), '已到店核销 ✅',
               '《%s》%s %s 已核销，祝你玩得开心～' % (hit.get('title'), hit.get('day'), hit.get('time')), 'verify')
        audit(who, my_role, '核销《%s》（码 %s）' % (hit.get('title'), code))
        return jsonify(ok=True, booking=hit)

    if action == 'ban':                          # 拉黑 / 恢复账号
        target = next((x for x in db.rows('users') if str(x.get('phone')) == str(b.get('phone'))), None)
        if not target:
            return fail('账号不存在', 404)
        if target.get('super') is True:
            return fail('超级管理员不可限制', 403)
        banned = not target.get('banned')
        db.update('users', lambda rows: [dict(x, banned=banned,
                                              banReason=clean_text(b.get('reason'), 60) if banned else '')
                                         if str(x.get('phone')) == str(b.get('phone')) else x for x in rows])
        audit(who, my_role, ('拉黑' if banned else '恢复') + '账号 ' + str(target.get('username')))
        return jsonify(ok=True, banned=banned)

    if action == 'customer':                     # 查看客户档案（留痕）
        audit(who, my_role, '查看客户档案 ' + str(b.get('phone')))
        return jsonify(ok=True)

    if action == 'recharge':                     # 会员充值
        target = next((x for x in db.rows('users') if str(x.get('phone')) == str(b.get('phone'))), None)
        if not target:
            return fail('该手机号还没有注册账号', 404)
        amount = int(b.get('amount') or 0)
        before = int(target.get('balance') or 0)
        db.update('users', lambda rows: [dict(x, balance=before + amount, walletLogs=(
            [{'id': now_ms(), 'delta': amount, 'note': clean_text(b.get('note'), 40),
              'by': who, 'at': now_ms()}] + (x.get('walletLogs') or []))[:100])
            if str(x.get('phone')) == str(b.get('phone')) else x for x in rows])
        notify(target.get('phone'), '会员余额变动 💳', '充值 ¥%d，当前余额 ¥%d。' % (amount, before + amount), 'wallet')
        return jsonify(ok=True, before=before, after=before + amount)

    if action == 'coupon':                       # 发券（沉睡客户回访 / 全员）
        users, bookings = db.rows('users'), db.rows('bookings')
        scope = str(b.get('all') or 'sleeping')
        amount = int(b.get('amount') or 0) or 20
        days, sleep_days = int(b.get('days') or 30), int(b.get('sleepDays') or 30)
        cut = now_ms() - sleep_days * 86400000
        picked = []
        for c in [x for x in users if role_of(x) == 'user']:
            if scope == 'all':
                picked.append(c)
                continue
            last = max([bk.get('createdAt') or 0 for bk in bookings
                        if str(bk.get('phone')) == str(c.get('phone'))] or [c.get('first') or 0])
            if last < cut:                       # 超过 N 天没来 = 沉睡客户
                picked.append(c)
        for c in picked:
            db.update('coupons', lambda rows: rows + [{
                'id': now_ms() + secrets.randbelow(999), 'phone': c.get('phone'), 'amount': amount,
                'minAmount': int(b.get('minAmount') or 0), 'kind': 'deposit',
                'exp': now_ms() + days * 86400000, 'used': False, 'from': '门店回访'}])
            notify(c.get('phone'), '送你一张优惠券 🎁',
                   '好久不见～送你一张 %d 元定金抵扣券（%d 天内有效），快来开本吧！' % (amount, days), 'coupon')
        return jsonify(ok=True, count=len(picked), msg='' if picked else '没有符合条件的客户')

    if action == 'purge':                        # 清空业务数据（保留账号与剧本）
        if my_role != 'super':
            return fail('仅超级管理员可清空数据', 403)
        for key in ('bookings', 'pays', 'messages', 'reviews', 'posts', 'notices',
                    'carmsgs', 'logs', 'wants', 'waitlist', 'codes'):
            db.write(key, [])
        audit(who, 'super', '清空了全部业务数据')
        return jsonify(ok=True)

    if action == 'session':                      # 场次取消 / 锁定 → 通知已报名客户
        sessions = db.rows('sessions')
        s = next((x for x in sessions if str(x.get('id')) == str(b.get('id'))), None)
        if not s:
            return fail('场次不存在', 404)
        s['status'] = str(b.get('status') or 'open')
        if b.get('reason'):
            s['statusReason'] = clean_text(b.get('reason'), 60)
        db.write('sessions', sessions)
        if s['status'] == 'cancelled':
            for bk in db.rows('bookings'):
                if bk.get('sessionId') == s.get('id') and bk.get('status') == 'booked':
                    notify(bk.get('phone'), '场次变动通知',
                           '《%s》%s %s 的场次已被取消（%s），请联系门店改约。'
                           % (s.get('title'), day_label(s.get('ts')), s.get('time'), s.get('statusReason') or ''), 'session')
        return jsonify(ok=True)

    if action == 'settle':                       # DM 结算标记
        settle_id, dm_phone, month = b.get('id'), b.get('dmPhone'), b.get('month')

        def mark(rows):
            for x in rows:
                if (settle_id and str(x.get('id')) == str(settle_id)) or \
                   (dm_phone and str(x.get('dmPhone')) == str(dm_phone) and (not month or x.get('month') == month)):
                    x.update(settled=True, settledAt=now_ms(), settledBy=who)
            return rows

        db.update('settles', mark)
        return jsonify(ok=True)

    return fail('未知操作', 404)


@app.post('/api/dm/<action>')
def api_dm(action):
    """DM 端：credit=调整信用分 assign=分配角色"""
    my_role = role_of(me())
    if not (is_staff() or my_role == 'dm'):
        return fail('需要 DM 权限', 403)
    u, b = me(), body()

    if action == 'credit':                       # 调信用分（会通知客户）
        before, after = adjust_credit(b.get('phone'), max(-100, min(100, int(b.get('delta') or 0))),
                                      clean_text(b.get('reason'), 40) or '门店调整', u.get('username'))
        if before is None:
            return fail('客户不存在', 404)
        return jsonify(ok=True, before=before, after=after)

    if action == 'assign':                       # 开本前分配角色
        bookings = db.rows('bookings')
        bk = next((x for x in bookings if str(x.get('id')) == str(b.get('id'))), None)
        if not bk:
            return fail('预约不存在', 404)
        bk['role'] = clean_text(b.get('role'), 20)
        db.write('bookings', bookings)
        notify(bk.get('phone'), '你的角色已分配 🎭', '《%s》%s %s 你的角色是：%s'
               % (bk.get('title'), bk.get('day'), bk.get('time'), bk['role'] or '现场分配'), 'role')
        return jsonify(ok=True)

    return fail('未知操作', 404)


@app.post('/api/practice/<action>')
def api_practice(action):
    """练本申请：create=DM提交 update=门店处理并通知 DM"""
    r = need_login()
    if r:
        return r
    b, u = body(), me()
    if action == 'create':
        db.update('practices', lambda rows: [{'id': now_ms(), 'phone': u.get('phone'), 'username': u.get('username'),
                                              'sid': b.get('sid'), 'ts': b.get('ts') or 0,
                                              'note': clean_text(b.get('note'), 200),
                                              'status': 'pending', 'at': now_ms()}] + rows, 500)
        return jsonify(ok=True)
    if action == 'update':
        if not is_staff():
            return fail('需要员工权限', 403)
        db.update('practices', lambda rows: [dict(x, status=str(b.get('status') or 'planned'))
                                             if str(x.get('id')) == str(b.get('id')) else x for x in rows])
        for x in db.rows('practices'):
            if str(x.get('id')) == str(b.get('id')) and x.get('phone'):
                notify(x.get('phone'), '练本申请已处理', '你的练本申请状态：%s' % x.get('status'), 'guide')
        return jsonify(ok=True)
    return fail('未知操作', 404)


@app.post('/api/guide/<action>')
def api_guide(action):
    """学本资料库：save=新增/修改 del=删除（管理员上传，DM 端可见）"""
    if not is_staff():
        return fail('需要员工权限', 403)
    b, u = body(), me()
    if action == 'del':
        db.write('guides', [x for x in db.rows('guides') if str(x.get('id')) != str(b.get('id'))])
        return jsonify(ok=True)
    gid = int(b.get('id') or 0)
    data = {'sid': b.get('sid') or 0, 'type': str(b.get('type') or '解析'),
            'title': clean_text(b.get('title'), 60), 'text': clean_text(b.get('text'), 5000),
            'links': (b.get('links') or [])[:8], 'by': u.get('username'), 'at': now_ms()}
    rows = db.rows('guides')
    hit = next((x for x in rows if x.get('id') == gid), None)
    if hit:
        hit.update(data)
    else:
        rows.insert(0, dict(data, id=now_ms(), super=bool(b.get('super'))))
    db.write('guides', rows[:500])
    return jsonify(ok=True)


@app.post('/api/notice/read')
def api_notice_read():
    """把通知标记为已读（ids 为空 = 全部）"""
    r = need_login()
    if r:
        return r
    ids = [str(x) for x in (body().get('ids') or [])]
    phone = str(me().get('phone'))

    def mark(rows):
        for x in rows:
            if not ids or str(x.get('id')) in ids:
                rb = x.get('readBy') or []
                if phone not in rb:
                    x['readBy'] = rb + [phone]
        return rows

    db.update('notices', mark)
    return jsonify(ok=True)


# ---- 网页 & 整份读写 & 启动 ----
@app.put('/api/data/<key>')
def api_data_put(key):
    """整份覆盖写数据（后台保存 / 多端同步用）；账号表有多重护栏，防止误清空"""
    key = key.replace('.json', '')
    if key in STAFF_ONLY_WRITE and not is_staff():
        return fail('该数据仅员工可写', 403)
    if key in LOGIN_WRITE and not tok():
        return fail('请先登录后再操作', 403)
    payload = request.get_json(silent=True)

    if key == 'users' and isinstance(payload, list):
        cloud = db.rows('users')
        by_phone = {str(x.get('phone')): x for x in cloud}
        if not is_staff():
            phone = str((tok() or {}).get('phone'))
            mine = next((x for x in payload if str(x.get('phone')) == phone), None)
            if not mine:
                return fail('只能修改自己的账号信息', 403)
            out = []
            for o in cloud:                       # 别人的记录原样保留，只能改自己那条
                m = dict(o)
                if str(o.get('phone')) == phone:
                    m.update({k: v for k, v in mine.items() if k not in PROTECT_FIELDS})
                out.append(m)
            payload = out
        else:
            out = []
            for x in payload:
                o = by_phone.get(str(x.get('phone')))
                if not o:
                    continue                                   # 新增账号请走注册
                m = dict(o)
                m.update(x)
                for f in PROTECT_FIELDS:                       # 受保护字段还原
                    m[f] = o.get(f)
                for f in ('role', 'super', 'credit', 'creditLogs', 'banned', 'banReason'):
                    if f in x:                                 # 员工可以改这些
                        m[f] = x[f]
                m['password'] = x.get('password') or o.get('password')
                out.append(m)
            payload = out
        # 三道护栏都是被坑过才加的：① 混进没手机号的记录 ② 一次砍掉一半账号 ③ 非员工改别人
        # TODO 并发还是"读-改-写"，两个人同时保存理论上会丢一条；店里这点量先这么放着
        if any(not str(x.get('phone') or '') for x in payload):    # 没有手机号的非法记录
            return fail('提交中含缺少手机号的非法账号记录，已拒绝写入，请刷新页面后重试', 400)
        if len(cloud) >= 2 and len(payload) < len(cloud) / 2:      # 一次删一半以上账号
            return fail('本次提交会删除一半以上账号，为安全已拒绝', 409)

    if key == 'sessions' and isinstance(payload, list):            # 房间冲突校验（防撞房）
        used = {}
        for s in payload:
            if not isinstance(s, dict) or s.get('status') == 'cancelled' or not s.get('roomId'):
                continue
            k = '%s|%s|%s' % (s.get('roomId'), s.get('ts'), s.get('time'))
            if k in used:
                return fail('房间冲突：该房间 %s %s 已排了《%s》'
                            % (day_label(s.get('ts')), s.get('time'), used[k]), 409)
            used[k] = s.get('title')

    if key == 'logs' and isinstance(payload, list):                # 日志署名由服务端决定
        u = me()
        payload = [dict(x, by=(u or {}).get('username') or '本机', role=role_of(u), at=x.get('at') or now_ms())
                   for x in payload[:500]]

    db.write(key, payload)
    return jsonify(ok=True, key=key)


@app.post('/api/append/<key>')
def api_append(key):
    """追加合并：客户没权限整份覆盖，就用它安全地提交自己那一条"""
    key = key.replace('.json', '')
    if key in ('bookings', 'pays') and not is_staff():
        return fail('该数据仅员工可写（客户请用预约接口）', 403)
    if key in STAFF_ONLY_WRITE and not is_staff():
        return fail('需要管理员权限', 403)
    if not is_staff() and not tok():
        return fail('请先登录后再操作', 403)
    items = body().get('items') if isinstance(body().get('items'), list) else []
    kf = 'phone' if key == 'users' else 'id'
    rows = db.rows(key)
    by_id = {str(x.get(kf)): x for x in rows}
    for it in items[:500]:
        if not isinstance(it, dict) or it.get(kf) is None:
            continue
        old = by_id.get(str(it.get(kf)))
        if key == 'users':
            if not old:
                if is_staff():
                    by_id[str(it.get(kf))] = it
                continue                                       # 客户不能新增账号，请走注册
            if not is_staff() and str(it.get(kf)) != str((tok() or {}).get('phone')):
                continue                                       # 客户只能改自己那条
            m = dict(old)
            m.update({k: v for k, v in it.items() if k not in PROTECT_FIELDS})
            by_id[str(it.get(kf))] = m
        else:
            by_id[str(it.get(kf))] = {**(old or {}), **it}
    db.write(key, list(by_id.values())[:5000])
    return jsonify(ok=True, merged=len(by_id))


@app.post('/api/remove/<key>')
def api_remove(key):
    """删除记录（仅员工）"""
    if not is_staff():
        return fail('需要管理员权限', 403)
    key = key.replace('.json', '')
    ids = [str(x) for x in (body().get('ids') or [])]
    kf = 'phone' if key == 'users' else 'id'
    db.write(key, [x for x in db.rows(key) if str(x.get(kf)) not in ids])
    return jsonify(ok=True, removed=len(ids))


@app.get('/api/help')
def api_help():
    """就是本页。接口清单是从代码里自动扒出来的，改完刷新一下就有"""
    rows = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        if not str(rule).startswith('/api') or str(rule) == '/api/help':
            continue
        fn = app.view_functions[rule.endpoint]
        doc = (fn.__doc__ or '').strip().splitlines()
        if not doc or str(rule).startswith('/api/<path:'):
            continue
        methods = '、'.join(sorted(m for m in rule.methods if m not in ('HEAD', 'OPTIONS')))
        rows.append((methods, str(rule), doc[0]))
    html = ['<meta charset="utf-8"><title>甜薯本地版 · 接口一览</title>',
            '<style>body{font:15px/1.7 -apple-system,"Microsoft YaHei";padding:28px;background:#0e0c1a;color:#e8e6f5}',
            'h1{font-size:20px}td{padding:7px 12px;border-bottom:1px solid #2a2545}',
            'th{text-align:left;padding:8px 12px;color:#a99fd0}m{color:#fdba74}',
            'table{border-collapse:collapse;width:100%;max-width:1000px}</style>',
            '<h1>甜薯剧本杀 · 本地版接口一览</h1>',
            '<p>共 %d 个接口。这份清单是程序自动生成的，改代码后刷新本页即可更新。</p>' % len(rows),
            '<table><tr><th>方法</th><th>地址</th><th>说明</th></tr>']
    html += ['<tr><td><m>%s</m></td><td>%s</td><td>%s</td></tr>' % r for r in rows]
    return Response(''.join(html) + '</table>', mimetype='text/html; charset=utf-8')


@app.get('/')
def index():
    """打开网站首页"""
    return send_from_directory(BASE_DIR, 'index.html')


@app.get('/<path:filename>')
def static_files(filename):
    """网站用到的其它文件（sw.js / icon.svg / manifest 等）"""
    full = os.path.normpath(os.path.join(BASE_DIR, filename))
    if not full.startswith(BASE_DIR) or not os.path.isfile(full):
        return fail('404 Not Found', 404)
    ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
    with open(full, 'rb') as f:
        return Response(f.read(), mimetype=ctype)


def lan_ip():
    """找出这台电脑在 WiFi 里的地址（手机要用它来访问你电脑）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))         # 不会真的发数据，只是让系统选出正在用的网卡
        return s.getsockname()[0]
    except Exception:
        return ''
    finally:
        s.close()


def pick_port(host, start):
    """端口被占用就自动往后找（8000→8009），并告诉用户原因"""
    for p in range(start, start + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # ⚠️ Windows 上不要加 SO_REUSEADDR：它会让"已被占用的端口"也能绑定成功，
                #    结果误判为端口空闲。直接 bind，占用时会抛错，这才是可靠的判断。
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start


def banner(port, lan=''):
    """启动横幅：把该知道的信息一次说清"""
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style='bold cyan', justify='right')
    t.add_column()
    t.add_row('电脑上打开', '[b]http://localhost:%d[/]' % port)
    if lan:
        t.add_row('手机上打开', '[b]http://%s:%d[/] [dim]（手机连同一个 WiFi）[/]' % (lan, port))
    else:
        t.add_row('手机也能看', '[dim]把文件第 1 节的 LAN_MODE 改成 True 再重启[/]')
    t.add_row('接口一览', '[b]http://localhost:%d/api/help[/]' % port)
    t.add_row('数据目录', DATA_DIR)
    t.add_row('内置账号', 'FireFly（超管）/ FireFly2（管理员）/ dm测试（DM）/ 调试debug（客户）')
    t.add_row('密码', '123123')
    t.add_row('停止', '按 Ctrl + C')
    console.print(Panel(t, title='甜薯剧本杀 · 本地版已启动', border_style='magenta'))
    console.print('[dim]这个窗口要一直开着，网页才能用；关掉窗口 = 关闭本地网站。[/]')


def pause_before_exit():
    """双击运行时万一出错，别让黑窗口一闪而过，留着让你看清报错"""
    try:
        if sys.stdin and sys.stdin.isatty():
            input('\n按回车键关闭这个窗口…')
    except Exception:
        pass


def show_stats():
    """--stats：随手写的小工具。看一眼库里有多少东西、账号都是谁（排查问题先跑它）"""
    def n(key):
        v = db.read(key)
        return len(v) if isinstance(v, list) else (1 if isinstance(v, dict) else 0)

    print('数据目录：%s' % DATA_DIR)
    for label, key in (('账号', 'users'), ('剧本', 'scripts'), ('预约', 'bookings'), ('订单', 'pays'),
                       ('场次', 'sessions'), ('评价', 'reviews'), ('留言', 'messages'),
                       ('通知', 'notices'), ('优惠券', 'coupons'), ('操作日志', 'logs')):
        print('  %-8s %s' % (label, n(key)))
    users = db.rows('users')
    if users:
        print('账号明细：')
        for u in users:
            print('  %-12s %-13s %-6s 信用 %s' % (u.get('username'), u.get('phone'),
                                               role_of(u), u.get('credit', 100)))


def do_backup():
    """--backup：把 data 整个打包成 zip 放在本目录（手改数据之前先跑一次，能救命）"""
    import shutil
    if not os.path.isdir(DATA_DIR):          # 还没启动过、没有 data 文件夹的情况
        print('还没有 data 文件夹（没启动过服务？），没什么可备份的')
        return
    name = os.path.join(BASE_DIR, '备份-%s' % time.strftime('%Y%m%d-%H%M'))
    shutil.make_archive(name, 'zip', DATA_DIR)
    print('已备份：%s.zip' % name)


def main():
    """启动服务
    平时双击 bat 就够了；自己敲命令时常用这几个：
        python app.py --stats        看数据统计（不改任何东西）
        python app.py --backup       把 data 打包备份
        python app.py --lan          让手机也能访问（同一个 WiFi）
        python app.py --port 8080    换端口
        python app.py --no-browser   不自动开浏览器"""
    global OPEN_BROWSER, LAN_MODE, PORT
    if '--stats' in sys.argv:
        show_stats()
        return
    if '--backup' in sys.argv:
        do_backup()
        return
    if '--no-browser' in sys.argv:
        OPEN_BROWSER = False
    if '--lan' in sys.argv:
        LAN_MODE = True
    if '--port' in sys.argv:
        try:
            PORT = int(sys.argv[sys.argv.index('--port') + 1])
        except Exception:
            pass
    seed_if_empty()
    host = '0.0.0.0' if LAN_MODE else '127.0.0.1'
    port = pick_port(host, PORT)
    if port != PORT:
        console.print('[yellow]提示：端口 %d 被占用了（可能已经开着一个服务窗口），本次改用 %d[/]' % (PORT, port))
    lan = lan_ip() if LAN_MODE else ''
    if LAN_MODE and not lan:
        console.print('[yellow]提示：没检测到 WiFi 地址，手机可能连不上，请确认电脑已联网[/]')
    banner(port, lan)
    if OPEN_BROWSER:
        threading.Timer(1.2, lambda: webbrowser.open('http://localhost:%d' % port)).start()
    try:
        from waitress import create_server
        server = create_server(app, host=host, port=port, threads=8)   # 先把端口占住，有问题会立刻报错
        server.run()
    except KeyboardInterrupt:
        console.print('\n[yellow]已停止[/]，数据都在 data 文件夹里，不会丢。')
    except Exception as e:
        console.print('[red]启动失败：%s[/]' % e)
        console.print('常见原因：① 端口被占用（把之前的黑窗口关掉再试）'
                      ' ② 杀毒软件/防火墙拦截 ③ data 文件夹没有写入权限')
        pause_before_exit()


# ============ 排查小抄（我平时出问题就照这个查，双击黑窗口一闪也看这里）============
# 打不开网页 ERR_CONNECTION_REFUSED → 黑窗口没开或被你关了，先启动再看
# 黑窗口闪一下就消失               → 去文件夹里直接双击 bat，看它停在哪儿报错
# 登录一直说密码错                 → python app.py --stats 看账号在不在；密码让超管重置
# 手机打不开                       → LAN_MODE 改 True 重启；确认手机和电脑同一个 WiFi
# 想手改 data 又怕改坏             → 先 python app.py --backup，再动 json
# 突然一堆 403                     → 令牌过期了（7 天），退出重新登录就行
# 提示端口被占用                   → 上次的窗口没关干净；不想找就随它，会自动用 8001

# —— 甜薯 · 2026.09 打烊之后写的
if __name__ == '__main__':
    try:
        main()
    except Exception as e:                          # 兜底：任何启动错误都留在窗口里
        console.print('[red]启动出错：%s[/]' % e)
        console.print_exception()
        pause_before_exit()
