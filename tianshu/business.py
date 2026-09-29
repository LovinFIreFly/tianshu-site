# -*- coding: utf-8 -*-
"""
★ 业务规则：钱怎么算、分怎么扣、车队怎么拼 —— 全店最要紧的一段

一条铁律：所有判断都在服务端。表单里传过来的数字只当"意向"，
最后算出来多少以这里为准（以前有人改前端把 288 的本订成 1 块钱）。
"""
import os
import secrets
import time

from tianshu.db import db
from tianshu.security import hash_password, verify_password
from config import DEMO_CODE, IMG_DIR, MAX_IMG_BYTES, WEEK

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
    import re
    m = re.search(r'(\d+)\s*[-~到]\s*(\d+)', str(script.get('players') or ''))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d+)', str(script.get('players') or ''))
    return (int(m.group(1)), int(m.group(1))) if m else (1, 8)


def get_settings():
    from config import SETTINGS_DEFAULT
    s = db.read('settings')
    out = dict(SETTINGS_DEFAULT)
    if isinstance(s, dict):
        out.update(s)
    return out


def clean(t, max_len=200):
    import re
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
    """给外人看的资料：昵称/头像/性别/年龄段，没手机号"""
    p = u.get('profile') or {}
    return {'username': u.get('username', ''), 'role': role_of(u),
            'nick': p.get('nick') or u.get('username', ''), 'avatar': p.get('avatar') or '🎭',
            'gender': p.get('gender') or '', 'ageBucket': age_bucket(p.get('age'))}


# ---------------------------------------------------------------- 通知 / 日志
def notify(phone, title, text, kind='system'):
    """站内通知（顶栏那个小铃铛的红点就是它）"""
    rows = db.rows('notices')
    rows.insert(0, {'id': now_ms() + secrets.randbelow(1000), 'title': title, 'text': text,
                    'at': now_ms(), 'to': [phone], 'kind': kind, 'readBy': []})
    db.write('notices', rows[:500])


def notify_staff(title, text, kind='system'):
    """给所有管理员 / 超管各发一条站内通知
    （"客人说定金付了"这种得有人去确认，所以别只发给客人自己）"""
    for u in db.rows('users'):
        if has_role(u, 'admin'):                 # 多角色：只要挂着管理员就算（含超管）
            notify(u.get('phone'), title, text, kind)


def parse_day(s):
    """日历控件交上来的 '2026-09-30' → 当天 0 点的毫秒。填不成日期就返回 0"""
    try:
        import time as _t
        return int(_t.mktime(_t.strptime(str(s).strip(), '%Y-%m-%d')) * 1000)
    except Exception:
        return 0


def iso_day(offset=0):
    """今天 +offset 天的 'YYYY-MM-DD'（日历控件的 min / max / 默认值都用它）"""
    import time as _t
    return _t.strftime('%Y-%m-%d', _t.localtime((midnight() + offset * 86400000) / 1000))


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
    """操作日志：谁在什么时候干了什么。后台「日志」页能看到"""
    rows = db.rows('logs')
    rows.insert(0, {'id': now_ms(), 'by': who or '系统', 'role': role_name or 'user',
                    'text': text, 'at': now_ms()})
    db.write('logs', rows[:500])


def my_notices(user, limit=30):
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
    after = max(0, min(120, before + int(delta)))
    me['credit'] = after
    logs = me.get('creditLogs') or []
    logs.insert(0, {'id': now_ms(), 'delta': after - before, 'reason': reason or '门店调整',
                    'by': who, 'at': now_ms()})
    me['creditLogs'] = logs[:100]
    db.write('users', users)
    notify(phone, '信用分变动', '信用分 %d → %d 分。原因：%s' % (before, after, reason or '门店调整'), 'credit')
    return before, after


# ---------------------------------------------------------------- 拼车
def car_pool(me_phone=''):
    """拼车大厅：车主 + 已上车的人（对外只给昵称/性别/年龄段）"""
    bookings = db.rows('bookings')
    users = {str(u.get('phone')): u for u in db.rows('users')}
    today0 = int(time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d'))) * 1000
    out = []
    for ob in bookings:
        if not (ob.get('carNew') is True and ob.get('status') == 'booked' and (ob.get('ts') or 0) >= today0):
            continue
        mates = [b for b in bookings if not b.get('carNew') and b.get('carOwner') == ob.get('username')
                 and b.get('sid') == ob.get('sid') and b.get('ts') == ob.get('ts')
                 and b.get('time') == ob.get('time') and b.get('status') != 'cancelled']
        joined = (ob.get('players') or 1) + sum((b.get('players') or 1) for b in mates)
        members = []
        for b in [ob] + mates:
            p = users.get(str(b.get('phone')), {}).get('profile') or {}
            members.append({'nick': b.get('username') or '玩家', 'gender': p.get('gender') or '',
                            'ageBucket': age_bucket(p.get('age')), 'players': b.get('players') or 1,
                            'owner': bool(b.get('carNew'))})
        out.append({'id': ob.get('id'), 'sid': ob.get('sid'), 'title': ob.get('title'),
                    'emoji': ob.get('emoji') or '🎭', 'ts': ob.get('ts'), 'day': ob.get('day') or day_label(ob.get('ts')),
                    'time': ob.get('time'), 'owner': ob.get('username') or '玩家',
                    'price': ob.get('price'), 'tags': ob.get('carTags') or [], 'joined': joined,
                    'cap': ob.get('carCap') or 8, 'min': ob.get('carMin') or 4,
                    'need': max(0, (ob.get('carMin') or 4) - joined),
                    'reserved': ob.get('reserved') or 0,
                    'full': joined >= (ob.get('cap') or 8), 'members': members,
                    'mine': bool(me_phone and any(str(b.get('phone')) == str(me_phone) for b in [ob] + mates))})
    return sorted(out, key=lambda c: (c.get('ts') or 0, str(c.get('time'))))


def car_msgs(car_id, limit=50):
    """某个车队的聊天记录（不暴露手机号，只看是谁说的）"""
    rows = [m for m in db.rows('carmsgs') if str(m.get('carId')) == str(car_id)]
    return sorted(rows, key=lambda x: x.get('at') or 0)[-limit:]


def my_cars(me_phone):
    """我所在的车队 id（模板里判断按钮显示用）"""
    out = set()
    for b in db.rows('bookings'):
        if str(b.get('phone')) == str(me_phone) and b.get('status') == 'booked':
            out.add(str(b.get('id')))
            if b.get('carOwner'):
                owner = db.one('users', username=b.get('carOwner'))
                if owner:
                    ob = next((x for x in db.rows('bookings') if x.get('carNew') and x.get('username') == b.get('carOwner')
                               and x.get('sid') == b.get('sid') and x.get('ts') == b.get('ts')), None)
                    if ob:
                        out.add(str(ob.get('id')))
    return out


# ---------------------------------------------------------------- 统计
def stats():
    """首页/后台要用的几个数字"""
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


def midnight(ts=None):
    """某一天的 0 点（毫秒）—— 算"今天"都用它，别在各处重复写一遍"""
    base = time.localtime((ts or now_ms()) / 1000)
    return int(time.mktime(time.strptime(time.strftime('%Y-%m-%d', base), '%Y-%m-%d'))) * 1000


def sessions_of(ts):
    """某天的场次，带上已报人数和余位"""
    rows = [s for s in db.rows('sessions') if s.get('ts') == ts and s.get('status') != 'cancelled']
    for s in rows:
        s['joined'] = sum((b.get('players') or 1) for b in db.rows('bookings')
                          if b.get('sessionId') == s.get('id') and b.get('status') != 'cancelled')
        s['left'] = max(0, (s.get('cap') or 99) - s['joined'])
    return sorted(rows, key=lambda x: str(x.get('time')))


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


def dm_growth(phone):
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


def mail_from_name(st=None):
    """发件人昵称（客人收件箱里显示的名字，例「甜薯剧本杀」）。留空 = 只显示邮箱地址。

    ⚠️ 必须掐掉换行/制表：邮件头里一旦能塞进 \\r\\n，就能伪造出别的头（**头注入**）。
    这个值只有店主能填，但发信是最不该图省事的地方 —— clean() 不删 \\r\\n\\t，所以这里单独删。
    """
    import re
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
        ok, err = send_mail(to, subject, body, st, code=code)
        print('[验证码] 发往 %s（%s）：%s  →  %s（通道 %s）'
              % (to, purpose, code, '已发送' if ok else '发送失败', mail_provider(st) or '未配置'))
        return code, ok, err
    print('[验证码] %s（%s）：%s%s'
          % (to, purpose, code, ('    也可以直接用 %s' % DEMO_CODE) if is_dev_request() else ''))
    return code, False, '还没配置发信通道'


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
    """注销：账号 + 名下数据一起删（客人有这个权利，别留着）"""
    phone = str(user.get('phone'))
    db.write('users', [x for x in db.rows('users') if str(x.get('phone')) != phone])
    for key in ('bookings', 'pays', 'messages', 'coupons', 'favs'):
        db.write(key, [x for x in db.rows(key) if str(x.get('phone')) != phone])
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
    after = max(0, before + int(delta))
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


def community_posts(limit=60, me_phone=''):
    """社区帖子，顺便标出"我点过赞没"（模板里好显示）"""
    rows = sorted(db.rows('posts'), key=lambda x: -(x.get('at') or 0))[:limit]
    for p in rows:
        likes = [str(x) for x in p.get('likes') or []]
        p['likeCount'] = len(likes)
        p['liked'] = bool(me_phone) and me_phone in likes
    return rows


def reviews_of(sid=None, only_visible=True):
    rows = db.rows('reviews')
    if sid is not None:
        rows = [r for r in rows if str(r.get('sid')) == str(sid)]
    if only_visible:
        rows = [r for r in rows if not r.get('hidden')]
    return sorted(rows, key=lambda x: -(x.get('createdAt') or 0))


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
    ts = int(form.get('ts') or 0) or parse_day(form.get('ts_day'))
    tm = str(form.get('time') or '19:00')
    if not ts:
        return False, '请选择日期', None
    if ts < midnight():
        return False, '日期不能选今天以前的', None
    lo, hi = player_range(sc)
    players = max(1, min(hi, int(form.get('players') or lo)))
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

    # ③ 优惠券
    coupon = None
    cid = str(form.get('couponId') or '')
    if cid and cid != '0':
        coupon = next((c for c in db.rows('coupons')
                       if str(c.get('id')) == cid and not c.get('used')
                       and (c.get('all') or str(c.get('phone')) == str(user.get('phone')))
                       and (not c.get('exp') or c.get('exp') > now_ms())), None)
        if not coupon:
            return False, '这张券用不了（可能过期或已用过）', None

    # ④ 算钱。拼车定金统一一口价（默认 50），包车按比例；都取整，别给客人报 229.6 这种数字
    if join_car:
        price = float(join_car.get('price') or sc.get('price') or 0)     # 上车跟着车价，不另算指定 DM 加价
    else:
        price = float(sc.get('price') or 0) + (float(st['dmFee']) if form.get('dmPhone') else 0)
    # 门店收费规则（2026-09 定的）：
    #   · 定金：**统一一个人 50**（拼车、包车都一样）—— 这是押位子的钱，玩完由小客服退回；
    #     没到场 / 中途跳车的，定金不退。
    #   · 游玩费：玩完再付（= 单价 × 人数），也走小客服确认那一步。
    #   · 优惠券抵的是游玩费（定金是要退回去的，抵它没意义）。
    amount = round(price * players)                    # 游玩费（玩完再付）
    deposit = deposit_per_person(st) * players         # 定金 = 一人 50 × 人数
    if coupon:
        amount = max(0, amount - int(coupon.get('amount') or 0))

    # ⑤ 会员余额抵扣：充过钱的客人可以直接用余额顶定金（顶完剩下的才需要付现）
    used = 0
    if str(form.get('use_balance') or '') in ('1', 'on', 'true') and int(user.get('balance') or 0) > 0:
        used = min(int(user.get('balance') or 0), deposit)

    bid = now_ms() + secrets.randbelow(90)
    booking = {'id': bid, 'phone': user.get('phone'), 'username': user.get('username'),
               'sid': sc.get('id'), 'title': sc.get('title'), 'emoji': sc.get('emoji') or '🎭',
               'day': day_label(ts), 'ts': ts, 'time': tm, 'players': players,
               'price': price, 'amount': amount, 'status': 'booked', 'mode': mode,
               'carNew': (mode == '拼车' and not join_car),
               'carOwner': (join_car.get('username') if join_car
                            else (user.get('username') if mode == '拼车' else None)),
               'carCap': (join_car.get('carCap') if join_car else hi),
               'carMin': (join_car.get('carMin') if join_car else min(lo, players)),
               'carTags': (list(join_car.get('carTags') or []) if join_car
                           else [clean(t, 10) for t in form.getlist('carTags') if clean(t, 10)][:4]),
               'reserved': 0, 'sessionId': session_id,
               'dmPhone': (join_car.get('dmPhone') if join_car else clean(form.get('dmPhone'), 20)),
               'role': role,
               # 到店报这个码核销。**付定金并经小客服确认之前，客人自己看不到它**
               'verifyCode': '%06d' % secrets.randbelow(1000000),
               'deposit': deposit, 'balanceUsed': used, 'createdAt': now_ms()}
    order = {'id': bid + 1, 'bid': bid, 'phone': user.get('phone'), 'username': user.get('username'),
             'title': sc.get('title'), 'day': booking['day'], 'ts': ts, 'time': tm, 'players': players,
             'amount': amount, 'deposit': deposit, 'balanceUsed': used, 'payable': deposit - used,
             'status': 'unpaid', 'createdAt': now_ms(),
             'couponId': coupon.get('id') if coupon else 0, 'paidAt': 0, 'refundAt': 0, 'claimedAt': 0}

    db.update('bookings', lambda rows: rows + [booking])
    db.update('pays', lambda rows: rows + [order])
    if used:
        adjust_balance(user.get('phone'), -used, '抵扣《%s》%s 的定金' % (sc.get('title'), booking['day']),
                       user.get('username'))
    if coupon:
        db.update('coupons', lambda rows: [dict(c, used=True, usedAt=now_ms()) if str(c.get('id')) == cid else c
                                           for c in rows])
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
def order_action(user, order_id, action, is_staff=False):
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

    # 确认收到定金：管理员 / 前台在「订单」页点；客人自己点的话只允许从 unpaid 走
    if action == 'pay':
        if order.get('status') not in ('unpaid', 'claimed'):
            return False, '这个订单现在付不了'
        if not is_staff and order.get('status') == 'claimed':
            return False, '这单已经提交过了，等店里确认'
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
        bal = max(0, int(order.get('amount') or 0))
        if order.get('balStatus') == 'paid':
            return False, '游玩费已经确认过了，不用再交'
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
        bal = max(0, int(order.get('amount') or 0))
        if order.get('balStatus') == 'paid':
            return False, '这单的游玩费已经确认过了'
        # 玩完 → 定金按门店规矩退回（没到场 / 中途跳车的单不会被核销，所以走不到这里）
        back = 0 if order.get('depositBack') else int(order.get('deposit') or 0)
        order.update(balStatus='paid', balPaidAt=now_ms())
        if back:
            order['depositBack'] = now_ms()
        db.write('pays', pays)
        notify(order.get('phone'), '游玩费已确认 ✅',
               '《%s》%s 的游玩费 ¥%d 收到了。%s去「我的预约」给剧本和 DM 打分吧，等你一句话～'
               % (order.get('title'), order.get('day'), bal,
                  ('定金 ¥%d 也一起原路退回了。' % back) if back else ''), 'pay')
        audit((user or {}).get('username') or '门店', 'staff',
              '确认《%s》游玩费 ¥%d%s' % (order.get('title'), bal,
                                        ('、退定金 ¥%d' % back) if back else ''))
        return True, ('已确认收到游玩费%s —— 客人那边的点评解锁了'
                      % ('、定金已退回' if back else ''))

    if action == 'refund':
        if order.get('status') not in ('paid', 'unpaid', 'claimed'):
            return False, '这一单退不了'
        hours = ((booking.get('ts') or 0) - now_ms()) / 3600000 if booking else 999
        free = hours >= float(st['freeCancelHours'])          # 距开场还够不够免费取消的时限
        if not free and not is_staff:
            return False, '距开场不足 %s 小时，按门店规矩定金不退，特殊情况联系门店' % st['freeCancelHours']
        order.update(status='refunded' if free else 'closed', refundAt=now_ms(),
                     refundAmount=order.get('deposit') if free else 0)
        db.write('pays', pays)
        if int(order.get('balanceUsed') or 0) > 0:          # 用余额抵的那部分，退回余额
            adjust_balance(order.get('phone'), int(order['balanceUsed']),
                           '《%s》取消，退回抵扣的余额' % order.get('title'), '系统')
        if booking:
            booking.update(status='cancelled', cancelAt=now_ms(), cancelBy='staff' if is_staff else 'user')
            db.write('bookings', bookings)
            if not free and not is_staff and int(st['lateCancelPenalty']) > 0:
                adjust_credit(order.get('phone'), -int(st['lateCancelPenalty']) * 10, '临期取消', '系统')
        notify(order.get('phone'), '退款已处理' if free else '已取消',
               ('《%s》定金 ¥%d 退给你了' % (order.get('title'), order.get('deposit'))) if free
               else ('《%s》的预约取消了，超时定金不退' % order.get('title')), 'pay')
        return True, '已退款' if free else '已取消（超时定金不退）'

    return False, '不认识这个操作'


# ---------------------------------------------------------------- 拼车动作 ★
def car_action(user, car_id, action, form=None):
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
        n = max(0, min(3, int(form.get('n') or 0)))
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

    return False, '不认识这个操作'


# ---------------------------------------------------------------- 到店核销 ★
def verify_checkin(code, by_name):
    """客户报核销码，前台在这儿核销"""
    bookings = db.rows('bookings')
    hit = next((b for b in bookings if str(b.get('verifyCode')) == str(code).strip()
                and b.get('status') == 'booked'), None)
    if not hit:
        return False, '这个码查不到未核销的预约', None
    hit.update(status='arrived', arrivedAt=now_ms(), verifiedBy=by_name)
    db.write('bookings', bookings)
    notify(hit.get('phone'), '到店核销 ✅',
           '《%s》%s %s 核销完成，玩得开心～' % (hit.get('title'), hit.get('day'), hit.get('time')), 'verify')
    audit(by_name, 'staff', '核销《%s》（码 %s）' % (hit.get('title'), code))
    return True, '核销成功：%s %s %s（%s 人）' % (hit.get('title'), hit.get('day'), hit.get('time'),
                                                hit.get('players')), hit
