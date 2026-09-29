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
  var hero = $('.dhero');
  if (hero && !reduce) {
    var glow = $('.dhero__glow', hero);
    if (glow) {
      hero.addEventListener('pointermove', function (e) {
        var r = hero.getBoundingClientRect();
        hero.style.setProperty('--mx', (e.clientX - r.left) + 'px');
        hero.style.setProperty('--my', (e.clientY - r.top) + 'px');
      });
    }
  }
})();
