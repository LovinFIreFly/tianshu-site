/* ============================================================================
   Unseen · 谢幕「暗场余烬」（canvas 2D，零依赖）

   ── 为什么单独写一个，而不是复用 unseen-light.js ──────────────────────────
   unseen-light.js 是**浅暖纸底**的散景光尘，它的整套参数都是为亮底定的：
   大半径（40–160px）、极低透明度（≤0.095）、"亮于或等于纸色"的暖调。
   搬到暗底上会完全看不见。

   而暗底的视觉语法是**反过来的**：
     · 亮底上，离散的微小暗点 = 灰尘（脏）；光滑连续的大亮面 = 干净。
     · **暗底上，离散的微小亮点 = 余烬/浮尘在光柱里（对）；光滑的大亮面 = 糊。**
   所以这一版是**小亮点**：半径 1.4–5.5px、透明度 0.18–0.55、缓慢上升 + 明暗闪烁，
   像散场之后剧场里还在飘的那点光。这是全站唯一一处敢用"小点"的地方 —— 因为底是黑的。

   参考：symphonyofvines（暗色沉浸 + 胶片颗粒）、unseen 的暗场案例。

   ── 三层内容 ──────────────────────────────────────────────────────────────
   1) 余烬（ember）：小亮点，缓慢上升 + 横向摆动 + 自身闪烁。
   2) 大晕（halo）：3–5 个 60–160px 的极淡暖光，只做景深，不抢戏。
   3) 光标扰动：指针附近的余烬**被吹散并提亮** —— 和亮底版"吸引+提亮"相反。
      暗场里手电扫过去，浮尘是被搅动的，不是被吸过来的。

   ── 性能红线（与 unseen-light.js 同一套，逐条守住）────────────────────────
   1) 绝不用 shadowBlur。用**预渲染软点精灵**（离屏 canvas 一次画好），每帧只 drawImage。
   2) 降档渲染 RENDER_SCALE=0.8。
   3) 数量按面积定并封顶；IntersectionObserver 离屏即停 rAF。
   4) prefers-reduced-motion：只画一帧静态图，不进循环。
   5) 事件一律原生 addEventListener，**不走 unseen.js 的 pOn**（pOff 会把它摘掉）。
   6) 换页后由 unseen.js 的 bootPage 重调 window.__emberInit()；init 幂等（WeakSet）。
   7) tick 首行检查 cv.isConnected，旧 canvas 被移除即自动停。

   挂载：<canvas class="curtain__ember" data-ember aria-hidden="true"></canvas>
   ========================================================================== */
(function () {
  'use strict';

  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var RENDER_SCALE = 0.8;      // 红线 2
  var AREA_DIV = 12000;        // 每多少 px² 一颗余烬（1440×480 的谢幕 ≈ 57 颗）
  var MIN_EMBERS = 40, MAX_EMBERS = 110;
  var HALO_N = 4;

  /* 暗场三档暖色：近白暖 / 琥珀 / 橙。都比背景亮 —— 暗底上"亮点"才成立 */
  var TINTS = ['255,232,205', '255,205,150', '232,150,90'];

  var bound = new WeakSet();
  var lives = [];

  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function rand(a, b) { return a + Math.random() * (b - a); }

  /* 预渲染软点精灵：中心实、到 0.34 就掉到 .22 —— 让它读成"光"而不是"圆点" */
  function sprite(rgb, size) {
    var c = document.createElement('canvas');
    c.width = c.height = size;
    var g = c.getContext('2d');
    var h = size / 2;
    var grd = g.createRadialGradient(h, h, 0, h, h, h);
    grd.addColorStop(0, 'rgba(' + rgb + ',1)');
    grd.addColorStop(0.34, 'rgba(' + rgb + ',.22)');
    grd.addColorStop(0.68, 'rgba(' + rgb + ',.06)');
    grd.addColorStop(1, 'rgba(' + rgb + ',0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, size, size);
    return c;
  }
  var SPR = null;

  function bind(cv) {
    if (bound.has(cv)) return;
    var ctx = cv.getContext && cv.getContext('2d', { alpha: true });
    if (!ctx) return;
    bound.add(cv);
    if (!SPR) SPR = TINTS.map(function (t) { return sprite(t, 64); });

    var W = 0, H = 0, E = [], HL = [];
    var raf = 0, last = 0, running = false, visible = true;
    /* 指针：目标值与缓动值分离（直接跟会跳） */
    var pmx = 0.5, pmy = 0.5, mx = 0.5, my = 0.5;
    var PULL_R = 240;

    function makeEmber(fromBottom) {
      return {
        x: Math.random(),                       // 0..1 归一化位置
        y: fromBottom ? rand(0.9, 1.15) : Math.random(),
        vy: rand(0.010, 0.030),                 // 每秒上升的归一化量（很慢）
        sway: rand(0.004, 0.016),               // 横向摆幅
        ph: Math.random() * Math.PI * 2,        // 摆动相位
        fl: rand(0.6, 1.9),                     // 闪烁频率
        r: rand(1.8, 6.5),                      // **小** —— 暗底上小点才对
        tint: (function () { var x = Math.random(); return x < 0.42 ? 0 : (x < 0.82 ? 1 : 2); })(),
        a: rand(0.18, 0.55)                     // 亮 —— 暗底上要看得见
      };
    }
    function makeHalo() {
      return { x: Math.random(), y: Math.random(), r: rand(70, 170),
               tint: Math.random() < 0.6 ? 1 : 0, a: rand(0.035, 0.075),
               ph: Math.random() * Math.PI * 2, sp: rand(0.12, 0.3) };
    }

    function reseed() {
      var rect = cv.getBoundingClientRect();
      var w = Math.max(1, rect.width || (cv.parentNode ? cv.parentNode.clientWidth : 1));
      var h = Math.max(1, rect.height || (cv.parentNode ? cv.parentNode.clientHeight : 1));
      var dpr = Math.min(window.devicePixelRatio || 1, 2) * RENDER_SCALE;
      W = w; H = h;
      cv.width = Math.max(1, Math.round(w * dpr));
      cv.height = Math.max(1, Math.round(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var n = clamp(Math.round((w * h) / AREA_DIV), MIN_EMBERS, MAX_EMBERS);
      E.length = 0; HL.length = 0;
      for (var i = 0; i < n; i++) E.push(makeEmber(false));
      for (var j = 0; j < HALO_N; j++) HL.push(makeHalo());
    }

    function draw(t) {
      var dt = last ? Math.min(2.5, (t - last) / 16.667) : 1;
      last = t;
      ctx.clearRect(0, 0, W, H);

      mx = lerp(mx, pmx, 0.07);
      my = lerp(my, pmy, 0.07);
      var mpx = mx * W, mpy = my * H;

      /* ---- 大晕：最底一层，只做景深 ---- */
      for (var q = 0; q < HL.length; q++) {
        var g = HL[q];
        var gx = g.x * W + Math.sin(t * 0.00016 * g.sp + g.ph) * 26;
        var gy = g.y * H + Math.cos(t * 0.00013 * g.sp + g.ph) * 20;
        var ga = g.a * (0.7 + 0.3 * Math.sin(t * 0.00025 * g.sp + g.ph));
        ctx.globalAlpha = clamp(ga, 0, 0.5);
        ctx.drawImage(SPR[g.tint], gx - g.r, gy - g.r, g.r * 2, g.r * 2);
      }

      /* ---- 余烬 ---- */
      for (var i = 0; i < E.length; i++) {
        var e = E[i];
        e.y -= e.vy * dt * 0.0016;                 // 缓慢上升
        if (e.y < -0.08) {                          // 飘出顶部就从底部回来（循环）
          var nw = makeEmber(true);
          e.x = nw.x; e.y = nw.y; e.vy = nw.vy; e.sway = nw.sway; e.ph = nw.ph;
          e.fl = nw.fl; e.r = nw.r; e.tint = nw.tint; e.a = nw.a;
        }
        var X = e.x * W + Math.sin(t * 0.0006 * e.fl + e.ph) * e.sway * W;
        var Y = e.y * H;

        var a = e.a * (0.55 + 0.45 * Math.sin(t * 0.0022 * e.fl + e.ph));   // 闪烁

        /* 光标扰动：暗场里手电扫过，浮尘被搅动 —— 往外推开并提亮 */
        var dx = X - mpx, dy = Y - mpy;
        var d2 = dx * dx + dy * dy;
        if (d2 < PULL_R * PULL_R && d2 > 0.01) {
          var f = 1 - Math.sqrt(d2) / PULL_R;
          a *= (1 + 0.9 * f);
          var inv = 1 / Math.sqrt(d2);
          X += dx * inv * 26 * f;                  // 推开（不是吸引）
          Y += dy * inv * 26 * f;
        }
        if (a <= 0.01) continue;
        var rad = e.r * (0.85 + 0.3 * Math.sin(t * 0.0018 * e.fl + e.ph));
        ctx.globalAlpha = a > 0.85 ? 0.85 : a;
        ctx.drawImage(SPR[e.tint], X - rad, Y - rad, rad * 2, rad * 2);
      }
      ctx.globalAlpha = 1;
    }

    function tick(t) {
      if (!cv.isConnected) { stop(); return; }      // 红线 7
      raf = requestAnimationFrame(tick);
      if (!visible || document.hidden) { last = 0; return; }
      draw(t);
    }
    function start() { if (running || REDUCE) return; running = true; last = 0; raf = requestAnimationFrame(tick); }
    function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }

    /* 事件：红线 5，全部原生 */
    window.addEventListener('pointermove', function (ev) {
      var r = cv.getBoundingClientRect();
      /* 只对**本块**内的指针位置做归一化（首屏那版用的是视口，谢幕在页尾，用视口会全错） */
      pmx = (ev.clientX - r.left) / Math.max(1, r.width);
      pmy = (ev.clientY - r.top) / Math.max(1, r.height);
    }, { passive: true });

    var rt = 0;
    function onResize() {
      clearTimeout(rt);
      rt = setTimeout(function () { reseed(); if (REDUCE) draw(0); }, 140);
    }
    window.addEventListener('resize', onResize, { passive: true });
    window.addEventListener('orientationchange', onResize, { passive: true });
    document.addEventListener('visibilitychange', function () { last = 0; });

    if (window.IntersectionObserver) {
      var io = new IntersectionObserver(function (es) {
        for (var i = 0; i < es.length; i++) visible = es[i].isIntersecting;
        if (visible) start(); else stop();
      }, { rootMargin: '140px' });
      io.observe(cv);
    } else {
      visible = true;
    }

    reseed();
    if (REDUCE) draw(0); else start();
    lives.push({ stop: stop });
  }

  /* 主入口：幂等。换页后由 unseen.js 的 bootPage 重调。 */
  window.__emberInit = function () {
    var list = document.querySelectorAll('[data-ember]');
    for (var i = 0; i < list.length; i++) bind(list[i]);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { window.__emberInit(); });
  } else {
    window.__emberInit();
  }
})();
