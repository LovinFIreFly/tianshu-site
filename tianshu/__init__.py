# -*- coding: utf-8 -*-
"""
应用工厂：把整站拼起来的地方（Flask 官方推荐的写法，方便以后拆模块、写测试）

    from tianshu import create_app
    app = create_app()
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, abort, g, jsonify, render_template, request
from jinja2 import BaseLoader, FileSystemLoader, TemplateNotFound

from config import IMG_DIR, ROOMS_DEFAULT, SEED_USERS, SESSION_DAYS, SETTINGS_DEFAULT, TEMPLATES_AUTO_RELOAD
from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, hash_password, role, session_secret


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
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,          # 表单别传太大（图片走单独上传）
        TEMPLATES_AUTO_RELOAD=TEMPLATES_AUTO_RELOAD,  # 热重载会拖慢每个请求，默认关；开发用 --dev
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

    @app.context_processor
    def inject_globals():
        """模板里到处都要用的东西，统一塞进去（省得每个视图都传一遍）"""
        import time as _t

        from flask import request as _req

        def static_v(fname):
            """静态文件版本号 = 文件的修改时间。文件一改，URL 就变（?v=1695…），
            浏览器立刻拉新版 —— 否则手机上老缓存不更新，"明明改了却没变化"（2026-09 用户被坑过）。"""
            import os as _os
            try:
                return int(_os.stat(_os.path.join(app.static_folder, fname)).st_mtime)
            except OSError:
                return 0
        u = current_user()
        # my_role 是"主角色"（显示用）；能不能进后台/工作台看 my_admin / my_dm
        # （一个人可以同时是 DM + 管理员，所以是三个独立的量，不是一个 my_role）
        return {'me': u, 'my_role': role(), 'my_roles': business.roles_of(u),
                'my_admin': business.has_role(u, 'admin'), 'my_dm': business.has_role(u, 'dm'),
                'settings': business.get_settings(),
                'unread': business.unread_count(u) if u else 0,
                'dev_env': business.is_dev_request(),      # 本机开发才显示"通用码 1234"这类提示
                'ui_ver': business.ui_ver(),               # 这次渲染的是"一代"还是"二代"界面
                'ui_versions': business.UI_VERSIONS,
                'day_label': business.day_label, 'year': _t.strftime('%Y'),
                'theme': _req.cookies.get('theme') or 'light',     # 深浅色（存在 cookie 里；2026-09 起默认浅色）
                'static_v': static_v,
                'skins': business.SKINS}                           # 外观款式（后台统一切换全站）

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
            sent = request.form.get('_csrf') or request.headers.get('X-CSRF') or ''
            if not g.csrf or not secrets.compare_digest(str(sent), str(g.csrf)):
                abort(403, '页面放太久，安全令牌对不上 —— 刷新一下页面再试')

    @app.after_request
    def csrf_issue(resp):
        """第一次来的访客还没有令牌：发一颗（跟登录一样长），之后的表单就都带着它"""
        if not g.get('csrf'):
            resp.set_cookie('csrf', secrets.token_hex(16), max_age=SESSION_DAYS * 86400,
                            samesite='Lax', httponly=False)   # 这颗故意让 JS 可读：它不是会话，泄了也无害
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

    return app
