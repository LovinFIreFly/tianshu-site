/* ════════════════════════════════════════════════════════════════════
   NOVA3 · 招牌签名引擎（从逆向文档拼来）
   ① Sphere —— 第九章 Unseen 线框球画廊（纯原生 JS 复刻，不依赖 Three.js）
   ② Tilt   —— 第十一章 Unseen 3D 透视倾斜卡片
   只挂首页，不碰 nova.js 的全局引擎。
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  var REDUCE = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var COARSE = window.matchMedia && matchMedia('(hover: none)').matches;

  /* ───────────────────────── ① 3D 线框球形画廊 ───────────────────────── */
  var Sphere = (function () {
    function radiusFor(scope) {
      var w = scope.clientWidth || window.innerWidth;
      return Math.max(150, Math.min(270, w * 0.30));
    }

    function build(scope) {
      var group = scope.querySelector('.nx-sphere__group') || scope;
      var cards = Array.prototype.slice.call(group.querySelectorAll('.nx-card'));
      if (!cards.length) return;

      var n = cards.length;
      var R = radiusFor(scope);
      var golden = Math.PI * (3 - Math.sqrt(5));

      // Fibonacci 球面撒点（文档 9.3.1）
      function place(RR) {
        var out = [];
        for (var i = 0; i < n; i++) {
          var y = 1 - (i / (n - 1)) * 2;
          var r = Math.sqrt(Math.max(0, 1 - y * y));
          var th = golden * i;
          out.push({ x: Math.cos(th) * r * RR, y: y * RR, z: Math.sin(th) * r * RR });
        }
        return out;
      }
      var pos = place(R);

      // 线框：8 条经线 + 2 条纬线（组成一个球笼）
      var wire = document.createElement('div');
      wire.className = 'nx-sphere__wire';
      for (var k = 0; k < 8; k++) {
        var ring = document.createElement('div');
        ring.className = 'nx-ring';
        ring.style.width = ring.style.height = (2 * R) + 'px';
        ring.style.marginLeft = ring.style.marginTop = (-R) + 'px';
        ring.style.transform = 'rotateY(' + (k * 22.5) + 'deg)';
        wire.appendChild(ring);
      }
      [-0.55, 0.55].forEach(function (sy) {
        var rr = R * Math.sqrt(Math.max(0, 1 - sy * sy));
        var lat = document.createElement('div');
        lat.className = 'nx-ring nx-ring--lat';
        lat.style.width = (2 * rr) + 'px';
        lat.style.height = (2 * R) + 'px';
        lat.style.marginLeft = (-rr) + 'px';
        lat.style.marginTop = (-R) + 'px';
        // 纬线：先立起来（rotateX 90）再按纬度抬到对应高度
        lat.style.transform = 'rotateX(90deg) translateZ(' + (sy * R) + 'px)';
        wire.appendChild(lat);
      });
      group.appendChild(wire);

      var st = {
        RX: -0.18, RY: 0.4, tRX: -0.18, tRY: 0.4,
        vX: 0, vY: 0, drag: false, lx: 0, ly: 0, R: R, moved: 0
      };
      var scopeState = { st: st, pos: pos, R: R, n: n, golden: golden, wire: wire };

      function onDown(e) {
        st.drag = true; st.vX = 0; st.vY = 0; st.moved = 0;
        st.lx = e.clientX; st.ly = e.clientY;
        scope.classList.add('is-grab');
      }
      function onMove(e) {
        if (!st.drag) return;
        var dx = e.clientX - st.lx, dy = e.clientY - st.ly;
        st.lx = e.clientX; st.ly = e.clientY;
        st.moved += Math.abs(dx) + Math.abs(dy);
        st.tRY += dx * 0.005;
        st.tRX += dy * 0.004;
        st.tRX = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2, st.tRX));
        st.vY = dx * 0.005;
        st.vX = dy * 0.004;
      }
      function onUp() {
        st.drag = false; scope.classList.remove('is-grab');
        // 拖拽过就不算点击，避免误跳详情页
        if (st.moved > 6) {
          scope._suppressClick = true;
          setTimeout(function () { scope._suppressClick = false; }, 80);
        }
      }

      scope.addEventListener('pointerdown', onDown);
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
      scope.addEventListener('click', function (e) {
        if (scope._suppressClick) { e.preventDefault(); e.stopPropagation(); }
      }, true);

      function frame() {
        if (!st.drag) {
          st.tRY += st.vY;
          st.tRX += st.vX;
          st.tRX = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2, st.tRX));
          st.vY *= 0.94; st.vX *= 0.94;   // 摩擦衰减（文档 0.94）
          st.tRY += 0.0016;               // 永不停止的微自旋（文档 0.0015）
        }
        st.RX += (st.tRX - st.RX) * 0.08;  // 滞后跟随（文档 lerp 0.08）
        st.RY += (st.tRY - st.RY) * 0.08;
        group.style.transform =
          'rotateX(' + st.RX + 'rad) rotateY(' + st.RY + 'rad)';

        for (var i = 0; i < cards.length; i++) {
          var p = pos[i];
          // world = Rx(RX) · Ry(RY) · p  →  与 CSS `rotateX rotateY` 一致
          var cy = Math.cos(st.RY), sy = Math.sin(st.RY);
          var x1 = p.x * cy + p.z * sy;
          var z1 = -p.x * sy + p.z * cy;
          var cx2 = Math.cos(st.RX), sx = Math.sin(st.RX);
          var y2 = p.y * cx2 - z1 * sx;
          var z2 = p.y * sx + z1 * cx2;
          var t = (z2 + st.R) / (2 * st.R);  // 0 背面 .. 1 正面
          t = t < 0 ? 0 : (t > 1 ? 1 : t);
          // billboarding：反向旋转让卡片永远正面朝镜头（文档 9.3.3）
          cards[i].style.transform =
            'translate3d(' + p.x.toFixed(1) + 'px,' + p.y.toFixed(1) + 'px,' + p.z.toFixed(1) +
            'px) rotateY(' + (-st.RY) + 'rad) rotateX(' + (-st.RX) + 'rad)';
          cards[i].style.opacity = (0.12 + 0.88 * t).toFixed(3);  // 边缘弱化（文档 9.3.4）
          cards[i].style.filter = 'blur(' + ((1 - t) * 5).toFixed(2) + 'px)';
          cards[i].style.zIndex = (100 + Math.round(t * 100)).toString();
        }
        requestAnimationFrame(frame);
      }
      frame();

      var rt;
      window.addEventListener('resize', function () {
        clearTimeout(rt);
        rt = setTimeout(function () {
          var nR = radiusFor(scope);
          if (Math.abs(nR - st.R) < 2) return;
          st.R = nR;
          pos = place(nR);
          var rings = wire.querySelectorAll('.nx-ring');
          for (var j = 0; j < rings.length; j++) {
            var isLat = rings[j].classList.contains('nx-ring--lat');
            if (!isLat) {
              rings[j].style.width = rings[j].style.height = (2 * nR) + 'px';
              rings[j].style.marginLeft = rings[j].style.marginTop = (-nR) + 'px';
            }
          }
        }, 160);
      });
    }

    function init(root) {
      if (REDUCE) return;
      var scopes = (root || document).querySelectorAll('[data-sphere]');
      Array.prototype.forEach.call(scopes, function (scope) {
        if (scope.getAttribute('data-bound') === '1') return;
        scope.setAttribute('data-bound', '1');
        build(scope);
      });
    }
    return { init: init };
  })();

  /* ───────────────────────── ② 3D 透视倾斜卡片 ───────────────────────── */
  var Tilt = (function () {
    function init(root) {
      if (REDUCE || COARSE) return;
      var els = (root || document).querySelectorAll('[data-tilt]');
      Array.prototype.forEach.call(els, function (el) {
        if (el.getAttribute('data-tilt-bound') === '1') return;
        el.setAttribute('data-tilt-bound', '1');
        var max = parseFloat(el.getAttribute('data-tilt') || '9');
        el.addEventListener('pointermove', function (e) {
          var r = el.getBoundingClientRect();
          var px = (e.clientX - r.left) / r.width - 0.5;
          var py = (e.clientY - r.top) / r.height - 0.5;
          var ry = px * max;
          var rx = -py * max;
          el.style.transition = 'transform .12s ease-out';
          el.style.transform =
            'perspective(820px) rotateX(' + rx.toFixed(2) + 'deg) rotateY(' + ry.toFixed(2) + 'deg) translateZ(6px)';
        });
        el.addEventListener('pointerleave', function () {
          el.style.transition = 'transform .65s cubic-bezier(.22,1,.36,1)';
          el.style.transform = '';
        });
      });
    }
    return { init: init };
  })();

  /* ───────────────────────── 启动 ───────────────────────── */
  function start() {
    Sphere.init(document);
    Tilt.init(document);
  }
  // nova 的无缝转场把首页换回来后，重新挂上招牌引擎
  if (window.addEventListener) {
    window.addEventListener('nv:navigated', function () {
      try { Sphere.init(document); Tilt.init(document); } catch (e) {}
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
  // 让 nova 的无缝转场换页后也能重新挂上（首页被换回时）
  window.NV3 = { rebind: function (root) { try { Sphere.init(root || document); Tilt.init(root || document); } catch (e) {} } };
})();
