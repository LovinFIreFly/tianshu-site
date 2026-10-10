/* ============================================================================
   NOVA · Unseen 交互引擎（2026-10 重写）
   ----------------------------------------------------------------------------
   一整个文件就干六件事，全部挂在同一个 requestAnimationFrame 上，
   保证所有位移共用一条时间轴、永远不会互相打架（这是"顺滑"的根本）。

     ① us-field    波纹场 + 视角晃动 —— 原生 WebGL，全屏一个 quad 画柔光/涟漪/颗粒
     ② us-search   搜索框描边进度环 —— 巡航转圈 → 聚焦提速 → 提交转满一圈再走
     ③ us-cursor   鼠标落位 —— 点 + 环 lerp 跟随；可点元素胀成白色光晕；
                   文字链接套一圈手绘椭圆；点下去往波纹场里打一发强涟漪
     ④ us-transit  画面切换 —— 内容错峰升起 → 纸幕一闪 → 新内容错峰落位，
                   fetch 无缝换页（失败立刻退回整页跳转，绝不分白屏）
     ⑤ us-fold     视角折叠 —— hover 那张跟着指针立起来，同排兄弟后退让位；
                   滚动入场时整组从"折进去"的姿态展开
     ⑥ us-base     基座 —— 揭示 / 数字滚动 / 磁性 / 表单忙碌 / 顶栏 / 抽屉 / 手风琴

   所有模块都以"DOM 里有没有对应节点"为前提，缺了就静默跳过 ——
   后台页、DM 工作台这些不套 nova 骨架的页面挂上这个文件也完全无害。

   降级：加不上 u-on / 取不到 WebGL / 用户开了 reduce-motion，
   页面退化成一份纯静态可读文档，功能一个不少。
   ========================================================================== */
(function () {
  'use strict';

  var W = window, D = document;
  var doc = D.documentElement;

  /* 环境探测：三条兜底线，任何一条不满足就整体降级 */
  var REDUCE = false;
  try { REDUCE = !!(W.matchMedia && W.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) {}
  var COARSE = false;
  try { COARSE = !!(W.matchMedia && W.matchMedia('(hover: none), (pointer: coarse)').matches); } catch (e) {}
  var FINE = ('onpointermove' in W) && !COARSE;

  function $(s, r) { try { return (r || D).querySelector(s); } catch (e) { return null; } }
  function $$(s, r) {
    try { return Array.prototype.slice.call((r || D).querySelectorAll(s)); } catch (e) { return []; }
  }
  function on(el, ev, fn, opt) { try { el.addEventListener(ev, fn, opt || false); } catch (e) {} }
  function num(v, d) { var n = parseFloat(v); return isNaN(n) ? d : n; }
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, k) { return a + (b - a) * k; }

  /* ══════════════════════════ 统一时钟 ══════════════════════════
     全站所有持续动画（波纹场、光标、折叠跟随、视角晃动）都在这里跑。
     单个 rAF 循环 = 一个时间基准 = 不会出现"A 动完了 B 才开始"的错位。 */
  var tickers = [];
  var last = 0, now = 0, running = false;

  function loop(ts) {
    if (!running) return;
    if (!last) last = ts;
    var dt = Math.min((ts - last) / 1000, 0.05);   // 掉帧时钳住，避免动画瞬移
    last = ts;
    now = ts / 1000;
    for (var i = 0; i < tickers.length; i++) {
      try { tickers[i](dt, now); } catch (e) {}
    }
    W.requestAnimationFrame(loop);
  }
  function startLoop() {
    if (running) return;
    running = true; last = 0;
    W.requestAnimationFrame(loop);
  }
  function addTick(fn) { if (tickers.indexOf(fn) < 0) tickers.push(fn); }
  function stopLoop() { running = false; }
  on(D, 'visibilitychange', function () {
    if (D.hidden) stopLoop();
    else if (tickers.length) startLoop();
  });

  /* 让浏览器先画一帧再改类 —— CSS 过渡必须"从一个已经渲染过的状态"出发才会跑。
     同一 tick 里连着加两个类，过渡是不会触发的（元素直接出现在终态）。 */
  function soon(fn) {
    W.requestAnimationFrame(function () { W.requestAnimationFrame(fn); });
  }

  /* ══════════════════════════ ① 波纹场 + 视角晃动 ══════════════════════════ */
  var Field = (function () {
    var cv = null, gl = null, prog = null, uni = {}, buf = null;
    var MAXR = 8, ripples = [];   // {x,y,t} 归一化坐标 + 注入时刻
    var px = 0.5, py = 0.5, tpx = 0.5, tpy = 0.5;
    var dpr = 1, w = 0, h = 0, alive = false, t0 = 0;

    var VS = [
      'attribute vec2 p;',
      'void main(){ gl_Position = vec4(p, 0.0, 1.0); }'
    ].join('\n');

    /* 片元：四团缓慢游走的柔光 → 叠加涟漪扰动 → 最后撒一层颗粒。
       颜色刻意压得很淡：它是"场景"，不是"图形"，绝不能抢正文。 */
    var FS = [
      'precision mediump float;',
      'uniform vec2 uRes;',
      'uniform float uT;',
      'uniform vec2 uP;',
      'uniform vec3 uR[' + MAXR + '];',   // xy=位置(0..1) z=年龄(秒)
      'uniform vec3 uG[4];',              // 三团光晕色 + 底色
      'uniform float uDark;',
      '',
      'float hash(vec2 p){ p = fract(p*vec2(123.34, 345.45)); p += dot(p, p+34.345); return fract(p.x*p.y); }',
      'float noise(vec2 p){',
      '  vec2 i = floor(p), f = fract(p);',
      '  f = f*f*(3.0-2.0*f);',
      '  return mix(mix(hash(i), hash(i+vec2(1.,0.)), f.x),',
      '             mix(hash(i+vec2(0.,1.)), hash(i+vec2(1.,1.)), f.x), f.y);',
      '}',
      'float blob(vec2 uv, vec2 c, float r){',
      '  float d = length((uv-c) * vec2(uRes.x/uRes.y, 1.0));',
      '  return smoothstep(r, 0.0, d);',
      '}',
      '',
      'void main(){',
      '  vec2 uv = gl_FragCoord.xy / uRes;',
      '  vec2 asp = vec2(uRes.x/uRes.y, 1.0);',
      '  float t = uT;',
      '',
      '  /* 涟漪：把采样坐标往外推，形成水面的环形扰动 */',
      '  vec2 ripple = vec2(0.0);',
      '  for(int i=0;i<' + MAXR + ';i++){',
      '    vec3 R = uR[i];',
      '    if(R.z < 0.0 || R.z > 2.6) continue;',
      '    vec2 d = (uv - R.xy) * asp;',
      '    float dist = length(d);',
      '    float age  = R.z;',
      '    float front = age * 0.42;',                 // 波前半径随时间扩散
      '    float ring  = sin((dist - front) * 46.0) * exp(-abs(dist - front) * 13.0);',
      '    float fad   = exp(-age * 1.35) * smoothstep(0.75, 0.0, dist);',
      '    ripple += normalize(d + 1e-5) * ring * fad * 0.017;',
      '  }',
      '',
      '  /* 指针处持续的微弱"体温"扰动，让画面一直活着 */',
      '  vec2 pd = (uv - uP) * asp;',
      '  float pdist = length(pd);',
      '  float breath = sin(pdist * 34.0 - t * 2.4) * exp(-pdist * 7.5) * 0.006;',
      '  ripple += normalize(pd + 1e-5) * breath;',
      '',
      '  vec2 q = uv + ripple;',
      '',
      '  /* 三团柔光，各自缓慢漂移 */',
      '  float c1 = blob(q, vec2(0.20 + 0.05*sin(t*0.13), 0.20 + 0.04*cos(t*0.11)), 0.62);',
      '  float c2 = blob(q, vec2(0.82 + 0.04*cos(t*0.09), 0.26 + 0.05*sin(t*0.15)), 0.55);',
      '  float c3 = blob(q, vec2(0.66 + 0.05*sin(t*0.07), 0.88 + 0.04*cos(t*0.12)), 0.66);',
      '  float c4 = blob(q, vec2(0.08 + 0.04*cos(t*0.10), 0.80 + 0.04*sin(t*0.08)), 0.52);',
      '',
      '  vec3 col = uG[3];',
      '  col = mix(col, uG[0], c1 * 0.95);',
      '  col = mix(col, uG[1], c2 * 0.78);',
      '  col = mix(col, uG[2], c3 * 0.86);',
      '  col = mix(col, uG[1], c4 * 0.50);',
      '',
      '  /* 涟漪处提亮一点点，像光在水面聚起来 */',
      '  col += vec3(length(ripple) * 3.4) * (1.0 - uDark);',
      '',
      '  /* 颗粒：动态噪点，压掉渐变的塑料感 */',
      '  float g = noise(gl_FragCoord.xy * 0.85 + vec2(t*13.0, t*7.0));',
      '  col += (g - 0.5) * (uDark > 0.5 ? 0.030 : 0.020);',
      '',
      '  gl_FragColor = vec4(col, 1.0);',
      '}'
    ].join('\n');

    function compile(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { gl.deleteShader(s); return null; }
      return s;
    }

    function css(name, fallback) {
      try {
        var v = getComputedStyle(doc).getPropertyValue(name).trim();
        return v || fallback;
      } catch (e) { return fallback; }
    }
    function hex2rgb(h) {
      h = (h || '').trim();
      if (h.charAt(0) !== '#') return [0.5, 0.5, 0.5];
      if (h.length === 4) h = '#' + h[1] + h[1] + h[2] + h[2] + h[3] + h[3];
      var n = parseInt(h.slice(1), 16);
      return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
    }

    function init() {
      cv = $('#usFieldCv');
      if (!cv || REDUCE) return false;
      try {
        gl = cv.getContext('webgl', { antialias: false, alpha: false, depth: false, stencil: false })
          || cv.getContext('experimental-webgl', { antialias: false, alpha: false, depth: false });
      } catch (e) { gl = null; }
      if (!gl) return false;

      var vs = compile(gl.VERTEX_SHADER, VS), fs = compile(gl.FRAGMENT_SHADER, FS);
      if (!vs || !fs) return false;
      prog = gl.createProgram();
      gl.attachShader(prog, vs); gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { prog = null; return false; }
      gl.useProgram(prog);

      buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var loc = gl.getAttribLocation(prog, 'p');
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

      uni.res = gl.getUniformLocation(prog, 'uRes');
      uni.t = gl.getUniformLocation(prog, 'uT');
      uni.p = gl.getUniformLocation(prog, 'uP');
      uni.r = gl.getUniformLocation(prog, 'uR[0]');
      uni.g = gl.getUniformLocation(prog, 'uG[0]');
      uni.dark = gl.getUniformLocation(prog, 'uDark');

      var dark = doc.getAttribute('data-theme') === 'dark';
      var cols = [
        hex2rgb(css('--us-glow-1', '#E3D3EC')),
        hex2rgb(css('--us-glow-2', '#F7DBE1')),
        hex2rgb(css('--us-glow-3', '#FCF0E2')),
        hex2rgb(css('--us-bg', '#F1F0EC'))
      ];
      var flat = [];
      for (var i = 0; i < 4; i++) flat.push(cols[i][0], cols[i][1], cols[i][2]);
      gl.uniform3fv(uni.g, new Float32Array(flat));
      gl.uniform1f(uni.dark, dark ? 1 : 0);

      for (var k = 0; k < MAXR; k++) ripples.push({ x: 0, y: 0, a: -1 });
      var rv = new Float32Array(MAXR * 3);
      gl.uniform3fv(uni.r, rv);

      resize();
      on(W, 'resize', resize);
      t0 = performance.now() / 1000;
      alive = true;
      addTick(step);
      startLoop();
      return true;
    }

    function resize() {
      if (!gl) return;
      var el = cv.parentNode || cv;
      var cw = el.clientWidth || W.innerWidth;
      var ch = el.clientHeight || W.innerHeight;
      dpr = Math.min(W.devicePixelRatio || 1, 1.5);
      w = Math.max(1, Math.round(cw * dpr));
      h = Math.max(1, Math.round(ch * dpr));
      if (cv.width !== w || cv.height !== h) {
        cv.width = w; cv.height = h;
        gl.viewport(0, 0, w, h);
      }
      gl.uniform2f(uni.res, w, h);
    }

    var rv = null;
    var idleAt = 0;

    function step(dt, tsec) {
      if (!alive || !gl) return;
      tsec = tsec || (performance.now() / 1000 - t0);

      /* 指针做一次 lerp：晃得太快会晕，慢半拍才有"镜头"的惯性 */
      px = lerp(px, tpx, 1 - Math.pow(0.001, dt));
      py = lerp(py, tpy, 1 - Math.pow(0.001, dt));
      gl.uniform2f(uni.p, px, 1 - py);

      /* 没人动 7 秒就自己打一发，画面不会"死" */
      if (tsec - idleAt > 7) {
        emit(0.22 + Math.random() * 0.56, 0.18 + Math.random() * 0.64, 0.55);
        idleAt = tsec;
      }

      if (!rv) rv = new Float32Array(MAXR * 3);
      var live = false;
      for (var i = 0; i < MAXR; i++) {
        var r = ripples[i];
        if (r.a >= 0) {
          r.a += dt;
          if (r.a > 2.6) r.a = -1;
          else live = true;
        }
        rv[i * 3] = r.x; rv[i * 3 + 1] = 1 - r.y; rv[i * 3 + 2] = r.a;
      }
      if (live) gl.uniform3fv(uni.r, rv);

      gl.uniform1f(uni.t, tsec);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    /* 往池子里塞一发涟漪（满了就顶掉最老的那发） */
    function emit(x, y, power) {
      if (!alive) return;
      power = power || 1;
      var slot = -1, oldest = 1e9;
      for (var i = 0; i < MAXR; i++) {
        if (ripples[i].a < 0) { slot = i; break; }
        if (ripples[i].a > oldest) { oldest = ripples[i].a; slot = i; }
      }
      if (slot < 0) slot = 0;
      ripples[slot] = { x: x, y: y, a: 0 };
    }

    function pointer(x, y) { tpx = x; tpy = y; }

    function repaint() {
      if (!alive || !gl) return;
      var dark = doc.getAttribute('data-theme') === 'dark';
      var cols = [
        hex2rgb(css('--us-glow-1', '#E3D3EC')),
        hex2rgb(css('--us-glow-2', '#F7DBE1')),
        hex2rgb(css('--us-glow-3', '#FCF0E2')),
        hex2rgb(css('--us-bg', '#F1F0EC'))
      ];
      var flat = [];
      for (var i = 0; i < 4; i++) flat.push(cols[i][0], cols[i][1], cols[i][2]);
      gl.uniform3fv(uni.g, new Float32Array(flat));
      gl.uniform1f(uni.dark, dark ? 1 : 0);
    }

    return { init: init, emit: emit, pointer: pointer, repaint: repaint, ok: function () { return alive; } };
  })();

  /* 视角晃动：跟着指针做几像素的位移 + 零点几度的旋转，
     再叠一条永远在跑的怠速漂移，让首屏"有呼吸"。 */
  var Sway = (function () {
    var els = [], tx = 0, ty = 0, cx = 0, cy = 0, tr = 0, cr = 0, started = false;

    function init() {
      els = $$('[data-sway]');
      if (!els.length || REDUCE) return;
      addTick(step);
      startLoop();
      started = true;
    }
    function pointer(nx, ny) {          // nx/ny ∈ -1..1
      tx = nx; ty = ny;
      tr = nx * 0.55;                   // 旋转幅度压得很小，多了就像坏掉
    }
    function step(dt, t) {
      var k = 1 - Math.pow(0.06, dt);   // 慢跟随 ≈ 6% 每帧
      cx = lerp(cx, tx, k);
      cy = lerp(cy, ty, k);
      cr = lerp(cr, tr, k);
      var drift = Math.sin(t * 0.42) * 3.2;
      var drift2 = Math.cos(t * 0.31) * 2.1;
      var dx = (cx * 13 + drift).toFixed(2);
      var dy = (cy * 10 + drift2).toFixed(2);
      for (var i = 0; i < els.length; i++) {
        els[i].style.setProperty('--swx', dx + 'px');
        els[i].style.setProperty('--swy', dy + 'px');
        els[i].style.setProperty('--swr', cr.toFixed(3) + 'deg');
      }
    }
    function rebind() { els = $$('[data-sway]'); }
    return { init: init, pointer: pointer, rebind: rebind, on: function () { return started; } };
  })();

  /* ══════════════════════════ ③ 鼠标落位（光标） ══════════════════════════ */
  var Cursor = (function () {
    var el, ring, dot, lab;
    var mx = 0, my = 0, rx = 0, ry = 0, sx = 0, sy = 0, k = 1;
    var ready = false, scrib = null, scribFor = null;

    function init() {
      if (!FINE || REDUCE) return;
      el = D.createElement('div');
      el.className = 'u-cur';
      el.setAttribute('aria-hidden', 'true');
      el.innerHTML = '<span class="u-cur__ring"></span><span class="u-cur__dot"></span><span class="u-cur__lab"></span>';
      D.body.appendChild(el);
      ring = $('.u-cur__ring', el);
      dot = $('.u-cur__dot', el);
      lab = $('.u-cur__lab', el);
      ready = true;
      /* 只有真建出来了才敢把系统光标藏掉（否则用户会一根光标都没有） */
      doc.classList.add('u-curon');
      addTick(step);
      startLoop();

      on(D, 'pointermove', move, { passive: true });
      on(D, 'pointerdown', down);
      on(D, 'pointerup', up);
      on(D, 'pointerleave', function () { el.classList.add('is-gone'); });
      on(D, 'pointerenter', function () { el.classList.remove('is-gone'); });
      on(D, 'pointerover', over);
      on(D, 'pointerout', out);

      /* 表单 / 可编辑区自动切成文本光标 */
      on(D, 'focusin', function (e) {
        var t = e.target;
        if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || (t && t.isContentEditable)) {
          D.body.setAttribute('data-cur', t.tagName === 'SELECT' ? 'link' : 'text');
        }
      });
      on(D, 'focusout', function () { D.body.removeAttribute('data-cur'); });
    }

    function move(e) {
      mx = e.clientX; my = e.clientY;
      Field.pointer(e.clientX / Math.max(1, W.innerWidth), e.clientY / Math.max(1, W.innerHeight));
      if (Sway.on()) {
        Sway.pointer((e.clientX / Math.max(1, W.innerWidth)) * 2 - 1,
                     (e.clientY / Math.max(1, W.innerHeight)) * 2 - 1);
      }
    }

    function step(dt) {
      var f = 1 - Math.pow(0.0006, dt);      // 环慢、点快 → 才有"落位"的层感
      rx = lerp(rx, mx, f);
      ry = lerp(ry, my, f);
      sx = lerp(sx, mx, 1 - Math.pow(0.00002, dt));
      sy = lerp(sy, my, 1 - Math.pow(0.00002, dt));
      el.style.transform = 'translate3d(' + sx.toFixed(2) + 'px,' + sy.toFixed(2) + 'px,0)';
      /* 位移每帧都在写，所以缩放必须**拼进同一条 transform** ——
         单独在 CSS 里写 transform:scale() 会被这里的 inline 覆盖掉（原来就是这么坏的）。 */
      ring.style.transform = 'translate3d(' + (rx - sx).toFixed(2) + 'px,' + (ry - sy).toFixed(2) + 'px,0)' +
        (k === 1 ? '' : ' scale(' + k.toFixed(3) + ')');
      dot.style.transform = 'translate3d(' + (mx - sx).toFixed(2) + 'px,' + (my - sy).toFixed(2) + 'px,0)';
    }

    /* 落位：指着什么，光标说什么 */
    var HIT = 'a,button,[role="button"],summary,label,input,select,textarea,[data-cursor]';
    function over(e) {
      var t = e.target && e.target.closest ? e.target.closest(HIT) : null;
      if (!t) return;
      var c = t.getAttribute('data-cursor') || '';
      var tag = t.tagName;
      if (!c) c = (/^(INPUT|TEXTAREA)$/.test(tag) || t.isContentEditable) ? 'text' : 'link';
      D.body.setAttribute('data-cur', c);
      var l = t.getAttribute('data-cursor-label');
      if (l && lab) { lab.textContent = l; D.body.setAttribute('data-cur', 'view'); }
      /* 文字链接：套一圈手绘椭圆 */
      if (t.hasAttribute('data-scribble')) drawScrib(t);
    }
    function out(e) {
      var t = e.target && e.target.closest ? e.target.closest(HIT) : null;
      if (!t) return;
      D.body.removeAttribute('data-cur');
      if (lab) lab.textContent = '';
      if (scribFor === t) clearScrib();
    }

    /* ── 手绘圈选：把一圈抖动的椭圆描出来 ── */
    function drawScrib(t) {
      if (scribFor === t && scrib) return;
      clearScrib();
      var r = t.getBoundingClientRect();
      var w = r.width, h = r.height;
      if (!w || !h) return;
      var padX = 8, padY = 6;
      var svg = D.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'u-scrib');
      svg.setAttribute('viewBox', '0 0 ' + (w + padX * 2) + ' ' + (h + padY * 2));
      svg.setAttribute('width', w + padX * 2);
      svg.setAttribute('height', h + padY * 2);
      svg.style.position = 'absolute';
      svg.style.left = '-6px';
      svg.style.top = '-5px';
      svg.style.pointerEvents = 'none';
      svg.style.overflow = 'visible';

      var path = D.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', scribPath(w + padX * 2, h + padY * 2));
      path.setAttribute('pathLength', '100');      // 归一化，描画时长与尺寸无关
      path.style.setProperty('--len', '100');
      svg.appendChild(path);

      var pos = '';
      try { pos = getComputedStyle(t).position; } catch (e) {}
      if (pos === 'static') t.style.position = 'relative';
      t.appendChild(svg);
      scrib = svg; scribFor = t;
    }
    function clearScrib() {
      if (scrib && scrib.parentNode) scrib.parentNode.removeChild(scrib);
      scrib = null; scribFor = null;
    }
    /* 一圈"随手画"的椭圆：半径按正弦抖两下，端点故意重合 */
    function scribPath(w, h) {
      var rx = w / 2 - 1, ry = h / 2 - 1, cx = w / 2, cy = h / 2;
      var N = 30, d = '';
      for (var i = 0; i <= N; i++) {
        var a = i / N * Math.PI * 2 - Math.PI * 0.62;         // 起点错开，更像随手起笔
        var j = 1 + (i % 3 === 0 ? 0.042 : (i % 3 === 1 ? -0.028 : 0.008));
        var x = cx + Math.cos(a) * rx * j;
        var y = cy + Math.sin(a) * ry * j;
        d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
      }
      return d;
    }

    function down(e) {
      if (!ready) return;
      el.classList.add('is-hit');
      k = 0.72;                                  // 环先塌一下
      Field.emit(e.clientX / Math.max(1, W.innerWidth), e.clientY / Math.max(1, W.innerHeight), 1);
    }
    function up() {
      if (!ready) return;
      el.classList.remove('is-hit');
      el.classList.add('is-boom');
      k = 1.3;                                   // 再弹回来
      W.setTimeout(function () {
        el.classList.remove('is-boom');
        k = 1;
        ring.style.transform = 'translate3d(' + (rx - sx).toFixed(2) + 'px,'
          + (ry - sy).toFixed(2) + 'px,0)';
      }, 300);
    }
    return { init: init, ok: function () { return ready; } };
  })();

  /* ══════════════════════════ ⑦ 平滑滚动（unseen 的 asscroll） ══════════════════════════
     拦下滚轮的 delta，做一次 lerp 补间再写回 window.scrollTo。
     为什么不用 transform 方案（Lenis 那套）：那会把 position:sticky 弄坏，
     而右栏粘住的预订面板是详情页的关键。
     这里保住了原生滚动 —— 键盘、滚动条、锚点、iOS 惯性全都不受影响。 */
  var Smooth = (function () {
    var target = 0, cur = 0, active = false, ext = false;

    function maxY() {
      var de = D.documentElement;
      return Math.max(0, (de.scrollHeight || 0) - W.innerHeight);
    }
    /* 事件路径上有没有"自己能滚"的祖先（聊天流、长下拉、可滚面板）——
       有就别抢它的滚轮，否则里面就锁死了 */
    function innerScrollable(node, dy) {
      while (node && node.nodeType === 1 && node !== D.body && node !== D.documentElement) {
        var s;
        try { s = getComputedStyle(node); } catch (e) { s = null; }
        if (s && /(auto|scroll)/.test(s.overflowY) && node.scrollHeight > node.clientHeight + 2) {
          var room = node.scrollHeight - node.clientHeight;
          var canGo = dy < 0 ? node.scrollTop > 1 : node.scrollTop < room - 1;
          if (canGo) return true;
        }
        node = node.parentNode;
      }
      return false;
    }

    function init() {
      if (REDUCE || COARSE || !FINE) return;          // 触屏 / 减少动态：一律走原生
      target = cur = W.pageYOffset || 0;
      on(W, 'wheel', wheel, { passive: false });
      /* 外部滚动（键盘 / 滚动条 / 锚点 / 转场里的 scrollTo）：对一次表，
         免得下一次滚轮是从一个过期的位置开始补间 */
      on(W, 'scroll', function () {
        if (active) return;
        cur = target = W.pageYOffset || 0;
      }, { passive: true });
    }

    function wheel(e) {
      if (e.ctrlKey || ext) return;                   // 捏合缩放交给浏览器
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      var lock = doc.style.overflow === 'hidden' || D.body.style.overflow === 'hidden';
      if (lock) return;                               // 全屏索引开着：别动
      if (innerScrollable(e.target, e.deltaY)) return;
      e.preventDefault();
      var d = e.deltaMode === 1 ? e.deltaY * 18
            : (e.deltaMode === 2 ? e.deltaY * W.innerHeight : e.deltaY);
      target = clamp(target + d, 0, maxY());
      if (!active) { active = true; cur = W.pageYOffset || 0; addTick(step); startLoop(); }
    }

    function step(dt) {
      cur = lerp(cur, target, 1 - Math.pow(0.0006, dt));
      if (Math.abs(target - cur) < 0.35) { cur = target; active = false; }
      ext = true;
      W.scrollTo(0, Math.round(cur));
      ext = false;
    }

    return { init: init };
  })();

  /* ══════════════════════════ ② 搜索框描边进度环 ══════════════════════════ */
  var Search = (function () {
    function init(root) {
      $$('.u-search', root).forEach(function (s) {
        if (s.getAttribute('data-bound') === '1') return;
        s.setAttribute('data-bound', '1');
        var inp = $('input', s);
        if (!inp) return;
        var form = s.closest('form') || $('form', s);

        on(inp, 'focus', function () { s.classList.add('is-focus', 'is-run'); });
        on(inp, 'blur', function () { s.classList.remove('is-focus'); s.classList.remove('is-run'); });
        on(inp, 'input', function () { s.classList.toggle('has-val', !!inp.value.trim()); });
        if (inp.value.trim()) s.classList.add('has-val');

        if (!form) return;
        on(form, 'submit', function (e) {
          /* 那一圈描边无论谁接管提交都要转满一圈 —— 反馈必须先于结果 */
          s.classList.remove('is-run');
          s.classList.add('is-go');
          W.setTimeout(function () { s.classList.remove('is-go'); s.classList.add('is-run'); }, 760);
          /* data-no-go：这表单由页面自己的脚本处理（剧本库走 fetch 换网格），
             这里只负责画那一圈，绝不抢它的提交 */
          if (form.hasAttribute('data-no-go')) return;
          if (s.getAttribute('data-going') === '1') return;
          if (REDUCE || !('fetch' in W)) return;
          e.preventDefault();
          s.setAttribute('data-going', '1');
          W.setTimeout(function () { form.submit(); }, 520);
        });
      });
    }
    return { init: init };
  })();

  /* ══════════════════════════ ⑥ 基座：揭示 / 数字 / 磁性 / 表单 / 顶栏 ══════════════════════════ */
  var Base = (function () {
    var io = null, countIo = null;

    function reveal(root) {
      var els = $$('[data-d]', root);
      if (!els.length) return;
      /* 延迟由 data-d 决定，但同一屏里超过 8 个就压住上限，否则最后几个等到天荒地老 */
      els.forEach(function (el, i) {
        var d = num(el.getAttribute('data-d'), -1);
        el.style.setProperty('--d', (d >= 0 ? d : Math.min(i * 70, 520)) + 'ms');
      });
      if (REDUCE || !('IntersectionObserver' in W)) {
        els.forEach(function (el) { el.classList.add('is-in'); });
        return;
      }
      if (!io) {
        /* 阈值压到 0.01、底边距只留 3%：刚探进视口一点点就该开始落位，
           否则首屏边缘的区块会一直停在 opacity:0，看起来像"这里没内容"。 */
        io = new IntersectionObserver(function (es) {
          es.forEach(function (e) {
            if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
          });
        }, { rootMargin: '0px 0px -3% 0px', threshold: 0.01 });
      }
      var vh = W.innerHeight || 0;
      els.forEach(function (el) { if (!el.classList.contains('is-in')) io.observe(el); });
      /* 已经在眼前的那批：等浏览器把 opacity:0 那一帧画出来再落位，
         否则过渡不会跑，内容会"啪"地出现。 */
      soon(function () {
        els.forEach(function (el) {
          if (el.classList.contains('is-in')) return;
          try {
            var r = el.getBoundingClientRect();
            if (r.top < vh * 0.99 && r.bottom > 0) el.classList.add('is-in');
          } catch (e) {}
        });
      });
    }

    /* 数字滚动：从 0 爬到目标值，用 easeOut，末尾慢下来 */
    function counts(root) {
      var els = $$('[data-to]', root);
      if (!els.length) return;
      els.forEach(function (el) {
        if (el.getAttribute('data-done') === '1') return;
        var to = num(el.getAttribute('data-to'), 0);
        var dec = parseInt(el.getAttribute('data-dec') || '0', 10);
        function paint(v) {
          el.textContent = dec ? v.toFixed(dec) : String(Math.round(v));
        }
        if (REDUCE) { paint(to); el.setAttribute('data-done', '1'); return; }
        var t0 = 0, dur = 1.55;
        var tick = function (dt, t) {
          if (!t0) t0 = t;
          var p = clamp((t - t0) / dur, 0, 1);
          var e = 1 - Math.pow(1 - p, 3);
          paint(to * e);
          if (p >= 1) {
            paint(to);
            el.setAttribute('data-done', '1');
            var i = tickers.indexOf(tick); if (i >= 0) tickers.splice(i, 1);
          }
        };
        if (!('IntersectionObserver' in W)) { tick(0.016, performance.now() / 1000); addTick(tick); startLoop(); return; }
        if (!countIo) {
          countIo = new IntersectionObserver(function (es) {
            es.forEach(function (e) {
              if (!e.isIntersecting) return;
              countIo.unobserve(e.target);
              addTick(tick); startLoop();
            });
          }, { threshold: 0.4 });
        }
        countIo.observe(el);
      });
    }

    /* 磁性：指针靠近时元素朝指针挪一点点（≤8px），离开回弹 */
    function magnets(root) {
      if (!FINE || REDUCE) return;
      $$('[data-magnet]', root).forEach(function (el) {
        if (el.getAttribute('data-mag') === '1') return;
        el.setAttribute('data-mag', '1');
        var k = num(el.getAttribute('data-magnet'), 6);
        var tx = 0, ty = 0, cx = 0, cy = 0, active = false;
        function st(dt) {
          var f = 1 - Math.pow(0.002, dt);
          cx = lerp(cx, tx, f); cy = lerp(cy, ty, f);
          el.style.transform = 'translate3d(' + cx.toFixed(2) + 'px,' + cy.toFixed(2) + 'px,0)';
          if (!active && Math.abs(cx) < 0.05 && Math.abs(cy) < 0.05) {
            el.style.transform = '';
            var i = tickers.indexOf(st); if (i >= 0) tickers.splice(i, 1);
          }
        }
        on(el, 'pointermove', function (e) {
          var r = el.getBoundingClientRect();
          var dx = e.clientX - (r.left + r.width / 2);
          var dy = e.clientY - (r.top + r.height / 2);
          var d = Math.sqrt(dx * dx + dy * dy) || 1;
          var pull = clamp(1 - d / (Math.max(r.width, r.height) * 1.5), 0, 1);
          tx = (dx / d) * k * pull; ty = (dy / d) * k * pull;
          active = true;
          if (tickers.indexOf(st) < 0) { addTick(st); startLoop(); }
        });
        on(el, 'pointerleave', function () {
          tx = 0; ty = 0; active = false;
          if (tickers.indexOf(st) < 0) { addTick(st); startLoop(); }
        });
      });
    }

    /* 表单忙碌：提交后按钮转圈并锁住，防重复下单 */
    function busy(root) {
      $$('form[data-busy]', root).forEach(function (form) {
        if (form.getAttribute('data-busy-bound') === '1') return;
        form.setAttribute('data-busy-bound', '1');
        on(form, 'submit', function () {
          if (form.getAttribute('data-sent') === '1') { return; }
          form.setAttribute('data-sent', '1');
          W.setTimeout(function () {
            $$('button[type=submit], button:not([type])', form).forEach(function (b) {
              b.classList.add('u-busy');
              b.setAttribute('aria-busy', 'true');
            });
          }, 0);
        });
      });
    }

    /* 手风琴（问答页）：点一下展开一条，同时把别的收起来 */
    function accordion(root) {
      $$('.qa-item', root).forEach(function (it) {
        if (it.getAttribute('data-bnd') === '1') return;
        it.setAttribute('data-bnd', '1');
        var q = $('.qa-item__q', it);
        if (!q) return;
        on(q, 'click', function () {
          var was = it.classList.contains('is-on');
          $$('.qa-item.is-on', it.parentNode).forEach(function (o) { o.classList.remove('is-on'); });
          it.classList.toggle('is-on', !was);
        });
      });
    }

    /* 本页内分栏（我的页）：纯前端切面板，不跳页 */
    function panes(root) {
      $$('[data-panes]', root).forEach(function (bar) {
        if (bar.getAttribute('data-bnd') === '1') return;
        bar.setAttribute('data-bnd', '1');
        var scope = bar.parentNode;
        on(bar, 'click', function (e) {
          var b = e.target.closest('[data-pane]');
          if (!b) return;
          var key = b.getAttribute('data-pane');
          $$('button', bar).forEach(function (x) { x.classList.toggle('is-on', x === b); });
          $$('.me-pane', scope).forEach(function (p) {
            p.classList.toggle('is-on', p.getAttribute('data-pane') === key);
          });
          /* 切面板时抖一发涟漪，给一次"换页"的触感 */
          if (Field.ok()) Field.emit(0.5, 0.42, 0.7);
          try { history.replaceState(null, '', '?tab=' + key); } catch (err) {}
        });
      });
    }

    /* 顶栏：滚过一屏就浮出纸底；往下滚藏起来，往上滚立刻回来 */
    function topbar() {
      var bar = $('.u-top');
      if (!bar) return;
      var lastY = W.pageYOffset || 0;
      on(W, 'scroll', function () {
        var y = W.pageYOffset || 0;
        bar.classList.toggle('is-stuck', y > 30);
        if (y > 240 && y > lastY + 4) bar.classList.add('is-down');
        else if (y < lastY - 4 || y < 120) bar.classList.remove('is-down');
        lastY = y;
      }, { passive: true });
    }

    /* 导航滑动下划线：整条导航只有一根线，指针走到哪儿它滑到哪儿 */
    function navUl() {
      var nav = $('.u-nav');
      if (!nav) return;
      var ul = $('.u-nav__ul', nav);
      if (!ul && !REDUCE) {
        ul = D.createElement('span');
        ul.className = 'u-nav__ul';
        ul.setAttribute('aria-hidden', 'true');
        nav.appendChild(ul);
      }
      if (!ul) return;

      function to(a) {
        if (!a) { nav.classList.remove('is-ulah'); return; }
        var nr = nav.getBoundingClientRect(), ar = a.getBoundingClientRect();
        nav.classList.add('is-ulah');
        ul.style.transform = 'translateX(' + (ar.left - nr.left).toFixed(1) + 'px)';
        ul.style.width = ar.width.toFixed(1) + 'px';
      }
      /* 当前页那条；没有当前页（首页、错误页）就整根线收掉 ——
         让线挂在"本本墙"下面而其实当前在首页，比没有线更误导。 */
      var rest = function () { return $('a.is-on', nav); };

      on(nav, 'pointerover', function (e) {
        var a = e.target.closest && e.target.closest('a');
        if (a) to(a, true);
      });
      on(nav, 'pointerleave', function () { to(rest(), true); });
      /* 内容晚一步到（字体加载完宽度会变），窗口动过之后重新对一次 */
      on(W, 'resize', function () { to(rest(), true); }, { passive: true });
      W.setTimeout(function () { to(rest(), true); }, 260);
      W.setTimeout(function () { to(rest(), true); }, 900);
    }

    /* 白钮 → 全屏索引 */
    function menu() {
      var orb = $('#uOrb'), m = $('#uMenu');
      if (!orb || !m) return;
      function set(v) {
        m.classList.toggle('is-on', v);
        orb.classList.toggle('is-open', v);
        orb.setAttribute('aria-expanded', v ? 'true' : 'false');
        m.setAttribute('aria-hidden', v ? 'false' : 'true');
        doc.style.overflow = v ? 'hidden' : '';
        /* 菜单项错峰落下 */
        $$('a', m).forEach(function (a, i) {
          a.style.transitionDelay = (v ? 60 + i * 52 : 0) + 'ms';
        });
      }
      on(orb, 'click', function () { set(!m.classList.contains('is-on')); });
      on(D, 'keydown', function (e) { if (e.key === 'Escape') set(false); });
      on(m, 'click', function (e) { if (e.target === m) set(false); });
      return set;
    }

    return {
      reveal: reveal, counts: counts, magnets: magnets, busy: busy,
      accordion: accordion, panes: panes, topbar: topbar, navUl: navUl, menu: menu
    };
  })();

  /* ══════════════════════════ 0 · 入场门（unseen 的 js-loader） ══════════════════════════
     门本身写在 layout 里、由 html.u-boot 点亮（那个类在 <head> 里、首帧之前就加上了）。
     这里只负责把它推到底再撤掉：进度条按真实节奏爬到 100%，然后放画面进来。
     window.load 之前不撤，页面也不会一路白等 —— <head> 里 3s 兜底会自己收工。 */
  var Boot = (function () {
    var box, fill, pct, raf = null, t0 = 0, done = false, open = null;

    function init(onOpen) {
      open = onOpen || null;
      box = $('#uLoader');
      if (!box) { finish(); return; }            // 没有门（比如后台页）：直接放行
      fill = $('.u-loader__bar i', box);
      pct = $('.u-loader__pct', box);
      t0 = performance.now();
      doc.classList.add('u-boot');               // 兜底：万一 <head> 那段没跑到
      raf = W.requestAnimationFrame(tick);
      if (D.readyState === 'complete') W.setTimeout(finish, 420);
      else on(W, 'load', function () { W.setTimeout(finish, 260); });
      /* 万一 load 一直不来（有张图挂了），也别把门焊死 */
      W.setTimeout(finish, 2600);
    }

    /* 进度是"感觉"出来的：先快后慢爬到 92%，真正的 100% 留给 finish。
       真实资源进度拿不到（我们不掌控图片），装一个假的反而更假。 */
    function tick(ts) {
      if (done) return;
      var e = (ts - t0) / 1000;
      var p = Math.min(92, 8 + 84 * (1 - Math.pow(1 - Math.min(1, e / 1.15), 2.1)));
      paint(p);
      raf = W.requestAnimationFrame(tick);
    }
    function paint(p) {
      var n = Math.round(p);
      if (fill) fill.style.width = n + '%';
      if (pct) pct.textContent = (n < 100 ? '0' : '') + (n < 10 ? '0' : '') + n;
    }

    function finish() {
      if (done) return;
      done = true;
      if (raf) { try { W.cancelAnimationFrame(raf); } catch (e) {} raf = null; }
      paint(100);
      /* 有门才需要"至少亮一会儿"；没有门（登录/注册那套独立骨架）就该立刻放行，
         否则会白屏半秒 —— 那比没动画更糟。 */
      var wait = box ? Math.max(0, 520 - (performance.now() - t0)) : 0;
      W.setTimeout(function () {
        doc.classList.remove('u-boot');       // 门开始淡出
        doc.classList.add('u-ready');
        if (open) { try { open(); } catch (e) {} }   // 门开了，首屏内容才开始落位
        W.setTimeout(function () {
          if (box && box.parentNode) box.parentNode.removeChild(box);
        }, 700);
      }, wait);
    }
    return { init: init };
  })();

  /* ══════════════════════════ ⑤ 视角折叠 ══════════════════════════ */
  var Fold = (function () {
    var groups = [];

    function init(root) {
      var fresh = $$('[data-fold]', root).filter(function (g) {
        if (g.getAttribute('data-fold-bnd') === '1') return false;
        g.setAttribute('data-fold-bnd', '1');
        return true;
      });
      if (!fresh.length) return;

      fresh.forEach(function (g) {
        var items = $$('[data-fold-item]', g);
        if (!items.length) return;

        /* 入场：整组先"折进去"，滚到眼前再展开。
           阈值压到 0.01、底边距只留 4% —— 之前用 0.08 + -10% 时，
           首屏下半部分刚露出一点点的区块永远等不到 is-in（票卡就那样一直隐形）。
           再补一次"当场量一遍"：init 的时候已经进视口的，立刻展开，不等回调。 */
        if (!REDUCE && 'IntersectionObserver' in W) {
          g.classList.add('u-fold--in');
          var io = new IntersectionObserver(function (es) {
            es.forEach(function (e) {
              if (e.isIntersecting) { g.classList.add('is-in'); io.unobserve(g); }
            });
          }, { rootMargin: '0px 0px -4% 0px', threshold: 0.01 });
          io.observe(g);
          soon(function () {
            if (g.getAttribute('data-fold-in') === '1') return;
            try {
              var r = g.getBoundingClientRect();
              if (r.top < (W.innerHeight || 0) * 0.99 && r.bottom > 0) {
                g.setAttribute('data-fold-in', '1');
                g.classList.add('is-in');
                io.unobserve(g);
              }
            } catch (e2) {}
          });
        }

        var rec = { g: g, items: items, cur: null, tilts: [] };
        items.forEach(function (it) { rec.tilts.push({ el: it, tx: 0, ty: 0, cx: 0, cy: 0 }); });
        groups.push(rec);

        on(g, 'pointerover', function (e) {
          var it = e.target.closest('[data-fold-item]');
          if (!it || items.indexOf(it) < 0) return;
          g.classList.add('is-focus');
          rec.cur = it;
          items.forEach(function (x) { x.classList.toggle('is-cur', x === it); });
        });
        on(g, 'pointermove', function (e) {
          var it = e.target.closest('[data-fold-item]');
          if (!it || items.indexOf(it) < 0) return;
          var t = rec.tilts[items.indexOf(it)];
          if (!t) return;
          var r = it.getBoundingClientRect();
          var nx = clamp((e.clientX - r.left) / Math.max(1, r.width), 0, 1) * 2 - 1;
          var ny = clamp((e.clientY - r.top) / Math.max(1, r.height), 0, 1) * 2 - 1;
          t.ty = nx * 7.5;          // 横向强一点：像翻卡片
          t.tx = -ny * 5.5;
        });
        on(g, 'pointerleave', function () {
          g.classList.remove('is-focus');
          rec.cur = null;
          items.forEach(function (x) { x.classList.remove('is-cur'); });
          rec.tilts.forEach(function (t) { t.tx = 0; t.ty = 0; });
        });
      });

      if (!REDUCE) { addTick(step); startLoop(); }
    }

    function step(dt) {
      var f = 1 - Math.pow(0.004, dt);
      for (var i = 0; i < groups.length; i++) {
        var ts = groups[i].tilts;
        for (var j = 0; j < ts.length; j++) {
          var t = ts[j];
          if (Math.abs(t.cx - t.tx) < 0.02 && Math.abs(t.cy - t.ty) < 0.02) continue;
          t.cx = lerp(t.cx, t.tx, f);
          t.cy = lerp(t.cy, t.ty, f);
          t.el.style.setProperty('--fx', t.cx.toFixed(2) + 'deg');
          t.el.style.setProperty('--fy', t.cy.toFixed(2) + 'deg');
        }
      }
    }

    return { init: init };
  })();

  /* ══════════════════════════ ④ 画面切换（无缝换页） ══════════════════════════ */
  var Transit = (function () {
    var busy = false;
    var veil, main, dust;
    /* 这些脚本是"壳层级"的：换页时**不能**重跑（重跑会重复绑事件）。
       其余（如 library.js）属于页面级，必须跟着新内容重新执行。 */
    var SHELL_JS = /(^|\/)(csrf|upload|tabs|emojisvg|nova)\.js/i;

    function init() {
      veil = $('#uVeil'); main = $('#uMain'); dust = $('#uDust');
      if (!main) return;
      on(D, 'click', click);
      on(W, 'popstate', function () { location.reload(); });   // 后退：老实整页加载，最稳

      /* 内容里还挂了老的 data-curtain 就顺带兼容一下 */
      on(D, 'click', function (e) {
        var a = e.target.closest && e.target.closest('a[data-curtain]');
        if (a) Field.emit(e.clientX / W.innerWidth, e.clientY / W.innerHeight, 1);
      });
    }

    function click(e) {
      if (busy || REDUCE) return;
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      var a = e.target.closest && e.target.closest('a');
      if (!a) return;
      if (a.target === '_blank' || a.hasAttribute('download') || a.hasAttribute('data-no-transit')) return;
      if (a.hasAttribute('data-ask') || a.hasAttribute('data-nofetch')) return;
      var href = a.getAttribute('href') || '';
      if (!href || href.charAt(0) === '#' || /^(mailto:|tel:|javascript:|blob:)/i.test(href)) return;
      var url;
      try { url = new URL(a.href, location.href); } catch (err) { return; }
      if (url.origin !== location.origin) return;
      /* 表单外的外链、后台、DM 工作台：老老实实整页跳，别在这上面耍花样 */
      if (/^\/(admin|dm)(\/|$)/.test(url.pathname)) return;
      /* 只是换 query（筛选）时走前端 fetch，不惊动整页 */
      if (url.pathname === location.pathname && url.search) return;

      e.preventDefault();
      go(url.href);
    }

    function go(url) {
      busy = true;
      var t0 = performance.now();

      /* ① 现在的画面错峰升起淡出 */
      main.classList.remove('u-enter-page');
      main.classList.add('is-out');
      Array.prototype.slice.call(main.children).forEach(function (el, i) {
        el.style.setProperty('--us-delay', Math.min(i * 45, 260) + 'ms');
      });
      if (dust) dust.classList.add('is-on');
      if (Field.ok()) { Field.emit(0.5, 0.5, 0.8); Field.emit(0.35, 0.4, 0.6); }

      /* ② 纸幕盖上来（配合 fetch 并行跑，谁慢等谁） */
      var fetched = null, failed = false;
      var req = fetch(url, { headers: { 'X-Requested-With': 'fetch', 'Accept': 'text/html' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
        .then(function (html) { fetched = html; })
        .catch(function () { failed = true; });

      var MIN_OUT = 380;   // 至少让"出去"这段动画走完，别闪一下就走

      function cover() {
        if (failed) { location.href = url; return; }
        var wait = Math.max(0, MIN_OUT - (performance.now() - t0));
        W.setTimeout(function () {
          Promise.resolve(req).then(function () {
            if (failed || fetched == null) { location.href = url; return; }
            if (veil) veil.classList.add('is-on');
            W.setTimeout(function () { swap(url, fetched); }, 200);
          });
        }, wait);
      }
      cover();
    }

    function swap(url, html) {
      var doc2;
      try { doc2 = new DOMParser().parseFromString(html, 'text/html'); } catch (e) { doc2 = null; }
      var fresh = doc2 && doc2.querySelector('#uMain');
      var freshTop = doc2 && doc2.querySelector('.u-top');
      var freshFoot = doc2 && doc2.querySelector('.u-foot');
      var freshTabs = doc2 && doc2.querySelector('.u-mobtab');
      if (!fresh) { location.href = url; return; }

      /* 顶栏（登录态 / 未读数会变）、页脚、手机底栏一并换掉，
         否则换页之后"我的"还是未登录的样子 —— 这种不一致最伤可信度 */
      try {
        if (freshTop) { var oldTop = $('.u-top'); if (oldTop) oldTop.replaceWith(freshTop); }
        if (freshFoot) { var oldFoot = $('.u-foot'); if (oldFoot) oldFoot.replaceWith(freshFoot); }
        if (freshTabs) { var oldTabs = $('.u-mobtab'); if (oldTabs) oldTabs.replaceWith(freshTabs); }
      } catch (e) {}

      main.replaceWith(fresh);
      main = fresh;
      main.classList.remove('is-out');
      main.classList.add('u-enter-page');

      /* 标题与 OG 也跟着换 */
      try {
        var t = doc2.querySelector('title');
        if (t) D.title = t.textContent;
        var og = doc2.querySelector('meta[property="og:title"]');
        var mine = D.querySelector('meta[property="og:title"]');
        if (og && mine) mine.setAttribute('content', og.getAttribute('content') || '');
      } catch (e) {}

      runScripts(fresh, doc2);
      try { history.pushState({ us: 1 }, '', url); } catch (e) {}
      W.scrollTo(0, 0);

      /* 重新绑定所有"页面级"实例（揭示推迟两帧再跑：得先让浏览器画出 opacity:0 那一帧） */
      boot(main, true);
      soon(function () { try { Base.reveal(main); } catch (e) {} });
      /* 通知壳层：画面已经换了（导航下划线要跟着新的当前项重新落位） */
      try { W.dispatchEvent(new Event('nv:navigated')); } catch (e) {}

      /* ③ 纸幕撤掉，新内容错峰落位 */
      if (veil) veil.classList.remove('is-on');
      W.setTimeout(function () {
        main.classList.remove('u-enter-page');
        if (dust) dust.classList.remove('is-on');
        busy = false;
      }, 620);
    }

    /* 换页后把"页面级脚本"重跑一遍（壳层的不动）。
       浏览器有缓存，重跑一次的成本几乎为零，但少了它 library.js 这类
       只认第一次 DOM 的脚本就再也不会工作了。 */
    function runScripts(scope, doc2) {
      /* ① main 里的内联脚本（例如 scripts 页的 window.TS_LIB） */
      $$('script', scope).forEach(function (old) {
        if (old.src) return;
        var s = D.createElement('script');
        if (old.type) s.type = old.type;
        s.textContent = old.textContent;
        old.parentNode.replaceChild(s, old);
      });
      /* ② 全文档里的外链脚本，跳过壳层那几个 */
      var have = {};
      $$('script[src]').forEach(function (s) { have[s.src] = 1; });
      $$('script[src]', doc2).forEach(function (old) {
        var src = old.getAttribute('src') || '';
        if (!src || SHELL_JS.test(src)) return;
        var abs = old.src || src;
        if (have[abs]) {
          /* 已经在文档里 —— 摘掉再插回，强制重跑 */
          var ex = $$('script[src]').filter(function (s) { return (s.src || '') === abs; })[0];
          if (ex && ex.parentNode) ex.parentNode.removeChild(ex);
        }
        var s = D.createElement('script');
        s.src = src;
        if (old.defer) s.defer = true;
        D.body.appendChild(s);
      });
    }

    return { init: init };
  })();

  /* ══════════════════════════ 启动 ══════════════════════════ */
  var setMenu = null;

  function boot(root, skipReveal) {
    /* 首屏的揭示要等入场门开了再跑 —— 否则那一串错峰落位全在门后面演完了，
       用户推开门只看到一张静止的图。skipReveal 就是为这个留的。 */
    if (!skipReveal) Base.reveal(root);
    Base.counts(root);
    Base.magnets(root);
    Base.busy(root);
    Base.accordion(root);
    Base.panes(root);
    Search.init(root);
    Fold.init(root);
    /* tabs.js 只在首屏 DOMContentLoaded 绑一次，转场换进来的新标签条没人管 ——
       叫它重跑一遍（它自己带幂等守卫，只会处理新增的节点）。 */
    if (W.TS_TABS && W.TS_TABS.boot) { try { W.TS_TABS.boot(); } catch (e) {} }
  }

  function ready() {
    if (D.documentElement.classList.contains('u-on')) { boot(D); return; }

    /* 亮灯：从这一刻起 CSS 里所有 html.u-on 前缀的规则才生效。
       没跑这段的页面（后台、无 JS）就是一份纯静态文档。 */
    doc.classList.add('u-on');

    Field.init();
    Sway.init();
    Cursor.init();
    Smooth.init();
    setMenu = Base.menu();
    Base.topbar();
    Base.navUl();
    Transit.init();
    boot(D, true);

    /* 门一开，首屏才开始落位 */
    Boot.init(function () { Base.reveal(D); });

    /* 转场换页之后，导航下划线要对着新页的当前项重新落位 */
    on(W, 'nv:navigated', function () { Base.navUl(); });

    /* 主题切换后，画布里的柔光色要跟着换 —— 否则深色模式下背景还是浅色的 */
    on(D, 'click', function (e) {
      var a = e.target.closest && e.target.closest('a[href*="/theme"]');
      if (a) W.setTimeout(function () { doc.setAttribute('data-theme', doc.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'); Field.repaint(); }, 40);
    });
  }

  /* 对外只暴露一个重绑入口：页面自己的脚本（library.js 换网格）
     替换了 DOM 之后调一下，新的节点才会挂上揭示 / 折叠 / 光标状态。 */
  W.NV = {
    rebind: function (root) { try { boot(root || D); } catch (e) {} },
    ripple: function (x, y) { Field.emit(typeof x === 'number' ? x : 0.5, typeof y === 'number' ? y : 0.5, 1); },
    ready: function () { return doc.classList.contains('u-on'); }
  };

  if (D.readyState === 'loading') on(D, 'DOMContentLoaded', ready);
  else ready();
})();
