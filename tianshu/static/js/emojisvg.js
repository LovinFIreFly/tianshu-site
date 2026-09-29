/* ============================================================================
   emojisvg.js —— 「去 AI 味」第四类：通用 emoji → 手绘 SVG
   ----------------------------------------------------------------------------
   只在「柜台·手写账本」(skin=ledger) 风格下生效，不碰底层数据。
   把一批常见装饰 emoji 替换成内联手绘 SVG（stroke=currentColor，随文字色走，
   在 ledger 皮肤下自然变成墨线小图）。不在白名单里的 emoji 保持原样。
   ============================================================================ */
(function () {
  'use strict';

  // 手绘风 SVG：统一 viewBox 0 0 24 24，描边随文字色，圆头圆角（像钢笔手绘）
  var P = 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
  var M = {
    '🎭': '<svg viewBox="0 0 24 24" ' + P + '><path d="M4 5c4-2 12-2 16 0 1 5-2 12-8 14C6 17 3 10 4 5Z"/><circle cx="9" cy="10" r="1.1"/><circle cx="15" cy="10" r="1.1"/><path d="M9 14c1 1 5 1 6 0"/></svg>',
    '🎁': '<svg viewBox="0 0 24 24" ' + P + '><path d="M4 9h16v11H4z"/><path d="M3 9h18"/><path d="M12 9v11"/><path d="M12 9c-2-3-6-3-5 0M12 9c2-3 6-3 5 0"/></svg>',
    '🎉': '<svg viewBox="0 0 24 24" ' + P + '><path d="M5 14l9-9 4 4-9 9z"/><path d="M5 14l-2 4 4-2"/><path d="M14 5l2-2M17 8l3-1M11 8l-1-3"/></svg>',
    '⭐': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 3l2.6 5.6 6 .8-4.4 4.2 1.1 6L12 16.8 6.7 19.6l1.1-6L3.4 9.4l6-.8z"/></svg>',
    '🔥': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 3c1 4-3 5-3 9a3 3 0 006 0c0-2-1-3-1-3 2 1 3 3 3 5a5 5 0 01-10 0c0-5 5-7 5-11z"/></svg>',
    '💡': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 3a6 6 0 00-3 11c.7.7 1 1.5 1 2.5h4c0-1 .3-1.8 1-2.5A6 6 0 0012 3z"/><path d="M10 18h4M10.5 20h3"/></svg>',
    '📌': '<svg viewBox="0 0 24 24" ' + P + '><path d="M9 3h6v5l3 3H6l3-3z"/><path d="M12 11v9"/></svg>',
    '📍': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 21s7-6 7-12a7 7 0 10-14 0c0 6 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>',
    '☎': '<svg viewBox="0 0 24 24" ' + P + '><path d="M5 4h4l2 5-2 1c1 2 3 4 5 5l1-2 5 2v4c0 1-1 2-2 2C9 21 3 15 3 6c0-1 1-2 2-2z"/></svg>',
    '🏠': '<svg viewBox="0 0 24 24" ' + P + '><path d="M4 11l8-7 8 7"/><path d="M6 10v9h12v-9"/><path d="M10 19v-5h4v5"/></svg>',
    '⏰': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="12" cy="13" r="7"/><path d="M12 13V9M12 13l3 2"/><path d="M9 3l1.5 2M15 3l-1.5 2"/></svg>',
    '💰': '<svg viewBox="0 0 24 24" ' + P + '><rect x="3" y="7" width="18" height="10" rx="1.5"/><circle cx="12" cy="12" r="2.2"/><path d="M7 10v4M17 10v4"/></svg>',
    '🎲': '<svg viewBox="0 0 24 24" ' + P + '><rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1.2"/><circle cx="15" cy="9" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="9" cy="15" r="1.2"/><circle cx="15" cy="15" r="1.2"/></svg>',
    '📖': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 6c-2-1.5-5-1.5-7 0v12c2-1.5 5-1.5 7 0M12 6c2-1.5 5-1.5 7 0v12c-2-1.5-5-1.5-7 0M12 6v12"/></svg>',
    '🎮': '<svg viewBox="0 0 24 24" ' + P + '><rect x="3" y="8" width="18" height="9" rx="4.5"/><path d="M7 12h2M8 11v2"/><circle cx="16" cy="12.5" r=".9"/><circle cx="18" cy="10.5" r=".9"/></svg>',
    '👥': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="9" cy="9" r="2.5"/><circle cx="16" cy="9" r="2.2"/><path d="M4 19c0-3 2.5-5 5-5s5 2 5 5M14 19c0-2.5 1.5-4 3.5-4S21 16.5 21 19"/></svg>',
    '📝': '<svg viewBox="0 0 24 24" ' + P + '><path d="M5 4h11l3 3v13H5z"/><path d="M16 4v3h3"/><path d="M8 11h7M8 14h7"/></svg>',
    '🔔': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 4a5 5 0 015 5v4l2 3H5l2-3V9a5 5 0 015-5z"/><path d="M10 18a2 2 0 004 0"/></svg>',
    '👍': '<svg viewBox="0 0 24 24" ' + P + '><path d="M8 11H5v8h3"/><path d="M8 11l4-7c2 0 2 2 1 4h5a2 2 0 012 2l-2 6a2 2 0 01-2 1.5H8z"/></svg>',
    '🍜': '<svg viewBox="0 0 24 24" ' + P + '><path d="M4 11h16a8 8 0 01-16 0z"/><path d="M4 11v6a2 2 0 002 2h12a2 2 0 002-2v-6"/><path d="M7 11c0-2 1-4 0-5M11 11c0-2 1-4 0-5M15 11c0-2 1-4 0-5"/></svg>',
    '🚌': '<svg viewBox="0 0 24 24" ' + P + '><rect x="4" y="4" width="16" height="13" rx="2"/><path d="M4 11h16"/><circle cx="8" cy="19" r="1.6"/><circle cx="16" cy="19" r="1.6"/><path d="M7 17h10"/></svg>',
    '💬': '<svg viewBox="0 0 24 24" ' + P + '><path d="M4 5h16v10H9l-4 4z"/></svg>',
    '🎨': '<svg viewBox="0 0 24 24" ' + P + '><path d="M12 3a9 9 0 100 18c1 0 2-1 2-2 0-1-1-1-1-2 0-1 1-2 2-2h2a4 4 0 004-4c0-4-4-6-9-6z"/><circle cx="8" cy="9" r="1"/><circle cx="12" cy="7" r="1"/><circle cx="16" cy="9" r="1"/></svg>',
    '🧩': '<svg viewBox="0 0 24 24" ' + P + '><path d="M10 4h4v3a2 2 0 004 0v3h-3a2 2 0 000 4h3v3a2 2 0 01-2 2h-3v-3a2 2 0 00-4 0v3H6a2 2 0 01-2-2v-3h3a2 2 0 000-4H4V7a2 2 0 012-3z"/></svg>',
    '🚗': '<svg viewBox="0 0 24 24" ' + P + '><path d="M3 13l2-5a2 2 0 012-1.5h10A2 2 0 0119 8l2 5v4a1 1 0 01-1 1h-1M3 13v4a1 1 0 001 1h1"/><circle cx="7.5" cy="17" r="1.6"/><circle cx="16.5" cy="17" r="1.6"/><path d="M5 13h14"/></svg>',
    '📷': '<svg viewBox="0 0 24 24" ' + P + '><rect x="3" y="7" width="18" height="12" rx="2"/><circle cx="12" cy="13" r="3.2"/><path d="M8 7l1.5-2h5L16 7"/></svg>',
    '🎬': '<svg viewBox="0 0 24 24" ' + P + '><path d="M3 7h18v3H3z"/><path d="M3 10l3-2 2 2 3-2 2 2 3-2 2 2v9H3z"/><path d="M6 5l1.5 2M11 5l1.5 2M16 5l1.5 2"/></svg>',
    '📅': '<svg viewBox="0 0 24 24" ' + P + '><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9h16M8 3v4M16 3v4"/></svg>',
    '🕵': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="12" cy="8" r="3"/><path d="M5 19c0-4 3-6 7-6s7 2 7 6"/><path d="M4 16l4-2M20 16l-4-2"/></svg>',
    '✅': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></svg>',
    '✔': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></svg>',
    '✂': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="7" cy="7" r="2.2"/><circle cx="7" cy="17" r="2.2"/><path d="M9 8.5L20 18M9 15.5L20 6"/></svg>',
    '🍠': '<svg viewBox="0 0 24 24" ' + P + '><path d="M5 14c-1-3 2-6 5-6.5 1.6-.3 3 .4 4 1.2 3-1 6 1 6 4 .2 2.5-1.6 4.8-4.2 5.2-1 .2-2-.1-2.8-.4-.6 1-2 1.6-3.4 1.2-2-.6-4-1.8-5-4.7z"/><circle cx="9" cy="10" r=".9"/><circle cx="14" cy="9" r=".9"/></svg>',
    '🎂': '<svg viewBox="0 0 24 24" ' + P + '><path d="M4 20h16v-3H4z"/><path d="M6 17v-4h12v4"/><path d="M9 13c0-2 1-3 0-4M12 13c0-2 1-3 0-4M15 13c0-2 1-3 0-4M12 6v2"/></svg>',
    '😊': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="12" cy="12" r="9"/><circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><path d="M8.5 14.5c1.5 1.5 5.5 1.5 7 0"/></svg>',
    '🙂': '<svg viewBox="0 0 24 24" ' + P + '><circle cx="12" cy="12" r="9"/><circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><path d="M8.5 14.5c1.5 1.5 5.5 1.5 7 0"/></svg>',
    '🤝': '<svg viewBox="0 0 24 24" ' + P + '><path d="M3 13l4-4 3 2 3-2 4 4-2 2-3-2-3 2z"/></svg>',
    '🎤': '<svg viewBox="0 0 24 24" ' + P + '><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0012 0"/><path d="M12 17v4M9 21h6"/></svg>'
  };
  var KEYS = Object.keys(M);
  // 用字面量拼接正则（emoji 含代理对，JS 正则能正确匹配序列）
  var RE = new RegExp(KEYS.map(function (k) { return k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|'), 'g');

  function currentSkin() {
    var l = document.querySelector('link[data-skin]');
    if (!l) return null;
    var m = /skin-([\w-]+)\.css/.exec(l.getAttribute('href') || '');
    return m ? m[1] : null;
  }

  function hasEmoji(text) {
    for (var i = 0; i < KEYS.length; i++) {
      if (text.indexOf(KEYS[i]) !== -1) return true;
    }
    return false;
  }

  function replaceIn(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentNode;
        if (!node.nodeValue || !hasEmoji(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        if (p && (p.tagName === 'SCRIPT' || p.tagName === 'STYLE' || p.tagName === 'TEXTAREA')) return NodeFilter.FILTER_REJECT;
        if (p && p.closest && p.closest('.em-svg')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var list = [], n;
    while ((n = walker.nextNode())) list.push(n);
    for (var i = 0; i < list.length; i++) {
      var node = list[i];
      var html = node.nodeValue.replace(RE, function (m) { return '<span class="em-svg" aria-hidden="true">' + (M[m] || m) + '</span>'; });
      if (html === node.nodeValue) continue;
      var tmp = document.createElement('span');
      tmp.innerHTML = html;
      var frag = document.createDocumentFragment();
      while (tmp.firstChild) frag.appendChild(tmp.firstChild);
      node.parentNode.replaceChild(frag, node);
    }
  }

  function init() {
    if (currentSkin() !== 'ledger') return;   // 只在「柜台·手写账本」风格下替换
    replaceIn(document.body);
    // 动态内容（AJAX 评价、tab 切换、拼车上车等）也补一遍
    if ('MutationObserver' in window) {
      var t;
      var mo = new MutationObserver(function (muts) {
        clearTimeout(t);
        t = setTimeout(function () {
          for (var i = 0; i < muts.length; i++) {
            var adds = muts[i].addedNodes;
            for (var j = 0; j < adds.length; j++) {
              if (adds[j].nodeType === 1) replaceIn(adds[j]);
            }
          }
        }, 120);
      });
      mo.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
