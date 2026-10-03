/* CSRF 令牌注入（配合后端的 double-submit cookie 校验）
   —— 每个访客第一次打开页面会领到一颗 `csrf` cookie；这脚本把它自动塞进
      页面里**所有** POST 表单和 fetch 请求。以后新加的表单不用改任何东西。 */
(function () {
  var m = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
  if (!m) return;                       // 没领到令牌（极少见）：表单照常显示，提交会被要求刷新
  var t = decodeURIComponent(m[1]);

  function fill(root) {
    Array.prototype.forEach.call(root.querySelectorAll('form'), function (f) {
      if ((f.getAttribute('method') || '').toLowerCase() === 'post'
          && !f.querySelector('input[name="_csrf"]')) {
        var i = document.createElement('input');
        i.type = 'hidden';
        i.name = '_csrf';
        i.value = t;
        f.appendChild(i);
      }
    });
  }
  fill(document);

  // 兜底（2026-10）：后台 / DM 工作台的面板是懒加载的 —— tabs.js 用 fetch 把
  // ?partial=1 的 HTML 在页面加载**之后**才插进 DOM，这些表单永远赶不上上面的
  // fill(document)，一颗令牌都没有 → 第一次点「确认支付定金 / 核销」必弹
  // 「页面放太久啦」。与其到处补时机，不如在提交那一瞬间检查：
  // POST 表单还没令牌就现场补一颗 —— 以后任何动态插进来的表单都自动覆盖。
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f || f.tagName !== 'FORM') return;
    if ((f.getAttribute('method') || '').toLowerCase() !== 'post') return;
    if (f.querySelector('input[name="_csrf"]')) return;
    var i = document.createElement('input');
    i.type = 'hidden';
    i.name = '_csrf';
    i.value = t;
    f.appendChild(i);
  }, true);

  // fetch 也带上（发验证码这类 ajax 请求走的是头，不是表单字段）
  if (window.fetch) {
    var raw = window.fetch;
    window.fetch = function (url, opt) {
      opt = opt || {};
      if ((opt.method || 'GET').toUpperCase() !== 'GET') {
        opt.headers = Object.assign({}, opt.headers, { 'X-CSRF': t });
      }
      return raw.call(this, url, opt);
    };
  }
})();
