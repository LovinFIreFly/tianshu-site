/* ============================================================================
   剧本库：多选标签 + 搜索，全部前端换网格（整页不跳）
   ----------------------------------------------------------------------------
   后端契约：/scripts?partial=1&q=&tags=a,b&diff=1&fav=1
     · tags 逗号分隔 → 命中任意一个即算（OR 语义）
     · 返回的片段根节点带 data-count="N"，用来更新「N 本」
   失败兜底：任何一步出错就退回整页刷新（不会白屏）。
   ========================================================================== */
(function () {
  'use strict';
  var grid = document.getElementById('scriptGrid');
  if (!grid) return;

  var BOOT = window.TS_LIB || {};
  var state = {
    q: BOOT.q || '',
    tags: (BOOT.tags || []).slice(),
    diff: BOOT.diff || '',
    fav: BOOT.fav || ''
  };

  var filters = document.getElementById('filters');
  var flagBar = document.querySelector('[data-flag]') ? document.querySelector('[data-flag]').closest('.chips3') : null;
  var hit = document.getElementById('hitCount');
  var clearBtn = document.getElementById('clearAll');
  var searchForm = document.querySelector('.spa-search');
  var busy = false;

  function qs(withPartial) {
    var p = [];
    if (withPartial) p.push('partial=1');
    if (state.q) p.push('q=' + encodeURIComponent(state.q));
    if (state.tags.length) p.push('tags=' + encodeURIComponent(state.tags.join(',')));
    if (state.diff) p.push('diff=' + state.diff);
    if (state.fav) p.push('fav=' + state.fav);
    return p.join('&');
  }

  /* 没有 fetch（老浏览器）就直接整页跳 —— 功能不能丢 */
  function fallbackPage() {
    var q = qs(false);
    location.href = '/scripts' + (q ? '?' + q : '');
  }

  function syncChips() {
    if (filters) {
      Array.prototype.forEach.call(filters.querySelectorAll('[data-tag]'), function (b) {
        var on = state.tags.indexOf(b.getAttribute('data-tag')) >= 0;
        b.classList.toggle('on', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    if (flagBar) {
      Array.prototype.forEach.call(flagBar.querySelectorAll('[data-flag]'), function (b) {
        var f = b.getAttribute('data-flag');
        var on = f === 'diff' ? !!state.diff : f === 'fav' ? !!state.fav : false;
        b.classList.toggle('on', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
  }

  function playIn(html) {
    grid.innerHTML = html;
    var root = grid.firstElementChild;
    if (hit && root && root.getAttribute('data-count') != null) {
      hit.textContent = root.getAttribute('data-count') + ' 本';
    }
    if (!window.Element || !Element.prototype.animate) return;
    var items = grid.querySelectorAll('[data-anim]');
    Array.prototype.forEach.call(items, function (el, i) {
      el.animate(
        [{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
        { duration: 420, delay: Math.min(i * 36, 400), easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both' });
    });
  }

  function load() {
    if (busy) return;
    busy = true;
    if (!('fetch' in window)) { fallbackPage(); return; }
    var q = qs(true);
    fetch('/scripts?' + q, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(function (html) {
        playIn(html);
        /* 网址保持在 /scripts（可收藏），条件放在 hash 后不影响后端路由 */
        var pretty = qs(false);
        history.replaceState(null, '', '/scripts' + (pretty ? '?' + pretty : ''));
        busy = false;
      })
      .catch(function () { busy = false; fallbackPage(); });
  }

  /* 标签：多选开关 */
  if (filters) filters.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tag]');
    if (!b) return;
    var t = b.getAttribute('data-tag');
    var i = state.tags.indexOf(t);
    if (i >= 0) state.tags.splice(i, 1); else state.tags.push(t);
    syncChips(); load();
  });

  /* 其他开关：新手友好 / 我的想玩 */
  if (flagBar) flagBar.addEventListener('click', function (e) {
    var b = e.target.closest('[data-flag]');
    if (!b) return;
    var f = b.getAttribute('data-flag');
    if (f === 'diff') state.diff = state.diff ? '' : '1';
    if (f === 'fav') state.fav = state.fav ? '' : '1';
    syncChips(); load();
  });

  if (clearBtn) clearBtn.addEventListener('click', function () {
    state.q = ''; state.tags = []; state.diff = ''; state.fav = '';
    if (searchForm) { var inp = searchForm.querySelector('[name=q]'); if (inp) inp.value = ''; }
    syncChips(); load();
  });

  if (searchForm) searchForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var inp = searchForm.querySelector('[name=q]');
    state.q = inp ? inp.value.trim() : '';
    load();
  });

  syncChips();
})();
