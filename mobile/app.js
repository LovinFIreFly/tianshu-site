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

  function $(s) { return document.querySelector(s); }
  function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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
      D.cars = fb.cars || []; D.talks = fb.talks || []; D.me = fb.me || { guest: true };
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
  function favOn(id) {
    return ((D.me && D.me.favs) || []).indexOf(String(id)) >= 0;
  }
  function toggleFav(id) {
    if (D.me && D.me.guest) { toast('登录后才能收藏'); return; }
    post('/m/api/fav/' + id, new FormData())
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); return; }
        toast(j.on ? '加进「想玩」了' : '已取消收藏');
        var btn = $('#sheet [data-action="toggle-fav"]');
        if (btn) btn.textContent = j.on ? '已收藏 · 点一下取消' : '收藏 · 想玩';
        ensureData(true);
      }).catch(function () { toast('网络开了小差，待会儿再试'); });
  }
  function openScriptSheet(id) {
    var s = findScript(id); if (!s) { toast('剧本信息没找到'); return; }
    setSheetPhoto(s);
    $('#sheet-body').innerHTML =
      '<div class="sheet-no">剧本</div><h2 class="sheet-title">' + esc(s.title) + '</h2>' +
      '<div class="sheet-tags">' +
      (s.tags || []).map(function (x) { return '<span class="tag">' + esc(x) + '</span>'; }).join('') +
      '<span class="tag">' + esc(s.players || '') + '</span><span class="tag">' + esc(s.duration || '') + '</span>' +
      '<span class="tag">难度 ' + esc(s.difficulty || '') + '</span>' +
      (s.price ? '<span class="tag">¥' + esc(s.price) + ' / 人</span>' : '') + '</div>' +
      '<p class="sheet-desc">' + esc(s.desc || '') + '</p>' +
      '<div class="sheet-cta">' +
      '<button class="btn btn-primary btn-block" data-action="open-book" data-id="' + esc(s.id) + '">立即预约</button>' +
      '<button class="btn btn-ghost btn-block" data-action="open-car-create" data-id="' + esc(s.id) + '">拿这个本发一车</button>' +
      '<button class="btn btn-ghost btn-block" data-action="toggle-fav" data-id="' + esc(s.id) + '">' +
      (favOn(s.id) ? '已收藏 · 点一下取消' : '收藏 · 想玩') + '</button>' +
      '</div><div id="sheet-reviews" class="reviews"></div>';
    openSheet('#sheet', '#sheet-mask');
    fetchReviews(s.id);
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
          return '<div class="rev">' + avatarHTML('rev-av', x.avatar, (x.name || '玩')) +
            '<div class="rev-body"><div class="rev-meta"><b>' + esc(x.name || '玩家') + '</b>' +
            '<span><span class="stars">' + '★'.repeat(Number(x.rating) || 0) + '</span> ' + esc(x.time || '') + '</span></div>' +
            '<p>' + esc(x.text || '') + '</p></div></div>';
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
      '<div class="field"><label>指定 DM 手机号（选填）</label><input id="bk-dm" inputmode="numeric" placeholder="有相熟的 DM 就填"></div>' +
      '<div class="err" id="bk-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-book">提交预约</button>' +
      '<p class="sheet-note">定金一人 ¥50（玩完退回）· 开演前 2 小时外取消不影响信用分</p></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitBook() {
    if (D.me && D.me.guest) { toast('请先登录再预约'); openAuth(); return; }
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
      .catch(function () { $('#bk-err').textContent = '网络开了小差，待会儿再试'; });
  }

  /* ---------- 拼车 ---------- */
  function renderCarpool() {
    var body = $('#carpool-body'), empty = $('#carpool-empty');
    empty.hidden = D.cars.length > 0;
    body.innerHTML = D.cars.map(function (c) {
      return '<div class="ccard">' +
        '<div class="chead">' + avatarHTML('car-av', c.av, c.who) +
        '<div class="chead-main"><b>' + esc(c.script || '剧本') + '</b>' +
        '<small>' + esc(c.who || '玩家') + ' 发的车 · ' + esc(c.time || '') + '</small></div>' +
        (c.full ? '<span class="cbadge cbadge-full">满员</span>' : '<span class="cbadge cbadge-go">差 ' + (c.need || 0) + ' 人</span>') +
        '</div>' +
        ((c.members && c.members.length) ? '<div class="cmembers">' + c.members.map(function (m) { return '<span>' + esc(m) + '</span>'; }).join('') + '</div>' : '') +
        '<div class="cmeta">' +
        (c.price ? '<span>¥' + esc(c.price) + ' / 人</span>' : '') +
        (c.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') + '</div>' +
        '<div class="cops">' +
        (c.mine
          ? '<button class="btn btn-ghost" data-action="car-quit" data-id="' + esc(c.id) + '">下车</button>'
          : (c.full
            ? '<button class="btn btn-ghost" data-action="car-wait" data-id="' + esc(c.id) + '">排候补</button>'
            : '<button class="btn btn-primary" data-action="car-join" data-id="' + esc(c.id) + '">上车</button>')) +
        '</div></div>';
    }).join('');
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
      }).catch(function () { $('#car-err').textContent = '网络开了小差，待会儿再试'; });
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
      return '<div class="bkcard">' +
        '<div class="bk-head"><b>' + esc(o.title || '剧本') + '</b>' +
        '<span class="bk-chip bk-st ' + (o.status === 'paid' ? 'pay' : 'warn') + '">' + st + '</span></div>' +
        '<div class="bk-info">' + esc(o.day || '') + ' ' + esc(o.time || '') + ' · ' + (o.players || 1) + ' 人 · 游玩费 ¥' + (o.amount || 0) + ' · 定金 ¥' + (o.deposit || 0) + '</div>' +
        (o.status === 'unpaid' ? '<div class="bk-ops"><a class="btn btn-ghost" href="/me/pay/' + esc(o.id) + '">去付定金 ¥' + (o.payable || o.deposit || 0) + '</a></div>' : '') +
        '</div>';
    }).join('');

    var favs = (me.favs || []).map(function (id) { return findScript(id); }).filter(Boolean);
    $('#favs-sec').hidden = !favs.length;
    $('#favs-note').textContent = favs.length + ' 部';
    $('#favs-list').innerHTML = favs.map(function (s, i) {
      return '<button class="srow" data-action="open-script" data-id="' + esc(s.id) + '">' +
        '<span class="srow-no">0' + (i + 1) + '</span>' +
        thumbHTML(s, i) +
        '<span class="srow-main"><span class="srow-name">' + esc(s.title) + '</span>' +
        '<span class="srow-meta">' + esc(s.players || '') + ' · ' + esc(s.duration || '') + '</span></span>' +
        '<span class="srow-go">详情 ›</span></button>';
    }).join('');

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
    $('#book-body').innerHTML =
      '<div class="sheet-no">资料</div><h2 class="sheet-title">别人看到的是这些</h2>' +
      '<div class="form">' +
      '<div class="field"><label>昵称</label><input id="pf-nick" value="' + esc(p.nick || '') + '" placeholder="拼车时显示的名字"></div>' +
      '<div class="field"><label>性别</label><div class="seg" id="pf-gender">' +
      ['', '男', '女'].map(function (g, i) {
        return '<button type="button" data-gender="' + g + '" class="' + ((p.gender || '') === g ? 'on' : '') + '">' + (i ? g : '不填') + '</button>';
      }).join('') + '</div></div>' +
      '<div class="field"><label>年龄</label><input id="pf-age" type="number" inputmode="numeric" value="' + esc(p.age || '') + '" placeholder="选填"></div>' +
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

  function openReviewSheet(id) {
    var b = ((D.me || {}).records || []).filter(function (x) { return String(x.id) === String(id); })[0];
    if (!b) { toast('预约信息没找到'); return; }
    $('#book-body').innerHTML =
      '<div class="sheet-no">评价</div><h2 class="sheet-title">' + esc(b.name || '剧本') + '</h2>' +
      '<div class="form">' +
      '<div class="field"><label>总体评分</label><div class="times" id="rv-stars">' +
      [1, 2, 3, 4, 5].map(function (n) { return '<button class="dchip" data-star="' + n + '">' + '★'.repeat(n) + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><label>想说的</label><textarea id="rv-text" rows="3" maxlength="800" placeholder="剧情、DM、氛围…… 都可以写"></textarea></div>' +
      '<label class="agree-row"><input type="checkbox" id="rv-anon"><span>匿名评价</span></label>' +
      '<div class="err" id="rv-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-review" data-id="' + esc(id) + '">提交评价</button></div>';
    openSheet('#book-sheet', '#book-mask');
  }
  function submitReview(id) {
    var starBtn = $('#rv-stars .on');
    var fd = new FormData();
    fd.append('rating', starBtn ? starBtn.getAttribute('data-star') : '5');
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

  /* ---------- 登录 ---------- */
  function openAuth() {
    $('#auth-body').innerHTML =
      '<div class="sheet-no">登记</div><h2 class="sheet-title">回到这张桌子</h2>' +
      '<div class="form">' +
      '<div class="field"><label>手机号或用户名</label><input id="auth-account" autocomplete="username" placeholder="13800000000"></div>' +
      '<div class="field"><label>密码</label><input id="auth-pw" type="password" autocomplete="current-password" placeholder="••••••"></div>' +
      '<div class="err" id="auth-err"></div>' +
      '<button class="btn btn-primary btn-block" data-action="submit-login">入场</button>' +
      '<p class="switch">还没有账号？<a href="/register?next=/m/">去注册</a> · <a href="/forgot?next=/m/">忘了密码</a></p></div>';
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
  function openSheet(sheetSel, maskSel) {
    var m = $(maskSel); if (m) m.classList.add('show');
    var s = $(sheetSel); if (s) s.classList.add('show');
  }
  function closeSheets() {
    $$('.sheet').forEach(function (s) { s.classList.remove('show'); });
    $$('.mask').forEach(function (m) { m.classList.remove('show'); });
  }

  /* ---------- 事件 ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target;
    var mask = t.closest('.mask');
    if (mask) { closeSheets(); return; }
    if (t.closest('#sheet-close')) { closeSheets(); return; }

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
      if (a === 'gate-skip') { gateSkipped = true; applyGate(); return; }
      if (a === 'submit-login') { submitLogin(); return; }
      if (a === 'login') { if (!D.me.guest) { switchTab('me'); } else { openAuth(); } return; }
      if (a === 'signup') { window.location.href = '/register?next=/m/'; return; }
      if (a === 'forgot') { window.location.href = '/forgot?next=/m/'; return; }
      if (a === 'logout') { logout(); return; }
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

  function renderAll() {
    renderHome(); renderScripts(); renderCarpool(); renderTalks(); renderMe();
  }

  ensureData();
})();
