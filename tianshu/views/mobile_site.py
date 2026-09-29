# -*- coding: utf-8 -*-
"""手机端独立站（v2）：一套**完全独立**的静态移动站点，不碰任何数据库 / 业务层。

   桌面站（tianshu 模板 + business.py）保持原样不动；
   这里只负责把 mobile/ 目录下的静态文件（index.html / styles.css / app.js / data.js）
   原样吐出去，给手机访客一个从零按设计文档搭的原生移动体验。

   路由：
     /m             → 手机端首页（index.html）
     /m/<path>      → 静态资源（styles.css / app.js / data.js …）
"""
import os

from flask import Blueprint, Response, current_app, send_from_directory

bp = Blueprint("mobile_site", __name__)

# mobile/ 在仓库根目录（与 tianshu/ 同级），按本文件位置向上反推
_MOBILE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "mobile"))

# 简单的内容类型，避免依赖 Flask 的复杂猜测
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
}


@bp.get("/m")
@bp.get("/m/")
def mobile_index():
    # 关掉桌面站的 CSRF 挑战对静态页无意义；这里就是纯静态
    resp = Response(_read("index.html"), mimetype="text/html; charset=utf-8")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/m/<path:filename>")
def mobile_asset(filename):
    # 只允许文件级访问，阻止目录穿越
    full = os.path.normpath(os.path.join(_MOBILE_DIR, filename))
    if not full.startswith(_MOBILE_DIR) or not os.path.isfile(full):
        return Response("not found", status=404)
    ext = os.path.splitext(full)[1].lower()
    mime = _MIME.get(ext, "application/octet-stream")
    resp = Response(_read(filename), mimetype=mime)
    # 静态资源可缓存（改完靠文件名 ?v= 控制，这里直接长缓存）
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


def _read(filename):
    with open(os.path.join(_MOBILE_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()
