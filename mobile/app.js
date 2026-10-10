/* 甜薯剧本杀 · 手机端 v3 · zine 设计 × 旧版全功能（数据驱动） */
(function () {
  'use strict';

  var D = {
    scripts: [], sessions: [], cars: [], talks: [],
    me: { guest: true }, ready: false
  };
  var curTab = 'home', curCat = '全部', query = '';
  var bookCtx = { sid: '', day: '', time: '', players: 1, mode: '拼车', tags: [] };
  var carCtx = { sid: '', day: '', time: '', players: 1, tags: [] };
  var gateSkipped = false;
  var TIMES = ['14:00', '16:00', '18:30', '19:00', '20:30'];
  var CAR_TAGS = ['欢乐局', '新手友好', '剧情党', '推理控', '恐怖胆大'];
  // v6：玩家风格标签（对齐 config.PLAYER_TAGS 冻结值）、拼车筛选、收藏分组、发帖
  var PLAYER_TAGS = ['菠萝头', '水龙头', '推理机', '戏精', '全类型'];
  var carFilter = { q: '', players: '', time: '', diff: '' };
  var favTab = 'want';
  var pfTags = [];
  var FALLBACK_FAQ = [
    { q: '定金能退吗？', a: '开场前 24 小时以上取消全额退（临期按规则扣信用分），到店开演后定金原路退回/可抵尾款。' },
    { q: '能迟到吗？', a: '建议提前 10 分钟到；迟到会拖累整车开本，请提前在「我的预约」联系店家。' },
    { q: '几个人开？', a: '每个本有最低人数，拼车页会显示「还差 X 人」；不够人车主可提前截止或补满发车。' },
    { q: '怎么拼车？', a: '大厅看车 → 点「上车」交押位定金 → 小客服确认后出核销码；也可自己开一车等人。' },
    { q: '核销码哪来？', a: '定金确认到账后，「我的预约」里显示 6 位核销码，到店报码即可。' },
    { q: '改期规则？', a: '开场前可在「我的预约」申请改期，一次一改；改期后原定金随单走。' }
  ];
  var POST_TOPICS = ['情感', '硬核', '恐怖', '欢乐'];

  function $(s) { return document.querySelector(s); }
  function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }

  // ===== 主题三态（日 / 夜 / 跟随系统）：localStorage 'theme' = light|dark|auto =====
  var mqDark = (window.matchMedia && matchMedia('(prefers-color-scheme: dark)')) || null;
  function effTheme(mode) {
    if (mode === 'auto') return (mqDark && mqDark.matches) ? 'dark' : 'light';
    return mode;
  }
  function applyTheme(mode) {
    var root = document.documentElement;
    var eff = effTheme(mode);
    if (mode === 'auto') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', mode);
    var meta = $('#meta-theme'); if (meta) meta.content = (eff === 'dark') ? '#15130F' : '#F1EDE4';
    var btn = $('#theme-toggle');
    if (btn) btn.innerHTML = (mode === 'dark') ? '☾' : (mode === 'auto' ? '◐' : '日');
  }
  function curThemeMode() {
    var saved = null;
    try { saved = localStorage.getItem('theme'); } catch (e) {}
    return (saved === 'light' || saved === 'dark' || saved === 'auto') ? saved : 'auto';
  }
  function initTheme() {
    applyTheme(curThemeMode());
    // auto 跟随系统实时切换
    if (mqDark && mqDark.addEventListener) {
      mqDark.addEventListener('change', function () {
        if (curThemeMode() === 'auto') applyTheme('auto');
      });
    }
    var btn = $('#theme-toggle');
    if (btn) btn.addEventListener('click', function () {
      var order = ['light', 'dark', 'auto'];
      var cur = curThemeMode();
      var next = order[(order.indexOf(cur) + 1) % order.length];
      try { localStorage.setItem('theme', next); } catch (e) {}
      applyTheme(next);
    });
  }
  /* 埋点：启动后约 1.5s sendBeacon 上报 path，不阻塞 */
  function sendTrack() {
    try {
      var path = location.pathname + location.hash;
      var payload = new Blob([JSON.stringify({ path: path })], { type: 'application/json' });
      var done = false;
      if (navigator.sendBeacon) { done = navigator.sendBeacon('/m/api/track', payload); }
      if (!done) fetch('/m/api/track', { method: 'POST', body: payload, credentials: 'same-origin', keepalive: true });
    } catch (e) {}
  }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
      // 2026-10：顺手转义单引号 —— 一旦有人把数据拼进单引号包裹的属性里就会 XSS
      .replace(/'/g, '&#39;');
  }
  function toast(msg) {
    var t = $('#toast') || (function () {
      var d = document.createElement('div'); d.id = 'toast'; d.className = 'toast';
      document.body.appendChild(d); return d;
    })();
    t.textContent = msg; t.classList.add('show');
    clearTimeout(t._tm); t._tm = setTimeout(function () { t.classList.remove('show'); }, 2400);
  }

  /* ---------- 图片 / 头像 ---------- */
  function isImageUrl(u) {
    u = String(u || '').trim();
    if (!u || /^(avatar|placeholder|none|null|undefined|🎭)$/i.test(u)) return false;
    return /^https?:\/\//i.test(u) || /^\/(img|static|upload|m)\//i.test(u);
  }
  function coverURL(s, idx) {
    var u = (s && (s.cover || s.img || s.poster)) || '';
    if (isImageUrl(u)) return u;
    var posters = ['/m/poster-n01.jpg', '/m/poster-n02.jpg'];
    return posters[(idx == null ? 0 : idx) % posters.length];
  }
  function avatarHTML(cls, av, initial) {
    var fb = '<span class="av-fb">' + esc(String(initial || '玩').slice(0, 1)) + '</span>';
    if (isImageUrl(av))
      return '<div class="' + cls + '">' + fb +
        '<img src="' + esc(av) + '" alt="" loading="lazy" onerror="this.remove()"></div>';
    return '<div class="' + cls + '">' + fb + '</div>';
  }
  function gradOf(s) {
    return (s && s.grad) || 'linear-gradient(160deg,#3a2b4d,#15131f)';
  }
  /* 图片一律用 <img> 渲染：加载失败自动退回示范海报，再失败就露出底下的渐变，
     永远不会出现"空白方块 / 破图图标" */
  function photoHTML(s, idx, cls) {
    var cover = coverURL(s, idx);
    var poster = coverURL(null, idx);
    var fb = (cover === poster) ? '' : ' onerror="this.onerror=null;this.src=\'' + poster + '\'"';
    return '<div class="photo ' + (cls || '') + '" style="background:' + gradOf(s) + '">' +
      '<img src="' + esc(cover) + '" alt="" loading="lazy"' + fb + '></div>';
  }
  function thumbHTML(s, idx) {
    var cover = coverURL(s, idx);
    var poster = coverURL(null, idx);
    var fb = (cover === poster) ? '' : ' onerror="this.onerror=null;this.src=\'' + poster + '\'"';
    return '<span class="srow-thumb" style="background:' + gradOf(s) + '">' +
      '<img src="' + esc(cover) + '" alt="" loading="lazy"' + fb + '></span>';
  }

  /* ---------- CSRF：桌面站的守卫要求写操作必须带令牌 ---------- */
  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  function post(url, fd) {
    fd.append('_csrf', csrfToken());
    return fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' });
  }

  /* ---------- 数据 ---------- */
  function fetchJSON(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
  }
  function ensureData(force) {
    if (D.ready && !force) return Promise.resolve();
    return Promise.all([
      fetchJSON('/m/api/scripts'),
      fetchJSON('/m/api/sessions'),
      fetchJSON('/m/api/cars'),
      fetchJSON('/m/api/talks'),
      fetchJSON('/m/api/me')
    ]).then(function (r) {
      D.scripts = Array.isArray(r[0]) ? r[0] : [];
      D.sessions = (r[1] && r[1].sessions) ? r[1].sessions : (Array.isArray(r[1]) ? r[1] : []);
      D.cars = Array.isArray(r[2]) ? r[2] : [];
      D.talks = Array.isArray(r[3]) ? r[3] : [];
      D.me = r[4] || { guest: true };
      D.ready = true;
      renderAll();
    }).catch(function () {
      var fb = window.MOBILE_STATIC || {};
      D.scripts = fb.scripts || []; D.sessions = fb.sessions || [];
      D.cars = fb.cars || []; D.talks = fb.talks || [];
      // 2026-10 修复：接口抖动（网络/超时失败）时**不要**把已登录用户踢成游客 ——
      // 以前这里无条件 D.me = fb.me || {guest:true}，cookie 还在却弹出登录门页，
      // 用户以为被踢下线。只在本地确实没登录态时才退回游客。
      if (!(D.me && D.me.guest === false)) D.me = fb.me || { guest: true };
      renderAll();
    });
  }

  /* ---------- 视图切换 ---------- */
  function switchTab(name) {
    curTab = name;
    $$('.view').forEach(function (v) { v.classList.remove('active'); });
    var view = $('#view-' + name); if (view) view.classList.add('active');
    $$('.tab').forEach(function (t) { t.classList.toggle('on', t.getAttribute('data-tab') === name); });
    window.scrollTo(0, 0);
  }

  /* ---------- 大厅 ---------- */
  function renderHome() {
    var ss = D.scripts.slice(0, 2);
    var hi = $('#hero-imgs'), hc = $('#hero-cap');
    if (ss.length) {
      hi.innerHTML = photoHTML(ss[0], 0, 'hero-dark') +
        (ss[1] ? photoHTML(ss[1], 1, 'hero-bright') : '');
      hc.innerHTML = ss.map(function (s, i) {
        return '<span><b>NO.0' + (i + 1) + '</b> ' + esc(s.title) + '</span>';
      }).join('');
    } else { hi.innerHTML = ''; hc.innerHTML = ''; }

    $('#tonight-note').textContent = D.sessions.length ? '今夜发车' : '今夜暂无排期';
    $('#tonight').innerHTML = D.sessions.slice(0, 6).map(function (s) {
      var left = (s.left == null) ? Math.max(0, (s.cap || 0) - (s.have || 0)) : s.left;
      return '<button class="trow" data-action="open-session" data-id="' + esc(s.id) + '">' +
        '<span class="tt">' + esc(s.time || '') + '</span>' +
        '<span class="tn"><b>' + esc(s.name || '未命名场次') + '</b><small>' + esc(s.room || '') + ' · ' + esc(s.script || '') + '</small></span>' +
        '<span class="ts' + (left <= 1 ? ' low' : '') + '">余 ' + left + '</span></button>';
    }).join('') || '<p class="sheet-note">今天没排场，去本本墙挑一本约起来。</p>';

    $('#collage-note').textContent = '已上架 ' + D.scripts.length + ' 部';
    var cs = D.scripts.slice(0, 4);
    $('#collage').innerHTML = cs.map(function (s, i) {
      return '<article class="pcard" data-action="open-script" data-id="' + esc(s.id) + '" role="button" tabindex="0">' +
        '<div class="pcard-img">' + photoHTML(s, i) +
        '<span class="pcard-no">0' + (i + 1) + '</span><span class="pcard-v">甜薯剧本杀</span></div>' +
        '<div class="pcard-info"><div class="pcard-name">' + esc(s.title) + '</div>' +
        '<div class="pcard-meta">' + esc(s.players || '') + ' · ' + esc(s.duration || '') + '</div></div></article>';
    }).join('');

    var ht = D.talks.slice(0, 3);
    $('#home-talks').innerHTML = ht.map(talkHTML).join('') ||
      '<p class="sheet-note">还没人说话，去唠嗑区开个头。</p>';

    renderHomeHots();
  }
  /* v6：热玩本 / 新本首车 小横滑（api_scripts 全量前端排序） */
  function hcardHTML(s, i, badge) {
    return '<div class="hcard" data-action="open-script" data-id="' + esc(s.id) + '">' +
      '<div class="hcard-img">' + photoHTML(s, i) +
      '<span class="hcard-no">0' + (i + 1) + '</span>' +
      (badge ? '<span class="hcard-badge">' + esc(badge) + '</span>' : '') + '</div>' +
      '<div class="hcard-name">' + esc(s.title) + '</div>' +
      '<div class="hcard-meta">' + esc(s.players || '') + ' · ' + esc(s.difficulty || '') + '</div></div>';
  }
  function renderHomeHots() {
    var boxHot = $('#home-hot'), boxNew = $('#home-new');
    if (!boxHot || !boxNew) return;
    var ss = D.scripts.slice();
    var byRating = function (a, b) {
      return ((Number(b.rating) || 0) - (Number(a.rating) || 0)) || (Number(b.id) > Number(a.id) ? 1 : -1);
    };
    var hot = ss.filter(function (s) { return s.hot || s.isHot || Number(s.rating) >= 4.5; })
      .sort(byRating).slice(0, 6);
    if (!hot.length) hot = ss.slice().sort(byRating).slice(0, 6);
    boxHot.innerHTML = hot.length ? hot.map(function (s, i) { return hcardHTML(s, i, '热'); }).join('')
      : '<p class="sheet-note">还没有热玩本，先看今日排期。</p>';
    var news = ss.filter(function (s) { return s.isNew || s.new; })
      .sort(function (a, b) { return String(b.id) > String(a.id) ? 1 : -1; }).slice(0, 6);
    if (!news.length) news = ss.slice().sort(function (a, b) { return String(b.id) > String(a.id) ? 1 : -1; }).slice(0, 6);
    boxNew.innerHTML = news.length ? news.map(function (s, i) { return hcardHTML(s, i, '新'); }).join('')
      : '<p class="sheet-note">新本路上。</p>';
  }

  /* ---------- 本本墙 ---------- */
  function uniqueTags() {
    var set = [];
    D.scripts.forEach(function (s) { (s.tags || []).forEach(function (t) { if (set.indexOf(t) < 0) set.push(t); }); });
    return set;
  }
  function renderScripts() {
    var tags = uniqueTags();
    var chips = ['全部'].concat(tags);
    $('#chips-row').innerHTML = chips.map(function (t) {
      return '<button class="chip' + (t === curCat ? ' on' : '') + '" role="tab" aria-selected="' +
        (t === curCat) + '" data-cat="' + esc(t) + '">' + esc(t) + '</button>';
    }).join('');
    var q = query.toLowerCase();
    var list = D.scripts.filter(function (s) {
      var okCat = curCat === '全部' || (s.tags || []).indexOf(curCat) >= 0;
      var okQ = !q || String(s.title || '').toLowerCase().indexOf(q) >= 0;
      return okCat && okQ;
    });
    $('#scripts-empty').hidden = list.length > 0;
    $('#scripts-grid').innerHTML = list.map(function (s, i) {
      return '<button class="srow" data-action="open-script" data-id="' + esc(s.id) + '">' +
        '<span class="srow-no">0' + (i + 1) + '</span>' +
        thumbHTML(s, i) +
        '<span class="srow-main"><span class="srow-name">' + esc(s.title) + '</span>' +
        '<span class="srow-meta">' + esc(s.players || '') + ' · ' + esc(s.duration || '') +
        ' <span class="tag">' + esc(s.difficulty || '') + '</span>' +
        ((s.price ? ' <span class="tag">¥' + esc(s.price) + '/人</span>' : '')) + '</span></span>' +
        '<span class="srow-go">详情 ›</span></button>';
    }).join('');
  }

  /* ---------- 剧本 / 场次详情 ---------- */
  function findScript(id) {
    return D.scripts.filter(function (x) { return String(x.id) === String(id); })[0];
  }
  /* ---------- 收藏心愿单三组（want/done/avoid） ---------- */
  function favGroups() {
    var g = (D.me && D.me.favGroups) || null;
    if (g && g.want) return g;
    // 兼容旧字段 me.favs（=want）
    var old = (D.me && D.me.favs) || [];
    return { want: old, done: [], avoid: [] };
  }
  function favGroupOf(id) {
    var g = favGroups(), sid = String(id);
    var keys = ['want', 'done', 'avoid'];
    for (var k = 0; k < keys.length; k++) {
      var arr = g[keys[k]] || [];
      var hit = arr.filter(function (x) { return String(typeof x === 'object' ? x.id : x) === sid; })[0];
      if (hit) return keys[k];
    }
    return '';
  }
  function favGroupScripts(group) {
    var g = favGroups(), arr = g[group] || [];
    return arr.map(function (x) {
      if (x && typeof x === 'object') return x;
      return findScript(x);
    }).filter(Boolean);
  }
  function setFavGroup(id, group, on) {
    if (D.me && D.me.guest) { toast('登录后才能收藏'); return; }
    var fd = new FormData();
    fd.append('group', group);
    fd.append('on', on ? '1' : '0');
    post('/m/api/fav/' + id, fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); return; }
        toast(on ? ('已移入「' + { want: '想玩', done: '已玩', avoid: '避雷' }[group] + '」') : '已移出收藏');
        ensureData(true);
      }).catch(function () { toast('网络开了小差，待会儿再试'); });
  }
  function openScriptSheet(id) {
    var s = findScript(id); if (!s) { toast('剧本信息没找到'); return; }
    setSheetPhoto(s);
    var fg = favGroupOf(s.id);
    var favSeg = ['want', 'done', 'avoid'].map(function (g) {
      return '<button type="button" class="favtab' + (fg === g ? ' on' : '') + '" data-favset="' + g +
        '" data-id="' + esc(s.id) + '" style="flex:1">' +
        { want: '想玩', done: '已玩', avoid: '避雷' }[g] + '</button>';
    }).join('') +
      '<button type="button" class="favtab" data-action="fav-remove" data-id="' + esc(s.id) + '" style="flex:1">移出</button>';
    $('#sheet-body').innerHTML =
      '<div class="sheet-no">剧本</div><h2 class="sheet-title">' + esc(s.title) + '</h2>' +
      '<div class="sheet-tags">' +
      (s.tags || []).map(function (x) { return '<span class="tag">' + esc(x) + '</span>'; }).join('') +
      '<span class="tag">' + esc(s.players || '') + '</span><span class="tag">' + esc(s.duration || '') + '</span>' +
      '<span class="tag">难度 ' + esc(s.difficulty || '') + '</span>' +
      (s.price ? '<span class="tag">¥' + esc(s.price) + ' / 人</span>' : '') + '</div>' +
      '<p class="sheet-desc">' + esc(s.desc || '') + '</p>' +
      '<div id="sheet-extra"></div>' +
      '<div class="sheet-cta">' +
      '<button class="btn btn-primary btn-block" data-action="open-book" data-id="' + esc(s.id) + '">立即预约</button>' +
      '<button class="btn btn-ghost btn-block" data-action="open-car-create" data-id="' + esc(s.id) + '">拿这个本发一车</button>' +
      '<div class="favtabs" style="margin-top:0">' + favSeg + '</div>' +
      '<button class="btn btn-ghost btn-block" data-action="share-script" data-id="' + esc(s.id) + '">分享这本</button>' +
      '</div><div id="sheet-reviews" class="reviews"></div>';
    openSheet('#sheet', '#sheet-mask');
    fetchReviews(s.id);
    fetchScriptDetail(s.id);
  }
  /* v6：剧本详情追加 角色卡 / 演绎视频 / 演后复盘（来源 GET /m/api/scripts/<sid>） */
  function fetchScriptDetail(sid) {
    var box = $('#sheet-extra'); if (!box) return;
    fetchJSON('/m/api/scripts/' + sid).then(function (d) {
      if (!d || d.error) { box.innerHTML = ''; return; }
      var html = '';
      // 角色卡
      var roles = Array.isArray(d.roles) ? d.roles : [];
      if (roles.length) {
        html += '<h4 class="rev-head" style="margin-top:var(--s5)">角色卡</h4>' +
          roles.map(function (r, i) {
            var name = typeof r === 'object' ? (r.name || '') : r;
            var line = (typeof r === 'object') ? (r.line || '') : '';
            var img = (typeof r === 'object') ? r.img : '';
            return '<div class="rolecard"><div class="rolecard-av">' +
              (isImageUrl(img) ? '<img src="' + esc(img) + '" alt="" loading="lazy" onerror="this.remove()">' : '') +
              '</div><div><b>0' + (i + 1) + ' · ' + esc(name) + '</b><small>' + esc(line || '') + '</small></div></div>';
          }).join('');
      }
      // 演绎视频
      // 2026-10 修复：esc() 只转义 & < > "，拦不住 javascript: 这类伪协议，
      // 只要 videoUrl 被写成 javascript:... 点一下就触发 XSS。先做协议白名单。
      if (d.videoUrl && /^(https?:)?\/\//i.test(String(d.videoUrl).trim())) {
        html += '<a class="btn btn-ink btn-block" style="margin-top:var(--s4)" href="' + esc(d.videoUrl) +
          '" target="_blank" rel="noopener">观看演绎视频 ↗</a>';
      }
      // 演后复盘（DM/管理员可见）
      if (d.canSeeReview && d.reviewDoc) {
        html += '<details style="margin-top:var(--s4)"><summary class="rev-head" style="cursor:pointer">演后复盘（仅你可见）</summary>' +
          '<p class="sheet-desc" style="margin-top:var(--s2);white-space:pre-wrap">' + esc(d.reviewDoc) + '</p></details>';
      }
      box.innerHTML = html;
    }).catch(function () { box.innerHTML = ''; });
  }
  function setSheetPhoto(s) {
    var sp = $('#sheet-photo');
    if (!sp) return;
    sp.style.background = gradOf(s);
    var cover = coverURL(s), poster = coverURL(null, 0);
    var fb = (cover === poster) ? '' : ' onerror="this.onerror=null;this.src=\'' + poster + '\'"';
    sp.innerHTML = '<img src="' + esc(cover) + '" alt=""' + fb + '>';
  }

  function openSessionSheet(id) {
    var s = D.sessions.filter(function (x) { return String(x.id) === String(id); })[0];
    if (!s) { toast('场次信息没找到'); return; }
    if (s.sid && findScript(s.sid)) { openScriptSheet(s.sid); return; }
    bookCtx = { sid: '', day: '', time: s.time || '', players: 1, mode: '拼车', tags: [] };
    openBookSheet(bookCtx.sid, s);
  }
  function fetchReviews(sid) {
    var box = $('#sheet-reviews'); if (!box || !sid) return;
    fetchJSON('/m/api/reviews?sid=' + encodeURIComponent(sid)).then(function (list) {
      list = list || [];
      if (!list.length) { box.innerHTML = '<h4 class="rev-head">玩过的人说</h4><p class="sheet-note">还没有评价，做第一个打分的人吧。</p>'; return; }
      var avg = list.reduce(function (a, r) { return a + (Number(r.rating) || 0); }, 0) / list.length;
      box.innerHTML = '<h4 class="rev-head">玩过的人说</h4>' +
        '<div class="score"><b>' + avg.toFixed(1) + '</b><span>' +
        '<span class="stars">' + '★'.repeat(Math.round(avg)) + '</span><br>共 ' + list.length + ' 条真实评价</span></div>' +
        list.slice(0, 8).map(function (x) {
          var dims = x.dims || {};
          var dimTags = Object.keys(dims).map(function (k) {
            return '<span class="rev-dim">' + esc(k) + ' ' + dims[k] + '★</span>';
          }).join('');
          var dimHtml = dimTags ? '<div class="rev-dims" style="margin-top:2px">' + dimTags + '</div>' : '';
          var reply = x.reply ? '<div class="rev-reply"><b>店家回复</b><p>' + esc(x.reply) + '</p></div>' : '';
          return '<div class="rev">' + avatarHTML('rev-av', x.avatar, (x.name || '玩')) +
            '<div class="rev-body"><div class="rev-meta"><b>' + esc(x.name || '玩家') + '</b>' +
            '<span><span class="stars">' + '★'.repeat(Number(x.rating) || 0) + '</span> ' + esc(x.time || '') + '</span></div>' +
            dimHtml +
            '<p>' + esc(x.text || '') + '</p>' + reply + '</div></div>';
        }).join('');
    }).catch(function () {});
  }

  /* ---------- 预约 ---------- */
  function dayChips(sel) {
    var out = [], base = new Date();
    for (var i = 0; i < 7; i++) {
      var d = new Date(base.getTime() + i * 86400000);
      var iso = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
      var wd = '日一二三四五六'[d.getDay()];
      out.push('<button class="dchip' + (iso === sel ? ' on' : '') + '" data-day="' + iso + '">' +
        (i === 0 ? '今天' : (i === 1 ? '明天' : wd)) + '<b>' + (d.getMonth() + 1) + '/' + d.getDate() + '</b></button>');
    }
    return out.join('');
  }
  function openBookSheet(sid, preset) {
    var s = sid ? findScript(sid) : null;
    bookCtx = { sid: sid || '', day: '', time: (preset && preset.time) || '', players: 1, mode: '拼车', tags: [], role: '' };
    var roles = (s && s.allowRolePick && s.roles) ? s.roles : [];
    $('#book-body').innerHTML =
      '<div class="sheet-no">预约</div><h2 class="sheet-title">' + esc(s ? s.title : '选个本开一局') + '</h2>' +
      '<div class="form">' +
      '<div class="field"><label>哪天</label><div class="dates" id="bk-days">' + dayChips('') + '</div></div>' +
      '<div class="field"><label>几点</label><div class="times" id="bk-times">' +
      TIMES.map(function (t) { return '<button class="dchip" data-time="' + t + '">' + t + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><label>几个人</label><div class="stepper">' +
      '<button type="button" data-step="-1">−</button><b id="bk-players">1</b><button type="button" data-step="1">＋</button></div></div>' +
      '<div class="field"><label>拼车还是包场</label><div class="seg" id="bk-mode">' +
      '<button type="button" data-mode="拼车" class="on">拼车 · 等人拼</button><button type="button" data-mode="包车">包场 · 自己包</button></div></div>' +
      (roles.length ? '<div class="field"><label>提前选角（先到先得）</label><div class="times" id="bk-role">' +
        roles.map(function (r) { return '<button class="dchip" data-role="' + esc(r) + '">' + esc(r) + '</button>'; }).join('') + '</div></div>' : '') +
      '<div class="field"><label>指定 DM（选填）</label><select id="bk-dm">' +
        '<option value="">不指定，店家安排</option>' +
        ((D.me.dms || []).map(function (d) { return '<option value="' + esc(d.phone) + '">' + esc(d.name) + '</option>'; }).join('')) +
      '</select></div>' +
      '<div class="err" id="bk-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-book">提交预约</button>' +
      '<p class="sheet-note">定金一人 ¥50（玩完退回）· 开演前 2 小时外取消不影响信用分</p></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitBook() {
    if (D.me && D.me.guest) { toast('请先登录再预约'); openAuth(); return; }
    if (window.__busy) return; window.__busy = true;   // 2026-10 防抖：连点会产生重复预约
    if (!bookCtx.day) { $('#bk-err').textContent = '先挑一天'; return; }
    if (!bookCtx.time) { $('#bk-err').textContent = '再挑个时间'; return; }
    var fd = new FormData();
    fd.append('sid', bookCtx.sid);
    fd.append('ts_day', bookCtx.day);
    fd.append('time', bookCtx.time);
    fd.append('players', bookCtx.players);
    fd.append('mode', bookCtx.mode);
    bookCtx.tags.forEach(function (t) { fd.append('carTags', t); });
    if (bookCtx.role) fd.append('role', bookCtx.role);
    var dm = ($('#bk-dm') || {}).value || '';
    if (dm) fd.append('dmPhone', dm);
    fd.append('agree', '1');
    post('/m/api/book', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#bk-err').textContent = j.error; return; }
        toast(j.msg || '预约成功');
        closeSheets();
        ensureData(true);
      })
      .catch(function () { $('#bk-err').textContent = '网络开了小差，待会儿再试'; })
      .then(function () { window.__busy = false; });   // 释放防抖锁
  }

  /* ---------- 拼车 ---------- */
  function loadCars() {
    var qs = [];
    if (carFilter.q) qs.push('q=' + encodeURIComponent(carFilter.q));
    if (carFilter.players) qs.push('players=' + encodeURIComponent(carFilter.players));
    if (carFilter.time) qs.push('time=' + encodeURIComponent(carFilter.time));
    if (carFilter.diff) qs.push('diff=' + encodeURIComponent(carFilter.diff));
    var url = '/m/api/cars' + (qs.length ? '?' + qs.join('&') : '');
    return fetchJSON(url).then(function (list) {
      D.cars = Array.isArray(list) ? list : [];
      renderCarpool();
    }).catch(function () { /* file:// 下预期报错，保留现有 D.cars */ });
  }
  function carStatusLine(c) {
    if (c.closed) return '<span class="cstatus cstatus-closed">已截止</span>';
    if (c.filled) return '<span class="cstatus cstatus-filled">补满发车</span>';
    if (c.full) return '<span class="cstatus cstatus-closed">已满员</span>';
    var need = c.need || 0;
    if (c.deadlineIn && c.deadlineIn > 0) {
      var hrs = Math.ceil(c.deadlineIn / 3600000);
      return '<div class="cdline">剩 ' + hrs + ' 小时 · 还差 ' + need + ' 人</div>';
    }
    return '<div class="cdline is-dead">还差 ' + need + ' 人</div>';
  }
  function renderCarpool() {
    var body = $('#carpool-body'), empty = $('#carpool-empty');
    empty.hidden = D.cars.length > 0;
    body.innerHTML = D.cars.map(function (c) {
      var badge = c.closed ? '<span class="cbadge cbadge-full">已截止</span>'
        : c.filled ? '<span class="cbadge cbadge-go">补满发车</span>'
        : c.full ? '<span class="cbadge cbadge-full">满员</span>'
        : '<span class="cbadge cbadge-go">差 ' + (c.need || 0) + ' 人</span>';
      var members = (c.members || []).map(function (m) {
        if (m && typeof m === 'object') {
          return { name: m.name || m.who || '玩家', tags: m.tags || [] };
        }
        return { name: m, tags: [] };
      });
      var memberTags = members.map(function (m) { return m.tags; }).reduce(function (a, b) { return a.concat(b); }, []);
      var mtHtml = memberTags.length ? '<div class="member-tags">' +
        memberTags.filter(function (v, i, arr) { return arr.indexOf(v) === i; }).map(function (t) {
          return '<span>' + esc(t) + '</span>';
        }).join('') + '</div>' : '';
      return '<div class="ccard">' +
        '<div class="chead">' + avatarHTML('car-av', c.av, c.who) +
        '<div class="chead-main"><b>' + esc(c.script || '剧本') + '</b>' +
        '<small>' + esc(c.who || '玩家') + ' 发的车 · ' + esc(c.time || c.day || '') + '</small></div>' +
        badge + '</div>' +
        carStatusLine(c) +
        (c.likeMind ? '<div class="likemind">有和你口味相近的玩家在车上</div>' : '') +
        ((members.length) ? '<div class="cmembers">' + members.map(function (m) { return '<span>' + esc(m.name) + '</span>'; }).join('') + '</div>' + mtHtml : '') +
        '<div class="cmeta">' +
        (c.price ? '<span>¥' + esc(c.price) + ' / 人</span>' : '') +
        (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') + '</div>' +
        '<div class="cops">' +
        '<button class="btn btn-ghost" data-action="open-car-detail" data-id="' + esc(c.id) + '">详情</button>' +
        '<button class="btn btn-ghost" data-action="share-car" data-id="' + esc(c.id) + '" data-script="' + esc(c.script || '') + '" data-day="' + esc(c.day || '') + '" data-time="' + esc(c.time || '') + '" data-need="' + esc(c.need || 0) + '">分享</button>' +
        (c.mine
          ? '<button class="btn btn-ghost" data-action="car-quit" data-id="' + esc(c.id) + '">下车</button>'
          : (c.full || c.closed
            ? '<button class="btn btn-ghost" data-action="car-wait" data-id="' + esc(c.id) + '">排候补</button>'
            : '<button class="btn btn-primary" data-action="car-join" data-id="' + esc(c.id) + '">上车</button>')) +
        '</div></div>';
    }).join('');
  }
  function shareText(url, text) {
    if (navigator.share) {
      navigator.share({ title: '甜薯剧本杀', text: text, url: url }).catch(function () {});
    } else {
      copyText(text + ' ' + url);
    }
  }
  function carAct(id, action) {
    if (D.me && D.me.guest) { toast('请先登录再上车'); openAuth(); return; }
    post('/m/api/car/' + id + '/' + action, new FormData())
      .then(function (r) { return r.json(); })
      .then(function (j) {
        toast(j.msg || j.error || '操作完成');
        if (j.ok) ensureData(true);
      }).catch(function () { toast('网络开了小差，待会儿再试'); });
  }
  function openCarSheet(sid) {
    var s = sid ? findScript(sid) : null;
    carCtx = { sid: sid || '', day: '', time: '', players: 1, tags: [] };
    $('#car-body').innerHTML =
      '<div class="sheet-no">发车</div><h2 class="sheet-title">' + esc(s ? s.title : '发一辆拼车') + '</h2>' +
      '<div class="form">' +
      (s ? '' : '<div class="field"><label>挑个本</label><select id="car-sid">' +
        D.scripts.map(function (x) { return '<option value="' + esc(x.id) + '">' + esc(x.title) + '</option>'; }).join('') +
        '</select></div>') +
      '<div class="field"><label>哪天</label><div class="dates" id="car-days">' + dayChips('') + '</div></div>' +
      '<div class="field"><label>几点</label><div class="times" id="car-times">' +
      TIMES.map(function (t) { return '<button class="dchip" data-time="' + t + '">' + t + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><label>你带几个人上车</label><div class="stepper">' +
      '<button type="button" data-cstep="-1">−</button><b id="car-players">1</b><button type="button" data-cstep="1">＋</button></div></div>' +
      '<div class="field"><label>想找什么样的队友（可多选）</label><div class="times" id="car-tags">' +
      CAR_TAGS.map(function (t) { return '<button class="dchip" data-tag="' + t + '">' + t + '</button>'; }).join('') + '</div></div>' +
      '<div class="err" id="car-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-car">发车</button>' +
      '<p class="sheet-note">发车后等队友上车，人齐了系统会通知全车。</p></div>';
    openSheet('#car-sheet', '#car-mask');
  }
  function submitCar() {
    if (D.me && D.me.guest) { toast('请先登录再发车'); openAuth(); return; }
    if (window.__busy) return; window.__busy = true;   // 2026-10 防抖：连点会重复发车
    var sid = carCtx.sid || (($('#car-sid') || {}).value || '');
    if (!sid) { $('#car-err').textContent = '先挑个本'; return; }
    if (!carCtx.day) { $('#car-err').textContent = '先挑一天'; return; }
    if (!carCtx.time) { $('#car-err').textContent = '再挑个时间'; return; }
    var fd = new FormData();
    fd.append('sid', sid); fd.append('ts_day', carCtx.day); fd.append('time', carCtx.time);
    fd.append('players', carCtx.players); fd.append('mode', '拼车');
    carCtx.tags.forEach(function (t) { fd.append('carTags', t); });
    post('/m/api/book', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error || j.ok === false) { $('#car-err').textContent = j.msg || j.error || '发车失败'; return; }
        toast(j.msg || '车发出去了');
        closeSheets(); ensureData(true); switchTab('carpool');
      }).catch(function () { $('#car-err').textContent = '网络开了小差，待会儿再试'; })
      .then(function () { window.__busy = false; });   // 释放防抖锁
  }

  /* ---------- 唠嗑 ---------- */
  function talkHTML(t) {
    return '<div class="talk">' + avatarHTML('tav', t.avatar, t.name) +
      '<div class="tbody"><div class="tmeta"><b>' + esc(t.name || '玩家') + '</b>' + esc(t.ago || '') + '</div>' +
      '<div class="ttext">' + esc(t.text || '') + '</div></div></div>';
  }
  function renderTalks() {
    $('#talk-list').innerHTML = D.talks.map(talkHTML).join('');
    $('#talk-empty').hidden = D.talks.length > 0;
  }
  function sendTalk() {
    var input = $('#talk-input'), text = input.value.trim();
    if (!text) return;
    if (D.me && D.me.guest) { toast('登录后才能发帖'); openAuth(); return; }
    var fd = new FormData(); fd.append('text', text);
    post('/m/api/talks', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); openAuth(); return; }
        input.value = ''; toast('已发到唠嗑区'); ensureData(true);
      }).catch(function () { toast('网络开了小差，待会儿再试'); });
  }

  /* ---------- 我的 ---------- */
  function payLabel(p) {
    if (p === 'paid') return '定金已付';
    if (p === 'closed') return '订单关闭';
    if (p === 'refunded') return '定金已退';
    return '定金待付';
  }
  function renderMe() {
    var me = D.me || {}, card = $('#me-card');
    var logged = !me.guest;
    $('#menu-logout').hidden = !logged;
    $('#menu-admin').hidden = !me.staff;
    $('#menu-profile').hidden = !logged;
    $('#menu-pwd').hidden = !logged;
    $('#menu-login').style.display = logged ? 'none' : '';
    $('#mast-entry').hidden = logged;   // 登录后右上角不再挂「入场登记」
    applyGate();                        // 未登录时盖登录门页
    if (!logged) {
      card.innerHTML = '<div class="idcard"><div class="idav">甜</div>' +
        '<div style="flex:1;min-width:0"><h3>还没入场登记</h3>' +
        '<p>登记后可以预约、拼车、攒积分、领优惠券</p>' +
        '<div class="cops"><button class="btn btn-ink" data-action="login">入场登记</button></div></div></div>';
    } else {
      card.innerHTML = '<div class="idcard">' + avatarHTML('idav', me.avatar, me.initial || me.name) +
        '<div style="flex:1;min-width:0"><h3>' + esc(me.name || '玩家') + '</h3>' +
        '<p>' + esc(me.phone || '') + ' · 邀请码 ' + esc(me.id || '') + '</p>' +
        '<div class="stats">' +
        '<div class="stat"><b>' + (me.credit || 0) + '</b><span>信用分</span></div>' +
        '<div class="stat"><b>' + ((me.coupons || []).length) + '</b><span>可用券</span></div>' +
        '<div class="stat"><b>' + ((me.stats || {}).bookings || 0) + '</b><span>约过</span></div>' +
        '</div></div></div>';
    }
    var cps = me.coupons || [];
    $('#me-coupons-sec').hidden = !cps.length;
    $('#coupon-note').textContent = cps.length + ' 张';
    $('#coupon-list').innerHTML = cps.map(function (c) {
      return '<span class="coupon"><b>¥' + esc(c.amount) + '</b> ' + esc(c.name || '抵扣券') + '</span>';
    }).join('');

    var recs = me.records || [];
    $('#record-note').textContent = recs.length + ' 条';
    $('#record-empty').hidden = recs.length > 0;
    $('#record-list').innerHTML = recs.map(function (b) {
      var chips = '<span class="bk-chip bk-st ' + (b.payStatus === 'paid' ? 'pay' : 'warn') + '">' + payLabel(b.payStatus) + '</span>' +
        '<span class="bk-chip bk-st">' + esc(b.state || '') + '</span>' +
        (b.mode ? '<span class="bk-chip bk-mode">' + esc(b.mode) + '</span>' : '');
      var ops = '';
      if (b.cancelable) {
        ops += '<button class="btn btn-ghost" data-action="open-resched" data-id="' + esc(b.id) + '">改期</button>';
        ops += '<button class="btn btn-ghost" data-action="cancel-booking" data-id="' + esc(b.id) + '">取消预约</button>';
      }
      if (b.raw === 'done' && !b.reviewed) ops += '<button class="btn btn-ghost" data-action="open-review" data-id="' + esc(b.id) + '">去评价</button>';
      if (b.raw === 'done' && b.reviewed) ops += '<span class="bk-chip bk-st pay">已评价 ✓</span>';
      return '<div class="bkcard">' +
        '<div class="bk-head"><span class="bk-emoji">' + esc(b.emoji || '🎭') + '</span><b>' + esc(b.name || '剧本') + '</b>' + chips + '</div>' +
        '<div class="bk-info">' + esc(b.day || '') + ' ' + esc(b.time || '') + ' · ' + (b.players || 1) + ' 人 · 游玩费 ¥' + (b.amount || 0) + ' · 定金 ¥' + (b.deposit || 0) + '</div>' +
        (b.code ? '<div class="bk-code">到店报这个码 <i>' + esc(b.code) + '</i></div>' : '') +
        (ops ? '<div class="bk-ops">' + ops + '</div>' : '') + '</div>';
    }).join('');

    var orders = me.orders || [];
    $('#orders-sec').hidden = !orders.length;
    $('#orders-note').textContent = orders.length + ' 笔';
    $('#orders-list').innerHTML = orders.map(function (o) {
      var st = o.status === 'paid' ? '已付定金' : (o.status === 'closed' ? '已关闭' : '待付定金');
      var payBtn = '';
      if (o.status === 'unpaid') payBtn = '<button class="btn btn-ghost" data-action="open-pay" data-id="' + esc(o.id) + '">去付定金 ¥' + (o.payable || o.deposit || 0) + '</button>';
      else if (o.balStatus === 'unpaid') payBtn = '<button class="btn btn-ghost" data-action="open-pay" data-id="' + esc(o.id) + '">付游玩费 ¥' + (o.amount || 0) + '</button>';
      var invBtn = (o.status === 'paid') ? '<button class="btn btn-ghost" data-action="open-invoice" data-id="' + esc(o.id) + '">申请发票</button>' : '';
      return '<div class="bkcard">' +
        '<div class="bk-head"><b>' + esc(o.title || '剧本') + '</b>' +
        '<span class="bk-chip bk-st ' + (o.status === 'paid' ? 'pay' : 'warn') + '">' + st + '</span></div>' +
        '<div class="bk-info">' + esc(o.day || '') + ' ' + esc(o.time || '') + ' · ' + (o.players || 1) + ' 人 · 游玩费 ¥' + (o.amount || 0) + ' · 定金 ¥' + (o.deposit || 0) + '</div>' +
        ((payBtn || invBtn) ? '<div class="bk-ops">' + payBtn + invBtn + '</div>' : '') +
        '</div>';
    }).join('');

    var fg = favGroups();
    var totalFavs = ((fg.want || []).length + (fg.done || []).length + (fg.avoid || []).length);
    var favList = favGroupScripts(favTab);
    $('#favs-sec').hidden = !logged || !totalFavs;
    $('#favs-note').textContent = { want: '想玩', done: '已玩', avoid: '避雷' }[favTab] + ' ' + favList.length + ' 部';
    $$('#fav-tabs .favtab').forEach(function (b) {
      var on = b.getAttribute('data-favgroup') === favTab;
      b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    $('#favs-list').innerHTML = favList.map(function (s, i) {
      return '<div class="srow" style="padding-right:0">' +
        '<button class="srow" style="border:none;flex:1;padding:0" data-action="open-script" data-id="' + esc(s.id) + '">' +
        '<span class="srow-no">0' + (i + 1) + '</span>' +
        thumbHTML(s, i) +
        '<span class="srow-main"><span class="srow-name">' + esc(s.title) + '</span>' +
        '<span class="srow-meta">' + esc(s.players || '') + ' · ' + esc(s.duration || '') + '</span></span>' +
        '<span class="srow-go">详情 ›</span></button>' +
        '<button class="favrow-remove" data-action="fav-remove" data-id="' + esc(s.id) + '">移出</button></div>';
    }).join('') || '<p class="sheet-note">这组还空着，去本本墙挑一本。</p>';

    var notices = me.notices || [];
    $('#notices-sec').hidden = !notices.length;
    var unread = notices.filter(function (n) { return !n.read; }).length;
    $('#notices-note').textContent = unread ? unread + ' 条未读' : '都看过了';
    $('#notices-list').innerHTML = notices.map(function (n) {
      return '<button class="bkcard" data-action="read-notice" data-id="' + esc(n.id) + '">' +
        '<div class="bk-head"><b>' + esc(n.title) + '</b>' +
        '<span class="bk-chip bk-st ' + (n.read ? '' : 'warn') + '">' + (n.read ? '已读' : '未读') + '</span></div>' +
        '<div class="bk-info">' + esc(n.at || '') + ' · ' + esc(n.body || '') + '</div></button>';
    }).join('');
  }

  function readNotice(id) {
    var fd = new FormData(); fd.append('id', id);
    post('/m/api/notice/read', fd)
      .then(function () { return ensureData(true); })
      .catch(function () {});
  }

  function openProfileSheet() {
    var p = (D.me && D.me.profile) || {};
    pfTags = (D.me && D.me.myTags) ? D.me.myTags.slice() : [];
    var tagHtml = PLAYER_TAGS.map(function (t) {
      return '<button type="button" class="dchip' + (pfTags.indexOf(t) >= 0 ? ' on' : '') + '" data-ptag="' + esc(t) + '">' + esc(t) + '</button>';
    }).join('');
    $('#book-body').innerHTML =
      '<div class="sheet-no">资料</div><h2 class="sheet-title">别人看到的是这些</h2>' +
      '<div class="form">' +
      '<div class="field"><label>昵称</label><input id="pf-nick" value="' + esc(p.nick || '') + '" placeholder="拼车时显示的名字"></div>' +
      '<div class="field"><label>性别</label><div class="seg" id="pf-gender">' +
      ['', '男', '女'].map(function (g, i) {
        return '<button type="button" data-gender="' + g + '" class="' + ((p.gender || '') === g ? 'on' : '') + '">' + (i ? g : '不填') + '</button>';
      }).join('') + '</div></div>' +
      '<div class="field"><label>年龄</label><input id="pf-age" type="number" inputmode="numeric" value="' + esc(p.age || '') + '" placeholder="选填"></div>' +
      '<div class="field"><label>我是哪种玩家（最多 3 个）</label><div class="tagedit" id="pf-tags">' + tagHtml + '</div></div>' +
      '<div class="err" id="pf-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-profile">保存</button>' +
      '<p class="sheet-note">性别和年龄只在拼车时用，方便队友互相找人。</p></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitProfile() {
    var fd = new FormData();
    fd.append('nick', ($('#pf-nick') || {}).value || '');
    fd.append('age', ($('#pf-age') || {}).value || '');
    var gb = $('#pf-gender .on');
    fd.append('gender', gb ? gb.getAttribute('data-gender') : '');
    pfTags.slice(0, 3).forEach(function (t) { fd.append('tags', t); });
    post('/m/api/profile', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#pf-err').textContent = j.error; return; }
        toast('资料已更新'); closeSheets(); ensureData(true);
      }).catch(function () { $('#pf-err').textContent = '网络开了小差，待会儿再试'; });
  }

  /* ---------- 首次进入：专门的登录门页 ---------- */
  function applyGate() {
    var g = $('#gate'); if (!g) return;
    g.hidden = !(D.me && D.me.guest && !gateSkipped);
  }

  function maybeIntro() {
    if (!$('#intro-body') || !$('#intro-sheet')) return;  // 元素已移除，空转（AUD-G-0088 死代码清理）
    var key = 'tsm_intro_v1';
    var seen = false;
    try { seen = window.localStorage.getItem(key) === '1'; } catch (e) { seen = true; }
    if (seen) return;
    $('#intro-body').innerHTML =
      '<div class="sheet-no">先看两眼</div><h2 class="sheet-title">这里怎么玩</h2>' +
      '<div class="steps">' +
      '<div class="step"><span class="step-no">01</span><div><b>挑本</b><p>本本墙里按人数和难度挑，点开能看真实评价和预约。</p></div></div>' +
      '<div class="step"><span class="step-no">02</span><div><b>拼车</b><p>一个人也能开，发辆车等人上车；别人的车直接上。</p></div></div>' +
      '<div class="step"><span class="step-no">03</span><div><b>到店</b><p>付完定金后「我的预约」里会出现核销码，到店报给 DM。</p></div></div>' +
      '</div>' +
      '<button class="btn btn-primary btn-block" data-action="close-intro" style="margin-top:var(--s5)">知道了</button>' +
      '<p class="sheet-note">定金一人 ¥50，玩完退回。</p>';
    openSheet('#intro-sheet', '#intro-mask');
  }
  function closeIntro() {
    try { window.localStorage.setItem('tsm_intro_v1', '1'); } catch (e) {}
    closeSheets();
  }
  function cancelBooking(id) {
    if (!confirm('确定取消这条预约？开演前 2 小时内取消可能影响信用分。')) return;
    post('/m/api/booking/' + id + '/cancel', new FormData())
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); return; }
        toast('已取消'); ensureData(true);
      }).catch(function () { toast('网络开了小差，待会儿再试'); });
  }

  function dayToMs(iso) {
    var p = String(iso || '').split('-');
    if (p.length !== 3) return 0;
    return new Date(+p[0], +p[1] - 1, +p[2]).getTime();
  }

  function openReschedSheet(id) {
    var b = ((D.me || {}).records || []).filter(function (x) { return String(x.id) === String(id); })[0];
    if (!b) { toast('预约信息没找到'); return; }
    $('#book-body').innerHTML =
      '<div class="sheet-no">改期</div><h2 class="sheet-title">' + esc(b.name || '剧本') + '</h2>' +
      '<p class="sheet-desc">定金保留，换个时间就行。</p>' +
      '<div class="form">' +
      '<div class="field"><label>改到哪天</label><div class="dates" id="bk-days">' + dayChips('') + '</div></div>' +
      '<div class="field"><label>改到几点</label><div class="times" id="bk-times">' +
      TIMES.map(function (t) { return '<button class="dchip" data-time="' + t + '">' + t + '</button>'; }).join('') + '</div></div>' +
      '<div class="err" id="bk-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-resched" data-id="' + esc(id) + '">确认改期</button></div>';
    bookCtx.day = ''; bookCtx.time = '';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitResched(id) {
    if (!bookCtx.day || !bookCtx.time) { $('#bk-err').textContent = '挑好日期和时间'; return; }
    var fd = new FormData();
    fd.append('ts', dayToMs(bookCtx.day));
    fd.append('time', bookCtx.time);
    post('/m/api/booking/' + id + '/reschedule', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        toast(j.msg || j.error || '改期完成');
        if (j.ok) { closeSheets(); ensureData(true); }
        else $('#bk-err').textContent = j.msg || j.error || '';
      }).catch(function () { $('#bk-err').textContent = '网络开了小差，待会儿再试'; });
  }

  var rvDims = { plot: 0, dm: 0, vibe: 0, room: 0 };
  function dimRow(key, label) {
    var stars = [1, 2, 3, 4, 5].map(function (n) {
      return '<button type="button" class="dim-star" data-dim="' + key + '" data-n="' + n + '">★</button>';
    }).join('');
    return '<div class="dim-row"><label>' + label + '</label><div class="dim-stars" data-dimbox="' + key + '">' + stars + '</div></div>';
  }
  function openReviewSheet(id) {
    var b = ((D.me || {}).records || []).filter(function (x) { return String(x.id) === String(id); })[0];
    if (!b) { toast('预约信息没找到'); return; }
    rvDims = { plot: 0, dm: 0, vibe: 0, room: 0 };
    $('#book-body').innerHTML =
      '<div class="sheet-no">评价</div><h2 class="sheet-title">' + esc(b.name || '剧本') + '</h2>' +
      '<div class="form">' +
      '<div class="field"><label>总体评分</label><div class="times" id="rv-stars">' +
      [1, 2, 3, 4, 5].map(function (n) { return '<button class="dchip" data-star="' + n + '">' + '★'.repeat(n) + '</button>'; }).join('') + '</div></div>' +
      '<div class="dims">' + dimRow('plot', '剧情') + dimRow('dm', 'DM') + dimRow('vibe', '氛围') + dimRow('room', '房间') + '</div>' +
      '<div class="field"><label>想说的</label><textarea id="rv-text" rows="3" maxlength="800" placeholder="剧情、DM、氛围…… 都可以写"></textarea></div>' +
      '<label class="agree-row"><input type="checkbox" id="rv-anon"><span>匿名评价</span></label>' +
      '<div class="err" id="rv-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-review" data-id="' + esc(id) + '">提交评价</button></div>';
    openSheet('#book-sheet', '#book-mask');
    // 四维分项星星
    $$('#book-body .dim-star').forEach(function (b2) {
      b2.addEventListener('click', function () {
        var key = b2.getAttribute('data-dim'), n = Number(b2.getAttribute('data-n'));
        rvDims[key] = n;
        $$('#book-body .dim-star[data-dim="' + key + '"]').forEach(function (x) {
          x.classList.toggle('on', Number(x.getAttribute('data-n')) <= n);
        });
      });
    });
  }
  function submitReview(id) {
    var starBtn = $('#rv-stars .on');
    var fd = new FormData();
    fd.append('rating', starBtn ? starBtn.getAttribute('data-star') : '5');
    fd.append('plot', rvDims.plot || 0);
    fd.append('dm', rvDims.dm || 0);
    fd.append('vibe', rvDims.vibe || 0);
    fd.append('room', rvDims.room || 0);
    fd.append('text', ($('#rv-text') || {}).value || '');
    fd.append('anonymous', ($('#rv-anon') || {}).checked ? '1' : '0');
    post('/m/api/review/' + id, fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#rv-err').textContent = j.error; return; }
        toast(j.msg || '评价已提交'); closeSheets(); ensureData(true);
      }).catch(function () { $('#rv-err').textContent = '网络开了小差，待会儿再试'; });
  }

  function openPwdSheet() {
    $('#book-body').innerHTML =
      '<div class="sheet-no">密码</div><h2 class="sheet-title">换一个新密码</h2>' +
      '<div class="form">' +
      '<div class="field"><label>现在的密码</label><input id="pw-old" type="password" autocomplete="current-password"></div>' +
      '<div class="field"><label>新密码（至少 6 位）</label><input id="pw-new" type="password" autocomplete="new-password"></div>' +
      '<div class="err" id="pw-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-pwd">保存新密码</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitPwd() {
    var fd = new FormData();
    fd.append('old', ($('#pw-old') || {}).value || '');
    fd.append('password', ($('#pw-new') || {}).value || '');
    post('/m/api/password', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#pw-err').textContent = j.error; return; }
        toast(j.msg || '密码改好了'); closeSheets();
      }).catch(function () { $('#pw-err').textContent = '网络开了小差，待会儿再试'; });
  }

  /* ---------- 注册 / 找回（内联 Sheet，对齐桌面 register/forgot） ---------- */
  function sendCode() {
    var email = ($('#reg-email') || $('#for-email') || {}).value || '';
    var purpose = $('#reg-email') ? 'register' : 'reset';
    if (!email) { toast('先填邮箱'); return; }
    var fd = new FormData(); fd.append('email', email); fd.append('purpose', purpose);
    post('/m/api/code/send', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) { toast(j.msg || (j.ok ? '验证码已发' : '发送失败')); })
      .catch(function () { toast('网络开了小差'); });
  }
  function openSignupSheet() {
    $('#book-body').innerHTML =
      '<div class="sheet-no">注册</div><h2 class="sheet-title">开个新号</h2>' +
      '<div class="form">' +
      '<div class="field"><label>手机号</label><input id="reg-phone" inputmode="numeric" maxlength="11" placeholder="11 位手机号"></div>' +
      '<div class="field"><label>邮箱（收验证码）</label><input id="reg-email" type="email" placeholder="you@example.com"></div>' +
      '<div class="field"><label>邮箱验证码 <button type="button" class="copy-btn" data-action="send-code" style="float:right">获取验证码</button></label>' +
      '<input id="reg-code" placeholder="邮箱收到的 6 位码（本机测试 1234）"></div>' +
      '<div class="field"><label>昵称</label><input id="reg-name" maxlength="20" placeholder="别人拼车时看到的名字"></div>' +
      '<div class="field"><label>密码（至少 6 位）</label><input id="reg-pw" type="password" autocomplete="new-password"></div>' +
      '<div class="field"><label>再输一次密码</label><input id="reg-pw2" type="password" autocomplete="new-password"></div>' +
      '<div class="field"><label>邀请码（选填）</label><input id="reg-invite" placeholder="朋友给的码，两人各得券"></div>' +
      '<div class="err" id="reg-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-signup">注册并领取见面礼</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitSignup() {
    var fd = new FormData();
    fd.append('phone', ($('#reg-phone') || {}).value || '');
    fd.append('email', ($('#reg-email') || {}).value || '');
    fd.append('code', ($('#reg-code') || {}).value || '');
    fd.append('username', ($('#reg-name') || {}).value || '');
    fd.append('password', ($('#reg-pw') || {}).value || '');
    fd.append('password2', ($('#reg-pw2') || {}).value || '');
    fd.append('invite', ($('#reg-invite') || {}).value || '');
    post('/m/api/register', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error || j.ok === false) { $('#reg-err').textContent = j.msg || j.error; return; }
        toast(j.msg || '注册成功');
        // 注册后自动填手机号并切回登录
        var g = $('#gate-account'); if (g && j.phone) g.value = j.phone;
        closeSheets(); openAuth();
      }).catch(function () { $('#reg-err').textContent = '网络开了小差，待会儿再试'; });
  }
  function openForgotSheet() {
    $('#book-body').innerHTML =
      '<div class="sheet-no">找回</div><h2 class="sheet-title">重设密码</h2>' +
      '<p class="sheet-desc">验证码发到你注册时留的邮箱。</p>' +
      '<div class="form">' +
      '<div class="field"><label>手机号</label><input id="for-phone" inputmode="numeric" maxlength="11"></div>' +
      '<div class="field"><label>注册邮箱</label><input id="for-email" type="email"></div>' +
      '<div class="field"><label>验证码 <button type="button" class="copy-btn" data-action="send-code" style="float:right">获取验证码</button></label>' +
      '<input id="for-code" placeholder="本机测试可填 1234"></div>' +
      '<div class="field"><label>新密码（至少 6 位）</label><input id="for-pw" type="password" autocomplete="new-password"></div>' +
      '<div class="field"><label>再输一次</label><input id="for-pw2" type="password" autocomplete="new-password"></div>' +
      '<div class="err" id="for-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-forgot">重设密码</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitForgot() {
    var fd = new FormData();
    fd.append('phone', ($('#for-phone') || {}).value || '');
    fd.append('email', ($('#for-email') || {}).value || '');
    fd.append('code', ($('#for-code') || {}).value || '');
    fd.append('password', ($('#for-pw') || {}).value || '');
    fd.append('password2', ($('#for-pw2') || {}).value || '');
    post('/m/api/reset', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error || j.ok === false) { $('#for-err').textContent = j.msg || j.error; return; }
        toast(j.msg || '密码重设好了'); closeSheets(); openAuth();
      }).catch(function () { $('#for-err').textContent = '网络开了小差，待会儿再试'; });
  }

  /* ---------- 支付闭环（内联 Sheet：客服微信转账 + 我已转账） ---------- */
  var payCtx = { oid: null, couponId: '' };
  function openPaySheet(oid) {
    payCtx = { oid: oid, couponId: '' };
    $('#book-body').innerHTML = '<div class="sheet-no">支付</div><h2 class="sheet-title">加载中…</h2>';
    openSheet('#book-sheet', '#book-mask');
    fetchJSON('/m/api/pay/' + oid).then(function (o) {
      if (o.error) { $('#book-body').innerHTML = '<div class="empty"><h3>' + esc(o.error) + '</h3></div>'; return; }
      payCtx.couponId = '';
      var couponOpts = (o.coupons || []).map(function (c) {
        return '<button type="button" class="coupon-opt" data-coupon="' + esc(c.id) + '">¥' + c.amount + ' ' + esc(c.name) +
               (c.minAmount ? '（满' + c.minAmount + '可用）' : '') + '</button>';
      }).join('');
      var qr = o.groupQr ? '<div class="qr"><img src="' + esc(o.groupQr) + '" alt="顾客群二维码"><p>加不上小客服？群里也能找到人</p></div>' : '';
      $('#book-body').innerHTML =
        '<div class="sheet-no">' + esc(o.dueKind) + '</div><h2 class="sheet-title">《' + esc(o.title) + '》</h2>' +
        '<div class="pay-box">' +
          '<div style="font-size:var(--fs-meta);color:var(--ink-soft)">' + esc(o.day) + ' ' + esc(o.time) + '</div>' +
          '<div class="pay-amt">¥' + (o.due || 0) + '</div>' +
          '<div class="pay-row"><span>小客服微信</span>' +
            '<span class="pay-wx">' + esc(o.serviceWechat || '未配置') + '</span>' +
            '<button type="button" class="copy-btn" data-action="copy-wx" data-wx="' + esc(o.serviceWechat || '') + '">复制</button></div>' +
          qr +
        '</div>' +
        (couponOpts ? '<p class="sheet-note" style="margin-top:var(--s3)">选一张券抵（游玩费可用）：</p><div class="coupon-sel" id="pay-coupons">' + couponOpts + '</div>' : '') +
        '<div class="err" id="pay-err"></div>' +
        '<button class="btn btn-primary btn-block" style="margin-top:var(--s4)" data-action="submit-pay-claim" data-id="' + esc(o.id) + '">我已转账，通知小客服确认</button>' +
        '<p class="sheet-note">本系统无在线支付，点完这单会显示「待小客服确认」，到账后核销码才会放出。</p>';
      // 券选择
      $$('#pay-coupons .coupon-opt').forEach(function (b) {
        b.addEventListener('click', function () {
          $$('#pay-coupons .coupon-opt').forEach(function (x) { x.classList.remove('on'); });
          b.classList.add('on');
          payCtx.couponId = b.getAttribute('data-coupon');
        });
      });
    }).catch(function () { $('#book-body').innerHTML = '<div class="empty"><h3>加载失败</h3></div>'; });
  }
  function submitPayClaim(oid) {
    var fd = new FormData();
    if (payCtx.couponId) fd.append('couponId', payCtx.couponId);
    post('/m/api/pay/' + (oid || payCtx.oid) + '/claim', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#pay-err').textContent = j.error; return; }
        toast(j.msg || '已通知小客服'); closeSheets(); ensureData(true);
      }).catch(function () { $('#pay-err').textContent = '网络开了小差'; });
  }
  function copyText(txt) {
    if (!txt) { toast('没有可复制的内容'); return; }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(function () { toast('已复制：' + txt); }, function () { toast(txt); });
    } else { toast(txt); }
  }

  /* ---------- 给店家留言 ---------- */
  function openMsgSheet() {
    $('#book-body').innerHTML = '<div class="sheet-no">留言</div><h2 class="sheet-title">给店家说两句</h2><p class="sheet-desc">加载中…</p>';
    openSheet('#book-sheet', '#book-mask');
    fetchJSON('/m/api/msgs').then(function (rows) {
      rows = Array.isArray(rows) ? rows : [];
      var list = rows.map(function (m) {
        return '<div class="msg-item"><div class="mt">' + esc(m.cat) + ' · ' + esc(m.at) +
          '</div><p>' + esc(m.text) + '</p>' +
          (m.reply ? '<div class="reply"><b>店家回复：</b>' + esc(m.reply) + '</div>' : '<div class="mt" style="margin-top:4px">待回复</div>') +
          '</div>';
      }).join('') || '<p class="sheet-note">还没留过言。</p>';
      $('#book-body').innerHTML =
        '<div class="sheet-no">留言</div><h2 class="sheet-title">给店家说两句</h2>' +
        '<div class="field"><label>想说的话</label><textarea id="msg-text" rows="3" placeholder="晚了没车、想改时间、对 DM 有要求……"></textarea></div>' +
        '<div class="err" id="msg-err"></div>' +
        '<button class="btn btn-primary btn-block" data-action="submit-msg">发出去</button>' +
        '<h3 style="margin-top:var(--s4);font-size:var(--fs-meta);color:var(--ink-soft)">我的留言</h3>' + list;
    }).catch(function () { $('#book-body').innerHTML = '<div class="empty"><h3>加载失败</h3></div>'; });
  }
  function submitMsg() {
    var fd = new FormData();
    fd.append('text', ($('#msg-text') || {}).value || '');
    fd.append('cat', '💡 建议');
    post('/m/api/msg', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#msg-err').textContent = j.error; return; }
        toast(j.msg || '留言已发'); openMsgSheet();
      }).catch(function () { $('#msg-err').textContent = '网络开了小差'; });
  }

  /* ---------- 车队详情 + 车内聊天 ---------- */
  function openCarDetailSheet(cid) {
    $('#book-body').innerHTML = '<div class="sheet-no">车队</div><h2 class="sheet-title">加载中…</h2>';
    openSheet('#book-sheet', '#book-mask');
    renderCarDetail(cid);
  }
  function renderCarDetail(cid) {
    fetchJSON('/m/api/car/' + cid).then(function (c) {
      if (c.error) { $('#book-body').innerHTML = '<div class="empty"><h3>' + esc(c.error) + '</h3></div>'; return; }
      var msgs = (c.msgs || []).map(function (m) {
        return '<div class="cmsg"><b>' + esc(m.name) + '</b><span>：' + esc(m.text) + '</span></div>';
      }).join('') || '<p class="sheet-note">车里还没人说话。</p>';
      $('#book-body').innerHTML =
        '<div class="sheet-no">车队</div><h2 class="sheet-title">《' + esc(c.script) + '》</h2>' +
        '<p class="sheet-desc">' + esc(c.day) + ' ' + esc(c.time) + ' · 车主 ' + esc(c.who) +
        (c.closed ? ' · 已截止' : c.filled ? ' · 补满发车' : (' · 还差 ' + (c.need || 0) + ' 人')) + '</p>' +
        '<div class="cmsgs">' + msgs + '</div>' +
        '<div class="cmsg-input"><input id="car-msg-text" placeholder="在车里说点什么…">' +
        '<button class="btn btn-primary" data-action="send-carmsg" data-id="' + esc(cid) + '">发</button></div>' +
        '<button class="btn btn-ink btn-block" style="margin-top:var(--s3)" data-action="share-car" data-id="' + esc(cid) + '" data-script="' + esc(c.script || '') + '" data-day="' + esc(c.day || '') + '" data-time="' + esc(c.time || '') + '" data-need="' + esc(c.need || 0) + '">分享这辆车</button>';
    }).catch(function () { $('#book-body').innerHTML = '<div class="empty"><h3>加载失败</h3></div>'; });
  }
  function doShareCar(el) {
    var script = el.getAttribute('data-script') || '剧本';
    var day = el.getAttribute('data-day') || '';
    var time = el.getAttribute('data-time') || '';
    var need = el.getAttribute('data-need') || '?';
    var id = el.getAttribute('data-id');
    var text = '甜薯剧本杀｜《' + script + '》' + day + ' ' + time + ' 还差 ' + need + ' 人，一起？';
    // 2026-10 修复：/m/car/<id> 后端根本没有这个路由，分享出去点开是 404。
    // 改成分享手机站首页（剧本/时间/缺几人都写在文案里），保证链接一定能打开。
    var url = location.origin + '/m/';
    shareText(url, text);
  }
  function doShareScript(el) {
    var s = findScript(el.getAttribute('data-id'));
    if (!s) return;
    var text = '甜薯剧本杀｜《' + s.title + '》，' + esc(s.players || '') + '，一起开本？';
    var url = location.origin + '/m/';
    shareText(url, text);
  }
  function sendCarMsg(cid) {
    var v = ($('#car-msg-text') || {}).value || '';
    if (!v.trim()) { toast('说点什么'); return; }
    var fd = new FormData(); fd.append('text', v);
    post('/m/api/car/' + cid + '/msg', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) { if (!j.error) renderCarDetail(cid); })
      .catch(function () { toast('网络开了小差'); });
  }

  /* ---------- 常见问题 FAQ（GET /m/api/faq，兜底 spec §5.4） ---------- */
  function openFaqSheet() {
    $('#book-body').innerHTML = '<div class="sheet-no">帮助</div><h2 class="sheet-title">常见问题</h2><p class="sheet-desc">加载中…</p>';
    openSheet('#book-sheet', '#book-mask');
    fetchJSON('/m/api/faq').then(function (j) {
      var items = (j && Array.isArray(j.items)) ? j.items : FALLBACK_FAQ;
      renderFaq(items);
    }).catch(function () { renderFaq(FALLBACK_FAQ); });
  }
  function renderFaq(items) {
    var wx = (D.me && D.me.serviceWechat) || '';
    $('#book-body').innerHTML =
      '<div class="sheet-no">帮助</div><h2 class="sheet-title">常见问题</h2>' +
      '<div style="margin-top:var(--s3)">' + items.map(function (it, i) {
        return '<div class="faq-item"><div class="faq-q"><span class="fq-no">Q' + (i + 1) + '</span><span>' + esc(it.q) + '</span></div>' +
          '<p class="faq-a">' + esc(it.a) + '</p></div>';
      }).join('') + '</div>' +
      '<div class="pay-box" style="margin-top:var(--s4)"><div class="pay-row"><span>客服微信</span>' +
      '<span class="pay-wx">' + (wx ? esc(wx) : '待上线') + '</span>' +
      (wx ? '<button type="button" class="copy-btn" data-action="copy-wx" data-wx="' + esc(wx) + '">复制</button>' : '') +
      '</div></div>' +
      '<button class="btn btn-primary btn-block" style="margin-top:var(--s4)" data-action="close-sheets">知道了</button>';
  }

  /* ---------- 客服入口 ---------- */
  function openServiceSheet() {
    var wx = (D.me && D.me.serviceWechat) || '';
    $('#book-body').innerHTML =
      '<div class="sheet-no">客服</div><h2 class="sheet-title">找小客服</h2>' +
      '<p class="sheet-desc">' + (wx ? '加这个微信，拼车、改期、核销都能问。' : '客服微信待配置，可先在下方留言。') + '</p>' +
      (wx ? '<div class="pay-box"><div class="pay-row"><span>客服微信</span><span class="pay-wx">' + esc(wx) + '</span>' +
        '<button type="button" class="copy-btn" data-action="copy-wx" data-wx="' + esc(wx) + '">复制</button></div></div>' : '') +
      '<div class="sheet-cta">' +
      '<button class="btn btn-ink btn-block" data-action="open-msg">给店家留言</button>' +
      '<button class="btn btn-ghost btn-block" data-action="open-faq">常见问题</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }

  /* ---------- 社区：最近帖 + 发帖 ---------- */
  function loadCommRecent() {
    var box = $('#comm-recent'); if (!box) return;
    fetchJSON('/m/api/posts').then(function (list) {
      list = Array.isArray(list) ? list : [];
      box.innerHTML = list.slice(0, 3).map(postHTML).join('') ||
        '<p class="sheet-note">社区刚开张，发第一帖吧。</p>';
    }).catch(function () { box.innerHTML = '<p class="sheet-note">社区加载失败，稍后再来。</p>'; });
  }
  function postHTML(p) {
    var badge = '';
    if (p.postType === 'recruit') {
      badge = '<span class="post-badge">缺 ' + esc(p.recruitNeed || '?') + ' 人</span>' +
        (p.topic ? '<span class="post-badge">' + esc(p.topic) + '</span>' : '') +
        (p.recruitRole ? '<span class="post-badge">' + esc(p.recruitRole) + '</span>' : '');
    } else if (p.topic) { badge = '<span class="post-badge">' + esc(p.topic) + '</span>'; }
    return '<div class="talk">' + avatarHTML('tav', p.avatar, p.nick || p.name) +
      '<div class="tbody"><div class="tmeta"><b>' + esc(p.nick || p.name || '玩家') + '</b>' + esc(p.ago || p.at || '') + '</div>' +
      '<div>' + badge + '</div>' +
      '<div class="ttext">' + esc(p.content || p.text || '') + '</div></div></div>';
  }
  function openPostSheet() {
    if (D.me && D.me.guest) { toast('登录后才能发帖'); openAuth(); return; }
    $('#book-body').innerHTML =
      '<div class="sheet-no">社区</div><h2 class="sheet-title">发个帖</h2>' +
      '<div class="form">' +
      '<div class="field"><label>话题</label><div class="times" id="post-topics">' +
      POST_TOPICS.map(function (t) { return '<button class="dchip" data-topic="' + esc(t) + '">' + esc(t) + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><label>说点什么</label><textarea id="post-content" rows="3" maxlength="300" placeholder="拼车求队友、聊本、约夜宵……"></textarea></div>' +
      '<label class="agree-row"><input type="checkbox" id="post-recruit"><span>缺位招募（缺人一起开本）</span></label>' +
      '<div class="post-recruit-box" id="post-recruit-fields" hidden>' +
      '<div class="field"><label>缺几人（数字）</label><input id="post-need" type="number" inputmode="numeric" min="1" max="8" placeholder="例：2"></div>' +
      '<div class="field" style="margin-top:var(--s2)"><label>缺什么位（例：推理位/情感位/机制位）</label><input id="post-role" placeholder="推理位"></div>' +
      '<div class="field" style="margin-top:var(--s2)"><label>哪本本（剧本名）</label><input id="post-script" placeholder="剧本名"></div>' +
      '</div>' +
      '<div class="err" id="post-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-post">发出去</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitPost() {
    var fd = new FormData();
    fd.append('content', ($('#post-content') || {}).value || '');
    var topic = $('#post-topics .on');
    fd.append('topic', topic ? topic.getAttribute('data-topic') : '');
    var isRecruit = ($('#post-recruit') || {}).checked;
    if (isRecruit) {
      fd.append('postType', 'recruit');
      fd.append('recruitNeed', ($('#post-need') || {}).value || '');
      fd.append('recruitRole', ($('#post-role') || {}).value || '');
      fd.append('recruitScript', ($('#post-script') || {}).value || '');
    }
    post('/m/api/post', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#post-err').textContent = j.error; return; }
        toast(j.msg || '已发出'); closeSheets(); loadCommRecent();
      }).catch(function () { $('#post-err').textContent = '网络开了小差'; });
  }

  /* ---------- 申请发票（paid 订单） ---------- */
  function openInvoiceSheet(oid) {
    $('#book-body').innerHTML =
      '<div class="sheet-no">发票</div><h2 class="sheet-title">申请发票</h2>' +
      '<p class="sheet-desc">填好抬头信息，开好后客服会发到你的邮箱。</p>' +
      '<div class="form">' +
      '<div class="field"><label>发票抬头</label><input id="inv-company" placeholder="个人 / 公司名"></div>' +
      '<div class="field"><label>税号（个人可留空）</label><input id="inv-taxid" placeholder="统一社会信用代码"></div>' +
      '<div class="field"><label>邮箱</label><input id="inv-email" type="email" placeholder="you@example.com"></div>' +
      '<div class="err" id="inv-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-invoice" data-id="' + esc(oid) + '">提交申请</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitInvoice(oid) {
    var fd = new FormData();
    fd.append('oid', oid);
    fd.append('company', ($('#inv-company') || {}).value || '');
    fd.append('taxId', ($('#inv-taxid') || {}).value || '');
    fd.append('email', ($('#inv-email') || {}).value || '');
    post('/m/api/invoice/apply', fd)
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#inv-err').textContent = j.error; return; }
        toast(j.msg || '发票申请已提交'); closeSheets();
      }).catch(function () { $('#inv-err').textContent = '网络开了小差'; });
  }

  /* ---------- 下载 App 入口 ---------- */
  function openAppSheet() {
    $('#book-body').innerHTML =
      '<div class="sheet-no">App</div><h2 class="sheet-title">把甜薯揣兜里</h2>' +
      '<p class="sheet-desc">手机桌面添加快捷方式，约本、拼车、看核销码一步到位。</p>' +
      '<div class="form">' +
      '<div class="field"><label>iPhone（Safari）</label><p class="sheet-note">点底栏「分享」→「添加到主屏幕」。</p></div>' +
      '<div class="field"><label>安卓（Chrome）</label><p class="sheet-note">菜单 →「添加到主屏幕 / 安装应用」。</p></div>' +
      '<button class="btn btn-primary btn-block" data-action="close-sheets">知道了</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }

  /* ---------- 登录 ---------- */
  function openAuth() {
    $('#auth-body').innerHTML =
      '<div class="sheet-no">登记</div><h2 class="sheet-title">回到这张桌子</h2>' +
      '<div class="form">' +
      '<div class="field"><label>手机号 / 昵称</label><input id="auth-account" autocomplete="username" placeholder="请输入手机号/昵称"></div>' +
      '<div class="field"><label>密码</label><input id="auth-pw" type="password" autocomplete="current-password" placeholder="••••••"></div>' +
      '<div class="err" id="auth-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-login">入场</button>' +
      '<p class="switch">还没有账号？<a href="javascript:void(0)" data-action="signup">去注册</a> · <a href="javascript:void(0)" data-action="forgot">忘了密码</a></p></div>';
    openSheet('#auth-sheet', '#auth-mask');
  }
  function submitLogin() {
    var gate = $('#gate') && !$('#gate').hidden;
    var accEl = gate ? $('#gate-account') : $('#auth-account');
    var pwEl = gate ? $('#gate-pw') : $('#auth-pw');
    var errEl = gate ? $('#gate-err') : $('#auth-err');
    var say = function (m) { if (errEl) errEl.textContent = m; };
    var acc = (accEl || {}).value || '', pw = (pwEl || {}).value || '';
    if (!acc || !pw) { say('账号和密码都填一下'); return; }
    var fd = new FormData();
    fd.append('account', acc); fd.append('password', pw);
    var remember = gate ? ($('#gate-remember') || {}).checked !== false : true;
    fd.append('remember', remember ? '1' : '0');
    post('/login?next=/m/', fd)
      .then(function (r) {
        // 2026-10：429 是"试太多次被限流"，原来一律提示"密码不对"，
        // 客人会一直重试，越试越被锁。分开提示。
        if (r.status === 429) { say('试的次数太多了，10 分钟后再来'); return null; }
        if (r.status === 403) { say('页面放太久了，刷新一下再登录'); return null; }
        return ensureData(true);
      })
      .then(function () {
        if (!D.ready) return;
        if (D.me && D.me.guest) { say('账号或密码不对，再试试'); return; }
        toast('欢迎回来，' + (D.me.name || '玩家'));
        closeSheets(); applyGate();
      }).catch(function () { say('网络开了小差，待会儿再试'); });
  }
  function logout() {
    fetch('/logout', { credentials: 'same-origin' })
      .then(function () { return ensureData(true); })
      .then(function () { toast('已退出，下次再来'); });
  }

  /* ---------- Sheet 开关 ---------- */
  // 2026-10：用一个栈记录打开顺序，二级页（比如从剧本详情里点开预约）关掉后能
  // 回到上一级，而不是把所有 sheet 一起关掉。
  var sheetStack = [];
  function openSheet(sheetSel, maskSel) {
    var m = $(maskSel); if (m) m.classList.add('show');
    var s = $(sheetSel); if (s) s.classList.add('show');
    sheetStack.push(sheetSel + '|' + maskSel);
  }
  function closeTop() {
    if (!sheetStack.length) { closeSheets(); return; }
    var top = sheetStack.pop().split('|');
    var s = $(top[0]); if (s) s.classList.remove('show');
    var m = $(top[1]); if (m) m.classList.remove('show');
    if (!$$('.sheet.show').length) $$('.mask').forEach(function (x) { x.classList.remove('show'); });
  }
  function closeSheets() {
    sheetStack = [];
    $$('.sheet').forEach(function (s) { s.classList.remove('show'); });
    $$('.mask').forEach(function (m) { m.classList.remove('show'); });
  }

  /* ---------- 事件 ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target;
    var mask = t.closest('.mask');
    if (mask) { closeTop(); return; }
    if (t.closest('#sheet-close')) { closeTop(); return; }

    var tab = t.closest('.tab');
    if (tab) { switchTab(tab.getAttribute('data-tab')); return; }

    var act = t.closest('[data-action]');
    if (act) {
      var a = act.getAttribute('data-action'), id = act.getAttribute('data-id');
      if (a === 'open-script') { openScriptSheet(id); return; }
      if (a === 'open-session') { openSessionSheet(id); return; }
      if (a === 'open-book') { openBookSheet(id); return; }
      if (a === 'open-car-create') { openCarSheet(id); return; }
      if (a === 'submit-book') { submitBook(); return; }
      if (a === 'submit-car') { submitCar(); return; }
      if (a === 'car-join') { carAct(id, 'join'); return; }
      if (a === 'car-quit') { carAct(id, 'quit'); return; }
      if (a === 'car-wait') { carAct(id, 'wait'); return; }
      if (a === 'cancel-booking') { cancelBooking(id); return; }
      if (a === 'goto-review') { window.location.href = '/me'; return; }
      if (a === 'toggle-fav') { toggleFav(id); return; }
      if (a === 'open-resched') { openReschedSheet(id); return; }
      if (a === 'submit-resched') { submitResched(id); return; }
      if (a === 'open-review') { openReviewSheet(id); return; }
      if (a === 'submit-review') { submitReview(id); return; }
      if (a === 'open-pwd') { openPwdSheet(); return; }
      if (a === 'submit-pwd') { submitPwd(); return; }
      if (a === 'open-profile') { openProfileSheet(); return; }
      if (a === 'submit-profile') { submitProfile(); return; }
      if (a === 'read-notice') { readNotice(id); return; }
      if (a === 'close-intro') { closeIntro(); return; }
      if (a === 'close-sheets') { closeSheets(); return; }
      if (a === 'gate-skip') { gateSkipped = true; applyGate(); return; }
      if (a === 'submit-login') { submitLogin(); return; }
      if (a === 'login') { if (!D.me.guest) { switchTab('me'); } else { openAuth(); } return; }
      if (a === 'signup') { openSignupSheet(); return; }
      if (a === 'forgot') { openForgotSheet(); return; }
      if (a === 'send-code') { sendCode(); return; }
      if (a === 'open-pay') { openPaySheet(id); return; }
      if (a === 'submit-pay-claim') { submitPayClaim(id); return; }
      if (a === 'open-msg') { openMsgSheet(); return; }
      if (a === 'submit-msg') { submitMsg(); return; }
      if (a === 'open-car-detail') { openCarDetailSheet(id); return; }
      if (a === 'send-carmsg') { sendCarMsg(id); return; }
      if (a === 'copy-wx') { copyText(t.getAttribute('data-wx')); return; }
      if (a === 'download-app') { openAppSheet(); return; }
      if (a === 'logout') { logout(); return; }
      if (a === 'open-faq') { openFaqSheet(); return; }
      if (a === 'open-service') { openServiceSheet(); return; }
      if (a === 'open-post') { openPostSheet(); return; }
      if (a === 'submit-post') { submitPost(); return; }
      if (a === 'open-invoice') { openInvoiceSheet(id); return; }
      if (a === 'submit-invoice') { submitInvoice(id); return; }
      if (a === 'clear-cars') {
        carFilter = { q: '', players: '', time: '', diff: '' };
        $('#cf-q').value = ''; $('#cf-players').value = ''; $('#cf-time').value = ''; $('#cf-diff').value = '';
        loadCars(); return;
      }
      if (a === 'share-car') { doShareCar(act); return; }
      if (a === 'share-script') { doShareScript(act); return; }
      if (a === 'fav-remove') { setFavGroup(id, favGroupOf(id) || 'want', false); return; }
      // 后台是电脑版页面：在同标签页里打开（用 _blank 会被手机壳甩到外部浏览器）
      if (a === 'admin') { window.location.href = '/admin'; return; }
      if (a === 'clear-filter') { curCat = '全部'; query = ''; $('#search-input').value = ''; renderScripts(); return; }
      return;
    }

    var chip = t.closest('.chip');
    if (chip) { curCat = chip.getAttribute('data-cat') || '全部'; renderScripts(); return; }

    var dchip = t.closest('.dchip');
    if (dchip) {
      if (dchip.hasAttribute('data-day')) {
        var scope = dchip.closest('.dates').id;
        $$('#' + scope + ' .dchip').forEach(function (x) { x.classList.remove('on'); });
        dchip.classList.add('on');
        if (scope === 'bk-days') bookCtx.day = dchip.getAttribute('data-day');
        if (scope === 'car-days') carCtx.day = dchip.getAttribute('data-day');
        return;
      }
      if (dchip.hasAttribute('data-time')) {
        $$('#' + dchip.closest('.times').id + ' .dchip').forEach(function (x) { x.classList.remove('on'); });
        dchip.classList.add('on');
        var tm = dchip.getAttribute('data-time');
        if (dchip.closest('#book-body')) bookCtx.time = tm; else carCtx.time = tm;
        return;
      }
      if (dchip.hasAttribute('data-tag')) {
        dchip.classList.toggle('on');
        var tag = dchip.getAttribute('data-tag');
        var arr = dchip.closest('#car-body') ? carCtx.tags : bookCtx.tags;
        var i = arr.indexOf(tag);
        if (i >= 0) arr.splice(i, 1); else arr.push(tag);
        return;
      }
    }

    var step = t.closest('[data-step]');
    if (step) {
      bookCtx.players = Math.max(1, Math.min(9, bookCtx.players + Number(step.getAttribute('data-step'))));
      var bp = $('#bk-players'); if (bp) bp.textContent = bookCtx.players;
      return;
    }
    var cstep = t.closest('[data-cstep]');
    if (cstep) {
      carCtx.players = Math.max(1, Math.min(9, carCtx.players + Number(cstep.getAttribute('data-cstep'))));
      var cp = $('#car-players'); if (cp) cp.textContent = carCtx.players;
      return;
    }
    var mode = t.closest('[data-mode]');
    if (mode) {
      $$('#bk-mode button').forEach(function (x) { x.classList.remove('on'); });
      mode.classList.add('on');
      bookCtx.mode = mode.getAttribute('data-mode');
      return;
    }
    var gender = t.closest('[data-gender]');
    if (gender) {
      $$('#pf-gender button').forEach(function (x) { x.classList.remove('on'); });
      gender.classList.add('on');
      return;
    }
    var star = t.closest('[data-star]');
    if (star) {
      $$('#rv-stars .dchip').forEach(function (x) { x.classList.remove('on'); });
      star.classList.add('on');
      return;
    }
    var role = t.closest('[data-role]');
    if (role) {
      role.classList.toggle('on');
      bookCtx.role = role.classList.contains('on') ? role.getAttribute('data-role') : '';
      return;
    }

    // v6：收藏分组选择（剧本 sheet 内 想玩/已玩/避雷）
    var favset = t.closest('[data-favset]');
    if (favset) { setFavGroup(favset.getAttribute('data-id'), favset.getAttribute('data-favset'), true); return; }
    // v6：我的页 收藏三组 tab
    var favtab = t.closest('[data-favgroup]');
    if (favtab) { favTab = favtab.getAttribute('data-favgroup'); renderMe(); return; }
    // v6：资料页 玩家风格标签
    var ptag = t.closest('[data-ptag]');
    if (ptag) {
      var tv = ptag.getAttribute('data-ptag'), ix = pfTags.indexOf(tv);
      if (ix >= 0) pfTags.splice(ix, 1); else if (pfTags.length < 3) pfTags.push(tv);
      ptag.classList.toggle('on', pfTags.indexOf(tv) >= 0); return;
    }
    // v6：发帖 话题
    var topic = t.closest('[data-topic]');
    if (topic) {
      $$('#post-topics .dchip').forEach(function (x) { x.classList.remove('on'); });
      topic.classList.add('on'); return;
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSheets();
    var card = e.target.closest('[data-action="open-script"]');
    if (card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openScriptSheet(card.getAttribute('data-id')); }
  });

  $('#search-input').addEventListener('input', function () {
    query = this.value.trim(); renderScripts();
  });
  $('#talk-send').addEventListener('click', sendTalk);

  // v6：拼车筛选条
  var cfQ = $('#cf-q'), cfP = $('#cf-players'), cfT = $('#cf-time'), cfD = $('#cf-diff');
  if (cfQ) cfQ.addEventListener('input', function () { carFilter.q = this.value.trim(); clearTimeout(cfQ._t); cfQ._t = setTimeout(loadCars, 350); });
  if (cfP) cfP.addEventListener('change', function () { carFilter.players = this.value; loadCars(); });
  if (cfT) cfT.addEventListener('change', function () { carFilter.time = this.value; loadCars(); });
  if (cfD) cfD.addEventListener('change', function () { carFilter.diff = this.value; loadCars(); });
  // v6：发帖 缺位招募开关
  document.addEventListener('change', function (e) {
    if (e.target && e.target.id === 'post-recruit') {
      var box = $('#post-recruit-fields'); if (box) box.hidden = !e.target.checked;
    }
  });

  function renderAll() {
    renderHome(); renderScripts(); renderCarpool(); renderTalks(); renderMe();
    loadCommRecent();
  }

  initTheme();
  ensureData();
  setTimeout(sendTrack, 1500);
})();
