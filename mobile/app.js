/* ============================================================================
   甜薯剧本杀 · 手机端独立站逻辑
   纯前端 SPA：哈希路由 + 底部 Tab + 详情全屏 + 底部 Sheet + 骨架/入场动画
   数据优先取自 /m/api/*，接口不可达时回退 MOBILE_FALLBACK。
   设计对标 Top30 学习文档：暗色沉浸（Spotify/Netflix）、双列瀑布（小红书）、
   大圆角卡片 + 金刚区（淘宝/支付宝）、毛玻璃顶导（Apple/Stripe）、底部 Sheet（Airbnb/Uber）。
   ========================================================================== */
(function () {
  "use strict";

  var STATIC = window.MOBILE_STATIC || { shop: { name: "甜薯剧本杀" }, nav: [], menu: [] };
  var FALLBACK = window.MOBILE_FALLBACK || {};

  // D = 运行期数据：静态常驻 + 接口填充
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
  var getScript = function (id) {
    return (D.scripts || []).filter(function (x) { return x.id === id; })[0] || null;
  };

  /* ---------------- 数据加载：优先接口，失败兜底 ---------------- */
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
    ]).then(function () {
      if (!D.me) D.me = FALLBACK.me || { guest: true };
    });
    // 网络抖动：1.8s 内先用本地兜底把界面撑出来
    var timeout = new Promise(function (resolve) {
      setTimeout(function () {
        ["scripts", "sessions", "cars", "me"].forEach(function (k) {
          if (!(k in D) || D[k] == null) D[k] = FALLBACK[k] || [];
        });
        if (!D.me) D.me = FALLBACK.me || { guest: true };
        resolve();
      }, 1800);
    });
    _dataP = Promise.race([p, timeout]).then(function () { return p; });
    return _dataP;
  }

  /* ---------------- 图标（线性，原生感） ---------------- */
  var ICON = {
    home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    scripts: '<path d="M4 5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2z"/><path d="M14 3v5h5"/>',
    car: '<path d="M5 13l1.5-5h11L19 13"/><path d="M3 13h18v5H3z"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/>',
    group: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
    me: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    back: '<path d="M15 18l-6-6 6-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>'
  };
  function svg(name, cls) {
    return '<svg class="' + (cls || "") + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + ICON[name] + "</svg>";
  }

  var TABS = [
    { key: "home", label: "首页", icon: "home" },
    { key: "scripts", label: "挑本", icon: "scripts" },
    { key: "car", label: "拼车", icon: "car" },
    { key: "group", label: "组局", icon: "group" },
    { key: "me", label: "我的", icon: "me" }
  ];

  /* ---------------- 入场动画观察器 ---------------- */
  var io = null;
  function reveal(scope) {
    if (!io) {
      io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
        });
      }, { rootMargin: "0px 0px -8% 0px" });
    }
    $$(".reveal", scope).forEach(function (n) { io.observe(n); });
  }

  /* ---------------- 加载：先骨架，数据就绪后渲染（每视图只建一次） ---------------- */
  function load(view, build) {
    var node = $("#view-" + view);
    if (node.dataset.loaded) return;
    try {
      node.innerHTML = build();
      node.dataset.loaded = "1";
      reveal(node);
    } catch (e) {
      if (typeof showErr === "function") showErr("build " + view + " 失败: " + (e && e.message || e));
      node.innerHTML = skelList();
      throw e;
    }
    ensureData().then(function () { try { mount(view, build()); } catch (e) {} });
  }
  function mount(view, html) {
    var n = $("#view-" + view);
    n.innerHTML = html;
    reveal(n);
  }

  function skelList() {
    var s = "";
    for (var i = 0; i < 4; i++) s += '<div class="skel-card"><div class="skel cover"></div><div style="padding:12px"><div class="skel" style="height:14px;width:70%"></div><div class="skel" style="height:12px;width:40%;margin-top:8px"></div></div></div>';
    return s;
  }
  function emptyState(art, t, s) {
    return '<div class="empty"><div class="empty__art">' + art + '</div><div class="empty__t">' + esc(t) + '</div><div class="empty__s">' + esc(s) + "</div></div>";
  }

  /* ---------------- 组件：进度 / 人数 ---------------- */
  function pips(have, cap) {
    var h = "";
    for (var i = 0; i < cap; i++) h += '<span class="pip' + (i < have ? " on" : "") + '"></span>';
    return '<div class="pips">' + h + "</div>";
  }
  function progress(have, need) {
    var pct = Math.min(100, Math.round(have / (have + need) * 100));
    return '<div class="progress"><div class="progress__bar" style="width:' + pct + '%"></div></div>';
  }

  /* ====================== 首页 ====================== */
  function buildHome() {
    var featured = (D.scripts || []).filter(function (s) { return s.hot; })[0] || (D.scripts || [])[0];
    var hero = "";
    if (featured) {
      hero =
        '<div class="hero reveal" style="background:' + featured.grad + '">' +
          '<div class="hero__tag">本周主打</div>' +
          '<h1 class="hero__title">' + esc(featured.title) + "</h1>" +
          '<div class="hero__meta">' +
            "<span>" + featured.players + " 人</span>" +
            "<span>" + esc(featured.duration) + "</span>" +
            "<span>" + esc(featured.difficulty) + "</span>" +
          "</div>" +
          '<button class="hero__cta" data-script="' + featured.id + '">查看详情</button>' +
        "</div>";
    }

    // 金刚区
    var nav = (D.nav || []).map(function (n, i) {
      var brand = (i === 0 || n.key === "today") ? " grid-nav__ic--brand" : "";
      return '<button class="grid-nav__item reveal" style="transition-delay:' + (i * 30) + 'ms" data-nav="' + esc(n.key) + '">' +
        '<span class="grid-nav__ic' + brand + '">' + n.icon + "</span>" +
        '<span class="grid-nav__lb">' + esc(n.label) + "</span></button>";
    }).join("");

    // 今日开演：横向 rails
    var sessions = (D.sessions || []).map(function (s, i) {
      var sc = getScript(s.script) || {};
      return '<div class="rail__item reveal" style="transition-delay:' + (i * 40) + 'ms" data-session="' + s.id + '">' +
        '<div class="rail__cover" style="background:' + (sc.grad || "#241E19") + '"></div>' +
        '<div class="rail__body">' +
          '<div class="rail__time">' + esc(s.time) + "</div>" +
          '<div class="rail__name">' + esc(s.name) + "</div>" +
          '<div class="rail__room">' + esc(s.room) + "</div>" +
          '<div class="rail__foot">' + pips(s.have, s.cap) +
            '<span class="need">差 <b>' + Math.max(0, s.cap - s.have) + "</b></span></div>" +
        "</div></div>";
    }).join("");

    // 本周热门：双列瀑布
    var cards = (D.scripts || []).slice(0, 6).map(cardHTML).join("");

    return (
      hero +
      '<div class="grid-nav">' + nav + "</div>" +
      '<div class="section"><div class="section__head"><div class="section__title">今日开演</div>' +
        '<span class="section__more" data-nav="today">全部 ›</span></div></div>' +
      '<div class="rail">' + (sessions || emptyState("📅", "今天还没排场", "挑个本自己开一桌")) + "</div>" +
      '<div class="section"><div class="section__head"><div class="section__title">本周热门</div>' +
        '<span class="section__more" data-nav="scripts">挑本 ›</span></div></div>' +
      '<div class="waterfall">' + cards + "</div>"
    );
  }

  /* ====================== 挑本 ====================== */
  function cardHTML(s) {
    var tall = (s.id % 3 === 0);
    var wide = (s.id % 3 === 1);
    var cls = tall ? " pcard--tall" : (wide ? " pcard--wide" : "");
    return '<div class="pcard reveal' + cls + '" data-script="' + s.id + '">' +
      '<div class="pcard__cover" style="background:' + s.grad + '">' +
        '<span class="emoji">' + s.emoji + "</span></div>" +
      '<div class="pcard__body">' +
        '<div class="pcard__title">' + esc(s.title) + "</div>" +
        '<div class="pcard__meta">' +
          "<span>" + s.players + "人</span><span>" + esc(s.duration) + "</span>" +
          (s.hot ? '<span class="tag tag--hot">热门</span>' : "") +
        "</div>" +
        '<div class="pcard__foot">' +
          '<span class="price">¥' + s.price + "<small>/人</small></span>" +
          '<span class="tag">详情 ›</span></div>' +
      "</div></div>";
  }

  var scriptFilters = { tag: "", q: "" };
  function buildScripts() {
    var tags = ["全部", "沉浸", "推理", "情感", "欢乐", "恐怖", "机制", "科幻", "新手"];
    var chips = tags.map(function (t) {
      return '<button class="chip' + (scriptFilters.tag === t || (t === "全部" && !scriptFilters.tag) ? " on" : "") +
        '" data-tag="' + t + '">' + t + "</button>";
    }).join("");

    var list = (D.scripts || []).filter(function (s) {
      var okTag = !scriptFilters.tag || scriptFilters.tag === "全部" ||
        (s.tags || []).indexOf(scriptFilters.tag) >= 0;
      var okQ = !scriptFilters.q ||
        (s.title + (s.tags || []).join("") + (s.desc || "")).toLowerCase().indexOf(scriptFilters.q.toLowerCase()) >= 0;
      return okTag && okQ;
    });

    var cards = list.length
      ? list.map(cardHTML).join("")
      : '<div class="empty" style="grid-column:1/-1"><div class="empty__art">🔍</div><div class="empty__t">没有找到匹配的本子</div><div class="empty__s">换个关键词或筛选试试</div></div>';

    return '<div class="section" style="padding-top:0"><div class="chips">' + chips + "</div></div>" +
      '<div class="waterfall">' + cards + "</div>";
  }

  /* ====================== 拼车 ====================== */
  function carRow(c) {
    return '<div class="row reveal" data-car="' + c.id + '">' +
      '<div class="row__top">' +
        '<div class="avatar">' + c.av + "</div>" +
        '<div class="row__who"><div class="row__name">' + esc(c.who) + " 开了车</div>" +
          '<div class="row__sub">' + esc(c.script) + " · " + esc(c.time) + "</div></div>" +
        '<span class="tag">拼车</span></div>' +
      '<div class="row__body">' + esc(c.note) + "</div>" +
      '<div class="row__tags">' + (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") + "</div>" +
      '<div class="row__foot">' +
        "<div style=\"display:flex;align-items:center;flex:1\">" + progress(c.have, c.need) +
          '<span class="need">已 <b>' + c.have + "</b> / 需 " + c.need + "</span></div>" +
        '<button class="btn btn--primary btn--sm">上车</button></div></div>';
  }
  function buildCar() {
    if (!D.cars || !D.cars.length) return emptyState("🚗", "还没有人开车的局", "做第一个发车的人吧");
    return '<div class="list">' + D.cars.map(carRow).join("") + "</div>";
  }

  /* ====================== 组局 ====================== */
  function groupRow(s) {
    return '<div class="row reveal" data-session="' + s.id + '">' +
      '<div class="row__top">' +
        '<div class="avatar" style="background:var(--brand-soft);color:var(--brand)">🎭</div>' +
        '<div class="row__who"><div class="row__name">' + esc(s.name) + "</div>" +
          '<div class="row__sub">' + esc(s.time) + " · " + esc(s.room) + "</div></div>" +
        '<span class="tag">组局</span></div>' +
      '<div class="row__foot" style="margin-top:12px">' +
        "<div style=\"display:flex;align-items:center;flex:1\">" + progress(s.have, s.cap - s.have) +
          '<span class="need">还差 <b>' + Math.max(0, s.cap - s.have) + "</b> 人</span></div>" +
        '<button class="btn btn--primary btn--sm">加入</button></div></div>';
  }
  function buildGroup() {
    if (!D.sessions || !D.sessions.length) return emptyState("📅", "今天还没有开演的局", "挑个本自己开一桌");
    return '<div class="list">' + D.sessions.map(groupRow).join("") + "</div>";
  }

  /* ====================== 我的 ====================== */
  function buildMe() {
    var m = D.me;
    if (!m || m.guest) {
      return '<div class="empty" style="padding-top:80px"><div class="empty__art">👤</div>' +
        '<div class="empty__t">你还没登录</div><div class="empty__s">登录后查看你的开本、评价与券包</div>' +
        '<a class="btn btn--primary btn--block" style="max-width:200px;margin:16px auto 0" href="/login">去登录</a></div>';
    }
    var st = m.stats || { bookings: 0, reviews: 0, spent: 0 };
    var menu = (D.menu || []).map(function (x, i) {
      return '<button class="menu__item reveal" style="transition-delay:' + (i * 30) + 'ms">' +
        '<span class="menu__ic">' + x.icon + "</span>" +
        "<span>" + esc(x.label) + "</span>" +
        '<span class="arrow">›</span></button>';
    }).join("");

    return '<div class="me-hero reveal">' +
        '<div class="me-hero__top">' +
          '<div class="me-hero__av">' + (m.initial || "🦋") + "</div>" +
          "<div><div class=\"me-hero__name\">" + esc(m.name) + "</div>" +
          '<div class="me-hero__id">' + esc(m.phone) + (m.id ? " · 会员号 " + esc(m.id) : "") + "</div></div>" +
        "</div>" +
        '<div class="me-stats">' +
          "<div><b>" + st.bookings + "</b><span>开本</span></div>" +
          "<div><b>" + st.reviews + "</b><span>评价</span></div>" +
          "<div><b>" + st.spent + "</b><span>消费(¥)</span></div>" +
        "</div></div>" +
      '<div class="menu reveal">' + menu + "</div>";
  }

  /* ====================== 详情全屏 ====================== */
  function show(node) { node.classList.add("show"); }
  function hide(node) { node.classList.remove("show"); }

  function openDetailScript(id) {
    var s = getScript(id);
    if (!s) return;
    $("#detailContent").innerHTML =
      '<div class="detail__hero" style="background:' + s.grad + '">' +
        '<span class="emoji">' + s.emoji + "</span>" +
        '<div class="detail__title">' + esc(s.title) + "</div></div>" +
      '<div class="detail__body">' +
        '<div class="detail__meta">' +
          "<div><span>人数</span><b>" + s.players + "</b></div>" +
          "<div><span>时长</span><b>" + esc(s.duration) + "</b></div>" +
          "<div><span>难度</span><b>" + esc(s.difficulty) + "</b></div>" +
          "<div><span>单价</span><b>¥" + s.price + "</b></div>" +
        "</div>" +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">' +
          (s.tags || []).map(function (t) { return '<span class="tag">#' + esc(t) + "</span>"; }).join("") +
        "</div>" +
        '<div class="detail__desc">' + esc(s.desc) + "</div>" +
      "</div>" +
      '<div class="detail__bar">' +
        '<button class="btn btn--ghost btn--block">咨询 DM</button>' +
        '<button class="btn btn--primary btn--block">立即拼车</button>' +
      "</div>";
    show($("#detail"));
    history.pushState({ detail: 1 }, "");
  }

  /* ====================== 底部 Sheet ====================== */
  function openSheet(title, bodyHtml) {
    $("#sheetTitle").textContent = title;
    $("#sheetBody").innerHTML = bodyHtml;
    show($("#sheetMask")); show($("#sheet"));
  }
  function closeSheet() { hide($("#sheetMask")); hide($("#sheet")); }

  function openFabSheet() {
    openSheet("发起",
      '<button class="btn btn--primary btn--block" data-fab="car">🚗 发个拼车</button>' +
      '<button class="btn btn--ghost btn--block" data-fab="group">📅 开一局</button>' +
      '<button class="btn btn--ghost btn--block" data-fab="script">🎭 去挑本</button>');
  }

  /* ====================== 路由 ====================== */
  function route() {
    var h = location.hash.replace(/^#\/?/, "") || "home";
    var view = TABS.some(function (t) { return t.key === h.split("/")[0]; }) ? h.split("/")[0] : "home";
    TABS.forEach(function (t) {
      var v = $("#view-" + t.key), tab = $('.tab[data-key="' + t.key + '"]');
      if (t.key === view) { v.classList.add("active"); tab.classList.add("on"); }
      else { v.classList.remove("active"); tab.classList.remove("on"); }
    });
    if (view === "home") load("home", buildHome);
    else if (view === "scripts") load("scripts", buildScripts);
    else if (view === "car") load("car", buildCar);
    else if (view === "group") load("group", buildGroup);
    else if (view === "me") load("me", buildMe);
    window.scrollTo(0, 0);
    closeSheet();
  }

  /* ====================== 初始化 ====================== */
  function init() {
    $("#brandName").textContent = (D.shop && D.shop.name) || "甜薯剧本杀";

    $("#tabbar").innerHTML = TABS.map(function (t) {
      return '<button class="tab" data-key="' + t.key + '">' + svg(t.icon) + "<span>" + t.label + "</span></button>";
    }).join("");

    $$(".tab").forEach(function (b) {
      b.addEventListener("click", function () { location.hash = "#/" + b.dataset.key; });
    });

    document.addEventListener("click", function (e) {
      var hero = e.target.closest("[data-script]");
      if (hero) { openDetailScript(parseInt(hero.dataset.script, 10)); return; }

      var sess = e.target.closest("[data-session]");
      if (sess) {
        var s = (D.sessions || []).filter(function (x) { return x.id === parseInt(sess.dataset.session, 10); })[0];
        if (s) openDetailScript(s.script);
        return;
      }

      var navEl = e.target.closest("[data-nav]");
      if (navEl) {
        var key = navEl.dataset.nav;
        if (key === "scripts" || key === "car" || key === "group" || key === "today") {
          location.hash = "#/" + (key === "today" ? "group" : key);
        } else if (key === "shop") {
          openSheet("门店", '<div class="empty__s">上海市静安区南京西路 1788 号 3F</div>');
        } else {
          // 其它金刚区入口（按类型筛挑本）
          scriptFilters.tag = (key === "全部") ? "" : key;
          location.hash = "#/scripts";
          if (location.hash.replace(/^#\/?/, "") === "scripts") mount("scripts", buildScripts());
        }
        return;
      }

      var chip = e.target.closest("[data-tag]");
      if (chip) {
        scriptFilters.tag = chip.dataset.tag === "全部" ? "" : chip.dataset.tag;
        mount("scripts", buildScripts());
        return;
      }

      var fabAct = e.target.closest("[data-fab]");
      if (fabAct) {
        closeSheet();
        var a = fabAct.dataset.fab;
        if (a === "car") location.hash = "#/car";
        else if (a === "group") location.hash = "#/group";
        else if (a === "script") location.hash = "#/scripts";
        return;
      }
    });

    $("#globalSearch").addEventListener("input", function (e) {
      scriptFilters.q = e.target.value.trim();
      if (location.hash.replace(/^#\/?/, "") !== "scripts") location.hash = "#/scripts";
      else mount("scripts", buildScripts());
    });

    $("#fab").addEventListener("click", openFabSheet);
    $("#sheetMask").addEventListener("click", closeSheet);
    $("#detailBack").addEventListener("click", function () { history.back(); });
    window.addEventListener("popstate", function () {
      if ($("#detail").classList.contains("show")) hide($("#detail"));
    });

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
