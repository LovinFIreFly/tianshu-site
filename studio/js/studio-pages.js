/* ════════════════════════════════════════════════════════════════
   天枢 · STUDIO 内页引擎 —— 全部数据走 /studio/api/*（天枢共享库 db，与全站同源互通）
   功能：本子库列表 / 详情 / 约场下单 / 拼车大厅 / 上车占座
   ════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var GRADS = [
    ['#e07a5f', '#3d405b'], ['#81b29a', '#f2cc8f'], ['#f2cc8f', '#b56576'],
    ['#6d597a', '#b56576'], ['#468faf', '#2a9d8f'], ['#3d405b', '#81b29a'],
    ['#ff6b35', '#b56576'], ['#2a9d8f', '#e07a5f']
  ];
  function grad(i) { return GRADS[(((i || 0) % GRADS.length) + GRADS.length) % GRADS.length]; }

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
  }
  // 读站点发的 CSRF 令牌（double-submit cookie）：所有 POST 都要带上，否则被 csrf_guard 拦成 403
  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  function postJSON(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF': csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify(payload || {})
    }).then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); });
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function el(html) {
    var d = document.createElement('div');
    d.innerHTML = html.trim();
    return d.firstChild;
  }
  // 鼠标跟随倾斜（与首页 unseen 卡片同款，≤8°）
  function bindTilt(card) {
    if (!window.matchMedia || !matchMedia('(hover: hover)').matches) return;
    var max = parseFloat(card.getAttribute('data-tilt')) || 8;
    card.addEventListener('pointermove', function (e) {
      var r = card.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width - 0.5;
      var py = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = 'perspective(820px) rotateY(' + (px * max) + 'deg) rotateX(' + (-py * max) + 'deg) translateZ(6px)';
    });
    card.addEventListener('pointerleave', function () { card.style.transform = ''; });
  }
  function revealIn(node) {
    if (window.gsap && window.ScrollTrigger) {
      gsap.utils.toArray(node.querySelectorAll('[data-reveal]')).forEach(function (n) {
        gsap.from(n, { opacity: 0, y: 40, duration: 0.8, ease: 'power3.out',
          scrollTrigger: { trigger: n, start: 'top 88%' } });
      });
      ScrollTrigger.refresh();
    }
  }

  /* ════════ 本子库列表 ════════ */
  var grid = document.getElementById('scriptGrid');
  if (grid) {
    var ALL = [];
    var qInput = document.getElementById('q');
    var typeFilter = document.getElementById('typeFilter');
    var diffFilter = document.getElementById('diffFilter');
    var emptyEl = document.getElementById('empty');

    function stars(n) { n = Math.round(n || 0); return n ? '★'.repeat(Math.min(5, n)) : '—'; }

    function cardHTML(s) {
      var g = grad(s.id);
      var tags = (s.tags || []).slice(0, 4).map(function (t) { return '<span>' + esc(t) + '</span>'; }).join('');
      return '' +
        '<a class="card fade-in" href="/studio/script?id=' + encodeURIComponent(s.id) + '" data-tilt="7" data-type="' + esc(s.type) + '">' +
          '<div class="card__media">' +
            '<div class="img" style="background:linear-gradient(135deg,' + g[0] + ',' + g[1] + ')"></div>' +
            (s.rating ? '<span class="card__rating">★ ' + Number(s.rating).toFixed(1) + '</span>' : '') +
            '<span class="tag">' + esc(s.type) + '</span>' +
          '</div>' +
          '<div class="card__body">' +
            '<h3>' + esc(s.title) + '</h3>' +
            '<div class="card__meta">' +
              (s.players ? '<span><b>' + esc(s.players) + '</b> 人</span>' : '') +
              '<span>难度 <b>' + stars(s.diff) + '</b></span>' +
              (s.price ? '<span>¥<b>' + esc(s.price) + '</b>/人</span>' : '') +
            '</div>' +
            (tags ? '<div class="tag-row">' + tags + '</div>' : '') +
          '</div>' +
        '</a>';
    }

    function render() {
      var q = (qInput && qInput.value || '').trim().toLowerCase();
      var tBtn = typeFilter.querySelector('button.is-on');
      var dBtn = diffFilter.querySelector('button.is-on');
      var type = tBtn ? tBtn.getAttribute('data-t') : 'all';
      var diff = dBtn ? dBtn.getAttribute('data-d') : 'all';
      var list = ALL.filter(function (s) {
        if (q && (s.title + ' ' + (s.desc || '')).toLowerCase().indexOf(q) < 0) return false;
        if (type !== 'all' && s.type !== type) return false;
        if (diff !== 'all' && String(s.diff) !== diff) return false;
        return true;
      });
      grid.innerHTML = '';
      list.forEach(function (s) {
        var c = el(cardHTML(s));
        bindTilt(c);
        grid.appendChild(c);
      });
      if (emptyEl) emptyEl.hidden = list.length > 0;
      if (window.ScrollTrigger) ScrollTrigger.refresh();
    }

    getJSON('/studio/api/scripts').then(function (res) {
      ALL = (res && res.scripts) || [];
      // 用真实标签动态补充「类型」筛选按钮（去重、保持顺序）
      var seen = {};
      ALL.forEach(function (s) {
        if (s.type && !seen[s.type]) {
          seen[s.type] = true;
          var b = document.createElement('button');
          b.setAttribute('data-t', s.type);
          b.textContent = s.type;
          typeFilter.appendChild(b);
        }
      });
      render();
    }).catch(function () { if (emptyEl) { emptyEl.hidden = false; emptyEl.textContent = '数据加载失败，请刷新重试。'; } });

    if (qInput) qInput.addEventListener('input', render);
    [typeFilter, diffFilter].forEach(function (f) {
      if (!f) return;
      f.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        f.querySelectorAll('button').forEach(function (x) { x.classList.remove('is-on'); });
        b.classList.add('is-on');
        render();
      });
    });
  }

  /* ════════ 拼车大厅（上车占座）════════ */
  var carList = document.getElementById('carList');
  if (carList) {
    getJSON('/studio/api/cars').then(function (res) {
      var cars = (res && res.cars) || [];
      if (!cars.length) { var e = document.getElementById('empty'); if (e) e.hidden = false; return; }
      cars.forEach(function (c) {
        var row = el('' +
          '<div class="car-row fade-in" data-cid="' + esc(c.id) + '">' +
            '<span class="car-row__t">' + esc(c.title) + '</span>' +
            '<span class="car-row__m">' + esc(c.day) + ' ' + esc(c.time) +
              (c.scriptPlayers ? ' · ' + esc(c.scriptPlayers) + ' 人' : '') +
              (c.scriptDiff ? ' · 难度 ' + '★'.repeat(Math.min(5, c.scriptDiff)) : '') +
              (c.owner ? ' · 车主 ' + esc(c.owner) : '') + '</span>' +
            '<span class="car-row__s ' + (c.full ? 'full' : 'on') + '">' +
              (c.full ? '已满 ' + c.joined + '/' + c.cap : '还差 ' + (c.need || 0) + ' 人') + '</span>' +
            '<button class="car-row__cta' + (c.full ? ' is-off' : '') + '" data-cid="' + esc(c.id) + '"' +
              (c.full ? ' disabled' : '') + '>' + (c.full ? '已满' : '上车 →') + '</button>' +
          '</div>');
        carList.appendChild(row);
      });
      if (window.ScrollTrigger) ScrollTrigger.refresh();

      // 事件委托：点「上车」→ POST /studio/api/car/join
      carList.addEventListener('click', function (e) {
        var btn = e.target.closest('.car-row__cta'); if (!btn || btn.disabled) return;
        var cid = btn.getAttribute('data-cid');
        var row = btn.closest('.car-row');
        btn.disabled = true; btn.textContent = '占座中…';
        postJSON('/studio/api/car/join', { cid: cid }).then(function (r) {
          if (r.status === 200 && r.body.ok) {
            row.querySelector('.car-row__s').className = 'car-row__s ' + (r.body.full ? 'full' : 'on');
            row.querySelector('.car-row__s').textContent = r.body.full
              ? '已满 ' + r.body.joined + '/' + r.body.cap
              : '还差 ' + r.body.need + ' 人';
            btn.textContent = '已上车 ✓'; btn.classList.add('is-done');
          } else {
            btn.disabled = false; btn.textContent = '上车 →';
            var m = (r.body && r.body.msg) || '上车失败，稍后再试';
            var tip = row.querySelector('.car-row__s'); if (tip) tip.textContent = m;
          }
        }).catch(function () {
          btn.disabled = false; btn.textContent = '上车 →';
        });
      });
    }).catch(function () { var e = document.getElementById('empty'); if (e) { e.hidden = false; e.textContent = '数据加载失败，请刷新重试。'; } });
  }

  /* ════════ 本子详情（含约场下单）════════ */
  var detail = document.getElementById('detail');
  if (detail) {
    var id = new URLSearchParams(location.search).get('id') || new URLSearchParams(location.search).get('sid');
    if (!id) { detail.innerHTML = '<p class="empty">缺少本子 id。</p>'; return; }
    getJSON('/studio/api/script?id=' + encodeURIComponent(id)).then(function (res) {
      if (!res || !res.ok || !res.script) {
        detail.innerHTML = '<p class="empty">这个本子不在库里。</p>';
        return;
      }
      var s = res.script;
      var dms = (res.dms || []).map(function (d) {
        return '<span class="dm-chip"><i></i>' + esc(d.name || 'DM') +
          (d.style ? ' · ' + esc(d.style) : '') + '</span>';
      }).join('');
      var tags = (s.tags || []).map(function (t) { return '<span>' + esc(t) + '</span>'; }).join('');
      var next = res.next
        ? '<a href="/studio/script?id=' + encodeURIComponent(res.next.id) + '">下一本 · ' + esc(res.next.title) + ' →</a>'
        : '<span style="color:var(--muted)">已经是最后一卷了</span>';
      detail.innerHTML = '' +
        '<a class="detail__back" href="/studio/scripts">← 返回本子库</a>' +
        '<div class="detail__head"><h1 class="detail__title" data-reveal>' + esc(s.title) + '</h1></div>' +
        '<div class="detail__meta" data-reveal>' +
          '<div><span>类型</span><b>' + esc(s.type) + '</b></div>' +
          (s.players ? '<div><span>人数</span><b>' + esc(s.players) + '</b></div>' : '') +
          '<div><span>难度</span><b>' + '★'.repeat(Math.min(5, s.diff || 0)) + '</b></div>' +
          (s.price ? '<div><span>价格</span><b>¥' + esc(s.price) + '/人</b></div>' : '') +
          (res.rating ? '<div><span>评分</span><b>★ ' + Number(res.rating).toFixed(1) + '</b></div>' : '') +
          '<div><span>评价</span><b>' + (res.reviewCount || 0) + ' 条</b></div>' +
          '<div><span>可约场次</span><b>' + (res.sessionCount || 0) + '</b></div>' +
        '</div>' +
        (s.desc ? '<p class="detail__desc" data-reveal>' + esc(s.desc) + '</p>' : '') +
        (tags ? '<div class="tag-row" data-reveal>' + tags + '</div>' : '') +
        (dms ? '<div class="detail__sec" data-reveal><p class="kick">可选 DM</p><div class="dm-list">' + dms + '</div></div>' : '') +
        '<div class="detail__next" data-reveal><span class="kick" style="margin:0">下一卷</span>' + next + '</div>';

      // 把本子 id 与 DM 列表喂给下方的约场表单
      var form = document.getElementById('bookForm');
      if (form) {
        form.setAttribute('data-sid', s.id);
        var sel = document.getElementById('dmSelect');
        if (sel) {
          sel.innerHTML = '<option value="">不挑，听安排</option>' +
            (res.dms || []).map(function (d) {
              return '<option value="' + esc(d.name || 'DM') + '">' + esc(d.name || 'DM') +
                (d.style ? '（' + esc(d.style) + '）' : '') + '</option>';
            }).join('');
        }
        form.addEventListener('submit', function (e) {
          e.preventDefault();
          var ok = document.getElementById('bookOk');
          var btn = form.querySelector('.book__submit');
          var payload = {
            sid: form.getAttribute('data-sid'),
            name: form.name.value.trim(),
            phone: form.phone.value.trim(),
            day: form.day.value.trim(),
            time: form.time.value.trim(),
            players: form.players.value.trim(),
            dm: form.dm.value,
            note: form.note.value.trim()
          };
          if (!payload.name || !payload.phone) {
            if (ok) { ok.hidden = false; ok.className = 'book__ok is-err'; ok.textContent = '请把称呼和手机号填好。'; }
            return;
          }
          btn.disabled = true; btn.textContent = '提交中…';
          postJSON('/studio/api/book', payload).then(function (r) {
            if (r.status === 200 && r.body.ok) {
              if (ok) { ok.hidden = false; ok.className = 'book__ok is-ok';
                ok.textContent = '约场已收到 ✓ 小客服会尽快用 ' + payload.phone + ' 联系你确认「' + esc(s.title) + '」。'; }
              form.reset();
              if (sel) sel.innerHTML = '<option value="">不挑，听安排</option>' +
                (res.dms || []).map(function (d) {
                  return '<option value="' + esc(d.name || 'DM') + '">' + esc(d.name || 'DM') + '</option>';
                }).join('');
            } else {
              if (ok) { ok.hidden = false; ok.className = 'book__ok is-err';
                ok.textContent = (r.body && r.body.msg) || '提交失败，稍后再试。'; }
            }
            btn.disabled = false; btn.textContent = '提交约场 →';
          }).catch(function () {
            btn.disabled = false; btn.textContent = '提交约场 →';
            if (ok) { ok.hidden = false; ok.className = 'book__ok is-err'; ok.textContent = '网络异常，稍后再试。'; }
          });
        });
      }

      revealIn(detail);
    }).catch(function () { detail.innerHTML = '<p class="empty">加载失败，请刷新重试。</p>'; });
  }
})();
