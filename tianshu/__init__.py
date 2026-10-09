# -*- coding: utf-8 -*-
"""
应用工厂：把整站拼起来的地方（Flask 官方推荐的写法，方便以后拆模块、写测试）

    from tianshu import create_app
    app = create_app()
"""
import gzip
import os
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session
from jinja2 import BaseLoader, FileSystemLoader, TemplateNotFound

from config import IMG_DIR, ROOMS_DEFAULT, SEED_USERS, SESSION_DAYS, SETTINGS_DEFAULT, TEMPLATES_AUTO_RELOAD
from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, hash_password, role, session_secret

# 手机 UA 正则：device_guess / mobile_front 两处都用，提到模块级预编译一次（别每请求编译）
_MOBILE_UA_RE = re.compile(r'(?:iPhone|iPod|Android|Mobile|BlackBerry|IEMobile|Opera Mini|Windows Phone)',
                           re.IGNORECASE)

# static_v(fname) 的 mtime 缓存：每请求对每个静态文件 os.stat 一次太浪费，文件 mtime 不变就复用
_static_v_cache = {}

# 不需要 CSRF 令牌的写接口（见 csrf_guard 里的说明）：只记路径的匿名埋点
# 小程序登录 / 绑定用 Bearer token 鉴权，不是 Cookie，CSRF 对它无意义，直接放行。
_CSRF_FREE = {'/api/track', '/m/api/track', '/m/api/mp/login', '/m/api/mp/bind'}


class UiLoader(BaseLoader):
    """按"一代 / 二代"挑模板目录。

        二代 = tianshu/templates/
        一代 = tianshu/templates/v1/（只放客人看得到的页：首页 / 剧本库 / 拼车 / 登录…）

    一代模式下**必须先找 v1、找不到再落回二代**：后台面板、DM 工作台这些
    一代目录里没有（那是店里干活的地方，不跟着客人的界面切），得能落回新版。
    （第一版这里写成"二选一"，结果一代模式下后台直接 TemplateNotFound 500 —— 踩过。）

    另外 v1 的骨架叫 layout_v1.html / auth_v1.html，**故意不叫 base.html**：
    base.html 这个名字要留给二代，否则后台套上一代骨架。
    切换由 business.ui_ver() 决定。
    """

    def __init__(self, paths):
        self.v2 = FileSystemLoader(paths)
        self.v1 = FileSystemLoader([os.path.join(p, 'v1') for p in paths])

    def get_source(self, environment, template):
        if business.ui_ver() == '1':
            for loader in (self.v1, self.v2):        # 一代优先，缺的落回二代
                try:
                    return loader.get_source(environment, template)
                except TemplateNotFound:
                    continue
            raise TemplateNotFound(template)
        return self.v2.get_source(environment, template)


def seed():
    """第一次运行：建目录、建内置账号、写默认设置。已有数据就什么都不动"""
    os.makedirs(IMG_DIR, exist_ok=True)
    if db.read('users') is None:
        t = business.now_ms()
        db.write('users', [{
            'phone': phone, 'username': name, 'email': '', 'role': r, 'super': sup,
            'password': hash_password('123123'), 'credit': 100, 'creditLogs': [],
            'profile': {'avatar': '🎭', 'nick': name, 'gender': '', 'age': None},
            'first': t + i, 'last': t + i, 'invite': 'TS%04d' % (i + 1), 'banned': False,
        } for i, (name, phone, r, sup) in enumerate(SEED_USERS)])
        print('[初始化] 建好 %d 个内置账号（密码都是 123123）' % len(SEED_USERS))
    if db.read('settings') is None:
        db.write('settings', SETTINGS_DEFAULT)
    if db.read('rooms') is None:
        db.write('rooms', ROOMS_DEFAULT)


def create_app():
    seed()
    app = Flask(__name__)
    # 模板目录：一代 / 二代由 UiLoader 现挑（见类说明）
    app.jinja_loader = UiLoader([os.path.join(app.root_path, app.template_folder or 'templates')])
    app.secret_key = session_secret()

    @app.template_filter('nl2p')
    def nl2p_filter(text):
        """把纯文本按空行拆成 <p> 段落；先吃掉文本里原本的 <br> 标签（含转义后的 &lt;br&gt; / &amp;lt;br&amp;gt;），避免显示成 <br>。"""
        import html
        from markupsafe import escape, Markup
        s = html.unescape(str(text or ''))
        s = re.sub(r'<br\s*/?>', '\n', s, flags=re.IGNORECASE)
        s = re.sub(r'&lt;br\s*/?&gt;', '\n', s, flags=re.IGNORECASE)
        paragraphs = [p.strip() for p in s.split('\n\n') if p.strip()]
        if not paragraphs:
            return ''
        return Markup('<p>' + '</p><p>'.join(str(escape(p)).replace('\n', '<br>\n') for p in paragraphs) + '</p>')
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,          # 表单别传太大（图片走单独上传）
        TEMPLATES_AUTO_RELOAD=TEMPLATES_AUTO_RELOAD,  # 热重载会拖慢每个请求，默认关；开发用 --dev
        # 静态资源长缓存：文件名带 ?v=mtime，一改 URL 就变，所以可以放心发 max-age=30 天 + immutable。
        # HTML 不在这里（Flask 默认 static 才走这个；页面 HTML 由视图渲染，不带 immutable）。
        SEND_FILE_MAX_AGE_DEFAULT=2592000,
        # Cookie 安全标记：HttpOnly 让 JS 读不到登录会话（脚本偷不走）；
        # SameSite=Lax 让"别的网站骗你点一下"时带不上会话（CSRF 的第一道防线）。
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )

    from tianshu.views import admin, dm, public, user
    app.register_blueprint(public.bp)
    app.register_blueprint(user.bp)
    app.register_blueprint(dm.bp)
    app.register_blueprint(admin.bp)
    # 手机端独立站（v2）：与桌面站完全独立的一套静态移动站点，不碰数据库
    from tianshu.views import mobile_site
    app.register_blueprint(mobile_site.bp)

    @app.context_processor
    def inject_globals():
        """模板里到处都要用的东西，统一塞进去（省得每个视图都传一遍）"""
        def static_v(fname):
            """静态文件版本号 = 文件的修改时间。文件一改，URL 就变（?v=1695…），
            浏览器立刻拉新版 —— 否则手机上老缓存不更新，"明明改了却没变化"（2026-09 用户被坑过）。
            mtime 缓存：同一文件反复 stat 没意义，mtime 不变就直接返回上次结果。"""
            cached = _static_v_cache.get(fname)
            try:
                mt = int(os.stat(os.path.join(app.static_folder, fname)).st_mtime)
            except OSError:
                return 0
            if cached is not None and cached[0] == mt:
                return cached[1]
            _static_v_cache[fname] = (mt, mt)
            return mt
        u = current_user()
        # my_role 是"主角色"（显示用）；能不能进后台/工作台看 my_admin / my_dm
        # （一个人可以同时是 DM + 管理员，所以是三个独立的量，不是一个 my_role）
        return {'me': u, 'my_role': role(), 'my_roles': business.roles_of(u),
                'my_admin': business.has_role(u, 'admin'), 'my_dm': business.has_role(u, 'dm'),
                'settings': business.get_settings(),
                'unread': business.unread_count(u) if u else 0,
                'dev_env': business.is_dev_request(),      # 本机开发才显示"通用码 1234"这类提示
                # 在"客户端壳"里打开的？（电脑版 exe / 手机壳 App）—— 是的话就不显示"下载客户端"按钮
                'in_shell': bool(session.get('shell')),
                'ui_ver': business.ui_ver(),               # 这次渲染的是"一代"还是"二代"界面
                'ui_versions': business.UI_VERSIONS,
                'day_label': business.day_label, 'year': time.strftime('%Y'),
                'theme': request.cookies.get('theme') or 'light',     # 深浅色（存在 cookie 里；2026-09 起默认浅色）
                'static_v': static_v,
                'skins': business.SKINS}                           # 外观款式（后台统一切换全站）

    @app.context_processor
    def device_guess():
        """设备判定（手机端 / 电脑端）：决定加载哪套款式 + 是否叠手机原生布局层。

        优先级：网址 ?shell=mobile 已在 mark_shell() 记进 session；
        其次手机壳 App 的 UA 带 TianshuApp 标记；最后按 UA 平台兜底。
        """
        # 直接用请求头读 UA：比 werkzeug 的 user_agent 解析更稳（测试客户端也能拿到）
        ua = (request.headers.get('User-Agent') or '')
        is_mobile = (session.get('shell') == 'mobile'
                     or 'TianshuApp' in ua
                     or bool(_MOBILE_UA_RE.search(ua or '')))
        return {'is_mobile': is_mobile, 'device': 'mobile' if is_mobile else 'desktop'}

    @app.before_request
    def pick_ui():
        """一代 / 二代切换：真换了就把模板缓存清一次 ——
        Jinja 按"模板名"缓存编译结果，一/二代的名字是一样的（home.html），
        不清缓存的话切过去还是旧那套。"""
        v = business.ui_ver()
        env = app.jinja_env
        if getattr(env, '_ui_ver', None) != v:
            try:
                env.cache.clear()
            except Exception:
                pass
            env._ui_ver = v

    @app.before_request
    def mark_shell():
        """从**客户端壳**里进来的（网址带 ?shell=desktop）—— 记一笔。

        壳里（电脑版 exe / 手机壳 App）的用户已经在用客户端了，
        不该再看到「下载电脑版 / 装 App」这类按钮。记进 session 而不是网址：
        翻页、跳转都跟着走；然后把网址擦干净跳回去，客人看不到多余的参数。

        （手机壳 App 走的是 User-Agent 里的 TianshuApp 标记，见模板里的 in_app）
        """
        v = str(request.args.get('shell') or '').strip().lower()
        if v in ('desktop', 'app', 'mobile'):
            session['shell'] = 'mobile' if v == 'mobile' else 'desktop'
            rest = {k: val for k, val in request.args.items() if k != 'shell'}
            qs = urlencode(rest)
            return redirect(request.path + (('?' + qs) if qs else ''))

    @app.before_request
    def mobile_front():
        """手机端独立站分流：手机访客默认进 /m（与桌面站完全分开）。

        - 后台「门店设置 → 手机端方案」可切回 legacy（继续用旧的原生层 skin_mobile）；
        - 网址带 ?device=desktop 或曾经设过该覆盖，则留在桌面站（方便手机上预览桌面版）；
        - 后台 / 工作台 / 静态资源 / 健康检查 不受影响；/m 自身不重定向（防回环）。
        """
        p = request.path
        # ⚠️ /img 必须放行：它是"上传的图片"，不是页面。
        # 踩过的坑（2026-10）：手机 UA 请求 /img/cover/xxx.png 曾被这里 302 到 /m/，
        # 结果手机上所有图片都变成一段 HTML —— 电脑上正常、手机上全白。
        if p.startswith(('/m', '/static', '/img', '/health')):
            return
        if p.startswith(('/admin', '/dm')):
            return
        # 写操作绝不拦：手机端 POST /login 曾被这里 302 弹回 /m/，
        # 结果 session 永远建立不起来，登录永远显示"账号或密码有误"（2026-10 踩坑）
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return
        # 登录 / 注册 / 找回 / 个人中心这些页面手机用户也要能进
        # （手机端"去注册""忘密码"链接直接指过来，拦了就死循环）
        if p.startswith(('/login', '/register', '/forgot', '/logout', '/me',
                         '/notice', '/booking', '/order', '/review', '/profile',
                         '/account', '/code', '/car/')):
            return
        if request.args.get('device') == 'desktop':
            session['device_override'] = 'desktop'
            return
        if session.get('device_override') == 'desktop':
            return
        if business.get_settings().get('mobileMode', 'app') != 'app':
            return
        ua = request.headers.get('User-Agent') or ''
        is_mobile = ('TianshuApp' in ua) or bool(_MOBILE_UA_RE.search(ua or ''))
        if is_mobile and not p.startswith('/m'):
            # 跳 /m/（末尾斜杠）让浏览器的相对路径基准落在 /m/ 目录下
            return redirect('/m/')

    @app.before_request
    def csrf_guard():
        """CSRF 防护（double-submit cookie）：**写操作必须带上本站发的令牌**。

        这是"防别人替你操作"的关键一道：令牌放在一个只有本站页面能读到的 cookie 里，
        别的网站就算骗你点了提交，也读不到你的 cookie、造不出匹配的令牌 → 请求被拒。
        static/js/csrf.js 负责把令牌自动塞进页面里**所有**表单和 fetch，
        所以模板里的表单一个都不用改，以后新加的也自动被覆盖。

        顺带把真相说清楚：前端代码永远可以被改（F12 改的是他自己浏览器里的副本），
        所以真正的防线是——金额、人数、状态、权限全部由**服务端**重新计算和校验，
        前端传什么都只当参考。这条从设计上就是这么做 的。
        """
        g.csrf = request.cookies.get('csrf') or ''
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            # 小程序用 Bearer token 鉴权，与 Cookie/CSRF 无关，直接放行。
            from tianshu import mp
            if mp.valid_token_from_request():
                return
            # 埋点接口（桌面 /api/track、手机 /m/api/track）是页面加载后的匿名上报：
            # 用的是 navigator.sendBeacon，它**发不了自定义请求头**、也带不上表单字段，
            # 所以每个页面都会撞一次 403（控制台一片红，客人侧表现为"时不时报 403"）。
            # 它只记一个路径、不改任何数据，属于安全例外，这里放行。
            if request.path in _CSRF_FREE:
                return
            sent = request.form.get('_csrf') or request.headers.get('X-CSRF') or ''
            if not g.csrf or not secrets.compare_digest(str(sent), str(g.csrf)):
                # 自愈（2026-10）：从浏览器缓存 / 很久前开的标签页里翻出来的旧页面没带令牌，
                # 一提交就撞 403 —— 客人看到的是"这扇门只给店里人开"，其实只是页面放久了。
                # 只要浏览器里明明有令牌 cookie，就把他送回去刷新一次再点，别一棍子打死。
                # （cookie 都没有的才算真异常，仍走 403。）
                if g.csrf and not sent and request.referrer:
                    flash('页面放太久啦，已帮你刷新 —— 再点一次刚才那个按钮就好', 'warn')
                    return redirect(request.referrer)
                abort(403, '页面放太久，安全令牌对不上 —— 刷新一下页面再试')

    @app.after_request
    def csrf_issue(resp):
        """第一次来的访客还没有令牌：发一颗（跟登录一样长），之后的表单就都带着它"""
        if not g.get('csrf'):
            resp.set_cookie('csrf', secrets.token_hex(16), max_age=SESSION_DAYS * 86400,
                            samesite='Lax', httponly=False)   # 这颗故意让 JS 可读：它不是会话，泄了也无害
        # 页面一律不进缓存（2026-10）：不然「返回 / 历史记录」翻出的是很久以前的旧 HTML，
        # 表单里没有安全令牌，一提交就是 403 —— "网站动不动 403"多半是它。
        # 只限 HTML；图片 / css / js 静态资源照常缓存。
        if resp.mimetype == 'text/html' and resp.status_code == 200:
            resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.get('/health')
    def health():
        return jsonify(ok=True, mode='python-only')

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403, msg=getattr(e, 'description', '没有权限')), 403

    @app.errorhandler(404)
    def notfound(e):
        return render_template('error.html', code=404, msg='这个页面不存在，可能链接过期了'), 404

    @app.errorhandler(413)
    def too_big(e):
        return render_template('error.html', code=413,
                               msg='文件太大了 —— 单张图最大 683KB，表单整体别超过 4MB。'
                                   '新版的网页会自动帮你压图，刷新一下再传试试'), 413

    @app.errorhandler(500)
    def broken(e):
        return render_template('error.html', code=500, msg='服务端出了点问题，看下黑窗口的报错'), 500

    @app.after_request
    def _gzip(resp):
        """文本响应 gzip 压缩（标准库 gzip，不引第三方）。

        首页 HTML ~40KB，开 gzip 后约 9KB，省 75% 下载体积。
        只压 text/* / json / javascript；图片（/img、png/jpg/webp）本身已压缩，跳过。"""
        try:
            if 'gzip' not in (request.headers.get('Accept-Encoding') or '').lower():
                return resp
            if resp.headers.get('Content-Encoding'):
                return resp                       # 已经压过（比如 Caddy 外层压了），别压两遍
            ct = (resp.headers.get('Content-Type') or '').lower()
            if not (ct.startswith('text/') or 'json' in ct or 'javascript' in ct or 'svg' in ct):
                return resp
            data = resp.get_data()
            if len(data) < 1024:
                return resp                       # 太小的压了不划算
            resp.set_data(gzip.compress(data, 6))
            resp.headers['Content-Encoding'] = 'gzip'
            resp.headers['Content-Length'] = len(resp.get_data())
            vary = resp.headers.get('Vary')
            if 'Accept-Encoding' not in (vary or ''):
                resp.headers['Vary'] = ((vary + ', ') if vary else '') + 'Accept-Encoding'
        except Exception:
            pass
        return resp

    @app.teardown_request
    def _flush_buffers(exc=None):
        """请求结束：把 business.notify / business.audit 在本次请求里攒下的多条写盘合并成一次。

        （一个预约动作会 notify(客人)+notify_staff(员工们)+好几条 audit，原来每条都整份重写大 JSON。）"""
        try:
            business.flush_notices()
            business.flush_logs()
        except Exception as e:
            print('[flush] 通知/日志落盘失败：%s: %s' % (type(e).__name__, e))

    return app
