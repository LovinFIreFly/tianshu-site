/* ============================================================================
   甜薯剧场 3.0 —— 交互层（design3 的配套脚本）
   ----------------------------------------------------------------------------
   只管"手感"，不碰业务：任何一步失败都不影响页面功能。
     ① 顶栏：滚动加 .scrolled（第二行栏目条折叠）+ 顶部阅读进度条
     ② 入场：.rv / .rv-x 进视口才升起（子项 --i 错位）
     ③ 轨道：.rail3 可拖动 / 滚轮横滑 / 左右箭头 / 底部进度条
     ④ 数字：.count3 从 0 滚到目标值
     ⑤ 提示条：自动淡出（不挡内容，也不用来手动关）
     ⑥ 首屏：光标跟随光斑（--mx / --my）
   约束：不改 data-tab / mobtab / 表单，纯增强。
   ========================================================================== */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* 桌面鼠标（有精确指针）才做吸附和磁吸：触屏上这两样只会帮倒忙 */
  var finePtr = !!(window.matchMedia && window.matchMedia('(pointer:fine)').matches);
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

  /* ---------------------------------------------------------------- ① 顶栏 */
  var nav = document.getElementById('siteNav');
  if (nav) {
    var bar = document.createElement('div');
    bar.className = 'scrollbar3';
    document.body.appendChild(bar);
    var ticking = false;
    function onScroll() {
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      nav.classList.toggle('scrolled', y > 10);
      var h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (h > 0 ? Math.min(100, (y / h) * 100) : 0) + '%';
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
    }, { passive: true });
    onScroll();
  }

  /* ---------------------------------------------------------------- ② 入场 */
  var rv = $$('.rv, .rv-x');
  if (!rv.length) { /* 没有就不建观察器 */ }
  else if (reduce || !window.IntersectionObserver) {
    rv.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -8% 0px' });
    rv.forEach(function (el) { io.observe(el); });
  }

  /* ---------------------------------------------------------------- ③ 轨道 */
  $$('.rail3').forEach(function (rail) {
    var track = $('.rail3__track', rail);
    if (!track) return;
    var fill = $('.rail3__bar i', rail);
    var prev = $('[data-rail="prev"]', rail);
    var next = $('[data-rail="next"]', rail);

    function paint() {
      if (!fill) return;
      var max = track.scrollWidth - track.clientWidth;
      var r = max > 0 ? track.scrollLeft / max : 0;
      var w = max > 0 ? Math.max(0.08, track.clientWidth / track.scrollWidth) : 1;
      fill.style.width = (w * 100) + '%';
      fill.style.transform = 'translateX(' + (max > 0 ? (r * (1 - w) / w) * 100 : 0) + '%)';
    }
    track.addEventListener('scroll', paint, { passive: true });
    window.addEventListener('resize', paint);
    paint();

    function step(dir) {
      var card = track.firstElementChild;
      var dx = card ? card.getBoundingClientRect().width + 18 : 240;
      track.scrollBy({ left: dir * dx * 1.6, behavior: reduce ? 'auto' : 'smooth' });
    }
    if (prev) prev.addEventListener('click', function () { step(-1); });
    if (next) next.addEventListener('click', function () { step(1); });

    /* 拖动（鼠标；触屏交给原生滚动） */
    var down = false, sx = 0, sl = 0, moved = false;
    track.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'touch') return;
      down = true; moved = false; sx = e.clientX; sl = track.scrollLeft;
      track.classList.add('dragging');
    });
    window.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - sx;
      if (Math.abs(dx) > 4) moved = true;
      track.scrollLeft = sl - dx;
    });
    window.addEventListener('pointerup', function () {
      if (!down) return;
      down = false; track.classList.remove('dragging');
    });
    /* 拖动后别触发卡片的点击 */
    track.addEventListener('click', function (e) {
      if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; }
    }, true);
  });

  /* ---------------------------------------------------------------- ④ 数字 */
  var nums = $$('.count3');
  function run(el) {
    var raw = String(el.getAttribute('data-to') != null ? el.getAttribute('data-to') : el.textContent).trim();
    var to = parseFloat(raw.replace(/,/g, ''));
    /* 不是纯数字（带 %、带文字、带千分位以外的杂字）就原样显示，别硬算成 0 */
    if (isNaN(to)) { return; }
    var dec = (raw.split('.')[1] || '').replace(/[^0-9]/g, '').length;
    if (reduce) { el.textContent = to.toFixed(dec); return; }
    var t0 = null, dur = 900;
    function tick(ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var v = to * (1 - Math.pow(1 - p, 3));
      el.textContent = v.toFixed(dec);
      if (p < 1) window.requestAnimationFrame(tick);
    }
    window.requestAnimationFrame(tick);
  }
  if (nums.length && window.IntersectionObserver && !reduce) {
    var nio = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { run(e.target); nio.unobserve(e.target); } });
    }, { threshold: 0.4 });
    nums.forEach(function (el) { nio.observe(el); });
  } else {
    nums.forEach(function (el) { run(el); });
  }

  /* ---------------------------------------------------------------- ⑤ 提示条 */
  $$('.flash').forEach(function (f, i) {
    setTimeout(function () {
      f.classList.add('is-out');
      setTimeout(function () {
        var w = f.parentElement;
        f.remove();
        if (w && !w.children.length) w.remove();
      }, 340);
    }, 4200 + i * 400);
    f.addEventListener('click', function () {
      f.classList.add('is-out');
      setTimeout(function () {
        var w = f.parentElement;
        f.remove();
        if (w && !w.children.length) w.remove();
      }, 340);
    });
    f.style.cursor = 'pointer';
  });

  /* ---------------------------------------------------------------- ⑥ 光斑 */
  /* 首屏和"怎么玩"共用：光标在暗场里带一团印色光（--mx/--my 喂给 .glow3） */
  if (!reduce) {
    $$('.dhero, .how3').forEach(function (sec) {
      var box = sec.classList.contains('how3') ? ($('.how3__pin', sec) || sec) : sec;
      sec.addEventListener('pointermove', function (e) {
        var r = box.getBoundingClientRect();
        sec.style.setProperty('--mx', (e.clientX - r.left) + 'px');
        sec.style.setProperty('--my', (e.clientY - r.top) + 'px');
      }, { passive: true });
    });
  }

  /* ------------------------------------------------- ⑦ 首页"怎么玩"滚动分镜
     整块钉在视口里，按滚动进度换场（0-1/3-2/3-1）。窄屏时 CSS 已退化，
     这里算出来也是 1，不会把手机坑住。 */
  var how = $('.how3');
  if (how) {
    var hsteps = $$('.how3__step', how);
    var hbars = $$('.how3__bar li', how);
    var hbusy = false;
    var paintHow = function () {
      var r = how.getBoundingClientRect();
      var total = r.height - window.innerHeight;
      var p = total > 0 ? Math.min(0.999, Math.max(0, -r.top / total)) : 1;
      var idx = Math.floor(p * hsteps.length);
      hsteps.forEach(function (el, k) { el.classList.toggle('is-on', k === idx); });
      hbars.forEach(function (el, k) { el.classList.toggle('is-on', k <= idx); });
      hbusy = false;
    };
    if (hsteps.length) {
      window.addEventListener('scroll', function () {
        if (!hbusy) { hbusy = true; window.requestAnimationFrame(paintHow); }
      }, { passive: true });
      paintHow();
    }
  }

  /* ------------------------------------------------- ⑧ 吸附：一划一下，稳稳落到下一屏
     首屏往下划 → 平滑迅速对齐到"怎么玩"的开头；
     在分镜里每停一次 → 吸附到当前这一步的起点（0 / 1/3 / 2/3 / 结尾）。
     只在桌面（分镜真的钉住时）启用；手机上分镜会退化成普通三段，这里自动不生效。 */
  if (how && !reduce && finePtr) {
    var howPin = $('.how3__pin', how);
    var howTop = 0, howStep = 0, howTotal = 0, howGuard = 0, howTmr = null, howAnchor = null;
    var lastY = 0, scrollDir = 0;
    function measure() {
      howTop = how.getBoundingClientRect().top + (window.pageYOffset || 0);
      howTotal = Math.max(0, how.offsetHeight - window.innerHeight);
      howStep = howTotal / Math.max(1, how.querySelectorAll('.how3__step').length);
    }
    function glide(top) {
      howGuard = Date.now() + 800;
      howAnchor = top;
      window.scrollTo({ top: top, behavior: 'smooth' });
    }
    function snap() {
      if (!howPin || window.getComputedStyle(howPin).position !== 'sticky') return;
      var y = window.pageYOffset || 0;
      if (Date.now() < howGuard) return;
      var dir = scrollDir;          /* 方向在滚动时记下来（延时后 lastY 已经等于 y 了） */

      /* ① 还在首屏：往下划超过大半屏，就平滑对齐到分镜开头 */
      if (y < howTop - 6) {
        if (dir === 1 && y > howTop - window.innerHeight * 0.5) glide(howTop);
        return;
      }
      /* ② 已经划出去了，不再管 */
      if (y > howTop + howTotal + 6) return;

      /* ③ 在分镜里：滚过 1/4 步才算"翻页"，否则吸回原位
            （这样鼠标滚一格就是稳稳一步，不会一格一格被弹回来） */
      if (howAnchor === null) {
        howAnchor = howTop + Math.round((y - howTop) / howStep) * howStep;
      }
      var d = y - howAnchor;
      var near = Math.abs(d) < howStep * 0.26
        ? howAnchor
        : howAnchor + Math.round(d / howStep) * howStep;
      near = Math.max(howTop, Math.min(howTop + howTotal, near));
      if (Math.abs(near - y) < 8) { howAnchor = near; return; }
      glide(near);
    }
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', function () {
      var y = window.pageYOffset || 0;
      if (y > lastY) scrollDir = 1; else if (y < lastY) scrollDir = -1;
      lastY = y;
      if (howTmr) clearTimeout(howTmr);
      howTmr = setTimeout(snap, 150);
    }, { passive: true });
  }

  /* ---------------------------------------------------------------- ⑨ 磁吸 */
  /* 桌面鼠标才做：按钮朝光标方向偏 3~4px，松开回位（Duolingo 式微交互） */
  if (!reduce && finePtr) {
    $$('.b3, .btn').forEach(function (btn) {
      btn.addEventListener('pointermove', function (e) {
        var r = btn.getBoundingClientRect();
        if (!r.width || !r.height) return;
        var dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
        var dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
        btn.style.transform = 'translate(' + (dx * 4).toFixed(2) + 'px,' + (dy * 3).toFixed(2) + 'px)';
      });
      btn.addEventListener('pointerleave', function () { btn.style.transform = ''; });
    });
  }
})();
