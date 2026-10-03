# -*- coding: utf-8 -*-
"""
公开页面：不用登录也能看的 —— 首页 / 剧本库 / 剧本详情 / 拼车大厅

（这几个页面是客人第一眼看到的，改样式主要改 templates/ 里对应的 html）
"""
import os

from flask import (Blueprint, flash, jsonify, make_response, redirect,
                   render_template, request, session, url_for)

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
    """切换主题：三态循环 light → dark → auto → light。

    cookie theme 取值 light / dark / auto；base.html 的内联脚本据此
    （auto 时 matchMedia 跟随系统）尽早设置 data-theme。
    """
    cur = request.cookies.get('theme') or 'light'
    nxt = {'light': 'dark', 'dark': 'auto'}.get(cur, 'light')
    resp = make_response(redirect(request.referrer or url_for('public.home')))
    resp.set_cookie('theme', nxt, max_age=365 * 86400)
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
    served = sum(int(b.get('players') or 0) for b in db.rows('bookings')
                 if b.get('status') in ('arrived', 'done') and (b.get('ts') or 0) < day_end)
    # 七·真实内容前置：今日 DM 值班 / 真实玩家短评滚动 / 老板今日推荐
    sessions = business.today_sessions()
    dm_duty = []
    for s in sessions:
        n = (s.get('dmName') or '').strip()
        if n and n != '待安排' and n not in dm_duty:
            dm_duty.append(n)
    # 真实玩家短评：最近几条"已展示"的评价（reviews_of 已带昵称/头像，按时间倒序）
    # 只取最近 20 条来挑带文字的 8 条，不必给全量评价建昵称/头像（AUD-B-0026）
    script_titles = {str(s.get('id')): s.get('title', '') for s in scripts}
    reviews = []
    for r in business.reviews_of(limit=20):
        if not r.get('text'):
            continue
        reviews.append({
            'nick': r.get('nick') or '玩家',
            'avatar': r.get('avatar') or '',
            'title': script_titles.get(str(r.get('sid')) or '', ''),
            'text': r.get('text', ''),
            'stars': r.get('rating') or 0,
        })
        if len(reviews) >= 8:
            break
    boss_pick = feat[0] if feat else (scripts[0] if scripts else None)
    # 热玩本：stats['hot'] 已是 [(sid, {plays...})] 按 plays 降序 top6，转回剧本对象
    scripts_by_id = {str(s.get('id')): s for s in scripts}
    hotScripts = [scripts_by_id[sid] for sid, _ in st['hot'] if sid in scripts_by_id]
    # 新本首车：上架剧本按 id 倒序 top6
    on_sale = [s for s in scripts if s.get('onSale') is not False]
    newScripts = sorted(on_sale, key=lambda s: -(s.get('id') or 0))[:6]
    return render_template('home.html', scripts=feat, stat=st, rating=rating,
                           banners=business.banners(), served=served,
                           sessions=sessions, cars=business.car_pool()[:3],
                           dm_duty=dm_duty, reviews=reviews, boss_pick=boss_pick,
                           hotScripts=hotScripts, newScripts=newScripts)


@bp.get('/scripts')
def scripts():
    """剧本库：支持关键词 + 标签 + 难度筛选（参数都在网址上，方便收藏/转发）"""
    all_rows = db.rows('scripts')
    q = (request.args.get('q') or '').strip()
    tag = request.args.get('tag') or ''
    # 多选标签：?tags=情感,硬核 —— 命中任意一个就算（OR）。老的 ?tag= 单选仍然管用。
    sel_tags = [x.strip() for x in (request.args.get('tags') or '').split(',') if x.strip()]
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
        if sel_tags:
            if not any(t in (s.get('tags') or []) for t in sel_tags):
                continue
        elif tag and tag not in (s.get('tags') or []):
            continue
        if diff and str(s.get('diff')) != diff:
            continue
        if only_fav and str(s.get('id')) not in favs:
            continue
        rows.append(s)

    from config import TAG_PRESETS
    tags = list(TAG_PRESETS)                 # 平台常见的分类先摆上，客人一进来就有得筛
    for s in all_rows:                       # 剧本里自定义的标签也一并露出（去重、保持顺序）
        for t in s.get('tags') or []:
            if t and t not in tags:
                tags.append(t)
    st = business.stats()
    rating = {k: v.get('rating') for k, v in st['byScript'].items()}
    # SPA 筛选：带上 partial=1 时只返回卡片网格那一段 HTML（不含 base 布局），
    # 前端点了分类标签用 fetch 拉这段、原地替换，网址始终是 /scripts，不会整页跳。
    if request.args.get('partial') == '1':
        return render_template('_scripts_grid.html', scripts=rows, favs=favs, rating=rating)
    return render_template('scripts.html', scripts=rows, tags=tags,
                           q=q, tag=tag, sel_tags=sel_tags, diff=diff, only_fav=only_fav, favs=favs,
                           rating=rating)


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

    reviews = business.reviews_of(sid, only_visible=True)
    dms = db.rows('users')
    dms = [{'phone': d.get('phone'), 'name': (d.get('profile') or {}).get('nick') or d.get('username')}
           for d in dms if business.has_role(d, 'dm') and (d.get('dmProfile') or {}).get('canOpen', True)]

    # 拼车：「加入已有的车」那个下拉里列出来的车（别人开的、还没满、还没过日期）
    open_cars = [c for c in business.car_pool() if str(c.get('sid')) == str(sid) and not c.get('full')]
    # 评分 = 玩家点评的平均分（没人评过就是 0，页面上显示"—"）；n 是评价条数
    _st = business.stats()['byScript'].get(str(sid), {})
    # 演后复盘仅 DM/管理员可见（§2.5）
    canSeeReview = bool(u) and (business.has_role(u, 'dm') or business.has_role(u, 'admin'))

    return render_template('script.html', sc=sc, days=days, sessions=ses, coupons=coupons,
                           lo=lo, hi=hi, dm_fee=st['dmFee'], reviews=reviews, dms=dms,
                           taken=taken_roles, favs=my_fav_ids(u), join=joined,
                           open_cars=open_cars, car_deposit=business.car_deposit(st),
                           # 日历控件的可选范围：今天 ~ 30 天后（别再让客人翻无意义的月份）
                           day_min=business.iso_day(0), day_max=business.iso_day(30),
                           rating=_st.get('rating'), rating_n=_st.get('n'),
                           canSeeReview=canSeeReview,
                           # 评价里写的用户名不一定还是本站账号（改过名/注销/历史脏数据），
                           # 模板用它决定要不要显示「看 TA 主页」—— 不判断就会点出 404
                           user_names={str(d.get('username')) for d in db.rows('users')})


@bp.get('/car')
def car():
    """拼车大厅：谁开了车、还差几人、能上车还是排候补。

    GET 筛选：q(剧本名模糊) / players(≥人数，按 carMin) / time(时段 上午/下午/晚上
    或精确时间串) / diff(1-5，匹配 scriptDiff)。筛选参数原样回显给模板做表单回填。
    """
    u = current_user()
    cars = business.car_pool(u.get('phone') if u else '')
    q = (request.args.get('q') or '').strip()
    players = (request.args.get('players') or '').strip()
    tm = (request.args.get('time') or '').strip()
    diff = (request.args.get('diff') or '').strip()

    def _hour_of(c):
        s = str(c.get('time') or '')
        try:
            return int(s.split(':')[0])
        except (ValueError, IndexError):
            return -1

    def _match_period(c, period):
        h = _hour_of(c)
        if h < 0:
            return False
        if period == '上午':
            return h < 12
        if period == '下午':
            return 12 <= h < 18
        if period == '晚上':
            return h >= 18
        return str(c.get('time') or '') == period   # 精确时间串

    if q:
        cars = [c for c in cars if q in str(c.get('title') or '')]
    if players:
        try:
            pn = int(players)
            cars = [c for c in cars if int(c.get('min') or 0) >= pn]
        except ValueError:
            pass
    if tm:
        cars = [c for c in cars if _match_period(c, tm)]
    if diff:
        cars = [c for c in cars if str(c.get('scriptDiff') or '') == str(diff)]
    return render_template('car.html', cars=cars,
                           mine=business.my_cars(u.get('phone')) if u else set(),
                           tags=business.get_settings()['carTags'],
                           q=q, players=players, time=tm, diff=diff)


@bp.get('/group')
def group():
    """组局：今天在开的局一览 + 自己开一桌的入口（去挑本选拼车/包车即发车）"""
    return render_template('group.html', sessions=business.today_sessions())


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
                           tags=business.get_settings()['carTags'],
                           user_names={str(x.get('username')) for x in db.rows('users')})


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
    """读上传的图片（封面 / 头像 / 形象照 / 门店群二维码）。只让读 data/img/ 里这几类，别的一律不给

    图片一周内不变，发长缓存头让浏览器/CDN 直接缓存（AUD-B-0084）。
    conditional=True 让浏览器带 If-Modified-Since 时回 304，省带宽。"""
    from flask import abort, send_from_directory
    from config import IMG_DIR
    if sub not in ('cover', 'avatar', 'role', 'dm', 'qr') or '/' in name or '..' in name:
        abort(404)
    return send_from_directory(os.path.join(IMG_DIR, sub), name,
                               max_age=604800, conditional=True)


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
    """玩家社区。

    GET 筛选：type(all|chat|recruit) 按 postType 过滤（chat=非招募帖），
    topic 按话题（情感/硬核/恐怖/欢乐）过滤。筛选参数 ftype/ftopic 回显给模板。
    老的 ?t= 页内标签保留。
    """
    u = current_user()
    t = (request.args.get('t') or '').strip()
    ftype = (request.args.get('type') or 'all').strip()
    ftopic = (request.args.get('topic') or '').strip()
    # 映射到 business.community_posts 的 ftype：all/空→不过滤；recruit→精确匹配；chat→先全取再排除招募
    biz_ftype = '' if ftype in ('', 'all', 'chat') else ftype
    posts = business.community_posts(60, str((u or {}).get('phone') or ''),
                                     ftype=biz_ftype, ftopic=ftopic)
    if ftype == 'chat':
        posts = [p for p in posts if (p.get('postType') or '') != 'recruit']
    counts = {}
    for p in business.community_posts(200, str((u or {}).get('phone') or '')):
        k = p.get('type') or 'chat'
        counts[k] = counts.get(k, 0) + 1
    return render_template('comm.html', posts=posts, t=t, counts=counts,
                           ftype=ftype, ftopic=ftopic)


@bp.post('/post')
def post_create():
    u = current_user()
    if not u:
        flash('登录之后才能发帖', 'warn')
        return redirect(url_for('user.login', next='/comm'))
    text = business.clean(request.form.get('text'), 1000)
    if not text:
        flash('写点内容再发', 'warn')
        return redirect(url_for('public.comm'))
    # 话题 / 招募字段（§2.4）
    topic = business.clean(request.form.get('topic'), 8)
    post_type = request.form.get('postType') or ''
    if post_type not in ('recruit',):
        post_type = ''
    recruit_need = 0
    recruit_role = ''
    recruit_script = ''
    if post_type == 'recruit':
        recruit_role = business.clean(request.form.get('recruitRole'), 16)
        recruit_script = business.clean(request.form.get('recruitScript'), 30)
        try:
            recruit_need = int(request.form.get('recruitNeed') or 0)
            recruit_need = max(1, min(12, recruit_need))
        except ValueError:
            recruit_need = 0
        if not recruit_need and not recruit_role:
            flash('缺位招募要至少填「缺几人」或「缺什么位」', 'warn')
            return redirect(url_for('public.comm'))
    db.update('posts', lambda rows: [{
        'id': business.now_ms(), 'type': request.form.get('type') or 'chat',
        'title': business.clean(request.form.get('title'), 40), 'text': text, 'imgs': [],
        'topic': topic, 'postType': post_type,
        'recruitNeed': recruit_need, 'recruitRole': recruit_role,
        'recruitScript': recruit_script,
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
    """收藏分组（想玩 / 已玩 / 避雷）—— 没登录就先去登录。

    group 参数（form 或 query）：want|done|avoid，默认 want。
    切换逻辑：当前不在该组 → 加入；已在 → 移出。
    """
    u = current_user()
    if not u:
        flash('登录之后才能收藏哦', 'warn')
        return redirect(url_for('user.login', next=url_for('public.script_detail', sid=sid)))
    group = request.form.get('group') or request.args.get('group') or 'want'
    if group not in ('want', 'done', 'avoid'):
        group = 'want'
    groups = business.fav_groups(u)
    on = str(sid) not in groups.get(group, [])
    business.fav_set(u, sid, group, on)
    labels = {'want': '想玩', 'done': '已玩', 'avoid': '避雷'}
    label = labels.get(group, '想玩')
    flash(('已加入「%s」' % label) if on else ('已移出「%s」' % label), 'ok')
    # AJAX 收藏：前端那颗心点了用 fetch 打这个接口，成功后只回个 JSON，
    # 前端自己改按钮状态，整页不刷新（剧本库 SPA 体验的一部分）。
    if request.args.get('ajax') == '1' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'on': on, 'group': group})
    return redirect(request.referrer or url_for('public.scripts'))


def my_fav_ids(u):
    """我收藏过的剧本 id（集合，模板里好判断）"""
    if not u:
        return set()
    for r in db.rows('favs'):
        if str(r.get('phone')) == str(u.get('phone')):
            return {str(x) for x in r.get('sids') or []}
    return set()


@bp.get('/faq')
def faq():
    """常见问题页（匿名可访问）。内容见 spec §5.4，模板由 T1 创建。"""
    return render_template('faq.html', serviceWechat=business.get_settings().get('serviceWechat', ''))


@bp.post('/api/track')
def api_track():
    """埋点 beacon：前端 sendBeacon 发 {path}，服务端只记 IP 哈希 + path，不记任何用户信息。"""
    path = (request.get_json(silent=True) or {}).get('path') or request.form.get('path') or '/'
    business.track_visit(request.remote_addr or '', path)
    return jsonify({'ok': True})
