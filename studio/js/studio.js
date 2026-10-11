/* ════════════════════════════════════════════════════════════════
   天枢 · STUDIO（四代）引擎 —— 原生 JS，遵循 CodeBuddy-hy3 九轮法
   性能红线：只用 transform / opacity；ScrollTrigger 接管滚动；rAF 缓存
   ════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var REDUCE = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var HOVER  = window.matchMedia && matchMedia('(hover: hover)').matches;
  var MOBILE = window.matchMedia && matchMedia('(max-width: 768px)').matches;

  /* ════════ 本子数据（前端展示用，真实下单/拼车跳回天枢 /car、/scripts）════════ */
  var SCRIPTS = [
    { t: '雾起双龙',   c: '硬核', g: ['#e07a5f', '#3d405b'] },
    { t: '盛夏的蝉鸣', c: '情感', g: ['#81b29a', '#f2cc8f'] },
    { t: '欢乐撕逼局', c: '欢乐', g: ['#f2cc8f', '#b56576'] },
    { t: '血色晚宴',   c: '恐怖', g: ['#6d597a', '#b56576'] },
    { t: '孤岛回声',   c: '恐怖', g: ['#468faf', '#2a9d8f'] },
    { t: '机械之心',   c: '硬核', g: ['#3d405b', '#81b29a'] }
  ];

  /* ════════ 平滑滚动 + ScrollTrigger 桥接（第五章）════════ */
  var lenis = null;
  if (!REDUCE && window.Lenis) {
    lenis = new Lenis({ lerp: 0.08 });
    if (window.ScrollTrigger) {
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
      gsap.ticker.lagSmoothing(0);
    } else {
      (function raf(t) { lenis.raf(t); requestAnimationFrame(raf); })(0);
    }
  }
  function scrollToEl(el) {
    if (lenis) lenis.scrollTo(el, { offset: -80 });
    else el.scrollIntoView({ behavior: REDUCE ? 'auto' : 'smooth' });
  }

  /* ════════ 锚点平滑滚动（不白屏跳转）════════ */
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var id = a.getAttribute('href');
      if (id.length < 2) return;
      var el = document.querySelector(id);
      if (!el) return;
      e.preventDefault();
      scrollToEl(el);
      var links = document.getElementById('navLinks');
      if (links) links.classList.remove('is-open');
    });
  });

  /* ════════ 导航：滚动加深 + 汉堡菜单（第五章 / 第九章）════════ */
  var nav = document.getElementById('nav');
  function onScrollNav() {
    if (window.scrollY > 50) nav.classList.add('is-scrolled');
    else nav.classList.remove('is-scrolled');
  }
  window.addEventListener('scroll', onScrollNav, { passive: true });
  onScrollNav();

  var burger = document.getElementById('burger');
  var navLinks = document.getElementById('navLinks');
  if (burger && navLinks) {
    burger.addEventListener('click', function () { navLinks.classList.toggle('is-open'); });
  }

  /* ════════ 加载遮罩（第七章）════════ */
  var loader = document.getElementById('loader'),
      num = document.getElementById('loadNum'),
      bar = document.getElementById('loadBar');
  var pct = 0;
  var iv = setInterval(function () {
    pct += Math.random() * 16 + 6;
    if (pct >= 100) { pct = 100; clearInterval(iv); finish(); }
    if (num) num.textContent = Math.floor(pct);
    if (bar) bar.style.width = pct + '%';
  }, 90);
  function finish() {
    setTimeout(function () { if (loader) loader.classList.add('is-done'); }, 320);
    if (window.ScrollTrigger) setTimeout(ScrollTrigger.refresh, 400);
  }

  /* ════════ 自定义光标（第七章）════════ */
  if (HOVER && !REDUCE) {
    document.body.classList.add('cursor-on');
    var dot = document.getElementById('curDot'),
        ring = document.getElementById('curRing');
    var mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
    window.addEventListener('mousemove', function (e) {
      mx = e.clientX; my = e.clientY;
      dot.style.left = mx + 'px'; dot.style.top = my + 'px';
    });
    (function loop() {
      rx += (mx - rx) * 0.15; ry += (my - ry) * 0.15;
      ring.style.left = rx + 'px'; ring.style.top = ry + 'px';
      requestAnimationFrame(loop);
    })();
    document.querySelectorAll('a,button,.sphere,.card').forEach(function (el) {
      el.addEventListener('mouseenter', function () { ring.classList.add('is-hover'); });
      el.addEventListener('mouseleave', function () { ring.classList.remove('is-hover'); });
    });
  }

  /* ════════ 鼠标视差：Hero 光晕（第五章，移动端禁用）════════ */
  if (HOVER && !REDUCE) {
    var glow = document.getElementById('glow');
    var gx = 0, gy = 0, tx = 0, ty = 0;
    window.addEventListener('mousemove', function (e) {
      tx = (e.clientX / innerWidth - 0.5) * 40;
      ty = (e.clientY / innerHeight - 0.5) * 40;
    });
    (function gl() {
      gx += (tx - gx) * 0.06; gy += (ty - gy) * 0.06;
      if (glow) glow.style.transform = 'translate(calc(-50% + ' + gx + 'px),' + gy + 'px)';
      requestAnimationFrame(gl);
    })();
  }

  /* ════════ 3D 线框球画廊（unseen 签名，纯 CSS 3D + 原生 JS）════════ */
  function buildSphere() {
    var scope = document.getElementById('sphere');
    var group = document.getElementById('sphereGroup');
    if (!scope || !group) return;
    var n = SCRIPTS.length;
    var R = Math.min(200, scope.clientWidth * 0.46);
    var golden = Math.PI * (3 - Math.sqrt(5));
    var pos = [];
    for (var i = 0; i < n; i++) {
      var y = 1 - (i / (n - 1)) * 2;
      var r = Math.sqrt(Math.max(0, 1 - y * y));
      var th = golden * i;
      pos.push({ x: Math.cos(th) * r * R, y: y * R, z: Math.sin(th) * r * R });
    }
    pos.forEach(function (p, i) {
      var card = document.createElement('a');
      card.className = 'sphere__card';
      card.href = '/studio/scripts';
      card.innerHTML = '<div class="img" style="position:absolute;inset:0;background:linear-gradient(135deg,' +
        SCRIPTS[i].g[0] + ',' + SCRIPTS[i].g[1] + ')"></div><b>' + SCRIPTS[i].t + '</b>';
      group.appendChild(card);
    });
    var cards = [].slice.call(group.querySelectorAll('.sphere__card'));

    // 线框球笼（8 经线 + 2 纬线）
    var wire = document.createElement('div');
    wire.className = 'sphere__wire';
    for (var k = 0; k < 8; k++) {
      var ring = document.createElement('div');
      ring.className = 'sphere__ring';
      ring.style.width = ring.style.height = (2 * R) + 'px';
      ring.style.marginLeft = ring.style.marginTop = (-R) + 'px';
      ring.style.transform = 'rotateY(' + (k * 22.5) + 'deg)';
      wire.appendChild(ring);
    }
    [-0.55, 0.55].forEach(function (sy) {
      var rr = R * Math.sqrt(Math.max(0, 1 - sy * sy));
      var lat = document.createElement('div');
      lat.className = 'sphere__ring';
      lat.style.width = (2 * rr) + 'px';
      lat.style.height = (2 * R) + 'px';
      lat.style.marginLeft = (-rr) + 'px';
      lat.style.marginTop = (-R) + 'px';
      lat.style.transform = 'rotateX(90deg) translateZ(' + (sy * R) + 'px)';
      wire.appendChild(lat);
    });
    group.appendChild(wire);

    var st = { RX: -0.2, RY: 0.4, tRX: -0.2, tRY: 0.4, vX: 0, vY: 0, drag: false, lx: 0, ly: 0, moved: 0 };
    function down(e) {
      st.drag = true; st.vX = 0; st.vY = 0; st.moved = 0;
      var p = e.touches ? e.touches[0] : e; st.lx = p.clientX; st.ly = p.clientY;
      scope.style.cursor = 'grabbing';
    }
    function move(e) {
      if (!st.drag) return;
      var p = e.touches ? e.touches[0] : e;
      var dx = p.clientX - st.lx, dy = p.clientY - st.ly;
      st.lx = p.clientX; st.ly = p.clientY; st.moved += Math.abs(dx) + Math.abs(dy);
      st.tRY += dx * 0.005; st.tRX += dy * 0.004;
      st.tRX = Math.max(-1.2, Math.min(1.2, st.tRX));
      st.vY = dx * 0.005; st.vX = dy * 0.004;
    }
    function up() {
      st.drag = false; scope.style.cursor = '';
      if (st.moved > 6) { scope._sup = true; setTimeout(function () { scope._sup = false; }, 80); }
    }
    scope.addEventListener('pointerdown', down);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    scope.addEventListener('click', function (e) { if (scope._sup) { e.preventDefault(); e.stopPropagation(); } }, true);

    function frame() {
      if (!st.drag) {
        st.tRY += st.vY; st.tRX += st.vX;
        st.tRX = Math.max(-1.2, Math.min(1.2, st.tRX));
        st.vY *= 0.92; st.vX *= 0.92;
        st.tRY += 0.0015; // 永不停止的微自旋
      }
      st.RX += (st.tRX - st.RX) * 0.08; // lerp 滞后跟随
      st.RY += (st.tRY - st.RY) * 0.08;
      group.style.transform = 'rotateX(' + st.RX + 'rad) rotateY(' + st.RY + 'rad)';
      for (var i = 0; i < cards.length; i++) {
        var p = pos[i];
        // 绕 Y 再绕 X 旋转（billboarding 反向令卡片始终朝向相机）
        var cy = Math.cos(st.RY), sy = Math.sin(st.RY);
        var x1 = p.x * cy + p.z * sy, z1 = -p.x * sy + p.z * cy;
        var cx = Math.cos(st.RX), sx = Math.sin(st.RX);
        var y2 = p.y * cx - z1 * sx, z2 = p.y * sx + z1 * cx;
        var t = (z2 + R) / (2 * R); t = t < 0 ? 0 : (t > 1 ? 1 : t);
        cards[i].style.transform = 'translate3d(' + p.x.toFixed(1) + 'px,' + p.y.toFixed(1) + 'px,' + p.z.toFixed(1) +
          'px) rotateY(' + (-st.RY) + 'rad) rotateX(' + (-st.RX) + 'rad)';
        cards[i].style.opacity = (0.25 + 0.75 * t).toFixed(3);
        cards[i].style.filter = 'blur(' + ((1 - t) * 3).toFixed(2) + 'px)';
        cards[i].style.zIndex = (100 + Math.round(t * 100)).toString();
      }
      requestAnimationFrame(frame);
    }
    if (!REDUCE) frame();
  }
  if (MOBILE) {
    var fb = document.getElementById('sphereFallback');
    if (fb) SCRIPTS.forEach(function (p, i) {
      var c = document.createElement('div');
      c.className = 'sphere__card';
      c.innerHTML = '<div class="img" style="position:absolute;inset:0;background:linear-gradient(135deg,' +
        p.g[0] + ',' + p.g[1] + ')"></div><b>' + p.t + '</b>';
      fb.appendChild(c);
    });
  } else {
    buildSphere();
  }

  /* ════════ 本子卡片注入 + 筛选（第三章 hubtown，第八章流畅过渡）════════ */
  var grid = document.getElementById('grid');
  if (grid) {
    SCRIPTS.forEach(function (p, i) {
      var a = document.createElement('a');
      a.className = 'card';
      a.href = '/studio/scripts';
      a.setAttribute('data-cat', p.c);
      a.setAttribute('data-tilt', '7');
      a.innerHTML =
        '<div class="card__media"><div class="img" style="background:linear-gradient(135deg,' + p.g[0] + ',' + p.g[1] + ')"></div>' +
        '<span class="tag">' + p.c + '</span></div>' +
        '<div class="card__body"><h3>' + p.t + '</h3><p>《' + p.t + '》· ' + p.c + '向代表作，点进去挑今天这局。</p></div>';
      grid.appendChild(a);
    });

    var filter = document.getElementById('filter');
    filter.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      filter.querySelectorAll('button').forEach(function (x) { x.classList.remove('is-on'); });
      b.classList.add('is-on');
      var f = b.getAttribute('data-f');
      grid.querySelectorAll('.card').forEach(function (c) {
        var show = f === 'all' || c.getAttribute('data-cat') === f;
        c.classList.toggle('is-hide', !show);
      });
    });

    /* ════════ 鼠标跟随倾斜卡片（第八章 unseen，最大 8°）════════ */
    if (HOVER && !REDUCE) {
      grid.querySelectorAll('.card').forEach(function (card) {
        var max = parseFloat(card.getAttribute('data-tilt')) || 8;
        card.addEventListener('pointermove', function (e) {
          var r = card.getBoundingClientRect();
          var px = (e.clientX - r.left) / r.width - 0.5;
          var py = (e.clientY - r.top) / r.height - 0.5;
          card.style.transform = 'perspective(820px) rotateY(' + (px * max) + 'deg) rotateX(' + (-py * max) + 'deg) translateZ(6px)';
        });
        card.addEventListener('pointerleave', function () {
          card.style.transform = '';
        });
      });
    }
  }

  /* ════════ Reveal 动画（第五章：y40→0, opacity, stagger）════════ */
  if (window.gsap && window.ScrollTrigger) {
    gsap.registerPlugin(ScrollTrigger);
    gsap.from('[data-hero]', { opacity: 0, y: 50, duration: 1, ease: 'power3.out', stagger: 0.12, delay: 1.1 });
    gsap.utils.toArray('[data-reveal]').forEach(function (el) {
      gsap.from(el, {
        opacity: 0, y: 40, duration: 0.8, ease: 'power3.out',
        scrollTrigger: { trigger: el, start: 'top 85%' }
      });
    });

    /* ════════ 数字滚动（第七章）════════ */
    gsap.utils.toArray('[data-count]').forEach(function (el) {
      var end = parseFloat(el.getAttribute('data-count')) || 0;
      var obj = { v: 0 };
      gsap.to(obj, {
        v: end, duration: 1.6, ease: 'power2.out',
        scrollTrigger: { trigger: el, start: 'top 90%' },
        onUpdate: function () { el.textContent = Math.round(obj.v); }
      });
    });
  }
})();
