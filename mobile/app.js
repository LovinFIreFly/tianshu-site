/* ============================================================================
   甜薯剧本杀 · 手机端独立站（v2）逻辑
   纯前端 SPA：哈希路由 + 五个一级视图 + 详情浮层 + 底部弹层 + 骨架/入场动画
   数据优先取自 /m/api/*（真实后台），接口不可达时退回 MOBILE_FALLBACK 兜底。
   ========================================================================== */
(function () {
  "use strict";
  const STATIC = window.MOBILE_STATIC || { shop: { name: "甜薯剧本杀" }, nav: [], menu: [] };
  const FALLBACK = window.MOBILE_FALLBACK || {};
  // D 是运行期数据：静态常驻 + 动态由接口填充
  const D = Object.assign({}, STATIC);
  D.scripts = FALLBACK.scripts || [];
  D.sessions = FALLBACK.sessions || [];
  D.cars = FALLBACK.cars || [];
  D.me = FALLBACK.me || { guest: true };

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };

  /* -------- 数据加载：优先接口，失败兜底（只跑一次） -------- */
  let _dataP = null;
  function ensureData() {
    if (_dataP) return _dataP;
    const get = (url, key, fb) =>
      fetch(url).then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => { D[key] = d; })
        .catch(() => { D[key] = fb; });
    _dataP = Promise.allSettled([
      get("/m/api/scripts", "scripts", FALLBACK.scripts || []),
      get("/m/api/sessions", "sessions", FALLBACK.sessions || []),
      get("/m/api/cars", "cars", FALLBACK.cars || []),
      get("/m/api/me", "me", FALLBACK.me || { guest: true }),
    ]).then(() => { if (!D.me) D.me = FALLBACK.me || { guest: true }; });
    return _dataP;
  }

  /* -------- Tab 图标（线性，原生感） -------- */
  const ICON = {
    home: '<path d="M3 11l9-8 9 8"></path><path d="M5 10v10h14V10"></path>',
    scripts: '<path d="M4 5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2z"></path><path d="M14 3v5h5"></path>',
    car: '<path d="M5 13l1.5-5h11L19 13"></path><path d="M3 13h18v5H3z"></path><circle cx="7" cy="18" r="1.6"></circle><circle cx="17" cy="18" r="1.6"></circle>',
    group: '<rect x="3" y="4" width="18" height="17" rx="2"></rect><path d="M3 9h18M8 2v4M16 2v4"></path>',
    me: '<circle cx="12" cy="8" r="4"></circle><path d="M4 21c0-4 4-6 8-6s8 2 8 6"></path>',
    back: '<path d="M15 18l-6-6 6-6"></path>',
    plus: '<path d="M12 5v14M5 12h14"></path>',
  };
  function svg(name, cls) {
    return '<svg class="' + (cls || "") + '" viewBox="0 0 24 24">' + ICON[name] + "</svg>";
  }

  /* -------- Tab 定义（≤5） -------- */
  const TABS = [
    { key: "home", label: "首页", icon: "home" },
    { key: "scripts", label: "挑本", icon: "scripts" },
    { key: "car", label: "拼车", icon: "car" },
    { key: "group", label: "组局", icon: "group" },
    { key: "me", label: "我的", icon: "me" },
  ];

  /* -------- 小工具：骨架屏 -------- */
  function skelCard() {
    return '<div class="skel-card"><div class="skel cover"></div>' +
      '<div style="padding:12px"><div class="skel" style="height:14px;width:70%"></div>' +
      '<div class="skel" style="height:12px;width:50%;margin-top:8px"></div></div></div>';
  }
  function emptyState(art, t, s) {
    return '<div class="empty"><div class="empty__art" style="font-size:64px">' + art +
      '</div><div class="empty__t">' + esc(t) + '</div><div class="empty__s">' + esc(s) + "</div></div>";
  }

  /* -------- 入场动画观察器 -------- */
  let io;
  function reveal(scope) {
    if (!io) {
      io = new IntersectionObserver((es) => {
        es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
      }, { rootMargin: "0px 0px -8% 0px" });
    }
    $$(".reveal", scope).forEach((n) => io.observe(n));
  }

  /* -------- 加载：先骨架，数据就绪后渲染（每个视图只建一次） -------- */
  function load(view, build) {
    const node = $("#view-" + view);
    if (node.dataset.loaded) return;
    node.innerHTML = '<div class="hero-pad"></div>' +
      '<div class="waterfall">' + skelCard() + skelCard() + skelCard() + skelCard() + "</div>";
    ensureData().then(() => { node.innerHTML = build(); node.dataset.loaded = "1"; reveal(node); });
  }
  // 已加载的视图需要原地刷新（如筛选）
  function mount(view, html) { const n = $("#view-" + view); n.innerHTML = html; reveal(n); }

  /* ====================== 视图：首页 ====================== */
  function buildHome() {
    const nav = D.nav.map((n, i) =>
      '<button class="grid-nav__item reveal" style="transition-delay:' + (i * 20) + 'ms">' +
      '<span class="grid-nav__ic">' + n.icon + "</span><span class="grid-nav__lb">" + esc(n.label) + "</span></button>"
    ).join("");

    const sessions = D.sessions.map((s, i) => {
      const pips = Array.from({ length: s.cap }, (_, k) =>
        '<span class="pip' + (k < s.have ? " on" : "") + '"></span>').join("");
      return '<div class="card session reveal" data-session="' + s.id + '" style="transition-delay:' + (i * 40) + 'ms">' +
        '<div class="session__time">' + esc(s.time) + '</div>' +
        '<div class="session__name">' + esc(s.name) + "</div>" +
        '<div class="session__room">' + esc(s.room) + "</div>" +
        '<div class="session__spots"><div class="pips">' + pips + "</div>" +
        '<span class="need">还差 <b>' + Math.max(0, (s.cap - s.have)) + "</b> 人</span></div>" +
        '<button class="btn btn--primary btn--sm session__cta">上车</button></div>';
    }).join("");

    const cards = D.scripts.slice(0, 6).map(cardHTML).join("");

    return (
      '<div class="hero-pad"></div>' +
      '<div class="grid-nav">' + nav + "</div>" +
      '<div class="section"><div class="section__head"><div class="section__title">今日开演</div>' +
      '<span class="section__more">全部场次 ›</span></div></div>' +
      '<div class="rail">' + (sessions || emptyState("📅", "今天还没排场", "挑个本自己开一桌")) + "</div>" +
      '<div class="section"><div class="section__head"><div class="section__title">本周热门</div>' +
      '<span class="section__more">挑本 ›</span></div></div>' +
      '<div class="waterfall">' + cards + "</div>"
    );
  }

  /* ====================== 视图：挑本 ====================== */
  function cardHTML(s) {
    return '<div class="pcard reveal" data-script="' + s.id + '">' +
      '<div class="pcard__cover" style="background:' + (s.grad || _grad(s.id)) + '">' +
      '<span class="emoji">' + (s.emoji || "🎭") + "</span></div>" +
      '<div class="pcard__body"><div class="pcard__title">' + esc(s.title) + "</div>" +
      '<div class="pcard__meta"><span>' + s.players + "人</span><span>" + esc(s.duration) +
      '</span><span class="tag' + (s.hot ? " tag--hot" : "") + '">' + esc(s.difficulty) + "</span></div>" +
      '<div class="pcard__foot"><span class="price">¥' + s.price + "<small>/人</small></span>" +
      '<span class="tag">详情 ›</span></div></div></div>';
  }
  function _grad(i) {
    const G = ["linear-gradient(160deg,#3a2b4d,#15131f)", "linear-gradient(160deg,#1f3a4d,#0f1b22)",
      "linear-gradient(160deg,#4d3a2b,#221a13)", "linear-gradient(160deg,#2b4d3a,#13221a)",
      "linear-gradient(160deg,#4d3b1f,#221a0f)", "linear-gradient(160deg,#2b2b4d,#131322)",
      "linear-gradient(160deg,#3a1f1f,#1a0f0f)", "linear-gradient(160deg,#1f2f4d,#0f1622)"];
    return G[(parseInt(i, 10) || 0) % G.length];
  }
  let scriptFilters = { tag: "", q: "" };
  function buildScripts() {
    const tags = ["全部", "沉浸", "推理", "情感", "欢乐", "恐怖", "机制", "科幻", "新手"];
    const chips = tags.map((t) =>
      '<button class="chip' + (scriptFilters.tag === t || (t === "全部" && !scriptFilters.tag) ? " on" : "") +
      '" data-tag="' + t + '">' + t + "</button>").join("");
    const list = (D.scripts || []).filter((s) => {
      const okTag = !scriptFilters.tag || (s.tags || []).includes(scriptFilters.tag);
      const okQ = !scriptFilters.q || (s.title + (s.tags || []).join("") + (s.desc || "")).toLowerCase().includes(scriptFilters.q.toLowerCase());
      return okTag && okQ;
    });
    const cards = list.length ? list.map(cardHTML).join("")
      : '<div class="empty" style="grid-column:1/-1"><div class="empty__t">没有找到匹配的本子</div>' +
        '<div class="empty__s">换个关键词或筛选试试</div></div>';
    return '<div class="section" style="padding-top:var(--s4)"><div class="chips">' + chips + "</div></div>" +
      '<div class="waterfall">' + cards + "</div>";
  }

  /* ====================== 视图：拼车 ====================== */
  function carRow(c) {
    return '<div class="row reveal" data-car="' + c.id + '">' +
      '<div class="row__top"><div class="avatar">' + esc(c.av) + "</div>" +
      '<div class="row__who"><div class="row__name">' + esc(c.who) + " 开了车</div>" +
      '<div class="row__sub">' + esc(c.script) + " · " + esc(c.time) + "</div></div>" +
      '<span class="tag">拼车</span></div>' +
      '<div class="row__body">' + esc(c.note) + "</div>" +
      '<div class="row__tags">' + (c.tags || []).map((t) => '<span class="tag">' + esc(t) + "</span>").join("") + "</div>" +
      '<div class="row__foot"><span class="need">已 <b>' + c.have + "</b> / 需 " + c.need +
      ' 人</span><button class="btn btn--primary btn--sm">上车</button></div></div>';
  }
  function buildCar() {
    if (!D.cars || !D.cars.length) return emptyState("🚗", "还没有人开车的局", "做第一个发车的人吧");
    return '<div class="list">' + D.cars.map(carRow).join("") + "</div>";
  }

  /* ====================== 视图：组局 ====================== */
  function buildGroup() {
    if (!D.sessions || !D.sessions.length) return emptyState("📅", "今天还没有开演的局", "挑个本自己开一桌");
    const rows = D.sessions.map((s) => {
      const pips = Array.from({ length: s.cap }, (_, k) =>
        '<span class="pip' + (k < s.have ? " on" : "") + '"></span>').join("");
      return '<div class="row reveal" data-session="' + s.id + '">' +
        '<div class="row__top"><div class="avatar" style="background:var(--brand-soft);color:var(--brand)">🎭</div>' +
        '<div class="row__who"><div class="row__name">' + esc(s.name) + "</div>" +
        '<div class="row__sub">' + esc(s.time) + " · " + esc(s.room) + "</div></div></div>" +
        '<div class="row__foot" style="margin-top:12px"><div class="pips">' + pips +
        '</div><span class="need">还差 <b>' + Math.max(0, s.cap - s.have) + "</b> 人</span>" +
        '<button class="btn btn--primary btn--sm">加入</button></div></div>';
    }).join("");
    return '<div class="section" style="padding-top:var(--s4)"><div class="section__head">' +
      '<div class="section__title">今天在开的局</div></div></div>' +
      '<div class="list">' + rows + "</div>";
  }

  /* ====================== 视图：我的 ====================== */
  function buildMe() {
    const m = D.me;
    if (!m || m.guest) {
      return '<div class="empty" style="padding-top:var(--s7)"><div class="empty__art" style="font-size:64px">👤</div>' +
        '<div class="empty__t">你还没登录</div><div class="empty__s">登录后查看你的开本、评价与券包</div>' +
        '<a class="btn btn--primary btn--block" style="max-width:200px;margin:16px auto 0" href="/login">去登录</a></div>';
    }
    const st = m.stats || { bookings: 0, reviews: 0, spent: 0 };
    const menu = D.menu.map((x, i) =>
      '<button class="menu__item reveal" style="transition-delay:' + (i * 20) + 'ms">' +
      '<span class="menu__ic">' + x.icon + "</span>" + esc(x.label) +
      '<span class="arrow">' + svg("back").replace('class="" ', 'style="transform:rotate(180deg)" ') + "</span></button>").join("");
    return '<div class="me-hero reveal"><div class="me-hero__top"><div class="me-hero__av">' + esc(m.initial) +
      '</div><div><div class="me-hero__name">' + esc(m.name) + "</div>" +
      '<div class="me-hero__id">' + esc(m.phone) + (m.id ? " · 会员号 " + esc(m.id) : "") + "</div></div></div>" +
      '<div class="me-stats"><div><b>' + st.bookings + "</b><span>开本</span></div>" +
      '<div><b>' + st.reviews + "</b><span>评价</span></div>" +
      '<div><b>' + st.spent + "</b><span>消费(¥)</span></div></div></div>" +
      '<div class="menu reveal">' + menu + "</div>";
  }

  /* ====================== 详情浮层 ====================== */
  function show(node) { node.classList.add("show"); }
  function hide(node) { node.classList.remove("show"); }

  function openDetailScript(id) {
    const s = (D.scripts || []).find((x) => x.id === id); if (!s) return;
    $("#detailContent").innerHTML =
      '<div class="detail__hero" style="background:' + (s.grad || _grad(s.id)) + '">' +
      '<span class="emoji">' + (s.emoji || "🎭") + "</span>" +
      '<div class="detail__title">' + esc(s.title) + "</div></div>" +
      '<div class="detail__body"><div class="detail__meta">' +
      '<div>人数<b>' + s.players + "</b></div><div>时长<b>' + esc(s.duration) + "</b></div>" +
      '<div>难度<b>' + esc(s.difficulty) + "</b></div><div>单价<b>¥' + s.price + "</b></div></div>" +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:var(--s4)">' +
      (s.tags || []).map((t) => '<span class="tag">#' + esc(t) + "</span>").join("") + "</div>" +
      '<div class="detail__desc">' + esc(s.desc) + "</div></div>" +
      '<div class="detail__bar"><button class="btn btn--ghost btn--block">咨询 DM</button>' +
      '<button class="btn btn--primary btn--block">立即拼车</button></div>';
    show($("#detail"));
    history.pushState({ detail: 1 }, "");
  }

  /* ====================== 底部弹层 ====================== */
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
    let h = location.hash.replace(/^#\/?/, "") || "home";
    const view = TABS.some((t) => t.key === h.split("/")[0]) ? h.split("/")[0] : "home";
    TABS.forEach((t) => {
      const v = $("#view-" + t.key), tab = $('.tab[data-key="' + t.key + '"]');
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
    $("#tabbar").innerHTML = TABS.map((t) =>
      '<button class="tab" data-key="' + t.key + '">' + svg(t.icon) + "<span>" + t.label + "</span></button>").join("");
    $$(".tab").forEach((b) => b.addEventListener("click", () => { location.hash = "#/" + b.dataset.key; }));

    document.addEventListener("click", (e) => {
      const pcard = e.target.closest("[data-script]");
      if (pcard) { openDetailScript(+pcard.dataset.script); return; }
      const sess = e.target.closest("[data-session]");
      if (sess) { const s = (D.sessions || []).find((x) => x.id === +sess.dataset.session); if (s) openDetailScript(s.script); return; }
      const chip = e.target.closest("[data-tag]");
      if (chip) { scriptFilters.tag = chip.dataset.tag === "全部" ? "" : chip.dataset.tag; mount("scripts", buildScripts()); return; }
      const fabAct = e.target.closest("[data-fab]");
      if (fabAct) {
        closeSheet();
        const a = fabAct.dataset.fab;
        if (a === "car") location.hash = "#/car";
        else if (a === "group") location.hash = "#/group";
        else if (a === "script") location.hash = "#/scripts";
        return;
      }
    });

    $("#globalSearch").addEventListener("input", (e) => {
      scriptFilters.q = e.target.value.trim();
      if (location.hash.replace(/^#\/?/, "") !== "scripts") location.hash = "#/scripts";
      else mount("scripts", buildScripts());
    });

    $("#fab").addEventListener("click", openFabSheet);
    $("#sheetMask").addEventListener("click", closeSheet);
    $("#detailBack").addEventListener("click", () => history.back());
    window.addEventListener("popstate", () => { if ($("#detail").classList.contains("show")) hide($("#detail")); });

    window.addEventListener("hashchange", route);
    route();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
