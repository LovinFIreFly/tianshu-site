/* 甜薯剧本杀 · Service Worker（52：PWA 离线外壳）
   策略：
   · /api/ 接口与图片一律走网络（保证订单/余位/核销码永远是最新数据）
   · 页面与静态资源：网络优先，失败时回退缓存（断网也能打开外壳并看到上次内容）
   · 只缓存同源 GET，不做任何写操作 */
const CACHE = 'tianshu-shell-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;      // 跨域（图床/接口）不缓存
  if (url.pathname.startsWith('/api/')) return;    // 接口永远走网络

  e.respondWith(
    fetch(req)
      .then(res => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then(hit => hit || caches.match('./index.html')))
  );
});
