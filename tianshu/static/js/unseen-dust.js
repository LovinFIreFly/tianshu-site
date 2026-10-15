/* ============================================================================
   Unseen · 首屏「光中的浮尘」粒子场（canvas 2D，零依赖）

   为什么单独一个文件：unseen.js 已经贴近体积预算，粒子场是自成一体的东西，
   分文件既能独立测，也方便哪天不想要了直接摘掉一个 <script>。

   做的是**真粒子**，不是装饰：
     · 3D 透视 —— 粒子活在一个深度盒里，按 z 投影（远的又小又淡、近的又大又亮），
       产生真实的前后景深，而不是平面撒点。
     · 向相机飞行 —— z 持续减小、到近处循环回深处 → 人一直在"穿过尘埃"。
     · 指针吹散 —— 靠近光标的粒子被推开、同时变淡（学 kodeimmersive 的鼠标-内容互动）。
     · 滚动穿越 —— 滚轮速度越大，飞得越快（和 .stage__scene 的「星球展开」同向叠加）。
     · 光束密度 —— 离光斑中心越远越稀，把它和那束圆光焊成同一个构图。

   性能红线（这里踩过坑，逐条守住）：
     1) 绝不用 shadowBlur —— 那是 2D canvas 的头号掉帧源。改成**预渲染两张软点精灵**
        （一次性画好径向渐变），每帧只 drawImage 缩放贴图。
     2) 分辨率降档渲染（RENDER_SCALE），CSS 放大后肉眼几乎无差，填充率省一半以上。
     3) 粒子数按视口面积算，260–900 之间封顶；离屏 / 切标签页就停 rAF。
     4) 尊重 prefers-reduced-motion：只画一帧静态图，不进循环。

   挂载：<canvas class="stage__dust" data-dust aria-hidden="true"></canvas>
   ========================================================================== */
(function () {
  'use strict';

  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var RENDER_SCALE = 0.8;          // 渲染分辨率系数（见性能红线 2）
  var FOV = 900;                   // 透视焦距：控制近大远小的强度
  var DEPTH = 1700;                // 深度盒的 z 范围
  var BEAM = { x: 0.63, y: 0.40 }; // 光斑中心 —— 必须与 .stage__scene 的 mask 同源
  var DENSITY = 1500;              // 面积除数：越小越密
  var MAX_PARTICLES = 2000;

  var bound = new WeakSet();       // 幂等：同一个 canvas 只绑一次
  var live = null;                 // 当前在跑的实例（换页时先停旧的）

  /* ---- 预渲染软点精灵（性能红线 1）---- */
  function sprite(rgb, size) {
    var c = document.createElement('canvas');
    c.width = c.height = size;
    var g = c.getContext('2d');
    var h = size / 2;
    var grd = g.createRadialGradient(h, h, 0, h, h, h);
    grd.addColorStop(0, 'rgba(' + rgb + ',1)');
    grd.addColorStop(0.42, 'rgba(' + rgb + ',.40)');
    grd.addColorStop(1, 'rgba(' + rgb + ',0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, size, size);
    return c;
  }
  var SPR_DUST = null, SPR_WARM = null;

  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }

  function init() {
    var cv = document.querySelector('[data-dust]');
    if (!cv || bound.has(cv)) return;
    var ctx = cv.getContext && cv.getContext('2d', { alpha: true });
    if (!ctx) return;
    bound.add(cv);
    if (!SPR_DUST) { SPR_DUST = sprite('96,78,68', 24); SPR_WARM = sprite('196,118,66', 32); }

    /* 前一个实例（换页前的旧 canvas）先彻底停掉，避免两个 rAF 对着跑 */
    if (live) live.stop();
    var inst = { stop: stop, cv: cv };
    live = inst;

    var W = 0, H = 0, P = [];
    var raf = 0, last = 0, running = false, visible = true;

    /* 指针（归一化 0..1）+ 缓动值：不直接跟随，走 lerp —— 直接跟会生硬 */
    var pmx = 0.5, pmy = 0.5, mx = 0.5, my = 0.5;
    var scrollPrev = 0, warp = 0;

    function seedOne() {
      return {
        x: Math.random() * 2 - 1,
        y: Math.random() * 2 - 1,
        z: 40 + Math.random() * DEPTH,
        /* 半径走平方分布：大部分是很细的"灰"，少量偏大的颗粒 —— 均匀分布看起来
           像撒糖粒，平方分布才像真实的浮尘（细的多、粗的少）。 */
        r: 0.32 + Math.random() * Math.random() * 1.5,
        warm: Math.random() < 0.11,          // 约 1/9 是暖光点（砖红/琥珀方向）
        ph: Math.random() * Math.PI * 2,     // 摆动相位
        sp: 0.5 + Math.random() * 1.1        // 摆动速度
      };
    }

    function reseed() {
      var rect = cv.getBoundingClientRect();
      var w = Math.max(1, rect.width || (cv.parentNode ? cv.parentNode.clientWidth : 1));
      var h = Math.max(1, rect.height || (cv.parentNode ? cv.parentNode.clientHeight : 1));
      var dpr = Math.min(window.devicePixelRatio || 1, 2) * RENDER_SCALE;
      W = w; H = h;
      cv.width = Math.max(1, Math.round(w * dpr));
      cv.height = Math.max(1, Math.round(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // 之后全部按 CSS px 画
      /* 粒子数按面积定（性能红线 3） */
      var n = clamp(Math.round((w * h) / DENSITY), 420, MAX_PARTICLES);
      P.length = 0;
      for (var i = 0; i < n; i++) P.push(seedOne());
    }

    function draw(t) {
      var dt = last ? Math.min(2.5, (t - last) / 16.667) : 1;   // 归一化到 60fps 步长
      last = t;
      ctx.clearRect(0, 0, W, H);

      mx = lerp(mx, pmx, 0.06);
      my = lerp(my, pmy, 0.06);
      var ox = (mx - 0.5), oy = (my - 0.5);
      var cx = W * 0.5, cy = H * 0.5;
      var sx = W * 0.62, sy = H * 0.62;       // 投影后的铺展半径
      var mpx = mx * W, mpy = my * H;
      var falloffR = Math.max(W, H) * 0.78;
      var bxx = W * BEAM.x, byy = H * BEAM.y;
      /* 滚动穿越：滚轮越快飞得越快，随后自己衰减回常速 */
      var sy2 = window.scrollY || 0;
      var v = Math.abs(sy2 - scrollPrev);
      scrollPrev = sy2;
      warp = lerp(warp, clamp(v / 5, 0, 5.5), 0.12);
      var speed = 0.85 + warp;

      for (var i = 0; i < P.length; i++) {
        var p = P[i];
        p.z -= speed * dt;
        if (p.z <= 1) {                       // 飞到镜头前 → 循环回最深处
          p.z += DEPTH;
          p.x = Math.random() * 2 - 1;
          p.y = Math.random() * 2 - 1;
        }
        var wob = t * 0.0006;
        var wx = p.x + ox * 0.34 + Math.sin(wob * p.sp + p.ph) * 0.022;
        var wy = p.y + oy * 0.34 + Math.cos(wob * p.sp * 0.83 + p.ph) * 0.022;
        var s = FOV / (FOV + p.z);
        var X = cx + wx * sx * s;
        var Y = cy + wy * sy * s;
        if (X < -48 || X > W + 48 || Y < -48 || Y > H + 48) continue;

        var a = (p.warm ? 0.78 : 0.34) * clamp(s * 1.35, 0.08, 1);
        /* 光束密度：离光斑中心越远越稀。指数 >1 让"光柱"更明确 —— 中心和边缘
           拉开差距，观感才是"一束光里的尘"，而不是"整页均匀撒了点"。 */
        var bdx = X - bxx, bdy = Y - byy;
        var bd = Math.sqrt(bdx * bdx + bdy * bdy) / falloffR;
        var near = clamp(1 - bd, 0, 1);
        a *= (0.14 + 0.86 * near * near);

        /* 指针吹散：近处粒子被推开并变淡（学 kodeimmersive 的鼠标-内容互动） */
        var ddx = X - mpx, ddy = Y - mpy;
        var dd = ddx * ddx + ddy * ddy;
        if (dd < 30000) {
          var f = 1 - dd / 30000;
          X += ddx * 0.5 * f;
          Y += ddy * 0.5 * f;
          a *= (1 - 0.55 * f);
        }
        if (a <= 0.012) continue;

        var rad = p.r * s * (p.warm ? 11 : 5.2);
        if (rad < 0.22) rad = 0.22;
        ctx.globalAlpha = a > 1 ? 1 : a;
        ctx.drawImage(p.warm ? SPR_WARM : SPR_DUST, X - rad, Y - rad, rad * 2, rad * 2);
      }
      ctx.globalAlpha = 1;
    }

    function tick(t) {
      if (!cv.isConnected) { stop(); return; }     // 换页后节点已被移除 → 自动停
      raf = requestAnimationFrame(tick);
      if (!visible || document.hidden) { last = 0; return; }
      draw(t);
    }
    function start() {
      if (running || REDUCE) return;
      running = true; last = 0;
      raf = requestAnimationFrame(tick);
    }
    function stop() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    }
    inst.stop = stop;

    /* ---- 事件：全部用原生 addEventListener / 直接赋值 ----
       这里**绝不能**走 unseen.js 的 pOn：那是按页登记的监听表，换页时会被 pOff 一并摘掉，
       粒子场就静默死掉（#73 进度条踩过同一个坑）。 */
    window.addEventListener('pointermove', function (e) {
      pmx = e.clientX / Math.max(1, window.innerWidth);
      pmy = e.clientY / Math.max(1, window.innerHeight);
    }, { passive: true });

    var rt = 0;
    function onResize() {
      clearTimeout(rt);
      rt = setTimeout(function () { reseed(); if (REDUCE) draw(0); }, 140);
    }
    window.addEventListener('resize', onResize, { passive: true });
    window.addEventListener('orientationchange', onResize, { passive: true });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { last = 0; } else { last = 0; }
    });

    /* 离屏停摆：首屏滚过去之后不该还在烧 GPU */
    if (window.IntersectionObserver) {
      var io = new IntersectionObserver(function (es) {
        for (var i = 0; i < es.length; i++) visible = es[i].isIntersecting;
        if (visible) start(); else stop();
      }, { rootMargin: '120px' });
      io.observe(cv);
    }

    reseed();
    if (REDUCE) { draw(0); } else { start(); }
  }

  /* 首帧：DOM 就绪即建。换页后由 unseen.js 的 bootPage 再调一次（幂等）。 */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  window.__dustInit = init;
})();
