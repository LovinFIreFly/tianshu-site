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
import time

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


def _ago(ts):
    """毫秒时间戳 → 友好相对时间（唠嗑区用）"""
    if not ts:
        return ""
    s = (int(time.time() * 1000) - int(ts)) // 1000
    if s < 60:
        return "刚刚"
    if s < 3600:
        return "%d 分钟前" % (s // 60)
    if s < 86400:
        return "%d 小时前" % (s // 3600)
    if s < 86400 * 7:
        return "%d 天前" % (s // 86400)
    return time.strftime("%m-%d", time.localtime(ts / 1000))


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
        "cover": s.get("cover") or s.get("img") or "",
        "grad": s.get("grad") or _grad(s.get("id") or 0),
        "allowRolePick": bool(s.get("allowRolePick")),
        "roles": [r.get("name") for r in (s.get("roles") or []) if r.get("name")],
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


def _script_titles():
    return {str(x.get("id")): x.get("title") or "剧本" for x in db.rows("scripts")}


@bp.get("/m/api/sessions")
def api_sessions():
    """今日或指定日期场次，带余位。date=YYYY-MM-DD"""
    day = request.args.get("date")
    try:
        ts = business.parse_day(day) if day else business.midnight()
    except Exception:
        ts = business.midnight()
    rooms = {str(r.get("id")): r for r in db.rows("rooms")}
    titles = _script_titles()
    out = []
    for s in business.sessions_of(ts):
        rid = str(s.get("roomId"))
        room = rooms.get(rid) or {}
        cap = s.get("cap") or 0
        joined = s.get("joined") or 0
        out.append({
            "id": s.get("id"),
            "ts": s.get("ts"),
            "time": s.get("time") or "",
            "name": s.get("title") or "未命名场次",
            "room": "%s · %s座" % (room.get("name") or "房间", cap or ""),
            "cap": cap,
            "have": joined,
            "left": max(0, cap - joined),
            "sid": s.get("sid"),
            "script": titles.get(str(s.get("sid")), "剧本"),
        })
    return jsonify({"date": business.day_label(ts), "sessions": out})


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
            "sid": c.get("sid"),
            "who": c.get("owner") or "玩家",
            "av": av,
            "script": c.get("title") or "剧本",
            "time": "%s %s" % (c.get("day") or "", c.get("time") or ""),
            "have": c.get("joined") or 0,
            "cap": c.get("cap") or 8,
            "need": c.get("need") or 0,
            "price": c.get("price") or 0,
            "tags": list(c.get("tags") or []),
            "members": [m.get("nick") or "玩家" for m in (c.get("members") or [])][:8],
            "note": note,
            "full": bool(c.get("full")),
            "mine": bool(c.get("mine")),
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
    recs = []
    _titles = {str(x.get("id")): x.get("title") for x in db.rows("scripts")}
    _stmap = {"booked": "待开演", "arrived": "已入场", "done": "已结束", "cancelled": "已取消"}
    pays = db.rows("pays")
    my_reviews = [r for r in db.rows("reviews") if r.get("username") == u.get("username")]
    for b in db.rows("bookings"):
        if str(b.get("phone")) != str(phone):
            continue
        status = b.get("status") or "booked"
        pay = next((p for p in pays if str(p.get("bid")) == str(b.get("id"))), None)
        pay_status = (pay or {}).get("status") or "unpaid"
        reviewed = any(str(r.get("sid")) == str(b.get("sid"))
                       and (r.get("createdAt") or 0) > (b.get("createdAt") or 0) for r in my_reviews)
        recs.append({
            "id": b.get("id"),
            "sid": b.get("sid"),
            "emoji": b.get("emoji") or "🎭",
            "name": b.get("title") or _titles.get(str(b.get("sid")) or "", "剧本"),
            "day": b.get("day") or business.day_label(b.get("ts")),
            "time": b.get("time") or "",
            "players": b.get("players") or 1,
            "mode": b.get("mode") or ("拼车" if b.get("carNew") else ""),
            "state": _stmap.get(status, status),
            "raw": status,
            "amount": b.get("amount") or 0,
            "deposit": b.get("deposit") or 0,
            "payStatus": pay_status,
            "code": str(b.get("verifyCode") or "") if pay_status == "paid" else "",
            "reviewed": reviewed,
            "cancelable": status == "booked",
        })
    now = business.now_ms()
    coupons = [c for c in db.rows("coupons")
               if str(c.get("phone")) == str(phone) and not c.get("used") and (c.get("exp") or 0) > now]
    orders = []
    for o in sorted([x for x in db.rows("pays") if str(x.get("phone")) == str(phone)],
                    key=lambda x: -(x.get("id") or 0))[:20]:
        orders.append({
            "id": o.get("id"), "bid": o.get("bid"), "title": o.get("title") or "剧本",
            "day": o.get("day") or "", "time": o.get("time") or "", "players": o.get("players") or 1,
            "amount": o.get("amount") or 0, "deposit": o.get("deposit") or 0,
            "payable": o.get("payable") or 0, "status": o.get("status") or "unpaid",
        })
    favs = []
    for r in db.rows("favs"):
        if str(r.get("phone")) == str(phone):
            favs = [str(x) for x in (r.get("sids") or [])]
    notices = []
    try:
        for n in business.my_notices(u, 20):
            notices.append({
                "id": n.get("id"), "title": n.get("title") or "通知",
                "body": n.get("body") or "", "at": _ago(n.get("at")), "read": bool(n.get("read")),
            })
    except Exception:
        notices = []
    return jsonify({
        "guest": False,
        "name": prof.get("nick") or u.get("username") or "玩家",
        "initial": initial if not (str(initial).startswith("/img/") or str(initial).startswith("http")) else "",
        "avatar": avatar if (str(avatar).startswith("/img/") or str(avatar).startswith("http")) else "",
        "phone": _mask_phone(phone),
        "id": u.get("invite") or "",
        "credit": u.get("credit") or 0,
        "staff": business.role_of(u) in ("admin", "staff", "dm") or bool(u.get("super")),
        "profile": {"nick": prof.get("nick") or "", "gender": prof.get("gender") or "", "age": prof.get("age") or ""},
        "coupons": [{"id": c.get("id"), "name": c.get("name") or c.get("from") or "抵扣券", "amount": c.get("amount") or 0} for c in coupons],
        "orders": orders,
        "favs": favs,
        "notices": notices,
        "stats": {"bookings": len(bookings), "reviews": len(reviews), "spent": spent},
        "records": recs[:20],
    })


@bp.get("/m/api/talks")
def api_talks():
    """唠嗑区：社区帖子（公开可读）"""
    out = []
    for p in business.community_posts(60):
        out.append({
            "id": p.get("id"),
            "name": p.get("nick") or p.get("username") or "玩家",
            "avatar": p.get("avatar") or "",
            "text": p.get("text") or "",
            "ago": _ago(p.get("at")),
        })
    return jsonify(out)


@bp.post("/m/api/talks")
def api_talks_create():
    """唠嗑区发帖（需登录）。数据结构复用桌面社区 posts。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    text = business.clean(request.form.get("text"), 200)
    if not text:
        return jsonify({"error": "写点内容再发"}), 400
    db.update("posts", lambda rows: [{
        "id": business.now_ms(), "type": "chat", "title": "", "text": text,
        "imgs": [], "username": (u.get("profile") or {}).get("nick") or u.get("username"),
        "phone": u.get("phone"), "at": business.now_ms(), "likes": [],
    }] + rows, 500)
    return jsonify({"ok": True})


@bp.post("/m/api/cars")
def api_cars_create():
    """发起拼车（需登录）。写入 bookings（carNew=True），拼车大厅直接能读到。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    f = request.form
    ts = int(f.get("ts") or 0)
    if ts <= 0:
        return jsonify({"error": "请选择出发日期"}), 400
    need = max(1, int(f.get("need") or 4))
    tags = [t.strip() for t in (f.get("tags") or "").split(",") if t.strip()]
    bookings = db.rows("bookings")
    bid = business.now_ms()
    bookings.append({
        "id": bid, "carNew": True, "status": "booked",
        "phone": u.get("phone"), "username": u.get("username"),
        "sid": f.get("sid") or "0", "title": f.get("title") or "剧本",
        "ts": ts, "day": business.day_label(ts), "time": f.get("time") or "",
        "players": 1, "price": 0, "carCap": need + 1, "carMin": need,
        "carTags": tags, "emoji": "🎭", "at": business.now_ms(),
    })
    db.write("bookings", bookings)
    return jsonify({"ok": True, "id": bid})


@bp.get("/m/api/reviews")
def api_reviews():
    """某剧本的评价列表。?sid=..."""
    sid = request.args.get("sid")
    rows = business.reviews_of(sid, only_visible=True)
    return jsonify([{
        "id": r.get("id"),
        "name": r.get("nick") or r.get("username") or "玩家",
        "avatar": r.get("avatar") or "",
        "text": r.get("text") or "",
        "rating": r.get("rating") or 0,
        "time": _ago(r.get("createdAt")),
    } for r in rows])


@bp.post("/m/api/book")
def api_book():
    """预约占位（需登录）。字段直接透传给 business.create_booking：
    sid / ts_day / time / players / mode(拼车|包车) / carTags / sessionId"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    f = request.form
    sid = f.get("sid") or f.get("sessionId")
    if not sid:
        return jsonify({"error": "缺少剧本"}), 400
    ok, msg, booking = business.create_booking(u, f)
    return jsonify({"ok": ok, "msg": msg, "id": booking.get("id") if booking else None})


@bp.post("/m/api/car/<car_id>/<action>")
def api_car_action(car_id, action):
    """上车 / 下车 / 候补。直接复用桌面端 business.car_action"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    if action not in ("join", "quit", "wait"):
        return jsonify({"error": "不支持的操作"}), 400
    ok, msg = business.car_action(u, car_id, action, request.form)
    return jsonify({"ok": ok, "msg": msg})


@bp.post("/m/api/booking/<int:bid>/cancel")
def api_cancel_booking(bid):
    """取消自己的预约"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    rows = db.rows("bookings")
    hit = next((b for b in rows if b.get("id") == bid and str(b.get("phone")) == str(u.get("phone"))), None)
    if not hit:
        return jsonify({"error": "没找到这条预约"}), 404
    hit.update(status="cancelled", cancelAt=business.now_ms(), cancelBy="user")
    db.write("bookings", rows)
    db.update("pays", lambda r: [dict(o, status="closed") if (o.get("bid") == bid and o.get("status") == "unpaid") else o for o in r])
    return jsonify({"ok": True})


@bp.post("/m/api/profile")
def api_profile_save():
    """改资料：昵称 / 性别 / 年龄（拼车时别人看到的就是这些）"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    f = request.form
    users = db.rows("users")
    hit = next((x for x in users if str(x.get("phone")) == str(u.get("phone"))), None)
    if not hit:
        return jsonify({"error": "账号不见了"}), 400
    prof = hit.get("profile") or {}
    if f.get("nick") is not None:
        prof["nick"] = business.clean(f.get("nick"), 16)
    if f.get("gender") in ("男", "女", ""):
        prof["gender"] = f.get("gender")
    if f.get("age") is not None:
        try:
            prof["age"] = int(f.get("age")) if str(f.get("age")).strip() else None
        except ValueError:
            pass
    hit["profile"] = prof
    db.write("users", users)
    return jsonify({"ok": True, "nick": prof.get("nick") or ""})


@bp.post("/m/api/notice/read")
def api_notice_read():
    """把一条通知标成已读"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    nid = request.form.get("id") or request.args.get("id")
    if not nid:
        return jsonify({"error": "缺少通知 id"}), 400
    db.update("notices", lambda rows: [dict(n, read=True) if str(n.get("id")) == str(nid) else n for n in rows])
    return jsonify({"ok": True})


@bp.post("/m/api/fav/<sid>")
def api_fav(sid):
    """收藏 / 取消收藏（想玩）"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    phone = str(u.get("phone"))
    rows = db.rows("favs")
    rec = next((r for r in rows if str(r.get("phone")) == phone), None)
    if not rec:
        rec = {"phone": phone, "sids": []}
        rows.append(rec)
    sids = [str(x) for x in rec.get("sids") or []]
    sid = str(sid)
    if sid in sids:
        sids.remove(sid)
        on = False
    else:
        sids.append(sid)
        on = True
    rec["sids"] = sids
    db.write("favs", rows)
    return jsonify({"ok": True, "on": on})


@bp.post("/m/api/booking/<int:bid>/reschedule")
def api_reschedule(bid):
    """改期：定金保留，新时段没位子就改不了"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    try:
        ts = int(request.form.get("ts") or 0)
    except ValueError:
        ts = 0
    ok, msg = business.reschedule(u, bid, ts, request.form.get("time") or "")
    return jsonify({"ok": ok, "msg": msg})


@bp.post("/m/api/review/<int:bid>")
def api_review(bid):
    """写评价：到店开本之后（arrived/done），一条预约只能评一次。
    规则和桌面端 /review/<bid> 完全一致。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    bk = next((b for b in db.rows("bookings") if b.get("id") == bid
               and str(b.get("phone")) == str(u.get("phone"))), None)
    if not bk:
        return jsonify({"error": "没找到这条预约"}), 404
    if bk.get("status") not in ("arrived", "done"):
        return jsonify({"error": "到店开本之后再来评价哈"}), 400
    if any(r.get("bid") == bid for r in db.rows("reviews")):
        return jsonify({"error": "这条已经评过了"}), 400
    try:
        rating = max(1, min(5, int(request.form.get("rating") or 5)))
    except ValueError:
        rating = 5
    anon = request.form.get("anonymous") == "1"
    db.update("reviews", lambda rows: rows + [{
        "id": business.now_ms(), "sid": bk.get("sid"), "bid": bid,
        "dmPhone": bk.get("dmPhone") or "",
        "rating": rating,
        "text": business.clean(request.form.get("text"), 800),
        "username": "匿名玩家" if anon else u.get("username"), "anonymous": anon,
        "dims": {}, "reply": "", "likes": [], "hidden": False, "createdAt": business.now_ms()}])
    business.notify(u.get("phone"), "评价已提交，谢谢！",
                    "《%s》的评价收到了，欢迎下次再来" % bk.get("title"), "review")
    return jsonify({"ok": True, "msg": "评价收到了，谢谢！"})


@bp.post("/m/api/password")
def api_password():
    """改密码：复用 business.change_password 的校验和通知"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    ok, msg = business.change_password(u, request.form.get("old"), request.form.get("password"))
    return jsonify({"ok": ok, "msg": msg})


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
    # 图片/字体必须按二进制读，走文本模式会把 jpg 读坏（图片一直加载不出来的坑）
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico", ".svg"):
        with open(full, "rb") as f:
            body = f.read()
    else:
        body = _read(filename)
    resp = Response(body, mimetype=mime)
    # 静态资源可缓存（改完靠文件名 ?v= 控制，这里直接长缓存）
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


def _read(filename):
    with open(os.path.join(_MOBILE_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()
