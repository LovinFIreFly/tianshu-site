/* 甜薯剧本杀 · Service Worker（老版也有一份，照着改的）
   策略：
   · 页面和数据一律走网络（预约/余位/核销码必须是最新的，缓存不得）
   · 样式表 / 图标这类静态资源：网络优先，失败时回退缓存（断网也能打开外壳）
*/
const CACHE = 'tianshu-shell-v1';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/', '/static/css/style.css', '/static/icon.svg', '/static/manifest.webmanifest']).catch(() => null)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // 写操作一律不碰
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;             // 跨域不管
  if (!url.pathname.startsWith('/static/')) return;       // 页面/数据走网络，别缓存
  e.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(req).then(hit => hit || Response.error()))
  );
});
