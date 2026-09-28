# -*- coding: utf-8 -*-
"""
公开页面：不用登录也能看的 —— 首页 / 剧本库 / 剧本详情 / 拼车大厅

（这几个页面是客人第一眼看到的，改样式主要改 templates/ 里对应的 html）
"""
import os

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from tianshu import business
from tianshu.db import db
from tianshu.security import current_user

bp = Blueprint('public', __name__)


@bp.before_app_request
def _mark_entered():
    """游客一旦开始逛站内页面（剧本库 / 拼车 / 剧本详情…），欢迎页就不该再挡路。

    只对游客生效、只认 GET 的页面请求，而且 / 自己不算 ——
    否则一进站就被标记上，欢迎页永远也出不来了。
    """
    if request.method != 'GET' or current_user() or session.get('entered'):
        return
    ep = request.endpoint or ''
    if ep.startswith('public.') and ep not in ('public.home', 'public.welcome'):
        session['entered'] = True


def _welcome_ctx():
    """欢迎页底部那行小字：上架几部本、今天几场"""
    on_sale = [s for s in db.rows('scripts') if s.get('onSale') is not False]
    return {'meta': {'scripts': len(on_sale), 'today': len(business.today_sessions())}}


@bp.get('/welcome')
def welcome():
    """欢迎页（老版 page-welcome）：进站第一屏，🍠 + 店名 + 登录/注册两个按钮。

    正常从 / 进来就会看到它；这个网址单独留着，方便直接发给别人看。
    """
    return render_template('welcome.html', **_welcome_ctx())


@bp.get('/theme')
def toggle_theme():
    """切换深/浅色（顶栏那个 🌙 按钮）。

    默认是浅色（暖米底那套，Airbnb 方向的），喜欢暗的记在 cookie 里。
    注意别把默认值写反：base.html 里是「theme == 'dark' 才输出 data-theme」。
    """
    from flask import make_response, request as _req, redirect
    cur = _req.cookies.get('theme') or 'light'
    resp = make_response(redirect(_req.referrer or url_for('public.home')))
    resp.set_cookie('theme', 'dark' if cur != 'dark' else 'light', max_age=365 * 86400)
    return resp


@bp.get('/')
def home():
    """进站第一眼。

    没登录的人先看到**欢迎页**（老版就是 page-welcome → page-login 两步走，
    不是一进来就是登录表单）：点「登 录」才去登录页，想先看看的走「先随便逛逛」。
    登录之后这页就不再出现，/ 直接是门店首页。
    """
    if not current_user() and not (request.args.get('browse') or session.get('entered')):
        return render_template('welcome.html', **_welcome_ctx())
    if request.args.get('browse'):
        session['entered'] = True
    scripts = db.rows('scripts')
    # 首页先推"上架 + 标了热门/上新"的，没有就按价格从低到高摆几个
    feat = [s for s in scripts if s.get('onSale') is not False and (s.get('hot') or s.get('isNew'))][:4]
    if not feat:
        feat = [s for s in scripts if s.get('onSale') is not False][:4]
    st = business.stats()
    rating = {k: v.get('rating') for k, v in st['byScript'].items()}
    # 累计场次：到今天为止一共排了多少场（含今天的）—— 首页对外不露营业额，就露这个
    day_end = business.midnight() + 86400000
    done_sessions = len([s for s in db.rows('sessions') if (s.get('ts') or 0) < day_end])
    return render_template('home.html', scripts=feat, stat=st, rating=rating,
                           banners=business.banners(), done_sessions=done_sessions,
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
           for d in dms if business.has_role(d, 'dm') and (d.get('dmProfile') or {}).get('canOpen', True)]

    # 拼车：「加入已有的车」那个下拉里列出来的车（别人开的、还没满、还没过日期）
    open_cars = [c for c in business.car_pool() if str(c.get('sid')) == str(sid) and not c.get('full')]
    # 评分 = 玩家点评的平均分（没人评过就是 0，页面上显示"—"）；n 是评价条数
    _st = business.stats()['byScript'].get(str(sid), {})

    return render_template('script.html', sc=sc, days=days, sessions=ses, coupons=coupons,
                           lo=lo, hi=hi, dm_fee=st['dmFee'], reviews=reviews, dms=dms,
                           taken=taken_roles, favs=my_fav_ids(u), join=joined,
                           open_cars=open_cars, car_deposit=business.car_deposit(st),
                           # 日历控件的可选范围：今天 ~ 30 天后（别再让客人翻无意义的月份）
                           day_min=business.iso_day(0), day_max=business.iso_day(30),
                           rating=_st.get('rating'), rating_n=_st.get('n'))


@bp.get('/car')
def car():
    """拼车大厅：谁开了车、还差几人、能上车还是排候补"""
    u = current_user()
    return render_template('car.html', cars=business.car_pool(u.get('phone') if u else ''),
                           mine=business.my_cars(u.get('phone')) if u else set(),
                           tags=business.get_settings()['carTags'])


@bp.get('/car/<int:cid>')
def car_detail(cid):
    """车队详情：看成员、聊两句；车主还能贴标签、留熟人位"""
    u = current_user()
    car = next((c for c in business.car_pool(u.get('phone') if u else '') if str(c.get('id')) == str(cid)), None)
    if not car:
        return render_template('error.html', code=404, msg='这辆车已经不在了（可能过期了或被取消）'), 404
    owner_bk = next((b for b in db.rows('bookings') if b.get('id') == car.get('id') and b.get('carNew')), None)
    is_owner = bool(u) and owner_bk and str(owner_bk.get('phone')) == str(u.get('phone'))
    msgs = business.car_msgs(cid)
    for m in msgs:
        m['mine'] = bool(u) and str(m.get('phone')) == str(u.get('phone'))
    return render_template('car_detail.html', car=car, msgs=msgs, is_owner=is_owner,
                           tags=business.get_settings()['carTags'])


@bp.post('/review/<int:rid>/like')
def review_like(rid):
    """给别人的评价点个赞（表示"这条有用"）"""
    u = current_user()
    if not u:
        flash('登录之后才能点赞', 'warn')
        return redirect(request.referrer or url_for('public.home'))
    phone = str(u.get('phone'))
    rows = db.rows('reviews')
    for r in rows:
        if r.get('id') == rid:
            likes = [str(x) for x in r.get('likes') or []]
            r['likes'] = [x for x in likes if x != phone] if phone in likes else likes + [phone]
    db.write('reviews', rows)
    return redirect(request.referrer or url_for('public.home'))


@bp.get('/img/<sub>/<name>')
def upload_img(sub, name):
    """读上传的图片（封面 / 头像 / 形象照）。只让读 data/img/ 里这几类，别的一律不给"""
    from flask import abort, send_from_directory
    from config import IMG_DIR
    if sub not in ('cover', 'avatar', 'role', 'dm') or '/' in name or '..' in name:
        abort(404)
    return send_from_directory(os.path.join(IMG_DIR, sub), name)


@bp.get('/dm/<phone>')
def dm_page(phone):
    """DM 公开主页（老版那句"点击查看主页"）：段位、风格、自我介绍、带过的本、最近评价。

    客户和 DM 本人都能看；改资料在 DM 工作台「我的成长」里改。
    注意路由顺序：/dm/credit 这类静态路径优先于 /dm/<phone>，不会被吃掉。
    """
    u = db.one('users', phone=phone)
    if not u or not business.has_role(u, 'dm', 'admin'):
        flash('没找到这位 DM', 'warn')
        return redirect(url_for('public.scripts'))
    st = business.dm_growth(phone)
    # 他实际带过的本（从预约里推，不靠手工维护的清单）
    my_sids = {str(b.get('sid')) for b in db.rows('bookings')
               if str(b.get('dmPhone')) == phone and b.get('status') != 'cancelled'}
    titles = [s.get('title') for s in db.rows('scripts') if str(s.get('id')) in my_sids][:8]
    reviews = sorted([r for r in db.rows('reviews')
                      if str(r.get('dmPhone')) == phone and not r.get('hidden')],
                     key=lambda x: -(x.get('createdAt') or 0))[:4]
    return render_template('dm_profile.html', u=u, st=st, titles=titles, reviews=reviews,
                           nickname=(u.get('profile') or {}).get('nick') or u.get('username'))


@bp.get('/comm')
def comm():
    """玩家社区。分「动态 / 日记 / 攻略 / 组队」四类（老版就是这个分法），
    顶上能按分类筛；不带参数就是全部。"""
    u = current_user()
    t = (request.args.get('t') or '').strip()
    posts = business.community_posts(60, str((u or {}).get('phone') or ''))
    counts = {}
    for p in posts:
        k = p.get('type') or 'chat'
        counts[k] = counts.get(k, 0) + 1
    rows = [p for p in posts if not t or (p.get('type') or 'chat') == t]
    return render_template('comm.html', posts=rows, t=t, counts=counts)


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


@bp.get('/u/<username>')
def user_profile(username):
    """玩家主页（老版点开 DM/队友资料卡就是这种）：公开资料 + 关注 + 他的评价"""
    from tianshu.security import current_user as _cu
    u = db.one('users', username=username)
    if not u:
        return render_template('error.html', code=404, msg='没有这个人'), 404
    me = _cu()
    following = me and str(username) in [str(x) for x in (me.get('following') or [])]
    return render_template('profile.html', who=u, role_name=business.roles_text(u),
                           following=following, scripts=db.rows('scripts'),
                           reviews=[r for r in business.reviews_of() if str(r.get('username')) == str(username)],
                           followers=len(u.get('followers') or []))


@bp.post('/u/<username>/follow')
def user_follow(username):
    """关注 / 取关（老版有这套社交关系）"""
    u = current_user()
    if not u:
        flash('登录之后才能关注', 'warn')
        return redirect(url_for('user.login'))
    target = db.one('users', username=username)
    if not target:
        flash('没有这个人', 'warn')
        return redirect(url_for('public.home'))
    users = db.rows('users')
    me = next((x for x in users if str(x.get('phone')) == str(u.get('phone'))), None)
    tgt = next((x for x in users if str(x.get('phone')) == str(target.get('phone'))), None)
    if me is None or tgt is None:
        return redirect(url_for('public.home'))
    fl = [str(x) for x in me.get('following') or []]
    fr = [str(x) for x in tgt.get('followers') or []]
    if str(username) in fl:
        me['following'] = [x for x in fl if x != str(username)]
        tgt['followers'] = [x for x in fr if x != str(u.get('username'))]
        flash('已取消关注', 'ok')
    else:
        me['following'] = fl + [str(username)]
        tgt['followers'] = fr + [str(u.get('username'))]
        business.notify(tgt.get('phone'), '有人关注了你',
                        '%s 关注了你，拼车时更容易凑到一起' % u.get('username'), 'follow')
        flash('关注成功', 'ok')
    db.write('users', users)
    return redirect(url_for('public.user_profile', username=username))


@bp.post('/review/<int:rid>/follow')
def review_follow(rid):
    """追评：玩完过几天想补两句（老版 followUpId 就是干这个的）"""
    u = current_user()
    if not u:
        flash('登录之后才能追评', 'warn')
        return redirect(url_for('user.login'))
    text = business.clean(request.form.get('text'), 500)
    if not text:
        flash('写点什么再追评', 'warn')
        return redirect(request.referrer or url_for('public.home'))
    rows = db.rows('reviews')
    for r in rows:
        if r.get('id') == rid and str(r.get('username')) == str(u.get('username')):
            ups = r.get('followUps') or []
            ups.append({'text': text, 'at': business.now_ms()})
            r['followUps'] = ups
    db.write('reviews', rows)
    flash('追评加上了', 'ok')
    return redirect(request.referrer or url_for('public.home'))


@bp.post('/post/<int:pid>/report')
def post_report(pid):
    """举报帖子（广告 / 剧透不标注 / 人身攻击）。存起来等门店处理，不会自动删"""
    u = current_user()
    if not u:
        flash('登录之后才能举报', 'warn')
        return redirect(url_for('user.login'))
    reason = business.clean(request.form.get('reason'), 100) or '未说明'
    rows = db.rows('reports')
    rows.append({'id': business.now_ms(), 'kind': 'post', 'target': pid, 'reason': reason,
                 'by': u.get('username'), 'phone': u.get('phone'), 'at': business.now_ms(),
                 'handled': False})
    db.write('reports', rows[-200:])
    flash('举报收到了，我们会尽快看（不会立刻删，避免误伤）', 'ok')
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
