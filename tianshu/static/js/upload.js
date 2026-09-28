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

  /* 给"选完文件就自动提交"的输入框用（角色头像那格） */
  window.tianshuSmartSubmit = function (input) {
    var f = input.files && input.files[0];
    if (!f) return;
    if (f.size <= MAX || !/^image\//.test(f.type)) { input.form.submit(); return; }
    compress(f, function (blob) { swap(input, blob); input.form.submit(); });
  };

  /* 给"点按钮才提交"的表单用（换封面那格）：onsubmit 里 return 它的返回值 */
  window.tianshuSmartUpload = function (input) {
    var f = input.files && input.files[0];
    if (!f) return false;                                   // 没选文件就别提交了
    if (f.size <= MAX || !/^image\//.test(f.type)) return true;
    compress(f, function (blob) { swap(input, blob); input.form.submit(); });
    return false;                                           // 先别提交，压完自动交
  };
})();
