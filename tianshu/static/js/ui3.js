/* ============================================================================
   甜薯剧场 3.0 —— 交互层（design3 的配套脚本）
   ----------------------------------------------------------------------------
   只管"手感"，不碰业务：任何一步失败都不影响页面功能。
     ① 顶栏：滚动加 .scrolled（第二行栏目条折叠）+ 顶部阅读进度条
     ② 入场：.rv / .rv-x 进视口才升起（子项 --i 错位）
     ③ 轨道：.rail3 可拖动 / 滚轮横滑 / 左右箭头 / 底部进度条
     ④ 数字：.count3 从 0 滚到目标值
     ⑤ 提示条：自动淡出（不挡内容，也不用来手动关）
     ⑥ 首屏：光标跟随光斑（--mx / --my）
   约束：不改 data-tab / mobtab / 表单，纯增强。
   ========================================================================== */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* 桌面鼠标（有精确指针）才做吸附和磁吸：触屏上这两样只会帮倒忙 */
  var finePtr = !!(window.matchMedia && window.matchMedia('(pointer:fine)').matches);
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

  /* ---------------------------------------------------------------- ① 顶栏 */
  var nav = document.getElementById('siteNav');
  if (nav) {
    var bar = document.createElement('div');
    bar.className = 'scrollbar3';
    document.body.appendChild(bar);
    var ticking = false;
    function onScroll() {
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      nav.classList.toggle('scrolled', y > 10);
      var h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (h > 0 ? Math.min(100, (y / h) * 100) : 0) + '%';
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
    }, { passive: true });
    onScroll();

    /* 鼠标移到屏幕上方 → 栏目条自动浮现（不用往上滚回去） */
    var navHold = null;
    window.addEventListener('pointermove', function (e) {
      if (e.clientY < 58) {
        if (navHold) { clearTimeout(navHold); navHold = null; }
        nav.classList.add('nav-open');
      } else if (e.clientY > 132 && nav.classList.contains('nav-open') && !navHold) {
        navHold = setTimeout(function () {
          nav.classList.remove('nav-open');
          navHold = null;
        }, 260);
      }
    }, { passive: true });
    nav.addEventListener('pointerleave', function () {
      if (navHold) { clearTimeout(navHold); navHold = null; }
      nav.classList.remove('nav-open');
    });
  }

  /* ---------------------------------------------------------------- ② 入场 */
  var rv = $$('.rv, .rv-x');
  if (!rv.length) { /* 没有就不建观察器 */ }
  else if (reduce || !window.IntersectionObserver) {
    rv.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -8% 0px' });
    rv.forEach(function (el) { io.observe(el); });
  }

  /* ---------------------------------------------------------------- ③ 轨道 */
  $$('.rail3').forEach(function (rail) {
    var track = $('.rail3__track', rail);
    if (!track) return;
    var fill = $('.rail3__bar i', rail);
    var prev = $('[data-rail="prev"]', rail);
    var next = $('[data-rail="next"]', rail);

    function paint() {
      if (!fill) return;
      var max = track.scrollWidth - track.clientWidth;
      var r = max > 0 ? track.scrollLeft / max : 0;
      var w = max > 0 ? Math.max(0.08, track.clientWidth / track.scrollWidth) : 1;
      fill.style.width = (w * 100) + '%';
      fill.style.transform = 'translateX(' + (max > 0 ? (r * (1 - w) / w) * 100 : 0) + '%)';
    }
    track.addEventListener('scroll', paint, { passive: true });
    window.addEventListener('resize', paint);
    paint();

    function step(dir) {
      var card = track.firstElementChild;
      var dx = card ? card.getBoundingClientRect().width + 18 : 240;
      track.scrollBy({ left: dir * dx * 1.6, behavior: reduce ? 'auto' : 'smooth' });
    }
    if (prev) prev.addEventListener('click', function () { step(-1); });
    if (next) next.addEventListener('click', function () { step(1); });

    /* 拖动（鼠标；触屏交给原生滚动） */
    var down = false, sx = 0, sl = 0, moved = false;
    track.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'touch') return;
      down = true; moved = false; sx = e.clientX; sl = track.scrollLeft;
      track.classList.add('dragging');
    });
    window.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - sx;
      if (Math.abs(dx) > 4) moved = true;
      track.scrollLeft = sl - dx;
    });
    window.addEventListener('pointerup', function () {
      if (!down) return;
      down = false; track.classList.remove('dragging');
    });
    /* 拖动后别触发卡片的点击 */
    track.addEventListener('click', function (e) {
      if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; }
    }, true);
  });

  /* ---------------------------------------------------------------- ④ 数字 */
  var nums = $$('.count3');
  function run(el) {
    var raw = String(el.getAttribute('data-to') != null ? el.getAttribute('data-to') : el.textContent).trim();
    var to = parseFloat(raw.replace(/,/g, ''));
    /* 不是纯数字（带 %、带文字、带千分位以外的杂字）就原样显示，别硬算成 0 */
    if (isNaN(to)) { return; }
    var dec = (raw.split('.')[1] || '').replace(/[^0-9]/g, '').length;
    if (reduce) { el.textContent = to.toFixed(dec); return; }
    var t0 = null, dur = 900;
    function tick(ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var v = to * (1 - Math.pow(1 - p, 3));
      el.textContent = v.toFixed(dec);
      if (p < 1) window.requestAnimationFrame(tick);
    }
    window.requestAnimationFrame(tick);
  }
  if (nums.length && window.IntersectionObserver && !reduce) {
    var nio = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { run(e.target); nio.unobserve(e.target); } });
    }, { threshold: 0.4 });
    nums.forEach(function (el) { nio.observe(el); });
  } else {
    nums.forEach(function (el) { run(el); });
  }

  /* ---------------------------------------------------------------- ⑤ 提示条 */
  $$('.flash').forEach(function (f, i) {
    setTimeout(function () {
      f.classList.add('is-out');
      setTimeout(function () {
        var w = f.parentElement;
        f.remove();
        if (w && !w.children.length) w.remove();
      }, 340);
    }, 4200 + i * 400);
    f.addEventListener('click', function () {
      f.classList.add('is-out');
      setTimeout(function () {
        var w = f.parentElement;
        f.remove();
        if (w && !w.children.length) w.remove();
      }, 340);
    });
    f.style.cursor = 'pointer';
  });

  /* ---------------------------------------------------------------- ⑥ 光斑 */
  /* 首屏和"怎么玩"共用：光标在暗场里带一团印色光（--mx/--my 喂给 .glow3） */
  if (!reduce) {
    $$('.dhero, .how3').forEach(function (sec) {
      var box = sec.classList.contains('how3') ? ($('.how3__pin', sec) || sec) : sec;
      sec.addEventListener('pointermove', function (e) {
        var r = box.getBoundingClientRect();
        sec.style.setProperty('--mx', (e.clientX - r.left) + 'px');
        sec.style.setProperty('--my', (e.clientY - r.top) + 'px');
      }, { passive: true });
    });
  }

  /* ------------------------------------------------- ⑦ 首页"怎么玩"：自动播放
     3 秒走一步（底部那条 3 秒走满就翻），点下面的条可以直接切、切完重新计时。
     滚轮不参与 1/2/3 的切换 —— 这一屏就是一屏，往下划直接进下一块。 */
  var how = $('.how3');
  if (how) {
    var hsteps = $$('.how3__step', how);
    var hbtns = $$('.how3__bar button', how);
    var hidx = 0, htimer = null;
    var hCanAuto = !reduce && window.matchMedia && window.matchMedia('(min-width:834px)').matches;

    function showStep(i) {
      if (!hsteps.length) return;
      hidx = ((i % hsteps.length) + hsteps.length) % hsteps.length;
      hsteps.forEach(function (el, k) { el.classList.toggle('is-on', k === hidx); });
      hbtns.forEach(function (b, k) { b.classList.toggle('on', k === hidx); });
      var cur = hbtns[hidx];
      if (cur) {                    /* 去掉再加回，强制让进度条从 0 重新走一遍 */
        cur.classList.remove('on');
        void cur.offsetWidth;
        cur.classList.add('on');
      }
    }
    function startAuto() {
      if (!hCanAuto) return;
      if (htimer) clearInterval(htimer);
      htimer = setInterval(function () { showStep(hidx + 1); }, 3000);
    }
    hbtns.forEach(function (b, k) {
      b.addEventListener('click', function () { showStep(k); startAuto(); });
    });
    showStep(0);
    startAuto();
  }

  /* ------------------------------------------------- ⑧ 一划一屏：首屏 → 怎么玩
     两块都是满屏，所以往下划一点点就把你稳稳送到下一屏（阈值小 = 划一下就到）。
     只在下滑时对齐、只对齐这一个缝；进了「怎么玩」之后不再碰滚轮。 */
  if (how && !reduce && finePtr) {
    var howTop = 0, howGuard = 0, howTmr = null, hLastY = window.pageYOffset || 0, hDir = 0;
    function measureHow() { howTop = how.getBoundingClientRect().top + (window.pageYOffset || 0); }
    function onHowScroll() {
      var y = window.pageYOffset || 0;
      if (y > hLastY) hDir = 1; else if (y < hLastY) hDir = -1;
      hLastY = y;
      if (howTmr) clearTimeout(howTmr);
      howTmr = setTimeout(function () {
        var now = Date.now();
        if (now < howGuard) return;
        if (y >= howTop - 4) return;                       /* 已经在「怎么玩」里：不劫持 */
        if (hDir !== 1) return;                            /* 只在下滑时对齐 */
        if (y < window.innerHeight * 0.12) return;         /* 几乎没动：不打扰 */
        howGuard = now + 900;
        window.scrollTo({ top: howTop, behavior: 'smooth' });
      }, 140);
    }
    measureHow();
    window.addEventListener('resize', measureHow);
    window.addEventListener('scroll', onHowScroll, { passive: true });
  }

  /* ---------------------------------------------------------------- ⑨ 磁吸 */
  /* 桌面鼠标才做：按钮朝光标方向偏 3~4px，松开回位（Duolingo 式微交互） */
  if (!reduce && finePtr) {
    $$('.b3, .btn').forEach(function (btn) {
      btn.addEventListener('pointermove', function (e) {
        var r = btn.getBoundingClientRect();
        if (!r.width || !r.height) return;
        var dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
        var dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
        btn.style.transform = 'translate(' + (dx * 4).toFixed(2) + 'px,' + (dy * 3).toFixed(2) + 'px)';
      });
      btn.addEventListener('pointerleave', function () { btn.style.transform = ''; });
    });
  }

  /* ------------------------------------------------- ⑩ 卡片微倾（桌面）
     光标在卡片上移动时，卡片最多朝光标方向倾 3~4 度（像伸手翻一张牌）。
     拖动轨道时不倾，免得跟拖拽打架。 */
  if (!reduce && finePtr) {
    $$('.pcard3').forEach(function (card) {
      card.addEventListener('pointermove', function (e) {
        var tr = card.closest ? card.closest('.rail3__track') : null;
        if (tr && tr.classList.contains('dragging')) return;
        var r = card.getBoundingClientRect();
        if (!r.width || !r.height) return;
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        card.style.setProperty('--ry', (px * 7).toFixed(2) + 'deg');
        card.style.setProperty('--rx', (-py * 6).toFixed(2) + 'deg');
      });
      card.addEventListener('pointerleave', function () {
        card.style.setProperty('--ry', '0deg');
        card.style.setProperty('--rx', '0deg');
      });
    });
  }
})();
