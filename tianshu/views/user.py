# -*- coding: utf-8 -*-
"""
客户相关页面：登录注册 / 我的（预约·订单·券·通知）/ 下单 / 付款退款 / 上车下车

登录用的是 Flask 的 session（签名 cookie），值只存手机号，
被拉黑的账号在下一次请求会被踢出去（见 security.current_user）。
"""
import re
import secrets

from flask import (Blueprint, flash, jsonify, redirect, render_template, request, session, url_for)

from tianshu import business
from tianshu.db import db
from tianshu.security import (current_user, hash_password, is_staff, login_required, rate,
                              rate_clear, rate_peek, verify_password)

bp = Blueprint('user', __name__)


def next_days(n=7):
    """从明天起 n 天的可选日期（改期用；今天不算，来不及）"""
    import time as _t
    out = []
    for i in range(1, n + 1):
        d = _t.localtime(_t.time() + i * 86400)
        ts = int(_t.mktime(_t.strptime(_t.strftime('%Y-%m-%d', d), '%Y-%m-%d'))) * 1000
        out.append({'ts': ts, 'label': business.day_label(ts)})
    return out


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
            # 「记住我」勾着 = 半年不用再登（config.SESSION_DAYS）。
            # 没勾（表单里只有那个 hidden 的 0）= 只在这次浏览器会话里有效，关掉就要重登。
            # 老客户端/自检脚本不带这个字段，按"记住"处理，免得把它们的登录判成临时会话。
            session.permanent = ('1' in request.form.getlist('remember')) or ('remember' not in request.form)
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
        # 跟老版一样：手机号 + 验证码 + 两次密码 + 同意协议，才给建号
        f = request.form
        phone = (f.get('phone') or '').strip()
        email = (f.get('email') or '').strip()
        code = (f.get('code') or '').strip()
        name = business.clean(f.get('username'), 20)
        pw = f.get('password') or ''
        pw2 = f.get('password2') or ''
        invite = (f.get('invite') or '').strip().upper()
        if not re.match(r'^1\d{10}$', phone):
            flash('手机号要 11 位', 'warn')
        elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash('要填个邮箱，验证码发到邮箱里（手机号只当账号用）', 'warn')
        elif len(pw) < 6:
            flash('密码至少 6 位', 'warn')
        elif pw != pw2:
            flash('两次输入的密码不一样', 'warn')
        elif not name:
            flash('起个名字吧', 'warn')
        elif f.get('agree') != '1':
            flash('要先同意《用户协议》才能注册', 'warn')
        elif db.one('users', phone=phone):
            flash('这个手机号注册过了，直接登录', 'warn')
        elif db.one('users', username=name):
            flash('名字被占了，换一个', 'warn')
        elif not business.use_code(email, 'register', code):
            flash('验证码不对（本地测试可以直接填 1234）', 'warn')
        else:
            my_invite = 'TS' + secrets.token_hex(3).upper()
            users = db.rows('users')
            users.append({'phone': phone, 'username': name, 'email': email, 'role': 'user', 'super': False,
                          'password': hash_password(pw), 'credit': 100, 'creditLogs': [],
                          'profile': {'avatar': '🎭', 'nick': name, 'gender': '', 'age': None},
                          'first': business.now_ms(), 'last': business.now_ms(),
                          'invite': my_invite, 'banned': False})
            db.write('users', users)
            # 填了邀请码：双方各得一张抵扣券（金额在「门店设置 → 邀请返利券金额」里改，默认 10 元）
            inviter = db.one('users', invite=invite) if invite else None
            invite_amount = int(business.get_settings().get('inviteCoupon') or 10)
            if inviter:
                for who in ({'phone': phone}, inviter):
                    db.update('coupons', lambda rows: rows + [{
                        'id': business.now_ms() + secrets.randbelow(999),
                        'phone': who.get('phone'), 'amount': invite_amount, 'minAmount': 0, 'used': False,
                        'exp': business.now_ms() + 90 * 86400000, 'from': '邀请返利'}])
                business.notify(inviter.get('phone'), '邀请成功 🎁',
                                '%s 用你的邀请码注册了，送你一张 %s 元抵扣券' % (name, invite_amount), 'coupon')
                business.audit(name, 'user', '用 %s 的邀请码注册，双方各得 %s 元券'
                               % (inviter.get('username'), invite_amount))
            session.permanent = True
            session['phone'] = phone
            flash('注册好了，你的邀请码是 %s（朋友用它注册，你俩各得一张 %s 元券）'
                  % (my_invite, invite_amount), 'ok')
            return redirect(url_for('public.home'))
    return render_template('register.html')


@bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    """忘了密码：手机号 + 验证码 → 重设一个（不用登录）"""
    if request.method == 'POST':
        phone = (request.form.get('phone') or '').strip()
        code = (request.form.get('code') or '').strip()
        pw = request.form.get('password') or ''
        pw2 = request.form.get('password2') or ''
        email_ = (request.form.get('email') or '').strip().lower()
        u = db.one('users', phone=phone)
        if not u:
            flash('这个手机号还没注册过', 'warn')
        elif not email_ or email_ != str(u.get('email') or '').strip().lower():
            # 邮箱必须和注册时留的一致，不然验证码发不到本人手里（也就没有验证的意义）
            flash('邮箱和注册时填的不一样 —— 验证码只发注册邮箱，忘了请联系门店', 'warn')
        elif not business.use_code(email_, 'reset', code):
            flash('验证码不对（本地自己测试可以直接填 1234）', 'warn')
        elif len(pw) < 6:
            flash('新密码至少 6 位', 'warn')
        elif pw != pw2:
            flash('两次输入的密码不一样', 'warn')
        else:
            users = db.rows('users')
            for x in users:
                if str(x.get('phone')) == str(phone):
                    x['password'] = hash_password(pw)
            db.write('users', users)
            business.audit(u.get('username'), business.role_of(u), '用「找回密码」重设了密码')
            flash('密码重设好了，去登录吧', 'ok')
            return redirect(url_for('user.login'))
    return render_template('forgot.html')


@bp.post('/code/send')
def code_send():
    """要一个验证码 —— 只认邮箱（咱们没有短信通道，手机号收不到码）。

    配了发信邮箱（后台「门店设置 → 验证码发信」）就真发邮件；
    没配（比如店家自己在电脑上跑）就打进运行服务的黑窗口，方便本机测试。
    """
    email = (request.form.get('email') or '').strip()
    purpose = request.form.get('purpose') or 'reset'
    ok, msg = True, ''
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        ok, msg = False, '先填个有效的邮箱，验证码是发到邮箱的'
    else:
        code, sent, err = business.send_code(email, purpose)
        if code is None:                       # 被限频了（60 秒一次 / 每天 10 次）
            ok, msg = False, (err or '要码太频繁了，等一会儿再试')
        elif sent:
            ok, msg = True, '验证码已发到 %s，5 分钟内有效（收不到就翻翻垃圾邮件箱）' % email
        elif business.is_dev_request():
            ok, msg = True, '验证码已生成：去看运行服务的那个黑窗口（本机测试也可以直接填 1234）'
        else:
            ok, msg = False, '店里的发信通道还没配好，邮件发不出去（%s）—— 请先联系门店' % (err or '未配置')
    # 页面上那颗「获取验证码」是 fetch 调的：回 JSON，**不刷页面** ——
    # 刷页面会把用户已经填好的密码冲掉，还得重填一遍（以前就是这么难用）。
    if (request.headers.get('X-Requested-With') or '') == 'fetch':
        return jsonify(ok=ok, msg=msg)
    flash(msg, 'ok' if ok else 'warn')
    return redirect(request.referrer or url_for('user.me'))


# ---------------------------------------------------------------- 账号安全
@bp.post('/account/pwd')
@login_required
def account_pwd():
    ok, msg = business.change_password(current_user(), request.form.get('old'), request.form.get('password'))
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('user.me'))


# 换绑手机号的路由删了（2026-09）：只有邮箱验证码，没法确认新号是本人的。
# 前端的入口也一起删了，留着这个注释是怕以后有人翻旧代码找不到。


@bp.post('/account/delete')
@login_required
def account_delete():
    """注销：必须输入自己的手机号才算确认（防手滑，这一步不可逆）"""
    u = current_user()
    if (request.form.get('confirm') or '').strip() != str(u.get('phone')):
        flash('要原样输入自己的手机号才算确认', 'warn')
        return redirect(url_for('user.me'))
    ok, msg = business.delete_account(u)
    session.clear()
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('public.home'))


@bp.post('/booking/<int:bid>/reschedule')
@login_required
def reschedule(bid):
    """改期：换个日期/时间，定金保留"""
    ok, msg = business.reschedule(current_user(), bid, request.form.get('ts'), request.form.get('time'))
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('user.me'))


@bp.get('/logout')
def logout():
    session.clear()
    flash('已退出', 'ok')
    return redirect(url_for('public.home'))


# ---------------------------------------------------------------- 我的
@bp.get('/me')
@login_required
def me():
    u = business.ensure_invite(current_user())      # 老账号没邀请码的话，这里补一个
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
    # 侧栏那三格里显示"已付定金"，代替原来的余额（余额功能先撤了）
    spent = sum(int(o.get('deposit') or 0) for o in orders if o.get('status') == 'paid')
    # 我自己的评价（按预约 id 索引）：订单卡片里要把它摆出来 ——
    # 只显示一个「已评价」太没交代，客人想看自己当时写了什么。
    # 评价记录里没存手机号，但 bid 就是这条预约，而一条预约只有本人能评，
    # 所以用「我的预约 id」反查最稳。
    _mybids = {str(b.get('id')) for b in bookings}
    _revs = db.rows('reviews')
    my_reviews = {str(r.get('bid')): r for r in _revs if str(r.get('bid')) in _mybids}
    return render_template('me.html', u=u, bookings=bookings, orders=orders,
                           coupons=coupons, notices=business.my_notices(u, 20), spent=spent,
                           order_of=order_of, scripts=db.rows('scripts'), fav_ids=fav_ids,
                           reviewed={r.get('bid') for r in _revs},
                           my_reviews=my_reviews,
                           msgs=business.my_messages(u), days=next_days(7))


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
        # 四个细分维度（老版本就有）：剧情 / DM / 氛围 / 房间，各 1-5 分
        dims = {}
        for key, label in (('plot', '剧情'), ('dm', 'DM'), ('vibe', '氛围'), ('room', '房间')):
            v = int(request.form.get(key) or 0)
            if 1 <= v <= 5:
                dims[label] = v
        db.update('reviews', lambda rows: rows + [{
            'id': business.now_ms(), 'sid': bk.get('sid'), 'bid': bid,
            'dmPhone': bk.get('dmPhone') or '',
            'rating': max(1, min(5, int(request.form.get('rating') or 5))),
            'text': business.clean(request.form.get('text'), 800),
            'username': '匿名玩家' if anon else u.get('username'), 'anonymous': anon,
            'dims': dims, 'reply': '', 'likes': [], 'hidden': False, 'createdAt': business.now_ms()}])
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


@bp.get('/me/pay/<int:oid>')
@login_required
def pay_deposit(oid):
    """支付定金那一页：上面是小客服微信，下面一颗「我已完成支付」。

    为什么不做在线支付：本地版没有支付通道，店里收定金的实际做法就是加小客服微信转账。
    点「完成」只是把单子标成"待小客服确认"（claimed）—— 核销码要等管理员在「订单」页
    点「确认支付定金」之后才给客人看，这样码不会在钱没到之前就流出去。
    """
    u = current_user()
    o = next((x for x in db.rows('pays') if str(x.get('id')) == str(oid)
              and str(x.get('phone')) == str(u.get('phone'))), None)
    if not o:
        flash('没找到这一单（可能已经取消了）', 'warn')
        return redirect(url_for('user.me'))
    # 这页两用：玩之前是"定金"（一人 50，玩完退回），玩完（核销）之后是"游玩费"（全价）
    b = next((x for x in db.rows('bookings') if str(x.get('id')) == str(o.get('bid'))), {})
    if str(b.get('status')) in ('arrived', 'done') and o.get('balStatus') != 'paid':
        # 玩完付的是**游玩费全价**：定金是要退回的，不在这里抵
        o['due'] = max(0, int(o.get('amount') or 0))
        o['dueKind'] = '游玩费'
        o['dueAct'] = 'claim-bal'
    else:
        o['due'] = int(o.get('payable') if o.get('payable') is not None else o.get('deposit') or 0)
        o['dueKind'] = '定金'
        o['dueAct'] = 'claim'
    return render_template('pay_deposit.html', o=o)


@bp.get('/notice')
@login_required
def notice_center():
    """消息中心（顶栏那个 🔔 点进来就是这儿）"""
    u = current_user()
    return render_template('notice.html', rows=business.my_notices(u, 100))


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
    # 两个都别漏：表单（聊天/标签在里面）+ 员工身份（车主判断要用）
    ok, msg = business.car_action(dict(current_user(), _staff=is_staff()), cid, action, request.form)
    flash(msg, 'ok' if ok else 'warn')
    return redirect(url_for('public.car'))
