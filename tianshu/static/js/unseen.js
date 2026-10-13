/* ============================================================================
   Unseen 风格 · 前端引擎（零依赖）
   软光标 / 滚动揭示 / 导航态 / 移动菜单 / 暗场光标流场 / 换页 veil
   ========================================================================== */
(function () {
  'use strict';
  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var FINE = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  /* ---------- 软光标 ---------- */
  function initCursor() {
    if (!FINE || REDUCE) return;
    var dot = document.querySelector('.cursor');
    var ring = document.querySelector('.cursor-ring');
    if (!dot || !ring) return;
    document.body.classList.add('has-cursor');
    var mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
    addEventListener('mousemove', function (e) { mx = e.clientX; my = e.clientY; }, { passive: true });
    function loop() {
      rx += (mx - rx) * 0.18; ry += (my - ry) * 0.18;
      dot.style.transform = 'translate(' + mx + 'px,' + my + 'px) translate(-50%,-50%)';
      ring.style.transform = 'translate(' + rx + 'px,' + ry + 'px) translate(-50%,-50%)';
      requestAnimationFrame(loop);
    }
    loop();
    document.addEventListener('mouseover', function (e) {
      if (e.target.closest('a,button,[data-cursor],input,textarea,select')) ring.classList.add('big');
    });
    document.addEventListener('mouseout', function (e) {
      if (e.target.closest('a,button,[data-cursor],input,textarea,select')) ring.classList.remove('big');
    });
    document.addEventListener('mousedown', function () { ring.style.opacity = '.5'; });
    document.addEventListener('mouseup', function () { ring.style.opacity = ''; });
  }

  /* ---------- 滚动揭示 ---------- */
  function initReveal() {
    if (REDUCE) { return; }
    var els = document.querySelectorAll('[data-reveal]');
    if (!('IntersectionObserver' in window) || !els.length) return;
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- 导航态 + 移动菜单 ---------- */
  function initNav() {
    var nav = document.getElementById('nav');
    if (nav) {
      var onScroll = function () { nav.classList.toggle('scrolled', window.scrollY > 24); };
      onScroll(); addEventListener('scroll', onScroll, { passive: true });
    }
    var burger = document.getElementById('burger');
    var links = document.getElementById('navLinks');
    if (burger && links) {
      burger.addEventListener('click', function () { links.classList.toggle('open'); });
      links.addEventListener('click', function (e) { if (e.target.tagName === 'A') links.classList.remove('open'); });
    }
  }

  /* ---------- 暗场光标流场（2D canvas，稳健） ---------- */
  function initField() {
    var cv = document.querySelector('.band__canvas');
    if (!cv || REDUCE) return;
    var ctx = cv.getContext('2d');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var W, H, pts;
    function resize() {
      var r = cv.getBoundingClientRect();
      W = cv.width = Math.max(1, r.width * dpr); H = cv.height = Math.max(1, r.height * dpr);
      var n = Math.min(120, Math.round(W * H / 16000));
      pts = [];
      for (var i = 0; i < n; i++) pts.push({ x: Math.random() * W, y: Math.random() * H, vx: 0, vy: 0, a: .15 + Math.random() * .5 });
    }
    resize(); addEventListener('resize', resize, { passive: true });
    var mx = -9999, my = -9999;
    cv.parentElement.addEventListener('mousemove', function (e) {
      var r = cv.getBoundingClientRect(); mx = (e.clientX - r.left) * dpr; my = (e.clientY - r.top) * dpr;
    }, { passive: true });
    cv.parentElement.addEventListener('mouseleave', function () { mx = -9999; my = -9999; });
    var t = 0;
    function step() {
      t += 0.006;
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i];
        var ang = (Math.sin(p.x * 0.0016 + t) + Math.cos(p.y * 0.0016 - t)) * 1.7;
        p.vx += Math.cos(ang) * 0.06; p.vy += Math.sin(ang) * 0.06;
        var dx = mx - p.x, dy = my - p.y, d2 = dx * dx + dy * dy;
        if (d2 < 260 * 260 * dpr * dpr) {
          var f = (1 - Math.sqrt(d2) / (260 * dpr)) * 0.9;
          p.vx -= (dx / (Math.sqrt(d2) + 1)) * f; p.vy -= (dy / (Math.sqrt(d2) + 1)) * f;
        }
        p.vx *= 0.94; p.vy *= 0.94;
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x += W; if (p.x > W) p.x -= W; if (p.y < 0) p.y += H; if (p.y > H) p.y -= H;
        var accent = (i % 5 === 0);
        ctx.beginPath();
        ctx.fillStyle = accent ? 'rgba(217,119,46,' + p.a + ')' : 'rgba(241,234,223,' + (p.a * 0.5) + ')';
        ctx.arc(p.x, p.y, (accent ? 1.6 : 1.1) * dpr, 0, 6.283);
        ctx.fill();
      }
      requestAnimationFrame(step);
    }
    step();
  }

  /* ---------- 换页 veil ---------- */
  function initVeil() {
    if (REDUCE) return;
    var veil = document.querySelector('.veil');
    if (!veil) return;
    document.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (!a) return;
      var href = a.getAttribute('href') || '';
      if (a.target === '_blank' || a.hasAttribute('download') || href.charAt(0) === '#' || href.indexOf('mailto:') === 0) return;
      if (href.indexOf('http') === 0 && href.indexOf(location.host) === -1) return;
      if (a.hasAttribute('data-noveil')) return;
      e.preventDefault();
      veil.classList.add('show');
      setTimeout(function () { location.href = a.href; }, 460);
    });
  }

  /* ---------- 数字滚动（hero 统计） ---------- */
  function initCount() {
    if (REDUCE) return;
    var els = document.querySelectorAll('[data-count]');
    if (!els.length || !('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target, to = parseFloat(el.getAttribute('data-count')) || 0, s = 0, st = +new Date();
        (function tick() {
          var k = Math.min(1, (+new Date() - st) / 900);
          el.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))).toLocaleString();
          if (k < 1) requestAnimationFrame(tick);
        })();
        io.unobserve(el);
      });
    }, { threshold: 0.6 });
    els.forEach(function (el) { io.observe(el); });
  }

  function init() {
    initCursor(); initReveal(); initNav(); initField(); initVeil(); initCount();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
