# -*- coding: utf-8 -*-
"""微信小程序接入层：登录换 openid、令牌签发与校验、订阅消息推送。

依赖：
  - config.py: MP_APPID, MP_SECRET, MP_TMPL_*
  - db.py: mp_tokens、mp_access_token 两张表（JSON 文件）
  - security.py: verify_password（绑定账号时校验密码）

不引入第三方依赖，连微信 API 用标准库 urllib，避免污染 requirements。
"""
import json
import secrets
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import MP_APPID, MP_SECRET
from tianshu.db import db
from tianshu.security import verify_password

_TOKEN_TTL = 90 * 86400          # 小程序登录令牌 90 天
_ACCESS_TTL = 7000               # 微信 access_token 缓存 7000 秒（微信有效期 7200 秒）


def _wx_api(path, params=None, payload=None):
    """向微信 API 发 GET（params）或 POST（payload）。返回 JSON 字典。"""
    url = 'https://api.weixin.qq.com' + path
    if params:
        url += '?' + urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = Request(url, data=data,
                  headers={'Content-Type': 'application/json'} if payload else {})
    with urlopen(req, timeout=10) as r:
        body = r.read().decode('utf-8')
        return json.loads(body) if body else {}


def jscode2session(code):
    """用 wx.login 拿到的临时 code 换 openid/session_key。

    返回 (openid, None) 成功；返回 (None, err_msg) 失败。
    """
    if not MP_SECRET:
        return None, '小程序 AppSecret 未配置（config.py 里的 MP_SECRET）'
    try:
        out = _wx_api('/sns/jscode2session', {
            'appid': MP_APPID, 'secret': MP_SECRET,
            'js_code': code, 'grant_type': 'authorization_code'})
    except Exception as e:
        return None, '微信接口请求失败：%s' % e
    if out.get('errcode'):
        return None, '微信返回错误：%s %s' % (out.get('errcode'), out.get('errmsg'))
    if out.get('openid'):
        return out['openid'], None
    return None, '微信未返回 openid，请重试'


def _tokens_table():
    """读取 mp_tokens 表；没有则返回空列表。"""
    try:
        return list(db.rows('mp_tokens') or [])
    except Exception:
        return []


def _save_tokens(rows):
    db.write('mp_tokens', rows)


def clean_expired_tokens():
    """清理过期令牌；每次签新令牌时顺带跑。"""
    now = time.time()
    rows = [t for t in _tokens_table() if t.get('expires', 0) > now]
    _save_tokens(rows)


def issue_token(phone, openid='', days=90):
    """给用户签发一个长期访问令牌，后续小程序用 Bearer 调接口。"""
    clean_expired_tokens()
    token = secrets.token_urlsafe(32)
    rows = _tokens_table()
    rows.append({
        'token': token, 'phone': str(phone), 'openid': openid or '',
        'expires': time.time() + days * 86400,
    })
    _save_tokens(rows)
    return token


def phone_from_token(token):
    """校验令牌，返回手机号；过期/不存在返回 None。"""
    if not token:
        return None
    now = time.time()
    for t in _tokens_table():
        if t.get('token') == token and t.get('expires', 0) > now:
            return t.get('phone')
    return None


def valid_token_from_request():
    """从当前请求 Authorization: Bearer <token> 中解析并校验；
    若合法，返回 phone；否则返回 None。"""
    auth = (request.headers.get('Authorization') or '').strip()
    if not auth.lower().startswith('bearer '):
        return None
    return phone_from_token(auth[7:].strip())


def _access_token():
    """获取/刷新微信小程序接口的 access_token（全局接口调用凭证）。"""
    if not MP_SECRET:
        return None, 'MP_SECRET 未配置'
    rec = None
    try:
        rec = db.read('mp_access_token')
    except Exception:
        pass
    if rec and rec.get('token') and rec.get('expires', 0) > time.time() + 60:
        return rec['token'], None
    try:
        out = _wx_api('/cgi-bin/token', {
            'grant_type': 'client_credential', 'appid': MP_APPID, 'secret': MP_SECRET})
    except Exception as e:
        return None, '获取 access_token 失败：%s' % e
    if out.get('errcode'):
        return None, '获取 access_token 失败：%s %s' % (out.get('errcode'), out.get('errmsg'))
    token = out.get('access_token')
    if not token:
        return None, '微信未返回 access_token'
    db.write('mp_access_token', {'token': token, 'expires': time.time() + out.get('expires_in', 7200)})
    return token, None


def send_subscribe(openid, template_id, page, data):
    """发送订阅消息。

    参数：
      openid:      用户 openid
      template_id: 小程序后台申请的模板 ID
      page:        点击消息卡片跳转的页面路径（如 pages/index/index）
      data:        模板对应的关键字数据字典，如 {"thing1": {"value": "恐怖本"}}
    返回 (True, None) 或 (False, err_msg)。
    """
    if not template_id or not openid:
        return False, '缺少 template_id 或 openid'
    access_token, err = _access_token()
    if err:
        return False, err
    payload = {
        'touser': openid,
        'template_id': template_id,
        'page': page,
        'data': data,
    }
    try:
        out = _wx_api('/cgi-bin/message/subscribe/send',
                      params={'access_token': access_token}, payload=payload)
    except Exception as e:
        return False, '发送失败：%s' % e
    if out.get('errcode'):
        # 43101 = 用户拒绝订阅；这是正常业务，不报错但返回 False
        return False, '微信返回：%s %s' % (out.get('errcode'), out.get('errmsg'))
    return True, None


# 顶部延迟导入 request，避免循环导入
from flask import request  # noqa: E402
