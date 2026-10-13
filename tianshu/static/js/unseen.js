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

  /* ---------------- 情境软光标 ---------------- */
  function initCursor() {
    if (COARSE || REDUCE) return;
    var dot = $('.cursor'), ring = $('.cursor-ring');
    if (!dot || !ring) return;
    var lb = $('.lb', ring);
    document.body.classList.add('has-cursor');
    var mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
    addEventListener('mousemove', function (e) { mx = e.clientX; my = e.clientY; }, { passive: true });
    (function loop() {
      rx = lerp(rx, mx, 0.18); ry = lerp(ry, my, 0.18);
      dot.style.transform = 'translate(' + mx + 'px,' + my + 'px) translate(-50%,-50%)';
      ring.style.transform = 'translate(' + rx + 'px,' + ry + 'px) translate(-50%,-50%)';
      requestAnimationFrame(loop);
    })();
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
    document.addEventListener('mousedown', function () { dot.style.opacity = '.4'; });
    document.addEventListener('mouseup', function () { dot.style.opacity = ''; });
  }

  /* ---------------- Smooth 惯量滚动（Lenis 式：驱动原生 scrollTo，保留 sticky/锚点）---------------- */
  function initSmooth() {
    if (REDUCE || COARSE) return;
    var doc = document.documentElement;
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
    addEventListener('resize', relayout, { passive: true });
    addEventListener('scroll', relayout, { passive: true });
    stage.addEventListener('mousemove', function (e) { mxs = e.clientX; mys = e.clientY; }, { passive: true });
    (function loop() {
      cx = lerp(cx, mxs, 0.13); cy = lerp(cy, mys, 0.13);
      stage.style.setProperty('--mx', ((cx - sr.left) / (sr.width || 1) * 100) + '%');
      stage.style.setProperty('--my', ((cy - sr.top) / (sr.height || 1) * 100) + '%');
      if (type && tr) {
        type.style.setProperty('--mx', (cx - tr.left) + 'px');
        type.style.setProperty('--my', (cy - tr.top) + 'px');
      }
      requestAnimationFrame(loop);
    })();
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
    addEventListener('resize', function () { measure(); render(); }, { passive: true });
    addEventListener('scroll', render, { passive: true });

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
      window.scrollTo(0, sy - dx * 1.15);
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
    var cur = 0, timer = null;
    function go(i) {
      cur = (i + qs.length) % qs.length;
      qs.forEach(function (q, k) { q.classList.toggle('on', k === cur); });
      dots.forEach(function (d, k) { d.classList.toggle('on', k === cur); });
    }
    dots.forEach(function (d) { d.addEventListener('click', function () { go(+d.getAttribute('data-voice')); restart(); }); });
    function restart() { if (timer) clearInterval(timer); if (!REDUCE) timer = setInterval(function () { go(cur + 1); }, 5200); }
    restart();
  }

  /* ---------------- 换页 veil ---------------- */
  function initVeil() {
    if (REDUCE) return;
    var veil = $('.veil');
    if (!veil) return;
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a');
      if (!a) return;
      var href = a.getAttribute('href') || '';
      if (a.target === '_blank' || a.hasAttribute('download')) return;
      if (href.charAt(0) === '#' || href.indexOf('mailto:') === 0 || href.indexOf('javascript:') === 0) return;
      if (href.indexOf('http') === 0 && href.indexOf(location.host) === -1) return;
      if (a.hasAttribute('data-noveil')) return;
      e.preventDefault();
      veil.classList.add('show');
      setTimeout(function () { location.href = a.href; }, 420);
    });
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

  function init() {
    initCursor();
    initSmooth();
    initReveal();
    initSplit();
    initSpotlight();
    initGallery();
    initTouchGallery();
    initNight();
    initFloat();
    initMagnetic();
    initRail();
    initVoices();
    initNav();
    initVeil();
    initCount();
    initToday();
    wireScroll();
    renderFloat();
    document.documentElement.classList.add('js-on');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
