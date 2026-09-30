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
  /* 懒加载：升级包后端首屏只渲染当前 tab，其余面板是 <!-- panel:KEY --> 占位注释。
     切到还没加载的面板时，调 ?partial=1&tab=KEY 把那段 HTML 拉回来塞进 .tabpane。
     （升级包后端侧已就位，这里补上前端这一半 —— 原 zip 漏带了 tabs.js 的这段） */
  function ensureLoaded(bar, key) {
    var box = bar.closest ? bar.closest('.adm') : null;
    box = box || document;
    var pane = box.querySelector('.tabpane[data-tab="' + key + '"]');
    if (!pane) return;
    if (!/<!--\s*panel:/.test(pane.innerHTML)) return;     // 已经有内容，跳过
    if (pane.getAttribute('data-loading') === '1') return; // 正在拉，别重复
    pane.setAttribute('data-loading', '1');
    if (!window.fetch) { pane.removeAttribute('data-loading'); return; }
    var url = location.pathname + '?partial=1&tab=' + encodeURIComponent(key);
    fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        pane.innerHTML = html;
        pane.removeAttribute('data-loading');
        each(pane.querySelectorAll('[data-filter]'), bindFilter);
        if (window.TS && typeof window.TS.reinit === 'function') window.TS.reinit(pane);
      })
      .catch(function () { pane.removeAttribute('data-loading'); });  // 失败允许下次重试
  }

  /* 同步移动端上下文条标题（☰ 上方那个"当前面板名"） */
  function syncAdmTitle(bar, key) {
    try {
      var adm = bar.closest ? bar.closest('.adm') : null;
      var cur = adm && adm.querySelector('#adm-cur-name');
      if (cur && window.ADM_NAME_MAP && window.ADM_NAME_MAP[key]) cur.textContent = window.ADM_NAME_MAP[key];
    } catch (e) { /* 不在后台/工作台页就跳过 */ }
  }

  /* 升级包移动端导航（v5）：☰ 抽屉开合 + DM 底栏切 tab。
     原 zip 漏带了这段 JS（在 tabs.js v5 里），这里补上，否则手机上后台抽屉与 DM 底栏点不动。 */
  function closeDrawers(adm) {
    each(adm.querySelectorAll('.adm-drawer.show'), function (d) {
      d.hidden = true; d.classList.remove('show');
      var m = document.getElementById(d.id + '-mask');
      if (m) { m.hidden = true; m.classList.remove('show'); }
    });
  }
  function openDrawer(adm) {
    var d = adm.querySelector('.adm-drawer');
    if (!d) return;
    d.hidden = false; d.classList.add('show');
    var m = document.getElementById(d.id + '-mask');
    if (m) { m.hidden = false; m.classList.add('show'); }
  }
  function wireAdmMobileNav() {
    each(document.querySelectorAll('.adm'), function (adm) {
      var bar = adm.querySelector('[data-tabs]');
      each(adm.querySelectorAll('#adm-open-drawer, .js-open-drawer'), function (btn) {
        btn.addEventListener('click', function () { openDrawer(adm); });
      });
      each(adm.querySelectorAll('#adm-close-drawer, .adm-drawer-mask'), function (btn) {
        btn.addEventListener('click', function () { closeDrawers(adm); });
      });
      adm.addEventListener('click', function (e) {
        var t = e.target.closest && e.target.closest('.adm-tile');
        if (t && t.getAttribute('data-tab')) closeDrawers(adm);
      });
      each(adm.querySelectorAll('.dm-tabbar'), function (bar2) {
        bar2.addEventListener('click', function (e) {
          var b = e.target.closest && e.target.closest('.dm-tab[data-tab]');
          if (!b || !bar) return;
          activate(bar, document, b.getAttribute('data-tab'), bar.getAttribute('data-tabs'));
          closeDrawers(adm);
        });
      });
    });
  }

  function activate(bar, root, key, remember) {
    var hit = false;
    each(root.querySelectorAll('.tabpane'), function (p) {
      var on = p.getAttribute('data-tab') === key;
      p.classList.toggle('on', on);
      // 切出来时像"翻纸片"错位（去 AI 味：不是平滑滑动），用 WAAPI 每次重播
      if (on && p.animate) {
        p.animate(
          [{opacity: 0, transform: 'rotateX(-9deg) translateY(12px)'},
           {opacity: 1, transform: 'none'}],
          {duration: 420, easing: 'cubic-bezier(.22,.61,.36,1)', fill: 'both'});
      }
      hit = hit || on;
    });
    each(bar.querySelectorAll('[data-tab]'), function (b) {
      b.classList.toggle('on', b.getAttribute('data-tab') === key);
    });
    if (hit && remember) {
      try { sessionStorage.setItem('tabs:' + remember, key); } catch (e) { /* 隐身模式就算了 */ }
    }
    if (hit) {
      ensureLoaded(bar, key);   // 懒加载未渲染的面板（配合 ?partial=1 后端）
      syncAdmTitle(bar, key);   // 同步移动端上下文条标题
    }
    return hit;
  }

  /* 全站「收藏」按钮无刷新：任何页面里 <form data-ajax-fav> 提交都走 fetch，
     csrf.js 已自动给 fetch 的 POST 带上 X-CSRF 头，所以令牌不用自己管。
     失败（极少见）就退回普通提交，体验不降级。 */
  document.addEventListener('submit', function (e) {
    var f = e.target.closest && e.target.closest('form[data-ajax-fav]');
    if (!f || !window.fetch) return;
    e.preventDefault();
    var btn = f.querySelector('button');
    fetch(f.getAttribute('action') + '?ajax=1', {method: 'POST', headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var on = !!d.on;
        if (btn) {
          btn.classList.toggle('on', on);
          btn.textContent = on ? '❤' : '♡';
          btn.title = on ? '取消收藏' : '收藏这个本';
          if (on) {                       /* ⑤ 收藏 = 盖章：咚一下 + 红印 */
            btn.classList.remove('is-stamp');
            void btn.offsetWidth;          /* 强制重排，动画每次重播 */
            btn.classList.add('is-stamp');
          } else if (btn.animate) {
            btn.animate([{transform: 'scale(1)'}, {transform: 'scale(.85)'}, {transform: 'scale(1)'}],
              {duration: 180, easing: 'ease-out'});
          }
        }
      })
      .catch(function () { f.submit(); });
  });

  function scrollToId(id) {
    var el = document.getElementById(id);
    if (!el) return;
    try { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) { el.scrollIntoView(); }
  }

  /* 网址上的 #锚点 → 「该显示哪个面板 + 滚到哪儿」
     —— #users 这种本身就是标签名，直接切；
     —— #my-pay 这种是某个面板"里面"的块（结算块在「今日场次」标签里），
        得先查出它在哪个面板、把那个面板切出来，再滚过去。
        不这么做的话：目标在隐藏面板里，点了既不切标签也滚不动 = 看着像没反应。 */
  function resolveHash(bar, root, hash) {
    if (!hash) return false;
    if (activate(bar, root, hash, false)) {          // ① 锚点就是标签名
      scrollToId(hash);
      return true;
    }
    var el = document.getElementById(hash);          // ② 锚点是面板里的某个块
    var pane = el && el.closest ? el.closest('.tabpane') : null;
    if (!pane) return false;
    activate(bar, root, pane.getAttribute('data-tab'), bar.getAttribute('data-tabs'));
    scrollToId(hash);
    return true;
  }

  /* 就地筛选：把同面板里 data-status 不等于 val 的藏起来（'all' = 全显）
     data-filter="type" 就按 data-type 筛（社区的分类就是这么用的）——
     筛的是 DOM，不跳网址、不刷新，点起来是"立刻"的（用户嫌跳页一卡一卡）。 */
  function applyFilter(chipBar, val) {
    var box = chipBar.closest('.tabpane') || document;
    var attr = 'data-' + (chipBar.getAttribute('data-filter') || 'status');
    var shown = 0;
    each(box.querySelectorAll('[' + attr + ']'), function (it) {
      var on = (val === 'all') || it.getAttribute(attr) === val;
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
    wireAdmMobileNav();   // 移动端☰抽屉 + DM 底栏（升级包 v5 漏带的 JS 在这里补）
    each(document.querySelectorAll('[data-tabs]'), function (bar) {
      var root = document;
      var saved = null;
      try { saved = sessionStorage.getItem('tabs:' + bar.getAttribute('data-tabs')); } catch (e) { }
      var hash = (location.hash || '').slice(1);            // 老书签 /admin#bookings 还能用
      var first = bar.querySelector('[data-tab]');
      resolveHash(bar, root, hash) ||
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

      // 同页里点 <a href="/dm#my-pay"> 这类锚点链接只会改 hash、不会重新加载，
      // 所以得自己接一下：不然点在已经在同一页的链接上，什么都不会发生。
      window.addEventListener('hashchange', function () {
        resolveHash(bar, root, (location.hash || '').slice(1));
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
