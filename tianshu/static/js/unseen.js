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
  var WARM_READY = false;   // 媒体预暖只需装一次（换页后靠 MutationObserver 接管新节点）

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
    var mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my, live = false;
    addEventListener('mousemove', function (e) {
      mx = e.clientX; my = e.clientY;
      if (!live) { live = true; document.body.classList.add('cursor-live'); }   // 首次真实移动才显形
    }, { passive: true });
    loop('cursor', function () {
      rx = lerp(rx, mx, 0.18); ry = lerp(ry, my, 0.18);
      dot.style.transform = 'translate(' + mx + 'px,' + my + 'px) translate(-50%,-50%)';
      ring.style.transform = 'translate(' + rx + 'px,' + ry + 'px) translate(-50%,-50%)';
    });
    /* 状态机：交互元素放大；搜索框 → 放大镜；文本输入 → 竖杠；海报廊 → 四向箭头；
       链接/带标签 → 放大显标签。图标显隐交给 CSS（ring 的类）。 */
    function classify(t) {
      if (!t) return '';
      if (t.classList && t.classList.contains('u-search__in')) return 'search';
      if (t.closest && t.closest('.gallery__track')) return 'drag';
      if (t.matches && t.matches('input[type="text"],input[type="search"],input[type="email"],input[type="tel"],input:not([type]),textarea')) return 'text';
      if (t.matches && t.matches('a,[data-cursor]')) return 'link';
      return 'big';
    }
    function over(e) {
      var t = e.target.closest('a,button,[data-cursor],input,textarea,select,label,.u-search__in');
      if (!t) return;
      var state = classify(t);
      ring.classList.remove('big', 'search', 'text', 'drag', 'link');
      ring.classList.add(state);
      if (state === 'search' || state === 'text' || state === 'drag') {
        if (lb) lb.textContent = '';
        ring.classList.remove('tagged');
      } else {
        var label = t.getAttribute && t.getAttribute('data-cursor');
        if (lb) lb.textContent = label || '';
        if (label) ring.classList.add('tagged'); else ring.classList.remove('tagged');
      }
    }
    function out(e) {
      var t = e.target.closest('a,button,[data-cursor],input,textarea,select,label,.u-search__in');
      if (t) { ring.classList.remove('big', 'search', 'text', 'drag', 'link', 'tagged'); if (lb) lb.textContent = ''; }
    }
    document.addEventListener('mouseover', over);
    document.addEventListener('mouseout', out);
    document.addEventListener('mousedown', function (e) {
      dot.style.opacity = '.4';
      /* 确认类按钮：按压回弹 + 朱砂对勾（commit 反馈），不喷涟漪 */
      var bc = e.target.closest && e.target.closest('[data-confirm], .btn--confirm');
      if (bc) { commitFeedback(bc); return; }
      rippleAt(e.clientX, e.clientY);      // 其余：落点涟漪（学 nova）
    });
    document.addEventListener('mouseup', function () { dot.style.opacity = ''; });
  }

  /* 确认感动效（#99）：给按钮一个"落定"的按压回弹，取代涟漪；不暴露原生小手。 */
  function commitFeedback(el) {
    if (REDUCE || !el) return;
    el.classList.remove('is-commit'); void el.offsetWidth; el.classList.add('is-commit');
    setTimeout(function () { el.classList.remove('is-commit'); }, 640);
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
  /* #73 滚动进度条 + #78 回顶：轻量，一个 scroll 监听同时驱动两者。
     ⚠️ 必须用原生 addEventListener（不走 pOn）：bootPage 每次换页会 pOff 摘掉全部
     P_BOUND 监听，而本函数在 bootShell 只跑一次，若走 pOn 会被换页时一并摘掉，
     导致进度条/回顶失效。scrollbar/toTop 是 layout 里的常驻节点（在 #main 之外），
     监听挂 window 一次即可，换页不丢失、也不会堆积。 */
  function initScrollUI() {
    var barI = $('#scrollbar i');
    var top = $('#toTop');
    function update() {
      var h = document.documentElement;
      var max = Math.max(1, h.scrollHeight - innerHeight);
      var p = clamp(window.scrollY / max, 0, 1);
      if (barI) barI.style.width = (p * 100) + '%';
      if (top) top.classList.toggle('show', window.scrollY > 600);
    }
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update, { passive: true });
    update();
    if (top) {
      top.hidden = false;
      top.addEventListener('click', function () { scrollToY(0); });
    }
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
          scrollTrigger: { trigger: el, start: 'top 86%', once: true },
          /* 收尾清掉行内 transform：gsap 收尾会留下 identity 矩阵，使元素永久成为层叠上下文，
             把内部的下拉列表困在同层卡片/标签之下（选项点不到）。清掉后落回 CSS 的 transform:none。 */
          onComplete: function () { gsap.set(el, { clearProps: 'transform' }); }
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

  /* ---------------- 媒体预暖：提前「一整屏」把懒加载图解码好 ----------------
     用 rootMargin: '100% 0px' —— 元素还在屏幕下方一整屏之外时就算"进入"，
     于是解码/取图被提前执行，等真正滚到时那一刻不会卡。
     最需要它的是幕二那条横向海报廊：它一进屏就要被拖动，若 6 张图此刻才
     同时开始解码，拖动第一帧必掉。提前一屏解码，拖起来就是顺的。
     只做预暖：不改 DOM、不改尺寸、失败静默；新插入的卡片由 MutationObserver 自动接管。 */
  function initMediaWarm() {
    if (WARM_READY || !('IntersectionObserver' in window)) return;
    WARM_READY = true;
    var WARM = '[data-gallery-track] img[loading="lazy"], .cards img[loading="lazy"], img[data-warm]';
    var idle = window.requestIdleCallback || function (f) { return setTimeout(f, 160); };
    function warm(img) {
      // 先摘掉 lazy（否则浏览器在横向/远距离场景里可能压着不取），再解码。
      if (img.loading === 'lazy') img.loading = 'eager';
      idle(function () { if (img.decode) { img.decode()['catch'](function () {}); } });
    }
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        warm(en.target);
      });
    }, { rootMargin: '100% 0px' });
    // WeakSet：页面转场后旧节点被丢弃时不会拖住内存
    var seen = ('WeakSet' in window) ? new WeakSet() : { _a: [], has: function (n) { return this._a.indexOf(n) > -1; }, add: function (n) { this._a.push(n); } };
    function adopt(root) {
      var list = $$(WARM, root);
      for (var i = 0; i < list.length; i++) {
        if (seen.has(list[i])) continue;
        seen.add(list[i]); io.observe(list[i]);
      }
    }
    adopt(document);
    if (!('MutationObserver' in window)) return;
    var mo = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var n = added[j];
          if (n.nodeType !== 1) continue;
          if (n.matches && n.matches('img')) adopt(n.parentNode || document);
          else adopt(n);
        }
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });
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

  /* 首屏巨字逐行上浮（学 W1/U1 的进场）：两行标题错落淡入，把"平铺出现"换成有呼吸的开场 */
  function initHeroStagger() {
    var base = $('.base');
    if (!base || REDUCE) return;
    var lines = $$('.t', base);
    if (!lines.length) return;
    if (COARSE) { lines.forEach(function (l) { l.style.opacity = 1; }); return; }
    if (HAS_GSAP) {
      gsap.set(lines, { y: 28, opacity: 0 });
      gsap.to(lines, { y: 0, opacity: 1, duration: .9, ease: 'power3.out', stagger: .12, delay: .22 });
    }
  }

  /* 跑马灯随滚动提速（学 C1 的速度感应 marquee）：滚动越快，字幕跑得越快，停下归位 */
  function initTickerSpeed() {
    var track = $('.ticker__track');
    if (!track || COARSE) return;
    var anims = (track.getAnimations && track.getAnimations()) || [];
    if (!anims.length) return;
    var a = anims[0];
    var base = 1, target = 1, lenis = window.LENIS;
    loop('tickerSpeed', function () {
      var v = lenis && lenis.velocity ? Math.abs(lenis.velocity) : 0;
      target = 1 + Math.min(v / 16, 4);
      base += (target - base) * 0.08;
      try { a.playbackRate = base; } catch (e) {}
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
    var gbar = $('.gallery__bar i', sec);
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
      // #77 画廊进度指示：钉住模式下进度 = p
      if (gbar) gbar.style.width = (p * 100) + '%';
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
    var gbar = $('.gallery__bar i');
    function syncBar() {
      var max = Math.max(1, track.scrollWidth - track.clientWidth);
      if (gbar) gbar.style.width = (clamp(track.scrollLeft / max, 0, 1) * 100) + '%';
    }
    track.addEventListener('scroll', syncBar, { passive: true });
    syncBar();
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

  /* ---------------- 跟着光标走的悬浮缩略图（unseen.co 头号签名）----------------
     悬停剧目海报时，一张缩略图黏在光标旁、带轻微惯性，打破"一排静态卡片"的模板感。
     外层只定位、内层 .gal-thumb__in 负责缩放淡入（CSS 接管），互不抢 transform。 */
  function initGalleryThumb() {
    var thumb = $('.gal-thumb');
    if (!thumb || COARSE) return;
    var inner = $('.gal-thumb__in', thumb), img = $('.gal-thumb img', thumb), glyph = $('.gt-glyph', thumb);
    var tx = innerWidth / 2, ty = innerHeight / 2, cx = tx, cy = ty, active = false;
    function show(po) {
      var pic = $('.poster__img', po);
      if (pic && pic.getAttribute('src')) { img.src = pic.getAttribute('src'); img.style.display = ''; glyph.style.display = 'none'; }
      else { img.style.display = 'none'; img.removeAttribute('src'); glyph.textContent = (($('.poster__glyph', po) || {}).textContent || '本'); glyph.style.display = ''; }
      thumb.classList.add('on'); active = true;
    }
    function hide() { thumb.classList.remove('on'); active = false; }
    $$('.poster').forEach(function (po) {
      po.addEventListener('mouseenter', function () { show(po); });
      po.addEventListener('mouseleave', hide);
    });
    addEventListener('mousemove', function (e) { tx = e.clientX; ty = e.clientY; }, { passive: true });
    loop('galthumb', function () {
      cx = lerp(cx, tx, 0.16); cy = lerp(cy, ty, 0.16);
      thumb.style.transform = 'translate(' + cx + 'px,' + cy + 'px)';
    });
  }

  /* ---------------- 海报廊键盘替代（WCAG 2.5.7：拖拽不能是唯一方式）----------------
     Tab 本就能逐个聚焦卡片（浏览器会把卡片滚进视野，钉住的导轨随之推进）；
     这里再补两件：←/→ 在卡片间移动焦点，以及两个可见的前后按钮（已加在 home.html）。 */
  function initGalleryKeyboard() {
    var track = $('[data-gallery-track]');
    if (!track) return;
    var posters = $$('.poster', track);
    if (!posters.length) return;
    var i = 0;
    function go(n) {
      i = Math.max(0, Math.min(posters.length - 1, n));
      var p = posters[i];
      if (p && p.focus) p.focus();               // 聚焦即触发浏览器把卡片滚进视野
      posters.forEach(function (x) { x.classList.toggle('on', x === p); });
    }
    var prev = $('[data-gal-prev]'), next = $('[data-gal-next]');
    if (prev) prev.addEventListener('click', function () { go(i - 1); });
    if (next) next.addEventListener('click', function () { go(i + 1); });
    /* 只在海报廊进入视口时接管方向键，别把全站的方向键都抢了；
       也要避开正在输入的表单控件（换页会 pOff 统一摘掉这个监听）。 */
    pOn(document, 'keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      var a = document.activeElement;
      if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' ||
                a.tagName === 'SELECT' || a.isContentEditable)) return;
      var r = track.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight) return;
      e.preventDefault();
      go(e.key === 'ArrowRight' ? i + 1 : i - 1);
    });
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

  /* ---------------- 深度模糊墙（学 cosmos.so：随机布点 + 离中心越远越糊/越淡）---------------- */
  function initDepthWall() {
    $$('[data-depthwall]').forEach(function (host) {
      if (host.__built) return; host.__built = true;
      for (var i = 0; i < 22; i++) {
        var t = document.createElement('i');
        var x = Math.random() * 100, y = Math.random() * 100;
        var edge = Math.min(x, 100 - x, y, 100 - y) / 50;      // 0(贴边) ~ 1(居中)
        t.style.left = x + '%'; t.style.top = y + '%';
        t.style.transform = 'translate(-50%,-50%) rotate(' + (Math.random() * 40 - 20).toFixed(1) +
                            'deg) scale(' + (0.55 + edge * 0.7).toFixed(2) + ')';
        t.style.opacity = (0.18 + edge * 0.5).toFixed(2);
        t.style.filter = 'blur(' + ((1 - edge) * 2.4).toFixed(1) + 'px)';
        host.appendChild(t);
        if (HAS_GSAP && !REDUCE) {
          gsap.to(t, { y: '+=' + (8 + Math.random() * 18), duration: 5 + Math.random() * 4,
                       ease: 'sine.inOut', yoyo: true, repeat: -1, delay: Math.random() * 3 });
        }
      }
    });
  }

  /* ---------------- 卡片：噪声毛边圆形揭示（学 hubtown 的鼠标蒙版）----------------
     事件委托到 document —— 本本墙的网格会被 initLib 的 fetch 换掉，
     挂在卡片上的监听会一起被换掉；委托则对新卡片同样生效，且只有一个监听。 */
  function initCardLit() {
    if (COARSE || document.__cardLit) return;
    document.__cardLit = true;
    document.addEventListener('mousemove', function (e) {
      var cover = e.target && e.target.closest && e.target.closest('.card__cover');
      if (!cover) return;
      var r = cover.getBoundingClientRect();
      cover.style.setProperty('--mx', ((e.clientX - r.left) / (r.width || 1) * 100) + '%');
      cover.style.setProperty('--my', ((e.clientY - r.top) / (r.height || 1) * 100) + '%');
    }, { passive: true });
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
    /* 转场巨字（学 U1 进场先出巨大章节名）：按目的地种给一行大字幕，扫过时浮出 */
    var TRANSIT_LABEL = {
      home: '首页', browse: '本本墙', detail: '本子', list: '一览',
      form: '登记', account: '我的'
    };
    function transitTitleEl() { return document.getElementById('transitTitle'); }
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
    var SHELL_JS = /(^|\/)(csrf|unseen|unseen-field|gsap|ScrollTrigger|SplitText|lenis|vitals)\.(js|min\.js)/i;
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
      var tt = transitTitleEl();
      if (tt) tt.textContent = TRANSIT_LABEL[kindOf(toPath)] || '';

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

    /* 指针跟随下划线（学 nova 的滑动线）：整条导航一根线，走到哪滑到哪 */
    var links = $('.nav__links', nav);
    if (!links) return;
    var line = $('.nav__line', links), items = $$('a', links);
    if (!line || !items.length) return;
    function place(el) {
      if (!el) { line.style.opacity = '0'; return; }
      var r = el.getBoundingClientRect(), lr = links.getBoundingClientRect();
      line.style.opacity = '1';
      line.style.width = r.width + 'px';
      line.style.transform = 'translateX(' + (r.left - lr.left) + 'px)';
    }
    var cur = $('.on', links) || items[0];
    place(cur);
    items.forEach(function (a) {
      a.addEventListener('mouseenter', function () { place(a); });
      a.addEventListener('focus', function () { place(a); });
    });
    links.addEventListener('mouseleave', function () { place(cur); });
    addEventListener('resize', function () { place(cur); });
  }

  /* ---------------- 海报"立起来"（学 nova 的视角折叠）----------------
     悬停那张随指针做 rotateX/Y 立起，同排兄弟后退让位 —— 卡片不再是平面大方块。 */
  function initTilt() {
    var sec = $('[data-gallery]');
    if (!sec || COARSE) return;
    var posters = $$('.poster', sec);
    posters.forEach(function (po) {
      po.addEventListener('pointerenter', function () {
        sec.classList.add('dimming'); po.classList.add('is-cur');
        po.style.setProperty('--fz', '0px'); po.style.setProperty('--fs', '1.05');
      });
      po.addEventListener('pointermove', function (e) {
        var r = po.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - .5;
        var py = (e.clientY - r.top) / r.height - .5;
        po.style.setProperty('--fy', (px * 18).toFixed(2) + 'deg');
        po.style.setProperty('--fx', (py * -16).toFixed(2) + 'deg');
      });
      po.addEventListener('pointerleave', function () {
        sec.classList.remove('dimming'); po.classList.remove('is-cur');
        po.style.setProperty('--fx', '0deg'); po.style.setProperty('--fy', '0deg');
        po.style.setProperty('--fz', '0px'); po.style.setProperty('--fs', '1');
      });
    });
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

  /* ---------------- 首屏素材（图片直出，视频可升级）----------------
     图片现在由模板**直出**（见 home.html，带 fetchpriority="high"，是首屏 LCP 候选）。
     旧版要等这里先发 HEAD 探测再创建 <img> —— 那样图片是"晚发现"的，LCP 吃亏。
     这里只做两件事：① 图片就绪时给 <html> 加 has-media（激活压暗幕布等样式）；
     ② 若 hero.mp4 真的存在（HEAD 2xx）才把它换成循环视频；不存在就保留图片。 */
  function initHeroMedia() {
    var host = $('[data-hero]');
    if (!host) return;
    var existing = $('.stage__media', host);
    var vSrc = host.getAttribute('data-hero-video');
    function mark() { document.documentElement.classList.add('has-media'); }
    if (existing && existing.tagName === 'IMG') {
      if (existing.complete && existing.naturalWidth) mark();
      else existing.addEventListener('load', mark, { once: true });
    }
    if (!vSrc || !window.fetch) return;
    fetch(vSrc, { method: 'HEAD' }).then(function (r) {
      if (!r || !r.ok) return;                       // 没有视频 → 保留直出的图片
      var v = document.createElement('video');
      v.className = 'stage__media';
      v.src = vSrc; v.muted = true; v.loop = true; v.playsInline = true;
      v.setAttribute('autoplay', ''); v.setAttribute('muted', ''); v.setAttribute('preload', 'auto');
      v.setAttribute('tabindex', '-1');
      v.addEventListener('loadeddata', function () {
        if (existing && existing.parentNode) existing.parentNode.replaceChild(v, existing);
        else host.appendChild(v);
        mark(); if (v.play) v.play().catch(function () {});
      }, { once: true });
      v.load();
    }).catch(function () {});
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
      initSearchSuggest(s, inp, form);
      if (!form) return;
      form.addEventListener('submit', function () {
        /* 那圈描边无论谁接管提交都要转满一圈 */
        s.classList.remove('is-run');
        s.classList.add('is-go');
        setTimeout(function () { s.classList.remove('is-go'); s.classList.add('is-run'); }, 760);
      });
    });
  }

  /* ---------------- #148 搜索历史：聚焦下拉「最近搜过」----------------
     存在 localStorage（客户端私有，不占后端、不跨设备）。聚焦即列，输入即按包含过滤；
     点一条填回输入框并立即重搜（复用本本墙原地换网格），可一键清空。 */
  function initSearchSuggest(s, inp, form) {
    var sug = $('.u-search__sug', s);
    if (!sug) return;
    var listBox = $('[data-sug-list]', sug);
    var clearBtn = $('[data-sug-clear]', sug);
    var KEY = 'ts_recent_q_v1', MAX = 6;
    function load() { try { var a = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(a) ? a : []; } catch (e) { return []; } }
    function save(a) { try { localStorage.setItem(KEY, JSON.stringify(a.slice(0, MAX))); } catch (e) {} }
    function remember(q) {
      q = (q || '').trim(); if (!q) return;
      var a = load().filter(function (x) { return x !== q; });
      a.unshift(q); save(a);
    }
    var clockSVG = '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6.2" stroke="currentColor" stroke-width="1.3"/><path d="M8 4.6V8l2.4 1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';
    function render() {
      var q = (inp.value || '').trim().toLowerCase();
      var all = load();
      var items = q ? all.filter(function (x) { return x.toLowerCase().indexOf(q) > -1; }) : all;
      if (!items.length) { sug.hidden = true; return; }
      listBox.innerHTML = '';
      items.forEach(function (term) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'u-search__sug-i'; b.setAttribute('role', 'option');
        var ic = document.createElement('span'); ic.className = 'ic'; ic.innerHTML = clockSVG;
        var tx = document.createElement('span'); tx.className = 'tx'; tx.textContent = term;
        b.appendChild(ic); b.appendChild(tx);
        b.addEventListener('mousedown', function (e) { e.preventDefault(); });   // 抢在输入框 blur 之前
        b.addEventListener('click', function () {
          inp.value = term; inp.classList.add('has-val'); sug.hidden = true;
          remember(term);
          if (form) form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        });
        listBox.appendChild(b);
      });
      sug.hidden = false;
    }
    inp.addEventListener('focus', render);
    inp.addEventListener('input', render);
    inp.addEventListener('blur', function () { setTimeout(function () { sug.hidden = true; }, 170); });
    if (form) form.addEventListener('submit', function () { remember(inp.value); sug.hidden = true; });
    if (clearBtn) {
      clearBtn.addEventListener('mousedown', function (e) { e.preventDefault(); });
      clearBtn.addEventListener('click', function () { save([]); sug.hidden = true; });
    }
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
    var clearBtn = $('[data-lib-clear]', box);
    var busy = false;

    /* 清空筛选入口：有任一条件生效才显形（多选后条件可能多条，一键退回全部） */
    function hasFilters() {
      if (inp && inp.value.trim()) return true;
      if (favBtn && favBtn.getAttribute('data-lib-fav') === '1') return true;
      if (diffSel && $$('option', diffSel).some(function (o) { return o.selected; })) return true;
      if (tagBox && $$('[data-lib-tag]', tagBox).some(function (b) {
        return b.getAttribute('data-lib-tag') && b.classList.contains('on');
      })) return true;
      return false;
    }
    function syncClear() { if (clearBtn) clearBtn.hidden = !hasFilters(); }

    /* 条件一律从 DOM 现读，不在闭包里存状态 —— 任何来源的改动都能被正确反映 */
    function params() {
      var p = [];
      var q = inp && inp.value.trim();
      if (q) p.push('q=' + encodeURIComponent(q));
      var tags = $$('[data-lib-tag]', tagBox || document)
        .filter(function (b) { return b.classList.contains('on') && b.getAttribute('data-lib-tag'); })
        .map(function (b) { return b.getAttribute('data-lib-tag'); });
      if (tags.length) p.push('tags=' + encodeURIComponent(tags.join(',')));
      if (diffSel && diffSel.multiple) {
        var diffs = $$('option', diffSel).filter(function (o) { return o.selected; }).map(function (o) { return o.value; });
        if (diffs.length) p.push('diffs=' + encodeURIComponent(diffs.join(',')));
      } else if (diffSel && diffSel.value) {
        p.push('diff=' + encodeURIComponent(diffSel.value));
      }
      if (favBtn && favBtn.getAttribute('data-lib-fav') === '1') p.push('fav=1');
      return p.join('&');
    }

    function apply() {
      if (busy) return;
      syncClear();
      var qs = params();
      busy = true;
      var g0 = $('[data-lib-grid]');
      if (g0) { g0.classList.add('is-loading'); g0.classList.add('is-leaving'); }   // 旧网格先轻淡出下移，不再瞬切
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
          $$('[data-lib-count]').forEach(function (el) {
            if (el.textContent !== n) {            // 数字变了才轻弹一下，让"筛掉了"被看见
              el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump');
            }
            el.textContent = n;
          });
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
    if (clearBtn) clearBtn.addEventListener('click', function () {
      if (inp) { inp.value = ''; inp.classList.remove('has-val'); }
      if (favBtn) { favBtn.setAttribute('data-lib-fav', '0'); favBtn.classList.remove('on'); }
      if (diffSel) {                       // 多选清空：全部反选 + 让自定义下拉重画 label
        $$('option', diffSel).forEach(function (o) { o.selected = false; });
        var w = diffSel.closest ? diffSel.closest('.u-select') : null;
        if (w && w.__usync) w.__usync();
      }
      if (tagBox) $$('[data-lib-tag]', tagBox).forEach(function (x) { x.classList.toggle('on', !x.getAttribute('data-lib-tag')); });
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
    syncClear();                            // 首屏按当前条件决定是否露出「清空筛选」
  }

  /* ---------------- 自定义下拉选择框（#97 · 渐进增强原生 <select>）----------------
     把原生 <select data-u-select> 包成 editorial 风格下拉：发丝描边按钮 + 朱砂对勾 +
     展开时列表从顶部裁开、选项逐条错落淡入。原生 select 移入 wrapper 内（视觉隐藏），
     选中后回写值并 dispatch change —— 所以 car 的 onchange 整页筛、scripts 的 ?partial
     换网格、comm 的表单提交全部照旧工作，零后端改动。
     全局的"外部点击关闭 / Esc / 方向键"只绑一次（用 document 委托），避免换页后重复绑定。 */
  /* 唠嗑发图：选图即出缩略预览（原生 file 多选 + 本地预览，不发请求） */
  function initPostForm() {
    var inp = $('.post__file input[type=file]');
    var box = $('.post__previews');
    if (!inp || !box || box.__bound) return;
    box.__bound = 1;
    inp.addEventListener('change', function () {
      box.innerHTML = '';
      var files = inp.files || [];
      for (var i = 0; i < Math.min(files.length, 3); i++) {
        var f = files[i];
        if (!/^image\//.test(f.type)) continue;
        var url = URL.createObjectURL(f);
        var img = document.createElement('img');
        img.src = url; img.alt = '';
        box.appendChild(img);
        img.addEventListener('load', function () { try { URL.revokeObjectURL(url); } catch (e) {} });
      }
    });
  }

  function initSelect() {
    if (!document.__uSelBound) {
      document.__uSelBound = 1;
      document.addEventListener('click', function (e) {
        var open = $$('.u-select.open');
        for (var i = 0; i < open.length; i++) { if (!open[i].contains(e.target)) closeSelect(open[i]); }
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { $$('.u-select.open').forEach(closeSelect); return; }
        var cur = $('.u-select.open'); if (!cur) return;
        var list = $('.u-select__list', cur); if (!list) return;
        var opts = $$('.u-select__opt', list);
        var idx = -1;
        for (var i = 0; i < opts.length; i++) if (opts[i].classList.contains('active')) { idx = i; break; }
        if (e.key === 'ArrowDown') { e.preventDefault(); setSelectActive(cur, opts, Math.min(opts.length - 1, idx + 1)); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); setSelectActive(cur, opts, Math.max(0, idx - 1)); }
        else if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); if (idx >= 0) pickSelect(cur, opts[idx]); }
        else if (e.key === 'Home') { e.preventDefault(); setSelectActive(cur, opts, 0); }
        else if (e.key === 'End') { e.preventDefault(); setSelectActive(cur, opts, opts.length - 1); }
      });
    }
    $$('select[data-u-select]').forEach(function (sel) {
      if (sel.getAttribute('data-bound') === '1') return;
      sel.setAttribute('data-bound', '1');
      buildSelect(sel);
    });
  }
  function buildSelect(sel) {
    var multi = !!sel.multiple;
    var wrap = document.createElement('span');
    wrap.className = 'u-select' + (multi ? ' u-select--multi' : '');
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);                 // 原生 select 移入 wrapper：仍在表单内，照常提交
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'u-select__btn';
    btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
    var lbl = document.createElement('span'); lbl.className = 'lbl';
    var chev = document.createElement('span'); chev.className = 'chev';
    btn.appendChild(lbl); btn.appendChild(chev);
    var list = document.createElement('div'); list.className = 'u-select__list'; list.setAttribute('role', 'listbox');
    if (multi) list.setAttribute('aria-multiselectable', 'true');
    /* a11y：role=listbox 是"输入类"控件，必须有无障碍名，否则 axe 报 aria-input-field-name */
    list.setAttribute('aria-label', sel.getAttribute('aria-label') || '选项列表');
    var tickSVG = '<svg viewBox="0 0 16 16" fill="none"><path d="M3 8.5 6.5 12 13 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var btns = [], n = 0;                  // btns 与 sel.options 顺序一一对应
    function addOption(o) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'u-select__opt'; b.setAttribute('role', 'option');
      b.setAttribute('data-val', o.value);
      b.style.setProperty('--i', n++);     // 错落淡入序：用 --i 而非 :nth-child，避免被 optgroup 标题打乱
      var t = document.createElement('span'); t.textContent = o.textContent;
      var tick = document.createElement('span'); tick.className = 'tick'; tick.innerHTML = tickSVG;
      b.appendChild(t); b.appendChild(tick);
      b.addEventListener('click', function () { pickSelect(wrap, b); });
      btns.push(b); list.appendChild(b);
    }
    /* 遍历 children 才能保住 <optgroup> 的分组标题（sel.options 会把它们拍平） */
    Array.prototype.slice.call(sel.children).forEach(function (node) {
      if (node.tagName === 'OPTGROUP') {
        var gl = document.createElement('div');
        gl.className = 'u-select__grp'; gl.textContent = node.label || '';
        list.appendChild(gl);
        Array.prototype.slice.call(node.children).forEach(addOption);
      } else if (node.tagName === 'OPTION') {
        addOption(node);
      }
    });
    wrap.appendChild(btn); wrap.appendChild(list);
    var ph = sel.getAttribute('data-placeholder') || (multi ? '全部' : '');
    function findOpt(val) {
      for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === val) return sel.options[i];
      return null;
    }
    function sync() {
      if (multi) {
        var names = [];
        btns.forEach(function (b) {
          var o = findOpt(b.getAttribute('data-val'));
          var on = !!(o && o.selected);
          b.classList.toggle('sel', on);
          b.setAttribute('aria-selected', on ? 'true' : 'false');
          if (on) names.push(b.firstChild.textContent);
        });
        wrap.classList.toggle('has-sel', names.length > 0);
        lbl.textContent = !names.length ? ph : (names.length > 2 ? '已选 ' + names.length + ' 项' : names.join('、'));
      } else {
        var v = sel.value, cur = null;
        btns.forEach(function (b) {
          var on = b.getAttribute('data-val') === v; b.classList.toggle('sel', on); if (on) cur = b;
        });
        var o = sel.options[sel.selectedIndex]; lbl.textContent = o ? o.textContent : '';
      }
    }
    sync();
    sel.addEventListener('change', sync);
    wrap.__usync = sync;                    // 供 pickSelect（多选）复用
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = wrap.classList.contains('open');
      $$('.u-select.open').forEach(function (w) { if (w !== wrap) closeSelect(w); });
      if (wasOpen) closeSelect(wrap); else openSelect(wrap);
    });
  }
  function openSelect(wrap) {
    var list = $('.u-select__list', wrap);
    var btn = $('.u-select__btn', wrap);
    /* 先量再决定朝上还是朝下：下方放不下且上方更宽裕就向上弹（矮屏 / 靠近视口底部）。
       列表本身超高时由 CSS 的 max-height + overflow-y:auto 内部滚动。 */
    if (list && btn) {
      wrap.classList.remove('u-select--up');
      var rb = btn.getBoundingClientRect();
      var below = innerHeight - rb.bottom;
      var need = Math.min(list.scrollHeight || 260, innerHeight * 0.62);
      if (below < need + 18 && rb.top > below) wrap.classList.add('u-select--up');
    }
    wrap.classList.add('open');
    if (btn) btn.setAttribute('aria-expanded', 'true');
    var opts = $$('.u-select__opt', list);
    for (var i = 0; i < opts.length; i++) { opts[i].classList.remove('active'); if (opts[i].classList.contains('sel')) opts[i].classList.add('active'); }
    if (btn) btn.focus();
  }
  function closeSelect(wrap) {
    wrap.classList.remove('open');
    var btn = $('.u-select__btn', wrap); if (btn) btn.setAttribute('aria-expanded', 'false');
  }
  function setSelectActive(wrap, opts, idx) {
    for (var i = 0; i < opts.length; i++) opts[i].classList.toggle('active', i === idx);
    if (opts[idx] && opts[idx].scrollIntoView) opts[idx].scrollIntoView({ block: 'nearest' });
  }
  function pickSelect(wrap, b) {
    var sel = $('select', wrap);
    if (!sel) return;
    if (sel.multiple) {                     // 多选：翻转该项、保持展开、实时回写并通知
      var o = null, val = b.getAttribute('data-val');
      for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === val) { o = sel.options[i]; break; }
      if (o) o.selected = !o.selected;
      if (wrap.__usync) wrap.__usync();
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return;                               // 不关列表，方便连选
    }
    sel.value = b.getAttribute('data-val');
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    closeSelect(wrap);
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
    initMediaWarm();
    initHeroParallax();
    initHeroStagger();
    initTickerSpeed();
    initSpotlight();
    initGallery();
    initTouchGallery();
    initGalleryKeyboard();
    initGalleryThumb();
    initTilt();
    initNight();
    initFloat();
    initDepthWall();
    initCardLit();
    initMagnetic();
    initRail();
    initVoices();
    initCount();
    initToday();
    initHeroMedia();
    initSearch();
    initLib();
    initSelect();
    initPostForm();
  }

  function bootShell() {
    initCursor();
    initSmooth();
    initScrollUI();
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
