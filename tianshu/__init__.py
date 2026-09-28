# -*- coding: utf-8 -*-
"""
应用工厂：把整站拼起来的地方（Flask 官方推荐的写法，方便以后拆模块、写测试）

    from tianshu import create_app
    app = create_app()
"""
import os
from datetime import timedelta

from flask import Flask, jsonify, render_template

from config import IMG_DIR, ROOMS_DEFAULT, SEED_USERS, SESSION_DAYS, SETTINGS_DEFAULT, TEMPLATES_AUTO_RELOAD
from tianshu import business
from tianshu.db import db
from tianshu.security import current_user, hash_password, role, session_secret


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
    app.secret_key = session_secret()
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,          # 表单别传太大（图片走单独上传）
        TEMPLATES_AUTO_RELOAD=TEMPLATES_AUTO_RELOAD,  # 热重载会拖慢每个请求，默认关；开发用 --dev
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
        u = current_user()
        return {'me': u, 'my_role': role(), 'settings': business.get_settings(),
                'unread': business.unread_count(u) if u else 0,
                'dev_env': business.is_dev_request(),      # 本机开发才显示"通用码 1234"这类提示
                'day_label': business.day_label, 'year': _t.strftime('%Y'),
                'theme': _req.cookies.get('theme') or 'light'}     # 深浅色（存在 cookie 里；2026-09 起默认浅色）

    @app.get('/health')
    def health():
        return jsonify(ok=True, mode='python-only')

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403, msg=getattr(e, 'description', '没有权限')), 403

    @app.errorhandler(404)
    def notfound(e):
        return render_template('error.html', code=404, msg='这个页面不存在，可能链接过期了'), 404

    @app.errorhandler(500)
    def broken(e):
        return render_template('error.html', code=500, msg='服务端出了点问题，看下黑窗口的报错'), 500

    return app
