# -*- coding: utf-8 -*-
"""
客户相关页面：登录注册 / 我的（预约·订单·券·通知）/ 下单 / 付款退款 / 上车下车

登录用的是 Flask 的 session（签名 cookie），值只存手机号，
被拉黑的账号在下一次请求会被踢出去（见 security.current_user）。
"""
import re
import secrets

from flask import (Blueprint, flash, redirect, render_template, request, session, url_for)

from tianshu import business
from tianshu.db import db
from tianshu.security import (current_user, hash_password, login_required, rate, rate_clear,
                              rate_peek, verify_password)

bp = Blueprint('user', __name__)


# ---------------------------------------------------------------- 登录 / 注册
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr or 'local'
        ip_key = 'login:ip:' + ip
        if rate_peek(ip_key, 600000) >= 20:
            flash('同一网络失败太多次了，过 10 分钟再试', 'warn')
            return render_template('login.html'), 429
        acc = (request.form.get('account') or '').strip()
        pw = request.form.get('password') or ''
        acc_key = 'login:acc:%s:%s' % (ip, acc.lower())
        if rate_peek(acc_key, 600000) >= 8:
            flash('这个账号密码错了太多次，等 10 分钟，或者找前台重置', 'warn')
            return render_template('login.html'), 429

        u = db.one('users', phone=acc) or db.one('users', username=acc)
        if not u:
            rate(ip_key, 9999, 600000)
            rate(acc_key, 9999, 600000)
            flash('没找到这个账号', 'warn')
        elif u.get('banned'):
            flash('这个账号被限制使用了：%s' % (u.get('banReason') or '违反门店规矩'), 'warn')
        elif not verify_password(pw, u.get('password')):
            rate(ip_key, 9999, 600000)
            rate(acc_key, 9999, 600000)
            flash('密码不对', 'warn')
        else:
            # 老账号的弱哈希顺手升级掉（原来线上就是这么干的）
            if not str(u.get('password') or '').startswith('pbkdf2$'):
                users = db.rows('users')
                for x in users:
                    if str(x.get('phone')) == str(u.get('phone')):
                        x['password'] = hash_password(pw)
                db.write('users', users)
            rate_clear(ip_key, acc_key)
            session.permanent = True
            session['phone'] = u.get('phone')
            business.audit(u.get('username'), business.role_of(u), '登录')
            flash('欢迎回来，%s' % ((u.get('profile') or {}).get('nick') or u.get('username')), 'ok')
            return redirect(request.args.get('next') or url_for('public.home'))
    return render_template('login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        ip = request.remote_addr or 'local'
        # TODO 以后上线上，这里得加个人机验证，不然会被脚本注册刷爆
        if not rate('reg:' + ip, 12, 3600000):
            flash('注册太频繁了，歇一会儿再试', 'warn')
            return render_template('register.html'), 429
        phone = (request.form.get('phone') or '').strip()
        name = business.clean(request.form.get('username'), 20)
        pw = request.form.get('password') or ''
        invite = (request.form.get('invite') or '').strip().upper()
        if not re.match(r'^1\d{10}$', phone):
            flash('手机号要 11 位', 'warn')
        elif len(pw) < 6:
            flash('密码至少 6 位', 'warn')
        elif not name:
            flash('起个名字吧', 'warn')
        elif db.one('users', phone=phone):
            flash('这个手机号注册过了，直接登录', 'warn')
        elif db.one('users', username=name):
            flash('名字被占了，换一个', 'warn')
        else:
            my_invite = 'TS' + secrets.token_hex(3).upper()
            users = db.rows('users')
            users.append({'phone': phone, 'username': name, 'email': '', 'role': 'user', 'super': False,
                          'password': hash_password(pw), 'credit': 100, 'creditLogs': [],
                          'profile': {'avatar': '🎭', 'nick': name, 'gender': '', 'age': None},
                          'first': business.now_ms(), 'last': business.now_ms(),
                          'invite': my_invite, 'banned': False})
            db.write('users', users)
            # 填了邀请码：两个人各得一张 10 元券（拉新用）
            inviter = db.one('users', invite=invite) if invite else None
            if inviter:
                for who in ({'phone': phone}, inviter):
                    db.update('coupons', lambda rows: rows + [{
                        'id': business.now_ms() + secrets.randbelow(999),
                        'phone': who.get('phone'), 'amount': 10, 'minAmount': 0, 'used': False,
                        'exp': business.now_ms() + 90 * 86400000, 'from': '邀请返利'}])
                business.notify(inviter.get('phone'), '邀请成功 🎁',
                                '%s 用你的邀请码注册了，送你一张 10 元券' % name, 'coupon')
            session.permanent = True
            session['phone'] = phone
            flash('注册好了，你的邀请码是 %s（朋友用它注册，你俩各得一张券）' % my_invite, 'ok')
            return redirect(url_for('public.home'))
    return render_template('register.html')


@bp.get('/logout')
def logout():
    session.clear()
    flash('已退出', 'ok')
    return redirect(url_for('public.home'))


# ---------------------------------------------------------------- 我的
@bp.get('/me')
@login_required
def me():
    u = current_user()
    phone = str(u.get('phone'))
    bookings = sorted([b for b in db.rows('bookings') if str(b.get('phone')) == phone],
                      key=lambda x: -(x.get('id') or 0))
    orders = sorted([o for o in db.rows('pays') if str(o.get('phone')) == phone],
                    key=lambda x: -(x.get('id') or 0))
    coupons = [c for c in db.rows('coupons')
               if c.get('all') or str(c.get('phone')) == phone]
    order_of = {o.get('bid'): o for o in orders}
    fav_ids = set()
    for r in db.rows('favs'):
        if str(r.get('phone')) == phone:
            fav_ids = {str(x) for x in r.get('sids') or []}
    return render_template('me.html', u=u, bookings=bookings, orders=orders,
                           coupons=coupons, notices=business.my_notices(u, 20),
                           order_of=order_of, scripts=db.rows('scripts'), fav_ids=fav_ids,
                           reviewed={r.get('bid') for r in db.rows('reviews')},
                           msgs=business.my_messages(u))


@bp.post('/profile')
@login_required
def profile_save():
    """改资料：昵称 / 性别 / 年龄 + 传头像。拼车时别人看到的就是这些"""
    u = current_user()
    f = request.form
    users = db.rows('users')
    hit = next((x for x in users if str(x.get('phone')) == str(u.get('phone'))), None)
    if not hit:
        flash('账号不见了？', 'warn')
        return redirect(url_for('user.me'))
    prof = hit.get('profile') or {}
    if f.get('nick') is not None:
        prof['nick'] = business.clean(f.get('nick'), 16)
    if f.get('gender') in ('男', '女', ''):
        prof['gender'] = f.get('gender')
    if f.get('age'):
        try:
            prof['age'] = max(0, min(99, int(f.get('age'))))
        except ValueError:
            pass
    url, err = business.save_upload(request.files.get('avatar'), 'avatar')
    if url:
        prof['avatar'] = url
    elif err and request.files.get('avatar') and request.files['avatar'].filename:
        flash('头像没传上：%s' % err, 'warn')
    hit['profile'] = prof
    db.write('users', users)
    flash('资料存好了', 'ok')
    return redirect(url_for('user.me'))


@bp.post('/msg')
@login_required
def msg_create():
    """给店家留言：晚了没车、想改时间、对 DM 有要求…… 都能说（店家看到会回）"""
    text = business.clean(request.form.get('text'), 500)
    if not text:
        flash('写点内容再发', 'warn')
    else:
        u = current_user()
        db.update('messages', lambda rows: rows + [{
            'id': business.now_ms(), 'phone': u.get('phone'), 'username': u.get('username'),
            'cat': business.clean(request.form.get('cat'), 10) or '💡 建议', 'text': text,
            'status': 'pending', 'reply': '', 'createdAt': business.now_ms()}])
        business.audit(u.get('username'), business.role_of(u), '给门店留言')
        flash('留言发出去了，店家看到会回你', 'ok')
    return redirect(url_for('user.me'))


@bp.post('/review/<int:bid>')
@login_required
def review(bid):
    """写评价：得到店开本之后（status 变成 arrived/done），一条预约只能评一次"""
    u = current_user()
    bk = next((b for b in db.rows('bookings') if b.get('id') == bid
               and str(b.get('phone')) == str(u.get('phone'))), None)
    if not bk:
        flash('没找到这条预约', 'warn')
    elif bk.get('status') not in ('arrived', 'done'):
        flash('到店开本之后再来评价哈', 'warn')
    elif any(r.get('bid') == bid for r in db.rows('reviews')):
        flash('这条已经评过了', 'warn')
    else:
        anon = request.form.get('anonymous') == '1'
        db.update('reviews', lambda rows: rows + [{
            'id': business.now_ms(), 'sid': bk.get('sid'), 'bid': bid,
            'dmPhone': bk.get('dmPhone') or '',
            'rating': max(1, min(5, int(request.form.get('rating') or 5))),
            'text': business.clean(request.form.get('text'), 800),
            'username': '匿名玩家' if anon else u.get('username'), 'anonymous': anon,
            'dims': {}, 'reply': '', 'likes': [], 'hidden': False, 'createdAt': business.now_ms()}])
        business.notify(u.get('phone'), '评价已提交，谢谢！',
                        '《%s》的评价收到了，欢迎下次再来' % bk.get('title'), 'review')
        flash('评价收到了，谢谢！', 'ok')
    return redirect(url_for('user.me'))


@bp.post('/book')
@login_required
def book():
    """下单：只收"意向"，价格和校验都在 business.create_booking 里做"""
    u = current_user()
    ok, msg, booking = business.create_booking(u, request.form)
    flash(msg, 'ok' if ok else 'warn')
    if ok:
        return redirect(url_for('user.me'))
    sid = request.form.get('sid')
    return redirect(url_for('public.script_detail', sid=sid) if sid else url_for('public.scripts'))


@bp.post('/booking/<int:bid>/cancel')
@login_required
def cancel_booking(bid):
    u = current_user()
    rows = db.rows('bookings')
    hit = next((b for b in rows if b.get('id') == bid and str(b.get('phone')) == str(u.get('phone'))), None)
    if not hit:
        flash('没找到这条预约', 'warn')
    else:
        hit.update(status='cancelled', cancelAt=business.now_ms(), cancelBy='user')
        db.write('bookings', rows)
        db.update('pays', lambda r: [dict(o, status='closed') if (o.get('bid') == bid and o.get('status') == 'unpaid')
                                     else o for o in r])
        flash('已取消这条预约', 'ok')
    return redirect(url_for('user.me'))


@bp.post('/order/<int:oid>/<action>')
@login_required
def order_act(oid, action):
    ok, msg = business.order_action(current_user(), oid, action)
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('user.me'))


@bp.post('/notice/read')
@login_required
def notice_read():
    business.mark_read(current_user())
    flash('通知都标成已读了', 'ok')
    return redirect(url_for('user.me'))


# ---------------------------------------------------------------- 拼车动作
@bp.post('/car/<int:cid>/<action>')
@login_required
def car_act(cid, action):
    ok, msg = business.car_action(current_user(), cid, action)
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('public.car'))
