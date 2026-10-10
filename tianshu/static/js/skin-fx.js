/* ============================================================================
   皮肤动效层（统一入口）
   ----------------------------------------------------------------------------
   一个文件，按 <html data-skin> 自己路由到对应的动效模块。这样模板只需引一次，
   二代 / 三代骨架都自动生效。

   三条铁律（三个模块共同遵守）：
     ① prefers-reduced-motion 时**只做静态呈现**，不跑循环、不做位移
     ② 只在**视口内**运行（IntersectionObserver 启停）；页面不可见时暂停
     ③ 任何模块抛错都不能影响全站功能 —— 全部 try/catch 包起来
   ========================================================================== */
(function () {
  'use strict';

  var root = document.documentElement;
  var skin = root.getAttribute('data-skin') || '';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* 从 :root 读设计令牌（Canvas 不能解析 CSS 变量，必须读出来再传进去） */
  function token(name, fallback) {
    try {
      var v = getComputedStyle(root).getPropertyValue(name);
      v = (v || '').trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  function raf(fn) { return window.requestAnimationFrame(fn); }

  /* 通用：等 DOM 就绪 */
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else { fn(); }
  }

  /* ==========================================================================
     模块 A · 动能字体（kinetic）
     字重/字宽映射到滚动进度 + 单字级联进场
     ========================================================================== */
  var Kinetic = {
    chars: [],
    hero: null,
    ticking: false,

    split: function (el) {
      /* 按**字素簇**切分（Intl.Segmenter 能正确处理 emoji / 组合字符），
         降级到 Array.from（也能正确处理代理对）。只处理标题，不碰正文。 */

      /* 关键护栏：标题里如果已经有元素子节点（二代骨架是
         <span class="ln"><i><em>今天开一本吧</em></i></span> 这种"行遮罩"结构），
         就不能切 —— 切了会把 <i>/<em> 整层拆掉，行结构丢失，
         字素变成一堆 inline-block 乱换行（-ui2 截图里"今天"飘右上的事故）。
         此时直接放弃切分，交给 CSS 静态呈现，标题照样好看。 */
      for (var k = 0; k < el.childNodes.length; k++) {
        if (el.childNodes[k].nodeType === 1) return 0;
      }

      var text = el.textContent || '';
      if (!text.trim()) return 0;
      var parts;
      try {
        if (window.Intl && Intl.Segmenter) {
          parts = [];
          var seg = new Intl.Segmenter('zh', { granularity: 'grapheme' });
          var it = seg.segment(text);
          var s = it.next();
          while (!s.done) { parts.push(s.value.segment); s = it.next(); }
        } else { parts = Array.from(text); }
      } catch (e) { parts = Array.from(text); }

      /* 只在字数不太多时做单字切分 —— 太长会生成几百个节点，反而卡 */
      if (parts.length > 160) return 0;

      var frag = document.createDocumentFragment();
      for (var i = 0; i < parts.length; i++) {
        var ch = parts[i];
        if (ch === '\n') { frag.appendChild(document.createTextNode(' ')); continue; }
        var sp = document.createElement('span');
        sp.className = 'kx-char';
        /* 空格保留宽度，但不做动画（空 span 会塌） */
        if (ch === ' ' || ch === '\u00A0') {
          sp.style.display = 'inline-block';
          sp.style.width = '.3em';
          sp.textContent = '';
        } else {
          sp.textContent = ch;
        }
        sp.style.setProperty('--i', String(i % 40));   /* 上限 40 档，防超长延迟 */
        frag.appendChild(sp);
      }
      el.setAttribute('aria-label', text);   /* 读屏仍读完整标题 */
      el.textContent = '';
      el.appendChild(frag);
      return parts.length;
    },

    init: function () {
      var h1 = document.querySelector('.hero h1, .dhero__title, .hero .dhero__title');
      this.hero = h1;
      if (!h1) return;

      if (reduce) { return; }   /* 少动效：标签原样，CSS 已保证可见 */

      var n = this.split(h1);
      if (n) {
        /* 下一帧加 .kx-in 触发级联（保证初始态先被渲染，动画才会跑） */
        raf(function () { raf(function () { h1.classList.add('kx-in'); }); });
      }
      this.bindScroll();
    },

    bindScroll: function () {
      var self = this;
      var title = this.hero;
      if (!title) return;

      var update = function () {
        self.ticking = false;
        var r = title.getBoundingClientRect();
        var vh = window.innerHeight || 800;
        /* progress: 标题从"刚进视口底部"到"滚出视口顶部" → 0..1 */
        var p = 1 - (r.top + r.height * 0.5) / (vh + r.height * 0.5);
        p = Math.max(0, Math.min(1, p));
        /* 字重 300 → 900，字宽 92 → 104。范围刻意保守，避免重排抖动 */
        var w = Math.round(300 + p * 600);
        root.style.setProperty('--k-wght', String(w));
        root.style.setProperty('--k-wdth', String(Math.round(92 + p * 12)));
      };

      var onScroll = function () {
        if (self.ticking) return;
        self.ticking = true;
        raf(update);
      };

      window.addEventListener('scroll', onScroll, { passive: true });
      update();
    }
  };

  /* ==========================================================================
     模块 B · 生成艺术（generative）
     首屏噪声流场 + 卡片封面的确定性算法图案
     ========================================================================== */
  var Generative = {
    canvases: [],   /* {el, ctx, seed, kind, visible, raf} */
    running: false,

    /* 确定性伪随机：同一 seed 永远同一张图（稳定，不漂移） */
    rng: function (seed) {
      var s = seed >>> 0;
      return function () {
        s ^= s << 13; s >>>= 0;
        s ^= s >> 17;
        s ^= s << 5; s >>>= 0;
        return s / 4294967296;
      };
    },

    /* 背景：噪声流场（很多短线沿"噪声方向"排列，形成流动感） */
    drawField: function (c, t) {
      var el = c.el, ctx = c.ctx;
      var w = el.width, h = el.height;
      if (!w || !h) return;
      var rnd = this.rng(c.seed);
      var line = token('--gen-line', 'rgba(232,236,245,.55)');
      var accent = token('--gen-accent', '#22B8CF');
      var bg = token('--gen-bg', '#0B1020');
      var density = parseFloat(token('--gen-density', '1')) || 1;

      ctx.clearRect(0, 0, w, h);

      /* 预生成一批粒子（位置固定，只有角度随时间动 → 流动而不乱） */
      if (!c.parts) {
        c.parts = [];
        var n = Math.round(180 * density * Math.min(1.6, (w * h) / (900 * 600)));
        n = Math.max(70, Math.min(420, n));
        for (var i = 0; i < n; i++) {
          c.parts.push({
            x: rnd() * w,
            y: rnd() * h,
            len: 10 + rnd() * 46,
            ph: rnd() * Math.PI * 2,
            spd: 0.15 + rnd() * 0.5,
            hot: rnd() < 0.06      /* 极少数染成强调色 */
          });
        }
      }

      var scale = 0.0022;
      for (var j = 0; j < c.parts.length; j++) {
        var p = c.parts[j];
        /* 用 sin/cos 组合近似值噪声场，够用且极快 */
        var ang = Math.sin((p.x + t * p.spd * 20) * scale) * 2.4 +
                  Math.cos((p.y - t * p.spd * 14) * scale) * 2.4 +
                  p.ph;
        var dx = Math.cos(ang) * p.len;
        var dy = Math.sin(ang) * p.len;
        ctx.strokeStyle = p.hot ? accent : line;
        ctx.globalAlpha = p.hot ? 0.42 : 0.26;
        ctx.lineWidth = p.hot ? 1.5 : 1;
        ctx.beginPath();
        ctx.moveTo(p.x - dx * 0.5, p.y - dy * 0.5);
        ctx.lineTo(p.x + dx * 0.5, p.y + dy * 0.5);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    },

    /* 卡片封面：同心环 / 网格 / 山脊 三选一（按 seed 决定），单帧即可 */
    drawCover: function (c) {
      var el = c.el, ctx = c.ctx;
      var w = el.width, h = el.height;
      if (!w || !h) return;
      var rnd = this.rng(c.seed);
      var bg = token('--gen-bg', '#0B1020');
      var line = token('--gen-line', 'rgba(232,236,245,.55)');
      var accent = token('--gen-accent', '#22B8CF');

      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      var kind = c.seed % 3;
      ctx.lineWidth = 1;
      var i, j;

      if (kind === 0) {
        /* 同心环：从一角扩散 */
        var cx = w * (0.22 + rnd() * 0.56), cy = h * (0.22 + rnd() * 0.56);
        var max = Math.max(w, h) * 1.15;
        var step = 8 + rnd() * 16;
        for (var r = step; r < max; r += step) {
          ctx.strokeStyle = (Math.round(r / step) % 7 === 0) ? accent : line;
          ctx.globalAlpha = (Math.round(r / step) % 7 === 0) ? 0.55 : 0.16;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.stroke();
        }
      } else if (kind === 1) {
        /* 网格 + 随机点亮 */
        var cell = 10 + rnd() * 22;
        for (i = 0; i < w; i += cell) {
          ctx.strokeStyle = line; ctx.globalAlpha = 0.12;
          ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, h); ctx.stroke();
        }
        for (j = 0; j < h; j += cell) {
          ctx.strokeStyle = line; ctx.globalAlpha = 0.12;
          ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(w, j); ctx.stroke();
        }
        var cells = 26;
        for (i = 0; i < cells; i++) {
          var gx = Math.floor(rnd() * (w / cell)) * cell;
          var gy = Math.floor(rnd() * (h / cell)) * cell;
          ctx.fillStyle = rnd() < 0.14 ? accent : line;
          ctx.globalAlpha = rnd() < 0.14 ? 0.5 : 0.22;
          ctx.fillRect(gx, gy, cell, cell);
        }
      } else {
        /* 山脊：多条起伏折线（分层地形） */
        var rows = 16;
        for (i = 0; i < rows; i++) {
          var y0 = (h / rows) * i + 6;
          var amp = 6 + rnd() * 22;
          var freq = 0.006 + rnd() * 0.02;
          var phase = rnd() * 6.28;
          ctx.strokeStyle = (i % 5 === 0) ? accent : line;
          ctx.globalAlpha = (i % 5 === 0) ? 0.5 : 0.18;
          ctx.beginPath();
          for (var x = 0; x <= w; x += 6) {
            var yy = y0 + Math.sin(x * freq + phase) * amp;
            if (x === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
          }
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
    },

    resize: function (c) {
      var el = c.el;
      var rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) return false;
      var dpr = Math.min(2, window.devicePixelRatio || 1);   /* DPR 上限 2：4K 不炸 */
      var w = Math.round(rect.width * dpr);
      var h = Math.round(rect.height * dpr);
      if (el.width !== w || el.height !== h) {
        el.width = w; el.height = h;
        c.parts = null;   /* 尺寸变了，粒子重算 */
      }
      return true;
    },

    loop: function (ts) {
      var self = this;
      if (!self.running) return;
      var t = ts / 1000;
      var anyAlive = false;
      for (var i = 0; i < self.canvases.length; i++) {
        var c = self.canvases[i];
        if (!c.visible) continue;
        if (c.kind === 'field') {
          self.resize(c);
          self.drawField(c, t);
          anyAlive = true;
        }
      }
      if (anyAlive) {
        self.rafId = raf(function (ts2) { self.loop(ts2); });
      } else {
        self.running = false;
      }
    },

    ensureRunning: function () {
      var self = this;
      if (self.running) return;
      self.running = true;
      self.rafId = raf(function (ts) { self.loop(ts); });
    },

    init: function () {
      var self = this;

      /* ① 首屏背景画布 */
      var hero = document.querySelector('.hero, .dhero');
      if (hero && window.HTMLCanvasElement) {
        var cv = document.createElement('canvas');
        cv.className = 'gen-canvas';
        cv.setAttribute('aria-hidden', 'true');
        hero.insertBefore(cv, hero.firstChild);
        var ctx = cv.getContext('2d');
        if (ctx) {
          var c = { el: cv, ctx: ctx, seed: 20261010, kind: 'field', visible: true };
          self.resize(c);
          if (reduce) {
            self.drawField(c, 0);      /* 少动效：只画**一帧**静帧 */
          } else {
            self.canvases.push(c);
            self.observe(c, hero);
            self.ensureRunning();
          }
        }
      }

      /* ② 卡片封面图案（确定性：同一张卡片永远同一张图） */
      var covers = document.querySelectorAll('.pcard3__cover');
      for (var i = 0; i < covers.length && i < 60; i++) {
        var cover = covers[i];
        var cv2 = document.createElement('canvas');
        cv2.className = 'gen-cover';
        cv2.setAttribute('aria-hidden', 'true');
        cover.insertBefore(cv2, cover.firstChild);
        var ctx2 = cv2.getContext('2d');
        if (!ctx2) continue;
        /* seed 从卡片在页面里的序号推出来 —— 不用 DOM id，稳定且无副作用 */
        var cc = { el: cv2, ctx: ctx2, seed: (i * 2654435761) >>> 0, kind: 'cover', visible: false };
        cover._genCover = cc;
        self.canvases.push(cc);
        self.observe(cc, cover);
      }

      /* 尺寸变化：重算所有封面（首屏那个走 loop 自己处理） */
      var rT;
      window.addEventListener('resize', function () {
        if (rT) clearTimeout(rT);
        rT = setTimeout(function () {
          for (var k = 0; k < self.canvases.length; k++) {
            var q = self.canvases[k];
            if (q.kind !== 'cover') continue;
            if (self.resize(q)) self.drawCover(q);
          }
        }, 160);
      }, { passive: true });

      /* 页面不可见 → 停渲染（省电、省 CPU） */
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
          self.running = false;
          if (self.rafId) cancelAnimationFrame(self.rafId);
        } else {
          for (var m = 0; m < self.canvases.length; m++) {
            var p = self.canvases[m];
            if (p.kind === 'cover' && p.visible) self.drawCover(p);
          }
          self.ensureRunning();
        }
      });
    },

    observe: function (c, node) {
      var self = this;
      if (!('IntersectionObserver' in window)) {
        /* 没 IO 就退化成"全部直接画"，功能不残 */
        if (self.resize(c)) { if (c.kind === 'cover') self.drawCover(c); else c.visible = true; }
        return;
      }
      c.io = new IntersectionObserver(function (entries) {
        for (var i = 0; i < entries.length; i++) {
          var e = entries[i];
          c.visible = e.isIntersecting;
          if (e.isIntersecting) {
            if (c.kind === 'cover') {
              if (self.resize(c)) self.drawCover(c);   /* 封面只需一帧 */
            } else {
              self.ensureRunning();
            }
          }
        }
      }, { rootMargin: '160px' });
      c.io.observe(node);
    }
  };

  /* ==========================================================================
     模块 C · 流体重力（liquid）
     Lenis 式平滑滚动 + 卡片上浮的弹簧物理
     ========================================================================== */
  var Liquid = {
    lerp: 0.10,
    target: 0, cur: 0, rafId: 0, cards: [],

    /* 平滑滚动：自己实现一个极简 Lenis —— 不加外链依赖，避免 CDN 挂了整站不动 */
    initScroll: function () {
      var self = this;
      self.lerp = parseFloat(token('--lq-lerp', '0.10')) || 0.10;
      /* 只在桌面、且页面确实有滚动空间时启用 —— 手机上原生滚动更好，别抢 */
      if (window.innerWidth < 1024) return;
      if (reduce) return;

      var doc = document.documentElement;
      self.target = window.scrollY || window.pageYOffset || 0;
      self.cur = self.target;

      var maxScroll = function () {
        return Math.max(0, doc.scrollHeight - window.innerHeight);
      };

      /* 接管滚轮：只拦垂直滚动，横向 / 缩放 / 组合键一律放行 */
      var onWheel = function (e) {
        if (e.ctrlKey || e.metaKey || e.shiftKey) return;
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
        e.preventDefault();
        var mx = maxScroll();
        self.target = Math.max(0, Math.min(mx, self.target + e.deltaY));
        self.start();
      };

      /* 键盘 / 锚点 / 拖滚动条这些"非滚轮"滚动，要同步回 target，
         否则用户一拖滚动条，我们的 target 还停在旧位置，页面会跳回去 */
      var onNativeScroll = function () {
        if (self.selfScrolling) return;
        var y = window.scrollY || 0;
        /* 差距明显 → 是外部滚动，跟随它 */
        if (Math.abs(y - self.cur) > 2) { self.target = y; self.cur = y; }
      };

      var onKey = function (e) {
        var k = e.key;
        var step = window.innerHeight * 0.86;
        if (k === 'PageDown' || k === ' ') { self.target = Math.min(maxScroll(), self.target + step); self.start(); }
        else if (k === 'PageUp') { self.target = Math.max(0, self.target - step); self.start(); }
        else if (k === 'Home') { self.target = 0; self.start(); }
        else if (k === 'End') { self.target = maxScroll(); self.start(); }
      };

      window.addEventListener('wheel', onWheel, { passive: false });
      window.addEventListener('scroll', onNativeScroll, { passive: true });
      window.addEventListener('keydown', onKey);

      /* 外部改 hash（点锚点）时也跟随 */
      window.addEventListener('hashchange', function () {
        setTimeout(function () {
          var y = window.scrollY || 0;
          self.target = y; self.cur = y;
        }, 0);
      });
    },

    start: function () {
      var self = this;
      if (self.rafId) return;
      self.rafId = raf(function () { self.step(); });
    },

    step: function () {
      var self = this;
      var diff = self.target - self.cur;
      if (Math.abs(diff) < 0.4) {
        self.cur = self.target;
        window.scrollTo(0, Math.round(self.cur));
        self.rafId = 0;
        return;
      }
      self.cur += diff * self.lerp;
      self.selfScrolling = true;
      window.scrollTo(0, Math.round(self.cur));
      self.selfScrolling = false;
      self.rafId = raf(function () { self.step(); });
    },

    /* 卡片上浮：用弹簧（刚度 / 阻尼 / 质量）而不是 CSS 过渡 */
    initCards: function () {
      var self = this;
      if (reduce) return;
      var stiffness = parseFloat(token('--lq-stiffness', '210')) || 210;
      var damping = parseFloat(token('--lq-damping', '26')) || 26;
      var mass = parseFloat(token('--lq-mass', '1')) || 1;

      var list = document.querySelectorAll('.pcard3, .ccard3');
      for (var i = 0; i < list.length && i < 80; i++) (function (el) {
        var st = { y: 0, v: 0, goal: 0, active: false };
        el.addEventListener('mouseenter', function () { st.goal = -7; self.pump(st, el, stiffness, damping, mass); });
        el.addEventListener('mouseleave', function () { st.goal = 0; self.pump(st, el, stiffness, damping, mass); });
      })(list[i]);
    },

    pump: function (st, el, k, c, m) {
      var self = this;
      if (st.active) return;
      st.active = true;
      var last = performance.now();
      var tick = function (now) {
        var dt = Math.min(0.032, (now - last) / 1000);   /* 夹住 dt，切标签页回来不会爆 */
        last = now;
        /* 弹簧：a = (-k*(x - goal) - c*v) / m */
        var a = (-k * (st.y - st.goal) - c * st.v) / m;
        st.v += a * dt;
        st.y += st.v * dt;
        el.style.setProperty('--lq-y', st.y.toFixed(2) + 'px');
        /* 收敛判定：位移和速度都够小就停 */
        if (Math.abs(st.y - st.goal) < 0.25 && Math.abs(st.v) < 2) {
          st.y = st.goal; st.v = 0;
          el.style.setProperty('--lq-y', st.y.toFixed(2) + 'px');
          st.active = false;
          return;
        }
        raf(tick);
      };
      raf(tick);
    },

    init: function () {
      var self = this;
      try { self.initScroll(); } catch (e) { /* 平滑滚动挂了也要能滚：原生滚动还在 */ }
      try { self.initCards(); } catch (e) { /* 弹簧挂了就退回 CSS 渐变 */ }
    }
  };

  /* ==========================================================================
     路由
     ========================================================================== */
  ready(function () {
    try {
      if (skin === 'kinetic') Kinetic.init();
      else if (skin === 'generative') Generative.init();
      else if (skin === 'liquid') Liquid.init();
    } catch (e) {
      /* 动效层任何异常都不许影响页面功能 —— 静默吞掉，控制台留个痕 */
      if (window.console && console.warn) console.warn('[skin] 动效初始化失败：', e);
    }
  });

  /* 暴露给调试用（不影响生产） */
  window.__skinFx = { Kinetic: Kinetic, Generative: Generative, Liquid: Liquid, skin: skin, reduce: reduce };
})();
