/* ============================================================================
   Unseen · 首屏「散景光尘」（canvas 2D，零依赖）

   ── 为什么从"浮尘粒子"改成这个 ──────────────────────────────────────────────
   上一版是**小颗粒**（半径 0.3–1.8px、混了一批暗色 rgb(96,78,68)）。
   在浅暖纸底（oklch 96.5% 0.013 78 ≈ rgb(246,239,231)）上，暗色小点在物理上
   就是"灰尘"的视觉语法 —— 用户第一反应是「太显脏」。**干净的语汇不是"点"，
   是"面"**：大半径、极低透明度、边缘完全化开的软光斑（散景），加上极少的
   1px 发丝光丝。所以这一版：
     · 删掉全部暗色小颗粒（脏的唯一来源）
     · 只留三种"亮于或等于纸色"的暖调：暖白 / 琥珀 / 浅砖
     · 半径放大 30–80 倍（40–160px），透明度降到 0.025–0.075
     · 位移放慢（不再是"向相机飞行"，改成极缓漂移 + 呼吸）
   光滑连续的低透明大面 = 干净；离散的微小硬点 = 脏。区别就在这。

   ── 三层内容 ──────────────────────────────────────────────────────────────
   1) 大光斑（bokeh）：40–160px 软圆，慢漂移，呼吸式明暗。
   2) 发丝光丝（filament）：1px 宽、60–220px 长、极低透明的暖色斜线，极缓漂移。
   3) 光标增亮：指针靠近时光斑**被吸引并提亮**（不是被推开）—— 推开在软面上很怪，
      吸引+提亮才像"你走过去，那束光更亮了"，跟页面「一束光」的主题同源。

   ── 性能红线（踩过的坑，逐条守住）──────────────────────────────────────────
   1) 绝不用 shadowBlur —— 2D canvas 头号掉帧源。用**预渲染软点精灵**（一次性
      画好径向渐变到离屏 canvas），每帧只 drawImage 缩放贴图。
   2) 降档渲染 RENDER_SCALE=0.8，CSS 放大后肉眼无差，填充率省一半。
   3) 数量按面积定并封顶；IntersectionObserver 离屏即停 rAF。
   4) prefers-reduced-motion：只画一帧静态图，不进循环（CSS 不隐藏该层 ——
      WCAG 要的是"不要动"，不是"不要质感"）。
   5) 事件一律原生 addEventListener，**不走 unseen.js 的 pOn** —— pOn 的监听表
      会被换页时的 pOff 一并摘掉，这层会静默死掉（#73 进度条踩过同一个坑）。
   6) 换页后由 unseen.js 的 bootPage 重调 window.__lightInit()；本模块的 init
      **幂等**（WeakSet 记已绑 canvas，旧实例先 stop()）。
   7) tick 首行检查 cv.isConnected，旧 canvas 被移除即自动停。

   挂载：<canvas class="stage__bokeh" data-bokeh aria-hidden="true"></canvas>
   ========================================================================== */
(function () {
  'use strict';

  /* 用户开了"减弱动效"就只画一帧静态图 —— 先取一次系统偏好，后面全程复用 */
  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* 渲染分辨率系数：0.8 倍靠 CSS 放大，软光斑本来就模糊，肉眼分辨不出差别，
     但填充率直接省掉 36%（性能红线 2） */
  var RENDER_SCALE = 0.8;

  /* 光斑数量 = 视口面积 / 这个除数。越大越稀 */
  var AREA_DIV = 9000;
  /* 光斑数量上下限：太少就还是"空"，太多就腻 */
  var MIN_BLOBS = 26, MAX_BLOBS = 72;
  /* 光丝数量：它是"点缀"，必须少 —— 多了就成了斜纹布 */
  var MIN_LINES = 8, MAX_LINES = 18;

  /* 三种暖调（都在纸色同一色相家族里，绝不会读成灰/脏）。
     每一档 = [r,g,b]；alpha 由 JS 按深度和呼吸再乘一次 */
  var TINTS = [
    [236, 214, 190],   // 暖白：提亮纸面，最干净的一档
    [214, 158, 102],   // 琥珀：主要的那束光
    [190, 124, 86]     // 浅砖：跟 --accent 同族，收口用，数量最少
  ];

  /* 幂等标记：同一个 canvas 只绑一次（换页会换 canvas，所以用 WeakSet 而不是 flag） */
  var bound = new WeakSet();
  /* 当前在跑的实例：换页建新的之前，先把旧的彻底停掉，避免两个 rAF 对着跑 */
  var live = null;

  /* ---------- 工具：两个到处要用的数学小函数 ---------- */
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }          // 夹在 [a,b]
  function lerp(a, b, t) { return a + (b - a) * t; }                      // 线性插值

  /* ============================================================================
     预渲染软点精灵（性能红线 1 的核心）
     把一个"中心不透明、向外渐隐到全透明"的径向渐变**预先画进一张小离屏 canvas**，
     之后每帧只需要 drawImage 缩放它 —— 比每帧现算渐变快一个数量级，
     更是完全避开了 shadowBlur。
     rgb：颜色（"r,g,b" 字符串）；size：精灵边长（px）
     ========================================================================== */
  function sprite(rgb, size) {
    var c = document.createElement('canvas');          // 离屏画布
    c.width = c.height = size;                          // 正方形
    var g = c.getContext('2d');
    var h = size / 2;                                   // 圆心
    var grd = g.createRadialGradient(h, h, 0, h, h, h); // 圆心 → 边缘的径向渐变
    grd.addColorStop(0, 'rgba(' + rgb + ',1)');         // 圆心：满色
    /* 0.34 处就掉到 0.22 —— 让"实心部分"很小，绝大部分是化开的边。
       这一步决定了它看起来像"软光"而不是"圆点"，是干净与否的关键。 */
    grd.addColorStop(0.34, 'rgba(' + rgb + ',.22)');
    grd.addColorStop(0.68, 'rgba(' + rgb + ',.06)');    // 中段几乎没了
    grd.addColorStop(1, 'rgba(' + rgb + ',0)');         // 边缘全透明
    g.fillStyle = grd;
    g.fillRect(0, 0, size, size);                       // 铺满，得到一张软点
    return c;
  }

  var SPRITES = null;   // 三档颜色的软点精灵，首次 init 时建一次

  /* ============================================================================
     主入口：建实例。幂等 —— 同一个 canvas 重复调用直接返回。
     ========================================================================== */
  function init() {
    var cv = document.querySelector('[data-bokeh]');    // 找挂载点
    if (!cv || bound.has(cv)) return;                   // 没有 / 已绑过 → 走人
    var ctx = cv.getContext && cv.getContext('2d', { alpha: true });
    if (!ctx) return;                                   // 不支持 2D → 静默降级（首屏照常）
    bound.add(cv);
    if (!SPRITES) SPRITES = [sprite('236,214,190', 64), sprite('214,158,102', 64), sprite('190,124,86', 64)];

    if (live) live.stop();                              // 停掉上一个实例
    var inst = { stop: stop, cv: cv };                  // 实例对象（外部只需要 stop）
    live = inst;

    /* ---------- 尺寸与数据 ---------- */
    var W = 0, H = 0;          // CSS px 下的逻辑宽高
    var B = [];                // 光斑集合
    var L = [];                // 光丝集合
    var raf = 0;               // requestAnimationFrame 句柄
    var last = 0;              // 上一帧时间戳（用来算 dt）
    var running = false;       // 循环是否在跑
    var visible = true;        // 是否在视口内（IntersectionObserver 维护）

    /* 指针：pmx/pmy 是原始目标值（0..1 归一化），mx/my 是缓动后的值。
       必须缓动 —— 直接跟会让光斑跳，硬邦邦的。 */
    var pmx = 0.5, pmy = 0.5, mx = 0.5, my = 0.5;

    /* 滚动视差：上一帧的 scrollY，用来算位移增量 */
    var scrollPrev = 0;

    /* ------------------------------------------------------------------------
       造一个光斑。字段含义：
         bx,by   归一化的基准位置（-1..1），投影后乘视口铺展半径
         depth   0..1 的"深度感"：越大越靠前 → 越大越亮（模拟景深）
         r       半径系数
         tint    用哪一档颜色（0 暖白 / 1 琥珀 / 2 浅砖）
         ph/sp   呼吸与漂移的相位、速度（每个粒子错开，避免整齐划一）
       ---------------------------------------------------------------------- */
    function makeBlob() {
      return {
        bx: Math.random() * 2 - 1,
        by: Math.random() * 2 - 1,
        depth: 0.15 + Math.random() * 0.85,
        r: 0.45 + Math.random() * Math.random() * 1.35,   // 平方分布：小的多、大的少
        /* 颜色按权重抽：暖白 45% / 琥珀 40% / 浅砖 15% —— 浅砖最"重"，只做点缀 */
        tint: (function () { var x = Math.random(); return x < 0.45 ? 0 : (x < 0.85 ? 1 : 2); })(),
        ph: Math.random() * Math.PI * 2,
        sp: 0.24 + Math.random() * 0.5
      };
    }

    /* 造一根光丝：一条极细的暖色斜线，靠 angle 旋转、len 定长度 */
    function makeLine() {
      return {
        bx: Math.random() * 2 - 1,
        by: Math.random() * 2 - 1,
        depth: 0.2 + Math.random() * 0.8,
        len: 0.10 + Math.random() * 0.28,                 // 相对视口宽度的长度系数（少数很长 → 读作"光缝"）
        angle: -0.6 + Math.random() * 1.2,                // 弧度，整体偏"斜向上"
        tint: Math.random() < 0.55 ? 0 : 1,               // 暖白或琥珀，不用浅砖（会显沉）
        ph: Math.random() * Math.PI * 2,
        sp: 0.18 + Math.random() * 0.34
      };
    }

    /* ------------------------------------------------------------------------
       reseed：按当前视口重建画布尺寸与全部元素。窗口 resize 时也会走这里。
       ---------------------------------------------------------------------- */
    function reseed() {
      var rect = cv.getBoundingClientRect();                       // 拿 CSS 尺寸
      var w = Math.max(1, rect.width || (cv.parentNode ? cv.parentNode.clientWidth : 1));
      var h = Math.max(1, rect.height || (cv.parentNode ? cv.parentNode.clientHeight : 1));
      var dpr = Math.min(window.devicePixelRatio || 1, 2) * RENDER_SCALE;  // 红线 2
      W = w; H = h;
      cv.width = Math.max(1, Math.round(w * dpr));                 // 位图尺寸 = CSS × dpr
      cv.height = Math.max(1, Math.round(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);                      // 之后一律按 CSS px 作图
      var n = clamp(Math.round((w * h) / AREA_DIV), MIN_BLOBS, MAX_BLOBS);   // 红线 3
      var m = clamp(Math.round((w * h) / 34000), MIN_LINES, MAX_LINES);
      B.length = 0; L.length = 0;
      for (var i = 0; i < n; i++) B.push(makeBlob());
      for (var j = 0; j < m; j++) L.push(makeLine());
    }

    /* ------------------------------------------------------------------------
       单帧绘制。
       t：rAF 给的高精度时间戳（ms）
       ---------------------------------------------------------------------- */
    function draw(t) {
      /* dt 归一化到 60fps 的步长（1 = 一帧 16.67ms），并夹住 2.5 ——
         切后台再回来时 t 会跳很大，不夹住会让光斑瞬移。 */
      var dt = last ? Math.min(2.5, (t - last) / 16.667) : 1;
      last = t;

      ctx.clearRect(0, 0, W, H);                        // 每帧全清（画布是透明的）

      mx = lerp(mx, pmx, 0.05);                         // 指针缓动（比上一版更慢 → 更柔）
      my = lerp(my, pmy, 0.05);
      var ox = (mx - 0.5), oy = (my - 0.5);             // -0.5..0.5 的偏移量

      /* 滚动视差：把 scrollY 的增量转成一个极缓的纵向漂移（不再做"穿越"加速） */
      var sy = window.scrollY || 0;
      var dy = sy - scrollPrev;
      scrollPrev = sy;
      var drift = clamp(dy * 0.06, -3, 3);

      var cx = W * 0.5, cy = H * 0.5;                   // 投影中心
      var spanX = W * 0.66, spanY = H * 0.66;           // 铺展半径（0.66 让边缘留白）
      var mpx = mx * W, mpy = my * H;                   // 指针的屏幕坐标（CSS px）
      var pullR2 = 420 * 420;                           // 光标影响半径的平方（避免开根号）

      /* ===== 第一层：大光斑 ===== */
      for (var i = 0; i < B.length; i++) {
        var b = B[i];
        /* 缓漂移：两个不同频率的正弦叠加，避免看出周期 */
        var wob = t * 0.00022;
        var wx = b.bx + ox * 0.08 + Math.sin(wob * b.sp + b.ph) * 0.05;
        var wy = b.by + oy * 0.08 + Math.cos(wob * b.sp * 0.77 + b.ph) * 0.05 + drift * 0.004;
        /* 投影：depth 越大越靠前 → 位置更外扩、半径更大、越亮 */
        var X = cx + wx * spanX * (0.72 + b.depth * 0.42);
        var Y = cy + wy * spanY * (0.72 + b.depth * 0.42);

        /* 呼吸：每个光斑自己慢慢明暗，幅度 ±26% */
        var breath = 0.74 + 0.26 * Math.sin(t * 0.00034 * b.sp + b.ph);

        /* 基础透明度：上限只有 0.095。
           再低就看不见，再高就开始"糊"。光滑低透明的大面 = 干净；
           离散微小硬点 = 脏 —— 分界就在这。 */
        var a = 0.095 * b.depth * breath;

        /* 光标增亮（不是推开）：越近越亮，最多 ×2.1，并被轻微吸引过去 */
        var ddx = X - mpx, ddy = Y - mpy;
        var dd = ddx * ddx + ddy * ddy;
        if (dd < pullR2) {
          var f = 1 - dd / pullR2;                      // 0（边缘）→ 1（正中）
          a *= (1 + 1.1 * f);
          X -= ddx * 0.06 * f;                          // 往指针方向"靠一点"
          Y -= ddy * 0.06 * f;
        }
        if (a <= 0.002) continue;                       // 太淡就跳过，省一次 drawImage

        /* 半径：大。40px 起步，最靠前的能到 ~160px */
        var rad = (40 + b.depth * 74) * b.r;
        if (rad < 6) continue;
        ctx.globalAlpha = a > 0.9 ? 0.9 : a;            // 夹一下，别叠爆
        ctx.drawImage(SPRITES[b.tint], X - rad, Y - rad, rad * 2, rad * 2);
      }

      /* ===== 第二层：发丝光丝 ===== */
      ctx.lineWidth = 1;                                // 严格 1px —— 细才干净
      ctx.lineCap = 'round';
      for (var k = 0; k < L.length; k++) {
        var s = L[k];
        var wob2 = t * 0.00018;
        var sx = cx + (s.bx + ox * 0.12 + Math.sin(wob2 * s.sp + s.ph) * 0.05) * spanX * (0.75 + s.depth * 0.35);
        var sy2 = cy + (s.by + oy * 0.12 + Math.cos(wob2 * s.sp * 0.8 + s.ph) * 0.05) * spanY * (0.75 + s.depth * 0.35);
        var len = s.len * W * (0.6 + s.depth * 0.7);    // 光丝长度（CSS px）
        var ang = s.angle + Math.sin(t * 0.00012 * s.sp + s.ph) * 0.06;  // 极缓摆动角度
        var half = len / 2;
        var dxv = Math.cos(ang) * half, dyv = Math.sin(ang) * half;      // 两端偏移

        /* 光丝透明度：比光斑更低（0.052 封顶）。线是"点到为止"的装饰，
           加长之后它们就是这首屏的「光缝」—— 和 .stage__scene 那束圆光同一主题。 */
        var la = 0.052 * s.depth * (0.7 + 0.3 * Math.sin(t * 0.0003 * s.sp + s.ph));
        var mdx = sx - mpx, mdy = sy2 - mpy;
        var mdd = mdx * mdx + mdy * mdy;
        if (mdd < pullR2) la *= (1 + 1.4 * (1 - mdd / pullR2));          // 指针附近也提亮
        if (la <= 0.002) continue;

        /* 线性渐变让两端化开 —— 硬边线段是"划痕"，化开的才是"光" */
        var grd = ctx.createLinearGradient(sx - dxv, sy2 - dyv, sx + dxv, sy2 + dyv);
        var rgbStr = s.tint === 0 ? '236,214,190' : '214,158,102';
        grd.addColorStop(0, 'rgba(' + rgbStr + ',0)');
        grd.addColorStop(0.5, 'rgba(' + rgbStr + ',1)');
        grd.addColorStop(1, 'rgba(' + rgbStr + ',0)');
        ctx.strokeStyle = grd;
        ctx.globalAlpha = la > 0.5 ? 0.5 : la;
        ctx.beginPath();
        ctx.moveTo(sx - dxv, sy2 - dyv);
        ctx.lineTo(sx + dxv, sy2 + dyv);
        ctx.stroke();
      }

      ctx.globalAlpha = 1;                              // 复位，别影响别的绘制
    }

    /* ------------------------------------------------------------------------
       主循环：tick 只负责调度与"该不该画"，真正的绘制在 draw。
       ---------------------------------------------------------------------- */
    function tick(t) {
      if (!cv.isConnected) { stop(); return; }           // 红线 7：节点没了就自杀
      raf = requestAnimationFrame(tick);                 // 先排下一帧（保证不中断）
      if (!visible || document.hidden) { last = 0; return; }   // 离屏/切后台：只排帧不绘制
      draw(t);
    }
    function start() {                                   // 开跑（REDUCE 下永远不开）
      if (running || REDUCE) return;
      running = true; last = 0;
      raf = requestAnimationFrame(tick);
    }
    function stop() {                                    // 停：取消已排的帧
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    }
    inst.stop = stop;                                    // 暴露给"下一个实例"调用

    /* ---------- 事件（红线 5：全部原生，不走 pOn） ---------- */

    /* 指针位置：用 clientX/Y 除以视口尺寸做归一化 */
    window.addEventListener('pointermove', function (e) {
      pmx = e.clientX / Math.max(1, window.innerWidth);
      pmy = e.clientY / Math.max(1, window.innerHeight);
    }, { passive: true });

    /* 尺寸变化：防抖 140ms（拖窗口时不要每像素都重建整组光斑） */
    var rt = 0;
    function onResize() {
      clearTimeout(rt);
      rt = setTimeout(function () { reseed(); if (REDUCE) draw(0); }, 140);
    }
    window.addEventListener('resize', onResize, { passive: true });
    window.addEventListener('orientationchange', onResize, { passive: true });

    /* 切回标签页时重置 last，避免用到"上一小时"的时间戳算出一个巨大的 dt */
    document.addEventListener('visibilitychange', function () { last = 0; });

    /* 离屏停摆（红线 3）：首屏滚出视口后就别烧 GPU 了
       rootMargin 120px：提前一点启动，滚回来时不会看到"空一拍" */
    if (window.IntersectionObserver) {
      var io = new IntersectionObserver(function (es) {
        for (var i = 0; i < es.length; i++) visible = es[i].isIntersecting;
        if (visible) start(); else stop();
      }, { rootMargin: '120px' });
      io.observe(cv);
    }

    reseed();                                            // 定尺寸、造元素
    if (REDUCE) { draw(0); } else { start(); }            // 红线 4：静止 or 动画
  }

  /* 首帧：DOM 就绪即建。换页后由 unseen.js 的 bootPage 再调一次（幂等）。 */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  window.__lightInit = init;    // 暴露给 bootPage
})();
