/* 撒肥定位 Service Worker — 離線可用 */
const V = 'fertmap-v24';
const SHELL = [
  './fert_map.html',
  './fertmap-manifest.webmanifest',
  './fertmap-icons/icon-192.png',
  './fertmap-icons/icon-512.png',
  './fertmap-icons/apple-touch-icon.png',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'
];
const RUNTIME = [/fonts\.googleapis\.com/, /fonts\.gstatic\.com/, /cdnjs\.cloudflare\.com/];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(V);
    await Promise.allSettled(SHELL.map(u => c.add(u)));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== V).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', e => { if (e.data === 'skipWaiting') self.skipWaiting(); });

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // 本站頁面:網路優先,失敗才用快取(離線也打得開)
  if (req.mode === 'navigate') {
    if (!url.pathname.endsWith('/fert_map.html')) return; // 其他頁面不攔截
    e.respondWith((async () => {
      try { const r = await fetch(req); const c = await caches.open(V); c.put('./fert_map.html', r.clone()); return r; }
      catch { return (await caches.match('./fert_map.html')) || Response.error(); }
    })());
    return;
  }

  // 字型與程式庫:快取優先
  if (RUNTIME.some(re => re.test(url.host))) {
    e.respondWith((async () => {
      const hit = await caches.match(req);
      if (hit) return hit;
      try { const r = await fetch(req); if (r.ok) (await caches.open(V)).put(req, r.clone()); return r; }
      catch { return hit || Response.error(); }
    })());
    return;
  }

  // 自家圖示與資源
  if (url.origin === location.origin && /fertmap-icons\//.test(url.pathname)) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
  }
  // 其他(地圖圖磚、雲端 API)一律走網路,不快取
});
