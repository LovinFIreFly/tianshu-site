# -*- coding: utf-8 -*-
"""
员工后台：核销、预约管理、客户（信用分/拉黑/充值/发券）、剧本、订单、设置、日志

权限靠 staff_required（管理员和超管能进；DM 也能看一部分，按需再加）。
后台是"破坏性操作"最多的地方：拉黑、清数据、改价 —— 改这儿的东西动手前想一下。
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, is_staff, role, staff_required

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.get('/')
@staff_required
def dashboard():
    """概览：今天几场、多少人、收了多少钱、有没有待核销的"""
    bookings = db.rows('bookings')
    st = business.stats()
    today0 = business.day_label(business.now_ms())
    return render_template('admin/dashboard.html',
                           stat=st, sessions=business.today_sessions(),
                           pending=[b for b in bookings if b.get('status') == 'booked'
                                    and b.get('day') == today0][:10],
                           recent=sorted(bookings, key=lambda x: -(x.get('id') or 0))[:8],
                           logs=db.rows('logs')[:6],
                           users=db.rows('users'), scripts=db.rows('scripts'))


@bp.post('/verify')
@staff_required
def verify():
    """到店核销：客人报 6 位码，前台在这儿输一下"""
    ok, msg, _b = business.verify_checkin(request.form.get('code'), current_user().get('username'))
    flash(msg, 'ok' if ok else 'warn')
    return redirect(request.referrer or url_for('admin.dashboard'))


@bp.get('/bookings')
@staff_required
def bookings():
    """预约管理：按状态/日期筛，能代客户取消、能核销"""
    rows = db.rows('bookings')
    status = request.args.get('status') or 'booked'
    kw = (request.args.get('q') or '').strip()
    if status != 'all':
        rows = [b for b in rows if b.get('status') == status]
    if kw:
        rows = [b for b in rows if kw in str(b.get('title', '')) or kw in str(b.get('username', ''))
                or kw in str(b.get('phone', '')) or kw in str(b.get('verifyCode', ''))]
    rows = sorted(rows, key=lambda x: (-(x.get('ts') or 0), str(x.get('time'))))
    return render_template('admin/bookings.html', rows=rows, status=status, q=kw,
                           counts={s: len([b for b in db.rows('bookings') if b.get('status') == s])
                                   for s in ('booked', 'arrived', 'done', 'cancelled')})


@bp.post('/bookings/<int:bid>/cancel')
@staff_required
def cancel_booking(bid):
    """店里原因取消（退款按规则走 business.order_action）"""
    rows = db.rows('bookings')
    hit = next((b for b in rows if b.get('id') == bid), None)
    if not hit:
        flash('没这条预约', 'warn')
        return redirect(url_for('admin.bookings'))
    hit.update(status='cancelled', cancelAt=business.now_ms(), cancelBy='staff')
    db.write('bookings', rows)
    order = next((o for o in db.rows('pays') if o.get('bid') == bid), None)
    if order:
        business.order_action(current_user(), order.get('id'), 'refund', is_staff=True)
    business.audit(current_user().get('username'), role(), '店员取消了《%s》%s 的预约'
                   % (hit.get('title'), hit.get('day')))
    flash('已取消并处理退款', 'ok')
    return redirect(url_for('admin.bookings'))


@bp.get('/users')
@staff_required
def users():
    """客户档案：信用分、消费、是否拉黑（点开能改）"""
    kw = (request.args.get('q') or '').strip()
    bookings = db.rows('bookings')
    rows = []
    for u in db.rows('users'):
        if business.role_of(u) != 'user':
            continue                      # 员工账号不在客户名单里
        if kw and kw not in str(u.get('username')) and kw not in str(u.get('phone')):
            continue
        mine = [b for b in bookings if str(b.get('phone')) == str(u.get('phone')) and b.get('status') != 'cancelled']
        rows.append({'u': u, 'visits': len(mine), 'spent': sum(int(b.get('amount') or 0) for b in mine),
                     'last': max([b.get('createdAt') or 0 for b in mine] or [0])})
    rows.sort(key=lambda x: -x['visits'])
    return render_template('admin/users.html', rows=rows, q=kw)


@bp.post('/users/<phone>/credit')
@staff_required
def set_credit(phone):
    delta = int(request.form.get('delta') or 0)
    reason = business.clean(request.form.get('reason'), 40) or '门店调整'
    before, after = business.adjust_credit(phone, delta, reason, current_user().get('username'))
    flash('信用分 %s → %s（原因：%s）' % (before, after, reason) if before is not None else '没这个账号',
          'ok' if before is not None else 'warn')
    return redirect(url_for('admin.users'))


@bp.post('/users/<phone>/ban')
@staff_required
def ban(phone):
    users_rows = db.rows('users')
    hit = next((u for u in users_rows if str(u.get('phone')) == str(phone)), None)
    if not hit:
        flash('没这个账号', 'warn')
    elif hit.get('super') is True:
        flash('超管不能拉黑（自己把自己关门外就麻烦了）', 'warn')
    else:
        banned = not hit.get('banned')
        hit['banned'] = banned
        hit['banReason'] = business.clean(request.form.get('reason'), 60) if banned else ''
        db.write('users', users_rows)
        business.audit(current_user().get('username'), role(),
                       ('拉黑' if banned else '恢复') + '了 ' + str(hit.get('username')))
        flash('已拉黑该账号' if banned else '已恢复该账号', 'ok')
    return redirect(url_for('admin.users'))


@bp.post('/users/<phone>/recharge')
@staff_required
def recharge(phone):
    """会员充值（余额记在账号上，以后下单可以抵扣）"""
    amount = int(request.form.get('amount') or 0)
    rows = db.rows('users')
    hit = next((u for u in rows if str(u.get('phone')) == str(phone)), None)
    if not hit or not amount:
        flash('账号或金额不对', 'warn')
    else:
        before = int(hit.get('balance') or 0)
        hit['balance'] = before + amount
        logs = hit.get('walletLogs') or []
        logs.insert(0, {'at': business.now_ms(), 'delta': amount, 'by': current_user().get('username'),
                        'note': business.clean(request.form.get('note'), 40)})
        hit['walletLogs'] = logs[:50]
        db.write('users', rows)
        business.notify(phone, '会员余额变动 💳', '充值 ¥%d，当前余额 ¥%d' % (amount, hit['balance']), 'wallet')
        flash('充值成功：¥%d → ¥%d' % (before, hit['balance']), 'ok')
    return redirect(url_for('admin.users'))


@bp.post('/coupon')
@staff_required
def coupon():
    """发券：默认发给"好久没来"的客人（sleepDays 天没消费），也可以选全员"""
    scope = request.form.get('scope') or 'sleeping'
    amount = int(request.form.get('amount') or 20)
    days = int(request.form.get('days') or 30)
    sleep_days = int(request.form.get('sleepDays') or 30)
    cut = business.now_ms() - sleep_days * 86400000
    bookings = db.rows('bookings')
    picked = []
    for u in db.rows('users'):
        if business.role_of(u) != 'user':
            continue
        if scope == 'all':
            picked.append(u)
            continue
        last = max([b.get('createdAt') or 0 for b in bookings if str(b.get('phone')) == str(u.get('phone'))]
                   or [u.get('first') or 0])
        if last < cut:
            picked.append(u)
    for u in picked:
        db.update('coupons', lambda rows: rows + [{
            'id': business.now_ms() + len(picked), 'phone': u.get('phone'), 'amount': amount,
            'minAmount': 0, 'used': False, 'from': '门店回访',
            'exp': business.now_ms() + days * 86400000}])
        business.notify(u.get('phone'), '送你一张券 🎁',
                        '好久不见，送你 %d 元定金抵扣券（%d 天内有效）' % (amount, days), 'coupon')
    flash('发出 %d 张券' % len(picked) if picked else '没有符合条件的客人', 'ok' if picked else 'warn')
    return redirect(url_for('admin.dashboard'))


@bp.get('/scripts')
@staff_required
def scripts():
    """剧本管理：改价、上下架、角色、是否允许客人提前选角"""
    return render_template('admin/scripts.html', rows=db.rows('scripts'))


@bp.post('/scripts/new')
@staff_required
def script_new():
    """加一个新剧本：页面上填个名字就能建，细节建完再改（列表最下面那个）"""
    rows = db.rows('scripts')
    new_id = max([int(s.get('id') or 0) for s in rows] or [0]) + 1
    rows.append({'id': new_id, 'title': business.clean(request.form.get('title'), 30) or '新剧本',
                 'emoji': business.clean(request.form.get('emoji'), 4) or '🎭', 'tags': [],
                 'players': '6人', 'dur': '约4小时', 'diff': 3,
                 'price': int(request.form.get('price') or 128), 'desc': '',
                 'type': '盒装', 'stock': '在库', 'onSale': True, 'allowRolePick': False,
                 'roles': [], 'dms': [], 'hot': False, 'isNew': True, 'createdAt': business.now_ms()})
    db.write('scripts', rows)
    business.audit(current_user().get('username'), role(), '新增剧本《%s》' % rows[-1]['title'])
    flash('《%s》建好了，下面填细节' % rows[-1]['title'], 'ok')
    return redirect(url_for('admin.scripts'))


@bp.post('/scripts/<int:sid>/save')
@staff_required
def script_save(sid):
    rows = db.rows('scripts')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这个剧本', 'warn')
        return redirect(url_for('admin.scripts'))
    f = request.form
    if f.get('title'):
        hit['title'] = business.clean(f.get('title'), 30)
    if f.get('price'):
        hit['price'] = int(f.get('price'))
    hit['onSale'] = f.get('onSale') == '1'
    hit['allowRolePick'] = f.get('allowRolePick') == '1'      # 开了客人才能在网页上选角色
    if f.get('players'):
        hit['players'] = business.clean(f.get('players'), 12)
    if f.get('desc') is not None:
        hit['desc'] = business.clean(f.get('desc'), 200)
    if f.get('roles') is not None:
        names = [x.strip() for x in str(f.get('roles')).replace('，', ',').split(',') if x.strip()]
        old = {r.get('name'): r for r in hit.get('roles') or []}
        hit['roles'] = [old.get(n, {'name': n, 'img': ''}) for n in names]
    db.write('scripts', rows)
    business.audit(current_user().get('username'), role(), '改了剧本《%s》' % hit.get('title'))
    flash('《%s》存好了' % hit.get('title'), 'ok')
    return redirect(url_for('admin.scripts'))


@bp.get('/orders')
@staff_required
def orders():
    """订单 + 日结：一天卖了多少、退了多少"""
    rows = sorted(db.rows('pays'), key=lambda x: -(x.get('id') or 0))
    status = request.args.get('status') or 'all'
    if status != 'all':
        rows = [o for o in rows if o.get('status') == status]
    by_day = {}
    for o in db.rows('pays'):
        if o.get('status') == 'paid':
            d = o.get('day') or '未知'
            by_day[d] = by_day.get(d, 0) + int(o.get('deposit') or 0)
    return render_template('admin/orders.html', rows=rows, status=status,
                           by_day=sorted(by_day.items(), key=lambda kv: kv[0], reverse=True)[:14])


@bp.post('/settings')
@staff_required
def settings():
    """经营参数：改完立刻生效（存在 data/settings.json，也可以直接改那个文件）"""
    rows = db.read('settings') or {}
    f = request.form
    for k in ('shopName', 'notice'):
        if f.get(k) is not None:
            rows[k] = business.clean(f.get(k), 80)
    for k in ('dmFee', 'depositRatio', 'freeCancelHours', 'lateCancelPenalty', 'dmRate'):
        if f.get(k):
            try:
                rows[k] = float(f.get(k))
            except ValueError:
                pass
    rows['carTags'] = [t.strip() for t in (f.get('carTags') or '').replace('，', ',').split(',') if t.strip()][:6] \
        if f.get('carTags') is not None else rows.get('carTags', [])
    db.write('settings', rows)
    business.audit(current_user().get('username'), role(), '改了门店设置')
    flash('设置已保存（立刻生效）', 'ok')
    return redirect(url_for('admin.dashboard'))


@bp.get('/logs')
@staff_required
def logs():
    return render_template('admin/logs.html', rows=db.rows('logs')[:200])
