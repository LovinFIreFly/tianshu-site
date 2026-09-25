# -*- coding: utf-8 -*-
"""
公开页面：不用登录也能看的 —— 首页 / 剧本库 / 剧本详情 / 拼车大厅

（这几个页面是客人第一眼看到的，改样式主要改 templates/ 里对应的 html）
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from tianshu import business
from tianshu.db import db
from tianshu.security import current_user

bp = Blueprint('public', __name__)


@bp.get('/')
def home():
    scripts = db.rows('scripts')
    # 首页先推"上架 + 标了热门/上新"的，没有就按价格从低到高摆几个
    feat = [s for s in scripts if s.get('onSale') is not False and (s.get('hot') or s.get('isNew'))][:4]
    if not feat:
        feat = [s for s in scripts if s.get('onSale') is not False][:4]
    st = business.stats()
    rating = {k: v.get('rating') for k, v in st['byScript'].items()}
    return render_template('home.html', scripts=feat, stat=st, rating=rating,
                           sessions=business.today_sessions(), cars=business.car_pool()[:3])


@bp.get('/scripts')
def scripts():
    """剧本库：支持关键词 + 标签 + 难度筛选（参数都在网址上，方便收藏/转发）"""
    all_rows = db.rows('scripts')
    q = (request.args.get('q') or '').strip()
    tag = request.args.get('tag') or ''
    diff = request.args.get('diff') or ''
    only_fav = request.args.get('fav') == '1'
    u = current_user()

    rows = []
    favs = my_fav_ids(u)
    for s in all_rows:
        if s.get('onSale') is False:
            continue
        if q and q not in str(s.get('title', '')) and q not in str(s.get('desc', '')):
            continue
        if tag and tag not in (s.get('tags') or []):
            continue
        if diff and str(s.get('diff')) != diff:
            continue
        if only_fav and str(s.get('id')) not in favs:
            continue
        rows.append(s)

    tags = []
    for s in all_rows:                       # 标签是从剧本里现攒的，不用单独维护
        for t in s.get('tags') or []:
            if t not in tags:
                tags.append(t)
    st = business.stats()
    return render_template('scripts.html', scripts=rows, tags=tags,
                           q=q, tag=tag, diff=diff, only_fav=only_fav, favs=favs,
                           rating={k: v.get('rating') for k, v in st['byScript'].items()})


@bp.get('/scripts/<int:sid>')
def script_detail(sid):
    """剧本详情 + 预约表单（日期/时间/人数/拼车还是包车/指定 DM/选角/用券）"""
    sc = db.one('scripts', id=sid)
    if not sc:
        return render_template('error.html', code=404, msg='这个剧本不在库里（可能被删了）'), 404
    u = current_user()
    st = business.get_settings()
    lo, hi = business.player_range(sc)

    # 可选的日期：今天起 7 天
    import time as _t
    days = []
    for i in range(7):
        d = _t.localtime(_t.time() + i * 86400)
        ts = int(_t.mktime(_t.strptime(_t.strftime('%Y-%m-%d', d), '%Y-%m-%d'))) * 1000
        days.append({'ts': ts, 'label': '今天' if i == 0 else ('明天' if i == 1 else business.day_label(ts))})

    # 这个本已排的场次（客人可以直接约某一场）
    ses = [s for s in db.rows('sessions') if str(s.get('sid')) == str(sid) and s.get('status') == 'open']
    joined = {}
    for b in db.rows('bookings'):
        if b.get('sessionId') and b.get('status') != 'cancelled':
            k = str(b['sessionId'])
            joined[k] = joined.get(k, 0) + (b.get('players') or 1)

    # 我的券
    coupons = []
    if u:
        coupons = [c for c in db.rows('coupons') if not c.get('used')
                   and (c.get('all') or str(c.get('phone')) == str(u.get('phone')))
                   and (not c.get('exp') or c.get('exp') > business.now_ms())]

    # 这个本谁选过什么角色（同一天同一时段只能一人选一角，这里只做展示提示）
    taken_roles = {str(b.get('role')) for b in db.rows('bookings')
                   if str(b.get('sid')) == str(sid) and b.get('status') != 'cancelled' and b.get('role')}

    reviews = [r for r in db.rows('reviews') if str(r.get('sid')) == str(sid) and not r.get('hidden')]
    dms = db.rows('users')
    dms = [{'phone': d.get('phone'), 'name': (d.get('profile') or {}).get('nick') or d.get('username')}
           for d in dms if business.role_of(d) == 'dm' and (d.get('dmProfile') or {}).get('canOpen', True)]

    return render_template('script.html', sc=sc, days=days, sessions=ses, coupons=coupons,
                           lo=lo, hi=hi, dm_fee=st['dmFee'], reviews=reviews, dms=dms,
                           taken=taken_roles, favs=my_fav_ids(u), join=joined,
                           rating=business.stats()['byScript'].get(str(sid), {}).get('rating'))


@bp.get('/car')
def car():
    """拼车大厅：谁开了车、还差几人、能上车还是排候补"""
    u = current_user()
    return render_template('car.html', cars=business.car_pool(u.get('phone') if u else ''),
                           mine=business.my_cars(u.get('phone')) if u else set(),
                           tags=business.get_settings()['carTags'])


@bp.get('/comm')
def comm():
    """玩家社区：约不到人、想吐槽本子、想晒战报，都来这儿发（前台不主动推，玩家自己点进来）"""
    u = current_user()
    return render_template('comm.html', posts=business.community_posts(60, str((u or {}).get('phone') or '')))


@bp.post('/post')
def post_create():
    u = current_user()
    if not u:
        flash('登录之后才能发帖', 'warn')
        return redirect(url_for('user.login', next='/comm'))
    text = business.clean(request.form.get('text'), 1000)
    if not text:
        flash('写点内容再发', 'warn')
    else:
        db.update('posts', lambda rows: [{
            'id': business.now_ms(), 'type': request.form.get('type') or 'diary',
            'title': business.clean(request.form.get('title'), 40), 'text': text, 'imgs': [],
            'username': (u.get('profile') or {}).get('nick') or u.get('username'),
            'phone': u.get('phone'), 'at': business.now_ms(), 'likes': []}] + rows, 500)
        flash('发出去了', 'ok')
    return redirect(url_for('public.comm'))


@bp.post('/post/<int:pid>/like')
def post_like(pid):
    u = current_user()
    if not u:
        flash('登录之后才能点赞', 'warn')
        return redirect(url_for('user.login', next='/comm'))
    phone = str(u.get('phone'))
    rows = db.rows('posts')
    for p in rows:
        if p.get('id') == pid:
            likes = [str(x) for x in p.get('likes') or []]
            p['likes'] = [x for x in likes if x != phone] if phone in likes else likes + [phone]
    db.write('posts', rows)
    return redirect(url_for('public.comm'))


@bp.post('/fav/<int:sid>')
def fav(sid):
    """收藏（想玩）—— 没登录就先去登录"""
    u = current_user()
    if not u:
        flash('登录之后才能收藏哦', 'warn')
        return redirect(url_for('user.login', next=url_for('public.script_detail', sid=sid)))
    phone = str(u.get('phone'))
    rows = db.rows('favs')
    rec = next((r for r in rows if str(r.get('phone')) == phone), None)
    if not rec:
        rec = {'phone': phone, 'sids': []}
        rows.append(rec)
    sids = [str(x) for x in rec.get('sids') or []]
    if str(sid) in sids:
        sids.remove(str(sid))
        flash('已取消收藏', 'ok')
    else:
        sids.append(str(sid))
        flash('加进「想玩」了', 'ok')
    rec['sids'] = sids
    db.write('favs', rows)
    return redirect(request.referrer or url_for('public.scripts'))


def my_fav_ids(u):
    """我收藏过的剧本 id（集合，模板里好判断）"""
    if not u:
        return set()
    for r in db.rows('favs'):
        if str(r.get('phone')) == str(u.get('phone')):
            return {str(x) for x in r.get('sids') or []}
    return set()
