/* ============================================================================
   Unseen 风格 · 暗场运动引擎（v2 · 零依赖）
   Smooth 惯量滚动 / Split 逐字揭示 / Spotlight 追光照亮 / Gallery 钉住横滚
   Night 时间轴 / Float 视差 / Magnetic 磁吸 / Cursor 情境光标 / Transit 换页
   参考 nova 的运动语法，全部带降级保护（触摸 / 减弱动效 / 无 IO 时不动）。
   ========================================================================== */
(function () {
  'use strict';
  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var COARSE = window.matchMedia && window.matchMedia('(hover: none), (pointer: coarse)').matches;
  /* GSAP 3.13（本地 vendor）可用时，用它的编排替代手写揭示（更"被安排过"） */
  var HAS_GSAP = !!(window.gsap && window.ScrollTrigger);
  if (HAS_GSAP) {
    try {
      gsap.registerPlugin(ScrollTrigger);
      if (window.SplitText) gsap.registerPlugin(SplitText);
      document.documentElement.classList.add('gsap-on');
    } catch (e) { HAS_GSAP = false; }
  }
  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }

  /* ---------------- 可重入的常驻 rAF ----------------
     场景流动式转场会把"页面级"模块整体重跑一遍（换页后新 DOM 要重新接上动效）。
     凡是自己开 rAF 常驻循环的模块（光标跟随、追光），重跑时必须先把上一轮的循环掐掉，
     否则每换一页就多挂一个永远在跑的循环 —— 换五六页之后帧率就崩了。
     统一走 loop(name, fn)：同名再次注册 = 自动替换。 */
  var LOOPS = {};
  function stopLoop(name) {
    if (LOOPS[name]) { cancelAnimationFrame(LOOPS[name]); LOOPS[name] = 0; }
  }
  function loop(name, fn) {
    stopLoop(name);
    LOOPS[name] = requestAnimationFrame(function step() { fn(); LOOPS[name] = requestAnimationFrame(step); });
  }

  /* ---------------- 页面级监听登记处 ----------------
     页面级模块常往 window 上挂 scroll / resize（追光的 relayout、海报廊的 render…）。
     元素本身可以随 DOM 回收，但挂在 window 上的监听不会 —— 换页重跑几次之后就变成
     "滚一格触发五次回调"，越点越卡。所以页面级一律走 pOn 登记，换页前 pOff 统一摘。 */
  var P_BOUND = [];
  function pOn(t, ev, fn, opt) {
    try { t.addEventListener(ev, fn, opt || false); P_BOUND.push([t, ev, fn, opt || false]); } catch (e) {}
  }
  function pOff() {
    for (var i = 0; i < P_BOUND.length; i++) {
      var b = P_BOUND[i];
      try { b[0].removeEventListener(b[1], b[2], b[3]); } catch (e) {}
    }
    P_BOUND.length = 0;
  }
  /* 引言轮播是页面级的 setInterval，也要能停 —— 否则换页后两个轮播同时在跑 */
  var VOICE_TIMER = null;

  /* ---------------- 情境软光标 ---------------- */
  function initCursor() {
    if (COARSE || REDUCE) return;
    var dot = $('.cursor'), ring = $('.cursor-ring');
    if (!dot || !ring) return;
    var lb = $('.lb', ring);
    document.body.classList.add('has-cursor');
    var mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
    addEventListener('mousemove', function (e) { mx = e.clientX; my = e.clientY; }, { passive: true });
    loop('cursor', function () {
      rx = lerp(rx, mx, 0.18); ry = lerp(ry, my, 0.18);
      dot.style.transform = 'translate(' + mx + 'px,' + my + 'px) translate(-50%,-50%)';
      ring.style.transform = 'translate(' + rx + 'px,' + ry + 'px) translate(-50%,-50%)';
    });
    function over(e) {
      var t = e.target.closest('a,button,[data-cursor],input,textarea,select,label');
      if (!t) return;
      ring.classList.add('big');
      var label = t.getAttribute && t.getAttribute('data-cursor');
      if (lb) lb.textContent = label || '';
      if (label) ring.classList.add('tagged'); else ring.classList.remove('tagged');
    }
    function out(e) {
      var t = e.target.closest('a,button,[data-cursor],input,textarea,select,label');
      if (t) { ring.classList.remove('big'); ring.classList.remove('tagged'); if (lb) lb.textContent = ''; }
    }
    document.addEventListener('mouseover', over);
    document.addEventListener('mouseout', out);
    document.addEventListener('mousedown', function (e) {
      dot.style.opacity = '.4';
      rippleAt(e.clientX, e.clientY);      // 学 nova：点下去必须有落点反馈
    });
    document.addEventListener('mouseup', function () { dot.style.opacity = ''; });
  }

  /* 点击落点涟漪：纯 DOM 一个 span，不碰 WebGL 场 —— 一个元素的成本，反馈很实在。
     0.7s 后自己摘掉，不留垃圾节点。触摸设备走 initCursor 的提前 return，不接这个。 */
  function rippleAt(x, y) {
    if (REDUCE) return;
    var r = document.createElement('span');
    r.className = 'ripple';
    r.style.left = x + 'px';
    r.style.top = y + 'px';
    document.body.appendChild(r);
    setTimeout(function () { if (r.parentNode) r.parentNode.removeChild(r); }, 720);
  }

  /* ---------------- Smooth 惯量滚动 ----------------
     首选 Lenis（vendor 本地 1.1.20）。关键前提：Lenis 驱动的是**原生 scrollTo**
     （`options.wrapper.scrollTo({behavior:'instant'})`，不是 transform 包裹内容）——
     所以 window.scrollY / scroll 事件 / ScrollTrigger / sticky / 锚点全部照常工作，
     这正是能安全替换旧手写实现的原因（学 unseen.co 用 ASScroll 的同一套思路：
     滚动只由一个引擎驱动，其余模块都读它的结果，绝不各写一套）。
     与 ScrollTrigger 走官方同步：lenis.on('scroll', ScrollTrigger.update) +
     gsap.ticker.add(t => lenis.raf(t*1000))。缺 Lenis 时退回下面手写版，行为不变。 */
  var LENIS = null;
  /* 统一程序化滚动入口：有 Lenis 就走 Lenis（否则直接 window.scrollTo 会和它的
     缓动打架——Lenis 每帧回写位置，外部直接改会被它"拉回去"）。 */
  function scrollToY(y, immediate) {
    if (LENIS) { try { LENIS.scrollTo(y, { immediate: !!immediate }); return; } catch (e) {} }
    if (immediate) window.scrollTo(0, y); else window.scrollTo({ top: y, behavior: 'smooth' });
  }
  function initSmooth() {
    if (REDUCE || COARSE) return;
    var doc = document.documentElement;
    doc.classList.add('smooth');
    if (window.Lenis) {
      try {
        LENIS = new Lenis({ lerp: 0.14, smoothWheel: true, smoothTouch: false, wheelMultiplier: 1 });
        if (HAS_GSAP && window.ScrollTrigger) {
          LENIS.on('scroll', ScrollTrigger.update);
          gsap.ticker.add(function (time) { LENIS.raf(time * 1000); });
          gsap.ticker.lagSmoothing(0);
        } else {
          (function pump(t) { LENIS.raf(t); requestAnimationFrame(pump); })(performance.now());
        }
        return;
      } catch (e) { LENIS = null; }        // 构造失败就当没有，落到手写兜底
    }
    /* ---- 手写兜底（Lenis 没加载成功时）---- */
    function maxY() { return Math.max(0, doc.scrollHeight - innerHeight); }
    var target = window.scrollY, current = target, running = false;
    doc.classList.add('smooth');
    function raf() {
      current = lerp(current, target, 0.14);
      if (Math.abs(target - current) < 0.5) { current = target; running = false; window.scrollTo(0, current); return; }
      window.scrollTo(0, current);
      requestAnimationFrame(raf);
    }
    addEventListener('wheel', function (e) {
      if (e.ctrlKey) return;                                   // 保留浏览器缩放
      if (e.target.closest && e.target.closest('textarea,select,[data-nosmooth]')) return;
      if (Math.abs(e.deltaY) < 0.5 && !e.deltaX) return;
      e.preventDefault();
      target = clamp(target + e.deltaY, 0, maxY());
      if (!running) { running = true; requestAnimationFrame(raf); }
    }, { passive: false });
    addEventListener('scroll', function () {                   // 键盘/拖滚动条/锚点：交给原生，随后同步
      if (!running) { target = current = window.scrollY; }
    }, { passive: true });
    addEventListener('resize', function () { if (!running) target = current = window.scrollY; }, { passive: true });
  }

  /* ---------------- 揭示（淡入上浮）---------------- */
  function initReveal() {
    var els = $$('[data-reveal]');
    if (!els.length) return;
    if (HAS_GSAP && !REDUCE) {
      var run = function () { els.forEach(function (el) {
        var d = parseFloat(el.getAttribute('data-d') || '0') || 0;
        // 标题（.h2）用 SplitText 逐行遮罩揭示；其余淡入上浮
        if (el.classList.contains('h2') && window.SplitText) {
          var st = null;
          try { st = new SplitText(el, { type: 'lines', mask: 'lines' }); } catch (e) { st = null; }
          if (st && st.lines && st.lines.length) {
            gsap.from(st.lines, {
              yPercent: 115, duration: 1.0, ease: 'power4.out', stagger: 0.07, delay: d * 0.07,
              scrollTrigger: { trigger: el, start: 'top 88%', once: true }
            });
            return;
          }
        }
        gsap.from(el, {
          y: 30, autoAlpha: 0, duration: 1.0, ease: 'power3.out', delay: d * 0.07,
          scrollTrigger: { trigger: el, start: 'top 86%', once: true }
        });
      }); };
      // 等字体就绪再拆分/编排（避免 SplitText 断行测量不准）
      if (document.fonts && document.fonts.ready && document.fonts.ready.then) document.fonts.ready.then(run, run);
      else run();
      return;
    }
    if (REDUCE || !('IntersectionObserver' in window)) { els.forEach(function (el) { el.classList.add('in'); }); return; }
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------------- Split 逐字遮罩揭示 ---------------- */
  function initSplit() {
    var els = $$('[data-split]');
    if (!els.length) return;
    els.forEach(function (el) {
      var lines = (el.textContent || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      if (!lines.length) lines = [el.textContent || ''];
      el.textContent = '';
      el.classList.add('split');
      lines.forEach(function (line, li) {
        var ln = document.createElement('span'); ln.className = 'ln';
        Array.prototype.forEach.call(line, function (ch, ci) {
          if (ch === ' ') { ln.appendChild(document.createTextNode(' ')); return; }
          var s = document.createElement('span'); s.className = 'ch';
          s.style.setProperty('--i', ci); s.textContent = ch;
          ln.appendChild(s);
        });
        el.appendChild(ln);
      });
    });
    if (REDUCE || !('IntersectionObserver' in window)) { els.forEach(function (el) { el.classList.add('in'); }); return; }
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------------- 页内「场景流动」入场 ----------------
     首屏之下的每一幕（data-scene）：进入视口时从下方 9vh + 模糊流上来、去模糊就位，
     与页间转场（is-in）同一套视觉语言，让整页滚动像在不同场景间流动。
     安全：无 IO / reduced-motion 一律直接 .in；初始隐藏只在 html.js-on 下生效。 */
  function initScenes() {
    var secs = $$('[data-scene]');
    if (!secs.length) return;
    if (REDUCE || !('IntersectionObserver' in window)) {
      secs.forEach(function (s) { s.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.16, rootMargin: '0px 0px -10% 0px' });
    secs.forEach(function (s) { io.observe(s); });
  }

  /* ---------------- 首屏离场视差 ----------------
     滚出第一幕时，整组 hero 内容像「房间」在身后退去（上移 + 微缩 + 淡出）。
     配合背后固定不动的 WebGL 场（随滚动变章节），就是 bienville / hubtown 那种
     「你始终在一个空间里、只是视角在挪」的固定视图感。纯 transform/opacity，不重绘。 */
  function initHeroParallax() {
    var stage = $('.stage');
    if (!stage || REDUCE || COARSE) return;
    var body = $('.stage__body', stage);
    if (!body) return;
    var h = stage.offsetHeight || innerHeight, last = -1;
    pOn(window, 'resize', function () { h = stage.offsetHeight || innerHeight; }, { passive: true });
    loop('heroLeave', function () {
      var p = clamp(window.scrollY / h, 0, 1);
      if (Math.abs(p - last) < 0.002) return;     // 只在变动时写样式，避免无谓合成
      last = p;
      body.style.setProperty('--leave', p.toFixed(3));
    });
  }

  /* ---------------- Spotlight 追光照亮 ---------------- */
  function initSpotlight() {
    var stage = $('[data-spot]');
    if (!stage) return;
    var type = $('.stage__type', stage);
    if (COARSE || REDUCE) {
      // 无光标环境：把光固定在标题右下，仍有"被照亮"的层次
      stage.style.setProperty('--mx', '64%'); stage.style.setProperty('--my', '46%');
      if (type) { type.style.setProperty('--mx', '70%'); type.style.setProperty('--my', '60%'); }
      return;
    }
    var sr = stage.getBoundingClientRect(), tr = type ? type.getBoundingClientRect() : null;
    var mxs = sr.left + sr.width * 0.62, mys = sr.top + sr.height * 0.42;
    var cx = mxs, cy = mys;
    function relayout() { sr = stage.getBoundingClientRect(); tr = type ? type.getBoundingClientRect() : null; }
    pOn(window, 'resize', relayout, { passive: true });
    pOn(window, 'scroll', relayout, { passive: true });
    stage.addEventListener('mousemove', function (e) { mxs = e.clientX; mys = e.clientY; }, { passive: true });
    loop('spotlight', function () {
      cx = lerp(cx, mxs, 0.13); cy = lerp(cy, mys, 0.13);
      stage.style.setProperty('--mx', ((cx - sr.left) / (sr.width || 1) * 100) + '%');
      stage.style.setProperty('--my', ((cy - sr.top) / (sr.height || 1) * 100) + '%');
      if (type && tr) {
        type.style.setProperty('--mx', (cx - tr.left) + 'px');
        type.style.setProperty('--my', (cy - tr.top) + 'px');
      }
    });
  }

  /* ---------------- Gallery 钉住横滚（滚动驱动 + 拖拽）---------------- */
  function initGallery() {
    var sec = $('[data-gallery]');
    var track = sec && $('[data-gallery-track]', sec);
    if (!sec || !track) return;
    var sticky = $('.gallery__sticky', sec);
    var posters = $$('.poster', sec);
    var overflow = 0;
    function measure() {
      overflow = Math.max(0, track.scrollWidth - (sticky ? sticky.clientWidth : innerWidth));
      sec.style.height = (innerHeight + overflow) + 'px';
    }
    function render() {
      var r = sec.getBoundingClientRect();
      var total = sec.offsetHeight - innerHeight;
      var p = total > 0 ? clamp(-r.top / total, 0, 1) : 0;
      track.style.transform = 'translate3d(' + (-p * overflow) + 'px,0,0)';
      // 居中者点亮，其余压暗
      var mid = innerWidth / 2, best = null, bestD = Infinity;
      posters.forEach(function (po) {
        var b = po.getBoundingClientRect(), d = Math.abs((b.left + b.right) / 2 - mid);
        po.classList.toggle('dim', true);
        if (d < bestD) { bestD = d; best = po; }
      });
      if (best) { best.classList.remove('dim'); best.classList.add('on'); }
      posters.forEach(function (po) { if (po !== best) po.classList.remove('on'); });
    }
    measure(); render();
    pOn(window, 'resize', function () { measure(); render(); }, { passive: true });
    pOn(window, 'scroll', render, { passive: true });

    // 拖拽 = 直接改写页面滚动位置（pin 随之推进，干净）
    var down = false, sx = 0, sy = 0, moved = 0;
    track.addEventListener('pointerdown', function (e) {
      if (COARSE) return;
      down = true; sx = e.clientX; sy = window.scrollY; moved = 0;
      sec.classList.add('dragging'); track.setPointerCapture && track.setPointerCapture(e.pointerId);
    });
    track.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - sx; moved = Math.abs(dx);
      scrollToY(sy - dx * 1.15, true);      // 走统一入口：有 Lenis 时不让它把位置拉回去
    });
    function up(e) {
      if (!down) return; down = false; sec.classList.remove('dragging');
      if (moved < 6) {                     // 视为点击：交给链接
        var a = e.target.closest && e.target.closest('.poster');
        if (a && a.href) location.href = a.href;
      }
    }
    track.addEventListener('pointerup', up);
    track.addEventListener('pointercancel', up);
    track.addEventListener('click', function (e) { if (moved > 6) { e.preventDefault(); e.stopPropagation(); } }, true);
  }

  /* ---------------- 触摸端横滚海报廊：惯性甩动 ---------------- */
  function initTouchGallery() {
    var track = $('[data-gallery-track]');
    if (!track || !COARSE) return;
    var sx = 0, sy = 0, lx = 0, lt = 0, v = 0, mode = 0, id = null;
    track.addEventListener('touchstart', function (e) {
      var t = e.touches[0]; if (!t) return;
      sx = lx = t.clientX; sy = t.clientY; lt = performance.now(); v = 0; mode = 0;
      if (id) { cancelAnimationFrame(id); id = null; }
    }, { passive: true });
    track.addEventListener('touchmove', function (e) {
      var t = e.touches[0]; if (!t) return;
      var dx = t.clientX - sx, dy = t.clientY - sy;
      if (mode === 0) {
        if (Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy)) mode = 1;   // 横向意图
        else if (Math.abs(dy) > 8) mode = 2;                             // 纵向：交给页面滚动
      }
      if (mode !== 1) return;
      e.preventDefault();
      var now = performance.now(), mx = t.clientX;
      track.scrollLeft -= (mx - lx);
      if (now > lt) v = -(mx - lx) / (now - lt) * 16;
      lx = mx; lt = now;
      track.style.scrollSnapType = 'none';
    }, { passive: false });
    function end() {
      if (mode !== 1) return; mode = 0;
      (function decay() {
        v *= 0.95;
        if (Math.abs(v) < 0.5) { track.style.scrollSnapType = ''; return; }
        track.scrollLeft += v; id = requestAnimationFrame(decay);
      })();
    }
    track.addEventListener('touchend', end, { passive: true });
    track.addEventListener('touchcancel', end, { passive: true });
  }

  /* ---------------- Night 时间轴定位 ---------------- */
  function parseMin(t) {
    var m = /(\d{1,2})\s*[:：]\s*(\d{1,2})/.exec(t || '');
    if (!m) return null; var h = +m[1], mi = +m[2];
    if (h < 6) h += 24;                    // 凌晨场归到深夜
    return h * 60 + mi;
  }
  function fmtMin(v) {
    var h = Math.floor(v / 60) % 24, m = Math.round(v % 60);
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }
  function initNight() {
    var axis = $('[data-night]');
    if (!axis) return;
    var marks = $$('.night__mark', axis);
    var times = marks.map(function (m) { return parseMin(m.getAttribute('data-time')); }).filter(function (v) { return v != null; });
    if (!times.length) return;
    var lo = Math.min.apply(null, times), hi = Math.max.apply(null, times);
    if (hi - lo < 90) { var c = (lo + hi) / 2; lo = c - 60; hi = c + 60; }
    var pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
    for (var i = 0; i <= 5; i++) {
      var tick = document.createElement('div'); tick.className = 'night__tick';
      tick.style.left = (i / 5 * 88 + 6) + '%';
      var sp = document.createElement('span'); sp.textContent = fmtMin(lo + (hi - lo) * i / 5);
      tick.appendChild(sp); axis.appendChild(tick);
    }
    marks.forEach(function (m, i) {
      var t = parseMin(m.getAttribute('data-time'));
      if (t == null) { m.style.display = 'none'; return; }
      m.style.left = (6 + (t - lo) / (hi - lo) * 88) + '%';
      m.style.bottom = (22 + (i % 2) * 54) + 'px';
    });
    axis.style.minHeight = '256px';
  }

  /* ---------------- Float 视差 ---------------- */
  var floats = [];
  function initFloat() {
    floats = $$('[data-float]').map(function (el) {
      return { el: el, sp: parseFloat(el.getAttribute('data-float')) || -0.06 };
    });
  }
  function renderFloat() {
    for (var i = 0; i < floats.length; i++) {
      var f = floats[i], r = f.el.getBoundingClientRect();
      var c = r.top + r.height / 2 - innerHeight / 2;
      f.el.style.transform = 'translate3d(0,' + (c * f.sp).toFixed(2) + 'px,0)';
    }
  }

  /* ---------------- Magnetic 磁吸 ---------------- */
  function initMagnetic() {
    if (COARSE || REDUCE) return;
    $$('.btn').forEach(function (b) {
      var raf = null, tx = 0, ty = 0, cx = 0, cy = 0;
      b.addEventListener('mousemove', function (e) {
        var r = b.getBoundingClientRect();
        tx = (e.clientX - (r.left + r.width / 2)) * 0.28;
        ty = (e.clientY - (r.top + r.height / 2)) * 0.4;
        if (!raf) raf = requestAnimationFrame(tick);
      });
      b.addEventListener('mouseleave', function () { tx = 0; ty = 0; if (!raf) raf = requestAnimationFrame(tick); });
      function tick() {
        cx = lerp(cx, tx, 0.2); cy = lerp(cy, ty, 0.2);
        b.style.transform = 'translate(' + cx.toFixed(1) + 'px,' + cy.toFixed(1) + 'px)';
        if (Math.abs(cx - tx) > 0.1 || Math.abs(cy - ty) > 0.1) { raf = requestAnimationFrame(tick); } else { raf = null; }
      }
    });
  }

  /* ---------------- 幕次导轨 scroll-spy ---------------- */
  function initRail() {
    var rail = $('[data-rail]');
    if (!rail) return;
    var links = $$('a', rail);
    var secs = links.map(function (a) { return $(a.getAttribute('href')); }).filter(Boolean);
    if (!secs.length || !('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (en.isIntersecting) {
          links.forEach(function (a) { a.classList.toggle('on', a.getAttribute('href') === '#' + en.target.id); });
        }
      });
    }, { threshold: 0.4, rootMargin: '-20% 0px -40% 0px' });
    secs.forEach(function (s) { io.observe(s); });
  }

  /* ---------------- 引言轮播 ---------------- */
  function initVoices() {
    var box = $('[data-voices]');
    if (!box) return;
    var qs = $$('.voices__q', box), dots = $$('[data-voice-dots] button', box);
    if (qs.length < 2) return;
    var cur = 0;
    function go(i) {
      cur = (i + qs.length) % qs.length;
      qs.forEach(function (q, k) { q.classList.toggle('on', k === cur); });
      dots.forEach(function (d, k) { d.classList.toggle('on', k === cur); });
    }
    dots.forEach(function (d) { d.addEventListener('click', function () { go(+d.getAttribute('data-voice')); restart(); }); });
    /* 计时器挂在模块级 VOICE_TIMER 上：换页时 bootPage 会先 clearInterval，
       否则上一页那个轮播会一直转下去，和新页面的轮播抢同一批 --i */
    function restart() { if (VOICE_TIMER) clearInterval(VOICE_TIMER); if (!REDUCE) VOICE_TIMER = setInterval(function () { go(cur + 1); }, 5200); }
    restart();
  }

  /* ============================================================================
     场景流动式转场（v9 · 学 unseen.co 的换页）
     ----------------------------------------------------------------------------
     旧做法是「一个甜薯字标盖上去再跳」—— 硬切，用户一眼就看出来"卡了一下"。
     现在改成 unseen.co 那样：旧场景整体上移离场（子块错峰，像分镜而非一整块板砖），
     液面从下往上漫过屏幕（三条纵横光带 + 两条青/品红错位色散 = 图 2 那种水波折射），
     同时 fetch 新页面 → 就地换 DOM → 新场景从下方 11vh 流上来落到焦平面。

     为什么必须 fetch 换 DOM 而不是"播完动画再 location.href"：
       location.href 之后是白屏 + 重新解析 + 重新请求，中间那段白就是"卡顿感"的来源。
       就地换 DOM 才能让"旧场景退"和"新场景进"真正接得上。

     兜底（任何一条不满足就退回整页跳转，绝不留白屏）：
       · 拿不到 #main / DOMParser 解析失败 → location.href
       · fetch 非 2xx 或网络异常           → location.href
       · prefers-reduced-motion            → 不加任何位移，直接跳
       · 外部域 / # / mailto / download / _blank / 后台 / DM / data-noveil → 不拦
     ========================================================================== */
  var Transit = (function () {
    var busy = false;

    /* ---- 上下文转场表（学 unseen.co 的 Highway contextual transitions）----
       unseen.co 的换页不是"所有跳转一个样"：它按 from→to 的页面 slug 组合选不同转场
       （homeToProject / projectToProject / toWorld …）。这里把同样的思想搬进 Transit：
       按「页面种类」而非精确路径配对，选一个变体。默认 flow = 现状（液面漫过屏幕）；
       →详情 rise（更快、只留一条主液面，克制）；→表单 veil（不扫带，一层薄幕）；
       →首页 sweep（液面反向回落）。每个变体自带时长，JS 与 CSS 共用同一组 --tr-*。 */
    var TR = {
      flow:  { out: 0.44, in: 0.68, band: 0.82, cls: '' },        // 默认：三条液面 + 色散（现状）
      rise:  { out: 0.34, in: 0.56, band: 0.58, cls: 'tr-rise' }, // 进详情：更快、单条主液面
      veil:  { out: 0.30, in: 0.50, band: 0.50, cls: 'tr-veil' }, // 进表单/登录：薄幕淡换
      sweep: { out: 0.42, in: 0.66, band: 0.78, cls: 'tr-sweep' } // 回首页：液面反向
    };
    function kindOf(p) {
      if (!p || p === '/') return 'home';
      if (/^\/scripts\/?$/.test(p)) return 'browse';
      if (/^\/(script|car)\/[^/]/.test(p)) return 'detail';
      if (/^\/(login|register|forgot|profile)\/?$/.test(p)) return 'form';
      if (/^\/(me|dm|admin)\/?/.test(p)) return 'account';
      return 'list';                                        // 拼车/唠嗑/组局/问答 …
    }
    function pickTransition(fromPath, toPath) {
      var t = kindOf(toPath);
      if (t === 'detail') return 'rise';
      if (t === 'form') return 'veil';
      if (t === 'home') return 'sweep';
      return 'flow';                                        // 含 home→browse 等其余
    }
    /* 落表：把该变体的时长写进根元素的 --tr-*（secs() 读的就是它），并给液面层落类 */
    function applyTransition(name) {
      var cfg = TR[name] || TR.flow;
      try {
        var st = document.documentElement.style;
        st.setProperty('--tr-out', cfg.out + 's');
        st.setProperty('--tr-in', cfg.in + 's');
        st.setProperty('--tr-band', cfg.band + 's');
      } catch (e) {}
      var layer = $('#transit');
      if (layer) layer.className = 'transit' + (cfg.cls ? ' ' + cfg.cls : '');
      try { document.documentElement.setAttribute('data-tr', name); } catch (e) {}
    }

    /* 壳层级脚本：换页时**不能**重跑（重跑会重复绑 window/document 级监听，
       光标会变双份、滚动会双倍速）。其余页面级脚本必须跟着新内容重新执行。 */
    var SHELL_JS = /(^|\/)(csrf|unseen|unseen-field|gsap|ScrollTrigger|SplitText|lenis)\.(js|min\.js)/i;
    /* ⚠️ 这个值必须 ≥ --tr-out 的时长，否则旧场景的"上移"只播了个头就被换掉 ——
       实测过：硬编码 430ms 时，0.52s 的离场动画只走到 10%（translateY 才 -7px 就被换页）。 */
    function minOutMs() { return trOutMs(); }

    function init() {
      document.addEventListener('click', click);
      /* 后退：老实整页加载。在 SPA 里重建历史状态最容易出"点三次返回才回去"这类鬼问题 */
      addEventListener('popstate', function () { location.reload(); });
    }

    /* 转场时长只有一个来源：CSS 变量 --tr-out / --tr-in / --tr-band。
       以前这里的清场定时器硬编码 900ms，跟 CSS 里的 .52s/.78s 是两个独立的数字 ——
       调了 CSS 忘了改这里，动画就会被拦腰截断（而且这种 bug 很难一眼看出来）。 */
    function secs(name, dflt) {
      try {
        var v = getComputedStyle(document.documentElement).getPropertyValue(name);
        var n = parseFloat(v);
        return isFinite(n) && n > 0 ? n : dflt;
      } catch (e) { return dflt; }
    }
    function trOutMs() { return secs('--tr-out', 0.44) * 1000 + 60; }   // 离场动画播完才换页
    function totalMs() {
      return Math.max(secs('--tr-band', 0.82), secs('--tr-in', 0.68)) * 1000 + 160;
    }

    function click(e) {
      if (busy || REDUCE) return;
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      var a = e.target.closest && e.target.closest('a');
      if (!a) return;
      if (a.target === '_blank' || a.hasAttribute('download') ||
          a.hasAttribute('data-noveil') || a.hasAttribute('data-no-transit')) return;
      var href = a.getAttribute('href') || '';
      if (!href || href.charAt(0) === '#' || /^(mailto:|tel:|javascript:|blob:)/i.test(href)) return;
      var url;
      try { url = new URL(a.href, location.href); } catch (err) { return; }
      if (url.origin !== location.origin) return;
      if (/^\/(admin|dm)(\/|$)/.test(url.pathname)) return;              // 后台 / DM 工作台：各走各的
      /* 只换 query 时：只有「本页自带原地换内容」的才交给页面自己 —— 本本墙用 [data-lib] 标记，
         它的筛选/搜索是自己 fetch 换网格的，转场插一脚会和它打架。
         ⚠️ 别把这条写成「同名路径 + 有 query 就放行」：`/` → `/?browse=1` 也是同名路径带 query，
         但那是「落地页(welcome) → 浏览页(home)」的整页内容切换，放行就变成生硬整页跳（实测踩过）。 */
      if (url.pathname === location.pathname && url.search &&
          document.querySelector('[data-lib]')) return;
      e.preventDefault();
      go(url.href);
    }

    function go(url) {
      var main = $('#main');
      if (!main) { location.href = url; return; }
      busy = true;
      var t0 = (window.performance && performance.now) ? performance.now() : Date.now();

      /* ⓪ 先按 from→to 选转场变体（Highway contextual 的搬法）：落类 + 写 --tr-*。
         必须在下面读 minOutMs()/totalMs() 之前执行，否则用的还是上一组的时长。 */
      var toPath = url;
      try { toPath = new URL(url, location.href).pathname; } catch (e) {}
      applyTransition(pickTransition(location.pathname, toPath));

      /* ① 旧场景上移离场：每个直接子块给递增的上移量 + 递增延迟 —— 分镜感 */
      var kids = Array.prototype.slice.call(main.children);
      for (var i = 0; i < kids.length; i++) {
        kids[i].style.setProperty('--out-y', (14 + Math.min(i, 6) * 11) + 'px');
        kids[i].style.setProperty('--out-d', Math.min(i * 34, 190) + 'ms');
      }
      main.classList.add('is-out');

      /* ② 液面涌上来（纯 CSS transform，和 fetch 并行，谁慢等谁） */
      var layer = $('#transit');
      if (layer) layer.classList.add('on');

      /* ③ 并行拉新页面 */
      var html = null, failed = false;
      var req = fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
        .then(function (t) { html = t; })
        .catch(function () { failed = true; });

      Promise.resolve(req).then(function () {
        var spent = ((window.performance && performance.now) ? performance.now() : Date.now()) - t0;
        setTimeout(function () {
          if (failed || html == null) { location.href = url; return; }
          swap(url, html);
        }, Math.max(0, minOutMs() - spent));
      });
    }

    function swap(url, txt) {
      var doc2 = null;
      try { doc2 = new DOMParser().parseFromString(txt, 'text/html'); } catch (err) { doc2 = null; }
      var fresh = doc2 && doc2.querySelector('#main');
      if (!fresh) { location.href = url; return; }

      /* 顶栏 / 页脚一并换掉 —— 登录态、"我的"显示的名字、DM/后台入口都在里面。
         不换的话换页之后还是上一个页面的样子，这种不一致最伤可信度。 */
      try {
        var fn2 = doc2.querySelector('#nav'), on2 = $('#nav');
        if (fn2 && on2 && on2.parentNode) on2.parentNode.replaceChild(fn2, on2);
        var ff = doc2.querySelector('footer.foot'), of = $('footer.foot');
        if (ff && of && of.parentNode) of.parentNode.replaceChild(ff, of);
      } catch (err) {}

      var oldMain = $('#main');
      if (!oldMain || !oldMain.parentNode) { location.href = url; return; }
      oldMain.parentNode.replaceChild(fresh, oldMain);

      try { var tt = doc2.querySelector('title'); if (tt) document.title = tt.textContent; } catch (err) {}

      /* ④ 新场景先落到"下方 11vh + 略放大"的起跑位（无过渡），下一帧再放开 */
      fresh.classList.remove('is-out');
      fresh.classList.add('is-in');

      runScripts(fresh, doc2);
      try { history.pushState({ ts: 1 }, '', url); } catch (err) {}
      /* ⚠️ 不要在这里摘 html.smooth —— 那个类是"关掉 CSS 平滑滚动"的开关
         （html.smooth { scroll-behavior: auto }）。摘掉反而会让复位变成一段平滑滚动，
         新场景会从半空中滑下来。保持它不动，走统一入口的 immediate 复位才是瞬时的。 */
      scrollToY(0, true);

      /* ⑤ 重跑页面级实例（新 DOM 的揭示 / 逐字 / 追光 / 横滚 / 时间轴 / 视差 / 计数 / 素材探测） */
      bootPage(fresh);

      /* ⑥ 液面继续往上扫完再退（1.02s > 入场 0.78s），期间新场景已经在它后面流上来 ——
         这就是图 2 那种"水漫过屏幕、新场景在下面浮现"的观感。收尾统一在下面⑦做。 */
      if (layer2()) requestAnimationFrame(function () { layer2().classList.add('on'); });

      /* ⑦ 清场：位移、模糊、内联样式全部摘干净 —— 绝不给页面留常驻的合成开销。
         时长从 CSS 变量算，不写死。 */
      /* 拆两段：入场动画一结束就放开 busy（用户马上能再点），
         液面还要再扫一会儿才收，别把它提前掐掉。 */
      setTimeout(function () {
        var m = $('#main');
        if (m) {
          m.classList.remove('is-in', 'flow');
          m.style.filter = '';
          Array.prototype.slice.call(m.children).forEach(function (el) {
            el.style.removeProperty('--out-y'); el.style.removeProperty('--out-d');
          });
        }
        document.documentElement.classList.add('smooth');   // 幂等：确保平滑滚动始终关着
        busy = false;
      }, secs('--tr-in', 0.68) * 1000 + 120);
      setTimeout(function () {
        var l = layer2();
        if (l) { l.classList.remove('on'); l.className = 'transit'; }   // 顺带清掉 tr-* 变体类
      }, totalMs());
    }
    /* 液面层每次现查：换页时整块 #transit 是常驻节点（在 layout 里，不在 main 内），
       所以不会被 replaceChild 换掉，但现查更稳，也不依赖闭包缓存。 */
    function layer2() { return $('#transit'); }

    /* 换页后把"页面级脚本"重跑一遍（壳层那几个跳过）。
       浏览器有缓存，重跑一次成本几乎为零；少了它，只认第一次 DOM 的脚本（本本墙的
       前端筛选、上传、Tabs 这类）换页之后就再也不会工作了。 */
    function runScripts(scope, doc2) {
      /* ① 新内容里的内联脚本 */
      $$('script', scope).forEach(function (old) {
        if (old.src) return;
        var s = document.createElement('script');
        if (old.type) s.type = old.type;
        s.textContent = old.textContent;
        old.parentNode.replaceChild(s, old);
      });
      /* ② 文档级外链脚本：跳过滤层，其余"摘掉再插回"强制重跑 */
      var have = {};
      $$('script[src]').forEach(function (s) { have[s.src] = 1; });
      $$('script[src]', doc2).forEach(function (old) {
        var src = old.getAttribute('src') || '';
        if (!src || SHELL_JS.test(src)) return;
        var abs = old.src || src;
        if (have[abs]) {
          $$('script[src]').forEach(function (s) { if ((s.src || '') === abs && s.parentNode) s.parentNode.removeChild(s); });
        }
        var s = document.createElement('script');
        s.src = src;
        if (old.defer) s.defer = true;
        document.body.appendChild(s);
      });
    }

    return { init: init, go: go, busy: function () { return busy; } };
  })();

  /* ---------------- 首屏 loader（学 hubtown.co.in 的极简方块进度条）----------------
     hubtown 进场只有：一行等宽方块 + 「LOADING CONTENT」+ 右上百分比，没有 logo 动画。
     这里沿用同一套语法，而且让进度绑真实事件（DOM 就绪 / WebGL 首帧），
     再设 2.6s 兜底放行 —— 绝不把用户关在门外。 */
  function initBoot() {
    var boot = $('#boot');
    if (!boot || REDUCE) { if (boot) boot.classList.add('gone'); return; }
    var bar = $$('#bootBar i'), pct = $('#bootPct');
    var n = bar.length || 12, score = 0, done = false;
    function paint() {
      var filled = Math.round(score * n);
      for (var i = 0; i < n; i++) bar[i].classList.toggle('on', i < filled);
      if (pct) pct.textContent = Math.round(score * 100) + '%';
    }
    function bump(to) { if (to > score) { score = to; paint(); } }
    function finish() {
      if (done) return; done = true;
      bump(1);
      setTimeout(function () { boot.classList.add('gone'); }, 160);
    }
    paint();
    /* 场脚本可能比我们更早跑完（defer 顺序里 unseen-field.js 在 unseen.js 前面），
       那种情况下事件已经错过了，所以先看全局标记。 */
    if (window.__tsFieldReady) { score = 1; finish(); return; }
    bump(0.25);                                              // 脚本起来了
    requestAnimationFrame(function () { bump(0.55); });      // 首帧已经能画
    /* WebGL 场就绪（unseen-field.js 会派发这个事件）→ 直接满格 */
    addEventListener('ts:field-ready', function () { bump(1); finish(); }, { once: true });
    setTimeout(function () { bump(0.85); }, 700);
    setTimeout(finish, 2600);                                // 兜底：无论发生什么，2.6 秒后放行
    if (document.fonts && document.fonts.ready && document.fonts.ready.then) {
      document.fonts.ready.then(function () { bump(0.95); }, function () {});
    }
  }

  /* ---------------- 数字滚动 ---------------- */
  function initCount() {
    var els = $$('[data-count]');
    if (!els.length) return;
    els.forEach(function (el) {
      var to = parseFloat(el.getAttribute('data-count')) || 0;
      if (REDUCE) { el.textContent = to.toLocaleString(); return; }
      var st = null;
      (function tick(now) {
        if (st === null) st = now || performance.now();
        var k = Math.min(1, ((now || performance.now()) - st) / 1000);
        el.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))).toLocaleString();
        if (k < 1) requestAnimationFrame(tick);
      })();
    });
  }

  /* ---------------- 今日日期 ---------------- */
  function initToday() {
    var els = $$('[data-today]');
    if (!els.length) return;
    var d = new Date(), W = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    var s = (d.getMonth() + 1) + ' 月 ' + d.getDate() + ' 日 · ' + W[d.getDay()];
    els.forEach(function (el) { el.textContent = s; });
  }

  /* ---------------- 统一滚动帧（pin / 视差）---------------- */
  function wireScroll() {
    var pending = false;
    function on() {
      if (pending) return; pending = true;
      requestAnimationFrame(function () {
        pending = false;
        renderFloat();
        var g = $('[data-gallery]');
        if (g && g.__render) g.__render();
      });
    }
    addEventListener('scroll', on, { passive: true });
    addEventListener('resize', on, { passive: true });
  }

  /* ---------------- 导航滚动收缩 ---------------- */
  function initNav() {
    var nav = $('#nav');
    if (!nav) return;
    function upd() { nav.classList.toggle('scrolled', window.scrollY > 40); }
    addEventListener('scroll', upd, { passive: true });
    upd();
  }

  /* ---------------- 静止即退场（用户驱动：不自动表演）---------------- */
  function initIdle() {
    if (COARSE || REDUCE) return;
    var t = null, body = document.body;
    function active() {
      if (body.classList.contains('is-idle')) body.classList.remove('is-idle');
      clearTimeout(t);
      t = setTimeout(function () { body.classList.add('is-idle'); }, 2400);
    }
    addEventListener('mousemove', active, { passive: true });
    addEventListener('touchstart', active, { passive: true });
    addEventListener('keydown', active);
    t = setTimeout(function () { body.classList.add('is-idle'); }, 2400);
  }

  /* ---------------- 首屏实测素材位（有就启用，没有就退回纯 WebGL 暗场）---------------- */
  function initHeroMedia() {
    var host = $('[data-hero]');
    if (!host) return;
    var vSrc = host.getAttribute('data-hero-video');
    var iSrc = host.getAttribute('data-hero-img');
    function attach(el) {
      el.className = 'stage__media';
      host.appendChild(el);
      document.documentElement.classList.add('has-media');
    }
    function tryImage() {
      if (!iSrc) return;
      var img = new Image();
      img.onload = function () { attach(img); };
      img.src = iSrc;
    }
    if (vSrc && window.fetch) {
      fetch(vSrc, { method: 'HEAD' }).then(function (r) {
        if (!r || !r.ok) { tryImage(); return; }
        var v = document.createElement('video');
        v.src = vSrc; v.muted = true; v.loop = true; v.playsInline = true;
        v.setAttribute('autoplay', ''); v.setAttribute('muted', ''); v.setAttribute('preload', 'auto');
        v.setAttribute('tabindex', '-1');
        v.addEventListener('error', tryImage, { once: true });
        v.addEventListener('loadeddata', function () { attach(v); if (v.play) v.play().catch(function () {}); }, { once: true });
        v.load();
      }).catch(tryImage);
    } else { tryImage(); }
  }

  /* ---------------- 本本墙搜索：描边进度环（移植 nova 的 Search 模块）----------------
     一圈极淡底线 + 一段朱砂走线：聚焦开始巡航转圈，提交时一次性转满一整圈。
     值得抄的点是「反馈先于结果」—— 数据还没回来，那圈已经在转，人就不会觉得点了没反应。
     移植时只改一处：提交后的动作交回本页的原地换网格（见下面的 initLib）。 */
  function initSearch() {
    $$('.u-search').forEach(function (s) {
      if (s.getAttribute('data-bound') === '1') return;
      s.setAttribute('data-bound', '1');
      var inp = $('input', s);
      if (!inp) return;
      var form = s.closest('form') || $('form', s);
      inp.addEventListener('focus', function () { s.classList.add('is-focus', 'is-run'); });
      inp.addEventListener('blur', function () { s.classList.remove('is-focus', 'is-run'); });
      inp.addEventListener('input', function () { s.classList.toggle('has-val', !!inp.value.trim()); });
      if (inp.value.trim()) s.classList.add('has-val');
      if (!form) return;
      form.addEventListener('submit', function () {
        /* 那圈描边无论谁接管提交都要转满一圈 */
        s.classList.remove('is-run');
        s.classList.add('is-go');
        setTimeout(function () { s.classList.remove('is-go'); s.classList.add('is-run'); }, 760);
      });
    });
  }

  /* ---------------- 本本墙原地换网格（接上后端一直空着的 ?partial=1）----------------
     后端从一开始就支持"只返回卡片那一段"（views/public.py 的 partial=1），但前端从来没接 ——
     所以以前点分类、点难度全是整页跳：白一下、滚动位置没了、还得多等一次解析。
     这里补上：收集条件 → fetch 片段 → 只换网格 → pushState 改网址（能收藏能转发）。
     片段走 unseen/_scripts_grid.html（UiLoader 自动优先命中），**零后端改动**。 */
  function initLib() {
    var box = $('[data-lib]');
    if (!box || box.getAttribute('data-bound') === '1') return;
    box.setAttribute('data-bound', '1');
    var gridUrl = box.getAttribute('data-grid') || '';
    var pageUrl = box.getAttribute('data-url') || '/scripts';
    if (!gridUrl) return;
    var inp = $('.u-search__in', box);
    var diffSel = $('[data-lib-diff]', box);
    var favBtn = $('[data-lib-fav]', box);
    var tagBox = $('[data-lib-tags]');
    var busy = false;

    /* 条件一律从 DOM 现读，不在闭包里存状态 —— 任何来源的改动都能被正确反映 */
    function params() {
      var p = [];
      var q = inp && inp.value.trim();
      if (q) p.push('q=' + encodeURIComponent(q));
      var tags = $$('[data-lib-tag]', tagBox || document)
        .filter(function (b) { return b.classList.contains('on') && b.getAttribute('data-lib-tag'); })
        .map(function (b) { return b.getAttribute('data-lib-tag'); });
      if (tags.length) p.push('tags=' + encodeURIComponent(tags.join(',')));
      if (diffSel && diffSel.value) p.push('diff=' + encodeURIComponent(diffSel.value));
      if (favBtn && favBtn.getAttribute('data-lib-fav') === '1') p.push('fav=1');
      return p.join('&');
    }

    function apply() {
      if (busy) return;
      var qs = params();
      busy = true;
      var g0 = $('[data-lib-grid]');
      if (g0) g0.classList.add('is-loading');
      var url = gridUrl + (gridUrl.indexOf('?') > -1 ? '&' : '?') + qs;
      window.fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
        .then(function (html) {
          var g = $('[data-lib-grid]');
          if (!g || !g.parentNode) return;
          var tmp = document.createElement('div');
          tmp.innerHTML = html;
          var fresh = tmp.querySelector('[data-lib-grid]');
          if (!fresh) throw new Error('片段里没有网格');
          g.parentNode.replaceChild(fresh, g);
          /* 新卡片不会被 IntersectionObserver 观察到（它只认插入时那一批），
             所以手动补 in；延迟仍由 data-d 决定，于是换进来的卡片照样是依次淡入上浮。 */
          requestAnimationFrame(function () {
            $$('[data-reveal]', fresh).forEach(function (el) { el.classList.add('in'); });
          });
          var n = fresh.getAttribute('data-lib-n') || '0';
          $$('[data-lib-count]').forEach(function (el) { el.textContent = n; });
          var out = $('[data-lib-count-out]');
          if (out) out.textContent = n;
          try { history.pushState({ lib: 1 }, '', pageUrl + (qs ? '?' + qs : '')); } catch (e) {}
        })
        .catch(function () {
          /* 拿不到片段就老实整页跳 —— 绝不留在"点了没反应"的状态 */
          location.href = pageUrl + (qs ? '?' + qs : '');
        })
        .then(function () { busy = false; });
    }

    if (inp) {
      var deb = null;
      inp.addEventListener('input', function () {
        if (deb) clearTimeout(deb);
        deb = setTimeout(apply, 340);      // 边打边筛，但别每个字符都发一次请求
      });
    }
    if (diffSel) diffSel.addEventListener('change', apply);
    if (favBtn) favBtn.addEventListener('click', function () {
      var on = favBtn.getAttribute('data-lib-fav') === '1';
      favBtn.setAttribute('data-lib-fav', on ? '0' : '1');
      favBtn.classList.toggle('on', !on);
      apply();
    });
    if (tagBox) {
      tagBox.addEventListener('click', function (e) {
        var b = e.target.closest && e.target.closest('[data-lib-tag]');
        if (!b) return;
        var val = b.getAttribute('data-lib-tag');
        if (!val) {                        // 「全部」= 清空所有标签
          $$('[data-lib-tag]', tagBox).forEach(function (x) { x.classList.toggle('on', x === b); });
        } else {
          b.classList.toggle('on');
          var allBtn = $$('[data-lib-tag]', tagBox).filter(function (x) { return !x.getAttribute('data-lib-tag'); })[0];
          var anyOn = $$('[data-lib-tag]', tagBox).some(function (x) {
            return x.getAttribute('data-lib-tag') && x.classList.contains('on');
          });
          if (allBtn) allBtn.classList.toggle('on', !anyOn);
        }
        apply();
      });
    }
    /* 表单提交（回车 / 点放大镜）也走原地换网格，别让浏览器整页跳 */
    var form = $('form', box);
    if (form) form.addEventListener('submit', function (e) { e.preventDefault(); apply(); });
  }

  /* ---------------- 键盘彩蛋：S = 随机挑一本 ----------------
     （对标 whiteboard.is 首屏的 "PRESS S TO START A PROJECT" —— 一个不用点按钮的入口，
       让站点看起来"有人在用"，而不是一张静态海报。）*/
  function initShortcut() {
    /* 故意不在闭包里缓存元素列表：换页后 .poster / .card 是全新节点，
       缓存下来会让按 S 挑到一个已经不在 DOM 里的旧元素（点了没反应）。每次按键现查。 */
    function typing(el) {
      if (!el) return false;
      var t = (el.tagName || '').toLowerCase();
      return t === 'input' || t === 'textarea' || t === 'select' || el.isContentEditable;
    }
    addEventListener('keydown', function (e) {
      if (e.key !== 's' && e.key !== 'S') return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (typing(document.activeElement)) return;
      var links = $$('.poster, .card');
      if (!links.length) return;
      var a = links[Math.floor(Math.random() * links.length)];
      var href = a.getAttribute('href');
      if (!href) return;
      e.preventDefault();
      if (LENIS) LENIS.scrollTo(a, { offset: -(innerHeight - a.offsetHeight) / 2 });
      else a.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      links.forEach(function (p) { p.classList.remove('on'); });
      a.classList.add('on');
      /* 走场景流动转场，别用 location.href 硬切 —— 键盘入口更该有好动效 */
      setTimeout(function () { Transit.go(a.href); }, 480);
    });
  }

  /* ============================================================================
     启动：分两层
     · bootShell —— 整站只跑一次。它们绑的是 window / document 级监听
       （光标、惯量滚动、导航、idle、键盘彩蛋、loader、转场、统一滚动帧）。
       换页时重跑会让监听翻倍：光标变双影、滚轮变成双倍速。
     · bootPage —— 换页后必须重跑。它们认的是新 DOM 里的节点
       （揭示、逐字、追光、横滚、时间轴、视差、磁吸、导轨、引言、计数、素材探测）。
       跑之前先把上一轮的常驻资源清掉：pOff 摘 window 监听、停 rAF、停轮播计时器。
     ========================================================================== */
  function bootPage() {
    pOff();
    stopLoop('spotlight');
    stopLoop('heroLeave');
    if (VOICE_TIMER) { clearInterval(VOICE_TIMER); VOICE_TIMER = null; }
    initReveal();
    initSplit();
    initScenes();
    initHeroParallax();
    initSpotlight();
    initGallery();
    initTouchGallery();
    initNight();
    initFloat();
    initMagnetic();
    initRail();
    initVoices();
    initCount();
    initToday();
    initHeroMedia();
    initSearch();
    initLib();
  }

  function bootShell() {
    initCursor();
    initSmooth();
    initNav();
    initIdle();
    initShortcut();
    Transit.init();
    initBoot();
    wireScroll();
  }

  function init() {
    bootShell();
    bootPage();
    renderFloat();
    document.documentElement.classList.add('js-on');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
