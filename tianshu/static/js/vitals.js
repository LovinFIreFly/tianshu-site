/* ============================================================================
   轻量 Core Web Vitals 采集（零依赖，~1KB）
   ----------------------------------------------------------------------------
   只做一件事：把真实用户的 LCP / CLS / INP 在「页面被隐藏/卸载」时用一个
   sendBeacon 发回 /vitals（Flask 落盘 data/vitals.log）。
   为什么不用第三方库：字段数据要看，但没必要为此再引一个依赖、再开一个域名。
   安全：全程 try/catch，任何一步失败都静默 —— 监控永远不许反过来影响页面。
   ========================================================================== */
(function () {
  'use strict';
  if (!('PerformanceObserver' in window) || !navigator.sendBeacon) return;
  if (location.protocol.indexOf('http') !== 0) return;      // file:// 等不采

  var vals = {}, sent = false;

  function observe(type, cb, opts) {
    try {
      var o = new PerformanceObserver(function (list) { list.getEntries().forEach(cb); });
      var o2 = opts || {}; o2.type = type; o2.buffered = true;
      o.observe(o2);
    } catch (e) { /* 不支持就跳过该指标 */ }
  }

  /* LCP：观察器每次回调给出的都是"当前最大的元素"，取最后一次即最终值 */
  observe('largest-contentful-paint', function (e) { vals.lcp = Math.round(e.startTime); });

  /* CLS：只累加非用户输入引起的位移 */
  var cls = 0;
  observe('layout-shift', function (e) { if (!e.hadRecentInput) { cls += e.value; vals.cls = Math.round(cls * 1000) / 1000; } });

  /* INP：取交互事件里最差的一次（event timing，阈值 40ms 起） */
  var worst = 0;
  observe('event', function (e) {
    if (e.interactionId && e.duration > worst) { worst = e.duration; vals.inp = Math.round(worst); }
  }, { durationThreshold: 40 });

  function flush() {
    if (sent) return;
    sent = true;
    try {
      var body = JSON.stringify({
        path: location.pathname,
        lcp: vals.lcp || 0, cls: vals.cls || 0, inp: vals.inp || 0,
        vw: window.innerWidth,
        ui: document.documentElement.getAttribute('data-ui') || '',
        conn: (navigator.connection && navigator.connection.effectiveType) || ''
      });
      navigator.sendBeacon('/vitals', new Blob([body], { type: 'application/json' }));
    } catch (e) { /* 静默 */ }
  }

  /* 页面要走的时候再发（此时 LCP/CLS/INP 都稳定了） */
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flush();
  });
  window.addEventListener('pagehide', flush);
})();
