/* ============================================================================
   Unseen · 暗场实时场
   —— 优先：WebGL2 真 GPU 流体（Navier-Stokes：速度场 + 散度 + Jacobi 压力投影
      + 半拉格朗日平流 + 光标力注入），拼进 fbm 暗场 → 光标划过的"水一样"流动。
   —— 兜底：无 WebGL2/浮点渲染时退回 WebGL1 的 fbm 域扭曲噪声场。
   —— 再兜底：都不可用 → html.no-field（CSS 渐变）。
   纯零依赖。挂载：<canvas class="field-canvas" data-field>
   （类名别叫 .field —— 表单字段占着这个名字，见 unseen.css 的 forms 段）
   ========================================================================== */
(function () {
  'use strict';
  var canvas = document.querySelector('[data-field]');
  if (!canvas) return;
  /* 暗场流体画布已默认退役（layout 的 <html class="no-field">）：浅暖亮场下不再需要暗场背景，
     直接跳过 WebGL 初始化以省 GPU / 防掉帧。要回暗场沉浸时，把 no-field 去掉即可。 */
  if (document.documentElement.classList.contains('no-field')) { canvas.style.display = 'none'; return; }
  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* 渲染分辨率系数：这是块「软噪声背景」，不需要满分辨率——0.55 倍靠 CSS 放大后肉眼几乎无差，
     但填充率省约 3 倍。它曾经是整站掉帧的头号原因（满分辨率 × 每像素 6 次 fbm × 5 层）。*/
  var RENDER_SCALE = REDUCE ? 1 : 0.55;

  function noField() { document.documentElement.classList.add('no-field'); canvas.style.display = 'none'; }

  var VERT_QUAD = [
    'attribute vec2 aPos; varying vec2 vUv;',
    'void main(){ vUv = aPos*0.5+0.5; gl_Position = vec4(aPos,0.0,1.0); }'
  ].join('\n');

  /* ======================= 公共：fbm 片段片元（显示用） ======================= */
  var FBM_BLOCK = [
    'float hash(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y); }',
    'float noise(vec2 p){ vec2 i=floor(p), f=fract(p); float a=hash(i),b=hash(i+vec2(1.,0.)),c=hash(i+vec2(0.,1.)),d=hash(i+vec2(1.,1.)); vec2 u=f*f*(3.-2.*f); return mix(mix(a,b,u.x),mix(c,d,u.x),u.y); }',
    'float fbm(vec2 p){ float v=0.0,a=0.5; for(int i=0;i<4;i++){ v+=a*noise(p); p=p*2.02+vec2(1.7,9.2); a*=0.5; } return v; }'
  ].join('\n');

  /* ======================================================================
     路径 A：WebGL2 真 GPU 流体
     ====================================================================== */
  function initFluid(gl) {
    gl.getExtension('EXT_color_buffer_float');
    gl.getExtension('OES_texture_float_linear');

    function sh(t, src) {
      var s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error('[field]', gl.getShaderInfoLog(s)); return null; }
      return s;
    }
    function prog(frag) {
      var p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, VERT_QUAD)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, frag));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) { console.error('[field]', gl.getProgramInfoLog(p)); return null; }
      return p;
    }
    function U(p, names) { var o = {}; names.forEach(function (n) { o[n] = gl.getUniformLocation(p, n); }); return o; }

    var F_SPLAT = [
      'precision highp float; varying vec2 vUv;',
      'uniform sampler2D uTarget; uniform float uAspect; uniform vec3 uPoint; uniform vec2 uForce;',
      'void main(){ vec2 p=vUv-uPoint.xy; p.x*=uAspect; vec3 s=exp(-dot(p,p)/uPoint.z)*vec3(uForce,0.0);',
      '  gl_FragColor = vec4(texture2D(uTarget,vUv).xyz + s, 1.0); }'
    ].join('\n');
    var F_ADVECT = [
      'precision highp float; varying vec2 vUv;',
      'uniform sampler2D uVelocity; uniform sampler2D uSource; uniform vec2 uTexel; uniform float uDt; uniform float uDissipation;',
      'void main(){ vec2 coord = vUv - uDt * texture2D(uVelocity,vUv).xy * uTexel;',
      '  gl_FragColor = uDissipation * texture2D(uSource, coord); gl_FragColor.a = 1.0; }'
    ].join('\n');
    var F_DIVERGENCE = [
      'precision highp float; varying vec2 vUv;',
      'uniform sampler2D uVelocity; uniform vec2 uTexel;',
      'void main(){ float L=texture2D(uVelocity,vUv-vec2(uTexel.x,0.)).x; float R=texture2D(uVelocity,vUv+vec2(uTexel.x,0.)).x;',
      '  float B=texture2D(uVelocity,vUv-vec2(0.,uTexel.y)).y; float T=texture2D(uVelocity,vUv+vec2(0.,uTexel.y)).y;',
      '  gl_FragColor = vec4(0.5*((R-L)+(T-B)),0.0,0.0,1.0); }'
    ].join('\n');
    var F_PRESSURE = [
      'precision highp float; varying vec2 vUv;',
      'uniform sampler2D uPressure; uniform sampler2D uDivergence; uniform vec2 uTexel;',
      'void main(){ float L=texture2D(uPressure,vUv-vec2(uTexel.x,0.)).x; float R=texture2D(uPressure,vUv+vec2(uTexel.x,0.)).x;',
      '  float B=texture2D(uPressure,vUv-vec2(0.,uTexel.y)).x; float T=texture2D(uPressure,vUv+vec2(0.,uTexel.y)).x;',
      '  float div=texture2D(uDivergence,vUv).x; gl_FragColor = vec4((L+R+B+T-div)*0.25,0.0,0.0,1.0); }'
    ].join('\n');
    var F_GRADIENT = [
      'precision highp float; varying vec2 vUv;',
      'uniform sampler2D uPressure; uniform sampler2D uVelocity; uniform vec2 uTexel;',
      'void main(){ float L=texture2D(uPressure,vUv-vec2(uTexel.x,0.)).x; float R=texture2D(uPressure,vUv+vec2(uTexel.x,0.)).x;',
      '  float B=texture2D(uPressure,vUv-vec2(0.,uTexel.y)).x; float T=texture2D(uPressure,vUv+vec2(0.,uTexel.y)).x;',
      '  vec2 v=texture2D(uVelocity,vUv).xy - vec2(R-L,T-B)*0.5; gl_FragColor = vec4(v,0.0,1.0); }'
    ].join('\n');
    var F_DISPLAY = [
      '#ifdef GL_FRAGMENT_PRECISION_HIGH', 'precision highp float;', '#else', 'precision mediump float;', '#endif',
      'varying vec2 vUv;',
      'uniform sampler2D uVelocity; uniform vec2 uRes; uniform float uFlow; uniform float uChapter;',
      'uniform vec2 uMouse; uniform float uMouseAmt; uniform vec3 uTrail[16]; uniform int uTrailN;',
      FBM_BLOCK,
      'void main(){',
      '  float asp = uRes.x/uRes.y;',
      '  vec2 vel = texture2D(uVelocity, vUv).xy;',
      '  vec2 q = vec2((vUv.x-0.5)*asp, (vUv.y-0.5));',
      '  q += clamp(vel,-0.10,0.10) * 0.009;',                  // 流体位移限幅
      '  float t = uFlow, ch = uChapter;',                       // ★ 相位只跟"用户移动量"走：不动就不动
      '  vec2 w = q*1.5 + vec2(t*0.55,-t*0.40);',
      '  w += fbm(w*0.8 + t*0.30) * vec2(0.86, 0.62);',              // 1 次 fbm 完成域扭曲（原 2 次）
      '  float nG = fbm(w*1.1 + ch*2.0);',                            // 主结构（原 nR/nG/nB 三次，现一次）
      '  float n2 = fbm(w*2.35 - ch*3.0 + 7.0);',                     // 细节（原 n2）
      '  float smoke = smoothstep(0.50,1.26, nG*0.70 + n2*0.40);',   // 结构更少、更淡
      '  vec2 p = vec2((vUv.x-0.5)*asp, vUv.y-0.5); vec2 m = vec2((uMouse.x-0.5)*asp, uMouse.y-0.5);',
      '  float lit = exp(-length(p-m)*(3.2 - ch*0.6));',             // "被照亮"的宽域（决定哪里允许暖）
      '  float gl0 = exp(-length(p-m)*(9.5 - ch*1.4)) * (0.04 + uMouseAmt*0.11);',   // 收紧的光核
      '  float carve = 0.0;',
      '  for(int i=0;i<16;i++){ if(i>=uTrailN) break; vec3 tp=uTrail[i]; vec2 tv=vec2((tp.x-0.5)*asp, tp.y-0.5);',
      '    carve += exp(-length(p-tv)*18.0)*(1.0-tp.z); }',
      '  carve = clamp(carve*0.20*(0.5+ch*0.7),0.0,0.7);',
      '  vec3 base=vec3(0.012,0.013,0.018);',                       // 冷近黑
      '  vec3 cool=vec3(0.034,0.046,0.076);',                       // 冷调烟雾
      // 光色随"叙事进度"变：幕一朱砂橙 → 中段琥珀 → 末幕偏玫瑰（仍留在暖色家族内）
      '  vec3 warmA=vec3(0.62,0.27,0.11);',
      '  vec3 warmB=vec3(0.60,0.40,0.16);',
      '  vec3 warmC=vec3(0.46,0.20,0.22);',
      '  vec3 warm=mix(mix(warmA,warmB,smoothstep(0.0,0.55,ch)), warmC, smoothstep(0.55,1.0,ch));',
      '  vec3 col = base;',
      '  col += smoke * mix(cool, warm*0.55, lit*0.60) * 0.26;',    // 越靠近光才越暖
      '  float disp = sin(w.x*53.0 + w.y*29.0);',                    // 廉价色散（原要 2 次 fbm）
      '  col.r += disp*0.022; col.b -= disp*0.022;',
      '  col += gl0 * warm * 0.55;',
      '  col += carve * vec3(0.90,0.58,0.30) * 0.26;',
      '  float vig = smoothstep(1.18,0.16, length(vUv-0.5)*1.5); col *= 0.26 + 0.82*vig;',
      '  col += (hash(vUv*vec2(1600.0,900.0)*1.7+11.0)-0.5)*0.028;', // 静态颗粒（按屏幕尺度，与渲染分辨率解耦）
      '  gl_FragColor = vec4(max(col,0.0),1.0);',
      '}'
    ].join('\n');

    var pSplat = prog(F_SPLAT), pAdvect = prog(F_ADVECT), pDiv = prog(F_DIVERGENCE),
        pPress = prog(F_PRESSURE), pGrad = prog(F_GRADIENT), pDisp = prog(F_DISPLAY);
    if (!pSplat || !pAdvect || !pDiv || !pPress || !pGrad || !pDisp) return false;

    var uSplat = U(pSplat, ['uTarget', 'uAspect', 'uPoint', 'uForce']);
    var uAdv = U(pAdvect, ['uVelocity', 'uSource', 'uTexel', 'uDt', 'uDissipation']);
    var uDiv = U(pDiv, ['uVelocity', 'uTexel']);
    var uPress = U(pPress, ['uPressure', 'uDivergence', 'uTexel']);
    var uGrad = U(pGrad, ['uPressure', 'uVelocity', 'uTexel']);
    var uDisp = U(pDisp, ['uVelocity', 'uRes', 'uFlow', 'uChapter', 'uMouse', 'uMouseAmt', 'uTrail', 'uTrailN']);

    // 全屏四边形
    var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    function bindQuad(p) { var a = gl.getAttribLocation(p, 'aPos'); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0); }
    function draw(p) { bindQuad(p); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); }

    // FBO
    function mkFBO(w, h, internal) {
      var tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, internal, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
      var fbo = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      var ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      return { tex: tex, fbo: fbo, w: w, h: h, ok: ok };
    }
    function mkDouble(w, h, internal) { var a = mkFBO(w, h, internal), b = mkFBO(w, h, internal); return { read: a, write: b, swap: function () { var t = this.read; this.read = this.write; this.write = t; } }; }

    var sim = { w: 0, h: 0, texel: [0, 0] }, velocity, divergence, pressure;
    var FMT = gl.RGBA16F;
    function initSim() {
      var long = 128;
      if (canvas.width >= canvas.height) { sim.w = long; sim.h = Math.max(1, Math.round(long * canvas.height / canvas.width)); }
      else { sim.h = long; sim.w = Math.max(1, Math.round(long * canvas.width / canvas.height)); }
      sim.texel = [1 / sim.w, 1 / sim.h];
      velocity = mkDouble(sim.w, sim.h, FMT);
      divergence = mkFBO(sim.w, sim.h, FMT);
      pressure = mkDouble(sim.w, sim.h, FMT);
      if (!velocity.read.ok || !divergence.ok || !pressure.read.ok) return false;
      return true;
    }

    function resize() {
      var dpr = Math.min(1, window.devicePixelRatio || 1) * RENDER_SCALE;
      canvas.width = Math.max(1, Math.floor(innerWidth * dpr));
      canvas.height = Math.max(1, Math.floor(innerHeight * dpr));
      canvas.style.width = innerWidth + 'px'; canvas.style.height = innerHeight + 'px';
      if (!sim.w || Math.abs(canvas.width / canvas.height - sim.w / sim.h) > 0.35) { if (!initSim()) return false; }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, canvas.width, canvas.height);
      return true;
    }

    // 鼠标 / 章节
    var mx = 0.62, my = 0.42, pmx = mx, pmy = my, amt = 0, tamt = 0, firstMove = true;
    var trail = [], TRAIL_MAX = 16, TRAIL_LIFE = 1300;
    function pushTrail(x, y) { var l = trail[trail.length - 1]; if (l && Math.hypot(x - l.x, y - l.y) < 0.02) return; trail.push({ x: x, y: y, t0: nowMs() }); if (trail.length > TRAIL_MAX) trail.shift(); }
    function nowMs() { return performance.now(); }
    function onMove(cx, cy) {
      var nx = cx / innerWidth, ny = 1 - cy / innerHeight;
      pmx = mx; pmy = my; mx = nx; my = ny; tamt = 1;
      if (firstMove) { pmx = nx; pmy = ny; firstMove = false; return; }
      pushTrail(nx, ny);
    }
    window.addEventListener('mousemove', function (e) { onMove(e.clientX, e.clientY); }, { passive: true });
    window.addEventListener('touchmove', function (e) { if (e.touches[0]) onMove(e.touches[0].clientX, e.touches[0].clientY); }, { passive: true });

    var chapter = 0, chapterTarget = 0, flow = 0;
    function onScroll() { var max = Math.max(1, document.documentElement.scrollHeight - innerHeight); chapterTarget = Math.min(1, Math.max(0, scrollY / max)); }
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();

    var SPLAT_FORCE = 6200, DISSIPATION = 0.975, PRESSURE_ITER = 22, CURL = 0;
    var trailData = new Float32Array(TRAIL_MAX * 3);
    var aspect = 1;

    function step(dt, now) {
      var mdx = mx - pmx, mdy = my - pmy;
      flow += Math.hypot(mdx, mdy) * 0.42;   // ★ 噪声相位由用户移动量累积；鼠标静止 → 画面完全静止
      var dx = mdx * SPLAT_FORCE, dy = mdy * SPLAT_FORCE;
      pmx = mx; pmy = my;
      if (Math.abs(dx) > 0.01 || Math.abs(dy) > 0.01) {
        gl.useProgram(pSplat); gl.uniform1i(uSplat.uTarget, 0); gl.uniform1f(uSplat.uAspect, aspect);
        gl.uniform3f(uSplat.uPoint, mx, my, 0.00035); gl.uniform2f(uSplat.uForce, dx, dy);
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, velocity.read.tex);
        gl.bindFramebuffer(gl.FRAMEBUFFER, velocity.write.fbo); gl.viewport(0, 0, sim.w, sim.h); draw(pSplat);
        velocity.swap();
      }
      // 速度自平流
      gl.useProgram(pAdvect); gl.uniform2f(uAdv.uTexel, sim.texel[0], sim.texel[1]);
      gl.uniform1f(uAdv.uDt, dt); gl.uniform1f(uAdv.uDissipation, DISSIPATION);
      gl.uniform1i(uAdv.uVelocity, 0); gl.uniform1i(uAdv.uSource, 0);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, velocity.read.tex);
      gl.bindFramebuffer(gl.FRAMEBUFFER, velocity.write.fbo); draw(pAdvect); velocity.swap();
      // 散度
      gl.useProgram(pDiv); gl.uniform2f(uDiv.uTexel, sim.texel[0], sim.texel[1]); gl.uniform1i(uDiv.uVelocity, 0);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, velocity.read.tex);
      gl.bindFramebuffer(gl.FRAMEBUFFER, divergence.fbo); draw(pDiv);
      // 压力 Jacobi
      gl.useProgram(pPress); gl.uniform2f(uPress.uTexel, sim.texel[0], sim.texel[1]);
      gl.uniform1i(uPress.uDivergence, 1);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, divergence.tex);
      gl.uniform1i(uPress.uPressure, 0);
      for (var i = 0; i < PRESSURE_ITER; i++) {
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, pressure.read.tex);
        gl.bindFramebuffer(gl.FRAMEBUFFER, pressure.write.fbo); draw(pPress); pressure.swap();
      }
      // 减压力梯度 → 无散度速度
      gl.useProgram(pGrad); gl.uniform2f(uGrad.uTexel, sim.texel[0], sim.texel[1]);
      gl.uniform1i(uGrad.uPressure, 0); gl.uniform1i(uGrad.uVelocity, 1);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, pressure.read.tex);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, velocity.read.tex);
      gl.bindFramebuffer(gl.FRAMEBUFFER, velocity.write.fbo); draw(pGrad); velocity.swap();

      // 光迹
      var k = 0;
      for (var j = 0; j < trail.length; j++) {
        var age = (now - trail[j].t0) / TRAIL_LIFE; if (age >= 1) continue;
        trailData[k * 3] = trail[j].x; trailData[k * 3 + 1] = trail[j].y; trailData[k * 3 + 2] = age; k++;
      }
      // 显示
      gl.useProgram(pDisp);
      gl.uniform1i(uDisp.uVelocity, 0); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, velocity.read.tex);
      gl.uniform2f(uDisp.uRes, canvas.width, canvas.height);
      gl.uniform1f(uDisp.uFlow, flow);
      gl.uniform1f(uDisp.uChapter, chapter);
      gl.uniform2f(uDisp.uMouse, mx, my);
      gl.uniform1f(uDisp.uMouseAmt, Math.min(1, amt));
      gl.uniform3fv(uDisp.uTrail, trailData); gl.uniform1i(uDisp.uTrailN, k);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, canvas.width, canvas.height); draw(pDisp);
    }

    if (!resize()) return false;
    var last = nowMs(), running = true;
    function loop(now) {
      if (!running) return;
      var dt = Math.min(0.033, (now - last) / 1000); last = now;
      amt += (tamt - amt) * 0.05; tamt *= 0.96; chapter += (chapterTarget - chapter) * 0.06;
      aspect = canvas.width / canvas.height;
      step(dt, now);
      requestAnimationFrame(loop);
    }
    window.addEventListener('resize', function () { if (running) resize(); }, { passive: true });
    document.addEventListener('visibilitychange', function () { if (document.hidden) running = false; else { running = true; last = nowMs(); requestAnimationFrame(loop); } });
    if (REDUCE) { aspect = canvas.width / canvas.height; step(0.016, nowMs()); }
    else requestAnimationFrame(loop);
    return true;
  }

  /* ======================================================================
     路径 B：WebGL1 fbm 兜底（原实现）
     ====================================================================== */
  function initFbm() {
    var gl = canvas.getContext('webgl', { antialias: false, alpha: false, depth: false }) || canvas.getContext('experimental-webgl');
    if (!gl) return false;
    function sh(t, s) { var x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) { console.error('[field]', gl.getShaderInfoLog(x)); return null; } return x; }
    var vs = sh(gl.VERTEX_SHADER, 'attribute vec2 aPos; void main(){ gl_Position=vec4(aPos,0.,1.); }');
    var frag = [
      '#ifdef GL_FRAGMENT_PRECISION_HIGH', 'precision highp float;', '#else', 'precision mediump float;', '#endif',
      'uniform vec2 uRes; uniform float uFlow; uniform vec2 uMouse; uniform float uMouseAmt; uniform float uChapter;',
      'uniform vec3 uTrail[16]; uniform int uTrailN;',
      FBM_BLOCK,
      'void main(){ vec2 uv=vec2(gl_FragCoord.x/uRes.x, 1.0-gl_FragCoord.y/uRes.y); float asp=uRes.x/uRes.y;',
      ' vec2 p=vec2((uv.x-0.5)*asp,uv.y-0.5); vec2 m=vec2((uMouse.x/uRes.x-0.5)*asp, uMouse.y/uRes.y-0.5);',
      ' float t=uFlow, ch=uChapter; vec2 q=p*1.5+vec2(t*0.55,-t*0.40);',
      ' q+=fbm(q*0.8+t*0.30)*vec2(0.86,0.62);',
      ' float nG=fbm(q*1.1+ch*2.0), n2=fbm(q*2.35-ch*3.0+7.0);',
      ' float smoke=smoothstep(0.50,1.26,nG*0.70+n2*0.40);',
      ' float lit=exp(-length(p-m)*(3.2-ch*0.6)); float gl0=exp(-length(p-m)*(9.5-ch*1.4))*(0.04+uMouseAmt*0.11); float carve=0.0;',
      ' for(int i=0;i<16;i++){ if(i>=uTrailN) break; vec3 tp=uTrail[i]; vec2 tv=vec2((tp.x/uRes.x-0.5)*asp,(tp.y/uRes.y-0.5));',
      '   carve+=exp(-length(p-tv)*18.0)*(1.0-tp.z); }',
      ' carve=clamp(carve*0.20*(0.5+ch*0.7),0.0,0.7);',
      ' vec3 base=vec3(0.012,0.013,0.018), cool=vec3(0.034,0.046,0.076);',
      ' vec3 warmA=vec3(0.62,0.27,0.11), warmB=vec3(0.60,0.40,0.16), warmC=vec3(0.46,0.20,0.22);',
      ' vec3 warm=mix(mix(warmA,warmB,smoothstep(0.0,0.55,ch)), warmC, smoothstep(0.55,1.0,ch));',
      ' vec3 col=base; col+=smoke*mix(cool,warm*0.55,lit*0.60)*0.26;',
      ' float disp=sin(q.x*53.0+q.y*29.0); col.r+=disp*0.022; col.b-=disp*0.022;',
      ' col+=gl0*warm*0.55; col+=carve*vec3(0.90,0.58,0.30)*0.26;',
      ' float vig=smoothstep(1.18,0.16,length(uv-0.5)*1.5); col*=0.26+0.82*vig;',
      ' col+=(hash(uv*vec2(1600.0,900.0)*1.7+11.0)-0.5)*0.028;',
      ' gl_FragColor=vec4(max(col,0.0),1.0); }'
    ].join('\n');
    var fs = sh(gl.FRAGMENT_SHADER, frag); if (!vs || !fs) return false;
    var p = gl.createProgram(); gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) { console.error('[field]', gl.getProgramInfoLog(p)); return false; }
    gl.useProgram(p);
    var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var a = gl.getAttribLocation(p, 'aPos'); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
    var L = { res: gl.getUniformLocation(p, 'uRes'), flow: gl.getUniformLocation(p, 'uFlow'), mouse: gl.getUniformLocation(p, 'uMouse'), amt: gl.getUniformLocation(p, 'uMouseAmt'), chapter: gl.getUniformLocation(p, 'uChapter'), trail: gl.getUniformLocation(p, 'uTrail'), trailN: gl.getUniformLocation(p, 'uTrailN') };
    var dpr = 1, mx = innerWidth * 0.62, my = innerHeight * 0.42, tmx = mx, tmy = my, amt = 0, tamt = 0, flow = 0, fmx = mx, fmy = my;
    var trail = [], TR_MAX = 16, TR_LIFE = 1300, t0 = performance.now();
    function push(x, y) { var l = trail[trail.length - 1]; if (l && Math.hypot(x - l.x, y - l.y) < 14) return; trail.push({ x: x, y: y, t0: performance.now() }); if (trail.length > TR_MAX) trail.shift(); }
    function mv(x, y) { tmx = x; tmy = y; tamt = 1; push(x, y); }
    window.addEventListener('mousemove', function (e) { mv(e.clientX, e.clientY); }, { passive: true });
    window.addEventListener('touchmove', function (e) { if (e.touches[0]) mv(e.touches[0].clientX, e.touches[0].clientY); }, { passive: true });
    var chapter = 0, chapterTarget = 0;
    function onScroll() { var max = Math.max(1, document.documentElement.scrollHeight - innerHeight); chapterTarget = Math.min(1, Math.max(0, scrollY / max)); }
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
    function resize() { dpr = Math.min(1, window.devicePixelRatio || 1) * RENDER_SCALE; canvas.width = Math.max(1, Math.floor(innerWidth * dpr)); canvas.height = Math.max(1, Math.floor(innerHeight * dpr)); canvas.style.width = innerWidth + 'px'; canvas.style.height = innerHeight + 'px'; gl.viewport(0, 0, canvas.width, canvas.height); if (L.res) gl.uniform2f(L.res, canvas.width, canvas.height); }
    window.addEventListener('resize', resize, { passive: true });
    var td = new Float32Array(TR_MAX * 3), running = true;
    function render(now) { if (!running) return; mx += (tmx - mx) * 0.12; my += (tmy - my) * 0.12; amt += (tamt - amt) * 0.05; tamt *= 0.96; chapter += (chapterTarget - chapter) * 0.06;
      flow += Math.hypot(mx - fmx, my - fmy) / Math.max(1, innerWidth) * 0.42; fmx = mx; fmy = my;   // ★ 只跟用户移动走
      var k = 0; for (var i = 0; i < trail.length; i++) { var age = (now - trail[i].t0) / TR_LIFE; if (age >= 1) continue; td[k * 3] = trail[i].x * dpr; td[k * 3 + 1] = trail[i].y * dpr; td[k * 3 + 2] = age; k++; }
      if (L.mouse) gl.uniform2f(L.mouse, mx * dpr, my * dpr); if (L.amt) gl.uniform1f(L.amt, Math.min(1, amt)); if (L.flow) gl.uniform1f(L.flow, flow); if (L.chapter) gl.uniform1f(L.chapter, chapter);
      if (L.trail) gl.uniform3fv(L.trail, td); if (L.trailN) gl.uniform1i(L.trailN, k);
      gl.drawArrays(gl.TRIANGLES, 0, 3); requestAnimationFrame(render); }
    resize();
    if (REDUCE) { if (L.flow) gl.uniform1f(L.flow, 0.0); if (L.trailN) gl.uniform1i(L.trailN, 0); gl.drawArrays(gl.TRIANGLES, 0, 3); running = false; }
    else requestAnimationFrame(render);
    return true;
  }

  /* ---- 启动：先用临时 canvas 探测 WebGL2 浮点渲染，再决定本 canvas 用哪条路径 ----
     （同一 canvas 只能有一种 context：webgl2 与 webgl 不能共存） */
  function supportsGL2Float() {
    try {
      var c = document.createElement('canvas');
      var g = c.getContext('webgl2');
      return !!(g && g.getExtension('EXT_color_buffer_float'));
    } catch (e) { return false; }
  }
  var ok = false;
  if (supportsGL2Float()) {
    var gl2 = canvas.getContext('webgl2', { antialias: false, alpha: false, depth: false, powerPreference: 'high-performance' });
    if (gl2) { try { ok = initFluid(gl2); } catch (e) { console.error('[field]', e); ok = false; } }
  } else {
    try { ok = initFbm(); } catch (e2) { console.error('[field]', e2); ok = false; }
  }
  if (!ok) noField();

  /* 告诉壳层"场已就绪" —— 首屏 loader 等的就是这个信号（见 unseen.js 的 initBoot）。
     为什么连等两帧：着色器刚编译完时第一帧还没上屏，这时候撤 loader 会闪一下空白。
     为什么还要写全局标记：defer 的执行顺序是 unseen-field.js 早于 unseen.js，
     所以事件可能派发在监听器绑定之前 —— 漏掉的用 window.__tsFieldReady 兜回来。 */
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      window.__tsFieldReady = true;
      try { window.dispatchEvent(new Event('ts:field-ready')); } catch (e) {}
    });
  });
})();
