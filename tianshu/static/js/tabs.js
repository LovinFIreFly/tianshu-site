/* ---------------------------------------------------------------------------
   标签页 & 就地筛选 —— 一个网址里切面板
   ---------------------------------------------------------------------------
   为什么不用 <a href="?tab=x">：那样点一下就整页刷新、网址还会变（后台 14 个功能
   等于 14 个子网址）。这里改成纯前端：所有面板早就渲染在同一页里，点标签只是
   藏/显，网址从头到尾就是 /admin。

   页面需要的样子（外壳模板已经照这个写了）：
     <nav class="tabbar" data-tabs="admin">
       <button data-tab="dash">概览</button> …
     </nav>
     <div class="tabpane" data-tab="dash"> …面板内容… </div>

   筛选（可选）：<div data-filter="status"><button data-show="booked">待开本</button>…</div>
   同面板里带 data-status="booked" 的元素会被就地藏/显，不刷新页面。
   --------------------------------------------------------------------------- */
(function () {
  'use strict';

  function each(list, fn) { Array.prototype.forEach.call(list, fn); }

  /* 把某个标签亮起来，其余藏掉；返回这次有没有真的命中 */
  function activate(bar, root, key, remember) {
    var hit = false;
    each(root.querySelectorAll('.tabpane'), function (p) {
      var on = p.getAttribute('data-tab') === key;
      p.classList.toggle('on', on);
      hit = hit || on;
    });
    each(bar.querySelectorAll('[data-tab]'), function (b) {
      b.classList.toggle('on', b.getAttribute('data-tab') === key);
    });
    if (hit && remember) {
      try { sessionStorage.setItem('tabs:' + remember, key); } catch (e) { /* 隐身模式就算了 */ }
    }
    return hit;
  }

  /* 就地筛选：把同面板里 data-status 不等于 val 的藏起来（'all' = 全显） */
  function applyFilter(chipBar, val) {
    var box = chipBar.closest('.tabpane') || document;
    var shown = 0;
    each(box.querySelectorAll('[data-status]'), function (it) {
      var on = (val === 'all') || it.getAttribute('data-status') === val;
      it.hidden = !on;
      if (on) shown++;
    });
    each(box.querySelectorAll('.no-hit'), function (n) { n.hidden = shown > 0; });
  }

  function bindFilter(chipBar) {
    each(chipBar.querySelectorAll('[data-show]'), function (btn) {
      btn.addEventListener('click', function () {
        each(chipBar.querySelectorAll('[data-show]'), function (b) { b.classList.remove('on'); });
        btn.classList.add('on');
        applyFilter(chipBar, btn.getAttribute('data-show'));
      });
    });
    var def = chipBar.querySelector('[data-show].on');      // 服务端渲染时给默认那颗加了 .on
    if (def) applyFilter(chipBar, def.getAttribute('data-show'));
  }

  function boot() {
    /* [data-tabs] 可能是顶部的胶囊标签条（.tabbar），也可能是后台左侧栏（.adm-side）——
       两种都走同一套逻辑，所以面板统一从整个文档里找。 */
    each(document.querySelectorAll('[data-tabs]'), function (bar) {
      var root = document;
      var saved = null;
      try { saved = sessionStorage.getItem('tabs:' + bar.getAttribute('data-tabs')); } catch (e) { }
      var hash = (location.hash || '').slice(1);            // 老书签 /admin#bookings 还能用
      var first = bar.querySelector('[data-tab]');
      activate(bar, root, hash, false) ||
        activate(bar, root, saved, false) ||
        activate(bar, root, first ? first.getAttribute('data-tab') : '', false);

      bar.addEventListener('click', function (e) {
        var b = e.target.closest('[data-tab]');
        if (!b) return;
        activate(bar, root, b.getAttribute('data-tab'), bar.getAttribute('data-tabs'));
        if (location.hash) {                                // 把 #xxx 抹掉，网址保持干净
          history.replaceState(null, '', location.pathname + location.search);
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
    each(document.querySelectorAll('[data-filter]'), bindFilter);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
