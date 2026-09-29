# -*- coding: utf-8 -*-
"""手机端独立站（v2）：一套**完全独立**的静态移动站点（UI / 模板 / 样式都不碰桌面站）。

   与桌面站的区别只在「界面与样式」—— 数据通过下面这组只读 JSON 接口接回真实的
   business 层（剧本库 / 今日场次 / 拼车大厅 / 我的），不引入任何桌面模板或样式。

   路由：
     /m                 → 手机端首页（index.html）
     /m/<path>          → 静态资源（styles.css / app.js / data.js …）
     /m/api/scripts     → 剧本库（支持 ?q=&tag=&diff= 筛选）
     /m/api/sessions    → 今日开演 / 组局
     /m/api/cars        → 拼车大厅
     /m/api/me          → 当前登录用户（未登录返回 {guest:true}）
"""
import os
import re

from flask import Blueprint, Response, current_app, jsonify, request
from tianshu import business
from tianshu.db import db
from tianshu.security import current_user

bp = Blueprint("mobile_site", __name__)

# mobile/ 在仓库根目录（与 tianshu/ 同级），按本文件位置向上反推
_MOBILE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "mobile"))

# 剧本封面缺渐变时，按 id 给一个稳定好看的深色渐变（烛光暖调，和品牌一致）
_GRADS = [
    "linear-gradient(160deg,#3a2b4d,#15131f)",
    "linear-gradient(160deg,#1f3a4d,#0f1b22)",
    "linear-gradient(160deg,#4d3a2b,#221a13)",
    "linear-gradient(160deg,#2b4d3a,#13221a)",
    "linear-gradient(160deg,#4d3b1f,#221a0f)",
    "linear-gradient(160deg,#2b2b4d,#131322)",
    "linear-gradient(160deg,#3a1f1f,#1a0f0f)",
    "linear-gradient(160deg,#1f2f4d,#0f1622)",
]


def _grad(i):
    return _GRADS[(int(i) if str(i).isdigit() else 0) % len(_GRADS)]


def _mask_phone(p):
    p = str(p or "")
    return (p[:3] + "****" + p[-4:]) if len(p) >= 7 else p


def _norm_script(s):
    return {
        "id": s.get("id"),
        "emoji": s.get("emoji") or "🎭",
        "title": s.get("title") or "未命名剧本",
        "tags": list(s.get("tags") or []),
        "players": s.get("players") or s.get("cap") or "—",
        "duration": s.get("duration") or "—",
        "difficulty": s.get("diff") or "—",
        "price": s.get("price") or 0,
        "hot": bool(s.get("hot") or s.get("isNew")),
        "desc": s.get("desc") or "",
        "grad": s.get("grad") or _grad(s.get("id") or 0),
    }


@bp.get("/m/api/scripts")
def api_scripts():
    q = (request.args.get("q") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip()
    diff = (request.args.get("diff") or "").strip()
    rows = []
    for s in db.rows("scripts"):
        if s.get("onSale") is False:
            continue
        if q and q not in str(s.get("title", "")).lower() and q not in str(s.get("desc", "")).lower():
            continue
        if tag and tag not in (s.get("tags") or []):
            continue
        if diff and str(s.get("diff")) != diff:
            continue
        rows.append(_norm_script(s))
    return jsonify(rows)


@bp.get("/m/api/sessions")
def api_sessions():
    rooms = {str(r.get("id")): r for r in db.rows("rooms")}
    out = []
    for s in business.today_sessions():
        rid = str(s.get("roomId"))
        room = rooms.get(rid) or {}
        out.append({
            "id": s.get("id"),
            "time": s.get("time") or "",
            "name": s.get("title") or "未命名场次",
            "room": "%s · %s座" % (room.get("name") or "房间", room.get("cap") or s.get("cap") or ""),
            "cap": s.get("cap") or 0,
            "have": s.get("joined") or 0,
            "script": s.get("sid"),
        })
    return jsonify(out)


@bp.get("/m/api/cars")
def api_cars():
    u = current_user()
    me_phone = u.get("phone") if u else ""
    users = {str(x.get("phone")): x for x in db.rows("users")}
    out = []
    for c in business.car_pool(me_phone):
        owner = users.get(str(c.get("owner"))) if c.get("owner") else None
        prof = (owner or {}).get("profile") or {}
        av = prof.get("avatar") or ((owner or {}).get("username") or "🎭")
        # 头像若是图片地址就用原值；否则当文字（首字 / emoji）
        if not (str(av).startswith("/img/") or str(av).startswith("http")):
            av = str(av)[:1]
        note = "%d 人已上车 · 还差 %d 人发车" % (c.get("joined") or 0, c.get("need") or 0)
        out.append({
            "id": c.get("id"),
            "who": c.get("owner") or "玩家",
            "av": av,
            "script": c.get("title") or "剧本",
            "time": "%s %s" % (c.get("day") or "", c.get("time") or ""),
            "have": c.get("joined") or 0,
            "need": c.get("need") or 0,
            "tags": list(c.get("tags") or []),
            "note": note,
            "full": bool(c.get("full")),
        })
    return jsonify(out)


@bp.get("/m/api/me")
def api_me():
    u = current_user()
    if not u:
        return jsonify({"guest": True})
    phone = u.get("phone") or ""
    prof = u.get("profile") or {}
    bookings = [b for b in db.rows("bookings")
                if str(b.get("phone")) == str(phone) and b.get("status") != "cancelled"]
    reviews = [r for r in db.rows("reviews") if r.get("username") == u.get("username")]
    spent = sum(int(p.get("deposit") or 0) for p in db.rows("pays")
                if str(p.get("phone")) == str(phone) and p.get("status") == "paid")
    avatar = prof.get("avatar") or u.get("username") or "🦋"
    if not (str(avatar).startswith("/img/") or str(avatar).startswith("http")):
        initial = str(avatar)[:1]
    else:
        initial = avatar
    return jsonify({
        "guest": False,
        "name": prof.get("nick") or u.get("username") or "玩家",
        "initial": initial,
        "phone": _mask_phone(phone),
        "id": u.get("invite") or "",
        "credit": u.get("credit") or 0,
        "stats": {"bookings": len(bookings), "reviews": len(reviews), "spent": spent},
    })


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
