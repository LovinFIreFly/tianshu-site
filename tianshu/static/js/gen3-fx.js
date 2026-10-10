/* ============================================================================
   三代骨架动效层（ui=3 / 4 / 5 / 6 / 7 / 8）
   ----------------------------------------------------------------------------
   自己按 <html data-ui> 路由。二代及以下进来读一下 data-ui 就退出（空转）。

   三条不可违背的铁律（写在最前面，代码里逐条守住）：
     1. **绝不劫持滚动**：不 preventDefault、不改滚动方向、不伪造惯性。
        用户的滚轮/触控板/手指动多少，页面就走多少。
     2. **内容默认可见**：所有动效都是"增强"。JS 挂了 / 动画没跑，
        页面照样能读能点。绝不做"默认 opacity:0 等 JS 来揭示"这种事。
     3. **prefers-reduced-motion**：用户开了"减少动态"，全部直接跳到终态。

   ⚠️ 选择器必须用**三代真实类名**（.v3hero/.v3sec/.pcard3/.mason3 这一套），
      不是二代的 .dhero（那在三代页面里根本不存在，改了也没效果）。
      三代首页的骨架类：.v3hero / .v3hero__t / .v3hero__k / .v3hero__aside /
      .v3sec / .v3sec__no / .rail3 / .board3 / .pcard3 / .ccard3 / .mason3 /
      .idx3 / .chalk3 / .shopwall3 / .sheet3 / .realstrip
   ========================================================================== */
(function () {
  'use strict';

  var html = document.documentElement;
  var UI = html.getAttribute('data-ui') || '';
  if (UI !== '3' && UI !== '4' && UI !== '5' && UI !== '6' && UI !== '7' && UI !== '8') return;

  var reduce = false;
  try {
    reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  var raf = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };

  /* ------------------------------------------------------------------ 工具 */

  /* 只处理"纯文本"元素（有元素子节点就跳过）——
     踩过的坑：逐字切分会把嵌套的 <em>/<span> 拆散，标题塌成乱换行。 */
  function isPlainText(el) {
    for (var i = 0; i < el.childNodes.length; i++) {
      if (el.childNodes[i].nodeType === 1) return false;
    }
    return (el.textContent || '').trim().length > 0;
  }

  function each(list, fn) {
    for (var i = 0; i < list.length; i++) fn(list[i], i);
  }

  /* 一次性 IntersectionObserver：进视口就跑一次，然后自己注销 */
  function once(el, fn, threshold) {
    if (!('IntersectionObserver' in window)) { fn(); return; }
    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          io.disconnect();
          fn();
          return;
        }
      }
    }, { threshold: threshold == null ? 0.15 : threshold });
    io.observe(el);
  }

  /* 数字滚字机：从 0 滚到 data-to（不用库） */
  function countTo(el) {
    var to = parseInt(el.getAttribute('data-to') || '0', 10) || 0;
    if (reduce || to <= 0 || to > 1000000) {
      el.textContent = String(to);
      return;
    }
    var t0 = null;
    var dur = Math.min(1400, 420 + to * 6);
    function step(ts) {
      if (t0 == null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var e = 1 - Math.pow(1 - p, 4);            // easeOutQuart
      el.textContent = String(Math.round(to * e));
      if (p < 1) raf(step);
    }
    raf(step);
  }

  /* 首页"卡片容器"的通用取法：三代用 .mason3 / .rail3__track / .split3 / .shopwall3 */
  function cardsIn(scope) {
    var out = [];
    var sels = [
      scope + ' .mason3 > *',
      scope + ' .rail3__track > *',
      scope + ' .split3 > *',
      scope + ' .shopwall3 > *',
      scope + ' .idx3 > li'
    ];
    for (var i = 0; i < sels.length; i++) {
      var n = document.querySelectorAll(sels[i]);
      for (var j = 0; j < n.length; j++) out.push(n[j]);
    }
    return out;
  }

  /* ==========================================================================
     一 · 开本（ui=4）：逐字墨迹 + 章节翻页推入
     ========================================================================== */
  function initBook() {
    /* 逐字墨迹：长段落被"一笔一笔写上去"。
       铁律 2：**内容默认可见** —— 我们不改 DOM 结构去藏内容，
       只在原文本上按滚动进度调每个字的颜色（从淡灰 → 实墨）。
       为此给每个字包一层 span；若包裹失败（有元素子节点）就整段跳过。 */
    var paras = document.querySelectorAll(
      '[data-ui="4"] .v3hero__stats span, [data-ui="4"] .chalk3__b, [data-ui="4"] .v3sec__title small'
    );
    if (!reduce && paras.length) {
      each(paras, function (p) {
        if (!isPlainText(p)) return;
        var text = p.textContent;
        if (text.length < 8 || text.length > 80) return;    // 太长不做（性能 & 反而不像"落墨"）
        p.textContent = '';
        var spans = [];
        for (var i = 0; i < text.length; i++) {
          var sp = document.createElement('span');
          sp.className = 'bk-ink__ch';
          sp.textContent = text[i];
          p.appendChild(sp);
          spans.push(sp);
        }
        function onScroll() {
          var r = p.getBoundingClientRect();
          var vh = window.innerHeight || 800;
          var t = (vh * 0.90 - r.top) / (vh * 0.5);        // 顶从 90% 走到 40% 写完
          t = Math.max(0, Math.min(1, t));
          var n = Math.round(spans.length * t);
          for (var k = 0; k < spans.length; k++) {
            if (k < n) spans[k].classList.remove('is-off');
            else spans[k].classList.add('is-off');
          }
        }
        onScroll();
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('resize', onScroll, { passive: true });
      });
    }

    /* 章节翻页：每个 .v3sec 进视口时从装订线方向推入。
       铁律 2：默认是靠 CSS 的 .bk-page 藏（但那层 class 是我们自己加的），
       所以进视口前先加 .bk-page —— 若 observer 不触发，2 秒兜底全显示。 */
    if (!reduce) {
      var secs = document.querySelectorAll('[data-ui="4"] .v3sec');
      each(secs, function (sec) {
        sec.classList.add('bk-page');
        once(sec, function () { sec.classList.add('bk-in'); }, 0.04);
      });
      setTimeout(function () {
        each(document.querySelectorAll('[data-ui="4"] .v3sec'), function (s) { s.classList.add('bk-in'); });
      }, 2000);
    }

    each(document.querySelectorAll('[data-ui="4"] .count3'), function (el) { once(el, function () { countTo(el); }); });
  }

  /* ==========================================================================
     二 · 剧幕（ui=5）：幕布升起
     ========================================================================== */
  function initPlayhouse() {
    /* 每一"幕"进视口时，一块同色幕布从下往上卷起。
       做法：加 .pr-veil（clip-path 收到 0）→ 下一帧加 .pr-rise（动画拉开）。
       ⚠️ 只在 .dsec--stage 上做（三代里真正有暗场的是它）。
       绝不把首屏 .v3hero 也盖上 —— 那会把内容挡在幕布后面。 */
    if (reduce) return;
    var secs = document.querySelectorAll('[data-ui="5"] .dsec--stage');
    each(secs, function (sec) {
      sec.classList.add('pr-veil');
      once(sec, function () {
        raf(function () { raf(function () { sec.classList.add('pr-rise'); }); });
      }, 0.06);
    });
    // 兜底：1.6 秒后把所有幕布状态清掉（防止剪裁残留）
    setTimeout(function () {
      each(document.querySelectorAll('[data-ui="5"] .pr-veil'), function (s) {
        s.classList.add('pr-rise');
      });
    }, 1600);

    each(document.querySelectorAll('[data-ui="5"] .count3'), function (el) { once(el, function () { countTo(el); }); });
  }

  /* ==========================================================================
     三 · 卷宗（ui=6）：红线 + 逐张钉上
     ========================================================================== */
  function initCaseFile() {
    /* ★「乱中有序」的关键：红线只连**相邻两张**，换行的那对跳过。
       卡片本身的角度由 CSS 的 nth-child(4n+k) 控制（四个固定角度循环）。 */
    var wall = document.querySelector('[data-ui="6"] .mason3')
            || document.querySelector('[data-ui="6"] .split3')
            || document.querySelector('[data-ui="6"] .rail3__track');
    if (wall && !reduce && 'IntersectionObserver' in window) {
      var parent = wall.parentNode;
      if (parent && !parent.querySelector('.fi-threads')) {
        if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'fi-threads');
        svg.setAttribute('preserveAspectRatio', 'none');
        parent.appendChild(svg);

        var paths = [];
        function draw() {
          var pr = parent.getBoundingClientRect();
          svg.setAttribute('viewBox', '0 0 ' + Math.round(pr.width) + ' ' + Math.round(pr.height));
          while (svg.firstChild) svg.removeChild(svg.firstChild);
          paths = [];
          var cards = wall.children;
          for (var i = 0; i + 1 < cards.length; i++) {
            var a = cards[i].getBoundingClientRect();
            var b = cards[i + 1].getBoundingClientRect();
            // 卡右缘中点 → 下一张左缘中点；换行的（下一张在更左边）跳过
            var x1 = a.right - pr.left - 8, y1 = a.top - pr.top + a.height / 2;
            var x2 = b.left - pr.left + 8, y2 = b.top - pr.top + b.height / 2;
            if (x2 < x1) continue;
            if (Math.abs(y1 - y2) > a.height * 1.4) continue;
            var mx = (x1 + x2) / 2, my = (y1 + y2) / 2 - 14;
            var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            p.setAttribute('d', 'M' + x1 + ' ' + y1 + ' Q' + mx + ' ' + my + ' ' + x2 + ' ' + y2);
            svg.appendChild(p);
            paths.push(p);
          }
          var vh = window.innerHeight || 800;
          for (var k = 0; k < paths.length; k++) {
            var pa = paths[k];
            var len = pa.getTotalLength ? pa.getTotalLength() : 200;
            pa.style.setProperty('--fi-len', len);
            var bb = pa.getBoundingClientRect();
            var t = (vh * 0.94 - bb.top) / (vh * 0.6);
            t = Math.max(0, Math.min(1, t));
            pa.style.strokeDasharray = len;
            pa.style.strokeDashoffset = len * (1 - t);
          }
        }
        var pending = false;
        function schedule() {
          if (pending) return;
          pending = true;
          raf(function () { pending = false; draw(); });
        }
        schedule();
        window.addEventListener('scroll', schedule, { passive: true });
        window.addEventListener('resize', schedule, { passive: true });
        window.addEventListener('load', schedule);
        setTimeout(schedule, 300);
      }
    }

    /* 卡片逐张钉上（CSS .fi-in 做入场；默认不可见是 CSS 的 animation both，
       所以必须保证最终都加上 .fi-in —— 加个 2 秒兜底）。 */
    if (!reduce) {
      var cards = cardsIn('[data-ui="6"]');
      each(cards, function (el, i) {
        el.style.animationDelay = Math.min(i * 60, 520) + 'ms';
        once(el, function () { el.classList.add('fi-in'); }, 0.04);
      });
      setTimeout(function () {
        each(cardsIn('[data-ui="6"]'), function (el) { el.classList.add('fi-in'); });
      }, 2000);
    }
    each(document.querySelectorAll('[data-ui="6"] .count3'), function (el) { once(el, function () { countTo(el); }); });
  }

  /* ==========================================================================
     四 · 分镜（ui=7）：逐格走片
     ========================================================================== */
  function initFilm() {
    /* 帧号：写到卡片的 data-fr（CSS 用 ::before 显示）。F 001 格式。 */
    function frameNo(n) {
      return 'F ' + (n < 10 ? '00' + n : (n < 100 ? '0' + n : String(n)));
    }
    each(cardsIn('[data-ui="7"]'), function (el, i) {
      el.setAttribute('data-fr', frameNo(i + 1));
      el.classList.add('fl-frame');
    });

    /* 逐格走片：每张卡进入视口时"曝光到位"（opacity + brightness）。
       ⚠️ 默认 opacity 一律是 1（CSS 里 .fl-stop 才降到 .32），
       我们**先加 .fl-stop 再靠 observer 加 .fl-in** —— 2 秒兜底全 .fl-in。 */
    if (!reduce) {
      var stops = cardsIn('[data-ui="7"]');
      each(stops, function (el) {
        el.classList.add('fl-stop');
        once(el, function () { el.classList.add('fl-in'); }, 0.08);
      });
      setTimeout(function () {
        each(document.querySelectorAll('[data-ui="7"] .fl-stop'), function (el) { el.classList.add('fl-in'); });
      }, 2000);
    }

    /* 首屏帧号：把今天写成 F 0MMDD，放在 data-code（可选增强） */
    var hero = document.querySelector('[data-ui="7"] .v3hero');
    if (hero) {
      var d = new Date();
      hero.setAttribute('data-code', 'R' + ('0' + (d.getMonth() + 1)).slice(-2) + ('0' + d.getDate()).slice(-2));
    }

    each(document.querySelectorAll('[data-ui="7"] .count3'), function (el) { once(el, function () { countTo(el); }); });
  }

  /* ==========================================================================
     五 · 站牌（ui=8）：纸片微摆
     ========================================================================== */
  function initNoticeboard() {
    /* 首页日期（写进 data-date，交给 CSS 的 [data-date]:not([data-date=""]) 显示） */
    var title = document.querySelector('[data-ui="8"] .v3hero__k');
    if (title) {
      var d = new Date();
      var wk = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
      title.setAttribute('data-date', (d.getMonth() + 1) + ' 月 ' + d.getDate() + ' 日 周' + wk);
    }

    /* 纸片微摆：滚动时纸片有极轻的摇摆，像走廊的风吹过。
       ⚠️ 幅度必须小（≤ ±1.1deg）—— 大了就晃眼，用户会不舒服。 */
    if (reduce) return;
    var papers = cardsIn('[data-ui="8"]');
    if (!papers.length) return;

    var last = window.pageYOffset || 0;
    var vel = 0;
    var ticking = false;

    function apply() {
      ticking = false;
      var v = Math.max(-1, Math.min(1, vel / 40));      // 速度归一
      if (vel === 0) v = 0;
      for (var i = 0; i < papers.length; i++) {
        var s = ((i % 3) - 1) * 0.42;                   // -0.42 / 0 / +0.42
        papers[i].style.setProperty('--nb-sway', (v * s).toFixed(3) + 'deg');
      }
    }

    var decay = null;
    window.addEventListener('scroll', function () {
      var y = window.pageYOffset || 0;
      vel = y - last;
      last = y;
      if (!ticking) { ticking = true; raf(apply); }
      clearTimeout(decay);
      decay = setTimeout(function () {
        vel = 0;
        if (!ticking) { ticking = true; raf(apply); }
      }, 130);
    }, { passive: true });

    each(document.querySelectorAll('[data-ui="8"] .count3'), function (el) { once(el, function () { countTo(el); }); });
  }

  /* ==========================================================================
     六 · 三代竖排导轨（ui=3）：日期
     ========================================================================== */
  function initRail() {
    var d = document.getElementById('v3date');
    if (d) {
      var t = new Date();
      var wk = ['日', '一', '二', '三', '四', '五', '六'][t.getDay()];
      d.textContent = ('0' + (t.getMonth() + 1)).slice(-2) + '·' + ('0' + t.getDate()).slice(-2) + ' 周' + wk;
    }
    each(document.querySelectorAll('[data-ui="3"] .count3'), function (el) { once(el, function () { countTo(el); }); });
  }

  /* ------------------------------------------------------------------ 启动 */
  function boot() {
    try {
      if (UI === '3') initRail();
      if (UI === '4') initBook();
      if (UI === '5') initPlayhouse();
      if (UI === '6') initCaseFile();
      if (UI === '7') initFilm();
      if (UI === '8') initNoticeboard();
    } catch (e) {
      // 动效永远不能把页面搞挂：出错就悄悄退场，内容原样留在那儿
      if (window.console && console.warn) console.warn('[gen3-fx]', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
