/* ============================================================================
   Unseen · 暗场实时噪声场（零依赖 WebGL，替换 2D radial-gradient 追光）
   —— 全屏片元着色器：fbm 域扭曲暗场烟雾 + 光标暖光 + 光标「雕刻」光迹
      + 分章演化（随滚动 uChapter 调制噪声尺度/色相/雕刻强度）
      + 胶片颗粒 + 暗角 + 廉价色散。WebGL1 兼容；无 WebGL 回退 CSS 渐变。
   挂载：<canvas class="field" data-field>，由 layout 全局放置。
   ========================================================================== */
(function () {
  'use strict';
  var canvas = document.querySelector('[data-field]');
  if (!canvas) return;
  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var gl = canvas.getContext('webgl', { antialias: false, alpha: false, depth: false, stencil: false, powerPreference: 'high-performance' })
        || canvas.getContext('experimental-webgl', { antialias: false, alpha: false, depth: false, stencil: false });
  if (!gl) { document.documentElement.classList.add('no-field'); canvas.style.display = 'none'; return; }

  var VERT = [
    'attribute vec2 aPos;',
    'void main(){ gl_Position = vec4(aPos, 0.0, 1.0); }'
  ].join('\n');

  var FRAG = [
    '#ifdef GL_FRAGMENT_PRECISION_HIGH',
    'precision highp float;',
    '#else',
    'precision mediump float;',
    '#endif',
    'uniform vec2  uRes;',
    'uniform float uTime;',
    'uniform vec2  uMouse;',       // 光标像素坐标（左上原点）
    'uniform float uMouseAmt;',    // 光标活跃度 0..1
    'uniform float uChapter;',     // 0..1 章节进度（滚动驱动）
    'uniform vec3  uTrail[16];',   // 光迹：xy 像素坐标，z 年龄 0(新)..1(将逝)
    'uniform int   uTrailN;',
    'float hash(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y); }',
    'float noise(vec2 p){',
    '  vec2 i=floor(p), f=fract(p);',
    '  float a=hash(i), b=hash(i+vec2(1.,0.)), c=hash(i+vec2(0.,1.)), d=hash(i+vec2(1.,1.));',
    '  vec2 u=f*f*(3.-2.*f);',
    '  return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);',
    '}',
    'float fbm(vec2 p){',
    '  float v=0.0, a=0.5;',
    '  for(int i=0;i<5;i++){ v+=a*noise(p); p=p*2.02+vec2(1.7,9.2); a*=0.5; }',
    '  return v;',
    '}',
    'void main(){',
    '  vec2 uv = vec2(gl_FragCoord.x/uRes.x, 1.0 - gl_FragCoord.y/uRes.y);', // 左上原点，与 CSS/鼠标一致
    '  float asp = uRes.x/uRes.y;',
    '  vec2 p = vec2((uv.x-0.5)*asp, uv.y-0.5);',
    '  vec2 m = vec2((uMouse.x/uRes.x-0.5)*asp, uMouse.y/uRes.y-0.5);',
    '  float t = uTime*0.055;',
    '  float ch = uChapter;',
    // 域扭曲噪声（两层流向相反）
    '  vec2 q = p*1.55 + vec2(t, -t*0.72);',
    '  q += vec2(fbm(q*0.8 + t*0.6), fbm(q*0.8 - t*0.6 + 3.1))*0.85;',
    '  float nR = fbm(q*1.1 + vec2(0.010,0.0) + ch*2.0);',
    '  float nG = fbm(q*1.1 + ch*2.0);',
    '  float nB = fbm(q*1.1 - vec2(0.010,0.0) + ch*2.0);',
    '  float n2 = fbm(q*2.35 - ch*3.0 + 7.0);',
    '  float smoke = smoothstep(0.18, 0.98, nG*0.72 + n2*0.45);',
    // 光标暖光
    '  vec2 dm = p - m;',
    '  float gl0 = exp(-length(dm)*3.1) * (0.42 + uMouseAmt*0.85);',
    // 光标「雕刻」光迹
    '  float carve = 0.0;',
    '  for(int i=0;i<16;i++){',
    '    if(i >= uTrailN) break;',
    '    vec3 tp = uTrail[i];',
    '    vec2 tpv = vec2((tp.x/uRes.x-0.5)*asp, (tp.y/uRes.y-0.5));',
    '    float dd = length(p - tpv);',
    '    carve += exp(-dd*15.0) * (1.0 - tp.z);',
    '  }',
    '  carve = clamp(carve*0.42*(0.6+ch*0.8), 0.0, 1.6);',
    // 配色
    '  vec3 base  = vec3(0.030,0.026,0.022);',
    '  vec3 ember = vec3(0.812,0.353,0.196);',   // #CF5A32
    '  vec3 amber = vec3(0.886,0.580,0.278);',   // #E29447
    '  vec3 cool  = vec3(0.16,0.19,0.30);',
    '  vec3 col = base;',
    '  col.r += smoke*0.36*mix(cool.r, ember.r, ch) + (nR-nG)*0.28;',
    '  col.g += smoke*0.36*mix(cool.g, ember.g, ch);',
    '  col.b += smoke*0.36*mix(cool.b, ember.b, ch) + (nB-nG)*0.28;',
    '  col += gl0  * amber * 0.55;',
    '  col += carve* vec3(1.0,0.86,0.66) * 0.55;',
    // 顶部一束极弱光带，制造纵深
    '  col += vec3(0.10,0.075,0.055) * smoothstep(0.42,0.0,uv.y) * (0.6+0.4*ch);',
    // 暗角
    '  float vig = smoothstep(1.30, 0.32, length(uv-0.5)*1.42);',
    '  col *= 0.5 + 0.66*vig;',
    // 胶片颗粒
    '  col += (hash(uv*uRes + fract(uTime))-0.5)*0.045;',
    // 微弱扫描线
    '  col *= 1.0 - 0.03*step(0.5, fract(uv.y*uRes.y*0.5));',
    '  gl_FragColor = vec4(max(col,0.0), 1.0);',
    '}'
  ].join('\n');

  function compile(type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error('[field]', gl.getShaderInfoLog(s)); return null; }
    return s;
  }
  var vs = compile(gl.VERTEX_SHADER, VERT), fs = compile(gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) { document.documentElement.classList.add('no-field'); canvas.style.display = 'none'; return; }
  var prog = gl.createProgram(); gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { console.error('[field]', gl.getProgramInfoLog(prog)); document.documentElement.classList.add('no-field'); canvas.style.display = 'none'; return; }
  gl.useProgram(prog);

  var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW); // 覆盖全屏的大三角
  var aPos = gl.getAttribLocation(prog, 'aPos'); gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
  gl.viewport(0, 0, canvas.width, canvas.height);

  var U = {
    res: gl.getUniformLocation(prog, 'uRes'),
    time: gl.getUniformLocation(prog, 'uTime'),
    mouse: gl.getUniformLocation(prog, 'uMouse'),
    amt: gl.getUniformLocation(prog, 'uMouseAmt'),
    chapter: gl.getUniformLocation(prog, 'uChapter'),
    trail: gl.getUniformLocation(prog, 'uTrail'),
    trailN: gl.getUniformLocation(prog, 'uTrailN')
  };

  /* ---- 尺寸（DPR 封顶 1.5）---- */
  var dpr = 1;
  function resize() {
    dpr = Math.min(1.5, window.devicePixelRatio || 1);
    canvas.width = Math.max(1, Math.floor(innerWidth * dpr));
    canvas.height = Math.max(1, Math.floor(innerHeight * dpr));
    canvas.style.width = innerWidth + 'px'; canvas.style.height = innerHeight + 'px';
    gl.viewport(0, 0, canvas.width, canvas.height);
    if (U.res) gl.uniform2f(U.res, canvas.width, canvas.height);
    renderFrame();
  }
  addEventListener('resize', resize, { passive: true });

  /* ---- 光标 + 光迹 ---- */
  var mx = innerWidth * 0.62, my = innerHeight * 0.42;  // 平滑后（用于暖光）
  var tmx = mx, tmy = my;                                // 目标
  var amt = 0, tAmt = 0;
  var trail = [];                                        // {x,y,t0}
  var TRAIL_MAX = 16, TRAIL_LIFE = 1300;                 // ms
  function pushTrail(x, y) {
    var last = trail[trail.length - 1];
    if (last && Math.hypot(x - last.x, y - last.y) < 14) return;
    trail.push({ x: x, y: y, t0: performance.now() });
    if (trail.length > TRAIL_MAX) trail.shift();
  }
  function onMove(x, y) { tmx = x; tmy = y; tAmt = 1; pushTrail(x, y); }
  addEventListener('mousemove', function (e) { onMove(e.clientX, e.clientY); }, { passive: true });
  addEventListener('pointermove', function (e) { if (e.pointerType !== 'mouse') onMove(e.clientX, e.clientY); }, { passive: true });
  addEventListener('touchmove', function (e) { if (e.touches[0]) onMove(e.touches[0].clientX, e.touches[0].clientY); }, { passive: true });

  /* ---- 章节（滚动驱动）---- */
  var chapter = 0, chapterTarget = 0;
  function onScroll() {
    var max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    chapterTarget = Math.min(1, Math.max(0, scrollY / max));
  }
  addEventListener('scroll', onScroll, { passive: true }); onScroll();

  /* ---- 渲染循环 ---- */
  var trailData = new Float32Array(TRAIL_MAX * 3);
  var running = true, t0 = performance.now();
  function render(now) {
    if (!running) return;
    var time = (now - t0) / 1000;
    mx += (tmx - mx) * 0.12; my += (tmy - my) * 0.12;
    amt += (tAmt - amt) * 0.05; tAmt *= 0.96;
    chapter += (chapterTarget - chapter) * 0.06;

    // 光迹年龄 / 淘汰
    var k = 0, nowMs = now;
    for (var i = 0; i < trail.length; i++) {
      var age = (nowMs - trail[i].t0) / TRAIL_LIFE;
      if (age >= 1) continue;
      trailData[k * 3] = trail[i].x * dpr; trailData[k * 3 + 1] = trail[i].y * dpr; trailData[k * 3 + 2] = age;
      k++;
    }
    gl.uniform2f(U.mouse, mx * dpr, my * dpr);
    gl.uniform1f(U.amt, Math.min(1, amt));
    gl.uniform1f(U.time, time);
    gl.uniform1f(U.chapter, chapter);
    if (U.trail) gl.uniform3fv(U.trail, trailData);
    if (U.trailN) gl.uniform1i(U.trailN, k);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    requestAnimationFrame(render);
  }
  function renderFrame() {
    var now = performance.now();
    mx = tmx; my = tmy;
    gl.uniform2f(U.mouse, mx * dpr, my * dpr);
    gl.uniform1f(U.amt, 1); gl.uniform1f(U.time, (now - t0) / 1000); gl.uniform1f(U.chapter, chapterTarget);
    gl.uniform1i(U.trailN, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { running = false; }
    else if (running === false) { running = true; requestAnimationFrame(render); }
  });

  resize();
  if (REDUCE) { running = false; renderFrame(); }   // 减弱动效：静态渲染一帧
  else { requestAnimationFrame(render); }
})();
