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
import secrets
import time

from flask import Blueprint, Response, current_app, jsonify, request
from tianshu import business, mp
from tianshu.db import db
from tianshu.security import current_user, hash_password, verify_password

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


# 常见问题（§5.4，与桌面 faq.html 文案完全一致）
_FAQ = [
    {"q": "定金能退吗？",
     "a": "开场前 24 小时以上取消全额退（临期按规则扣信用分），到店开演后定金原路退回/可抵尾款。"},
    {"q": "能迟到吗？",
     "a": "建议提前 10 分钟到；迟到会拖累整车开本，请提前在「我的预约」联系店家。"},
    {"q": "几个人开？",
     "a": "每个本有最低人数，拼车页会显示「还差 X 人」；不够人车主可提前截止或补满发车。"},
    {"q": "怎么拼车？",
     "a": "大厅看车 → 点「上车」交押位定金 → 小客服确认后出核销码；也可自己开一车等人。"},
    {"q": "核销码哪来？",
     "a": "定金确认到账后，「我的预约」里显示 6 位核销码，到店报码即可。"},
    {"q": "改期规则？",
     "a": "开场前可在「我的预约」申请改期，一次一改；改期后原定金随单走。"},
]

# 帖子话题白名单（与 spec §2.4 一致）
_TOPICS = ("情感", "硬核", "恐怖", "欢乐")


def _norm_script(s, rating=0):
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
        "rating": rating,
        # 2026-10 修复：前端"新本首车"靠 s.isNew 判断，原来接口只回了 hot，
        # 导致新本永远进不了"首车"推荐，只能退而用 id 倒序兜底。这里把 isNew 也带上。
        "isNew": bool(s.get("hot") or s.get("isNew")),
    }


def _rating_map():
    """sid → 平均评分（仅 visible）"""
    acc = {}
    for r in db.rows("reviews"):
        if r.get("hidden"):
            continue
        k = str(r.get("sid"))
        a = acc.setdefault(k, [0, 0])
        a[0] += float(r.get("rating") or 0)
        a[1] += 1
    return {k: round(v[0] / v[1], 1) if v[1] else 0 for k, v in acc.items()}


@bp.get("/m/api/scripts")
def api_scripts():
    q = (request.args.get("q") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip()
    diff = (request.args.get("diff") or "").strip()
    ratings = _rating_map()
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
        rows.append(_norm_script(s, ratings.get(str(s.get("id")), 0)))
    return jsonify(rows)


@bp.get("/m/api/faq")
def api_faq():
    """常见问题（静态，与桌面 faq.html 一致，§5.4）"""
    return jsonify({"items": _FAQ})


@bp.post("/m/api/track")
def api_track():
    """页面访问埋点（只存 IP 的 sha256 摘要，不记任何用户信息）。
    body: JSON {path}。对齐桌面 /api/track。"""
    data = request.get_json(silent=True) or {}
    path = business.clean(str(data.get("path") or "/"), 200) or "/"
    business.track_visit(request.remote_addr or "", path)
    return jsonify({"ok": True})


@bp.get("/m/api/scripts/<int:sid>")
def api_script_detail(sid):
    """单个剧本全字段详情：sc 全字段 + 评分 + canSeeReview + roles（含 line/img）。
    复盘 reviewDoc / 视频 videoUrl 由 T2 按 canSeeReview 决定是否展示。"""
    sc = next((s for s in db.rows("scripts") if s.get("id") == sid), None)
    if not sc:
        return jsonify({"error": "没这个剧本"}), 404
    u = current_user()
    can_see = bool(u) and business.has_role(u, "dm", "admin")
    by = (business.stats().get("byScript") or {}).get(str(sid)) or {}
    out = dict(sc)
    out["canSeeReview"] = can_see
    out["rating"] = by.get("rating") or 0
    out["rating_n"] = by.get("n") or 0
    out["roles"] = sc.get("roles") or []
    return jsonify(out)


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
    by_name = {str(x.get("username")): x for x in db.rows("users")}
    # 多维筛选（与桌面 car 同口径，§3.1）：剧本名 q / 最低人数 players / 时段 time / 难度 diff(1-5)
    f_q = (request.args.get("q") or "").strip().lower()
    f_players = request.args.get("players")
    f_time = (request.args.get("time") or "").strip()
    f_diff = (request.args.get("diff") or "").strip()
    try:
        need_players = int(f_players) if f_players else 0
    except (ValueError, TypeError):
        need_players = 0
    try:
        want_diff = int(f_diff) if f_diff else 0
    except (ValueError, TypeError):
        want_diff = 0
    out = []
    for c in business.car_pool(me_phone):
        if f_q and f_q not in str(c.get("title", "")).lower():
            continue
        if need_players and int(c.get("min") or 0) < need_players:
            continue
        if f_time and str(c.get("time") or "") != f_time:
            continue
        if want_diff and int(c.get("scriptDiff") or 0) != want_diff:
            continue
        # 2026-10 修复：car_pool 的 owner 可能是 phone 也可能是 username（历史数据混用），
        # 只按 phone 查会查不到，头像恒为 🎭。两个索引都试一下。
        _okey = str(c.get("owner") or "")
        owner = (users.get(_okey) or by_name.get(_okey)) if _okey else None
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
            "day": c.get("day") or "",
            "startTime": c.get("time") or "",
            "have": c.get("joined") or 0,
            "cap": c.get("cap") or 8,
            "min": c.get("min") or 4,
            "need": c.get("need") or 0,
            "price": c.get("price") or 0,
            "tags": list(c.get("tags") or []),
            "members": [{"nick": m.get("nick") or "玩家", "tags": list(m.get("tags") or [])}
                        for m in (c.get("members") or [])][:8],
            "note": note,
            "full": bool(c.get("full")),
            "mine": bool(c.get("mine")),
            # 车队扩展字段（M1，数据层已算好，直接透传）
            "deadline": c.get("deadline") or 0,
            "deadlineIn": c.get("deadlineIn") or 0,
            "closed": bool(c.get("closed")),
            "filled": bool(c.get("filled")),
            "scriptDiff": c.get("scriptDiff") or 0,
            "scriptPlayers": c.get("scriptPlayers") or "",
            "likeMind": bool(c.get("likeMind")),
            "likeCount": c.get("likeCount") or 0,
        })
    return jsonify(out)


@bp.get("/m/api/me")
def api_me():
    u = current_user()
    if not u:
        return jsonify({"guest": True})
    u = business.ensure_invite(u)   # 老账号补邀请码（对齐桌面 /me，AUD-G-0069）
    phone = u.get("phone") or ""
    prof = u.get("profile") or {}
    all_bookings = db.rows("bookings")
    all_pays = db.rows("pays")
    bookings = [b for b in all_bookings
                if str(b.get("phone")) == str(phone) and b.get("status") != "cancelled"]
    reviews = [r for r in db.rows("reviews") if r.get("username") == u.get("username")]
    spent = sum(int(p.get("deposit") or 0) for p in all_pays
                if str(p.get("phone")) == str(phone) and p.get("status") == "paid")
    avatar = prof.get("avatar") or u.get("username") or "🦋"
    if not (str(avatar).startswith("/img/") or str(avatar).startswith("http")):
        initial = str(avatar)[:1]
    else:
        initial = avatar
    recs = []
    _titles = {str(x.get("id")): x.get("title") for x in db.rows("scripts")}
    _stmap = {"booked": "待开演", "arrived": "已入场", "done": "已结束", "cancelled": "已取消"}
    # 原来每条预约都 next() 全表扫 pays（M×P）、any() 全表扫 my_reviews（M×R）。
    # 这里一次建好 bid→订单 和 sid→最近评论时间 两张表，循环内 O(1) 查（AUD-B-0018/0022）。
    pay_by_bid = {}
    for p in all_pays:
        if p.get("bid") is not None:
            pay_by_bid.setdefault(str(p.get("bid")), p)
    my_reviews = [r for r in db.rows("reviews") if r.get("username") == u.get("username")]
    review_time_by_sid = {}
    for r in my_reviews:
        sid = str(r.get("sid"))
        ct = r.get("createdAt") or 0
        if ct > review_time_by_sid.get(sid, 0):
            review_time_by_sid[sid] = ct
    for b in all_bookings:
        if str(b.get("phone")) != str(phone):
            continue
        status = b.get("status") or "booked"
        pay = pay_by_bid.get(str(b.get("id")))
        pay_status = (pay or {}).get("status") or "unpaid"
        reviewed = review_time_by_sid.get(str(b.get("sid")), 0) > (b.get("createdAt") or 0)
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
    for o in sorted([x for x in all_pays if str(x.get("phone")) == str(phone)],
                    key=lambda x: -(x.get("id") or 0))[:20]:
        orders.append({
            "id": o.get("id"), "bid": o.get("bid"), "title": o.get("title") or "剧本",
            "day": o.get("day") or "", "time": o.get("time") or "", "players": o.get("players") or 1,
            "amount": o.get("amount") or 0, "deposit": o.get("deposit") or 0,
            "payable": o.get("payable") or 0, "status": o.get("status") or "unpaid",
            # 2026-10 修复：前端靠 balStatus 判断"要不要出现付游玩费按钮"，
            # 以前这里没返回该字段，app.js 的判断恒为假 —— 手机端永远付不了尾款。
            "balStatus": o.get("balStatus") or "",
        })
    favs = []
    for r in db.rows("favs"):
        if str(r.get("phone")) == str(phone):
            favs = [str(x) for x in (r.get("sids") or [])]
    # 收藏三组（want/done/avoid）→ 每组剧本对象列表（§2.9）
    try:
        business.reminder_scan(u)          # 打开我的页时自动生成开场提醒（M8#157）
    except Exception:
        pass
    _scripts_by_id = {str(s.get("id")): s for s in db.rows("scripts")}

    def _fav_objs(sids):
        objs = []
        for x in sids or []:
            sc = _scripts_by_id.get(str(x))
            if sc:
                objs.append({"id": sc.get("id"), "title": sc.get("title") or "剧本",
                             "emoji": sc.get("emoji") or "🎭", "img": sc.get("img") or "",
                             "diff": sc.get("diff") or 0})
        return objs

    try:
        _fg = business.fav_groups(u) or {}
    except Exception:
        _fg = {}
    fav_groups_out = {k: _fav_objs(_fg.get(k)) for k in ("want", "done", "avoid")}
    my_tags = list(prof.get("tags") or [])
    can_see_review = business.has_role(u, "dm", "admin")
    notices = []
    try:
        for n in business.my_notices(u, 20):
            notices.append({
                "id": n.get("id"), "title": n.get("title") or "通知",
                "body": n.get("body") or "", "at": _ago(n.get("at")), "read": bool(n.get("read")),
            })
    except Exception:
        notices = []
    # 可选 DM 列表（预约 Sheet 下拉用，AUD-G-0004/0099）
    dms = []
    for x in db.rows("users"):
        if business.role_of(x) in ("dm", "staff", "admin") or x.get("super"):
            xp = x.get("profile") or {}
            dms.append({"phone": x.get("phone"), "name": xp.get("nick") or x.get("username") or "DM"})
    st = business.get_settings() or {}
    return jsonify({
        "guest": False,
        "name": prof.get("nick") or u.get("username") or "玩家",
        "initial": initial if not (str(initial).startswith("/img/") or str(initial).startswith("http")) else "",
        "avatar": avatar if (str(avatar).startswith("/img/") or str(avatar).startswith("http")) else "",
        "phone": _mask_phone(phone),
        "id": u.get("invite") or "",
        "credit": u.get("credit") or 0,
        "staff": business.role_of(u) in ("admin", "staff", "dm") or bool(u.get("super")),
        "isDm": business.role_of(u) in ("dm", "staff", "admin") or bool(u.get("super")),
        "canSeeReview": can_see_review,
        "serviceWechat": st.get("serviceWechat") or "",
        "myTags": my_tags,
        "favGroups": fav_groups_out,
        "profile": {"nick": prof.get("nick") or "", "gender": prof.get("gender") or "", "age": prof.get("age") or "",
                    "tags": my_tags},
        "coupons": [{"id": c.get("id"), "name": c.get("name") or c.get("from") or "抵扣券", "amount": c.get("amount") or 0,
                     "minAmount": c.get("minAmount") or 0} for c in coupons],
        "orders": orders,
        "favs": favs,
        "notices": notices,
        "dms": dms,
        "shop": {"name": st.get("shopName") or "甜薯剧本杀",
                 "serviceWechat": st.get("serviceWechat") or "",
                 "groupQr": st.get("groupQr") or ""},
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


@bp.get("/m/api/posts")
def api_posts():
    """社区最近帖子（含话题/招募字段 + 点赞数/我是否赞过/昵称/头像）。
    ?type=recruit&topic=情感 过滤（''=不过滤）。"""
    u = current_user()
    me_phone = u.get("phone") if u else ""
    ftype = request.args.get("type") or request.args.get("postType") or ""
    ftopic = request.args.get("topic") or ""
    rows = business.community_posts(30, me_phone, ftype, ftopic)
    out = []
    for p in rows:
        out.append({
            "id": p.get("id"),
            "name": p.get("nick") or p.get("username") or "玩家",
            "nick": p.get("nick") or p.get("username") or "玩家",
            "avatar": p.get("avatar") or "",
            "text": p.get("text") or "",
            "content": p.get("text") or "",
            "ago": _ago(p.get("at")),
            "at": p.get("at"),
            "topic": p.get("topic") or "",
            "postType": p.get("postType") or "",
            "recruitNeed": p.get("recruitNeed") or 0,
            "recruitRole": p.get("recruitRole") or "",
            "recruitScript": p.get("recruitScript") or "",
            "likeCount": p.get("likeCount") or 0,
            "liked": bool(p.get("liked")),
        })
    return jsonify(out)


@bp.post("/m/api/post")
def api_post_create():
    """发帖（含话题与缺位招募）。清洗/校验与桌面 post_create 同口径。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    f = request.form
    text = business.clean(f.get("content") or f.get("text"), 1000)
    if not text:
        return jsonify({"error": "写点内容再发"}), 400
    topic = business.clean(f.get("topic"), 10)
    if topic not in _TOPICS:
        topic = ""
    is_recruit = (f.get("postType") or "") == "recruit"
    rec = {
        "id": business.now_ms(), "type": "chat", "title": "", "text": text, "imgs": [],
        "username": (u.get("profile") or {}).get("nick") or u.get("username"),
        "phone": u.get("phone"), "at": business.now_ms(), "likes": [],
        "topic": topic, "postType": "recruit" if is_recruit else "",
    }
    if is_recruit:
        try:
            rec["recruitNeed"] = max(0, int(f.get("recruitNeed") or 0))
        except (ValueError, TypeError):
            rec["recruitNeed"] = 0
        rec["recruitRole"] = business.clean(f.get("recruitRole"), 30)
        rec["recruitScript"] = business.clean(f.get("recruitScript"), 40)
    db.update("posts", lambda rows: [rec] + rows, 500)
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
    """某剧本的评价列表。?sid=... （含店长回复 reply、点赞数、四维分项 dims）"""
    sid = request.args.get("sid")
    rows = business.reviews_of(sid, only_visible=True)
    return jsonify([{
        "id": r.get("id"),
        "name": r.get("nick") or r.get("username") or "玩家",
        "avatar": r.get("avatar") or "",
        "text": r.get("text") or "",
        "rating": r.get("rating") or 0,
        "dims": r.get("dims") or {},
        "reply": r.get("reply") or "",
        "likes": len(r.get("likes") or []),
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
    # 风格标签（多选 getlist，或逗号/顿号串）→ business.set_player_tags 清洗限 3 个
    tag_list = f.getlist("tags")
    if not tag_list and f.get("tags"):
        tag_list = [t.strip() for t in str(f.get("tags")).replace("，", ",").replace("、", ",")
                    .split(",") if t.strip()]
    tag_msg = ""
    if tag_list:
        _ok, tag_msg = business.set_player_tags(hit, tag_list)
    return jsonify({"ok": True, "nick": prof.get("nick") or "", "tagMsg": tag_msg})


@bp.post("/m/api/notice/read")
def api_notice_read():
    """把一条通知标成已读"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    nid = request.form.get("id") or request.args.get("id")
    if not nid:
        return jsonify({"error": "缺少通知 id"}), 400
    # 2026-10 修复：原来任意登录用户能把**别人**的通知标已读（IDOR）——
    # 传入任意 id 即可篡改他人消息状态。现在只标"收件人在列表里有我"的那条。
    me = str(u.get("phone"))
    def _mark(n):
        if str(n.get("id")) != str(nid):
            return n
        to = n.get("to")
        if isinstance(to, list) and me not in to:
            return n                       # 不是发给我的，不动
        return dict(n, read=True)
    db.update("notices", lambda rows: [_mark(n) for n in rows])
    return jsonify({"ok": True})


@bp.post("/m/api/fav/<sid>")
def api_fav(sid):
    """收藏 / 移出，支持分组（want|done|avoid，默认 want）。
    form.group + form.on(1/0)；on 缺省时默认加入该组。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    group = request.form.get("group") or "want"
    if group not in ("want", "done", "avoid"):
        group = "want"
    on_raw = request.form.get("on")
    on = True if on_raw is None else str(on_raw) not in ("0", "", "false", "off")
    ok, msg = business.fav_set(u, sid, group, on)
    return jsonify({"ok": ok, "msg": msg, "on": on, "group": group})


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
    # 四个细分维度（剧情/DM/氛围/房间），与桌面端一致
    dims = {}
    for key, label in (("plot", "剧情"), ("dm", "DM"), ("vibe", "氛围"), ("room", "房间")):
        try:
            v = int(request.form.get(key) or 0)
        except ValueError:
            v = 0
        if 1 <= v <= 5:
            dims[label] = v
    db.update("reviews", lambda rows: rows + [{
        "id": business.now_ms(), "sid": bk.get("sid"), "bid": bid,
        "dmPhone": bk.get("dmPhone") or "",
        "rating": rating,
        "text": business.clean(request.form.get("text"), 800),
        "username": "匿名玩家" if anon else u.get("username"), "anonymous": anon,
        "dims": dims, "reply": "", "likes": [], "hidden": False, "createdAt": business.now_ms()}])
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


# ---------------------------------------------------------------- 验证码 / 注册 / 找回（内联 Sheet）
@bp.post("/m/api/code/send")
def api_code_send():
    """发邮箱验证码（purpose=register|reset）。对齐桌面 /code/send，回 JSON。"""
    email = (request.form.get("email") or "").strip()
    purpose = request.form.get("purpose") or "reset"
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "msg": "先填个有效的邮箱，验证码发到邮箱"})
    code, sent, err = business.send_code(email, purpose)
    if code is None:
        return jsonify({"ok": False, "msg": err or "要码太频繁了，等一会儿"})
    if sent:
        return jsonify({"ok": True, "msg": "验证码已发到 %s，5 分钟内有效" % email})
    if business.is_dev_request():
        return jsonify({"ok": True, "msg": "已生成：看服务黑窗口，本机也可直接填 1234"})
    return jsonify({"ok": False, "msg": "发信通道没配好，联系门店（%s）" % (err or "未配置")})


@bp.post("/m/api/register")
def api_register():
    """内联注册（对齐桌面 /register）：手机号+邮箱验证码+昵称+两次密码+邀请码"""
    # 2026-10 修复：/m/api/register 原本没有限流（桌面端有），可被脚本刷手机号注册、
    # 连带狂刷邀请券。这里加单进程内存兜底限流（多 worker 各自计数，能挡大部分，
    # 反向代理层也建议再加一层）。
    _reg_hits = globals().setdefault("_reg_hits", {})
    _now = business.now_ms()
    _ip = request.remote_addr or "?"
    _wl = [t for t in _reg_hits.get(_ip, []) if _now - t < 60000]
    if len(_wl) >= 6:
        return jsonify({"ok": False, "msg": "操作太频繁，请 1 分钟后再试"})
    _wl.append(_now); _reg_hits[_ip] = _wl
    f = request.form
    phone = (f.get("phone") or "").strip()
    email = (f.get("email") or "").strip()
    code = (f.get("code") or "").strip()
    name = business.clean(f.get("username"), 20)
    pw = f.get("password") or ""
    pw2 = f.get("password2") or ""
    invite = (f.get("invite") or "").strip().upper()
    if not re.match(r"^1\d{10}$", phone):
        return jsonify({"ok": False, "msg": "手机号要 11 位"})
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "msg": "要填个邮箱，验证码发到邮箱"})
    if len(pw) < 6:
        return jsonify({"ok": False, "msg": "密码至少 6 位"})
    if pw != pw2:
        return jsonify({"ok": False, "msg": "两次输入的密码不一样"})
    if not name:
        return jsonify({"ok": False, "msg": "起个名字吧"})
    if db.one("users", phone=phone):
        return jsonify({"ok": False, "msg": "这个手机号注册过了，直接登录"})
    if db.one("users", username=name):
        return jsonify({"ok": False, "msg": "名字被占了，换一个"})
    if not business.use_code(email, "register", code):
        return jsonify({"ok": False, "msg": "验证码不对（本机测试可填 1234）"})
    my_invite = "TS" + secrets.token_hex(3).upper()
    users = db.rows("users")
    users.append({"phone": phone, "username": name, "email": email, "role": "user", "super": False,
                  "password": hash_password(pw), "credit": 100, "creditLogs": [],
                  "profile": {"avatar": "🎭", "nick": name, "gender": "", "age": None},
                  "first": business.now_ms(), "last": business.now_ms(),
                  "invite": my_invite, "banned": False})
    db.write("users", users)
    inviter = db.one("users", invite=invite) if invite else None
    invite_amount = int(business.get_settings().get("inviteCoupon") or 10)
    if inviter:
        for who in ({"phone": phone}, inviter):
            db.update("coupons", lambda rows: rows + [{
                "id": business.now_ms() + secrets.randbelow(999),
                "phone": who.get("phone"), "amount": invite_amount, "minAmount": 0, "used": False,
                "exp": business.now_ms() + 90 * 86400000, "from": "邀请返利"}])
        business.notify(inviter.get("phone"), "邀请成功", "%s 用你的邀请码注册了" % name, "coupon")
    return jsonify({"ok": True, "msg": "注册成功，请登录", "phone": phone})


@bp.post("/m/api/reset")
def api_reset():
    """内联找回密码（对齐桌面 /forgot）：手机号+注册邮箱+验证码→重设"""
    f = request.form
    phone = (f.get("phone") or "").strip()
    code = (f.get("code") or "").strip()
    pw = f.get("password") or ""
    pw2 = f.get("password2") or ""
    email_ = (f.get("email") or "").strip().lower()
    u = db.one("users", phone=phone)
    if not u:
        return jsonify({"ok": False, "msg": "这个手机号还没注册过"})
    if not email_ or email_ != str(u.get("email") or "").strip().lower():
        return jsonify({"ok": False, "msg": "邮箱要和注册时填的一致"})
    if not business.use_code(email_, "reset", code):
        return jsonify({"ok": False, "msg": "验证码不对（本机测试可填 1234）"})
    if len(pw) < 6:
        return jsonify({"ok": False, "msg": "新密码至少 6 位"})
    if pw != pw2:
        return jsonify({"ok": False, "msg": "两次输入的密码不一样"})
    users = db.rows("users")
    for x in users:
        if str(x.get("phone")) == str(phone):
            x["password"] = hash_password(pw)
    db.write("users", users)
    return jsonify({"ok": True, "msg": "密码重设好了，去登录"})


# ---------------------------------------------------------------- 支付闭环（内联 Sheet）
@bp.get("/m/api/pay/<int:oid>")
def api_pay_info(oid):
    """返回这一单的支付信息：金额/类型/动作/客服微信/群码/可用券。对齐桌面 pay_deposit。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    o = next((x for x in db.rows("pays") if str(x.get("id")) == str(oid)
              and str(x.get("phone")) == str(u.get("phone"))), None)
    if not o:
        return jsonify({"error": "没找到这一单"}), 404
    b = next((x for x in db.rows("bookings") if str(x.get("id")) == str(o.get("bid"))), {}) or {}
    coupons = []
    if str(b.get("status")) in ("arrived", "done") and o.get("balStatus") != "paid":
        due = max(0, int(o.get("amount") or 0))
        due_kind = "游玩费"
        due_act = "claim-bal"
        now = business.now_ms()
        coupons = [{"id": c.get("id"), "name": c.get("name") or c.get("from") or "抵扣券",
                    "amount": c.get("amount") or 0, "minAmount": c.get("minAmount") or 0}
                   for c in db.rows("coupons")
                   if not c.get("used") and (not c.get("exp") or c.get("exp") > now)
                   and (c.get("all") or str(c.get("phone")) == str(u.get("phone")))]
    else:
        due = int(o.get("payable") if o.get("payable") is not None else o.get("deposit") or 0)
        due_kind = "定金"
        due_act = "claim"
    st = business.get_settings() or {}
    return jsonify({
        "id": o.get("id"), "title": o.get("title") or "剧本",
        "day": o.get("day") or "", "time": o.get("time") or "",
        "due": due, "dueKind": due_kind, "dueAct": due_act,
        "status": o.get("status"), "balStatus": o.get("balStatus") or "",
        "coupons": coupons,
        "serviceWechat": st.get("serviceWechat") or "",
        "groupQr": st.get("groupQr") or "",
        "shopName": st.get("shopName") or "甜薯剧本杀",
    })


@bp.post("/m/api/pay/<int:oid>/claim")
def api_pay_claim(oid):
    """「我已转账」：把单子标成 claimed，等小客服确认（不做假在线支付，AUD-G-0032）。"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    o = next((x for x in db.rows("pays") if str(x.get("id")) == str(oid)
              and str(x.get("phone")) == str(u.get("phone"))), None)
    if not o:
        return jsonify({"error": "没找到这一单"}), 404
    b = next((x for x in db.rows("bookings") if str(x.get("id")) == str(o.get("bid"))), {}) or {}
    if str(b.get("status")) in ("arrived", "done") and o.get("balStatus") != "paid":
        act = "claim-bal"
    else:
        act = "claim"
    ok, msg = business.order_action(u, oid, act, coupon_id=request.form.get("couponId"))
    return jsonify({"ok": ok, "msg": msg})


@bp.post("/m/api/invoice/apply")
def api_invoice_apply():
    """申请开票（oid/company/taxId/email）。订单须 paid 且属本人，同 oid 只能申请一次。"""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "msg": "请先登录"}), 401
    oid = request.form.get("oid")
    if not oid:
        return jsonify({"ok": False, "msg": "缺少订单号"}), 400
    ok, msg = business.invoice_apply(u, oid, request.form)
    return jsonify({"ok": ok, "msg": msg})


# ---------------------------------------------------------------- 给店家留言
@bp.get("/m/api/msgs")
def api_msgs():
    """我给店家留的言（含店家回复）"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    return jsonify([{
        "id": m.get("id"), "cat": m.get("cat") or "💡 建议", "text": m.get("text") or "",
        "reply": m.get("reply") or "", "status": m.get("status") or "pending",
        "at": _ago(m.get("createdAt")),
    } for m in business.my_messages(u, 30)])


@bp.post("/m/api/msg")
def api_msg_create():
    """给店家留言（分类+文字，店家在后台回）"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    text = business.clean(request.form.get("text"), 500)
    if not text:
        return jsonify({"error": "写点内容再发"}), 400
    db.update("messages", lambda rows: rows + [{
        "id": business.now_ms(), "phone": u.get("phone"), "username": u.get("username"),
        "cat": business.clean(request.form.get("cat"), 10) or "💡 建议", "text": text,
        "status": "pending", "reply": "", "createdAt": business.now_ms()}])
    return jsonify({"ok": True, "msg": "留言发出去了，店家看到会回你"})


# ---------------------------------------------------------------- 车队详情 + 车内聊天
@bp.get("/m/api/car/<int:cid>")
def api_car_detail(cid):
    """车队详情：基本信息 + 成员(含 tags) + 车内聊天记录 + 车队状态新字段"""
    booking = next((b for b in db.rows("bookings") if str(b.get("id")) == str(cid)), None)
    if not booking:
        return jsonify({"error": "没这辆车"}), 404
    u = current_user()
    # 2026-10 修复：以前这个函数不看登录，任何人按 id 遍历就能把所有车队的
    # 成员昵称和车内聊天全部拉走（隐私泄露）。车队详情改为登录后可见。
    if not u:
        return jsonify({"error": "请先登录"}), 401
    me_phone = u.get("phone") if u else ""
    # 从 car_pool 取数据层已算好的扩展字段（倒计时/截止/补满/难度/口味相近）
    enriched = next((c for c in business.car_pool(me_phone) if str(c.get("id")) == str(cid)), {})
    users = {str(x.get("phone")): x for x in db.rows("users")}
    owner = users.get(str(booking.get("phone"))) or {}
    op = owner.get("profile") or {}
    msgs = [{"name": m.get("nick") or m.get("username") or "玩家", "text": m.get("text") or ""}
            for m in business.car_msgs(cid, 50)]
    return jsonify({
        "id": booking.get("id"), "script": booking.get("title") or "剧本",
        "day": booking.get("day") or "", "time": booking.get("time") or "",
        "who": op.get("nick") or owner.get("username") or "玩家",
        "tags": booking.get("carTags") or [],
        # 前端读的是 name，这里补上（否则拼车成员一律显示成"玩家"）
        "members": [{"nick": m.get("nick") or "玩家", "name": m.get("nick") or "玩家",
                     "tags": list(m.get("tags") or [])}
                    for m in (enriched.get("members") or booking.get("members") or [])],
        "msgs": msgs,
        "deadline": enriched.get("deadline") or booking.get("carDeadline") or 0,
        "deadlineIn": enriched.get("deadlineIn") or 0,
        "closed": bool(enriched.get("closed") or booking.get("carClosed")),
        "filled": bool(enriched.get("filled") or booking.get("carFilled")),
        "scriptDiff": enriched.get("scriptDiff") or 0,
        "scriptPlayers": enriched.get("scriptPlayers") or "",
        "likeMind": bool(enriched.get("likeMind")),
        "likeCount": enriched.get("likeCount") or 0,
        "need": enriched.get("need") or 0,
        "joined": enriched.get("joined") or 0,
        "cap": enriched.get("cap") or 0,
    })


@bp.post("/m/api/car/<int:cid>/msg")
def api_car_msg(cid):
    """在车队里发一条聊天"""
    u = current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    text = business.clean(request.form.get("text"), 200)
    if not text:
        return jsonify({"error": "说点什么再发"}), 400
    # 2026-10 修复：以前只校验"登录了没"，任何登录用户都能往任意车队灌消息。
    # 现在要求是车主或本车成员（car_pool 的 mine 标记）。
    booking = next((b for b in db.rows("bookings") if str(b.get("id")) == str(cid)), None)
    if not booking:
        return jsonify({"error": "没这辆车"}), 404
    me = str(u.get("phone") or "")
    if str(booking.get("phone")) != me:
        enriched = next((c for c in business.car_pool(me) if str(c.get("id")) == str(cid)), {})
        if not enriched.get("mine"):
            return jsonify({"error": "你不在这一车里，不能发言"}), 403
    db.update("carmsgs", lambda rows: rows + [{
        "id": business.now_ms(), "carId": cid,
        "nick": (u.get("profile") or {}).get("nick") or u.get("username"),
        "text": text, "at": business.now_ms()}])
    return jsonify({"ok": True})


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
    # 目录穿越防护：比的是「规范化后的绝对路径 + 分隔符」前缀，
    # 光用 startswith(_MOBILE_DIR) 会被 /mobile2 这种同前缀的兄弟目录绕过去。
    _root = os.path.abspath(_MOBILE_DIR) + os.sep
    if not os.path.abspath(full).startswith(_root) or not os.path.isfile(full):
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


# ---------------------------------------------------------------- 微信小程序
# 注意：小程序没有 Cookie 概念，所有写请求都靠 Authorization: Bearer <token> 鉴权。
# __init__.py 里的 csrf_guard 已识别该头部并自动跳过 CSRF；下面两个「登录/绑定」接口
# 本身也放进 _CSRF_FREE，这样哪怕没 token 也能调用。


@bp.post("/m/api/mp/login")
def mp_login():
    """小程序 wx.login 拿 code 换 openid；若该 openid 已绑定账号，直接返回长期 token。"""
    data = request.get_json(silent=True) or request.form or {}
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify(ok=False, msg='缺少 code')

    openid, err = mp.jscode2session(code)
    if err:
        return jsonify(ok=False, msg=err)

    # 找已绑定该 openid 的账号
    rows = db.rows('users') or []
    user = None
    for u in rows:
        if u.get('mpOpenid') == openid:
            user = u
            break

    if user:
        if user.get('banned'):
            return jsonify(ok=False, msg='账号已被禁用')
        token = mp.issue_token(user['phone'], openid=openid)
        return jsonify(ok=True, token=token,
                       phone=user['phone'],
                       nick=(user.get('profile') or {}).get('nick'))
    # 没绑定过：让前端走绑定流程（手机号+密码）
    return jsonify(ok=False, needBind=True, openid=openid)


@bp.post("/m/api/mp/bind")
def mp_bind():
    """首次使用：用手机号+密码绑定 openid，之后即可一键登录。"""
    data = request.get_json(silent=True) or request.form or {}
    phone = (data.get('phone') or '').strip()
    password = (data.get('password') or '')
    openid = (data.get('openid') or '').strip()

    if not phone or not password or not openid:
        return jsonify(ok=False, msg='缺少手机号、密码或 openid')

    user = db.one('users', phone=phone)
    if not user:
        return jsonify(ok=False, msg='手机号未注册')
    if not verify_password(password, user.get('password')):
        return jsonify(ok=False, msg='密码错误')
    if user.get('banned'):
        return jsonify(ok=False, msg='账号已被禁用')

    # 写回 openid 绑定关系
    user['mpOpenid'] = openid
    db.write('users', [u if u.get('phone') != phone else user for u in (db.rows('users') or [])])
    mp.clean_expired_tokens()
    token = mp.issue_token(phone, openid=openid)
    return jsonify(ok=True, token=token,
                   phone=phone,
                   nick=(user.get('profile') or {}).get('nick'))


@bp.post("/m/api/mp/subscribe")
def mp_subscribe_send():
    """手动触发订阅消息（示例：管理员/顾客在小程序内触发后，服务端代发）。"""
    data = request.get_json(silent=True) or request.form or {}
    template_id = (data.get('template_id') or '').strip()
    page = (data.get('page') or '').strip()
    payload_data = data.get('data') or {}
    openid = (data.get('openid') or '').strip()

    if not all([template_id, openid]):
        return jsonify(ok=False, msg='缺少 template_id 或 openid')

    ok, err = mp.send_subscribe(openid, template_id, page or 'pages/index/index', payload_data)
    return jsonify(ok=ok, msg=err or '')
