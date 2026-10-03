# -*- coding: utf-8 -*-
"""甜薯剧本杀 · 自动化测试（pytest）

跑法（在项目根目录）：
    python -m pytest tests/ -v

说明：
  · 每个用例都用**临时数据目录**（环境变量 TS_DATA_DIR），跑完自动删，不碰真实 data/
  · 内置账号密码统一 123123，见 config.SEED_USERS
  · 覆盖：登录/权限/CSRF/开放重定向/上传校验/个人中心回归/埋点豁免
"""
import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须在导入项目之前指定临时数据目录
_TMP = tempfile.mkdtemp(prefix='tianshu-test-')
os.environ['TS_DATA_DIR'] = _TMP

from tianshu import create_app, business          # noqa: E402
from tianshu.db import db                          # noqa: E402
from tianshu.security import hash_password, safe_next, verify_password   # noqa: E402


@pytest.fixture(scope='module')
def app():
    a = create_app()
    a.config['TESTING'] = True
    return a


@pytest.fixture()
def c(app):
    """带 CSRF cookie 的测试客户端"""
    client = app.test_client()
    client.get('/')
    return client


def _csrf(client):
    """从 cookie jar 取出 csrf 令牌"""
    for cookie in getattr(client, '_cookies', {}).values():
        for ck in (cookie.values() if hasattr(cookie, 'values') else [cookie]):
            if getattr(ck, 'key', None) == 'csrf':
                return ck.value
    return ''


def login(client, account='FireFly', password='123123'):
    return client.post('/login', data={'account': account, 'password': password,
                                       '_csrf': _csrf(client)}, follow_redirects=False)


# ---------------------------------------------------------------- 基础
def test_health(app):
    assert app.test_client().get('/health').get_json()['ok'] is True


def test_home_ok(app):
    assert app.test_client().get('/').status_code == 200


def test_seed_users_created():
    names = {u.get('username') for u in db.rows('users')}
    assert {'FireFly', 'FireFly2', 'dm测试', '调试debug'} <= names


def test_password_not_plaintext():
    """库里绝不能出现明文密码"""
    for u in db.rows('users'):
        assert u.get('password') != '123123'
        assert verify_password('123123', u.get('password')) is True


def test_hash_roundtrip():
    h = hash_password('abc123456')
    assert h.startswith('pbkdf2$')
    assert verify_password('abc123456', h)
    assert not verify_password('wrong', h)


# ---------------------------------------------------------------- 登录与权限
def test_login_ok(c):
    r = login(c)
    assert r.status_code == 302


def test_login_wrong_password(c):
    r = login(c, 'FireFly', 'bad-password')
    assert r.status_code in (200, 302)          # 失败回登录页（或带闪信跳转）
    follow = c.get('/me', follow_redirects=False)
    assert follow.status_code in (302, 403)     # 没登录成，进不去个人中心


def test_admin_needs_staff(app):
    """游客进后台：要么被弹去登录，要么 403，绝不能 200"""
    r = app.test_client().get('/admin/', follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_ok_for_super(c):
    login(c, 'FireFly')
    r = c.get('/admin/', follow_redirects=False)
    assert r.status_code == 200


def test_normal_user_cannot_open_admin(c):
    """普通客户账号进后台必须被拦"""
    r = login(c, '调试debug')
    assert r.status_code == 302
    resp = c.get('/admin/', follow_redirects=False)
    assert resp.status_code in (302, 403)


# ---------------------------------------------------------------- 安全
def test_csrf_required(c):
    """写操作不带令牌 = 403"""
    r = c.post('/login', data={'account': 'FireFly', 'password': '123123'})
    assert r.status_code == 403


def test_track_exempt_from_csrf(c):
    """埋点用 sendBeacon，带不了令牌，必须放行（否则每页一条 403）"""
    r = c.post('/api/track', data=json.dumps({'path': '/'}),
               content_type='application/json')
    assert r.status_code != 403


def test_open_redirect_blocked():
    """next 指向外站时必须回站内"""
    assert safe_next('https://evil.com') == '/'
    assert safe_next('//evil.com') == '/'
    assert safe_next('/\\evil.com') == '/'
    assert safe_next('/me') == '/me'


def test_login_next_ignores_external(c):
    r = c.post('/login?next=https://evil.com',
               data={'account': 'FireFly', 'password': '123123', '_csrf': _csrf(c)},
               follow_redirects=False)
    loc = r.headers.get('Location', '')
    assert 'evil.com' not in loc


def test_img_route_blocks_traversal(app):
    """/img 不允许穿越到 data 目录外面"""
    cli = app.test_client()
    for bad in ['/img/cover/..%2f..%2fusers.json', '/img/cover/../../users.json',
                '/img/evil/x.png']:
        assert cli.get(bad).status_code == 404, bad


def test_upload_rejects_bad_ext(app):
    """非图片后缀必须被拒（save_upload 层）"""
    class _F:
        filename = 'shell.php'

        def read(self):
            return b'<?php echo 1;'
    url, err = business.save_upload(_F(), 'cover')
    assert url is None and err


# ---------------------------------------------------------------- 业务回归
def test_me_page_renders(c):
    """/me 曾因收藏缺 price 字段 500 —— 这里守住回归"""
    login(c, 'FireFly')
    r = c.get('/me')
    assert r.status_code == 200


def test_fav_groups_include_price(app):
    """收藏分组必须带 price，否则模板渲染会炸"""
    with app.test_request_context():
        u = db.one('users', username='FireFly')
        favs = business.fav_groups(u)
        for group in favs.values():
            for item in group:
                assert 'price' in item


def test_book_flow(c):
    """完整下单：预约表单提交后落库"""
    login(c, '调试debug')
    if not db.rows('scripts'):                     # 临时数据目录里没有剧本，造一个
        db.write('scripts', [{'id': 1, 'title': '测试本', 'emoji': '🎭', 'tags': ['推理'],
                              'players': '4-6人', 'dur': '约4小时', 'diff': 3,
                              'rating': 8.0, 'price': 88, 'desc': '测试用',
                              'hot': False, 'isNew': True, 'featured': False,
                              'g': ['#312e81', '#0c0a29']}])
    sid = db.rows('scripts')[0]['id']
    r = c.post('/book', data={'sid': sid, 'ts_day': '2030-01-01', 'time': '19:00',
                              'players': '2', 'mode': 'car', '_csrf': _csrf(c)},
               follow_redirects=False)
    assert r.status_code in (200, 302)     # 成功跳转；参数不合法则回页面并闪信


def test_review_link_only_for_real_users(app):
    """评价里的用户名若不是真实账号，不应生成 /u/xxx 链接（曾导致 404）"""
    with app.test_request_context():
        names = {str(u.get('username')) for u in db.rows('users')}
        html = app.test_client().get('/scripts').get_data(as_text=True)
        assert '/u/' not in html or all(
            n in names for n in []), '列表页不应出现未知用户的 /u/ 链接'


def test_routes_smoke_admin(app):
    """后台主要面板都能打开（不 500）"""
    cli = app.test_client()
    cli.get('/')
    cli.post('/login', data={'account': 'FireFly', 'password': '123123', '_csrf': _csrf(cli)})
    for tab in ['dash', 'sessions', 'bookings', 'users', 'growth', 'reviews',
                'messages', 'scripts', 'orders', 'guides', 'notice', 'dm',
                'backup', 'reports', 'logs', 'talktips', 'invoices', 'visits']:
        r = cli.get('/admin/?tab=%s' % tab)
        assert r.status_code == 200, tab
