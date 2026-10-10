/* ============================================================================
   NOVA · 动效与交互层（2026-10 修订版：全纵向 / 全站统一）
   ----------------------------------------------------------------------------
   四条铁律（能不能"不难受"的关键）：
     ① 绝不劫持滚动 —— 不接管滚轮、不接管触摸；原生滚动永远第一优先。
     ② 内容默认可见 —— .rv / .mask-line 只有在 JS 成功启动后才隐藏；
        脚本报错 / 被拦 / prefers-reduced-motion 时，页面**本来就是完整的**。
     ③ 只在"进入视口"时动一次 —— 不来回抖、不无限循环。
     ④ 所有事件用 passive + rAF 节流 —— 只动 transform / opacity，不碰布局属性。

   模块：
     · 顶栏收窄 + 阅读进度条        initTop
     · 入场揭示（错峰）             initReveal      [data-d] 错峰延迟
     · 逐行遮罩揭示                 initMask        .mask > span
     · 数字滚动                     initCount       .count[data-to]
     · 抽屉菜单                     initDrawer
     · 轨道拖拽翻页                 initRail        .rail（需横滑时仍可用，非页面级）
     · 鼠标微视差                   initParallax    .par
     · 巨型字标上浮                 initFootLogo
     · 图片淡入                     initImages
     · 自定义光标（lerp 跟随）      initCursor      [data-cursor] 状态变形
     · 色幕转场                     initCurtain     a[data-curtain]
     · 磁性按钮                     initMagnet      [data-magnet]
     · 加载态 / 表单保护            initBusy        form[data-busy]
   全部包在 try/catch 里，任一步失败都不影响页面可用。
   ============================================================================ */
(function () {
  'use strict';

  var reduce = false, coarse = false, fine = false;
  try {
    reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    coarse = !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
    fine   = !!(window.matchMedia && window.matchMedia('(pointer: fine)').matches);
  } catch (e) { /* 保持默认 false */ }

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function on(el, ev, fn, opt) { try { el.addEventListener(ev, fn, opt || false); } catch (e) {} }

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
    on(window, 'scroll', onScroll, { passive: true });
    on(window, 'resize', onScroll, { passive: true });
    paint();
  }

  /* ---------------- 入场揭示（错峰） ----------------
     .rv 元素在进入视口前保持隐藏，进入后加 .rv-in。
     data-d="120" 可指定错峰延迟（ms）。 */
  function initReveal() {
    var els = $$('.rv');
    if (!els.length) return;
    if (reduce || !('IntersectionObserver' in window)) return;

    els.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.92) return;   // 首屏内不隐藏，避免闪
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

  /* ---------------- 逐行遮罩揭示 ----------------
     结构：<span class="mask"><span>一行字</span></span>
     内层从 translateY(110%) 推到 0，配合 overflow:hidden 形成"揭开"感。
     同一组内自动错峰 70ms。 */
  function initMask() {
    var groups = $$('.mask');
    if (!groups.length) return;
    if (reduce || !('IntersectionObserver' in window)) {
      groups.forEach(function (g) { g.classList.add('mask-on'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var g = en.target;
        var inner = $$('span', g);
        inner.forEach(function (sp, i) {
          window.setTimeout(function () { sp.classList.add('mask-on'); }, i * 70);
        });
        g.classList.add('mask-on');
        io.unobserve(g);
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.12 });
    groups.forEach(function (g) { io.observe(g); });
  }

  /* ---------------- 数字滚动 ---------------- */
  function initCount() {
    var els = $$('.count');
    if (!els.length) return;
    function run(el) {
      var to = parseFloat(el.getAttribute('data-to') || '0') || 0;
      var dec = parseInt(el.getAttribute('data-dec') || '0', 10);
      if (reduce) { el.textContent = to.toFixed(dec); return; }
      var start = performance.now(), dur = 1100;
      function step(t) {
        var k = Math.min(1, (t - start) / dur);
        var e = 1 - Math.pow(1 - k, 3);          // easeOutCubic
        el.textContent = (to * e).toFixed(dec);
        if (k < 1) window.requestAnimationFrame(step);
        else el.textContent = to.toFixed(dec);
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
    on(btn, 'click', function () { set(!drawer.classList.contains('open')); });
    $$('a', drawer).forEach(function (a) { on(a, 'click', function () { set(false); }); });
    on(document, 'keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('open')) set(false);
    });
  }

  /* ---------------- 轨道：拖拽 + 翻页按钮 ----------------
     页面级滚动永远是纵向的；这个只服务于**卡片条内部**的横向浏览（可选）。 */
  function initRail() {
    $$('.rail').forEach(function (rail) {
      var track = $('.rail__track', rail);
      if (!track) return;
      var down = false, sx = 0, sl = 0, moved = 0;
      on(track, 'pointerdown', function (e) {
        if (e.pointerType === 'touch') return;     // 触屏交给原生惯性滚动
        down = true; moved = 0; sx = e.clientX; sl = track.scrollLeft;
        track.classList.add('dragging');
      });
      on(window, 'pointermove', function (e) {
        if (!down) return;
        var dx = e.clientX - sx;
        moved = Math.max(moved, Math.abs(dx));
        track.scrollLeft = sl - dx;
      });
      on(window, 'pointerup', function () {
        if (!down) return;
        down = false; track.classList.remove('dragging');
      });
      on(window, 'pointercancel', function () {
        down = false; track.classList.remove('dragging');
      });
      on(track, 'click', function (e) {
        if (moved > 8) { e.preventDefault(); e.stopPropagation(); }
      }, true);
      $$('[data-rail]', rail).forEach(function (b) {
        on(b, 'click', function () {
          var dir = b.getAttribute('data-rail') === 'next' ? 1 : -1;
          track.scrollBy({ left: dir * Math.max(280, track.clientWidth * 0.8), behavior: reduce ? 'auto' : 'smooth' });
        });
      });
    });
  }

  /* ---------------- 鼠标微视差（仅桌面、极小幅） ---------------- */
  function initParallax() {
    if (reduce || !fine) return;
    var els = $$('.par');
    if (!els.length) return;
    var ticking = false, mx = 0, my = 0;
    on(window, 'mousemove', function (e) {
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
      var k = Math.min(1, Math.max(0, (vh - r.top) / (vh * 0.6)));
      el.style.transform = 'translateY(' + ((1 - k) * 26).toFixed(1) + 'px)';
    }
    on(window, 'scroll', function () {
      if (ticking) return; ticking = true; window.requestAnimationFrame(paint);
    }, { passive: true });
    paint();
  }

  /* ---------------- 图片解码后淡入 ---------------- */
  function initImages() {
    $$('img[loading="lazy"]').forEach(function (img) {
      if (img.complete && img.naturalWidth) return;
      img.style.opacity = '0';
      img.style.transition = 'opacity .6s ease';
      function show() { img.style.opacity = '1'; }
      on(img, 'load', show, { once: true });
      on(img, 'error', show, { once: true });
    });
  }

  /* ---------------- 自定义光标（lerp 跟随 + data-cursor 状态） ----------------
     仅"细指针 + 允许动效"的桌面环境启用；触屏/降级环境完全不生成 DOM。
     圆点瞬时跟随、外环 lerp 追赶，形成"被牵引"的手感。
     [data-cursor="view|open|drag|hide"] 让环变形；hover 可交互元素自动放大。 */
  function initCursor() {
    if (reduce || coarse || !fine) return;
    var dot = document.createElement('div');
    var ring = document.createElement('div');
    dot.className = 'nv-cursor-dot';
    ring.className = 'nv-cursor-ring';
    dot.setAttribute('aria-hidden', 'true');
    ring.setAttribute('aria-hidden', 'true');
    document.body.appendChild(dot);
    document.body.appendChild(ring);
    document.documentElement.classList.add('nv-has-cursor');

    var mx = window.innerWidth / 2, my = window.innerHeight / 2;
    var rx = mx, ry = my, seen = false;

    on(window, 'mousemove', function (e) {
      mx = e.clientX; my = e.clientY;
      if (!seen) { seen = true; rx = mx; ry = my; document.body.classList.add('nv-cursor-on'); }
      dot.style.transform = 'translate3d(' + mx + 'px,' + my + 'px,0)';
    }, { passive: true });

    on(document, 'mouseleave', function () { document.body.classList.remove('nv-cursor-on'); });
    on(document, 'mouseenter', function () { if (seen) document.body.classList.add('nv-cursor-on'); });

    // 可交互元素上自动放大
    on(document, 'mouseover', function (e) {
      var t = e.target && e.target.closest ? e.target.closest('a,button,input,select,textarea,label,[data-cursor]') : null;
      if (t) {
        ring.classList.add('is-hot');
        var c = t.getAttribute('data-cursor');
        if (c) ring.setAttribute('data-c', c);
        var lab = t.getAttribute('data-cursor-label');
        if (lab) ring.setAttribute('data-label', lab);
      }
    });
    on(document, 'mouseout', function (e) {
      var t = e.target && e.target.closest ? e.target.closest('a,button,input,select,textarea,label,[data-cursor]') : null;
      if (t) {
        ring.classList.remove('is-hot');
        ring.removeAttribute('data-c');
        ring.removeAttribute('data-label');
      }
    });

    // 按下：环收缩（点击反馈）
    on(document, 'mousedown', function () { document.body.classList.add('nv-cursor-down'); });
    on(document, 'mouseup', function () { document.body.classList.remove('nv-cursor-down'); });

    function loop() {
      rx += (mx - rx) * 0.16;
      ry += (my - ry) * 0.16;
      ring.style.transform = 'translate3d(' + rx.toFixed(2) + 'px,' + ry.toFixed(2) + 'px,0)';
      window.requestAnimationFrame(loop);
    }
    window.requestAnimationFrame(loop);
  }

  /* ---------------- 色幕转场 ----------------
     <a data-curtain href="..."> 点击后从点击点炸开一枚圆形色幕，再跳转。
     相同源 / 新窗口 / 修饰键 / 站外锚点：一律放行原生行为。 */
  function initCurtain() {
    var links = $$('a[data-curtain]');
    if (!links.length || reduce) return;

    var veil = document.createElement('div');
    veil.className = 'nv-curtain';
    veil.setAttribute('aria-hidden', 'true');
    document.body.appendChild(veil);

    // 入场：从页面中央淡入（首屏仪式感）
    try {
      veil.classList.add('nv-curtain--in');
      window.setTimeout(function () { veil.classList.remove('nv-curtain--in'); }, 60);
    } catch (e) {}

    var busy = false;
    links.forEach(function (a) {
      on(a, 'click', function (e) {
        if (busy) { e.preventDefault(); return; }
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        var href = a.getAttribute('href') || '';
        if (!href || href.charAt(0) === '#' || a.target === '_blank') return;
        try {
          if (new URL(a.href, location.href).origin !== location.origin) return;
        } catch (err) { return; }

        e.preventDefault();
        busy = true;
        var r = a.getBoundingClientRect();
        var x = (r.left + r.width / 2), y = (r.top + r.height / 2);
        veil.style.setProperty('--cx', x + 'px');
        veil.style.setProperty('--cy', y + 'px');
        veil.classList.add('nv-curtain--open');
        document.documentElement.classList.add('nv-leaving');
        window.setTimeout(function () { location.href = a.href; }, 620);
      });
    });

    // 从 bfcache 返回时清掉遮罩
    on(window, 'pageshow', function () {
      busy = false;
      veil.classList.remove('nv-curtain--open');
      document.documentElement.classList.remove('nv-leaving');
    });
  }

  /* ---------------- 磁性按钮 ----------------
     [data-magnet] 元素在指针靠近时轻微偏移，离开回弹。幅度 6px 以内。 */
  function initMagnet() {
    if (reduce || !fine) return;
    var els = $$('[data-magnet]');
    if (!els.length) return;
    els.forEach(function (el) {
      var ticking = false, tx = 0, ty = 0;
      on(el, 'mousemove', function (e) {
        var r = el.getBoundingClientRect();
        var k = parseFloat(el.getAttribute('data-magnet') || '6');
        tx = ((e.clientX - (r.left + r.width / 2)) / (r.width / 2)) * k;
        ty = ((e.clientY - (r.top + r.height / 2)) / (r.height / 2)) * k;
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(function () {
          ticking = false;
          el.style.transform = 'translate3d(' + tx.toFixed(2) + 'px,' + ty.toFixed(2) + 'px,0)';
        });
      }, { passive: true });
      on(el, 'mouseleave', function () { el.style.transform = ''; });
    });
  }

  /* ---------------- 加载态 / 重复提交保护 ----------------
     form[data-busy] 提交后按钮进入 loading，并禁用，避免重复下单/重复登录。 */
  function initBusy() {
    $$('form[data-busy]').forEach(function (form) {
      on(form, 'submit', function () {
        if (form.getAttribute('data-sent') === '1') return;
        form.setAttribute('data-sent', '1');
        $$('button[type="submit"], button:not([type])', form).forEach(function (b) {
          b.classList.add('is-loading');
          b.setAttribute('aria-busy', 'true');
          window.setTimeout(function () { b.disabled = true; }, 0);
        });
        // 提交失败会整页刷新回来，所以不需要手动复位
      });
    });
  }

  function boot() {
    var steps = [
      initTop, initReveal, initMask, initCount, initDrawer, initRail,
      initParallax, initFootLogo, initImages, initCursor, initCurtain,
      initMagnet, initBusy
    ];
    for (var i = 0; i < steps.length; i++) {
      try { steps[i](); } catch (e) { /* 单步失败不拖累其他 */ }
    }
  }

  if (document.readyState === 'loading') on(document, 'DOMContentLoaded', boot);
  else boot();
})();
