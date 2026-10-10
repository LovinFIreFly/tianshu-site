/* 上传前自动压缩：手机照片动不动 3-8MB，直接传会被"图太大"拒掉。
   选了超过 ~600KB 的图，先在浏览器里缩到最长边 1600px、转成 JPEG（质量 0.85）再提交
   —— 店主不用自己会压图。小图（截图、小头像）原样上传，不受影响。 */
(function () {
  var MAX = 600 * 1024;      // 超过这个大小才压
  var EDGE = 1600;           // 最长边压到多少像素（网站展示足够了）

  function compress(file, cb) {
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      URL.revokeObjectURL(url);
      var k = Math.min(1, EDGE / Math.max(img.width, img.height));
      var c = document.createElement('canvas');
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      c.toBlob(function (b) { cb(b || file); }, 'image/jpeg', 0.85);
    };
    img.onerror = function () { URL.revokeObjectURL(url); cb(file); };   // 压不了就原样传，让后端给提示
    img.src = url;
  }

  function swap(input, blob) {
    var dt = new DataTransfer();
    dt.items.add(new File([blob], (input.dataset.name || 'photo') + '.jpg', { type: 'image/jpeg' }));
    input.files = dt.files;
  }

  /* 2026-10 修复：form.submit() 属于"程序化提交"，**不会触发 submit 事件**，
     而 csrf.js 正是在 submit 事件里补 _csrf 令牌的 —— 于是所有走压缩分支的上传
     （>600KB 的封面/角色图）一律被 CSRF 拦成 403，而小图直接原生提交反而正常，
     表现成"时好时坏"。这里优先用 requestSubmit()（会触发事件），
     老浏览器退化为手动补一个隐藏 _csrf 再提交。 */
  function submitForm(form) {
    if (!form) return;
    if (typeof form.requestSubmit === 'function') { form.requestSubmit(); return; }
    var m = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
    var token = m ? decodeURIComponent(m[1]) : '';
    if (token && !form.querySelector('input[name="_csrf"]')) {
      var h = document.createElement('input');
      h.type = 'hidden'; h.name = '_csrf'; h.value = token;
      form.appendChild(h);
    }
    form.submit();
  }

  /* 给"选完文件就自动提交"的输入框用（角色头像那格） */
  window.tianshuSmartSubmit = function (input) {
    var f = input.files && input.files[0];
    if (!f) return;
    if (f.size <= MAX || !/^image\//.test(f.type)) { submitForm(input.form); return; }
    compress(f, function (blob) { swap(input, blob); submitForm(input.form); });
  };

  /* 给"点按钮才提交"的表单用（换封面那格）：onsubmit 里 return 它的返回值 */
  window.tianshuSmartUpload = function (input) {
    var f = input.files && input.files[0];
    if (!f) return false;                                   // 没选文件就别提交了
    if (f.size <= MAX || !/^image\//.test(f.type)) return true;
    compress(f, function (blob) { swap(input, blob); submitForm(input.form); });
    return false;                                           // 先别提交，压完自动交
  };

  /* 批量上传：角色图片多选后统一提交 */
  window.tianshuBatchUpload = function (form) {
    var inputs = Array.from(form.querySelectorAll('input[type="file"]'));
    var status = document.getElementById(form.id.replace('role-batch-form-', 'role-batch-status-'));
    if (status) status.textContent = '';

    var toCompress = [];
    inputs.forEach(function (input) {
      if (input.files && input.files[0]) {
        var f = input.files[0];
        if (f.size > MAX && /^image\//.test(f.type)) {
          toCompress.push({ input: input, file: f });
        }
      }
    });

    if (toCompress.length === 0) return true;              // 不需要压缩，直接提交

    if (status) status.textContent = '正在压缩 ' + toCompress.length + ' 张图…';
    var i = 0;
    function next() {
      if (i >= toCompress.length) {
        if (status) status.textContent = '压缩完成，正在上传…';
        submitForm(form);
        return;
      }
      var item = toCompress[i++];
      if (status) status.textContent = '正在压缩 ' + i + '/' + toCompress.length + '…';
      compress(item.file, function (blob) {
        swap(item.input, blob);
        next();
      });
    }
    next();
    return false;                                           // 先别提交，压完一起交
  };
})();
