# -*- coding: utf-8 -*-
"""
★ 业务规则：钱怎么算、分怎么扣、车队怎么拼 —— 全店最要紧的一段

一条铁律：所有判断都在服务端。表单里传过来的数字只当"意向"，
最后算出来多少以这里为准（以前有人改前端把 288 的本订成 1 块钱）。
"""
import hashlib
import os
import re
import secrets
import threading
import time

from tianshu.db import db
from tianshu.security import hash_password, verify_password
from config import DEMO_CODE, IMG_DIR, MAX_IMG_BYTES, PLAYER_TAGS, WEEK
from tianshu._ttlcache import get_or_set, invalidate

# ---------------------------------------------------------------- 小工具
def now_ms():
    return int(time.time() * 1000)


def day_label(ts):
    """时间戳 → 「9月25日 周五」"""
    d = time.localtime((ts or 0) / 1000)
    return '%d月%d日 %s' % (d.tm_mon, d.tm_mday, WEEK[d.tm_wday])


def age_bucket(age):
    """年龄只对外露"年龄段"，拼车时够用，又不泄露具体岁数"""
    try:
        n = int(age)
    except Exception:
        return ''
    for top, label in ((18, '18岁及以下'), (24, '18-24'), (30, '25-30'), (35, '31-35'), (45, '36-45')):
        if n <= top:
            return label
    return '45岁以上'


def player_range(script):
    """「4-6人」→ (4, 6)"""
    m = re.search(r'(\d+)\s*[-~到]\s*(\d+)', str(script.get('players') or ''))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d+)', str(script.get('players') or ''))
    return (int(m.group(1)), int(m.group(1))) if m else (1, 8)


# get_settings() 的合并结果缓存：[settings.json 的 mtime, 合并后的 dict]
# 每请求会被 context_processor / script_detail / car_deposit / mail_* / current_skin…调十几次，
# 每次 dict(SETTINGS_DEFAULT)+update 是纯重复劳动。settings.json 几乎不变，按 mtime 命中即可。
_settings_cache = [None, None]


def get_settings():
    from config import SETTINGS_DEFAULT
    p = db.path('settings')
    try:
        mt = os.path.getmtime(p)
    except OSError:
        mt = None
    if _settings_cache[0] == mt and _settings_cache[1] is not None:
        return _settings_cache[1]
    s = db.read('settings')
    out = dict(SETTINGS_DEFAULT)
    if isinstance(s, dict):
        out.update(s)
    _settings_cache[0] = mt
    _settings_cache[1] = out
    return out


def clean(t, max_len=200):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(t or ''))[:max_len]


# ---------------------------------------------------------------- 角色（可以同时有多个）
# 一个人可以**同时**是 DM + 管理员（店主自己带本很常见），所以角色存成一个列表：
#     user['roles'] = ['user', 'dm', 'admin']
# 老数据只有单值 user['role']（'user'/'dm'/'admin'）、超管另有一个 user['super']=True ——
# roles_of() 两边都认，**不用写迁移脚本**；保存时两个字段一起写（role = 最高的那个，日志还在读它）。
ROLE_NAMES = {'user': '普通用户', 'dm': 'DM', 'admin': '管理员', 'super': '超级管理员'}
ROLE_RANK = {'user': 0, 'dm': 1, 'admin': 2, 'super': 3}
ROLE_PICK = ('user', 'dm', 'admin')          # 后台能勾的三个（super 不给勾，它是初始账号的标记）


def roles_of(u):
    """这个人拥有哪些角色（列表，按级别从低到高）。

    **普通用户是人人都有、去不掉的**（客人、DM、管理员一样都能下单、评价、攒券），
    所以返回里永远带 'user' —— 后台不用让人去勾它，勾的只是"额外的身份"。

    · 超管（初始那个账号）：['super']
    · 老数据只有单值 role → 包成只有一个元素的列表
    """
    if not u:
        return []
    if u.get('super') is True or u.get('role') == 'super':
        return ['super']
    rs = u.get('roles')
    if isinstance(rs, (list, tuple)) and rs:
        out = {str(r) for r in rs if str(r) in ROLE_PICK}
    else:
        r = str(u.get('role') or 'user')
        out = {r if r in ROLE_PICK else 'user'}
    out.add('user')                       # 人人都是普通用户：显式带上，少了它说明数据不对
    return sorted(out, key=lambda r: ROLE_RANK.get(r, 0))


def extra_roles(u):
    """"额外身份"：普通用户之外的那些（DM / 管理员）—— 卡片徽章只显示这些，才够短"""
    return [r for r in roles_of(u) if r != 'user']


def roles_badge(u_or_roles):
    """小徽章的文字：有额外身份就写它们（"DM、管理员"），一个都没有才写"普通用户" """
    rs = u_or_roles if isinstance(u_or_roles, (list, tuple, set)) else roles_of(u_or_roles)
    names = [ROLE_NAMES.get(r, r) for r in sorted(rs, key=lambda r: ROLE_RANK.get(r, 0)) if r != 'user']
    return '、'.join(names) or '普通用户'


def has_role(u, *want):
    """有没有其中任意一个角色 —— **判权限统一用它**，别再写 role_of(u) == 'dm' 那种。

    超管算管理员：'super' 的账号 has_role(u, 'admin') 为真
    （不然初始那个账号反而进不去后台）。
    """
    rs = set(roles_of(u))
    if rs & set(want):
        return True
    return 'super' in rs and 'admin' in want


def role_of(u):
    """**主角色**（最高的那个）—— 只用来显示和写日志；判权限请用 has_role()。

    名字没改是因为调用它的地方太多（日志、通知、资料页…），换语义比换名字划算。
    """
    if not u:
        return 'guest'
    rs = roles_of(u)
    for r in ('super', 'admin', 'dm', 'user'):
        if r in rs:
            return r
    return 'user'


def roles_text(u_or_roles):
    """角色列表 → 中文串（例："普通用户、DM、管理员"），通知/日志里用"""
    rs = u_or_roles if isinstance(u_or_roles, (list, tuple, set)) else roles_of(u_or_roles)
    return '、'.join(ROLE_NAMES.get(r, r) for r in sorted(rs, key=lambda r: ROLE_RANK.get(r, 0))) \
        or '普通用户'


def set_roles(phone, new_roles, by_user):
    """给一个人设置角色组合（普通用户 / DM / 管理员，可多选）。

    三条护栏跟以前一样（都是防"手一抖把店弄瘫"）：
      ① 不能改自己的角色 —— 不然管理员一点就把自己降权，后台当场进不去
      ② 超级管理员（初始那个账号）不可改 —— 它是最后的保险
      ③ 只有超管能调整"已经是管理员"的人 —— 避免两个管理员互相降权
    """
    me = by_user or {}
    # 后台只勾 DM / 管理员这两项：普通用户是人人都有、去不掉的（见 roles_of）
    # 一个都不勾 = 只剩普通用户权限（不是"没有任何角色"）
    want = {str(r).strip() for r in (new_roles or []) if str(r).strip() in ('dm', 'admin')} | {'user'}
    users = db.rows('users')
    hit = next((x for x in users if str(x.get('phone')) == str(phone)), None)
    if not hit:
        return False, '没这个人'
    old = set(roles_of(hit))
    if str(hit.get('phone')) == str(me.get('phone')):
        return False, '不能改自己的角色（想改让另一个管理员来）'
    if hit.get('super') is True or hit.get('role') == 'super':
        return False, '超级管理员不能改'
    if 'admin' in old and 'super' not in roles_of(me):
        return False, '只有超级管理员能调整管理员'
    if old == want:
        return False, '他本来就是%s' % roles_badge(old)
    # 单值 role 跟着"最高的那个"走：老代码、日志、排序都还在读它
    primary = 'admin' if 'admin' in want else ('dm' if 'dm' in want else 'user')
    for x in users:
        if str(x.get('phone')) == str(phone):
            x['roles'] = sorted(want, key=lambda r: ROLE_RANK.get(r, 0))
            x['role'] = primary
            x['super'] = False                   # 明确不是超管，免得 role 和 super 打架
    db.write('users', users)
    audit(me.get('username'), role_of(me), '把 %s 的角色从「%s」改成「%s」'
          % (hit.get('username'), roles_text(old), roles_text(want)))
    msg = '%s 现在是：%s' % (hit.get('username'), roles_text(want))
    if 'dm' in want:
        msg += '（他登进去会看到 DM 工作台；记得去「排期」把场次排给他）'
    if 'admin' in want:
        msg += '（他也能进管理后台了）'
    return True, msg


def set_role(phone, new_role, by_user):
    """老的单角色接口（留着兼容）：等价于 set_roles([new_role])"""
    return set_roles(phone, [new_role], by_user)


def ensure_invite(user):
    """老账号可能没有邀请码（邀请返利是后加的功能），打开「我的」时顺手补一个。

    不补的话，这些账号的「我的 → 资料」里邀请码是「—」，想拉新也没码可用。
    """
    if not user or user.get('invite'):
        return user
    code = 'TS' + secrets.token_hex(3).upper()
    users = db.rows('users')
    for x in users:
        if str(x.get('phone')) == str(user.get('phone')) and not x.get('invite'):
            x['invite'] = code
    db.write('users', users)
    return dict(user, invite=code)


def public_profile(u):
    """给外人看的资料：昵称/头像/性别/年龄段/风格标签，没手机号"""
    p = u.get('profile') or {}
    return {'username': u.get('username', ''), 'role': role_of(u),
            'nick': p.get('nick') or u.get('username', ''), 'avatar': p.get('avatar') or '🎭',
            'gender': p.get('gender') or '', 'ageBucket': age_bucket(p.get('age')),
            'tags': list(p.get('tags') or [])}


def set_player_tags(user, tags):
    """设置玩家风格标签（最多 3 个，只允许 PLAYER_TAGS 内的值）。

    输入可能是列表、或逗号分隔的字符串（表单多选/逗号串都收）；清洗去重限 3 个写回 users.json。
    """
    if not user:
        return False, '没登录'
    if isinstance(tags, str):
        tags = [t for t in re.split(r'[,，、]', tags)]
    seen = []
    for t in (tags or []):
        t = clean(t, 12).strip()
        if t and t in PLAYER_TAGS and t not in seen:
            seen.append(t)
    seen = seen[:3]
    users = db.rows('users')
    for x in users:
        if str(x.get('phone')) == str(user.get('phone')):
            prof = x.get('profile') or {}
            prof['tags'] = seen
            x['profile'] = prof
    db.write('users', users)
    if seen:
        return True, '风格标签存好了（%s）' % '、'.join(seen)
    return True, '风格标签已清空'


# ---------------------------------------------------------------- 通知 / 日志
def _req_g():
    """当前请求的 flask.g（不在请求上下文时返回 None，如自检/启动脚本直接调函数）"""
    try:
        from flask import g, has_request_context
        return g if has_request_context() else None
    except Exception:
        return None


def notify(phone, title, text, kind='system', key=None):
    """站内通知（顶栏那个小铃铛的红点就是它）

    性能：一次预约动作会 notify(客人) + notify_staff(员工们) = N 次整份重写 notices.json（~150KB）。
    这里改成"请求级缓冲"：先攒在 flask.g 上，由 __init__ 的 teardown_request 一次性落盘。
    不在请求上下文（自检/启动）时保持原行为，直接写。

    key（可选，M8 去重）：同 key 已有**未读**通知（含本次请求缓冲里还没落盘的）就跳过不发，
    避免打开通知中心、重复核销等场景把同一条提醒刷成好几条。"""
    g = _req_g()
    if key:
        # ① 请求缓冲内查重：同一请求里可能已经 notify 过同 key（还没落盘）
        buf = getattr(g, '_notify_buf', None) if g is not None else None
        if buf:
            for r in buf:
                if r.get('key') == key and str(phone) in [str(p) for p in r.get('to') or []]:
                    return
        # ② 已落库的未读通知查重
        for n in db.rows('notices'):
            if n.get('key') != key:
                continue
            if str(phone) in [str(x) for x in n.get('readBy') or []]:
                continue                       # 已读的不算，允许重发
            if (not n.get('to')) or str(phone) in [str(p) for p in n.get('to') or []]:
                return
    row = {'id': now_ms() + secrets.randbelow(1000), 'title': title, 'text': text,
           'at': now_ms(), 'to': [phone], 'kind': kind, 'readBy': []}
    if key:
        row['key'] = key
    if g is not None:
        if not hasattr(g, '_notify_buf'):
            g._notify_buf = []
        g._notify_buf.append(row)
        return
    rows = db.rows('notices')
    rows.insert(0, row)
    db.write('notices', rows[:500])


def notify_staff(title, text, kind='system'):
    """给所有管理员 / 超管各发一条站内通知
    （"客人说定金付了"这种得有人去确认，所以别只发给客人自己）"""
    for u in db.rows('users'):
        if has_role(u, 'admin'):                 # 多角色：只要挂着管理员就算（含超管）
            notify(u.get('phone'), title, text, kind)


def flush_notices():
    """teardown_request 调：把本次请求攒下的通知合并成一次写盘。无请求上下文/无缓冲则什么都不做。"""
    g = _req_g()
    if g is None or not getattr(g, '_notify_buf', None):
        return
    rows = db.rows('notices')
    # 原逻辑每条都是 insert(0)：先调的排在底下，反序前置才和逐条 insert 等价
    for row in reversed(g._notify_buf):
        rows.insert(0, row)
    g._notify_buf = []
    db.write('notices', rows[:500])


def parse_day(s):
    """日历控件交上来的 '2026-09-30' → 当天 0 点的毫秒。填不成日期就返回 0"""
    try:
        return int(time.mktime(time.strptime(str(s).strip(), '%Y-%m-%d')) * 1000)
    except Exception:
        return 0


def iso_day(offset=0):
    """今天 +offset 天的 'YYYY-MM-DD'（日历控件的 min / max / 默认值都用它）"""
    return time.strftime('%Y-%m-%d', time.localtime((midnight() + offset * 86400000) / 1000))


def car_deposit(st=None):
    """拼车定金：一口价（默认 50，后台设置里能改）"""
    st = st or get_settings()
    try:
        return int(st.get('carDeposit') or 50)
    except Exception:
        return 50


def deposit_per_person(st=None):
    """定金：**一个人收多少钱**（默认 50，后台设置里能改）。

    门店规矩：定金是押位子的钱，玩完由小客服退回；没到场 / 中途跳车的不退。
    所以它跟"玩完再付的游玩费"是两笔钱，不能互相抵。
    """
    return car_deposit(st)


def audit(who, role_name, text):
    """操作日志：谁在什么时候干了什么。后台「日志」页能看到

    和 notify 一样做请求级缓冲：一个动作常连带好几条 audit（登录/下单/核销），
    合并成一次写 logs.json。"""
    row = {'id': now_ms(), 'by': who or '系统', 'role': role_name or 'user',
           'text': text, 'at': now_ms()}
    g = _req_g()
    if g is not None:
        if not hasattr(g, '_audit_buf'):
            g._audit_buf = []
        g._audit_buf.append(row)
        return
    rows = db.rows('logs')
    rows.insert(0, row)
    db.write('logs', rows[:500])


def flush_logs():
    """teardown_request 调：把本次请求攒下的日志合并成一次写盘。"""
    g = _req_g()
    if g is None or not getattr(g, '_audit_buf', None):
        return
    rows = db.rows('logs')
    for row in reversed(g._audit_buf):
        rows.insert(0, row)
    g._audit_buf = []
    db.write('logs', rows[:500])


def reminder_scan(user):
    """扫该用户「待开本」的预约，按开场远近自动发提醒（M8#157）。

    - 距开场 0~1 小时：「稍后 X 点开《…》」（key=open-<bid>-h1）
    - 距开场 23~25 小时：「明天 X 点开《…》」（key=open-<bid>-d1）
    key 去重：同一窗口只发一次，已读可重发。打开通知中心时由 my_notices 顺手调一次。"""
    if not user:
        return
    phone = str(user.get('phone'))
    now = now_ms()
    for b in db.rows('bookings'):
        if str(b.get('phone')) != phone or b.get('status') != 'booked':
            continue
        ts = int(b.get('ts') or 0)
        if ts <= now:
            continue
        hours = (ts - now) / 3600000
        bid = b.get('id')
        title = b.get('title') or ''
        tm = b.get('time') or ''
        if 0 < hours <= 1:
            notify(phone, '开场提醒', '稍后 %s 点开《%s》，别迟到哈～' % (tm, title),
                   kind='remind', key='open-%s-h1' % bid)
        elif 23 < hours <= 25:
            notify(phone, '明天开场', '明天 %s 点开《%s》，记得安排好时间' % (tm, title),
                   kind='remind', key='open-%s-d1' % bid)


def my_notices(user, limit=30):
    # 打开通知中心时顺手扫一遍待开本预约，自动补发开场提醒（reminder_scan 内部 key 去重）
    reminder_scan(user)
    phone = str(user.get('phone'))
    rows = [n for n in db.rows('notices') if not n.get('to') or phone in [str(p) for p in n.get('to') or []]]
    return rows[:limit]


def unread_count(user):
    phone = str(user.get('phone'))
    return len([n for n in db.rows('notices')
                if (not n.get('to') or phone in [str(p) for p in n.get('to') or []])
                and phone not in [str(x) for x in n.get('readBy') or []]])


def mark_read(user, ids=None):
    phone = str(user.get('phone'))
    rows = db.rows('notices')
    for n in rows:
        if ids and str(n.get('id')) not in [str(i) for i in ids]:
            continue
        if not n.get('to') or phone in [str(p) for p in n.get('to')]:
            rb = [str(x) for x in n.get('readBy') or []]
            if phone not in rb:
                n['readBy'] = rb + [phone]
    db.write('notices', rows)


# ---------------------------------------------------------------- 信用分
def adjust_credit(phone, delta, reason, who='系统'):
    """改信用分并留一条流水（客户在「我的」里能看到为什么被扣）"""
    users = db.rows('users')
    me = next((u for u in users if str(u.get('phone')) == str(phone)), None)
    if not me:
        return None, None
    before = int(me.get('credit', 100))
    try:                                    # 2026-10：参数不是数字时别让接口 500
        after = max(0, min(120, before + int(delta)))
    except (TypeError, ValueError):
        return None, None
    me['credit'] = after
    logs = me.get('creditLogs') or []
    logs.insert(0, {'id': now_ms(), 'delta': after - before, 'reason': reason or '门店调整',
                    'by': who, 'at': now_ms()})
    me['creditLogs'] = logs[:100]
    db.write('users', users)
    notify(phone, '信用分变动', '信用分 %d → %d 分。原因：%s' % (before, after, reason or '门店调整'), 'credit')
    return before, after


# ---------------------------------------------------------------- 拼车
def _car_pool_base():
    """一次遍历 bookings 同时挑出"车主车"和"同组 mates"，消除原来车主车×全表的 O(N²)。

    返回的每辆车带一个内部字段 '_phones'（车主+mates 的手机号），仅供 car_pool() 判断
    "这辆车是不是我的"用；对外输出时会剥掉。结果按 15 秒 TTL 缓存（拼车状态秒级不变）。
    """
    bookings = db.rows('bookings')
    users = {str(u.get('phone')): u for u in db.rows('users')}
    scripts = {str(s.get('id')): s for s in db.rows('scripts')}   # sid→剧本（难度/人数串）
    today0 = midnight()
    now = now_ms()
    owners = []
    mates_bucket = {}
    for ob in bookings:
        if ob.get('carNew') is True and ob.get('status') == 'booked' and (ob.get('ts') or 0) >= today0:
            owners.append(ob)
        elif not ob.get('carNew') and ob.get('carOwner') and ob.get('status') != 'cancelled':
            k = (ob.get('carOwner'), ob.get('sid'), ob.get('ts'), ob.get('time'))
            mates_bucket.setdefault(k, []).append(ob)
    out = []
    for ob in owners:
        k = (ob.get('username'), ob.get('sid'), ob.get('ts'), ob.get('time'))
        mates = mates_bucket.get(k, [])
        joined = (ob.get('players') or 1) + sum((b.get('players') or 1) for b in mates)
        members = []
        phone_set = [ob.get('phone')] + [b.get('phone') for b in mates]
        for b in [ob] + mates:
            p = users.get(str(b.get('phone')), {}).get('profile') or {}
            members.append({'nick': b.get('username') or '玩家', 'gender': p.get('gender') or '',
                            'ageBucket': age_bucket(p.get('age')), 'players': b.get('players') or 1,
                            'owner': bool(b.get('carNew')),
                            'tags': list(p.get('tags') or [])})
        sc = scripts.get(str(ob.get('sid')), {})
        deadline = int(ob.get('carDeadline') or 0)
        out.append({'id': ob.get('id'), 'sid': ob.get('sid'), 'title': ob.get('title'),
                    'emoji': ob.get('emoji') or '🎭', 'ts': ob.get('ts'), 'day': ob.get('day') or day_label(ob.get('ts')),
                    'time': ob.get('time'), 'owner': ob.get('username') or '玩家',
                    'price': ob.get('price'), 'tags': ob.get('carTags') or [], 'joined': joined,
                    'cap': ob.get('carCap') or 8, 'min': ob.get('carMin') or 4,
                    'need': max(0, (ob.get('carMin') or 4) - joined),
                    'reserved': ob.get('reserved') or 0,
                    # 满没满看的是**车主设的车上限 carCap**（不是剧本人数 cap）——
                    # 之前这里读了另一个字段，结果 6/6 的车也算"有位"，客人点进去才发现上不去
                    'full': joined >= (ob.get('carCap') or 8), 'members': members,
                    # 车主车队扩展（M1#3/#5/#6）：截止倒计时 / 提前截止 / 补满 / 剧本难度与人数串
                    'deadline': deadline,
                    'deadlineIn': max(0, deadline - now),
                    'closed': bool(ob.get('carClosed')),
                    'filled': bool(ob.get('carFilled')),
                    'scriptDiff': sc.get('diff') or 0,
                    'scriptPlayers': sc.get('players') or '',
                    '_phones': [str(p) for p in phone_set if p]})
    return sorted(out, key=lambda c: (c.get('ts') or 0, str(c.get('time'))))


def car_pool(me_phone=''):
    """拼车大厅：车主 + 已上车的人（对外只给昵称/性别/年龄段）

    基础分组结果 15 秒 TTL 缓存；'mine' 标记按当前请求的 me_phone 现算（不能缓存，因人而异）。
    likeCount/likeMind 也按 me_phone 现算：排除自己后，成员 tags ∩ 我的 tags 的人数。"""
    base = get_or_set('car_pool', 15, _car_pool_base)
    me_tags = set()
    if me_phone:
        me = db.one('users', phone=str(me_phone))
        me_tags = set(((me or {}).get('profile') or {}).get('tags') or [])
    out = []
    for c in base:
        c2 = {k: v for k, v in c.items() if k != '_phones'}
        c2['mine'] = bool(me_phone and str(me_phone) in c['_phones'])
        # 口味相投：成员里标签和我有交集的人数（扣掉我自己）
        like = 0
        if me_tags:
            for m in c2.get('members') or []:
                if set(m.get('tags') or []) & me_tags:
                    like += 1
            if c2['mine']:
                like -= 1                       # 我自己和我自己必然相交，扣掉
        c2['likeCount'] = max(0, like)
        c2['likeMind'] = c2['likeCount'] > 0
        out.append(c2)
    return out


def car_msgs(car_id, limit=50):
    """某个车队的聊天记录（不暴露手机号，只看是谁说的）"""
    rows = [m for m in db.rows('carmsgs') if str(m.get('carId')) == str(car_id)]
    return sorted(rows, key=lambda x: x.get('at') or 0)[-limit:]


def my_cars(me_phone):
    """我所在的车队 id（模板里判断按钮显示用）

    原来循环里每条预约都 db.one('users', username=...)（O(用户)）+ 再全表扫车主车（O(预约)），
    这里一次建好 username→用户 和 (车主, sid, ts)→车主车 两张表，循环内 O(1) 查。"""
    bookings = db.rows('bookings')
    users = {str(u.get('username')): u for u in db.rows('users')}
    owner_cars = {}
    for x in bookings:
        if x.get('carNew') and x.get('username'):
            owner_cars[(str(x.get('username')), str(x.get('sid')), x.get('ts'))] = x.get('id')
    out = set()
    for b in bookings:
        if str(b.get('phone')) == str(me_phone) and b.get('status') == 'booked':
            out.add(str(b.get('id')))
            if b.get('carOwner'):
                if str(b.get('carOwner')) not in users:
                    continue
                ob_id = owner_cars.get((str(b.get('carOwner')), str(b.get('sid')), b.get('ts')))
                if ob_id:
                    out.add(str(ob_id))
    return out


# ---------------------------------------------------------------- 统计
def _stats_uncached():
    bookings, pays, reviews = db.rows('bookings'), db.rows('pays'), db.rows('reviews')
    ok_bk = [b for b in bookings if b.get('status') != 'cancelled']
    by_script = {}
    for b in ok_bk:
        s = by_script.setdefault(str(b.get('sid')), {'plays': 0, 'sum': 0.0, 'n': 0})
        s['plays'] += 1
    for r in reviews:
        if not r.get('hidden'):
            s = by_script.setdefault(str(r.get('sid')), {'plays': 0, 'sum': 0.0, 'n': 0})
            s['sum'] += float(r.get('rating') or 0)
            s['n'] += 1
    for k, v in by_script.items():
        v['rating'] = round(v['sum'] / v['n'], 1) if v['n'] else 0
    paid = [o for o in pays if o.get('status') == 'paid']
    return {'plays': len(ok_bk), 'income': sum(int(o.get('deposit') or 0) for o in paid),
            'byScript': by_script, 'paidCount': len(paid),
            'hot': sorted(by_script.items(), key=lambda kv: -kv[1]['plays'])[:6]}


def stats():
    """首页/后台要用的几个数字。

    原来每次都全表扫 bookings+pays+reviews 重算，而首页→剧本库→详情会连算 3 遍。
    加 60 秒进程内 TTL：数据秒级不变，写 bookings/pays/reviews 后最长 60s 才刷新，可接受。"""
    return get_or_set('stats', 60, _stats_uncached)


def midnight(ts=None):
    """某一天的 0 点（毫秒）—— 算"今天"都用它，别在各处重复写一遍"""
    base = time.localtime((ts or now_ms()) / 1000)
    return int(time.mktime(time.strptime(time.strftime('%Y-%m-%d', base), '%Y-%m-%d'))) * 1000


def sessions_of(ts):
    """某天的场次，带上已报人数和余位。

    原来对当天每场都全表扫一遍 bookings（M 场 × B 预约 = M×B，周视图 ×7 天更明显）。
    这里先按 sessionId 一次聚合 bookings 成 joined_map，再 O(1) 赋值。
    返回 dict(s, ...) 副本：不再原地改 db 缓存里的 session 对象（AUD-B-0041）。"""
    rows = [s for s in db.rows('sessions') if s.get('ts') == ts and s.get('status') != 'cancelled']
    joined_map = {}
    for b in db.rows('bookings'):
        if b.get('status') == 'cancelled':
            continue
        sid = b.get('sessionId')
        if sid:
            joined_map[sid] = joined_map.get(sid, 0) + (b.get('players') or 1)
    out = []
    for s in rows:
        j = joined_map.get(s.get('id'), 0)
        out.append(dict(s, joined=j, left=max(0, (s.get('cap') or 99) - j)))
    return sorted(out, key=lambda x: str(x.get('time')))


def today_sessions():
    """今天的场次（首页和后台概览都用它）"""
    return sessions_of(midnight())


def room_busy(room_id, ts, tm, skip_id=None):
    """这个房间这个时段是不是排了别的场次（防撞房）。忙就返回那一场，闲就是 None"""
    if not room_id:
        return None
    for s in db.rows('sessions'):
        if str(s.get('id')) == str(skip_id):
            continue
        if (str(s.get('roomId')) == str(room_id) and s.get('ts') == ts
                and str(s.get('time')) == str(tm) and s.get('status') != 'cancelled'):
            return s
    return None


def dm_settlement(month=None):
    """DM 结算：这个月每个 DM 该拿多少

    算法（跟店里聊过的口径）：
      分成 = 他带的那些场次的营业额 × dmRate
      另外，客人"指定"了他，那部分加价（dmFee × 人数）也归他
    场次没排 DM 又不带指定加价的，就不参与结算（那是店里自己开的场）
    """
    st = get_settings()
    month = month or time.strftime('%Y-%m')
    ses_map = {s.get('id'): s for s in db.rows('sessions')}
    settles = db.rows('settles')
    acc = {}
    for b in db.rows('bookings'):
        if b.get('status') == 'cancelled':
            continue
        if time.strftime('%Y-%m', time.localtime((b.get('ts') or 0) / 1000)) != month:
            continue
        ses = ses_map.get(b.get('sessionId'))
        dm_phone = str((ses or {}).get('dm') or b.get('dmPhone') or '')
        if not dm_phone:
            continue
        a = acc.setdefault(dm_phone, {'dmPhone': dm_phone, 'sessions': set(), 'players': 0,
                                      'income': 0, 'share': 0.0, 'fee': 0, 'count_tmp': 0})
        if (b.get('sessionId') or ('b%s' % b.get('id'))) not in a['sessions']:
            a['count_tmp'] += 1                  # 一个场次算一场（同一场多人不重复计场）
        a['sessions'].add(b.get('sessionId') or ('b%s' % b.get('id')))
        a['players'] += int(b.get('players') or 0)
        a['income'] += int(b.get('amount') or 0)
        if b.get('dmPhone'):                     # 客人点名要的 DM，加价归他
            a['fee'] += int(st['dmFee']) * int(b.get('players') or 0)
    users = {str(u.get('phone')): u for u in db.rows('users')}
    mode = st.get('dmPayMode') or 'rate'
    rows = []
    for phone, a in acc.items():
        if mode == 'fixed':                      # 店里按场给固定场费（一场多少钱写死在设置里）
            a['share'] = int(st.get('dmFixedPay') or 0) * a['count_tmp']
        else:                                    # 按营业额分成
            a['share'] = round(a['income'] * float(st['dmRate']))
        a['total'] = a['share'] + a['fee']
        a['count'] = len(a.pop('sessions'))
        a['dmName'] = users.get(phone, {}).get('username') or phone
        g = dm_growth(phone)                  # 顺手把段位和好评率带上，后台一眼看出谁在成长
        a['tier'] = g['tier']
        a['goodRate'] = g['goodRate']
        a['rating'] = g['rating']
        a['settled'] = any(str(x.get('dmPhone')) == phone and x.get('month') == month and x.get('settled')
                           for x in settles)
        rows.append(a)
    return {'month': month, 'rows': sorted(rows, key=lambda x: -x['total'])}


# ---------------------------------------------------------------- DM 成长（段位）
# 六段位，定义照抄老版 DM_TIER_DEFS：带本量够了、好评率也够，才给晋升
DM_TIERS = [
    {'name': '见习 DM', 'icon': '🌱', 'need': 0, 'rate': 0},
    {'name': '青铜 DM', 'icon': '🥉', 'need': 5, 'rate': 3.5},
    {'name': '白银 DM', 'icon': '🥈', 'need': 15, 'rate': 4.0},
    {'name': '黄金 DM', 'icon': '🥇', 'need': 30, 'rate': 4.3},
    {'name': '铂金 DM', 'icon': '💠', 'need': 60, 'rate': 4.5},
    {'name': '王者 DM', 'icon': '👑', 'need': 100, 'rate': 4.7},
]


def dm_level(st):
    """定段位：带本量到位 + 好评率达标才升（老版 dmLevel 的规则，一模一样）"""
    tier = DM_TIERS[0]
    for t in DM_TIERS:
        if st['done'] >= t['need'] and (t['rate'] == 0 or st['rating'] >= t['rate']):
            tier = t
    return tier


def _dm_growth_uncached(phone):
    """一个 DM 的成长档案（老版 dmGrowth 的 Python 版）

    带本量 = 排在他名下的场次 + 客人点名他的单（去重前的条数，跟结算口径一致）
    好评率 = 收到的评价里 4–5 星占比；指定次数 = 客人下单时点名他的单数
    """
    phone = str(phone)
    sessions = [s for s in db.rows('sessions') if str(s.get('dm')) == phone]
    ses_ids = {s.get('id') for s in sessions}
    bookings = db.rows('bookings')
    mine = [b for b in bookings if b.get('status') != 'cancelled'
            and (b.get('sessionId') in ses_ids or str(b.get('dmPhone')) == phone)]
    reviews = [r for r in db.rows('reviews') if str(r.get('dmPhone')) == phone and not r.get('hidden')]
    good = [r for r in reviews if float(r.get('rating') or 0) >= 4]
    scripts = {str(s.get('id')): s for s in db.rows('scripts')}
    tag_count = {}
    for b in mine:
        for t in (scripts.get(str(b.get('sid')), {}).get('tags') or []):
            tag_count[t] = tag_count.get(t, 0) + 1
    st = {
        'done': len(mine),
        'sessions': len(sessions),
        'players': sum(int(b.get('players') or 1) for b in mine),
        'revenue': sum(int(b.get('amount') or 0) for b in mine),
        'rating': round(sum(float(r.get('rating') or 0) for r in reviews) / len(reviews), 1) if reviews else 0,
        'ratingCount': len(reviews),
        'goodRate': round(len(good) / len(reviews) * 100) if reviews else 0,
        'assigned': len([b for b in bookings if str(b.get('dmPhone')) == phone and b.get('status') != 'cancelled']),
        'topTags': [t for t, _ in sorted(tag_count.items(), key=lambda x: -x[1])[:3]],
    }
    st['tier'] = dm_level(st)
    st['next'] = next((t for t in DM_TIERS if t['need'] > st['done']), None)
    st['toNext'] = (st['next']['need'] - st['done']) if st['next'] else 0
    return st


def dm_growth(phone):
    """一个 DM 的成长档案。后台 growth 页对每个 DM 调一次、DM 工作台/公开主页也调，
    每次都全扫 sessions+bookings+reviews+scripts。按 phone 加 60 秒 TTL。"""
    return get_or_set(('dm_growth', str(phone)), 60, lambda: _dm_growth_uncached(phone))


def dm_customers_of(phone):
    """某个 DM 带过的客人（老版 dm-credit 用的就是这个口径）

    只算两类：① 排期里指定他当 DM 的那些场次里的客人 ② 下单时点名要他的客人。
    别人的客人他不该看到，这是边界。
    """
    ses_ids = {s.get('id') for s in db.rows('sessions') if str(s.get('dm')) == str(phone)}
    users = {str(u.get('phone')): u for u in db.rows('users')}
    seen = {}
    for b in db.rows('bookings'):
        p = str(b.get('phone'))
        if not p or p == str(phone):
            continue
        if b.get('sessionId') in ses_ids or str(b.get('dmPhone')) == str(phone):
            seen[p] = b.get('username') or '客人'
    out = []
    for p, name in seen.items():
        u = users.get(p, {})
        out.append({'phone': p,
                    'username': (u.get('profile') or {}).get('nick') or name,
                    'credit': u.get('credit', 100)})
    return sorted(out, key=lambda x: -(x.get('credit') or 100))


def guides(sid=None):
    """学本资料库（门店上传的解析 / 话术 / 复盘，DM 端看）"""
    rows = db.rows('guides')
    if sid is not None:
        rows = [g for g in rows if str(g.get('sid')) == str(sid)]
    return sorted(rows, key=lambda x: -(x.get('at') or 0))


def practices(status=None):
    """练本申请（DM 提、门店处理）"""
    rows = db.rows('practices')
    if status:
        rows = [p for p in rows if (p.get('status') or 'pending') == status]
    return sorted(rows, key=lambda x: -(x.get('at') or 0))


def broadcast(title, text, scope='all'):
    """群发站内通知：scope = all(全员) / customers(只客户) / dm / sleeping(老没来的)"""
    users = db.rows('users')
    cut = now_ms() - 30 * 86400000
    bookings = db.rows('bookings')
    hit = []
    for u in users:
        # 多角色之后，"是不是员工"不能再看单个 role 了：
        # 一个人可以既 DM 又管理员 —— 群发普通用户时这类账号一样要跳过。
        staffish = has_role(u, 'dm', 'admin')
        if scope == 'customers' and staffish:
            continue
        if scope == 'dm' and not has_role(u, 'dm'):
            continue
        if scope == 'sleeping':
            if staffish:
                continue
            last = max([b.get('createdAt') or 0 for b in bookings
                        if str(b.get('phone')) == str(u.get('phone'))] or [u.get('first') or 0])
            if last >= cut:
                continue
        hit.append(u)
    # 2026-10 修复：一个人都没筛出来时**不要建这条通知**。
    # 空 to 在读取侧会被当成"发给所有人"，一次没选中的群发就会变成全站广播。
    if not hit:
        return 0
    rows = db.rows('notices')
    row = {'id': now_ms(), 'title': title, 'text': text, 'at': now_ms(), 'by': '门店',
           'kind': 'broadcast', 'to': [str(u.get('phone')) for u in hit], 'readBy': []}
    rows.insert(0, row)
    db.write('notices', rows[:500])
    return len(hit)


def banners():
    """首页轮播（后台设置里能改）。老版是写死在页面里的，新版放到设置里方便改"""
    return get_settings().get('banners') or []


def parse_banners(text):
    """把后台文本框里的轮播内容解析成列表，一行一条：表情|标题|一句话|剧本id"""
    out = []
    for line in str(text or '').splitlines():
        parts = [p.strip() for p in line.split('|')]
        if not parts or not parts[0]:
            continue
        try:
            sid = int(parts[3]) if len(parts) > 3 and str(parts[3]).strip().isdigit() else 0
        except ValueError:
            sid = 0
        out.append({'emoji': parts[0] if parts[0] else '🎭',
                    'title': parts[1] if len(parts) > 1 and parts[1] else '',
                    'text': parts[2] if len(parts) > 2 and parts[2] else '', 'sid': sid})
    return out[:5]


def save_upload(file_storage, sub='misc'):
    """存上传的图片（封面 / 头像）

    返回 (网址, 错误)。网址长这样：/img/cover/cover-1a2b3c.png
    图片落在 data/img/<sub>/ 下，跟数据一起备份、一起搬走，不会丢。
    """
    if not file_storage or not file_storage.filename:
        return None, '没选文件'
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext == 'jpeg':
        ext = 'jpg'
    if ext not in ('png', 'jpg', 'webp', 'gif'):
        return None, '只收 png / jpg / webp / gif'
    raw = file_storage.read()
    if not raw:
        return None, '文件是空的'
    if len(raw) > MAX_IMG_BYTES:
        return None, '图太大了（限 %dKB，先压缩一下再传）' % (MAX_IMG_BYTES // 1024)
    folder = os.path.join(IMG_DIR, sub)
    os.makedirs(folder, exist_ok=True)
    name = '%s-%s.%s' % (sub, secrets.token_hex(6), ext)
    with open(os.path.join(folder, name), 'wb') as f:
        f.write(raw)
    return '/img/%s/%s' % (sub, name), ''


# ---------------------------------------------------------------- 验证码（只走邮箱）
# 咱们没有短信通道，验证码一律发到邮箱：注册、找回密码都是往邮箱发。
# 手机号只当账号用（登录名），别拿它收码 —— 发不出去的。
# 验证码的规矩（照抄老版 legacy/functions/api 的那几个常量，防的是"被人拿去轰炸邮箱"）
CODE_TTL = 5 * 60 * 1000       # 5 分钟有效
CODE_MAX_TRY = 5               # 同一个码最多让人试 5 次，超了作废（防暴力猜）
CODE_SEND_GAP = 60 * 1000      # 同一个邮箱 60 秒内只能要一次
CODE_DAY_LIMIT = 10            # 同一个邮箱每天最多要 10 次


def mail_provider(st=None):
    """当前用哪条发信通道。没显式选的话：谁配好了就用谁（resend 优先，其次 smtp）。"""
    st = st or get_settings()
    p = str(st.get('mailProvider') or '').strip().lower()
    if p in ('resend', 'smtp', 'webhook'):
        return p
    if str(st.get('mailKey') or '').strip():
        return 'resend'
    if st.get('smtpHost') and st.get('smtpUser') and st.get('smtpPass'):
        return 'smtp'
    return ''


def mail_ready(st=None):
    """发信通道配好了没？（后台「门店设置 → 验证码发信」里填）"""
    st = st or get_settings()
    p = mail_provider(st)
    if p == 'resend':
        return bool(str(st.get('mailKey') or '').strip())
    if p == 'webhook':
        return bool(str(st.get('mailWebhook') or '').strip())
    if p == 'smtp':
        return bool(str(st.get('smtpHost') or '').strip() and str(st.get('smtpUser') or '').strip()
                    and str(st.get('smtpPass') or '').strip())
    return False


def code_mail_html(code, shop='甜薯剧本杀', minutes=5):
    """验证码邮件的 HTML（照老版那封改的，配色换成现在这套朱红）"""
    return ('<div style="font-family:-apple-system,\'PingFang SC\',sans-serif;padding:24px">'
            '<h2 style="margin:0 0 12px">%s</h2>'
            '<p>你的验证码是：</p>'
            '<div style="font-size:32px;font-weight:800;letter-spacing:6px;color:#C8321E">%s</div>'
            '<p style="color:#666">%d 分钟内有效，请勿泄露给他人。</p></div>'
            % (shop, code, minutes))


def _post_json(url, payload, headers=None, timeout=15):
    """POST 一个 JSON（标准库，不引第三方 requests）。返回 (状态码, 响应文本)

    ⚠️ 必须带个像浏览器的 User-Agent：urllib 默认发的是 `Python-urllib/3.x`，
    而 Resend 前面挂着 Cloudflare，会把这种请求当机器人**直接拦掉**，
    返回 `403 ... error code: 1010` —— 看着像密钥错，其实是请求头被判定成爬虫，
    导致"验证码永远发不出去"（2026-09 上线当天排查出来的，别删这个头）。
    """
    import json as _json
    import urllib.request
    data = _json.dumps(payload, ensure_ascii=False).encode('utf-8')
    hdr = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'),
    }
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=data, method='POST', headers=hdr)
    import urllib.error
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        # ★ 服务端的说明在正文里，一定要读出来。
        # 以前这里直接把异常往外扔，只剩 `str(e)` = "HTTP Error 403: Forbidden" ——
        # 真正的线索（error code: 1010 / restricted_api_key / domain is not verified）
        # 全被吞了，人在后台只看得到一句"连不上"，没法修。
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            body = ''
        return e.code, body or str(e)


def mail_error_hint(status, text):
    """把邮件服务的报错翻译成一句"下一步该动哪里"的中文。

    后台那个提示条是写给店主看的，光有 `HTTP Error 403: Forbidden` 等于没说 ——
    上线当天就是被这种没头没尾的报错卡了半天，所以把已知的几种都写明白。
    """
    t = str(text or '').strip()[:220]
    low = t.lower()
    if '1010' in low:
        return ('被 Cloudflare 挡了（error code: 1010）—— 发信程序没带正常 User-Agent，'
                '说明服务器跑的还是老代码。上去更新一下：\n'
                'cd /opt/tianshu && git pull && bash deploy/install.sh tianshu.lovinfirefly.cn')
    if 'api key' in low or 'unauthorized' in low or 'restricted' in low:
        return ('Resend 不认这把 Key（%s）。去 resend.com → API Keys 重新复制一把'
                '（注意别粘到空格、别混入换行），贴到上面「API Key」栏再测' % t)
    if 'only send testing emails' in low or 'your own email' in low or 'own email address' in low:
        return ('测试发件人 onboarding@resend.dev 只能发给"注册 Resend 的那个邮箱"。'
                '想给客人发：先在 resend.com 的 Domains 里验证 lovinfirefly.cn（加几条 DNS），'
                '再把发件人改成 noreply@lovinfirefly.cn')
    if 'not verified' in low or 'verify' in low and 'domain' in low:
        return ('发件人的域名没在 Resend 验证过（%s）。去 resend.com → Domains 添加 '
                'lovinfirefly.cn，按提示加 SPF / DKIM 的 DNS 记录，验证通过再改发件人' % t)
    if 'name resolution' in low or 'getaddrinfo' in low or 'timed out' in low:
        return ('服务器连不上 api.resend.com（网络/DNS 问题）：%s —— 在服务器上跑一下 '
                '`curl -I https://api.resend.com` 看看通不通' % t)
    return '%s：%s' % (status, t)


# ---------------------------------------------------------------- 外观款式（skin）
# 一套 skin = 叠在主样式（style.css）之上的一层覆盖：只换设计语言，不动结构、不动功能。
# 管理员在「门店设置 → 外观款式」里选，**全站统一**（手机端电脑端都跟着变）。
# ⚠️ key 必须等于 CSS 文件名 skin-<key>.css，且只能取这里列出的值 ——
#    它会被拼进静态文件路径，白名单就是防路径穿越的闸门。
SKINS = {
    'playbill':  '戏单 · 铅字印刷（报头居中 / 双线 / 编号条目）',
    'noir':      '墨 · 暗色影院（灰阶分层 / 朱红点缀）',
    'riso':      'Riso 三色套印（朱红群青柠檬黄 / 巨型字）',
    'swiss':     '瑞士网格（纯白无衬线 / 细线 / 高密度）',
    'monolith':  '石碑 · 灰岩（灰底 / 单点正红 / 巨字）',
    'film':      '胶片 · 做旧（暖棕颗粒 / 手绘朱线 / 纸张噪点）',
    'ledger':    '柜台 · 手写账本（虚线框 / 等宽数字 / 印章红）',
    'symphony':  'Symphony · 暗色剧场（去模板化 / 高质感暗色 SaaS）',
}
DEFAULT_SKIN = 'playbill'


def current_skin(st=None):
    """现在用的款式（永远返回白名单内的值：没配/配错就用默认）"""
    st = st or get_settings()
    v = str(st.get('skin') or '').strip()
    return v if v in SKINS else DEFAULT_SKIN


def skin_css(st=None):
    """要额外加载的皮肤表文件名；默认款（playbill）不需要额外文件"""
    v = current_skin(st)
    return None if v == DEFAULT_SKIN else 'css/skin-%s.css' % v


# ---------------------------------------------------------------- 界面代次（uiVer）
# 一代 = 3.0 改版前那套（style.css + design2.css + templates/v1/ 的模板）
# 二代 = 现在的 3.0 骨架（多一层 design3.css + templates/ 的模板）
# 管理员在「门店设置 → 网站版式」里选，**全站统一**；客人看不到这个开关。
# 后台和 DM 工作台老用二代 —— 那是店里自己干活的地方，不跟着客人的界面来回切。
UI_VERSIONS = {
    '2': '二代 · 新骨架（推荐）',
    '1': '一代 · 老版式（改版前那套）',
}
DEFAULT_UI = '2'


def current_ui(st=None):
    """现在用哪一代界面（永远返回白名单内的值：没配/配错就用二代）"""
    st = st or get_settings()
    v = str(st.get('uiVer') or '').strip()
    return v if v in UI_VERSIONS else DEFAULT_UI


def ui_ver():
    """本次请求该渲染哪一代：管理员带 ?ui=1 / ?ui=2 可以先看再决定（和 ?skin= 一个路子）。

    模板目录、样式表都跟着它走，所以这一个函数决定了"这次整个页面长什么样"。
    """
    try:
        from flask import request as _r

        from tianshu.security import current_user as _cu
        q = _r.args.get('ui')
        if q in UI_VERSIONS and has_role(_cu(), 'admin'):
            return q
    except Exception:
        pass                      # 没有请求上下文（后台任务、自检直接调函数）就走设置值
    return current_ui()


def mail_from_name(st=None):
    """发件人昵称（客人收件箱里显示的名字，例「甜薯剧本杀」）。留空 = 只显示邮箱地址。

    ⚠️ 必须掐掉换行/制表：邮件头里一旦能塞进 \\r\\n，就能伪造出别的头（**头注入**）。
    这个值只有店主能填，但发信是最不该图省事的地方 —— clean() 不删 \\r\\n\\t，所以这里单独删。
    """
    st = st or get_settings()
    return re.sub(r'[\r\n\t]+', ' ', str(st.get('mailFromName') or '')).strip()[:40]


def mail_sender(st=None):
    """拼成 `昵称 <地址>` —— 收件箱里就显示店名而不是光秃秃一个地址。

    只有 Resend 这种 JSON 接口需要自己拼（它不认 Python formataddr 那套编码）；
    SMTP 那边用 formataddr(Header(...)) 自己处理中文 ✓
    """
    st = st or get_settings()
    addr = str(st.get('mailFrom') or st.get('smtpFrom') or st.get('smtpUser') or '').strip()
    name = mail_from_name(st)
    # 昵称/地址里带尖括号就别拼了：拼出来是坏的 From，宁可退回纯地址
    if name and addr and '<' not in addr and '<' not in name:
        return '%s <%s>' % (name, addr)
    return addr


def send_mail(to, subject, body, st=None, code=''):
    """按后台选的通道发一封邮件。返回 (成功吗, 错误说明)。

    三条通道（和老版 legacy/functions/api 那套一致，老版用的是 Resend）：
      · resend  —— POST https://api.resend.com/emails
      · webhook —— 往你自己的接口 POST（想接哪个服务都接得进来）
      · smtp    —— 直连 SMTP：465 走 SSL、587 走 STARTTLS
                   （别用 25，阿里云和几乎所有云厂商都封 25，防垃圾邮件）
    发信人、密钥这些全从「门店设置」取，不写在代码里。
    """
    st = st or get_settings()
    shop = st.get('shopName') or '甜薯剧本杀'
    provider = mail_provider(st)
    sender = str(st.get('mailFrom') or st.get('smtpFrom') or st.get('smtpUser') or '').strip()

    if provider == 'resend':
        key = str(st.get('mailKey') or '').strip()
        if not key:
            return False, '没填 Resend API Key'
        # From 用「昵称 <地址>」：客人收件箱里显示的是店名，不是一个光秃秃的邮箱
        payload = {'from': mail_sender(st) or 'onboarding@resend.dev', 'to': [to],
                   'subject': subject, 'text': body}
        if code:
            payload['html'] = code_mail_html(code, shop)
        try:
            status, resp = _post_json('https://api.resend.com/emails', payload,
                                      {'Authorization': 'Bearer ' + key})
        except Exception as e:
            # 到不了服务器（DNS / 超时 / 端口不通）
            return False, mail_error_hint(-1, '%s: %s' % (type(e).__name__, e))
        if 200 <= status < 300:
            return True, ''
        return False, mail_error_hint(status, resp)

    if provider == 'webhook':
        url = str(st.get('mailWebhook') or '').strip()
        if not url:
            return False, '没填 Webhook 地址'
        try:
            # 同时给地址和昵称：接的那头爱拼就自己拼（老版只给了 from 地址，这里只加不删）
            status, resp = _post_json(url, {'to': to, 'code': code, 'subject': subject,
                                            'from': sender, 'fromName': mail_from_name(st),
                                            'text': body})
            if 200 <= status < 300:
                return True, ''
            return False, 'Webhook 返回 %s：%s' % (status, resp[:120])
        except Exception as e:
            return False, 'Webhook 没通：%s' % str(e)[:140]

    import smtplib
    from email.header import Header
    from email.mime.text import MIMEText
    from email.utils import formataddr

    host = str(st.get('smtpHost') or '').strip()
    user = str(st.get('smtpUser') or '').strip()
    pw = str(st.get('smtpPass') or '').strip()
    if not (host and user and pw):
        return False, '还没配置发信通道（后台「概览 → 门店设置 → 验证码发信」里选一条）'
    try:
        port = int(st.get('smtpPort') or 465)
    except Exception:
        port = 465
    sender = str(st.get('smtpFrom') or '').strip() or user
    shop = st.get('shopName') or '甜薯剧本杀'

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    # 昵称优先用后台设置里的（默认就是店名），留空则只写地址
    msg['From'] = formataddr((str(Header(mail_from_name(st) or shop, 'utf-8')), sender))
    msg['To'] = to
    try:
        if port == 587:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        try:
            server.login(user, pw)
            server.sendmail(sender, [to], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return True, ''
    except Exception as e:
        return False, str(e)[:180]


def _mask_email(addr):
    """日志用的邮箱脱敏：a***@x.com（2026-10：日志里不再出现完整地址与验证码）"""
    s = str(addr or '')
    if '@' not in s:
        return (s[:1] + '***') if s else ''
    name, dom = s.split('@', 1)
    return (name[:1] + '***@' + dom)


def send_code(email, purpose):
    """发验证码。返回 (验证码, 是否真发出去了, 错误说明)。

    ※ 2026-09 起这里会**真发邮件**（配了发信邮箱的话）。
       没配发信邮箱（比如店里本机使用）就退回老办法：码打印在运行服务的黑窗口里。
       老版（legacy）也是这个思路，注释原话："未接短信服务商时为演示模式" ——
       区别是现在线上必须真发，因为没人看得到服务器那个黑窗口。
    """
    st = get_settings()
    now = now_ms()
    to = str(email).strip().lower()

    # ---- 限频（照老版的规矩：同邮箱 60 秒一次、每天 10 次，防被人拿去轰炸邮箱）----
    keep = [c for c in db.rows('codes') if (c.get('exp') or 0) + 86400000 > now]   # 留一天，用来算限频
    mine = [c for c in keep if str(c.get('target')) == to]
    last = max([c.get('at') or c.get('id') or 0 for c in mine] or [0])
    if now - last < CODE_SEND_GAP:
        return None, False, '刚发过一条，%d 秒后再点' % max(1, (CODE_SEND_GAP - (now - last)) // 1000)
    if len([c for c in mine if now - (c.get('at') or c.get('id') or 0) < 86400000]) >= CODE_DAY_LIMIT:
        return None, False, '这个邮箱今天要的验证码有点多，明天再试吧'

    code = '%06d' % secrets.randbelow(1000000)
    keep.append({'id': now, 'at': now, 'target': to, 'purpose': purpose, 'code': code,
                 'exp': now + CODE_TTL, 'used': False, 'tries': 0})
    db.write('codes', keep[-200:])

    if mail_ready(st):
        shop = st.get('shopName') or '甜薯剧本杀'
        subject = str(st.get('mailSubject') or '').strip() or '【%s】验证码' % shop
        body = ('你的验证码是：%s\n\n'
                '5 分钟内有效，请别转发给别人。\n'
                '如果不是你本人操作，忽略这封邮件就行。\n\n'
                '—— %s' % (code, shop))
        # 验证码已落库（codes.json）。真正发邮件可能要等 Resend/SMTP 往返（可达 15s），
        # 不该让用户和 waitress 工作线程干等 —— 丢进 daemon 线程发，接口立即返回。
        threading.Thread(target=_send_code_async,
                         args=(to, purpose, subject, body, st, code), daemon=True).start()
        return code, True, ''
    # 2026-10 修复：日志里**绝不打印验证码明文** —— 能读到日志的人
    # 就能拿它注册任意账号、重置别人密码。邮箱也一并脱敏。
    print('[验证码] %s（%s）：已生成，明文不落日志%s'
          % (_mask_email(to), purpose, ('（本机可用通用码）' if is_dev_request() else '')))
    return code, False, '还没配置发信通道'


def _send_code_async(to, purpose, subject, body, st, code):
    """后台线程里发验证码邮件：失败只打日志，不影响用户拿码（码已落库）。"""
    try:
        ok, err = send_mail(to, subject, body, st, code=code)
        print('[验证码] 发往 %s（%s）→ %s（通道 %s）'
              % (_mask_email(to), purpose, '已发送' if ok else '发送失败：%s' % err,
                 mail_provider(st) or '未配置'))
    except Exception as e:
        print('[验证码] 后台发信异常（码已落库）：%s: %s' % (type(e).__name__, e))


def is_dev_request():
    """这次请求算不算"在本机开发"？—— 决定通用码 1234 认不认。

    为什么不能只看 remote_addr：云服务器上 Caddy 反代之后，**所有访客的 remote_addr
    都是 127.0.0.1** —— 那样通用码就等于对全网开放（谁都能注册、还能重置别人密码）。

    主判断看 **Host**（最可靠，伪造不了）：
      · 本机开发：浏览器地址是 127.0.0.1:8000 / localhost:8000 / 局域网 192.168.x.x:8000
      · 线上：地址是自己的域名（tianshu.lovinfirefly.cn）→ 一律不算本地
    再加上两道：带 X-Forwarded-For（经反代进来）不算；来源 IP 不是内网也不算。
    （线上 8000 端口没对外开、只走 Caddy，所以"伪造 Host 为 127.0.0.1"根本进不来）
    """
    try:
        from flask import request
        host = (request.host or '').split(':')[0].strip().lower()
        if request.headers.get('X-Forwarded-For'):
            return False
        ip = request.remote_addr or ''
    except Exception:
        return True                    # 没有请求上下文（自检里直接调函数）→ 当本地
    local_host = (host in ('127.0.0.1', 'localhost', '', '0.0.0.0')
                  or host.startswith(('192.168.', '10.'))
                  or any(host.startswith('172.%d.' % n) for n in range(16, 32)))
    if not local_host:
        return False                   # 用域名访问 = 线上
    return (ip in ('', '::1', 'localhost') or ip.startswith(('127.', '10.', '192.168.'))
            or any(ip.startswith('172.%d.' % n) for n in range(16, 32)))


def use_code(email, purpose, code):
    """校验并核销验证码（一次性）。邮箱统一小写比较，用户大小写乱输也能过"""
    code = str(code or '').strip()
    if not code:
        return False
    if code == DEMO_CODE:
        # 通用码只在本机开发时有效。⚠️ 上线后这条就是后门：公网填 1234 能注册、能重置密码
        return is_dev_request()
    target = str(email or '').strip().lower()
    rows = db.rows('codes')
    dirty = False
    for c in rows:
        if (str(c.get('target')) == target and c.get('purpose') == purpose
                and str(c.get('code')) == code and not c.get('used') and (c.get('exp') or 0) > now_ms()):
            c['used'] = True
            db.write('codes', rows)
            return True
        # 码对不上：给这条码记一次"猜错"，猜满 CODE_MAX_TRY 次就作废（照老版的规矩，防暴力猜）
        if (str(c.get('target')) == target and c.get('purpose') == purpose
                and not c.get('used') and (c.get('exp') or 0) > now_ms()):
            c['tries'] = int(c.get('tries') or 0) + 1
            if c['tries'] >= CODE_MAX_TRY:
                c['used'] = True
            dirty = True
    if dirty:
        db.write('codes', rows)
    return False


# ---------------------------------------------------------------- 账号安全（改密码 / 换绑 / 注销）
def change_password(user, old_pw, new_pw):
    if not verify_password(old_pw or '', user.get('password')):
        return False, '原密码不对'
    if len(new_pw or '') < 6:
        return False, '新密码至少 6 位'
    users = db.rows('users')
    for x in users:
        if str(x.get('phone')) == str(user.get('phone')):
            x['password'] = hash_password(new_pw)
    db.write('users', users)
    notify(user.get('phone'), '密码已修改', '你的登录密码刚改过，如果不是你本人操作请联系门店', 'safe')
    audit(user.get('username'), role_of(user), '改了密码')
    return True, '密码改好了，下次用新密码登录'


# 换绑手机号的功能删了（2026-09）。
# 原因：要换绑就得先证明新号是你的，可咱们只有邮箱验证码、没有短信通道；
# 光靠"填个号码"就把名下预约订单全迁过去，等于谁都能把账号抢走。
# 真要做的话，得先加短信服务商，或者改成"换邮箱"。
# 老代码在 git 历史里（搜 change_phone），需要时能翻出来。


def delete_account(user):
    """注销：账号 + 名下数据一起删（客人有这个权利，别留着）

    2026-10 修复：以前只清 6 张表，posts / reviews / invoices / codes / wants /
    notices 里仍留着这个人的手机号或昵称，等于"注销了但个人信息还在"。
    现在把带个人标识的表都过一遍，整段放进事务里（中途失败不会留下"删了一半"的状态）。
    """
    phone = str(user.get('phone'))
    uname = str(user.get('username') or '')
    with db.transaction():
        db.write('users', [x for x in db.rows('users') if str(x.get('phone')) != phone])
        for key in ('bookings', 'pays', 'messages', 'coupons', 'favs',
                    'posts', 'invoices', 'codes', 'wants', 'reviews'):
            out = []
            for x in db.rows(key):
                if str(x.get('phone') or '') == phone:
                    continue
                if uname and str(x.get('username') or '') == uname:
                    continue
                out.append(x)
            db.write(key, out)
        # 站内通知：从收件人列表里去掉他；收件人空了的整条删掉
        ns = []
        for n in db.rows('notices'):
            to = n.get('to')
            if isinstance(to, list):
                left = [t for t in to if str(t) != phone]
                if not left:
                    continue
                n = dict(n, to=left)
            ns.append(n)
        db.write('notices', ns)
    audit(user.get('username'), role_of(user), '注销了账号（名下数据一并删除）')
    return True, '账号已注销，数据也清了'


def reschedule(user, bid, ts, new_time):
    """改期：换到新的日期/时间，定金保留；新时段没位子就改不了"""
    bookings = db.rows('bookings')
    hit = next((b for b in bookings if b.get('id') == bid), None)
    if not hit:
        return False, '没这条预约'
    if str(hit.get('phone')) != str(user.get('phone')):
        return False, '这不是你的预约'
    if hit.get('status') != 'booked':
        return False, '只有「待开本」的预约能改期'
    ts = int(ts or 0)
    tm = str(new_time or hit.get('time'))
    if not ts:
        return False, '选个新日期'
    ses = next((x for x in db.rows('sessions') if str(x.get('sid')) == str(hit.get('sid'))
                and x.get('ts') == ts and x.get('time') == tm and x.get('status') == 'open'), None)
    if ses:
        used = sum((b.get('players') or 1) for b in bookings if b.get('sessionId') == ses.get('id')
                   and b.get('status') != 'cancelled' and b.get('id') != bid)
        if (ses.get('cap') or 99) - used < (hit.get('players') or 1):
            return False, '那个时段没位子了，换一个吧'
        hit['sessionId'] = ses.get('id')
    hit.update(ts=ts, time=tm, day=day_label(ts),
               rescheduleCount=(hit.get('rescheduleCount') or 0) + 1)
    db.write('bookings', bookings)
    pays = db.rows('pays')
    for o in pays:
        if o.get('bid') == bid:
            o.update(ts=ts, time=tm, day=hit['day'])
    db.write('pays', pays)
    notify(user.get('phone'), '改期成功 📅', '《%s》改到 %s %s，定金保留' % (hit.get('title'), hit['day'], tm), 'booking')
    audit(user.get('username'), role_of(user), '把《%s》改期到 %s %s' % (hit.get('title'), hit['day'], tm))
    return True, '改到 %s %s，定金保留' % (hit['day'], tm)


def adjust_balance(phone, delta, note='', by='系统'):
    """动会员余额并记流水（充值、抵扣定金、退款都走它，账才不乱）"""
    users = db.rows('users')
    me = next((u for u in users if str(u.get('phone')) == str(phone)), None)
    if not me:
        return None, None
    before = int(me.get('balance') or 0)
    # 2026-10 修复：不要把负余额静默截成 0。
    # 那样调用方以为扣款成功了，实际根本没扣够 —— 并发时同一笔余额能被两单各抵一次。
    # 扣不动就明确返回失败（None），让调用方去提示"余额不足"。
    try:
        after = before + int(delta)
    except (TypeError, ValueError):
        return None, None
    if after < 0:
        return None, None
    me['balance'] = after
    logs = me.get('walletLogs') or []
    logs.insert(0, {'id': now_ms(), 'delta': after - before, 'note': note, 'by': by, 'at': now_ms()})
    me['walletLogs'] = logs[:100]
    db.write('users', users)
    return before, after


def my_messages(user, limit=20):
    """我给店家留的言（含店家回复）"""
    phone = str(user.get('phone'))
    return sorted([m for m in db.rows('messages') if str(m.get('phone')) == phone],
                  key=lambda x: -(x.get('createdAt') or 0))[:limit]


def community_posts(limit=60, me_phone='', ftype='', ftopic=''):
    """社区帖子，顺便标出"我点过赞没"（模板里好显示）。
    同时把发帖人头像/昵称带出来，社区页能显示头像。

    ftype / ftopic（M7，默认 ''=不过滤）：按 postType（如 'recruit'）/ topic（情感/硬核…）过滤。
    先按时间倒序排，再过滤，最后截断 limit —— 保证拿到的是最新的匹配帖。"""
    rows = sorted(db.rows('posts'), key=lambda x: -(x.get('at') or 0))
    if ftype:
        rows = [p for p in rows if (p.get('postType') or '') == ftype]
    if ftopic:
        rows = [p for p in rows if (p.get('topic') or '') == ftopic]
    rows = rows[:limit]
    users = {str(u.get('phone')): u for u in db.rows('users')}
    for p in rows:
        likes = [str(x) for x in p.get('likes') or []]
        p['likeCount'] = len(likes)
        p['liked'] = bool(me_phone) and me_phone in likes
        author = users.get(str(p.get('phone') or ''))
        profile = (author or {}).get('profile') or {}
        p['avatar'] = profile.get('avatar') or ''
        p['nick'] = profile.get('nick') or p.get('username') or '玩家'
    return rows


def reviews_of(sid=None, only_visible=True, limit=None):
    rows = db.rows('reviews')
    if sid is not None:
        rows = [r for r in rows if str(r.get('sid')) == str(sid)]
    if only_visible:
        rows = [r for r in rows if not r.get('hidden')]
    # 先按时间倒序，再截断 limit：首页只要最近几条，不必给全部评价建昵称/头像
    rows = sorted(rows, key=lambda x: -(x.get('createdAt') or 0))
    if limit:
        rows = rows[:limit]
    users = {str(u.get('username')): u for u in db.rows('users')}
    for r in rows:
        author = users.get(str(r.get('username') or ''))
        profile = (author or {}).get('profile') or {}
        r['avatar'] = profile.get('avatar') or ''
        r['nick'] = profile.get('nick') or r.get('username') or '玩家'
    return rows


# ---------------------------------------------------------------- 话术库（M7）
TALKTIP_CATS = ('开场白', '过渡', '结尾', '其他')


def talktips(cat=''):
    """DM/门店维护的开本话术库，按时间倒序；cat 给定时只看该分类。数据文件 talktips.json，cap 300。"""
    rows = db.rows('talktips')
    if cat:
        rows = [t for t in rows if (t.get('cat') or '') == cat]
    return sorted(rows, key=lambda x: -(x.get('at') or 0))


def talktip_add(user, cat, title, text):
    """新增一条话术。DM / 管理员才能加；cat 限定四类，title/text clean 限长。"""
    if not has_role(user, 'dm', 'admin'):
        return False, '只有 DM / 管理员能维护话术库'
    cat = clean(cat, 10).strip()
    if cat not in TALKTIP_CATS:
        return False, '分类只能是：%s' % ' / '.join(TALKTIP_CATS)
    title = clean(title, 40).strip()
    text = clean(text, 500).strip()
    if not title or not text:
        return False, '标题和正文都要填'
    db.update('talktips', lambda rows: rows + [{
        'id': now_ms(), 'cat': cat, 'title': title, 'text': text,
        'by': (user or {}).get('username') or '', 'phone': (user or {}).get('phone') or '',
        'at': now_ms()}], 300)
    return True, '话术已收录'


def talktip_del(user, tip_id):
    """删一条话术：作者本人 或 管理员。"""
    rows = db.rows('talktips')
    hit = next((t for t in rows if str(t.get('id')) == str(tip_id)), None)
    if not hit:
        return False, '没这条话术'
    is_author = bool(user) and str(hit.get('phone')) == str(user.get('phone'))
    if not (is_author or has_role(user, 'admin')):
        return False, '只有作者本人或管理员能删'
    rows = [t for t in rows if str(t.get('id')) != str(tip_id)]
    db.write('talktips', rows)
    return True, '已删除'


# ---------------------------------------------------------------- 发票（M8#155）
def invoice_apply(user, oid, form):
    """申请开票：订单必须 paid 且属于本人；同一订单只能申请一次。

    company/taxId/email 做 clean 限长。写 invoices.json（rows，cap 300）。"""
    if not user:
        return False, '没登录'
    order = next((o for o in db.rows('pays') if str(o.get('id')) == str(oid)), None)
    if not order:
        return False, '订单不存在'
    if str(order.get('phone')) != str(user.get('phone')):
        return False, '这不是你的订单'
    # 2026-10 修复：status='paid' 只代表**定金**已确认，游玩费是 balStatus。
    # 原来只看 status，客人付个定金就能把整单全额开成发票（钱还没收就先开票）。
    if order.get('status') != 'paid' or order.get('balStatus') != 'paid':
        return False, '只有定金和游玩费都已确认到账的订单才能申请开票'
    rows = db.rows('invoices')
    if any(str(x.get('oid')) == str(oid) for x in rows):
        return False, '这单已经申请过发票了，别重复提交'
    rec = {'id': now_ms(), 'oid': order.get('id'), 'phone': order.get('phone'),
           'username': order.get('username') or user.get('username'),
           'title': order.get('title') or '', 'day': order.get('day') or '',
           'time': order.get('time') or '', 'amount': order.get('amount') or 0,
           'company': clean(form.get('company'), 80),
           'taxId': clean(form.get('taxId'), 40),
           'email': clean(form.get('email'), 80),
           'status': 'pending', 'at': now_ms(), 'doneAt': 0, 'by': ''}
    db.update('invoices', lambda r: r + [rec], 300)
    return True, '开票申请已提交，开好会通知你'


def invoices_list(status=''):
    """发票申请列表，按时间倒序；status 给定时只看 pending/done。"""
    rows = db.rows('invoices')
    if status:
        rows = [x for x in rows if (x.get('status') or 'pending') == status]
    return sorted(rows, key=lambda x: -(x.get('at') or 0))


def invoice_mark_done(iid, by):
    """门店标记发票已开。"""
    rows = db.rows('invoices')
    hit = next((x for x in rows if str(x.get('id')) == str(iid)), None)
    if not hit:
        return False, '没这条申请'
    if hit.get('status') == 'done':
        return False, '这单已经开过了'
    hit['status'] = 'done'
    hit['doneAt'] = now_ms()
    hit['by'] = clean(by, 40)
    db.write('invoices', rows)
    if hit.get('phone'):
        notify(hit.get('phone'), '发票已开好',
               '《%s》的发票已开，留意邮箱。' % (hit.get('title') or ''),
               kind='pay', key='invoice-done-%s' % hit.get('id'))
    return True, '已标记为已开'


# ---------------------------------------------------------------- 访问埋点（M10）
def _ip_hash(ip):
    """IP 做 sha256 摘要：只存哈希不存原始 IP，拿不到具体是谁。"""
    return hashlib.sha256(str(ip or '').strip().encode('utf-8')).hexdigest()


def track_visit(ip, path):
    """记一次页面访问。visits.json 是 dict 结构（不是 rows 数组）：
    {'days': {day: {ipHash: {path: n}}}, 'updated': ms}。path 计数 +1。"""
    path = clean(path or '/', 120) or '/'
    day = iso_day(0)
    data = db.read('visits')
    if not isinstance(data, dict):
        data = {}
    days = data.setdefault('days', {})
    # 2026-10 修复：埋点是**匿名可调用**的接口，path 又完全不清理，
    # 谁刷一堆不同路径就能把 visits.json 撑到无限大、让每次请求越来越慢。
    # 这里做三件事：丢掉 30 天前的旧数据、path 截断（上面 120）、
    # 单个 IP 每天最多记 200 个不同路径。
    for old in [k for k in days if k < iso_day(-30)]:
        days.pop(old, None)
    d = days.setdefault(day, {})
    h = d.setdefault(_ip_hash(ip), {})
    if path not in h and len(h) >= 200:
        return
    h[path] = int(h.get(path) or 0) + 1
    data['updated'] = now_ms()
    db.write('visits', data)


def visit_stats(days=7):
    """近 N 天访问统计：今日 PV/UV、每日趋势、热门页面 top10。

    PV = 页面浏览次数总和；UV = 去重 ipHash 数。只看 visits.json 里最近 days 天。"""
    data = db.read('visits')
    days_map = (data or {}).get('days') if isinstance(data, dict) else None
    days_map = days_map or {}
    today = iso_day(0)
    # 最近 days 天的日期列表（含今天）
    recent = [iso_day(-i) for i in range(days - 1, -1, -1)]
    trend = []
    top = {}
    today_pv = today_uv = 0
    for day in recent:
        d = days_map.get(day) or {}
        pv = uv = 0
        for ip_hash, paths in d.items():
            uv += 1
            for p, n in (paths or {}).items():
                n = int(n or 0)
                pv += n
                top[p] = top.get(p, 0) + n
        trend.append({'day': day, 'pv': pv, 'uv': uv})
        if day == today:
            today_pv, today_uv = pv, uv
    top10 = [{'path': p, 'n': n} for p, n in sorted(top.items(), key=lambda kv: -kv[1])[:10]]
    return {'today': {'pv': today_pv, 'uv': today_uv}, 'trend': trend, 'top': top10}


# ---------------------------------------------------------------- 收藏分组（M10#172）
FAV_GROUPS = ('want', 'done', 'avoid')


def _fav_rec(rows, phone):
    return next((r for r in rows if str(r.get('phone')) == str(phone)), None)


def fav_groups(user):
    """取我的收藏分组 {'want':[],'done':[],'avoid':[]}。

    老数据只有 sids（=想玩）；第一次访问时把 sids 迁移进 groups.want 并写回一次。
    旧 sids 字段保留为兼容（=want），视图层 my_fav_ids 仍读它。"""
    if not user:
        return {'want': [], 'done': [], 'avoid': []}
    phone = str(user.get('phone'))
    rows = db.rows('favs')
    rec = _fav_rec(rows, phone)
    if rec is None:
        return {'want': [], 'done': [], 'avoid': []}
    if not isinstance(rec.get('groups'), dict):
        old_sids = [str(x) for x in (rec.get('sids') or [])]
        rec['groups'] = {'want': old_sids, 'done': [], 'avoid': []}
        db.write('favs', rows)
    g = rec['groups']
    return {'want': [str(x) for x in g.get('want') or []],
            'done': [str(x) for x in g.get('done') or []],
            'avoid': [str(x) for x in g.get('avoid') or []]}


def fav_set(user, sid, group, on):
    """把某个剧本加入/移出指定分组（want|done|avoid）。on=True 加入，False 移出。

    加入 want 时同步写回兼容字段 sids（=want），移出 want 时从 sids 删除，
    这样老的 my_fav_ids / 视图不用改也照常工作。"""
    if not user:
        return False, '没登录'
    group = str(group or 'want')
    if group not in FAV_GROUPS:
        return False, '分组只能是 want / done / avoid'
    sid = str(sid)
    rows = db.rows('favs')
    rec = _fav_rec(rows, str(user.get('phone')))
    if rec is None:
        rec = {'phone': str(user.get('phone')), 'sids': [],
               'groups': {'want': [], 'done': [], 'avoid': []}}
        rows.append(rec)
    if not isinstance(rec.get('groups'), dict):
        rec['groups'] = {'want': [str(x) for x in (rec.get('sids') or [])], 'done': [], 'avoid': []}
    g = rec['groups']
    g.setdefault('want', [])
    g.setdefault('done', [])
    g.setdefault('avoid', [])
    lst = [str(x) for x in g[group]]
    if on:
        if sid not in lst:
            lst.append(sid)
    else:
        lst = [x for x in lst if x != sid]
    g[group] = lst
    # 兼容：sids 始终等于 want
    rec['sids'] = list(g['want'])
    db.write('favs', rows)
    if on:
        return True, '已加入%s' % group
    return True, '已移出%s' % group


# ---------------------------------------------------------------- 下单 ★
def create_booking(user, form):
    """创建预约 + 生成待付定金订单
    返回 (成功吗, 提示语, 预约对象)。表单里只需要给"想要什么"，钱由这里算。"""
    st = get_settings()
    sc = db.one('scripts', id=form.get('sid'))
    if not sc:
        return False, '这个剧本不存在了，刷新看看', None
    if sc.get('onSale') is False:
        return False, '该剧本已下架', None

    # 日期两种交法都认：日历控件给的是 '2026-09-30'（ts_day），场次按钮给的是毫秒（ts）
    try:                                    # 2026-10：非数字不要抛 500，退回按日历日期解析
        ts = int(form.get('ts') or 0)
    except (TypeError, ValueError):
        ts = 0
    ts = ts or parse_day(form.get('ts_day'))
    tm = str(form.get('time') or '19:00')
    if not ts:
        return False, '请选择日期', None
    if ts < midnight():
        return False, '日期不能选今天以前的', None
    lo, hi = player_range(sc)
    try:                                    # 2026-10：人数填了非数字就按剧本下限，别 500
        players = max(1, min(hi, int(form.get('players') or lo)))
    except (TypeError, ValueError):
        players = lo
    mode = '包车' if form.get('mode') == '包车' else '拼车'
    bookings = db.rows('bookings')

    # 拼车有两种走法：自己单开一辆车（car=new）／上别人已经在等人那辆车（car=join）。
    # 上车的话日期、时间都跟着那辆车走 —— 客人不用也不能另挑。
    join_car = None
    if mode == '拼车' and str(form.get('car') or 'new') == 'join':
        cid = str(form.get('carId') or '')
        join_car = next((b for b in bookings if str(b.get('id')) == cid and b.get('carNew') is True
                         and str(b.get('sid')) == str(sc.get('id')) and b.get('status') == 'booked'
                         and (b.get('ts') or 0) >= midnight()), None)
        if not join_car:
            return False, '这辆车已经没了 —— 换一辆，或者自己单开一辆', None
        ts, tm = join_car.get('ts'), join_car.get('time')
        mates = [b for b in bookings if not b.get('carNew') and b.get('carOwner') == join_car.get('username')
                 and b.get('sid') == join_car.get('sid') and b.get('ts') == ts and b.get('time') == tm
                 and b.get('status') != 'cancelled']
        joined = (join_car.get('players') or 1) + sum(int(b.get('players') or 1) for b in mates)
        room = (join_car.get('carCap') or 8) - joined - (join_car.get('reserved') or 0)
        if room < players:
            return False, '这辆车只剩 %d 个位子了，改下人数' % max(0, room), None

    # 单开一辆车：先按你自己 1 个人上车算（定金、游玩费都先收你 1 人的份）。
    # 别人看到你的车再加进来、各自付各自的定金 —— 不然"人数"一栏会把整桌位子一次占满，
    # 车刚开出来就"已满锁车"（2026-10 客人反馈：1 个人的车显示 7/7 还锁了）。
    if mode == '拼车' and not join_car:
        players = 1

    # ① 已排场次的话，先看还有没有位子（防超卖）。上车不用查：位子由车的容量管
    ses = None
    session_id = join_car.get('sessionId') if join_car else 0
    if not join_car:
        ses = next((x for x in db.rows('sessions') if str(x.get('sid')) == str(sc.get('id'))
                    and x.get('ts') == ts and x.get('time') == tm and x.get('status') == 'open'), None)
        if ses:
            used = sum((b.get('players') or 1) for b in bookings
                       if b.get('sessionId') == ses.get('id') and b.get('status') != 'cancelled')
            left = (ses.get('cap') or 99) - used
            if left < players:
                return False, '该场次只剩 %d 个位置了，改下人数或换个时段' % max(0, left), None
            session_id = ses.get('id')
    else:
        # 2026-10 修复：**加入别人的车**以前只查车容量，完全不查场次总容量。
        # 车没满、但这场（房间）已经坐不下时照样能上车，到店才发现没位子 —— 超卖。
        ses = next((x for x in db.rows('sessions')
                    if str(x.get('id')) == str(session_id)), None)
        if ses and (ses.get('cap') or 0) > 0:
            used = sum((b.get('players') or 1) for b in bookings
                       if str(b.get('sessionId')) == str(session_id)
                       and b.get('status') != 'cancelled')
            if (ses.get('cap') or 0) - used < players:
                return False, '这场已经满了，换个时段或者改下人数', None

    # ② 线上选角：得后台给这个本开了"可提前选角"才行，且同一角色只能一人
    role = ''
    if sc.get('allowRolePick') is True:
        role = clean(form.get('role'), 20)
        if role:
            names = [r.get('name') for r in (sc.get('roles') or [])]
            if names and role not in names:
                return False, '没有这个角色', None
            if any(str(b.get('sid')) == str(sc.get('id')) and b.get('ts') == ts and b.get('time') == tm
                   and b.get('role') == role and b.get('status') != 'cancelled' for b in bookings):
                return False, '角色「%s」已经被选走了，挑一个别的吧' % role, None

    # ③ 优惠券：现在不在预约时扣，放到「支付游玩费」那一步让客人自己选。
    #     这里先按全价记录游玩费，couponId 初始为 0。

    # ④ 算钱。定金按人头（默认 50 / 人，后台能改）；都取整，别给客人报 229.6 这种数字
    if join_car:
        price = float(join_car.get('price') or sc.get('price') or 0)     # 上车跟着车价，不另算指定 DM 加价
    else:
        price = float(sc.get('price') or 0) + (float(st['dmFee']) if form.get('dmPhone') else 0)
    # 门店定金规矩（2026-10 更新）：
    #   · 拼车（单开一辆车 / 加入别人的车）：**一人 50** —— 单开先按 1 人收 50，
    #     别人上车后各自再付自己的 50；带朋友上车的话按人头一份一份交。
    #   · 包车：**50 × 车上人数**（整桌一起包，定金一次交齐）。
    #   · 共通：定金是押位子的钱，玩完由小客服退回；没到场 / 中途跳车的不退。
    #   · 游玩费：玩完再付（= 单价 × 人数），也走小客服确认那一步；优惠券抵的是它。
    amount = round(price * players)                    # 游玩费全价（玩完再付，届时可选券）
    deposit = deposit_per_person(st) * players         # 定金 = 一人 50 × 人数（单开=1人 → ¥50）

    # ⑤ 会员余额抵扣：充过钱的客人可以直接用余额顶定金（顶完剩下的才需要付现）
    used = 0
    if str(form.get('use_balance') or '') in ('1', 'on', 'true') and int(user.get('balance') or 0) > 0:
        used = min(int(user.get('balance') or 0), deposit)

    bid = now_ms() + secrets.randbelow(90)
    # 车主新开拼车：开团即开始倒计时（默认 settings.carDeadlineHours 小时；表单给 carDeadlineHours 则用它）
    _new_car = (mode == '拼车' and not join_car)
    if _new_car:
        try:
            _dh = int(form.get('carDeadlineHours') or st.get('carDeadlineHours') or 24)
        except Exception:
            _dh = int(st.get('carDeadlineHours') or 24)
        car_deadline = now_ms() + _dh * 3600000
    else:
        car_deadline = 0
    booking = {'id': bid, 'phone': user.get('phone'), 'username': user.get('username'),
               'sid': sc.get('id'), 'title': sc.get('title'), 'emoji': sc.get('emoji') or '🎭',
               'day': day_label(ts), 'ts': ts, 'time': tm, 'players': players,
               'price': price, 'amount': amount, 'status': 'booked', 'mode': mode,
               'carNew': (mode == '拼车' and not join_car),
               'carOwner': (join_car.get('username') if join_car
                            else (user.get('username') if mode == '拼车' else None)),
               'carCap': (join_car.get('carCap') if join_car else hi),
               # 2026-10 修复：原来是 min(lo, players)，而新开车时 players 被强制成 1，
               # 于是四人本也被存成"最低 1 人"—— 一开车就显示已满足最低人数，
               # 倒计时和缺人提示全失真。最低人数应取**剧本**下限，且不超过车上限。
               'carMin': (join_car.get('carMin') if join_car else max(1, min(lo, hi))),
               'carTags': (list(join_car.get('carTags') or []) if join_car
                           else [clean(t, 10) for t in form.getlist('carTags') if clean(t, 10)][:4]),
               'reserved': 0, 'sessionId': session_id,
               # 车主车队状态（仅 carNew 车主车有意义；上车的 mate 车不挂倒计时）
               'carDeadline': car_deadline, 'carClosed': False, 'carFilled': False,
               'dmPhone': (join_car.get('dmPhone') if join_car else clean(form.get('dmPhone'), 20)),
               'role': role,
               # 到店报这个码核销。**付定金并经小客服确认之前，客人自己看不到它**
               'verifyCode': '%06d' % secrets.randbelow(1000000),
               'deposit': deposit, 'balanceUsed': used, 'createdAt': now_ms()}
    order = {'id': bid + 1, 'bid': bid, 'phone': user.get('phone'), 'username': user.get('username'),
             'title': sc.get('title'), 'day': booking['day'], 'ts': ts, 'time': tm, 'players': players,
             'amount': amount, 'deposit': deposit, 'balanceUsed': used, 'payable': deposit - used,
             'status': 'unpaid', 'createdAt': now_ms(),
             'couponId': 0, 'paidAt': 0, 'refundAt': 0, 'claimedAt': 0}

    db.update('bookings', lambda rows: rows + [booking])
    db.update('pays', lambda rows: rows + [order])
    if used:
        adjust_balance(user.get('phone'), -used, '抵扣《%s》%s 的定金' % (sc.get('title'), booking['day']),
                       user.get('username'))

    if join_car:
        notify(join_car.get('phone'), '有人上你的车了',
               '%s 上了《%s》%s %s 这辆车，付定金的事店里会跟他确认。'
               % (user.get('username'), sc.get('title'), booking['day'], tm), 'car')
    # 通知里**不写核销码**：得等定金确认了才给客人看，不然等于白送一个码
    notify(user.get('phone'), '预约成功，等付定金',
           '《%s》%s %s 先给你留着位子了，定金 ¥%d（一人 %d 元）。付完定金、小客服确认到账后，'
           '核销码才会出现在「我的预约」里。'
           '玩完由小客服把定金退回；没到场或中途跳车的不退。'
           % (sc.get('title'), booking['day'], tm, deposit, deposit_per_person(st)), 'booking')
    # 门店这边也要第一时间知道：客人挑好时间了，去排期页给这条安排房间和 DM
    notify_staff('有新预约待安排',
                 '%s 约《%s》%s %s（%s · %d 人）—— 去排期页给这条安排房间和 DM'
                 % (user.get('username'), sc.get('title'), booking['day'], tm, mode, players), 'booking')
    audit(user.get('username'), role_of(user),
          '%s《%s》%s %s' % ('上车' if join_car else '预约', sc.get('title'), booking['day'], tm))
    return True, ('预约成功！定金 ¥%d（一人 %d 元，玩完退回）—— 付完等小客服确认，核销码就会显示'
                  % (deposit, deposit_per_person(st))), booking


# ---------------------------------------------------------------- 订单 ★
def order_action(user, order_id, action, is_staff=False, reason='', coupon_id='0'):
    """付定金 / 退定金。能不能退、退多少、扣不扣信用分，全看这里"""
    st = get_settings()
    pays, bookings = db.rows('pays'), db.rows('bookings')
    order = next((o for o in pays if str(o.get('id')) == str(order_id)), None)
    if not order:
        return False, '订单不存在'
    if str(order.get('phone')) != str(user.get('phone')) and not is_staff:
        return False, '这不是你的订单'
    booking = next((b for b in bookings if b.get('id') == order.get('bid')), None)

    # 客人点完「我已支付定金」→ claimed（待小客服确认）。
    # 这一步只是"他自己说付了"，钱还没认；核销码这时候仍然不给看，等 cash 到账被确认。
    if action == 'claim':
        if order.get('status') != 'unpaid':
            return False, '这一单不用再提交了'
        order.update(status='claimed', claimedAt=now_ms())
        db.write('pays', pays)
        notify(order.get('phone'), '定金已提交，等小客服确认',
               '《%s》%s %s 的定金 ¥%d，等小客服确认到账后，核销码就会显示出来。'
               % (order.get('title'), order.get('day'), order.get('time'), order.get('deposit')), 'pay')
        notify_staff('有客人说付了定金，去确认一下',
                     '%s《%s》的定金 ¥%s 待确认 —— 去「订单」页点「确认支付定金」，'
                     '确认完客人才看得到核销码。'
                     % (order.get('username'), order.get('title'), order.get('deposit')), 'pay')
        return True, '已提交，等小客服确认到账（确认后核销码才显示）'

    # 确认收到定金：**只能门店点**（管理员 / 前台 / 该场 DM）
    # 2026-10 修复：以前客人自己点 pay 也能把 unpaid 单直接置成 paid ——
    # 等于自己给自己确认收款，核销码白拿，定金确认这道人工核验形同虚设。
    # 客人只能走 claim（"我已支付"提交），确认权必须留在门店。
    if action == 'pay':
        if not is_staff:
            return False, '定金到账要由门店确认；你先点「我已支付」提交，等小客服核对'
        if order.get('status') not in ('unpaid', 'claimed'):
            return False, '这个订单现在付不了'
        order.update(status='paid', paidAt=now_ms(),
                     tradeNo=('STAFF%d' if is_staff else 'LOCAL%d') % now_ms())
        db.write('pays', pays)
        notify(order.get('phone'), '定金已确认 ✅',
               '《%s》%s %s 的定金 ¥%d 收到了 —— 核销码已经出现在「我的预约」里，到店报给 DM 就行。'
               % (order.get('title'), order.get('day'), order.get('time'), order.get('deposit')), 'pay')
        return True, '已确认收到定金 —— 客人那边现在能看到核销码了'

    # 游玩费：玩完（核销）之后付的钱 = 总价（定金是要退回的，不在这里抵）。
    # 客人点"我已完成支付" → claimed；客服 / DM 确认到账 → paid，
    # **这时定金按规矩退回，客人的点评也解锁**（玩完直接跑单的口子堵上）。
    if action == 'claim-bal':
        if order.get('balStatus') == 'paid':
            return False, '游玩费已经确认过了，不用再交'

        # 如果这单还没用券，客人可能在支付页选了一张券；在这里一次性应用并标记为已用。
        # 老数据：couponId != 0 表示预约时已经抵过了（amount 已经是抵扣后的），直接沿用。
        cid = str(coupon_id or '')
        if not int(order.get('couponId') or 0) and cid and cid != '0':
            # 券的「校验 → 改订单 → 标记已用 → 落盘」必须一气呵成：
            # 以前跨两张表且无锁，两个请求能同时读到 used=False，同一张券抵两次（2026-10 修复）
            with db.transaction():
                coupons = db.rows('coupons')
                coupon = next((c for c in coupons
                               if str(c.get('id')) == cid and not c.get('used')
                               and (c.get('all') or str(c.get('phone')) == str(user.get('phone')))
                               and (not c.get('exp') or c.get('exp') > now_ms())), None)
                if not coupon:
                    return False, '这张券用不了（可能过期、已用过或不属于你）'
                order.update(couponId=cid,
                             amount=max(0, int(order.get('amount') or 0) - int(coupon.get('amount') or 0)))
                db.write('pays', pays)
                db.update('coupons', lambda rows: [dict(c, used=True, usedAt=now_ms())
                                                   if str(c.get('id')) == cid else c for c in rows])

        bal = max(0, int(order.get('amount') or 0))
        if bal <= 0:
            return False, '这一单没有游玩费要交'
        order.update(balStatus='claimed', balClaimedAt=now_ms())
        db.write('pays', pays)
        notify(order.get('phone'), '游玩费已提交，等门店确认',
               '《%s》%s 的游玩费 ¥%d —— 小客服确认到账后，就能去「我的预约」点评这场啦。'
               % (order.get('title'), order.get('day'), bal), 'pay')
        notify_staff('有客人提交了游玩费，去确认一下',
                     '%s《%s》的游玩费 ¥%d 待确认 —— 确认完客人的点评才解锁。'
                     % (order.get('username'), order.get('title'), bal), 'pay')
        return True, '已提交，等小客服确认到账（确认后就能点评了）'

    if action == 'pay-bal':
        # 同 pay：确认收款只能门店做。以前客人能直接把 balStatus 置成 paid，
        # 不付钱就解锁点评、还触发"定金已退回"通知。
        if not is_staff:
            return False, '游玩费到账要由门店确认；你先点「我已支付」提交'
        bal = max(0, int(order.get('amount') or 0))
        if order.get('balStatus') == 'paid':
            return False, '这单的游玩费已经确认过了'
        # 玩完 → 定金按门店规矩退回（没到场 / 中途跳车的单不会被核销，所以走不到这里）。
        # **只在定金确实收到过（status=paid）时才退**：核销只证明人来了，
        # 不代表定金在系统里被确认过 —— 前台代收 / 现金那种可能还停在 unpaid。
        # 没收到过的钱不能记成"已退回"，否则客人收到"定金已退回"、账上却从来没进过这笔。
        back = 0
        warn_deposit = 0
        if not order.get('depositBack'):
            if order.get('status') == 'paid':
                back = int(order.get('deposit') or 0)
            else:
                warn_deposit = int(order.get('deposit') or 0)
        order.update(balStatus='paid', balPaidAt=now_ms())
        if back:
            order['depositBack'] = now_ms()
            # 定金里如果用会员余额抵过，要把那部分加回钱包 ——
            # 以前只记 depositBack（对外退款），余额却没退回，客人的余额平白少了（2026-10 修复）
            if int(order.get('balanceUsed') or 0) > 0:
                adjust_balance(order.get('phone'), int(order.get('balanceUsed')),
                               '《%s》玩完，退回定金里抵扣的余额' % order.get('title'), '系统')
        db.write('pays', pays)
        notify(order.get('phone'), '游玩费已确认 ✅',
               '《%s》%s 的游玩费 ¥%d 收到了。%s去「我的预约」给剧本和 DM 打分吧，等你一句话～'
               % (order.get('title'), order.get('day'), bal,
                  ('定金 ¥%d 也一起原路退回了。' % back) if back else ''), 'pay')
        if warn_deposit:
            notify_staff('游玩费确认了，但这单定金没自动退',
                         '%s《%s》%s：定金 ¥%d 在系统里还没确认到账（不是"已付"），'
                         '所以这次没有记成"已退回" —— 该退就手动退给客人，'
                         '或者先在订单页点「确认支付定金」把账补上。'
                         % (order.get('username'), order.get('title'), order.get('day'), warn_deposit),
                         'pay')
        audit((user or {}).get('username') or '门店', 'staff',
              '确认《%s》游玩费 ¥%d%s%s' % (order.get('title'), bal,
                                          ('、退定金 ¥%d' % back) if back else '',
                                          ('（定金 ¥%d 未确认到账，未退）' % warn_deposit) if warn_deposit else ''))
        return True, ('已确认收到游玩费%s —— 客人那边的点评解锁了'
                      % ('、定金已退回' if back else
                         ('（注意：定金 ¥%d 还没确认到账，这次没退）' % warn_deposit if warn_deposit else '')))

    if action == 'refund':
        if order.get('status') not in ('paid', 'unpaid', 'claimed'):
            return False, '这一单退不了'
        # 预约缺失时不能假设"离开场还早"：以前给 999 小时等于永远判定为可免费退，
        # 会对一笔**根本没收过**的钱发出"已原路退回"通知（虚假退款）。
        # 缺预约时按"不可免费退"处理，交给门店人工判断（2026-10 修复）
        hours = ((booking.get('ts') or 0) - now_ms()) / 3600000 if booking else -1
        free = hours >= float(st['freeCancelHours'])          # 距开场还够不够免费取消的时限
        was_paid = order.get('status') == 'paid'              # 这笔定金到底收过没有
        if not free and not is_staff:
            return False, '距开场不足 %s 小时，按门店规矩定金不退，特殊情况联系门店' % st['freeCancelHours']
        order.update(status='refunded' if free else 'closed', refundAt=now_ms(),
                     refundAmount=(order.get('deposit') if (free and was_paid) else 0))
        db.write('pays', pays)
        if int(order.get('balanceUsed') or 0) > 0:          # 用余额抵的那部分，退回余额
            adjust_balance(order.get('phone'), int(order['balanceUsed']),
                           '《%s》取消，退回抵扣的余额' % order.get('title'), '系统')
        if booking:
            booking.update(status='cancelled', cancelAt=now_ms(), cancelBy='staff' if is_staff else 'user')
            db.write('bookings', bookings)
            # 2026-10：原来这里有一句"临期取消扣信用分"，但它上面已经
            # `if not free and not is_staff: return False` 提前返回了，永远走不到（死代码），
            # 导致后台的「临期取消扣分」配置形同虚设。扣分改由 cancel_booking 统一负责。
        # 退款进度通知（#150）：核验结论——refund 分支原本就有一条 kind='pay' 通知；
        # 这里把免费退定金的文案明确为「已发起原路退回，1-3 工作日到账」，对齐 spec「退款已发起/已到账」。
        # 本流程是单步原子退款（发起即处理），无需再拆两条通知。
        # 只有**确实收过钱**的单才说"已原路退回"；没收过的只说取消，
        # 否则客人以为钱会退回来、实际账上从来没进过这笔（2026-10 修复）
        if free and was_paid:
            notify(order.get('phone'), '退款已发起',
                   '《%s》定金 ¥%d 已发起原路退回，1-3 个工作日到账，请留意。'
                   % (order.get('title'), order.get('deposit')), 'pay')
        elif free:
            notify(order.get('phone'), '已取消',
                   '《%s》已取消（这单定金此前未确认到账，无需退款）。' % order.get('title'), 'pay')
        else:
            notify(order.get('phone'), '已取消',
                   '《%s》的预约取消了，超时定金不退' % order.get('title'), 'pay')
        return True, (('已退款' if was_paid else '已取消（定金此前未确认到账）') if free
                      else '已取消（超时定金不退）')

    # 标记未到 / 中途跳车：按门店规矩**定金不退**（这笔钱门店收了）。
    # 只有门店能点（staff_required）：钱的事不能让客人自己操作。
    # 人没来的话顺手把这条预约取消掉，把位子放回池子；已经核销过的（玩到一半跳车）不动预约。
    if action == 'forfeit':
        if not is_staff:
            return False, '只有门店能标记未到'
        # 「已经处理过」要先判：处理完状态会变成 closed，不然重复点会误报成"定金没到账"
        if order.get('forfeitAt') or order.get('status') in ('refunded', 'closed'):
            return False, '这单已经处理过了（不用再点）'
        if order.get('status') not in ('paid', 'claimed'):
            return False, '这单的定金还没确认到账，先确认收款或直接取消'
        lost = int(order.get('deposit') or 0)
        tag = clean(reason, 30) or '未到 / 中途跳车'
        order.update(status='closed', forfeitAt=now_ms(), forfeitReason=tag, refundAmount=0)
        db.write('pays', pays)
        if booking and booking.get('status') not in ('arrived', 'done'):
            booking.update(status='cancelled', cancelAt=now_ms(), cancelBy='noshow')
            db.write('bookings', bookings)
        notify(order.get('phone'), '这一单的定金不退',
               '《%s》%s %s 这一场没有到场（或中途离开），按门店规矩定金 ¥%d 不退。'
               '位子当时一直给你留着，下次提前说一声就好～'
               % (order.get('title'), order.get('day'), order.get('time') or '', lost), 'pay')
        notify_staff('已标记未到 · 定金不退',
                     '%s《%s》%s %s —— 定金 ¥%d 按规矩不退（%s）。'
                     % (order.get('username'), order.get('title'), order.get('day'),
                        order.get('time') or '', lost, tag), 'pay')
        audit((user or {}).get('username') or '门店', 'staff',
              '标记《%s》%s 未到 · 定金 ¥%d 不退（%s）'
              % (order.get('title'), order.get('day'), lost, tag))
        return True, '已标记未到：定金 ¥%d 不退，单子关掉了' % lost

    return False, '不认识这个操作'


# ---------------------------------------------------------------- 拼车动作 ★
def car_action(user, car_id, action, form=None):
    """上车 / 退出 / 候补 / 聊两句（对外入口）。

    车队任何写操作成功后立刻作废 car_pool 的 15 秒缓存 —— 不然上车成功了，
    页面还端着旧成员表，成员数不变、按钮不消失，看着就像"点了没用"
    （真实踩坑：2026-10 用户反馈，Playwright 复现坐实）。"""
    ok, msg = _car_action(user, car_id, action, form)
    if ok:
        invalidate('car_pool')
    return ok, msg


def _car_action(user, car_id, action, form=None):
    """上车 / 退出 / 候补 / 聊两句"""
    form = form or {}
    phone, name = user.get('phone'), user.get('username')
    bookings = db.rows('bookings')
    ob = next((b for b in bookings if str(b.get('id')) == str(car_id) and b.get('carNew') is True), None)
    if not ob:
        return False, '这辆车已经没了'

    def mates():
        return [b for b in bookings if not b.get('carNew') and b.get('carOwner') == ob.get('username')
                and b.get('sid') == ob.get('sid') and b.get('ts') == ob.get('ts')
                and b.get('time') == ob.get('time') and b.get('status') != 'cancelled']

    in_car = any(str(b.get('phone')) == str(phone) and b.get('sid') == ob.get('sid')
                 and b.get('ts') == ob.get('ts') and b.get('time') == ob.get('time')
                 and b.get('status') != 'cancelled' for b in bookings)

    if action == 'join':
        if in_car:
            return False, '你已经在这辆车上了'
        joined = (ob.get('players') or 1) + sum((b.get('players') or 1) for b in mates())
        if (ob.get('carCap') or 8) - joined - (ob.get('reserved') or 0) < 1:
            return False, '车位满了，要不先排个候补？'
        dep = car_deposit()
        jid, joi = now_ms(), now_ms() + 1 + secrets.randbelow(90)
        bookings.append({'id': jid, 'phone': phone, 'username': name, 'sid': ob.get('sid'),
                         'title': ob.get('title'), 'emoji': ob.get('emoji'), 'day': ob.get('day'),
                         'ts': ob.get('ts'), 'time': ob.get('time'), 'players': 1, 'price': ob.get('price'),
                         'amount': ob.get('price'), 'deposit': dep, 'status': 'booked', 'mode': '拼车',
                         'carNew': False, 'carOwner': ob.get('username'), 'sessionId': ob.get('sessionId') or 0,
                         'dmPhone': '', 'role': '',
                         # 上车的人也要有自己的核销码（同样：定金确认后才给他看）
                         'verifyCode': '%06d' % secrets.randbelow(1000000), 'createdAt': now_ms()})
        db.write('bookings', bookings)
        # 上车同样要交押位定金（统一一口价），走跟正常预约一样的「提交 → 小客服确认 → 出核销码」
        db.update('pays', lambda rows: rows + [{
            'id': joi, 'bid': jid, 'phone': phone, 'username': name, 'title': ob.get('title'),
            'day': ob.get('day'), 'ts': ob.get('ts'), 'time': ob.get('time'), 'players': 1,
            'amount': ob.get('price') or 0, 'deposit': dep, 'balanceUsed': 0, 'payable': dep,
            'status': 'unpaid', 'createdAt': now_ms(), 'couponId': 0, 'paidAt': 0, 'refundAt': 0,
            'claimedAt': 0}])
        notify(ob.get('phone'), '有人上你的车了',
               '%s 加入了《%s》%s %s 这车。' % (name, ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        notify(phone, '上车了，还差定金',
               '《%s》%s %s 你上了 %s 的车，定金 ¥%d。回「我的预约」点支付定金，'
               '小客服确认到账后核销码才会显示。'
               % (ob.get('title'), ob.get('day'), ob.get('time'), ob.get('username'), dep), 'car')
        if joined + 1 >= (ob.get('carMin') or 4):            # 够最低人数就通知全车"成局"
            for x in [ob] + mates():
                if x.get('phone'):
                    notify(x.get('phone'), '这车凑齐人啦 🎉',
                           '《%s》%s %s 够开局人数了，准时到哈' % (ob.get('title'), ob.get('day'), ob.get('time')), 'car')
        return True, '上车成功，记得到点到店'

    if action == 'quit':
        if not in_car:
            return False, '你本来就不在这辆车上'
        for b in bookings:
            if (str(b.get('phone')) == str(phone) and not b.get('carNew')
                    and b.get('carOwner') == ob.get('username') and b.get('sid') == ob.get('sid')
                    and b.get('ts') == ob.get('ts') and b.get('time') == ob.get('time')
                    and b.get('status') == 'booked'):
                b.update(status='cancelled', cancelAt=now_ms())
        db.write('bookings', bookings)
        notify(ob.get('phone'), '有人下车了', '%s 退出了《%s》那车。' % (name, ob.get('title')), 'car')
        wl = sorted([x for x in db.rows('wants') if x.get('carId') == car_id and x.get('status') == 'waiting'],
                    key=lambda x: x.get('at') or 0)
        if wl:                                               # 有空位先喊排在最前头的
            notify(wl[0].get('phone'), '有空位了 🚗',
                   '《%s》%s %s 空出一个位置，快去上车' % (ob.get('title'), ob.get('day'), ob.get('time')), 'car')
            return True, '已下车（顺手通知了一位候补的）'
        return True, '已下车'

    if action == 'tags':
        """车主给车队贴标签（不跳车 / 准时到场 / 新手友好…），别人看了更放心"""
        if str(ob.get('phone')) != str(phone) and not user.get('_staff'):
            return False, '只有车主能改车队标签'
        # 表单可能给一个字符串（单选）也可能给一组（多选勾选框），两种都收
        raw = form.getlist('tags') if hasattr(form, 'getlist') else form.get('tags')
        if isinstance(raw, str):
            raw = [t for t in raw.replace('，', ',').split(',') if t.strip()]
        tags = [clean(t, 8) for t in (raw or [])][:4]
        ob['carTags'] = tags
        db.write('bookings', bookings)
        return True, '车队标签存好了'

    if action == 'reserved':
        """车主留几个熟人位（别人就占不满了）"""
        if str(ob.get('phone')) != str(phone) and not user.get('_staff'):
            return False, '只有车主能留位'
        try:                                # 2026-10：非数字不要 500
            n = max(0, min(3, int(form.get('n') or 0)))
        except (TypeError, ValueError):
            return False, '留位数量填得不对'
        ob['reserved'] = n
        db.write('bookings', bookings)
        return True, '留了 %d 个熟人位' % n

    if action == 'msg':
        """车队里聊两句（拼车的人互相通气用）"""
        text = clean(form.get('text'), 120)
        if not text:
            return False, '说点什么再发'
        db.update('carmsgs', lambda rows: rows + [{
            'id': now_ms(), 'carId': car_id, 'by': name, 'phone': phone,
            'text': text, 'at': now_ms()}], 300)
        return True, '发出去了'

    if action == 'wait':
        rows = db.rows('wants')
        if any(x.get('carId') == car_id and str(x.get('phone')) == str(phone) and x.get('status') == 'waiting' for x in rows):
            pos = len([x for x in rows if x.get('carId') == car_id and x.get('status') == 'waiting'])
            return True, '你已经在候补队列里了（第 %d 位）' % pos
        rows.append({'id': now_ms(), 'carId': car_id, 'phone': phone, 'username': name,
                     'status': 'waiting', 'at': now_ms()})
        db.write('wants', rows)
        pos = len([x for x in rows if x.get('carId') == car_id and x.get('status') == 'waiting'])
        return True, '排上候补了，第 %d 位，有空位就叫你' % pos

    # ---- 车主车队状态：提前截止 / 标记补满 / 改截止时间（M1#5/#6/#9）----
    # 权限统一：车主本人 或 门店员工（user._staff，后台代操作时传）
    def _is_owner_or_staff():
        return str(ob.get('phone')) == str(phone) or bool(user.get('_staff'))

    if action == 'close':
        if not _is_owner_or_staff():
            return False, '只有车主能提前截止'
        ob['carClosed'] = True
        db.write('bookings', bookings)
        for x in [ob] + mates():                       # 通知全体成员
            if x.get('phone'):
                notify(x.get('phone'), '这车提前截止了',
                       '《%s》%s %s 提前截止拼车，不再加人了。' % (ob.get('title'), ob.get('day'), ob.get('time')),
                       kind='car', key='carclosed-%s' % car_id)
        # 候补队列里这台车的 waiting 行全部置 closed，并逐个通知
        wrows = db.rows('wants')
        touched = False
        for w in wrows:
            if w.get('carId') == car_id and w.get('status') == 'waiting':
                w['status'] = 'closed'
                touched = True
                if w.get('phone'):
                    notify(w.get('phone'), '这车截止了',
                           '《%s》%s %s 截止拼车了，去看看别的车吧。' % (ob.get('title'), ob.get('day'), ob.get('time')),
                           kind='car', key='carclosed-w-%s' % w.get('id'))
        if touched:
            db.write('wants', wrows)
        return True, '已提前截止，通知了车上和候补的人'

    if action == 'fill':
        if not _is_owner_or_staff():
            return False, '只有车主能标记补满'
        ob['carFilled'] = True
        db.write('bookings', bookings)
        for x in [ob] + mates():
            if x.get('phone'):
                notify(x.get('phone'), '已标记补满',
                       '《%s》%s %s 已补满，准备发车啦～' % (ob.get('title'), ob.get('day'), ob.get('time')),
                       kind='car', key='carfilled-%s' % car_id)
        return True, '已标记补满，通知车上成员准备发车'

    if action == 'deadline':
        if not _is_owner_or_staff():
            return False, '只有车主能改截止时间'
        try:
            h = int(form.get('deadlineHours') or 0)
        except Exception:
            h = 0
        if not (1 <= h <= 168):
            return False, '截止时长要在 1~168 小时之间'
        ob['carDeadline'] = now_ms() + h * 3600000
        db.write('bookings', bookings)
        return True, '已把拼车截止时间改成 %d 小时后' % h

    return False, '不认识这个操作'


# ---------------------------------------------------------------- 到店核销 ★
def _maybe_car_reward(phone):
    """车主奖励（M1#7）：核销车主自己开的那一车时 carCount+1；
    每开满 settings.carRewardThreshold 车就发一张 settings.carRewardValue 元券（180 天有效）。"""
    st = get_settings()
    threshold = int(st.get('carRewardThreshold') or 5)
    value = int(st.get('carRewardValue') or 10)
    users = db.rows('users')
    me = next((u for u in users if str(u.get('phone')) == str(phone)), None)
    if not me:
        return
    count = int(me.get('carCount') or 0) + 1
    me['carCount'] = count
    db.write('users', users)
    if threshold > 0 and count % threshold == 0:
        now = now_ms()
        coupon = {'id': now + secrets.randbelow(90), 'phone': phone,
                  # 既有核销逻辑读 amount；spec 契约字段为 value，两个都写以兼容
                  'amount': value, 'value': value, 'minAmount': 0,
                  'used': False, 'exp': now + 180 * 86400000, 'all': False,
                  'note': '车主奖励', 'at': now}
        db.update('coupons', lambda rows: rows + [coupon])
        notify(phone, '车主奖励到账',
               '你已经开满 %d 车啦，送你一张 ¥%d 抵扣券（180 天有效），下次玩本直接用～'
               % (count, value), kind='pay', key='car-reward-%s-%d' % (phone, count))


def verify_checkin(code, by_name):
    """客户报核销码，前台在这儿核销"""
    bookings = db.rows('bookings')
    hit = next((b for b in bookings if str(b.get('verifyCode')) == str(code).strip()
                and b.get('status') == 'booked'), None)
    if not hit:
        return False, '这个码查不到未核销的预约', None
    hit.update(status='arrived', arrivedAt=now_ms(), verifiedBy=by_name)
    db.write('bookings', bookings)
    # 核销的是车主自己开的那一车 → 计一次车数，满阈值发车主奖励券
    if hit.get('carNew') is True:
        _maybe_car_reward(hit.get('phone'))
    notify(hit.get('phone'), '到店核销 ✅',
           '《%s》%s %s 核销完成，玩得开心～' % (hit.get('title'), hit.get('day'), hit.get('time')), 'verify')
    # 玩完顺手邀请写短评（key=review-<bid> 天然去重，同一车只提醒一次）
    notify(hit.get('phone'), '写个短评吧',
           '《%s》刚开完，回「我的预约」给这场写条短评？' % (hit.get('title') or ''),
           kind='review', key='review-%s' % hit.get('id'))
    audit(by_name, 'staff', '核销《%s》（码 %s）' % (hit.get('title'), code))
    return True, '核销成功：%s %s %s（%s 人）' % (hit.get('title'), hit.get('day'), hit.get('time'),
                                                hit.get('players')), hit
