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
from config import IMG_DIR, MAX_IMG_BYTES, WEEK

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


def role_of(u):
    if not u:
        return 'guest'
    return 'super' if (u.get('super') is True or u.get('role') == 'super') else (u.get('role') or 'user')


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
        a['settled'] = any(str(x.get('dmPhone')) == phone and x.get('month') == month and x.get('settled')
                           for x in settles)
        rows.append(a)
    return {'month': month, 'rows': sorted(rows, key=lambda x: -x['total'])}


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

    ts = int(form.get('ts') or 0)
    tm = str(form.get('time') or '19:00')
    if not ts:
        return False, '请选择日期', None
    lo, hi = player_range(sc)
    players = max(1, min(hi, int(form.get('players') or lo)))
    mode = '包车' if form.get('mode') == '包车' else '拼车'
    bookings = db.rows('bookings')

    # ① 已排场次的话，先看还有没有位子（防超卖）
    ses = next((x for x in db.rows('sessions') if str(x.get('sid')) == str(sc.get('id'))
                and x.get('ts') == ts and x.get('time') == tm and x.get('status') == 'open'), None)
    session_id = 0
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

    # ④ 算钱。定金四舍五入取整，别给客人报 229.6 这种数字
    price = float(sc.get('price') or 0) + (float(st['dmFee']) if form.get('dmPhone') else 0)
    amount = round(price * players)
    deposit = round(amount * float(st['depositRatio']))
    if coupon:
        deposit = max(0, deposit - int(coupon.get('amount') or 0))

    # ⑤ 会员余额抵扣：充过钱的客人可以直接用余额顶定金（顶完剩下的才需要付现）
    used = 0
    if str(form.get('use_balance') or '') in ('1', 'on', 'true') and int(user.get('balance') or 0) > 0:
        used = min(int(user.get('balance') or 0), deposit)

    bid = now_ms() + secrets.randbelow(90)
    booking = {'id': bid, 'phone': user.get('phone'), 'username': user.get('username'),
               'sid': sc.get('id'), 'title': sc.get('title'), 'emoji': sc.get('emoji') or '🎭',
               'day': day_label(ts), 'ts': ts, 'time': tm, 'players': players,
               'price': price, 'amount': amount, 'status': 'booked', 'mode': mode,
               'carNew': mode == '拼车', 'carOwner': user.get('username') if mode == '拼车' else None,
               'carCap': hi, 'carMin': min(lo, players), 'carTags': [], 'reserved': 0,
               'sessionId': session_id, 'dmPhone': clean(form.get('dmPhone'), 20), 'role': role,
               'verifyCode': '%06d' % secrets.randbelow(1000000),      # 到店报这个码核销
               'deposit': deposit, 'balanceUsed': used, 'createdAt': now_ms()}
    order = {'id': bid + 1, 'bid': bid, 'phone': user.get('phone'), 'username': user.get('username'),
             'title': sc.get('title'), 'day': booking['day'], 'ts': ts, 'time': tm, 'players': players,
             'amount': amount, 'deposit': deposit, 'balanceUsed': used, 'payable': deposit - used,
             'status': 'unpaid', 'createdAt': now_ms(),
             'couponId': coupon.get('id') if coupon else 0, 'paidAt': 0, 'refundAt': 0}

    db.update('bookings', lambda rows: rows + [booking])
    db.update('pays', lambda rows: rows + [order])
    if used:
        adjust_balance(user.get('phone'), -used, '抵扣《%s》%s 的定金' % (sc.get('title'), booking['day']),
                       user.get('username'))
    if coupon:
        db.update('coupons', lambda rows: [dict(c, used=True, usedAt=now_ms()) if str(c.get('id')) == cid else c
                                           for c in rows])
    notify(user.get('phone'), '预约成功，等付定金',
           '《%s》%s %s 先给你留着位置了，定金 ¥%d，到店报核销码 %s。'
           % (sc.get('title'), booking['day'], tm, deposit, booking['verifyCode']), 'booking')
    audit(user.get('username'), role_of(user), '预约《%s》%s %s' % (sc.get('title'), booking['day'], tm))
    return True, '预约成功！定金 ¥%d，到店报核销码 %s' % (deposit, booking['verifyCode']), booking


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

    if action == 'pay':
        if order.get('status') != 'unpaid':
            return False, '这个订单现在付不了'
        order.update(status='paid', paidAt=now_ms(), tradeNo='LOCAL%d' % now_ms())
        db.write('pays', pays)
        notify(order.get('phone'), '定金已付 ✅',
               '《%s》%s %s 的定金 ¥%d 收到了，到时候见～' % (order.get('title'), order.get('day'),
                                                          order.get('time'), order.get('deposit')), 'pay')
        return True, '定金已记录（本地版没有真实支付，先按已付处理）'

    if action == 'refund':
        if order.get('status') not in ('paid', 'unpaid'):
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
        bookings.append({'id': now_ms(), 'phone': phone, 'username': name, 'sid': ob.get('sid'),
                         'title': ob.get('title'), 'emoji': ob.get('emoji'), 'day': ob.get('day'),
                         'ts': ob.get('ts'), 'time': ob.get('time'), 'players': 1, 'price': ob.get('price'),
                         'amount': ob.get('price'), 'deposit': 0, 'status': 'booked', 'mode': '拼车',
                         'carNew': False, 'carOwner': ob.get('username'), 'sessionId': ob.get('sessionId') or 0,
                         'dmPhone': '', 'role': '', 'verifyCode': '', 'createdAt': now_ms()})
        db.write('bookings', bookings)
        notify(ob.get('phone'), '有人上你的车了',
               '%s 加入了《%s》%s %s 这车。' % (name, ob.get('title'), ob.get('day'), ob.get('time')), 'car')
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
