/* ============================================================================
   甜薯剧本杀 · 手机端网站逻辑（v3）
   架构（与上一版彻底不同）：
   · 顶部文字导航（无底部 Tab，参考 Apple/Stripe 官网）
   · 首页=编辑式全屏 Hero + 数据条 + 今日开演时间线 + 挑本特写入口
   · 挑本=全屏滑动卡组（TikTok/Wrapped）：拖/点左右滑，想玩/跳过
   · 拼车=发丝线极简列表（Notion/Things）
   · 组局=时间线（同今日开演）
   · 我的=极简资料卡
   数据优先 /m/api/*，失败回退 MOBILE_FALLBACK。
   ========================================================================== */
(function () {
  "use strict";

  var STATIC = window.MOBILE_STATIC || { shop: { name: "甜薯剧本杀" }, nav: [], menu: [] };
  var FALLBACK = window.MOBILE_FALLBACK || {};
  var D = Object.assign({}, STATIC);
  D.scripts = FALLBACK.scripts || [];
  D.sessions = FALLBACK.sessions || [];
  D.cars = FALLBACK.cars || [];
  D.me = FALLBACK.me || { guest: true };

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  };
  var getScript = function (id) { return (D.scripts || []).filter(function (x) { return x.id === id; })[0] || null; };

  /* ---------- 数据加载 ---------- */
  var _dataP = null;
  function ensureData() {
    if (_dataP) return _dataP;
    function get(url, key, fb) {
      return fetch(url).then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (d) { D[key] = d; })
        .catch(function () { D[key] = fb; });
    }
    var p = Promise.allSettled([
      get("/m/api/scripts", "scripts", FALLBACK.scripts || []),
      get("/m/api/sessions", "sessions", FALLBACK.sessions || []),
      get("/m/api/cars", "cars", FALLBACK.cars || []),
      get("/m/api/me", "me", FALLBACK.me || { guest: true })
    ]).then(function () { if (!D.me) D.me = FALLBACK.me || { guest: true }; });
    var timeout = new Promise(function (resolve) {
      setTimeout(function () {
        ["scripts", "sessions", "cars", "me"].forEach(function (k) { if (!(k in D) || D[k] == null) D[k] = FALLBACK[k] || []; });
        if (!D.me) D.me = FALLBACK.me || { guest: true };
        resolve();
      }, 1800);
    });
    _dataP = Promise.race([p, timeout]).then(function () { return p; });
    return _dataP;
  }

  function pips(have, cap) {
    var h = "";
    for (var i = 0; i < cap; i++) h += '<span class="pip' + (i < have ? " on" : "") + '"></span>';
    return '<div class="pips">' + h + "</div>";
  }

  /* ---------- 入场动画 ---------- */
  var io = null;
  function reveal(scope) {
    if (!io) io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -8% 0px" });
    $$(".reveal", scope).forEach(function (n) { io.observe(n); });
  }

  function skel() {
    var s = "";
    for (var i = 0; i < 4; i++) s += '<div class="reveal" style="height:64px;border-bottom:1px solid var(--hair);margin-bottom:4px"></div>';
    return s;
  }
  function emptyState(a, t, s) {
    return '<div style="text-align:center;padding:64px 24px"><div style="font-size:54px">' + a + '</div><div style="font-size:20px;font-weight:700;margin-top:12px">' + esc(t) + '</div><div style="color:var(--text-3);margin-top:8px">' + esc(s) + "</div></div>";
  }

  /* ---------- 首页：编辑式 ---------- */
  function buildHome() {
    var featured = (D.scripts || []).filter(function (s) { return s.hot; })[0] || (D.scripts || [])[0];
    var hero = featured ? (
      '<a class="hero reveal" data-action="toScripts" style="background:' + featured.grad + '">' +
        '<div class="hero__kicker">本周主打</div>' +
        '<h1 class="hero__title">' + esc(featured.title) + "</h1>" +
        '<p class="hero__sub">' + featured.players + " 人 · " + esc(featured.duration) + " · " + esc(featured.difficulty) + "</p>" +
        '<span class="hero__cta">开始选本 →</span>' +
      "</a>"
    ) : "";

    var stats =
      '<div class="stats reveal">' +
        "<div><b>" + (D.scripts || []).length + "</b><span>在售本子</span></div>" +
        "<div><b>" + (D.sessions || []).length + "</b><span>今日场次</span></div>" +
        "<div><b>12</b><span>驻店 DM</span></div>" +
      "</div>";

    var tl = (D.sessions || []).map(function (s) {
      return '<div class="tl reveal" data-session="' + s.id + '">' +
        '<div class="tl__time">' + esc(s.time) + '<span class="tl__ampm">场次</span></div>' +
        '<div><div class="tl__name">' + esc(s.name) + '</div><div class="tl__room">' + esc(s.room) + "</div></div>" +
        '<div class="tl__foot">' + pips(s.have, s.cap) + '<span class="link">差' + Math.max(0, s.cap - s.have) + "</span></div>" +
      "</div>";
    }).join("");

    var feat = (D.scripts || [])[1] || featured;
    var feature = feat ? (
      '<a class="feature reveal" data-action="toScripts" style="background:' + feat.grad + '">' +
        '<div><div class="hero__kicker">挑本</div>' +
        '<h3 class="feature__title">不想看列表？<br>滑着选</h3>' +
        '<div class="feature__sub">一屏一个本，左滑跳过 · 右滑想玩</div>' +
        '<div class="feature__cta">滑动选本 →</div></div>' +
      "</a>"
    ) : "";

    return (
      hero + stats +
      '<div class="sec-head"><div class="kicker">Tonight</div><h2 class="sec-title">今日开演</h2></div>' +
      '<div class="timeline">' + (tl || emptyState("📅", "今天还没排场", "挑个本自己开一桌")) + "</div>" +
      '<div class="sec-head"><div class="kicker">Pick a script</div><h2 class="sec-title">挑本</h2></div>' +
      feature
    );
  }

  /* ---------- 挑本：全屏滑动卡组 ---------- */
  var deckState = { top: 0, liked: [], cards: [] };
  function renderDeck() {
    var view = $("#view-scripts");
    view.innerHTML = '<div class="deck__prog" id="deckProg"></div><div class="deck" id="deck"></div>';
    var deck = $("#deck");
    deckState = { top: 0, liked: [], cards: [] };

    (D.scripts || []).forEach(function (s, i) {
      var c = document.createElement("div");
      c.className = "deck__card";
      c.style.background = s.grad;
      c.style.zIndex = String(1000 - i);
      c.dataset.id = s.id;
      c.innerHTML =
        '<div class="deck__scrim"></div>' +
        '<div class="deck__meta">' +
          '<div class="deck__emoji">' + s.emoji + "</div>" +
          '<div class="deck__title">' + esc(s.title) + "</div>" +
          '<div class="deck__tags">' + (s.tags || []).map(function (t) { return "<span>" + esc(t) + "</span>"; }).join("") + "</div>" +
          '<div class="deck__info"><b>' + s.players + "</b> 人 · " + esc(s.duration) + " · " + esc(s.difficulty) + " · ¥" + s.price + "</div>" +
          '<div class="deck__hint">← 跳过 &nbsp;·&nbsp; 右滑想玩 →</div>' +
        "</div>";
      deck.appendChild(c);
      deckState.cards.push(c);
    });

    var actions = document.createElement("div");
    actions.className = "deck__actions";
    actions.innerHTML = '<button class="deck__btn deck__btn--no" data-act="no">跳过</button><button class="deck__btn deck__btn--yes" data-act="yes">想玩</button>';
    deck.appendChild(actions);

    wireDeck(deck);
    updateDeckProg();
  }
  function updateDeckProg() {
    var prog = $("#deckProg");
    if (!prog) return;
    var n = deckState.cards.length, h = "";
    for (var i = 0; i < n; i++) h += '<i class="' + (i <= deckState.top ? "on" : "") + '"></i>';
    prog.innerHTML = h;
  }
  function showDeckEnd() {
    var deck = $("#deck");
    if (!deck || $("#deckEnd")) return;
    var end = document.createElement("div");
    end.className = "deck__end";
    end.id = "deckEnd";
    end.innerHTML =
      "<div style=\"font-size:54px\">🍠</div>" +
      "<h2>这一轮看完啦</h2>" +
      "<p>你标记了 <b style=\"color:var(--brand)\">" + deckState.liked.length + "</b> 个想玩的本<br>去拼车或组局，凑齐人就能开</p>" +
      '<button class="btn btn--primary btn--block" data-action="toCar">去拼车 ›</button>' +
      '<button class="btn btn--ghost btn--block" data-action="replay">再看一轮</button>';
    deck.appendChild(end);
  }
  function commitSwipe(act, card) {
    var out = act === "yes" ? 1 : -1;
    card.style.transform = "translate(" + (out * 130) + "%,-12%) rotate(" + (out * 14) + "deg)";
    card.style.opacity = "0";
    if (act === "yes") deckState.liked.push(parseInt(card.dataset.id, 10));
    deckState.top++;
    updateDeckProg();
    if (deckState.top >= deckState.cards.length) setTimeout(showDeckEnd, 320);
  }
  function wireDeck(deck) {
    var drag = null;
    deck.addEventListener("pointerdown", function (e) {
      if (e.target.closest(".deck__actions")) return; // 点按钮不触发卡片拖拽/详情
      if (deckState.top >= deckState.cards.length) return;
      var card = deckState.cards[deckState.top];
      if (!card) return;
      drag = { card: card, sx: e.clientX, sy: e.clientY, dx: 0, moved: false };
      card.style.transition = "none";
    });
    deck.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
      if (Math.abs(dx) > 6) drag.moved = true;
      drag.dx = dx;
      drag.card.style.transform = "translate(" + dx + "px," + (dy * 0.15) + "px) rotate(" + (dx / 22) + "deg)";
    });
    function end() {
      if (!drag) return;
      var card = drag.card, dx = drag.dx;
      card.style.transition = "";
      if (!drag.moved) { drag = null; openDetailScript(parseInt(card.dataset.id, 10)); return; }
      if (Math.abs(dx) > 90) commitSwipe(dx > 0 ? "yes" : "no", card);
      else card.style.transform = "";
      drag = null;
    }
    deck.addEventListener("pointerup", end);
    deck.addEventListener("pointercancel", end);
    deck.addEventListener("click", function (e) {
      var b = e.target.closest("[data-act]");
      if (b) { e.stopPropagation(); handleAct(b.dataset.act); }
    });
  }

  /* ---------- 拼车：极简列表 ---------- */
  function buildCar() {
    if (!D.cars || !D.cars.length) return emptyState("🚗", "还没有人开车的局", "做第一个发车的人吧");
    return '<div class="list">' + D.cars.map(function (c) {
      var pct = Math.min(100, Math.round(c.have / (c.have + c.need) * 100));
      return '<div class="row reveal" data-car="' + c.id + '">' +
        '<div class="avatar">' + c.av + "</div>" +
        "<div><div class=\"row__name\">" + esc(c.who) + " 开了车</div>" +
          '<div class="row__sub">' + esc(c.script) + " · " + esc(c.time) + "</div>" +
          '<div class="row__body">' + esc(c.note) + "</div>" +
          '<div class="row__tags">' + (c.tags || []).map(function (t) { return "<span>" + esc(t) + "</span>"; }).join("") + "</div>" +
          '<div class="row__foot"><div class="progress"><div class="progress__bar" style="width:' + pct + '%"></div></div>' +
            '<span class="link">已 ' + c.have + " / 需 " + c.need + "</span></div>" +
        "</div>" +
        '<button class="btn btn--primary btn--sm">上车</button></div>';
    }).join("") + "</div>";
  }

  /* ---------- 组局：时间线 ---------- */
  function buildGroup() {
    if (!D.sessions || !D.sessions.length) return emptyState("📅", "今天还没有开演的局", "挑个本自己开一桌");
    return '<div class="timeline">' + D.sessions.map(function (s) {
      return '<div class="tl reveal" data-session="' + s.id + '">' +
        '<div class="tl__time">' + esc(s.time) + '<span class="tl__ampm">场次</span></div>' +
        '<div><div class="tl__name">' + esc(s.name) + '</div><div class="tl__room">' + esc(s.room) + "</div></div>" +
        '<div class="tl__foot">' + pips(s.have, s.cap) + '<span class="link">差' + Math.max(0, s.cap - s.have) + "</span></div>" +
      "</div>";
    }).join("") + "</div>";
  }

  /* ---------- 我的 ---------- */
  function buildMe() {
    var m = D.me;
    if (!m || m.guest) {
      return '<div style="padding:80px 24px;text-align:center"><div style="font-size:54px">👤</div>' +
        '<div style="font-size:20px;font-weight:700;margin-top:12px">你还没登录</div>' +
        '<div style="color:var(--text-3);margin-top:8px">登录后查看开本、评价与券包</div>' +
        '<a class="btn btn--primary btn--block" style="max-width:220px;margin:16px auto 0" href="/login">去登录</a></div>';
    }
    var st = m.stats || { bookings: 0, reviews: 0, spent: 0 };
    var menu = (D.menu || []).map(function (x) {
      return '<button class="menu__item"><span class="menu__ic">' + x.icon + "</span><span>" + esc(x.label) + '</span><span class="arrow">›</span></button>';
    }).join("");
    return (
      '<div class="me-hero reveal"><div class="me-av">' + (m.initial || "🦋") + "</div>" +
        "<div><div class=\"me-name\">" + esc(m.name) + "</div><div class=\"me-id\">" + esc(m.phone) + (m.id ? " · " + esc(m.id) : "") + "</div></div></div>" +
      '<div class="me-stats reveal"><div><b>' + st.bookings + "</b><span>开本</span></div>" +
        "<div><b>" + st.reviews + "</b><span>评价</span></div><div><b>" + st.spent + "</b><span>消费</span></div></div>" +
      '<div class="menu reveal">' + menu + "</div>"
    );
  }

  /* ---------- 详情 ---------- */
  function show(n) { n.classList.add("show"); }
  function hide(n) { n.classList.remove("show"); }
  function openDetailScript(id) {
    var s = getScript(id);
    if (!s) return;
    $("#detailContent").innerHTML =
      '<div class="detail__hero" style="background:' + s.grad + '"><span class="emoji">' + s.emoji + '</span><div class="detail__title">' + esc(s.title) + "</div></div>" +
      '<div class="detail__body">' +
        '<div class="detail__meta">' +
          "<div><span>人数</span><b>" + s.players + "</b></div>" +
          "<div><span>时长</span><b>" + esc(s.duration) + "</b></div>" +
          "<div><span>难度</span><b>" + esc(s.difficulty) + "</b></div>" +
          "<div><span>单价</span><b>¥" + s.price + "</b></div>" +
        "</div>" +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">' + (s.tags || []).map(function (t) { return '<span class="deck__tags" style="background:none;padding:0"><span style="font-size:12px;color:var(--text);background:var(--surface);border:1px solid var(--hair);padding:3px 10px;border-radius:999px">' + esc(t) + "</span></span>"; }).join("") + "</div>" +
        '<div class="detail__desc">' + esc(s.desc) + "</div>" +
      "</div>" +
      '<div class="detail__bar"><button class="btn btn--ghost btn--block">咨询 DM</button><button class="btn btn--primary btn--block">立即拼车</button></div>';
    show($("#detail"));
    history.pushState({ detail: 1 }, "");
  }

  /* ---------- Sheet / FAB ---------- */
  function openSheet(title, body) { $("#sheetTitle").textContent = title; $("#sheetBody").innerHTML = body; show($("#sheetMask")); show($("#sheet")); }
  function closeSheet() { hide($("#sheetMask")); hide($("#sheet")); }
  function openFabSheet() {
    openSheet("发起",
      '<button class="btn btn--primary btn--block" data-action="toCar">🚗 发个拼车</button>' +
      '<button class="btn btn--ghost btn--block" data-action="toGroup">📅 开一局</button>' +
      '<button class="btn btn--ghost btn--block" data-action="toScripts">🎭 去挑本</button>');
  }
  function handleAct(act) {
    if (act === "toScripts") { closeSheet(); location.hash = "#/scripts"; }
    else if (act === "toCar") { closeSheet(); location.hash = "#/car"; }
    else if (act === "toGroup") { closeSheet(); location.hash = "#/group"; }
    else if (act === "replay") { renderDeck(); }
    else if (act === "yes" || act === "no") {
      var c = deckState.cards[deckState.top];
      if (c) commitSwipe(act, c);
    }
  }

  /* ---------- 路由 ---------- */
  function route() {
    var h = location.hash.replace(/^#\/?/, "") || "home";
    var view = (["home", "scripts", "car", "group", "me"].indexOf(h.split("/")[0]) >= 0) ? h.split("/")[0] : "home";
    $$(".topnav a").forEach(function (a) {
      if (a.dataset.key === view) a.classList.add("on"); else a.classList.remove("on");
    });
    ["home", "car", "group", "me"].forEach(function (v) {
      var n = $("#view-" + v);
      if (v === view) { n.classList.add("active"); if (!n.dataset.loaded) { n.innerHTML = buildView(v); n.dataset.loaded = "1"; reveal(n); } }
      else n.classList.remove("active");
    });
    var sv = $("#view-scripts");
    if (view === "scripts") { sv.classList.add("active"); renderDeck(); } else sv.classList.remove("active");
    window.scrollTo(0, 0);
    closeSheet();
    ensureData().then(function () {
      if (view !== "scripts") {
        var n = $("#view-" + view);
        if (n && !n.dataset.filled) { n.innerHTML = buildView(view); n.dataset.filled = "1"; reveal(n); }
      }
    });
  }
  function buildView(v) {
    if (v === "home") return buildHome();
    if (v === "car") return buildCar();
    if (v === "group") return buildGroup();
    if (v === "me") return buildMe();
    return "";
  }

  /* ---------- 初始化 ---------- */
  function init() {
    $("#brandName").textContent = (D.shop && D.shop.name) || "甜薯剧本杀";
    $$(".topnav a").forEach(function (a) {
      a.addEventListener("click", function () { location.hash = "#/" + a.dataset.key; });
    });
    document.addEventListener("click", function (e) {
      var act = e.target.closest("[data-action]");
      if (act) { handleAct(act.dataset.action); return; }
      var sess = e.target.closest("[data-session]");
      if (sess) {
        var s = (D.sessions || []).filter(function (x) { return x.id === parseInt(sess.dataset.session, 10); })[0];
        if (s) openDetailScript(s.script);
        return;
      }
    });
    $("#fab").addEventListener("click", openFabSheet);
    $("#sheetMask").addEventListener("click", closeSheet);
    $("#detailBack").addEventListener("click", function () { history.back(); });
    window.addEventListener("popstate", function () { if ($("#detail").classList.contains("show")) hide($("#detail")); });
    window.addEventListener("hashchange", route);
    route();
  }

  try {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  } catch (e) {
    if (typeof showErr === "function") showErr("init 失败: " + (e && e.message || e) + "\n" + (e && e.stack || ""));
    throw e;
  }
})();
