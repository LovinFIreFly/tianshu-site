# -*- coding: utf-8 -*-
"""
安全相关：密码怎么存、谁能进后台、防止有人疯狂试密码

这里的东西别随手改，改错了全站登不上（尤其是 hash_password 的格式，
要和线上老账号兼容：老格式是 'h' 开头的弱哈希，登录成功后自动升级成 pbkdf2）。
"""
import hashlib
import hmac
import os
import secrets
import time
from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from config import SECRET_FILE
from tianshu.db import db

# ---------------------------------------------------------------- 密码
PBKDF2_ROUNDS = 100000


def hash_password(pw):
    """存密码：随机盐 + PBKDF2-SHA256。库里永远不该出现明文密码"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return 'pbkdf2$%d$%s$%s' % (PBKDF2_ROUNDS, salt, dk.hex())


def legacy_hash(p):
    """老账号用的弱哈希，只为兼容，见文件头说明"""
    h = 5381
    for ch in p:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return 'h' + format(h, 'x')


def verify_password(pw, stored):
    s = str(stored or '')
    if s.startswith('pbkdf2$'):
        try:
            _, rounds, salt, _ = s.split('$')
            dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), int(rounds))
            return hmac.compare_digest('pbkdf2$%s$%s$%s' % (rounds, salt, dk.hex()), s)
        except Exception:
            return False
    return legacy_hash(pw) == s


def session_secret():
    """会话签名密钥：首次运行生成一个，存在 data/secret.key（别外传）"""
    os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, 'w', encoding='utf-8') as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_FILE, 'r', encoding='utf-8') as f:
        return f.read().strip()


# ---------------------------------------------------------------- 限流
_RL = {}


def rate(key, limit, window_ms):
    """同一个 key 在窗口期内最多来几次（防暴力试密码）"""
    now = int(time.time() * 1000)
    arr = [t for t in _RL.get(key, []) if now - t < window_ms]
    if len(arr) >= limit:
        _RL[key] = arr
        return False
    arr.append(now)
    _RL[key] = arr
    return True


def rate_peek(key, window_ms):
    """只看次数不计数（登录用：成功就清零，别让正常用户被自己人挤掉）"""
    now = int(time.time() * 1000)
    arr = [t for t in _RL.get(key, []) if now - t < window_ms]
    _RL[key] = arr
    return len(arr)


def rate_clear(*keys):
    for k in keys:
        _RL.pop(k, None)


# ---------------------------------------------------------------- 身份
def current_user():
    """当前登录的账号（没登录返回 None）。一次请求只查一次库"""
    if not hasattr(g, '_user'):
        phone = session.get('phone')
        g._user = db.one('users', phone=phone) if phone else None
        if g._user and g._user.get('banned'):          # 被拉黑的当场踢下线
            session.clear()
            g._user = None
    return g._user


def role():
    u = current_user()
    if not u:
        return 'guest'
    return 'super' if (u.get('super') is True or u.get('role') == 'super') else (u.get('role') or 'user')


def is_staff():
    return role() in ('admin', 'super')


def is_dm():
    return role() in ('dm', 'admin', 'super')


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for('user.login', next=request.path))
        return view(*a, **kw)
    return wrapper


def staff_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for('user.login', next=request.path))
        if not is_staff():
            abort(403, '这块只有员工能进')
        return view(*a, **kw)
    return wrapper
