/* 甜薯剧本杀 · 手机端 v5 · 数据驱动（示范页 zine 设计 + 真实接口） */
(function () {
  'use strict';

  var STATIC = window.MOBILE_STATIC || {
    scripts: [], sessions: [], cars: [], talks: [], me: { guest: true }
  };

  var D = {
    scripts: STATIC.scripts.slice(),
    sessions: STATIC.sessions.slice(),
    cars: STATIC.cars.slice(),
    talks: STATIC.talks.slice(),
    me: STATIC.me,
    ready: false
  };

  var curTab = 'home', curCat = '全部', query = '';
  var TAB_TITLES = { home: '大厅', scripts: '本本墙', carpool: '拼车局', talk: '唠嗑区', me: '我的' };

  function $(s) { return document.querySelector(s); }
  function $$(s) { return document.querySelectorAll(s); }
  function esc(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function isImageUrl(u) {
    u = String(u || '').trim();
    if (!u) return false;
    // 过滤掉占位字符串/表情也走兜底
    if (/^(avatar|placeholder|none|null|undefined|🎭)$/i.test(u)) return false;
    return /^https?:\/\//i.test(u) || /^\/(img|static|upload|m)\//i.test(u);
  }
  function coverURL(s, idx) {
    var u = (s && (s.cover || s.img || s.poster)) || '';
    if (isImageUrl(u)) return u;
    // 没图时按顺序复用两张示范海报，避免全站只有渐变
    var posters = ['/m/poster-n01.jpg', '/m/poster-n02.jpg'];
    return posters[(idx == null ? 0 : idx) % posters.length];
  }
  function avatarHTML(cls, av, initial) {
    if (isImageUrl(av))
      return '<div class="' + cls + '"><img src="' + esc(av) + '" alt="" onerror="this.parentNode.innerHTML=\'' + esc(initial || '玩') + '\'"></div>';
    return '<div class="' + cls + '">' + esc(initial || '玩') + '</div>';
  }

  function uniqueTags() {
    var set = [];
    D.scripts.forEach(function (s) {
      (s.tags || []).forEach(function (t) { if (set.indexOf(t) < 0) set.push(t); });
    });
    return set;
  }

  function loadOne(url, fb) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : fb; })
      .catch(function () { return fb; });
  }
  function ensureData() {
    if (D.ready) return Promise.resolve();
    return Promise.all([
      loadOne('/m/api/scripts', STATIC.scripts),
      loadOne('/m/api/sessions', STATIC.sessions),
      loadOne('/m/api/cars', STATIC.cars),
      loadOne('/m/api/talks', STATIC.talks),
      loadOne('/m/api/me', STATIC.me)
    ]).then(function (r) {
      D.scripts = r[0];
      D.sessions = (r[1] && r[1].sessions) ? r[1].sessions : (r[1] || []);
      D.cars = r[2]; D.talks = r[3]; D.me = r[4];
      D.ready = true;
    });
  }

  function renderHome() {
    var ss = D.scripts.slice(0, 2);
    var hi = $('#hero-imgs'), hc = $('#hero-cap');
    if (ss.length) {
      var durl = coverURL(ss[0], 0), burl = coverURL(ss[1] || {}, 1);
      hi.innerHTML = '<div class="photo hero-dark" style="background-image:url(\'' + esc(durl) + '\'),' + esc(ss[0].grad) + '"></div>' +
        (ss[1] ? '<div class="photo hero-bright" style="background-image:url(\'' + esc(burl) + '\'),' + esc(ss[1].grad) + '"></div>' : '');
      hc.innerHTML = ss.map(function (s, i) {
        return '<span><b>NO.0' + (i + 1) + '</b> ' + esc(s.title) + '</span>';
      }).join('');
    } else { hi.innerHTML = ''; hc.innerHTML = ''; }

    var t = $('#tonight');
    if (D.sessions.length) {
      $('#tonight-note').textContent = '今夜 ' + D.sessions.length + ' 场';
      var rows = D.sessions.slice(0, 6).map(function (s) {
        return '<div class="trow" role="button" tabindex="0" data-action="session" data-id="' + esc(s.id) + '">' +
          '<span class="tt">' + esc(s.time || '') + '</span>' +
          '<div class="tn"><b>' + esc(s.name || '未命名场次') + '</b><small>' + esc(s.room || '') + '</small></div>' +
          '<span class="ts">余 ' + (s.left || 0) + '</span></div>';
      }).join('');
      t.innerHTML = '<div class="tonight-row"><span class="big-zero">' + D.sessions.length + '</span><span class="big-unit">场</span></div>' +
        '<p class="tonight-line">今晚这些场次要开本，挑一个凑进去。</p>' +
        '<div class="tonight-list">' + rows + '</div>' +
        '<div class="cta-row"><button class="btn btn-primary btn-block" data-action="carpool">发起拼车</button>' +
        '<button class="btn btn-ghost btn-block" data-action="book">包下整场</button></div>';
    } else {
      $('#tonight-note').textContent = '今夜发车';
      t.innerHTML = '<div class="tonight-row"><span class="big-zero">0</span><span class="big-unit">场</span></div>' +
        '<p class="tonight-line">今晚还没人发车。想玩的话，你来开一局。</p>' +
        '<div class="cta-row"><button class="btn btn-primary btn-block" data-action="carpool">发起拼车</button>' +
        '<button class="btn btn-ghost btn-block" data-action="book">包下整场</button></div>';
    }

    var cs = D.scripts.slice(0, 3);
    $('#collage-note').textContent = '已上架 ' + D.scripts.length + ' 部';
    $('#collage').innerHTML = cs.map(function (s, i) {
      var cls = i % 2 ? 'pcard-b' : 'pcard-a';
      return '<article class="pcard ' + cls + '" data-id="' + esc(s.id) + '" role="button" tabindex="0" aria-label="查看剧本：' + esc(s.title) + '">' +
        '<div class="pcard-img"><div class="photo" style="background-image:url(\'' + esc(coverURL(s, i)) + '\'),' + esc(s.grad) + '"></div>' +
        '<span class="pcard-no">0' + (i + 1) + '</span><span class="pcard-v">甜薯剧本杀</span></div>' +
        '<div class="pcard-info"><div class="pcard-name">' + esc(s.title) + '</div>' +
        '<div class="pcard-meta">' + esc(s.players) + ' · ' + esc(s.duration) + '</div>' +
        '<div class="pcard-tags">' + (s.tags || []).map(function (x) { return '<span class="tag">' + esc(x) + '</span>'; }).join('') +
        (s.hot ? '<span class="tag tag-ok">热门</span>' : '') + '</div></div></article>';
    }).join('');

    var ht = D.talks.slice(0, 2).map(talkHTML).join('');
    $('#home-talks').innerHTML = ht || '<p class="tonight-line">还没人唠嗑，去唠嗑区开个头。</p>';
  }

  function renderScripts() {
    var chips = ['全部'].concat(uniqueTags());
    $('#chips-row').innerHTML = chips.map(function (c) {
      return '<button class="chip' + (c === curCat ? ' on' : '') + '" data-chip="' + esc(c) + '">' + esc(c) + '</button>';
    }).join('');
    var list = D.scripts.filter(function (s) {
      var okCat = curCat === '全部' || (s.tags || []).indexOf(curCat) > -1;
      var okQ = !query || (s.title || '').indexOf(query) > -1;
      return okCat && okQ;
    });
    $('#scripts-grid').innerHTML = list.map(function (s, i) {
      return '<div class="srow" data-id="' + esc(s.id) + '" role="button" tabindex="0" aria-label="查看剧本：' + esc(s.title) + '">' +
        '<span class="srow-no">0' + (i + 1) + '</span>' +
        '<div class="srow-thumb" style="background-image:url(\'' + esc(coverURL(s, i)) + '\'),' + esc(s.grad) + '"></div>' +
        '<div class="srow-main"><div class="srow-name">' + esc(s.title) + '</div>' +
        '<div class="srow-meta">' + esc(s.players) + ' · ' + esc(s.duration) +
        ' <span class="tag">' + esc(s.difficulty) + '</span></div></div></div>';
    }).join('');
    $('#scripts-empty').hidden = list.length > 0;
  }

  function renderCars() {
    var body = $('#carpool-body');
    var head = '<div class="cta-row" style="padding:var(--s4) var(--page-pad) 0"><button class="btn btn-primary btn-block" data-action="carpool">发起拼车</button></div>';
    if (!D.cars.length) {
      body.innerHTML = '<div class="carpool-empty"><div class="zero">0</div><h3>今晚还没有局</h3><p>你是第一个想玩的人。发个车，等人上车。</p></div>';
      return;
    }
    body.innerHTML = head + '<div class="carlist">' + D.cars.map(function (c) {
      return '<div class="car"><div class="car-top">' + avatarHTML('car-av', c.av, (c.who || '玩')[0]) +
        '<div class="car-main"><div class="car-name">' + esc(c.script || '剧本') + '</div>' +
        '<div class="car-sub">' + esc(c.time || '') + ' · 车主 ' + esc(c.who || '玩家') + '</div></div></div>' +
        '<div class="car-note">' + esc(c.note || '') + '</div>' +
        '<div class="car-tags">' + (c.tags || []).map(function (x) { return '<span class="tag">' + esc(x) + '</span>'; }).join('') + '</div></div>';
    }).join('') + '</div>';
  }

  function talkHTML(t) {
    return '<div class="titem">' + avatarHTML('tav', t.avatar, (t.name || '玩')[0]) +
      '<div class="tbody"><div class="tmeta"><span class="tname">' + esc(t.name || '玩家') +
      '</span><span class="ttime">' + esc(t.ago || '') + '</span></div>' +
      '<p class="ttext">' + esc(t.text || '') + '</p></div></div>';
  }
  function renderTalks() {
    if (!D.talks.length) { $('#talk-list').innerHTML = ''; $('#talk-empty').hidden = false; return; }
    $('#talk-empty').hidden = true;
    $('#talk-list').innerHTML = D.talks.map(talkHTML).join('');
  }
  function sendTalk() {
    var input = $('#talk-input');
    var text = input.value.trim();
    if (!text) return;
    if (D.me && D.me.guest) { toast('登录后才能发帖'); openAuth('login'); return; }
    var fd = new FormData();
    fd.append('text', text);
    fetch('/m/api/talks', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); openAuth('login'); return; }
        input.value = ''; toast('已发到唠嗑区'); ensureData().then(renderTalks);
      })
      .catch(function () { toast('网络开了小差，待会儿再试'); });
  }

  function bookSession(btn) {
    if (D.me && D.me.guest) { toast('请先登录再预约'); openAuth('login'); return; }
    var fd = new FormData();
    fd.append('sid', btn.getAttribute('data-sid'));
    fd.append('sessionId', btn.getAttribute('data-session'));
    fd.append('players', '1');
    fetch('/m/api/book', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); return; }
        toast(j.msg || '预约成功');
        closeAllSheets();
        ensureData().then(function () { renderHome(); renderMe(); });
      })
      .catch(function () { toast('网络开了小差，待会儿再试'); });
  }

  function cancelBooking(id) {
    if (!id) return;
    if (!confirm('确定取消这条预约？')) return;
    fetch('/m/api/booking/' + id + '/cancel', { method: 'POST', credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { toast(j.error); return; }
        toast('已取消');
        ensureData().then(renderMe);
      })
      .catch(function () { toast('网络开了小差，待会儿再试'); });
  }

  function renderMe() {
    var me = D.me || {}, card = $('#me-card');
    if (me.guest) {
      card.innerHTML = '<div class="idcard"><div class="idav">甜</div><div><h3>还没入场登记</h3><p>登记后能看到你的打本记录、优惠券和积分</p></div></div>';
    } else {
      var coupons = (me.coupons || []).slice(0, 3).map(function (c) {
        return '<span class="cpill">' + esc(c.name) + ' ¥' + (c.amount || 0) + '</span>';
      }).join('');
      card.innerHTML = '<div class="idcard">' + avatarHTML('idav', me.avatar, me.initial) +
        '<div><h3>' + esc(me.name || '玩家') + '</h3><p>' + esc(me.phone || '') + ' · 邀请码 ' + esc(me.id || '') + '</p>' +
        '<div class="idstat"><span>积分 ' + (me.credit || 0) + '</span>' + coupons + '</div></div></div>';
    }
    var recs = me.records || [];
    $('#record-note').textContent = recs.length + ' 条';
    if (!recs.length) { $('#record-list').innerHTML = ''; $('#record-empty').hidden = false; }
    else {
      $('#record-empty').hidden = true;
      $('#record-list').innerHTML = recs.map(function (r) {
        var canCancel = (r.state === '待开演' || r.state === '已预约');
        return '<div class="rrow" ' + (r.id ? 'data-id="' + esc(r.id) + '"' : '') + '>' +
          '<div class="rmain"><div class="rname">' + esc(r.name || '剧本') +
          '</div><div class="rtime">' + esc(r.time || '') + '</div></div>' +
          '<button class="st ' + (r.state === '已取消' ? 'st-warn' : 'st-ok') + '" ' +
          (canCancel ? 'data-action="cancel-booking" data-id="' + esc(r.id) + '"' : '') +
          '>' + esc(r.state || '已预约') + '</button></div>';
      }).join('');
    }
  }

  function showSheet(sel, mask) {
    $(sel).classList.add('show'); $(mask).classList.add('show'); document.body.style.overflow = 'hidden';
  }
  function hideSheet(sel, mask) {
    $(sel).classList.remove('show'); $(mask).classList.remove('show'); document.body.style.overflow = '';
  }
  function closeAllSheets() {
    ['#sheet', '#car-sheet', '#auth-sheet'].forEach(function (s) { $(s).classList.remove('show'); });
    ['#sheet-mask', '#car-mask', '#auth-mask'].forEach(function (m) { $(m).classList.remove('show'); });
    document.body.style.overflow = '';
  }

  function openSheet(id) {
    var s = D.scripts.filter(function (x) { return x.id === id; })[0];
    if (!s) return;
    $('#sheet-photo').style.backgroundImage = 'url(' + coverURL(s) + '), ' + s.grad;
    var tags = (s.tags || []).map(function (x) { return '<span class="tag">' + esc(x) + '</span>'; }).join('') +
      '<span class="tag">' + esc(s.players) + '</span><span class="tag">' + esc(s.duration) + '</span>' +
      '<span class="tag">难度 ' + esc(s.difficulty) + '</span>';
    $('#sheet-body').innerHTML = '<div class="sheet-no">' + esc(s.id) + '</div><h2 class="sheet-title">' + esc(s.title) + '</h2>' +
      '<div class="sheet-tags">' + tags + '</div><p class="sheet-desc">' + esc(s.desc || '') + '</p>' +
      '<div class="sheet-cta"><button class="btn btn-primary btn-block" data-action="join" data-id="' + esc(s.id) + '">拼车入局</button>' +
      '<button class="btn btn-ghost btn-block" data-action="book" data-id="' + esc(s.id) + '">包下整场</button></div>' +
      '<p class="sheet-note">拼车和包场走桌面下单，点完跳过去。</p>';
    showSheet('#sheet', '#sheet-mask');
    fetchReviews(s.id);
  }

  function fetchReviews(sid) {
    fetch('/m/api/reviews?sid=' + encodeURIComponent(sid), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (list) {
        var box = $('#sheet-reviews');
        if (!box || !list.length) { if (box) box.innerHTML = ''; return; }
        box.innerHTML = '<h4 class="rev-head">玩过的人说</h4>' + list.map(function (x) {
          return '<div class="rev">' + avatarHTML('rev-av', x.avatar, (x.name || '玩')[0]) +
            '<div class="rev-body"><div class="rev-meta"><b>' + esc(x.name) + '</b><span>' + esc(x.time) + '</span></div>' +
            '<p>' + esc(x.text) + '</p></div></div>';
        }).join('');
      })
      .catch(function () {});
  }

  function openSessionSheet(id) {
    var s = D.sessions.filter(function (x) { return String(x.id) === String(id); })[0];
    if (!s) { toast('场次信息没找到'); return; }
    var script = D.scripts.filter(function (x) { return String(x.id) === String(s.sid); })[0];
    $('#sheet-photo').style.backgroundImage = 'url(' + coverURL(script || s, 0) + '), ' + ((script && script.grad) || s.grad || 'var(--paper-deep)');
    $('#sheet-body').innerHTML = '<div class="sheet-no">场次</div><h2 class="sheet-title">' + esc(s.name || '未命名场次') + '</h2>' +
      '<p class="sheet-desc">' + esc(s.time || '') + ' · ' + esc(s.room || '') + '<br>剧本：' + esc(s.script || '待定') + '</p>' +
      '<div class="sheet-cta"><button class="btn btn-primary btn-block" data-action="book-session" data-sid="' + esc(s.sid) + '" data-session="' + esc(s.id) + '">报名占位</button>' +
      '<button class="btn btn-ghost btn-block" data-action="close-sheet">先不约</button></div>' +
      '<div id="sheet-reviews" class="reviews"></div>';
    showSheet('#sheet', '#sheet-mask');
    if (s.sid) fetchReviews(s.sid);
  }

  function openCarSheet() {
    if (D.me && D.me.guest) { toast('请先登录再发车'); openAuth('login'); return; }
    var sel = $('#car-script');
    sel.innerHTML = D.scripts.map(function (s) {
      return '<option value="' + esc(s.id) + '">' + esc(s.title) + '</option>';
    }).join('');
    $('#car-err').textContent = '';
    showSheet('#car-sheet', '#car-mask');
  }

  function authHead(t, sub) {
    return '<div class="sheet-no">登记</div><h2 class="sheet-title">' + t + '</h2><p class="sheet-desc">' + sub + '</p>';
  }
  function openAuth(mode) {
    var b = $('#auth-body');
    if (mode === 'login') {
      b.innerHTML = authHead('入场登记', '登个记，挑本拼车一条龙') +
        '<form class="form" action="/login?next=/m/" method="post">' +
        '<div class="field"><label>手机号 / 用户名</label><input name="account" required></div>' +
        '<div class="field"><label>密码</label><input name="password" type="password" required></div>' +
        '<input type="hidden" name="remember" value="1">' +
        '<button class="btn btn-primary btn-block" type="submit">登录</button></form>' +
        '<p class="switch">还没账号？<a data-auth="signup">去注册</a> · <a data-auth="forgot">忘密码</a></p>';
    } else if (mode === 'signup') {
      b.innerHTML = authHead('注册新账号', '手机号当账号，验证码发到邮箱') +
        '<form class="form" action="/register?next=/m/" method="post">' +
        '<div class="field"><label>手机号</label><input name="phone" pattern="1[0-9]{10}" required></div>' +
        '<div class="field"><label>邮箱</label><input name="email" type="email" required></div>' +
        '<div class="field"><label>验证码（本地测试填 1234）</label><input name="code" required></div>' +
        '<div class="field"><label>昵称</label><input name="username" required></div>' +
        '<div class="field"><label>密码（≥6 位）</label><input name="password" type="password" required></div>' +
        '<div class="field"><label>再输一次</label><input name="password2" type="password" required></div>' +
        '<div class="field"><label>邀请码（选填）</label><input name="invite"></div>' +
        '<input type="hidden" name="agree" value="1">' +
        '<button class="btn btn-primary btn-block" type="submit">注册</button></form>' +
        '<p class="switch">已有账号？<a data-auth="login">去登录</a></p>';
    } else {
      b.innerHTML = authHead('找回密码', '手机号 + 邮箱验证码重设') +
        '<form class="form" action="/forgot?next=/m/" method="post">' +
        '<div class="field"><label>手机号</label><input name="phone" required></div>' +
        '<div class="field"><label>邮箱</label><input name="email" type="email" required></div>' +
        '<div class="field"><label>验证码（本地测试填 1234）</label><input name="code" required></div>' +
        '<div class="field"><label>新密码（≥6 位）</label><input name="password" type="password" required></div>' +
        '<div class="field"><label>再输一次</label><input name="password2" type="password" required></div>' +
        '<button class="btn btn-primary btn-block" type="submit">重设密码</button></form>' +
        '<p class="switch">想起来了？<a data-auth="login">去登录</a></p>';
    }
    showSheet('#auth-sheet', '#auth-mask');
  }

  function goTab(tab) {
    if (curTab === tab || !$('#view-' + tab)) return;
    curTab = tab;
    $$('.tab, .tab-fab').forEach(function (t) { t.classList.toggle('on', t.getAttribute('data-tab') === tab); });
    $$('.view').forEach(function (v) { v.classList.remove('active'); });
    $('#view-' + tab).classList.add('active');
    if (tab === 'home') renderHome();
    else if (tab === 'scripts') renderScripts();
    else if (tab === 'carpool') renderCars();
    else if (tab === 'talk') renderTalks();
    else if (tab === 'me') renderMe();
    history.pushState(null, '', '#' + tab);
    document.title = TAB_TITLES[tab] + ' · 甜薯剧本杀';
    window.scrollTo(0, 0);
  }

  var toastTimer = null;
  function toast(msg) {
    var t = $('#toast');
    t.textContent = msg; t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 2500);
  }

  document.addEventListener('click', function (e) {
    var auth = e.target.closest('[data-auth]');
    if (auth) { openAuth(auth.getAttribute('data-auth')); return; }
    var act = e.target.closest('[data-action]');
    if (act) {
      var a = act.getAttribute('data-action');
      if (a === 'login') openAuth('login');
      else if (a === 'signup') openAuth('signup');
      else if (a === 'forgot') openAuth('forgot');
      else if (a === 'carpool') openCarSheet();
      else if (a === 'book') toast('包场请到桌面端下单');
      else if (a === 'join') toast('拼车入局请到桌面端下单');
      else if (a === 'clear-filter') { curCat = '全部'; query = ''; $('#search-input').value = ''; renderScripts(); }
      else if (a === 'book-session') { bookSession(act); return; }
      else if (a === 'cancel-booking') { cancelBooking(act.getAttribute('data-id')); return; }
      else if (a === 'close-sheet') { closeAllSheets(); return; }
      return;
    }
    var chip = e.target.closest('.chip');
    if (chip) { curCat = chip.getAttribute('data-chip'); renderScripts(); return; }
    var card = e.target.closest('[data-id]');
    if (card && (card.classList.contains('pcard') || card.classList.contains('srow'))) {
      openSheet(card.getAttribute('data-id')); return;
    }
    var sess = e.target.closest('[data-action="session"]');
    if (sess) { openSessionSheet(sess.getAttribute('data-id')); return; }
    var tabBtn = e.target.closest('[data-tab]');
    if (tabBtn) { goTab(tabBtn.getAttribute('data-tab')); return; }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllSheets();
  });

  $('#search-input').addEventListener('input', function () { query = this.value.trim(); renderScripts(); });
  $('#talk-send').addEventListener('click', sendTalk);
  $('#talk-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendTalk(); }
  });
  $('#sheet-mask').addEventListener('click', closeAllSheets);
  $('#sheet-close').addEventListener('click', closeAllSheets);
  $('#car-mask').addEventListener('click', closeAllSheets);
  $('#auth-mask').addEventListener('click', closeAllSheets);

  $('#car-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target;
    var date = f.date.value, time = f.time.value;
    if (!date || !time) { $('#car-err').textContent = '选好日期和时间'; return; }
    var ts = new Date(date + 'T' + time).getTime();
    if (!ts || isNaN(ts)) { $('#car-err').textContent = '日期时间不对'; return; }
    var fd = new FormData(f);
    fd.delete('date'); fd.delete('time');
    fd.append('ts', ts);
    var picked = D.scripts.filter(function (s) { return s.id === f.sid.value; })[0];
    fd.append('title', (picked && picked.title) || '剧本');
    fetch('/m/api/cars', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.error) { $('#car-err').textContent = j.error; return; }
        closeAllSheets(); toast('发车成功，去拼车局看看');
        ensureData().then(renderCars); goTab('carpool');
      })
      .catch(function () { $('#car-err').textContent = '网络开了小差，待会儿再试'; });
  });

  function paintAll() {
    renderHome(); renderScripts(); renderCars(); renderTalks(); renderMe();
  }
  paintAll();
  ensureData().then(paintAll);
  var h = location.hash.replace('#', '');
  if (h && $('#view-' + h)) goTab(h);
  window.addEventListener('hashchange', function () {
    var hh = location.hash.replace('#', '');
    if (hh && $('#view-' + hh) && hh !== curTab) goTab(hh);
  });
})();
