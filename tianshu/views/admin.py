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


@bp.get('/scripts/export')
@staff_required
def scripts_export():
    """导出剧本库成 CSV —— Excel 能直接打开，改完再导回来"""
    import csv
    import io

    from flask import Response
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['id', 'title', 'emoji', 'tags', 'players', 'dur', 'diff', 'price', 'type',
                'onSale', 'allowRolePick', 'roles', 'desc'])
    for s in db.rows('scripts'):
        w.writerow([s.get('id'), s.get('title'), s.get('emoji'), '/'.join(s.get('tags') or []),
                    s.get('players'), s.get('dur'), s.get('diff'), s.get('price'), s.get('type'),
                    1 if s.get('onSale') is not False else 0,
                    1 if s.get('allowRolePick') else 0,
                    ','.join(r.get('name') for r in (s.get('roles') or [])), s.get('desc')])
    data = '\ufeff' + buf.getvalue()          # 前面这个 BOM 是给 Excel 看的，不然中文乱码
    return Response(data, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=scripts.csv'})


@bp.post('/scripts/import')
@staff_required
def scripts_import():
    """导入 CSV：填了 id 就更新那条，id 空着就当新本加进来

    一次录 20 个本不用一个个建；tags 用 / 或 , 分隔，roles 用逗号分隔。
    """
    import csv
    import io

    f = request.files.get('csv')
    if not f or not f.filename:
        flash('先选一个 CSV 文件（可以先用「导出」下一个当模板）', 'warn')
        return redirect(url_for('admin.scripts'))
    text = f.read().decode('utf-8-sig', 'replace')
    rows = db.rows('scripts')
    by_id = {str(s.get('id')): s for s in rows}
    next_id = max([int(s.get('id') or 0) for s in rows] or [0]) + 1
    added = updated = skipped = 0
    for raw in csv.DictReader(io.StringIO(text)):
        title = (raw.get('title') or '').strip()
        if not title:
            skipped += 1
            continue
        sid = (raw.get('id') or '').strip()
        rec = by_id.get(sid) if sid else None
        tags_raw = (raw.get('tags') or '').replace('，', '/').replace(',', '/')
        item = {
            'title': title, 'emoji': (raw.get('emoji') or '🎭').strip(),
            'tags': [t.strip() for t in tags_raw.split('/') if t.strip()],
            'players': (raw.get('players') or '6人').strip(),
            'dur': (raw.get('dur') or '约4小时').strip(),
            'diff': int(raw['diff']) if str(raw.get('diff') or '').strip().isdigit() else 3,
            'price': int(float(raw.get('price') or 128)),
            'type': (raw.get('type') or '盒装').strip(),
            'onSale': str(raw.get('onSale') or '1').strip() not in ('0', '否', 'false', 'False'),
            'allowRolePick': str(raw.get('allowRolePick') or '0').strip() in ('1', '是', 'true', 'True'),
            'roles': [{'name': n.strip(), 'img': ''} for n in (raw.get('roles') or '').replace('，', ',').split(',')
                      if n.strip()],
            'desc': (raw.get('desc') or '').strip(),
        }
        if rec:
            rec.update(item)
            updated += 1
        else:
            item['id'] = next_id
            next_id += 1
            rows.append(item)
            added += 1
    db.write('scripts', rows)
    business.audit(current_user().get('username'), role(),
                   '导入剧本 CSV：新增 %d、更新 %d' % (added, updated))
    flash('导入完成：新增 %d 个、更新 %d 个%s'
          % (added, updated, ('、跳过 %d 行（没填名字）' % skipped) if skipped else ''), 'ok')
    return redirect(url_for('admin.scripts'))


@bp.post('/scripts/<int:sid>/img')
@staff_required
def script_img(sid):
    """传剧本封面（建议 4:3，压到 300KB 以内，打开快）"""
    rows = db.rows('scripts')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这个剧本', 'warn')
        return redirect(url_for('admin.scripts'))
    url, err = business.save_upload(request.files.get('cover'), 'cover')
    if not url:
        flash('封面没传上：%s' % err, 'warn')
    else:
        hit['img'] = url
        db.write('scripts', rows)
        business.audit(current_user().get('username'), role(), '换了《%s》的封面' % hit.get('title'))
        flash('封面换好了（前台立刻能看到）', 'ok')
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
    if f.get('dmPayMode') in ('rate', 'fixed'):
        rows['dmPayMode'] = f.get('dmPayMode')
    for k in ('dmFee', 'depositRatio', 'freeCancelHours', 'lateCancelPenalty', 'dmRate', 'dmFixedPay'):
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


# ---------------------------------------------------------------- 排期（每天真正要用的）
@bp.get('/sessions')
@staff_required
def sessions():
    """一天的排期：新排一场、锁场、取消；同一房间同一时段排两场会被拦下来"""
    try:
        ts = int(request.args.get('ts') or business.midnight())
    except ValueError:
        ts = business.midnight()
    dms = [u for u in db.rows('users') if business.role_of(u) == 'dm']
    view = request.args.get('view') or 'day'
    week = []
    if view == 'week':                       # 周视图：一眼看整周，撞没撞房立刻看出来
        import time as _t
        wd = _t.localtime(ts / 1000).tm_wday                 # 0 = 周一
        monday = ts - wd * 86400000
        for i in range(7):
            d = monday + i * 86400000
            week.append({'ts': d, 'day': business.day_label(d), 'rows': business.sessions_of(d)})
    return render_template('admin/sessions.html', rows=business.sessions_of(ts), ts=ts, view=view,
                           prev=ts - 86400000, nxt=ts + 86400000, day=business.day_label(ts),
                           week=week, rooms=db.rows('rooms'), dms=dms,
                           scripts=[s for s in db.rows('scripts') if s.get('onSale') is not False])


@bp.post('/sessions/new')
@staff_required
def session_new():
    f = request.form
    ts = int(f.get('ts') or business.midnight())
    tm = str(f.get('time') or '19:00')
    room = business.clean(f.get('roomId'), 20)
    busy = business.room_busy(room, ts, tm)
    if busy:
        flash('撞房了：%s %s 的「%s」已经排了《%s》，换个房间或时间'
              % (business.day_label(ts), tm, room, busy.get('title')), 'warn')
        return redirect(url_for('admin.sessions', ts=ts))
    sc = db.one('scripts', id=f.get('sid'))
    dm_phone = business.clean(f.get('dm'), 20)
    dm = db.one('users', phone=dm_phone) if dm_phone else None
    rows = db.rows('sessions')
    rows.append({'id': max([int(x.get('id') or 0) for x in rows] or [0]) + 1,
                 'sid': (sc or {}).get('id'), 'title': (sc or {}).get('title') or '临时场',
                 'ts': ts, 'time': tm, 'roomId': room, 'cap': int(f.get('cap') or 6),
                 'dm': dm_phone, 'dmName': (dm or {}).get('username') or '',
                 'status': 'open', 'createdAt': business.now_ms()})
    db.write('sessions', rows)
    business.audit(current_user().get('username'), role(),
                   '排期：%s %s《%s》%s' % (business.day_label(ts), tm, rows[-1]['title'], room))
    flash('排好了：%s %s《%s》' % (business.day_label(ts), tm, rows[-1]['title']), 'ok')
    return redirect(url_for('admin.sessions', ts=ts))


@bp.post('/sessions/<int:sid>/status')
@staff_required
def session_status(sid):
    """改一场的状态：开放 / 锁场 / 取消 / 完成。取消会通知已报名的客人"""
    rows = db.rows('sessions')
    hit = next((s for s in rows if s.get('id') == sid), None)
    if not hit:
        flash('没这场', 'warn')
        return redirect(url_for('admin.sessions'))
    st = request.form.get('status') or 'open'
    if st == 'open':
        busy = business.room_busy(hit.get('roomId'), hit.get('ts'), hit.get('time'), skip_id=sid)
        if busy:
            flash('这间房那个时段已经排了《%s》，没法恢复开放' % busy.get('title'), 'warn')
            return redirect(url_for('admin.sessions', ts=hit.get('ts')))
    hit['status'] = st
    if request.form.get('reason'):
        hit['statusReason'] = business.clean(request.form.get('reason'), 60)
    db.write('sessions', rows)
    if st == 'cancelled':
        for b in db.rows('bookings'):
            if b.get('sessionId') == sid and b.get('status') == 'booked':
                business.notify(b.get('phone'), '场次变动',
                                '《%s》%s %s 这场被取消了（%s），想换时间跟我们说'
                                % (hit.get('title'), business.day_label(hit.get('ts')), hit.get('time'),
                                   hit.get('statusReason') or '门店原因'), 'session')
    business.audit(current_user().get('username'), role(),
                   '场次《%s》%s %s → %s' % (hit.get('title'), business.day_label(hit.get('ts')), hit.get('time'), st))
    flash('状态改成：%s' % st, 'ok')
    return redirect(url_for('admin.sessions', ts=hit.get('ts')))


@bp.post('/rooms/new')
@staff_required
def room_new():
    name = business.clean(request.form.get('name'), 20)
    if not name:
        flash('房间要有名字', 'warn')
    else:
        rows = db.rows('rooms')
        rows.append({'id': max([int(x.get('id') or 0) for x in rows] or [0]) + 1, 'name': name,
                     'cap': int(request.form.get('cap') or 6), 'dev': business.clean(request.form.get('dev'), 40)})
        db.write('rooms', rows)
        flash('加了房间：%s' % name, 'ok')
    return redirect(url_for('admin.sessions'))


@bp.post('/rooms/<int:rid>/del')
@staff_required
def room_del(rid):
    db.write('rooms', [r for r in db.rows('rooms') if r.get('id') != rid])
    flash('房间删了（已排的场次不受影响，但那些场次会显示空房间）', 'ok')
    return redirect(url_for('admin.sessions'))


# ---------------------------------------------------------------- 评价
@bp.get('/reviews')
@staff_required
def reviews():
    return render_template('admin/reviews.html', rows=business.reviews_of(only_visible=False))


@bp.post('/reviews/<int:rid>/reply')
@staff_required
def review_reply(rid):
    """门店回复：客人会收到通知（差评好好回，别删）"""
    text = business.clean(request.form.get('text'), 300)
    rows = db.rows('reviews')
    hit = next((r for r in rows if r.get('id') == rid), None)
    if not hit:
        flash('没这条评价', 'warn')
    else:
        hit['reply'] = text
        hit['repliedBy'] = current_user().get('username')
        hit['repliedAt'] = business.now_ms()
        db.write('reviews', rows)
        bk = next((b for b in db.rows('bookings') if b.get('id') == hit.get('bid')), None)
        if bk:
            business.notify(bk.get('phone'), '门店回复了你的评价',
                            '《%s》那条评价，店家说：%s' % (bk.get('title'), text), 'review')
        flash('回复已发出', 'ok')
    return redirect(url_for('admin.reviews'))


@bp.post('/reviews/<int:rid>/hide')
@staff_required
def review_hide(rid):
    rows = db.rows('reviews')
    for r in rows:
        if r.get('id') == rid:
            r['hidden'] = not r.get('hidden')
    db.write('reviews', rows)
    flash('已切换显示状态（隐藏的只有员工看得见）', 'ok')
    return redirect(url_for('admin.reviews'))


# ---------------------------------------------------------------- 店客留言 / 社区
@bp.get('/messages')
@staff_required
def messages():
    """客人留的言（没回的排前面）—— 晚到没车、想换时间、问价，基本都从这儿来"""
    rows = sorted(db.rows('messages'), key=lambda x: -(x.get('createdAt') or 0))
    status = request.args.get('status') or 'pending'
    if status != 'all':
        rows = [m for m in rows if (m.get('status') or 'pending') == status]
    return render_template('admin/messages.html', rows=rows, status=status,
                           counts={k: len([m for m in db.rows('messages') if (m.get('status') or 'pending') == k])
                                   for k in ('pending', 'replied')})


@bp.post('/messages/<int:mid>/reply')
@staff_required
def message_reply(mid):
    text = business.clean(request.form.get('text'), 300)
    rows = db.rows('messages')
    hit = next((m for m in rows if m.get('id') == mid), None)
    if not hit:
        flash('没这条留言', 'warn')
    else:
        hit.update(status='replied', reply=text, repliedBy=current_user().get('username'),
                   repliedAt=business.now_ms())
        db.write('messages', rows)
        business.notify(hit.get('phone'), '店家回复了你的留言',
                        '你问「%s」，店家回：%s' % (hit.get('text', '')[:18], text), 'msg')
        flash('回复已发出', 'ok')
    return redirect(url_for('admin.messages'))


@bp.post('/post/<int:pid>/del')
@staff_required
def post_del(pid):
    """删帖（广告、剧透不标注之类的）"""
    db.write('posts', [p for p in db.rows('posts') if p.get('id') != pid])
    business.audit(current_user().get('username'), role(), '删了社区帖 #%s' % pid)
    flash('帖子删了', 'ok')
    return redirect(url_for('public.comm'))


# ---------------------------------------------------------------- DM 结算
@bp.get('/dm')
@staff_required
def dm_page():
    """DM 结算：这个月每个 DM 分成多少（分成 = 营业额 × 比例，指定加价另算）"""
    month = request.args.get('month') or __import__('time').strftime('%Y-%m')
    return render_template('admin/dm.html', data=business.dm_settlement(month),
                           dms=[u for u in db.rows('users') if business.role_of(u) == 'dm'])


@bp.post('/dm/settle')
@staff_required
def dm_settle():
    """标记某人这个月已结清（只记标记，不碰钱）"""
    month = request.form.get('month')
    phone = request.form.get('dmPhone')
    rows = db.rows('settles')
    hit = next((x for x in rows if x.get('month') == month and str(x.get('dmPhone')) == str(phone)), None)
    if hit:
        hit['settled'] = request.form.get('undo') != '1'
        hit['settledAt'] = business.now_ms()
        hit['settledBy'] = current_user().get('username')
    else:
        rows.append({'id': business.now_ms(), 'month': month, 'dmPhone': phone, 'settled': True,
                     'settledAt': business.now_ms(), 'settledBy': current_user().get('username')})
    db.write('settles', rows)
    flash('已标记 %s 的 %s 月结算' % (phone, month), 'ok')
    return redirect(url_for('admin.dm_page', month=month))
