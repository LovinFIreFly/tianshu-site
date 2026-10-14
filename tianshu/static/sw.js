/* 甜薯剧本杀 · Service Worker
   策略：
   · 页面导航（HTML）：网络优先，失败回退缓存（断网时打开最后访问过的页面外壳）
   · 样式表 / 脚本 / 图标等 /static 静态资源：网络优先，失败回退缓存
   · 视频等大媒体：**不进缓存**（网络专用）
   · 其余写操作 / 跨域一律不碰
*/
// v6：① 缓存名换新，让旧缓存（含已删除的 hero.mp4）在 activate 时被清掉；
//     ② 视频/大媒体不再进缓存 —— 源站删了文件，回头的访客仍从旧缓存拿到它，
//        这正是"首页视频删不掉"的根因；③ 预缓存列表收缩到真正的壳层（去掉早已不用的 style.css）。
const CACHE = 'tianshu-shell-v6';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/', '/static/icon.svg',
    '/static/manifest.webmanifest', '/static/icons/icon-192.png', '/static/icons/icon-512.png'])
    .catch(() => null)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // 写操作一律不碰
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;             // 跨域不管

  const isNav = (req.mode === 'navigate') ||
    (req.headers.get('accept') || '').indexOf('text/html') !== -1;

  // 页面导航：网络优先，失败回退缓存（离线显示最后访问页）
  if (isNav) {
    e.respondWith(
      fetch(req).then(res => {
        // 只缓存真正成功的响应。以前 404 / 500 / 登录跳转也被写进缓存，
        // 客人离线或再次访问时拿到的是错误页，还以为是网站坏了。
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(req).then(hit => hit || caches.match('/')))
    );
    return;
  }

  // 视频等大媒体：交给浏览器默认的"网络"行为，不缓存
  // （否则源站删了文件，回头的访客仍从旧缓存拿到它。）
  if (/\.(mp4|webm|mov|m4v)$/i.test(url.pathname)) return;

  // /static 静态资源：网络优先，失败回退缓存
  if (!url.pathname.startsWith('/static/')) return;       // 其余 API/数据走网络，别缓存
  e.respondWith(
    fetch(req).then(res => {
      if (res && res.ok && res.type === 'basic') {   // 同上：错误响应不进缓存
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() => caches.match(req).then(hit => hit || Response.error()))
  );
});
