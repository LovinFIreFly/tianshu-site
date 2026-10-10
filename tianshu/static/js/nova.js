/* ============================================================================
   NOVA · 动效与交互层（2026-10）
   ----------------------------------------------------------------------------
   三条铁律（我给自己定的，也是这套能不能"不难受"的关键）：
     ① 绝不劫持滚动 —— 不引 Lenis 之类接管滚轮的库，原生滚动永远第一优先。
     ② 内容默认可见 —— .rv 元素只有在 JS 成功启动后才加 .rv-init 隐藏；
        脚本一旦报错 / 被拦 / prefers-reduced-motion，页面**本来就是完整的**。
     ③ 只在"进入视口"时动一次 —— 不来回抖、不无限循环、不劫持 hover 语义。

   干什么：
     · 顶部导航滚过一屏后收窄 + 加线（.is-stuck）
     · 阅读进度条（读 scrollY，不改 scrollY）
     · IntersectionObserver 驱动的 .rv 入场
     · 数字滚动（.count）
     · 全屏抽屉菜单开关
     · 横向拖拽轨道（.rail，拖 + 按钮翻页）
     · 鼠标微视差（.par，仅桌面指针，幅度极小）
     · 巨型字标随滚动轻微上浮（.footlogo）
   全部包在 try/catch 里，任一步失败都不影响页面可用。
   ============================================================================ */
(function () {
  'use strict';

  var reduce = false;
  try {
    reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) { reduce = false; }

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

  /* ---------------- 顶栏 / 进度条 ---------------- */
  function initTop() {
    var top = $('#nvTop');
    var bar = $('#nvProgress') && $('#nvProgress').firstElementChild;
    var ticking = false;
    function paint() {
      ticking = false;
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      if (top) { if (y > 40) top.classList.add('is-stuck'); else top.classList.remove('is-stuck'); }
      if (bar) {
        var h = document.documentElement.scrollHeight - window.innerHeight;
        var p = h > 0 ? Math.min(1, Math.max(0, y / h)) : 0;
        bar.style.width = (p * 100).toFixed(2) + '%';
      }
    }
    function onScroll() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(paint);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    paint();
  }

  /* ---------------- 入场动效 ---------------- */
  function initReveal() {
    var els = $$('.rv');
    if (!els.length) return;

    // 没有 IO 或用户要减少动效：什么都不做 —— 内容本来就是可见的
    if (reduce || !('IntersectionObserver' in window)) return;

    // 先隐藏（加 .rv-init），再交给 IO 显示。只有走到这里才会隐藏，
    // 所以前面任何一步 return 掉，页面都是完整的。
    els.forEach(function (el) {
      var r = el.getBoundingClientRect();
      // 首屏内（已经在视口里的）不隐藏，避免"一进来就闪一下"
      if (r.top < window.innerHeight * 0.92) return;
      el.classList.add('rv-init');
    });

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target;
        var d = parseInt(el.getAttribute('data-d') || '0', 10);
        window.setTimeout(function () { el.classList.add('rv-in'); }, d);
        io.unobserve(el);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });

    $$('.rv-init').forEach(function (el) { io.observe(el); });
  }

  /* ---------------- 数字滚动 ---------------- */
  function initCount() {
    var els = $$('.count');
    if (!els.length) return;
    function run(el) {
      var to = parseFloat(el.getAttribute('data-to') || '0') || 0;
      if (reduce) { el.textContent = String(to); return; }
      var start = performance.now(), dur = 1100;
      function step(t) {
        var k = Math.min(1, (t - start) / dur);
        var e = 1 - Math.pow(1 - k, 3);          // easeOutCubic
        el.textContent = String(Math.round(to * e));
        if (k < 1) window.requestAnimationFrame(step);
        else el.textContent = String(to);
      }
      window.requestAnimationFrame(step);
    }
    if (!('IntersectionObserver' in window)) { els.forEach(run); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        run(en.target); io.unobserve(en.target);
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------------- 抽屉菜单 ---------------- */
  function initDrawer() {
    var btn = $('#nvBurger'), drawer = $('#nvDrawer');
    if (!btn || !drawer) return;
    function set(open) {
      drawer.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
      document.documentElement.style.overflow = open ? 'hidden' : '';
    }
    btn.addEventListener('click', function () { set(!drawer.classList.contains('open')); });
    $$('a', drawer).forEach(function (a) { a.addEventListener('click', function () { set(false); }); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('open')) set(false);
    });
  }

  /* ---------------- 横向轨道：拖拽 + 翻页按钮 ---------------- */
  function initRail() {
    $$('.rail').forEach(function (rail) {
      var track = $('.rail__track', rail);
      if (!track) return;
      rail.style.touchAction = '';                 // 保留原生纵向滚动
      var down = false, sx = 0, sl = 0, moved = 0;
      track.addEventListener('pointerdown', function (e) {
        if (e.pointerType === 'touch') return;     // 触屏交给原生惯性滚动
        down = true; moved = 0; sx = e.clientX; sl = track.scrollLeft;
        track.classList.add('dragging');
      });
      window.addEventListener('pointermove', function (e) {
        if (!down) return;
        var dx = e.clientX - sx;
        moved = Math.max(moved, Math.abs(dx));
        track.scrollLeft = sl - dx;
      });
      window.addEventListener('pointerup', function () {
        if (!down) return;
        down = false; track.classList.remove('dragging');
      });
      // 拖动后抑制误触链接
      track.addEventListener('click', function (e) {
        if (moved > 8) { e.preventDefault(); e.stopPropagation(); }
      }, true);
      $$('[data-rail]', rail).forEach(function (b) {
        b.addEventListener('click', function () {
          var dir = b.getAttribute('data-rail') === 'next' ? 1 : -1;
          track.scrollBy({ left: dir * Math.max(280, track.clientWidth * 0.8), behavior: reduce ? 'auto' : 'smooth' });
        });
      });
    });
  }

  /* ---------------- 鼠标微视差（仅桌面、极小幅） ---------------- */
  function initParallax() {
    if (reduce) return;
    if (!window.matchMedia || !window.matchMedia('(pointer: fine)').matches) return;
    var els = $$('.par');
    if (!els.length) return;
    var ticking = false, mx = 0, my = 0;
    window.addEventListener('mousemove', function (e) {
      mx = (e.clientX / window.innerWidth - 0.5);
      my = (e.clientY / window.innerHeight - 0.5);
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () {
        ticking = false;
        els.forEach(function (el) {
          var k = parseFloat(el.getAttribute('data-par') || '8');
          el.style.transform = 'translate3d(' + (-mx * k).toFixed(2) + 'px,' + (-my * k).toFixed(2) + 'px,0)';
        });
      });
    }, { passive: true });
  }

  /* ---------------- 巨型字标随滚动上浮 ---------------- */
  function initFootLogo() {
    if (reduce) return;
    var el = $('.nv-foot__logo');
    if (!el) return;
    var ticking = false;
    function paint() {
      ticking = false;
      var r = el.getBoundingClientRect();
      var vh = window.innerHeight || 1;
      // 进入视口后从 +26px 收到 0
      var k = Math.min(1, Math.max(0, (vh - r.top) / (vh * 0.6)));
      el.style.transform = 'translateY(' + ((1 - k) * 26).toFixed(1) + 'px)';
    }
    window.addEventListener('scroll', function () {
      if (ticking) return; ticking = true; window.requestAnimationFrame(paint);
    }, { passive: true });
    paint();
  }

  /* ---------------- 图片解码后淡入（避免灰块） ---------------- */
  function initImages() {
    $$('img[loading="lazy"]').forEach(function (img) {
      if (img.complete && img.naturalWidth) return;
      img.style.opacity = '0';
      img.style.transition = 'opacity .6s ease';
      function show() { img.style.opacity = '1'; }
      img.addEventListener('load', show, { once: true });
      img.addEventListener('error', show, { once: true });
    });
  }

  function boot() {
    var steps = [initTop, initReveal, initCount, initDrawer, initRail, initParallax, initFootLogo, initImages];
    for (var i = 0; i < steps.length; i++) {
      try { steps[i](); } catch (e) { /* 单步失败不拖累其他 */ }
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
