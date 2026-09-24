/**
 * 甜薯剧本杀 · 云端数据代理（Cloudflare Pages Functions）
 * ------------------------------------------------------------
 * v2 安全增强：
 *   1) 登录在服务端校验（POST /api/login），返回 HMAC 签名令牌
 *      —— 浏览器里存的只是令牌，改 localStorage 无法伪造管理员身份
 *   2) 写数据时服务端做「权限净化」：非管理员写入 users.json 时，
 *      强制保留云端原有的 role / super / password，杜绝自我提权与改他人密码
 *   3) 密码用 PBKDF2-SHA256 加盐哈希（10 万次迭代），服务端校验
 *   4) 管理类数据（设置/场次/房间/剧本/敏感词/通知）写入需管理员令牌或管理密钥
 *
 * 部署：
 *   1. GitHub 仓库 tianshu-site → functions/api/[[path]].js 覆盖本文件 → Commit
 *   2. Cloudflare → Pages 项目 tianshu-co8 → Settings → Variables and secrets：
 *        GITHUB_TOKEN = Fine-grained Token（Contents: Read and write）
 *        APP_KEY      = 管理密钥（同时用作令牌签名密钥，务必够长够随机）
 *        REPO         = LovinFireFly/tianshu-data
 *   3. Deployments → 最新一条 → Retry deployment
 *   4. 验证：/api/health 返回 ok:true
 */

const DEFAULT_REPO = 'LovinFireFly/tianshu-data';
const DEFAULT_BRANCH = 'main';
const DEMO_CODE = '1234';          // 演示用短信验证码（正式应接短信服务商）
const TOKEN_DAYS = 7;              // 38：令牌有效期由 30 天缩短为 7 天

const ALLOWED = ['users', 'bookings', 'reviews', 'settings', 'messages', 'notices',
  'rooms', 'sessions', 'carmsgs', 'pays', 'favs', 'taglib', 'dmleave', 'posts', 'badwords', 'logs', 'scripts'];

/* 访客无需密钥即可写入的业务数据 */
const PUBLIC_WRITE = ['bookings', 'messages', 'reviews', 'posts', 'favs', 'carmsgs', 'pays', 'users'];

/* 支持服务端追加合并的数据 */
const ALLOWED_APPEND = ['logs', 'bookings', 'messages', 'reviews', 'posts', 'carmsgs', 'pays', 'users'];

/* 追加合并的唯一键（用户表用手机号） */
const APPEND_KEYFIELD = { users: 'phone' };

/* 只有管理员能写的数据 */
const STAFF_ONLY = ['settings', 'rooms', 'sessions', 'scripts', 'taglib', 'badwords', 'notices'];

const MAX_BODY = 8 * 1024 * 1024;

/* ---------- 36：CORS 白名单（不再对全网开放） ----------
   允许：自己的 Pages 域名 / 自有域名 / 本地调试 / 小程序（无 Origin）
   如需增改，配置环境变量 SITE_ORIGINS（逗号分隔，配置后以它为准） */
let _ACAO = '';
function originAllowed(origin, env) {
  if (!origin) return true;                       // 同源请求 / 小程序 / 命令行不带 Origin
  const extra = String(env.SITE_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
  if (extra.length) return extra.includes(origin);
  try {
    const h = new URL(origin).hostname;
    if (h === 'tianshu-co8.pages.dev' || h.endsWith('.tianshu-co8.pages.dev')) return true;
    if (h === 'lovinfirefly.cn' || h.endsWith('.lovinfirefly.cn')) return true;
    if (h === 'localhost' || h === '127.0.0.1') return true;    // 本地开发调试
  } catch (e) { return false; }
  return false;
}
function setOrigin(request, env) {
  const o = request.headers.get('Origin') || '';
  _ACAO = (o && originAllowed(o, env)) ? o : '';
}
function corsOf() {
  const h = {
    'Access-Control-Allow-Methods': 'GET,PUT,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,x-app-key,x-auth',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
  if (_ACAO) h['Access-Control-Allow-Origin'] = _ACAO;
  return h;
}
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, corsOf()),
  });

/* ---------- 35：接口限流（按 IP 的滑动窗口，防刷单/刷验证码/暴力破解） ---------- */
const _RL = new Map();
let _rlTick = 0;
function rate(key, max, winMs) {
  const now = Date.now();
  if (++_rlTick % 200 === 0) {
    for (const [k, v] of _RL) { if (!v.length || now - v[v.length - 1] > 900000) _RL.delete(k); }
  }
  const arr = (_RL.get(key) || []).filter(t => now - t < winMs);
  if (arr.length >= max) { _RL.set(key, arr); return false; }
  arr.push(now); _RL.set(key, arr); return true;
}
const clientIp = (request) =>
  request.headers.get('CF-Connecting-IP') ||
  String(request.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';

/* ---------------- 加密工具 ---------------- */
function b64url(bytes) {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function b64ToText(b64) {
  const bin = atob(String(b64 || '').replace(/\s/g, ''));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder('utf-8').decode(bytes);
}
function textToB64(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
function bytesToHex(b) {
  let s = '';
  for (let i = 0; i < b.length; i++) s += b[i].toString(16).padStart(2, '0');
  return s;
}
function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}
/* 旧版弱哈希（仅用于兼容历史账号，登录成功后自动升级为 PBKDF2） */
function legacyHash(p) {
  let h = 5381;
  for (let i = 0; i < p.length; i++) h = ((h << 5) + h + p.charCodeAt(i)) >>> 0;
  return 'h' + h.toString(16);
}
async function pbkdf2(pw, saltHex, iterations) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: hexToBytes(saltHex), iterations, hash: 'SHA-256' }, key, 256);
  return 'pbkdf2$' + iterations + '$' + saltHex + '$' + bytesToHex(new Uint8Array(bits));
}
async function newPasswordHash(pw) {
  const salt = bytesToHex(crypto.getRandomValues(new Uint8Array(16)));
  return await pbkdf2(pw, salt, 100000);
}
async function verifyPassword(pw, stored) {
  const s = String(stored || '');
  if (s.startsWith('pbkdf2$')) {
    const [, it, salt, hash] = s.split('$');
    return (await pbkdf2(pw, salt, parseInt(it, 10))) === s;
  }
  return legacyHash(pw) === s;   // 旧账号：本次通过，随后自动升级
}
/* HMAC 签名令牌 */
async function hmac(payloadStr, secret) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return b64url(new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payloadStr))));
}
async function makeToken(user, secret) {
  const payload = {
    phone: user.phone,
    username: user.username,
    role: (user.super === true || user.role === 'super') ? 'super' : (user.role || 'user'),
    exp: Date.now() + TOKEN_DAYS * 86400000,
  };
  const p = b64url(new TextEncoder().encode(JSON.stringify(payload)));
  return p + '.' + (await hmac(p, secret));
}
async function readToken(token, secret) {
  try {
    const [p, s] = String(token || '').split('.');
    if (!p || !s) return null;
    if ((await hmac(p, secret)) !== s) return null;                  // 签名不对 = 伪造
    const obj = JSON.parse(b64ToText(p + '='.repeat((4 - (p.length % 4)) % 4)));
    if (!obj.exp || obj.exp < Date.now()) return null;               // 过期
    return obj;
  } catch (e) { return null; }
}
/* 是否管理员（管理密钥 或 有效管理员令牌） */
async function isStaff(request, env) {
  if (env.APP_KEY && request.headers.get('x-app-key') === env.APP_KEY) return true;
  const t = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
  return !!(t && (t.role === 'admin' || t.role === 'super'));
}

/* ---------------- GitHub 读写 ---------------- */
function ghUrl(env, key, withRef) {
  const repo = env.REPO || DEFAULT_REPO;
  const branch = env.BRANCH || DEFAULT_BRANCH;
  return `https://api.github.com/repos/${repo}/contents/${key}.json${withRef ? '?ref=' + branch : ''}`;
}
function ghHeaders(env, extra) {
  return Object.assign({
    Authorization: 'Bearer ' + String(env.GITHUB_TOKEN || '').replace(/\s+/g, ''),
    Accept: 'application/vnd.github+json',
    'User-Agent': 'tianshu-pages-fn',
  }, extra || {});
}
async function readFile(env, key) {
  const res = await fetch(ghUrl(env, key, true), { headers: ghHeaders(env) });
  if (res.status === 404) return { ok: true, data: null, sha: null, status: 404 };
  if (!res.ok) return { ok: false, data: null, sha: null, status: res.status };
  const d = await res.json();
  let parsed = null;
  try { parsed = JSON.parse(b64ToText(d.content)); } catch (e) { parsed = null; }
  return { ok: true, data: parsed, sha: d.sha, status: 200 };
}
async function writeFile(env, key, sha, data, msg) {
  const res = await fetch(ghUrl(env, key, false), {
    method: 'PUT',
    headers: ghHeaders(env, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      message: msg || ('甜薯数据同步 ' + key),
      branch: env.BRANCH || DEFAULT_BRANCH,
      sha: sha || undefined,
      content: textToB64(JSON.stringify(data, null, 2)),
    }),
  });
  return res.ok;
}
async function writeWithRetry(env, key, cur, data, msg) {
  for (let i = 0; i < 3; i++) {
    const sha = i === 0 ? cur.sha : (await readFile(env, key)).sha;
    if (await writeFile(env, key, sha, data, msg)) return true;
    await new Promise(r => setTimeout(r, 250 * (i + 1)));
  }
  return false;
}

/* ================= v3：数据与业务辅助 ================= */
/* 43：读-改-写合并，始终以云端最新数据为基准，避免多端并发覆盖 */
async function mutate(env, key, fn, msg) {
  for (let i = 0; i < 4; i++) {
    const cur = await readFile(env, key);
    if (!cur.ok) return { ok: false, error: '云端读取失败 ' + cur.status };
    const before = Array.isArray(cur.data) ? cur.data : [];
    let next;
    try { next = fn(before.slice()); } catch (e) { return { ok: false, error: '处理失败' }; }
    if (!Array.isArray(next)) next = before;
    const caps = { logs: 1000, notices: 500, carmsgs: 3000, codes: 300, posts: 2000 };
    if (caps[key]) next = next.slice(0, caps[key]);
    if (await writeWithRetry(env, key, cur, next, msg || ('甜薯数据同步 ' + key))) return { ok: true, data: next };
    await new Promise(r => setTimeout(r, 200 * (i + 1)));
  }
  return { ok: false, error: '写入冲突，请重试' };
}
async function loadArr(env, key) {
  const r = await readFile(env, key);
  return { list: Array.isArray(r.data) ? r.data : [], sha: r.sha, ok: r.ok, status: r.status };
}
/* 50：费率/定金比例/取消时限等走设置，后台可改，不用改代码 */
async function getSettings(env) {
  const r = await readFile(env, 'settings');
  const s = (r.data && typeof r.data === 'object' && !Array.isArray(r.data)) ? r.data : {};
  return Object.assign({
    reviewsEnabled: true, dmRate: 0.1, dmFee: 20, depositRatio: 0.3,
    freeCancelHours: 24, lateCancelPenalty: 2, notice: '', carTags: ['不跳车', '准时到场', '新手友好', '硬核玩家'],
  }, s);
}
/* 站内通知（所有端可见） */
async function notify(env, phone, title, text, opt) {
  const o = opt || {};
  await mutate(env, 'notices', list => {
    list.unshift({
      id: Date.now() + Math.floor(Math.random() * 1000), title, text, at: Date.now(),
      to: [phone], by: o.by || '系统', readBy: [], kind: o.kind || 'system',
    });
    return list;
  }, '推送通知');
}
/* 49：内容清洗与敏感词（服务端判定，绕过前端也拦得住） */
function cleanText(t, max) {
  return String(t == null ? '' : t).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '').slice(0, max || 500);
}
async function badHit(env, text) {
  const r = await readFile(env, 'badwords');
  const list = Array.isArray(r.data) && r.data.length ? r.data : DEFAULT_BADWORDS;
  const s = String(text || '').toLowerCase();
  return list.some(w => w && s.includes(String(w).toLowerCase()));
}
/* 33：对外只暴露昵称/头像/性别/年龄段，绝不带手机号与消费信息 */
function ageBucket(age) {
  const n = parseInt(age, 10);
  if (!n) return '';
  if (n <= 18) return '18岁及以下';
  if (n <= 24) return '18-24';
  if (n <= 30) return '25-30';
  if (n <= 35) return '31-35';
  if (n <= 45) return '36-45';
  return '45岁以上';
}
function publicUser(u) {
  const p = u.profile || {};
  return {
    username: u.username, role: (u.super === true ? 'super' : (u.role || 'user')),
    profile: { nick: p.nick || '', avatar: p.avatar || '🎭', gender: p.gender || '', ageBucket: ageBucket(p.age) },
  };
}
function selfUser(u) {
  return {
    phone: u.phone, username: u.username, email: u.email || '',
    role: (u.super === true ? 'super' : (u.role || 'user')), super: u.super === true,
    credit: typeof u.credit === 'number' ? u.credit : 100,
    creditLogs: Array.isArray(u.creditLogs) ? u.creditLogs.slice(0, 50) : [],
    /* 6/10：会员余额与积分（后台可充值，余额可直接付定金） */
    balance: Number(u.balance) || 0,
    balanceLogs: Array.isArray(u.balanceLogs) ? u.balanceLogs.slice(0, 30) : [],
    points: Number(u.points) || 0,
    profile: u.profile || { avatar: '🎭', nick: '', gender: '', age: null },
    banned: !!u.banned, banReason: u.banReason || '', invite: u.invite || '',
    first: u.first || 0, last: u.last || 0,
  };
}
/* 45：手机号脱敏（DM 视角展示用） */
const maskPhone = p => String(p || '').replace(/^(\d{3})\d{4}(\d{4})$/, '$1****$2');
/* 8：会员等级（按累计消费）—— 用于下单折扣 */
function tierOf(spent) {
  if (spent >= 3000) return { name: '钻石会员', disc: 0.10 };
  if (spent >= 1500) return { name: '黄金会员', disc: 0.05 };
  if (spent >= 500)  return { name: '白银会员', disc: 0.02 };
  return { name: '新客', disc: 0 };
}
function dayLabel(ts) {
  const d = new Date(ts);
  const w = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
  return `${d.getMonth() + 1}月${d.getDate()}日 ${w}`;
}
function playerRange(s) {
  const m = String(s.players || '4-6人').match(/(\d+)\s*[-~到]\s*(\d+)/);
  if (m) return { min: +m[1], max: +m[2] };
  const one = String(s.players || '').match(/(\d+)/);
  return one ? { min: +one[1], max: +one[1] } : { min: 1, max: 8 };
}
/* 37/47/53：图片独立存储（不进 localStorage、不进 HTML），带类型与大小校验 */
async function uploadImage(env, dataUrl) {
  const m = String(dataUrl || '').match(/^data:(image\/(?:webp|jpeg|png|gif));base64,([A-Za-z0-9+/=]+)$/);
  if (!m) return { ok: false, error: '只支持 webp / jpg / png / gif' };
  const bytes = Math.floor(m[2].length * 3 / 4);
  if (bytes > MAX_IMG) return { ok: false, error: '图片过大（请小于 700KB）' };
  const ym = new Date().toISOString().slice(0, 7).replace('-', '');
  const name = ym + '-' + Date.now().toString(36) + '-' + bytesToHex(crypto.getRandomValues(new Uint8Array(4))) + '.' + m[1].split('/')[1];
  const path = 'img/' + ym + '/' + name;
  if (!(await ghWriteRetry(env, path, m[2], '上传图片 ' + path, null))) return { ok: false, error: '存储失败，请重试' };
  return { ok: true, url: '/api/img/' + path, size: bytes };
}
async function ghPut(env, path, sha, b64, msg) {
  const res = await fetch(`https://api.github.com/repos/${env.REPO || DEFAULT_REPO}/contents/${encodeURI(path)}`, {
    method: 'PUT',
    headers: ghHeaders(env, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message: msg || ('甜薯资源 ' + path), branch: env.BRANCH || DEFAULT_BRANCH, sha: sha || undefined, content: b64 }),
  });
  return res.ok;
}
async function ghWriteRetry(env, path, b64, msg, sha0) {
  for (let i = 0; i < 3; i++) {
    const sha = i === 0 ? sha0 : (await readFile(env, path)).sha;
    if (await ghPut(env, path, sha, b64, msg)) return true;
    await new Promise(r => setTimeout(r, 200 * (i + 1)));
  }
  return false;
}
async function serveImage(env, path, request) {
  const key = new Request(new URL(request.url).toString());
  try {
    if (typeof caches !== 'undefined' && caches.default) {
      const hit = await caches.default.match(key);
      if (hit) return hit;
    }
  } catch (e) { }
  const res = await fetch(`https://api.github.com/repos/${env.REPO || DEFAULT_REPO}/contents/${encodeURI(path)}?ref=${env.BRANCH || DEFAULT_BRANCH}`,
    { headers: ghHeaders(env, { Accept: 'application/vnd.github.raw' }) });
  if (!res.ok) return new Response('not found', { status: 404 });
  const buf = await res.arrayBuffer();
  const l = path.toLowerCase();
  const type = l.endsWith('.png') ? 'image/png' : l.endsWith('.gif') ? 'image/gif'
    : (l.endsWith('.jpg') || l.endsWith('.jpeg')) ? 'image/jpeg' : 'image/webp';
  const out = new Response(buf, {
    headers: { 'Content-Type': type, 'Cache-Control': 'public, max-age=31536000, immutable', 'Access-Control-Allow-Origin': '*' },
  });
  try { if (typeof caches !== 'undefined' && caches.default) await caches.default.put(key, out.clone()); } catch (e) { }
  return out;
}
/* 车队视图：客户只能看到昵称/性别/年龄段，看不到手机号 */
async function carPoolOf(env, mePhone) {
  const [bk, us] = await Promise.all([loadArr(env, 'bookings'), loadArr(env, 'users')]);
  const accOf = new Map(us.list.map(u => [u.phone, u]));
  const t0 = new Date(); t0.setHours(0, 0, 0, 0);
  const owners = bk.list.filter(b => b.carNew === true && b.status === 'booked' && (b.ts || 0) >= t0.getTime());
  return owners.map(ob => {
    const mates = bk.list.filter(b => !b.carNew && b.carOwner === ob.username && b.sid === ob.sid &&
      b.ts === ob.ts && b.time === ob.time && b.status !== 'cancelled');
    const joined = (ob.players || 1) + mates.reduce((n, b) => n + (b.players || 1), 0);
    const cap = ob.carCap || 8, min = ob.carMin || 4;
    const members = [ob].concat(mates).map(b => {
      const a = accOf.get(b.phone) || {};
      const p = a.profile || {};
      return { username: b.username || a.username || '玩家', gender: p.gender || '', ageBucket: ageBucket(p.age), players: b.players || 1 };
    });
    return {
      id: 'own-' + ob.id, sid: ob.sid, ts: ob.ts, time: ob.time, owner: ob.username || '玩家',
      tags: Array.isArray(ob.carTags) ? ob.carTags : [], joined, cap, min,
      need: Math.max(0, min - joined), reserved: ob.reserved || 0, members,
      mine: !!(mePhone && [ob].concat(mates).some(b => b.phone === mePhone)),
    };
  }).sort((a, b) => (a.ts - b.ts) || String(a.time).localeCompare(String(b.time)));
}
/* 公开聚合：评分/场次人数/车队/人气榜（不含任何手机号） */
async function summaryOf(env, mePhone) {
  const [bk, rv, cp] = await Promise.all([
    loadArr(env, 'bookings'), loadArr(env, 'reviews'),
    mePhone ? loadArr(env, 'coupons') : Promise.resolve({ list: [] }),
  ]);
  const stats = {};
  bk.list.filter(b => b.status !== 'cancelled').forEach(b => {
    const s = stats[b.sid] = stats[b.sid] || { plays: 0, sum: 0, n: 0 };
    s.plays++;
  });
  rv.list.filter(r => !r.hidden).forEach(r => {
    const s = stats[r.sid] = stats[r.sid] || { plays: 0, sum: 0, n: 0 };
    s.sum += Number(r.rating) || 0; s.n++;
  });
  const scriptStats = {};
  Object.keys(stats).forEach(k => {
    scriptStats[k] = { plays: stats[k].plays, rating: stats[k].n ? +(stats[k].sum / stats[k].n).toFixed(1) : 0, ratingCount: stats[k].n };
  });
  const sessionJoin = {};
  bk.list.filter(b => b.status !== 'cancelled').forEach(b => {
    if (b.sessionId) sessionJoin[b.sessionId] = (sessionJoin[b.sessionId] || 0) + (b.players || 1);
  });
  const hotRank = Object.keys(scriptStats).map(k => ({ sid: +k, plays: scriptStats[k].plays, rating: scriptStats[k].rating }))
    .sort((a, b) => b.plays - a.plays).slice(0, 10);
  const myCoupons = mePhone ? cp.list.filter(c => !c.used && (c.all || c.phone === mePhone) && (!c.exp || c.exp > Date.now()))
    .map(c => ({ id: c.id, amount: c.amount, minAmount: c.minAmount, exp: c.exp })) : [];
  return { scriptStats, sessionJoin, carPool: await carPoolOf(env, mePhone), hotRank, myCoupons };
}

export async function onRequest(context) {
  const { request, env } = context;
  setOrigin(request, env);            // 36：按请求来源决定是否放行 CORS
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsOf() });

  const url = new URL(request.url);
  const parts = url.pathname.replace(/^\/api\/?/, '').split('/').filter(Boolean);
  const staff = await isStaff(request, env);
  const token = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');

  /* ---------- POST /api/login 服务端登录 ---------- */
  if (request.method === 'POST' && parts[0] === 'login') {
    if (!rate('login:' + clientIp(request), 20, 600000)) return json({ ok: false, error: '尝试过于频繁，请 10 分钟后再试' }, 429);
    let body;
    try { body = JSON.parse(await request.text()); } catch (e) { return json({ ok: false, error: '参数错误' }, 400); }
    const acc = String(body.account || '').trim();
    const pw = String(body.password || '');
    if (!acc || !pw) return json({ ok: false, error: '请填写账号与密码' }, 400);

    const cur = await readFile(env, 'users');
    if (!cur.ok) return json({ ok: false, error: '云端读取失败 ' + cur.status }, 502);
    const users = Array.isArray(cur.data) ? cur.data : [];
    const u = users.find(x => x.phone === acc || x.username === acc);
    if (!u) return json({ ok: false, error: '账号不存在' }, 404);
    /* 30：被门店限制的账号不能登录 */
    if (u.banned) return json({ ok: false, error: '该账号已被限制使用：' + (u.banReason || '违反门店规则') }, 403);
    if (!(await verifyPassword(pw, u.password))) return json({ ok: false, error: '密码错误' }, 401);

    /* 旧弱哈希自动升级为 PBKDF2 */
    let upgraded = false;
    if (!String(u.password || '').startsWith('pbkdf2$')) {
      u.password = await newPasswordHash(pw);
      upgraded = true;
    }
    u.last = Date.now();
    if (upgraded) await writeWithRetry(env, 'users', cur, users, '升级密码哈希');

    const role = (u.super === true || u.role === 'super') ? 'super' : (u.role || 'user');
    return json({
      ok: true,
      token: await makeToken(u, env.APP_KEY || ''),
      user: { phone: u.phone, username: u.username, role },
    });
  }

  /* ---------- POST /api/verify 校验令牌（刷新页面时恢复登录态） ---------- */
  if (parts[0] === 'verify') {
    if (!token) return json({ ok: false, error: '令牌无效或已过期' }, 401);
    const cur = await readFile(env, 'users');
    const users = Array.isArray(cur.data) ? cur.data : [];
    const u = users.find(x => x.phone === token.phone);
    if (!u) return json({ ok: false, error: '账号不存在' }, 404);
    if (u.banned) return json({ ok: false, error: '该账号已被限制使用：' + (u.banReason || '违反门店规则') }, 403);
    const role = (u.super === true || u.role === 'super') ? 'super' : (u.role || 'user');
    /* 返回自己的完整档案（含信用分/头像资料），供「我的」页显示 */
    return json({ ok: true, user: Object.assign(selfUser(u), { role }) });
  }

  /* ---------- 验证码：服务端生成、有时效、限次数 ---------- */
const CODE_TTL = 5 * 60 * 1000;      // 5 分钟有效
const CODE_MAX_TRY = 5;              // 最多校验 5 次
const SEND_GAP = 60 * 1000;          // 同一号码 60 秒内只能发一次
const DAY_LIMIT = 10;                // 每日每号码上限（防短信轰炸）

async function readCodes(env) {
  const r = await readFile(env, 'codes');
  const now = Date.now();
  const list = (Array.isArray(r.data) ? r.data : []).filter(c => c && c.exp > now);
  return { list, sha: r.sha, ok: r.ok };
}
async function saveCodes(env, sha, list) {
  return await writeWithRetry(env, 'codes', { sha }, list, '更新验证码');
}
function todayKey() { return new Date().toISOString().slice(0, 10); }

/* 邮件发送：配置 Resend（免费 3000 封/月）或自定义 Webhook 即可真发；未配置则演示模式 */
async function sendEmail(env, to, code) {
  const provider = String(env.MAIL_PROVIDER || '').toLowerCase();
  const from = env.MAIL_FROM || 'onboarding@resend.dev';
  const subject = env.MAIL_SUBJECT || '【甜薯剧本杀】验证码';
  const html = `<div style="font-family:-apple-system,'PingFang SC',sans-serif;padding:24px">
    <h2 style="margin:0 0 12px">甜薯剧本杀</h2>
    <p>你的验证码是：</p>
    <div style="font-size:32px;font-weight:800;letter-spacing:6px;color:#8b5cf6">${code}</div>
    <p style="color:#666">5 分钟内有效，请勿泄露给他人。</p></div>`;

  if (provider === 'resend' && env.MAIL_KEY) {
    try {
      const r = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + env.MAIL_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ from, to: [to], subject, html }),
      });
      return r.ok || r.status === 200;
    } catch (e) { return false; }
  }
  if (provider === 'webhook' && env.MAIL_WEBHOOK) {
    try {
      const r = await fetch(env.MAIL_WEBHOOK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to, code, subject, from }),
      });
      return r.ok;
    } catch (e) { return false; }
  }
  return null;   // 未配置 → 演示模式，验证码回传前端显示
}

/* 短信发送：配置了服务商就真发，否则返回演示码（不真的发短信） */
async function sendSms(env, phone, code) {
  const provider = String(env.SMS_PROVIDER || '').toLowerCase();
  /* 方式一：自定义 Webhook（推荐，云片/短信宝/腾讯云都可套一层） */
  if (provider === 'webhook' && env.SMS_WEBHOOK) {
    try {
      const r = await fetch(env.SMS_WEBHOOK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, code, sign: env.SMS_SIGN || '' }),
      });
      return r.ok;
    } catch (e) { return false; }
  }
  /* 方式二：阿里云短信 */
  if (provider === 'aliyun' && env.SMS_AK && env.SMS_SK) {
    try {
      const p = {
        AccessKeyId: env.SMS_AK, Action: 'SendSms', Format: 'JSON', PhoneNumbers: phone,
        RegionId: env.SMS_REGION || 'cn-hangzhou', SignName: env.SMS_SIGN,
        SignatureMethod: 'HMAC-SHA1', SignatureNonce: crypto.randomUUID(),
        SignatureVersion: '1.0', TemplateCode: env.SMS_TPL,
        TemplateParam: JSON.stringify({ code }),
        Timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), Version: '2017-05-25',
      };
      const q = Object.keys(p).sort().map(k => rfc3986(k) + '=' + rfc3986(p[k])).join('&');
      const sts = 'GET&' + rfc3986('/') + '&' + rfc3986(q);
      const sig = await hmacSha1B64(String(env.SMS_SK) + '&', sts);
      const url = 'https://dysmsapi.aliyuncs.com/?Signature=' + rfc3986(sig) + '&' + q;
      const j = await (await fetch(url)).json();
      return j.Code === 'OK';
    } catch (e) { return false; }
  }
  /* 未配置服务商：演示模式，把验证码直接返回给前端显示 */
  return null;
}
function rfc3986(s) {
  return encodeURIComponent(String(s)).replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
}
async function hmacSha1B64(secret, str) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(str));
  let bin = '';
  for (const b of new Uint8Array(sig)) bin += String.fromCharCode(b);
  return btoa(bin);
}

/* ---------- GET /api/captcha 取一道人机验证题 ---------- */
if (request.method === 'GET' && parts[0] === 'captcha') {
  if (!rate('cap:' + clientIp(request), 60, 600000)) return json({ error: '请求过于频繁，请稍后再试' }, 429);
  const c = await issueCaptcha(env);
  if (!c) return json({ error: '服务繁忙，请重试' }, 502);
  return json(c);
}

/* ---------- POST /api/code/send 发送验证码 ---------- */
if (request.method === 'POST' && parts[0] === 'code' && parts[1] === 'send') {
/* 40：同 IP 限流，防批量刷验证码（邮箱/短信费用被刷） */
if (!rate('send:' + clientIp(request), 15, 600000)) return json({ ok: false, error: '请求过于频繁，请稍后再试' }, 429);
/* 40/41：同一 IP 一小时内发得越多，越必须过人机验证（前几次体验优先，超限强制） */
const ipSends = rate('sendfast:' + clientIp(request), 3, 3600000);
let body;
  try { body = JSON.parse(await request.text()); } catch (e) { return json({ ok: false, error: '参数错误' }, 400); }
  /* 40/41：前 3 次可免人机验证（体验优先），超过后必须过验证；带验证码时一律校验 */
  if (!ipSends || body.captchaId) {
    const cap = await checkCaptcha(env, body.captchaId, body.captchaAnswer);
    if (!cap.ok) return json({ ok: false, error: cap.error, needCaptcha: true }, 401);
  }
  const phone = String(body.phone || '').trim();
  const email = String(body.email || '').trim().toLowerCase();
  const purpose = String(body.purpose || 'register');
  const isMail = !!email;                                  // 有邮箱就走邮件通道
  const target = isMail ? email : phone;
  if (!isMail && !/^1\d{10}$/.test(phone)) return json({ ok: false, error: '请输入正确的手机号' }, 400);
  if (isMail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ ok: false, error: '请输入正确的邮箱' }, 400);

  const cur = await readCodes(env);
  const prev = cur.list.find(c => c.target === target && c.purpose === purpose);
  if (prev && Date.now() - (prev.sentAt || 0) < SEND_GAP) {
    return json({ ok: false, error: '发送太频繁，请稍后再试' }, 429);
  }
  const day = todayKey();
  const sentToday = cur.list.filter(c => c.target === target && c.day === day).length;
  if (sentToday >= DAY_LIMIT) return json({ ok: false, error: '今日发送次数已达上限' }, 429);

  const code = String(Math.floor(100000 + Math.random() * 900000));
  const list = cur.list.filter(c => !(c.target === target && c.purpose === purpose));
  list.push({
    target, channel: isMail ? 'email' : 'sms',
    phone: isMail ? '' : phone, email: isMail ? email : '',
    purpose, code: await newPasswordHash(code),            // 只存哈希，不存明文
    exp: Date.now() + CODE_TTL, sentAt: Date.now(), tries: 0, day,
  });
  await saveCodes(env, cur.sha, list);

  /* 邮件通道优先（个人无短信资质时用它）；否则走短信 */
  const sent = isMail ? await sendEmail(env, email, code) : await sendSms(env, phone, code);
  /* sent === null 表示未配置服务商 → 演示模式，把验证码回传前端显示 */
  return json({
    ok: true, channel: isMail ? 'email' : 'sms',
    sent: sent === true, devCode: sent === null ? code : undefined, ttl: CODE_TTL / 1000,
  });
}

/* 校验验证码（内部函数） */
async function verifyCode(env, phone, code, purpose) {
  const email = String(phone || '').trim().toLowerCase();
  const isMail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const target = isMail ? email : String(phone || '').trim();
  const cur = await readCodes(env);
  const rec = cur.list.find(c => c.target === target && c.purpose === purpose);
  if (!rec) return { ok: false, error: '请先获取验证码' };
  if (rec.tries >= CODE_MAX_TRY) return { ok: false, error: '验证码错误次数过多，请重新获取' };
  const good = await verifyPassword(String(code || ''), rec.code);
  if (!good) {
    rec.tries = (rec.tries || 0) + 1;
    await saveCodes(env, cur.sha, cur.list);
    return { ok: false, error: '验证码不正确' };
  }
  /* 验证通过即销毁 */
  await saveCodes(env, cur.sha, cur.list.filter(c => c !== rec));
  return { ok: true };
}

  /* ================= 40/41：算术人机验证（防脚本注册 / 刷验证码） =================
   题目与答案哈希存 codes.json，5 分钟过期，一次性消费 */
function capHash(v) {
  let h = 5381;
  const s = 'cap:' + String(v);
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return 'c' + h.toString(16);
}
async function issueCaptcha(env) {
  const a = 1 + Math.floor(Math.random() * 9), b = 1 + Math.floor(Math.random() * 9);
  const plus = Math.random() < 0.7;
  const q = plus ? `${a} + ${b} = ?` : `${Math.max(a, b)} - ${Math.min(a, b)} = ?`;
  const ans = plus ? a + b : Math.max(a, b) - Math.min(a, b);
  const id = crypto.randomUUID();
  const w = await mutate(env, 'codes', list => {
    list.push({ kind: 'captcha', id, code: capHash(ans), exp: Date.now() + CODE_TTL });
    return list;
  }, '生成人机验证');
  if (!w.ok) return null;
  return { id, q };
}
async function checkCaptcha(env, id, answer) {
  if (!id || !answer) return { ok: false, error: '请先完成人机验证' };
  let hit = null;
  const w = await mutate(env, 'codes', list => {
    const i = list.findIndex(c => c.kind === 'captcha' && c.id === id && c.exp > Date.now());
    if (i < 0) return list;
    hit = list[i];
    return list.filter((c, j) => j !== i);
  }, '校验人机验证');
  if (!w.ok || !hit) return { ok: false, error: '人机验证已过期，请点「换一题」' };
  if (capHash(String(answer).trim()) !== hit.code) return { ok: false, error: '人机验证答案不对，请重试' };
  return { ok: true };
}

/* ---------- POST /api/register 注册（服务端落库，强制客户身份） ---------- */
  if (request.method === 'POST' && parts[0] === 'register') {
    /* 41：注册限流，防脚本批量注册占位 */
    if (!rate('reg:' + clientIp(request), 5, 3600000)) return json({ ok: false, error: '注册过于频繁，请稍后再试' }, 429);
    let body;
    try { body = JSON.parse(await request.text()); } catch (e) { return json({ ok: false, error: '参数错误' }, 400); }
    const phone = String(body.phone || '').trim();
    const name = String(body.username || '').trim();
    const pw = String(body.password || '');
    const code = String(body.code || '').trim();
    const email = String(body.email || '').trim().toLowerCase();
    const codeTarget = email || phone;                     // 邮箱优先
    if (!email && !/^1\d{10}$/.test(phone)) return json({ ok: false, error: '手机号格式不正确' }, 400);
    if (!/^[\u4e00-\u9fa5A-Za-z0-9_]{2,16}$/.test(name)) return json({ ok: false, error: '用户名需 2-16 位' }, 400);
    if (pw.length < 6) return json({ ok: false, error: '密码至少 6 位' }, 400);
    /* 41：注册必须过人机验证（可用环境变量 CAPTCHA_OFF=true 临时关闭） */
    if (String(env.CAPTCHA_OFF || '') !== 'true') {
      const cap = await checkCaptcha(env, body.captchaId, body.captchaAnswer);
      if (!cap.ok) return json({ ok: false, error: cap.error, needCaptcha: true }, 401);
    }
    /* 服务端校验验证码（邮箱或短信） */
    const vc = await verifyCode(env, codeTarget, code, 'register');
    if (!vc.ok) return json({ ok: false, error: vc.error }, 401);

    const cur = await readFile(env, 'users');
    const users = Array.isArray(cur.data) ? cur.data : [];
    if (users.some(x => x.phone === phone)) return json({ ok: false, error: '该手机号已注册' }, 409);
    if (users.some(x => x.username === name)) return json({ ok: false, error: '用户名已被占用' }, 409);

    const now = Date.now();
    /* 11：邀请码（自己的）+ 邀请返利（用了别人的） */
    let myInvite = '';
    for (let i = 0; i < 8; i++) {
      const c = 'TS' + (Math.floor(Math.random() * 900000) + 100000);
      if (!users.some(x => String(x.invite || '') === c)) { myInvite = c; break; }
    }
    const inviter = String(body.invite || '').trim().toUpperCase();
    const inviterAcc = inviter ? users.find(x => String(x.invite || '').toUpperCase() === inviter) : null;
    const u = {
      username: name, phone, email,
      password: await newPasswordHash(pw),
      role: 'user', super: false,           // ← 服务端强制：注册只能是客户
      invite: myInvite, invitedBy: inviterAcc ? inviterAcc.phone : '',
      credit: 100, creditLogs: [], points: inviterAcc ? 50 : 0, balance: 0, balanceLogs: [],
      profile: { avatar: '🎭', nick: '', gender: '', age: null },
      first: now, last: now,
    };
    users.push(u);
    const ok = await writeWithRetry(env, 'users', cur, users, '注册新账号 ' + name);
    if (!ok) return json({ ok: false, error: '写入失败，请重试' }, 502);
    /* 双向返利：双方各得一张定金抵扣券（新客 ¥15 / 邀请人 ¥15） */
    if (inviterAcc) {
      const mk = (ph, i) => ({
        id: Date.now() + i, phone: ph, amount: 15, minAmount: 0, kind: 'deposit',
        exp: Date.now() + 60 * 86400000, used: false, by: '邀请返利', createdAt: Date.now(),
      });
      await mutate(env, 'coupons', list => list.concat([mk(phone, 0), mk(inviterAcc.phone, 1)]), '邀请返利发券');
      await mutate(env, 'users', list => {
        const t = list.find(x => x.phone === inviterAcc.phone);
        if (t) t.points = (t.points || 0) + 100;
        return list;
      }, '邀请人加积分');
      await notify(env, inviterAcc.phone, '🎉 邀请成功', `好友「${name}」通过你的邀请码注册，你获得 1 张 ¥15 定金券 + 100 积分！`, { kind: 'invite' });
    }
    await notify(env, phone, '欢迎加入甜薯 🍠',
      `注册成功！你的邀请码是 ${myInvite}，把邀请码发给朋友，双方各得 ¥15 定金券～`, { kind: 'welcome' });
    return json({
      ok: true, token: await makeToken(u, env.APP_KEY || ''),
      user: { phone, username: name, role: 'user' }, invite: myInvite,
    });
  }

  /* ---------- POST /api/pwd/reset 密码重置（需验证码） ---------- */
  if (request.method === 'POST' && parts[0] === 'pwd' && parts[1] === 'reset') {
    let body;
    try { body = JSON.parse(await request.text()); } catch (e) { return json({ ok: false, error: '参数错误' }, 400); }
    const phone = String(body.phone || '').trim();
    const code = String(body.code || '').trim();
    const email = String(body.email || '').trim().toLowerCase();
    const pw = String(body.password || '');
    if (pw.length < 6) return json({ ok: false, error: '密码至少 6 位' }, 400);
    /* 服务端校验验证码（邮箱或短信），不再接受写死的 1234 */
    const vc = await verifyCode(env, email || phone, code, 'reset');
    if (!vc.ok) return json({ ok: false, error: vc.error }, 401);

    const cur = await readFile(env, 'users');
    const users = Array.isArray(cur.data) ? cur.data : [];
    /* 支持用手机号或邮箱找回 */
    const u = users.find(x => (phone && x.phone === phone) || (email && String(x.email || '').toLowerCase() === email));
    if (!u) return json({ ok: false, error: '该账号未注册' }, 404);
    u.password = await newPasswordHash(pw);
    u.last = Date.now();
    const ok = await writeWithRetry(env, 'users', cur, users, '重置密码 ' + phone);
    if (!ok) return json({ ok: false, error: '写入失败，请重试' }, 502);
    return json({ ok: true });
  }

  /* ---------- GET /api/health ---------- */
  if (parts[0] === 'health') {
    const r = await readFile(env, 'users');
    const tok = String(env.GITHUB_TOKEN || '').replace(/\s+/g, '');
    let hint = '';
    if (!tok) hint = '未配置 GITHUB_TOKEN';
    else if (r.status === 401) hint = 'Token 无效或已过期';
    else if (r.ok) hint = 'ok';
    return json({
      ok: r.ok, repo: env.REPO || DEFAULT_REPO, branch: env.BRANCH || DEFAULT_BRANCH,
      github: r.status, tokenSet: !!env.GITHUB_TOKEN, appKeySet: !!env.APP_KEY,
      tokenLength: tok.length, hint,
    });
  }

  /* ---------- GET /api/data/:key 读取 ---------- */
  if (request.method === 'GET' && parts[0] === 'data' && parts[1]) {
    const key = parts[1].replace(/\.json$/, '');
    if (NEVER_READ.includes(key)) return json({ error: '该数据不可读取' }, 403);
    if (!ALLOWED.includes(key)) return json({ error: 'key not allowed' }, 400);
    /* 33：含手机号/隐私的数据 —— 分级读取
       · 仅管理员/超管：账号、订单、收藏、日志、敏感词、候补、券、结算
       · 管理员 + DM：预约、留言、请假（DM 工作必需）
       · 其余（剧本/场次/房间/评价/社区/标签/通知）所有访客可读 */
    const STAFF_ONLY_READ = ['users', 'pays', 'favs', 'logs', 'badwords', 'wants', 'waitlist', 'coupons', 'settles'];
    const DM_READ = ['bookings', 'messages', 'dmleave'];
    if (STAFF_ONLY_READ.includes(key) && !staff) return json({ error: '该数据仅员工可读' }, 403);
    if (DM_READ.includes(key) && !staff) {
      const meR = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
      if (!meR || meR.role !== 'dm') return json({ error: '该数据仅员工可读' }, 403);
    }
    const r = await readFile(env, key);
    if (!r.ok) return json({ error: 'github ' + r.status }, 502);
    if (r.data === null) return json(null, 404);
    let data = r.data;
    if (key === 'users') data = data.map(u => Object.assign(selfUser(u), { password: undefined }));
    /* 45：DM 只能看到自己场次的预约（最小权限） */
    if (key === 'bookings' && !staff && Array.isArray(data)) {
      const meR = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
      const mySes = new Set((await loadArr(env, 'sessions')).list.filter(s => s.dm === meR.phone).map(s => s.id));
      data = data.filter(b => (b.sessionId && mySes.has(b.sessionId)) || b.dmPhone === meR.phone);
    }
    if (Array.isArray(data)) {
      /* 公开数据一律去掉手机号字段 */
      if (['reviews', 'posts', 'carmsgs'].includes(key)) {
        data = data.map(x => Object.assign({}, x, { phone: undefined }));
      }
      /* 通知：员工看全部；客户只看发给自己的与全员公告；游客只看全员公告 */
      if (key === 'notices') {
        const me = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
        if (!staff) {
          data = data.filter(x => !Array.isArray(x.to) || (me && x.to.includes(me.phone)))
            .map(x => Object.assign({}, x, { to: undefined }));
        }
      }
    }
    return json(data, 200);
  }

  /* ---------- PUT /api/data/:key 全量写 ---------- */
  if (request.method === 'PUT' && parts[0] === 'data' && parts[1]) {
    const key = parts[1].replace(/\.json$/, '');
    if (!ALLOWED.includes(key)) return json({ error: 'key not allowed' }, 400);
    /* 31/33/34：写权限分级 —— 业务数据（预约/订单/账号/日志/通知/剧本/场次）仅员工可写；
       内容类（留言/评价/社区/车队聊天/收藏）必须登录，且署名以令牌为准 */
    const meW = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    const NEED_STAFF_WRITE = ['bookings', 'pays', 'users', 'logs', 'notices', 'sessions', 'rooms',
      'scripts', 'settings', 'taglib', 'badwords', 'dmleave', 'coupons', 'wants', 'waitlist', 'settles'];
    if (NEED_STAFF_WRITE.includes(key) && !staff) return json({ error: '该数据仅员工可写（客户请使用对应接口）' }, 403);
    if (!PUBLIC_WRITE.includes(key) && !staff) return json({ error: '该数据需要管理员权限' }, 403);
    if (!staff && !meW && ['messages', 'reviews', 'posts', 'carmsgs', 'favs'].includes(key)) {
      return json({ error: '请先登录后再操作' }, 403);
    }

    const bodyText = await request.text();
    if (bodyText.length > MAX_BODY) return json({ error: '数据过大' }, 413);
    let payload;
    try { payload = JSON.parse(bodyText); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }

    const cur = await readFile(env, key);
    let data = payload;
    /* ---------- 32/33：账号表强化净化 ----------
       · 非员工写入必须带登录令牌，且只能修改自己那一条记录
       · 受保护字段（角色 / 超级管理员 / 密码 / 信用分 / 信用流水 / 拉黑 / 微信 openid /
         注册时间 / 邀请码 / 手机号 / 用户名 / 邮箱）一律以云端原值为准
         → 客户无法给自己刷信用分、无法自我提权、无法改他人账号
       · 员工（店长/超管）保留后台应有的能力：改角色、改信用分、拉黑、重置密码 */
    if (key === 'users' && Array.isArray(payload)) {
      const me = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
      if (!staff && !me) return json({ error: '写入账号数据需要先登录' }, 403);
      const cloud = Array.isArray(cur.data) ? cur.data : [];
      const PROTECT = ['role', 'super', 'password', 'credit', 'creditLogs', 'banned', 'banReason',
        'openid', 'first', 'invite', 'phone', 'username', 'email', 'oldPhone'];
      if (!staff) {
        /* 客户：服务端以云端为底合并，只允许改自己那一条，其余记录原样保留 */
        const mine = payload.find(u => u && String(u.phone) === String(me.phone));
        if (!mine) return json({ error: '只能修改自己的账号信息' }, 403);
        data = cloud.map(o => {
          if (String(o.phone) !== String(me.phone)) return o;
          const out = Object.assign({}, o, mine);
          PROTECT.forEach(f => { out[f] = o[f]; });
          return out;
        });
      } else {
        const old = new Map(cloud.map(x => [String(x.phone), x]));
        data = payload.map(u => {
          const o = old.get(String((u && u.phone) || ''));
          if (!o) return null;                                      // 新增账号只能走注册接口
          const out = Object.assign({}, o, u);
          PROTECT.forEach(f => { out[f] = o[f]; });
          if (u.role !== undefined) out.role = u.role;
          if (u.super !== undefined) out.super = !!u.super;
          if (u.credit !== undefined) out.credit = Math.max(0, Math.min(120, Number(u.credit) || 0));
          if (Array.isArray(u.creditLogs)) out.creditLogs = u.creditLogs.slice(0, 100);
          if (u.banned !== undefined) out.banned = !!u.banned;
          if (u.banReason !== undefined) out.banReason = String(u.banReason || '').slice(0, 60);
          out.password = u.password || o.password;
          if (u.username) out.username = u.username;
          if (u.email !== undefined) out.email = String(u.email || '').toLowerCase();
          return out;
        }).filter(Boolean);
      }
    }
    /* ---------- 34：日志署名由令牌决定，匿名无法伪造操作人 ---------- */
    if (key === 'logs') {
      const me = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
      if (!staff && !me) return json({ error: '写入日志需要登录' }, 403);
      const who = staff ? ((me && me.username) || '管理端') : me.username;
      const role = staff ? ((me && me.role) || 'admin') : 'user';
      data = (Array.isArray(payload) ? payload : []).slice(0, 500)
        .map(x => Object.assign({}, x, { by: who, role, at: (x && x.at) || Date.now() }));
    }
    const ok = await writeWithRetry(env, key, cur, data, '甜薯数据同步 ' + key);
    return ok ? json({ ok: true, key }) : json({ error: '写入冲突，请重试' }, 502);
  }

  /* ---------- POST /api/append/:key 追加合并 ---------- */
  if (request.method === 'POST' && parts[0] === 'append' && parts[1]) {
    const key = parts[1].replace(/\.json$/, '');
    if (!ALLOWED_APPEND.includes(key)) return json({ error: 'append not allowed' }, 400);
    /* 31/33/34：与 PUT 同一套写权限规则 */
    const meA = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    const NEED_STAFF_APPEND = ['bookings', 'pays', 'users'];   // 日志允许任意登录用户追加（署名由令牌强制）
    if (NEED_STAFF_APPEND.includes(key) && !staff) return json({ error: '该数据仅员工可写（客户请使用对应接口）' }, 403);
    if (STAFF_ONLY.includes(key) && !staff) return json({ error: '需要管理员权限' }, 403);
    if (!staff && !meA) return json({ error: '请先登录后再操作' }, 403);

    let payload;
    try { payload = JSON.parse(await request.text()); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }
    const items = Array.isArray(payload && payload.items) ? payload.items : [];
    if (!items.length) return json({ ok: true, merged: 0 });
    if (items.length > 500) return json({ error: '单次最多 500 条' }, 413);

    const cur = await readFile(env, key);
    const kf = APPEND_KEYFIELD[key] || 'id';
    const old = Array.isArray(cur.data) ? cur.data : [];
    const map = new Map(old.map(x => [String(x && x[kf]), x]));
    const me = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    items.forEach(it => {
      if (!it || it[kf] == null) return;
      let v = it;
      /* 32：账号表同样净化 —— 受保护字段保留云端值，非员工只能改自己 */
      if (key === 'users') {
        const o = map.get(String(it[kf]));
        if (!o) {                                              // 新增账号只能走注册接口
          if (!staff) return;
          v = Object.assign({}, it, { role: it.role || 'user', super: !!it.super });
        } else {
          if (!staff && (!me || String(it[kf]) !== String(me.phone))) return;   // 他人记录直接跳过
          const PROTECT = ['role', 'super', 'password', 'credit', 'creditLogs', 'banned', 'banReason',
            'openid', 'first', 'invite', 'phone', 'username', 'email', 'oldPhone'];
          v = Object.assign({}, o, it);
          PROTECT.forEach(f => { v[f] = o[f]; });
          if (staff) {
            if (it.role !== undefined) v.role = it.role;
            if (it.super !== undefined) v.super = !!it.super;
            if (it.credit !== undefined) v.credit = Math.max(0, Math.min(120, Number(it.credit) || 0));
            if (Array.isArray(it.creditLogs)) v.creditLogs = it.creditLogs.slice(0, 100);
            if (it.banned !== undefined) v.banned = !!it.banned;
            if (it.banReason !== undefined) v.banReason = String(it.banReason || '').slice(0, 60);
            v.password = it.password || o.password;
            if (it.username) v.username = it.username;
          }
        }
      }
      map.set(String(it[kf]), v);
    });
    let merged = [...map.values()].sort((a, b) => (b.id || 0) - (a.id || 0));
    /* 34：日志署名由令牌决定，匿名无法伪造 */
    if (key === 'logs') {
      if (!staff && !me) return json({ error: '写入日志需要登录' }, 403);
      const who = staff ? ((me && me.username) || '管理端') : me.username;
      const role = staff ? ((me && me.role) || 'admin') : 'user';
      merged = merged.slice(0, 500).map(x => Object.assign({}, x, { by: who, role }));
    }
    if (key === 'users' && !staff && merged.length < old.length) return json({ error: '不允许删除账号（需管理员）' }, 403);

    const ok = await writeWithRetry(env, key, cur, merged, '甜薯追加同步 ' + key);
    return ok ? json({ ok: true, merged: merged.length }) : json({ error: '写入冲突' }, 502);
  }

  /* ---------- POST /api/remove/:key 服务端删除 ---------- */
  if (request.method === 'POST' && parts[0] === 'remove' && parts[1]) {
    const key = parts[1].replace(/\.json$/, '');
    if (!ALLOWED_APPEND.includes(key)) return json({ error: 'remove not allowed' }, 400);
    if (!PUBLIC_WRITE.includes(key) && !staff) return json({ error: '需要管理员权限' }, 403);

    let payload;
    try { payload = JSON.parse(await request.text()); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }
    const ids = Array.isArray(payload && payload.ids) ? payload.ids.map(String) : [];
    if (!ids.length) return json({ ok: true, removed: 0 });

    const cur = await readFile(env, key);
    const kf = APPEND_KEYFIELD[key] || 'id';
    const before = Array.isArray(cur.data) ? cur.data : [];
    const kept = before.filter(x => !ids.includes(String(x && x[kf])));
    if (key === 'users' && !staff && kept.length < before.length) return json({ error: '不允许删除账号（需管理员）' }, 403);

    const ok = await writeWithRetry(env, key, cur, kept, '甜薯删除同步 ' + key);
    return ok ? json({ ok: true, removed: before.length - kept.length }) : json({ error: '写入冲突' }, 502);
  }

  /* ================= 31：创建预约（服务端算价 + 余位/选角/优惠券校验） ================= */
  if (request.method === 'POST' && parts[0] === 'booking' && parts[1] === 'create') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (!rate('bk:' + clientIp(request), 30, 3600000)) return json({ error: '操作过于频繁，请稍后再试' }, 429);
    let body;
    try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const me = (await loadArr(env, 'users')).list.find(x => x.phone === token.phone);
    if (!me) return json({ error: '账号不存在' }, 404);
    if (me.banned) return json({ error: '账号已被限制使用：' + (me.banReason || '违反门店规则') }, 403);
    const scripts = await loadArr(env, 'scripts');
    const sc = scripts.list.find(x => String(x.id) === String(body.sid));
    if (!sc) return json({ error: '剧本不存在' }, 404);
    if (sc.onSale === false) return json({ error: '该剧本已下架' }, 400);
    const st = await getSettings(env);
    const ts = parseInt(body.ts, 10) || 0;
    const time = String(body.time || '19:00');
    if (!ts) return json({ error: '请选择日期' }, 400);
    const pr = playerRange(sc);
    const players = Math.max(1, Math.min(pr.max, parseInt(body.players, 10) || pr.min));
    const mode = body.mode === '包车' ? '包车' : '拼车';
    /* 37：命中已排场次时校验余位并绑定 */
    const ses = (await loadArr(env, 'sessions')).list
      .find(x => String(x.sid) === String(sc.id) && x.ts === ts && x.time === time && x.status === 'open');
    let sessionId = 0;
    const bkAll = await loadArr(env, 'bookings');
    if (ses) {
      const used = bkAll.list.filter(b => b.sessionId === ses.id && b.status !== 'cancelled')
        .reduce((n, b) => n + (b.players || 1), 0);
      const left = (ses.cap || 99) - used;
      if (left < players) return json({ error: `该场次仅剩 ${Math.max(0, left)} 个位置，请调整人数或换个时段` }, 409);
      sessionId = ses.id;
    }
    /* 20：线上选角（仅当该剧本在后台开启了「可提前选角」） */
    let role = '';
    if (sc.allowRolePick === true) {
      role = cleanText(body.role, 20);
      if (role) {
        const names = (sc.roles || []).map(r => r.name);
        if (names.length && names.indexOf(role) < 0) return json({ error: '角色不存在' }, 400);
        if (ses && bkAll.list.some(b => b.sessionId === ses.id && b.role === role && b.status !== 'cancelled'))
          return json({ error: `角色「${role}」已被选走，换一个吧` }, 409);
      }
    }
    /* 59：优惠券（定金抵扣） */
    let coupon = null;
    if (body.couponId) {
      coupon = (await loadArr(env, 'coupons')).list.find(c => String(c.id) === String(body.couponId) && !c.used &&
        (c.all || c.phone === me.phone) && (!c.exp || c.exp > Date.now()));
      if (!coupon) return json({ error: '优惠券不可用' }, 400);
    }
    const now = Date.now();
    /* 8：会员等级折扣（按该客户累计消费自动计算，服务端算价，前端改不了） */
    const spentBefore = bkAll.list.filter(b => b.phone === me.phone && b.status !== 'cancelled')
      .reduce((n, b) => n + (Number(b.price) || 0) * (b.players || 1), 0);
    const tier = tierOf(spentBefore);
    const basePrice = (Number(sc.price) || 0) + (body.dmPhone ? (Number(st.dmFee) || 0) : 0);
    const price = tier.disc ? Math.round(basePrice * (1 - tier.disc) * 100) / 100 : basePrice;
    const amount = price * players;
    let deposit = Math.round(amount * (Number(st.depositRatio) || 0.3));
    if (coupon) deposit = Math.max(0, deposit - (Number(coupon.amount) || 0));
    const booking = {
      id: now + Math.floor(Math.random() * 90), phone: me.phone, username: me.username,
      sid: sc.id, title: sc.title, emoji: sc.emoji || '🎭', g: sc.g || '', day: dayLabel(ts), ts, time,
      players, price, status: 'booked', mode,
      carNew: mode === '拼车', carOwner: mode === '拼车' ? me.username : null,
      carCap: pr.max, carMin: Math.min(pr.min, players), carTags: [], reserved: 0,
      sessionId, dmPhone: cleanText(body.dmPhone, 20), role,
      verifyCode: String(Math.floor(100000 + Math.random() * 900000)),
      couponId: coupon ? coupon.id : 0, createdAt: now,
    };
    const order = {
      id: now + 91, bid: booking.id, phone: me.phone, username: me.username, title: sc.title,
      day: booking.day, ts, time, players, price, amount, deposit, couponId: coupon ? coupon.id : 0,
      tier: tier.name, discount: tier.disc,
      status: 'unpaid', channel: 'demo', createdAt: now, paidAt: 0, refundAt: 0, tradeNo: '',
    };
    const w1 = await mutate(env, 'bookings', list => list.concat([booking]), '新增预约');
    if (!w1.ok) return json({ error: w1.error }, 502);
    await mutate(env, 'pays', list => list.concat([order]), '新增订单');
    if (coupon) await mutate(env, 'coupons', list => {
      const c = list.find(x => String(x.id) === String(coupon.id));
      if (c) { c.used = true; c.usedAt = now; c.usedBy = me.phone; }
      return list;
    }, '核销优惠券');
    await notify(env, me.phone, '待支付定金', `《${sc.title}》${booking.day} ${booking.time} 已锁定座位，请在 30 分钟内支付定金 ¥${order.deposit}。`, { kind: 'pay' });
    return json({ ok: true, booking, order });
  }
  /* ================= 取消预约（客户） ================= */
  if (request.method === 'POST' && parts[0] === 'booking' && parts[1] === 'cancel') {
    if (!token) return json({ error: '请先登录' }, 401);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    let hit = null;
    const w = await mutate(env, 'bookings', list => {
      hit = list.find(x => String(x.id) === String(body.id) && x.phone === token.phone);
      if (hit) { hit.status = 'cancelled'; hit.cancelAt = Date.now(); hit.cancelBy = 'user'; }
      return list;
    }, '取消预约');
    if (!w.ok) return json({ error: w.error }, 502);
    if (!hit) return json({ error: '预约不存在' }, 404);
    await mutate(env, 'pays', list => { const o = list.find(x => x.bid === hit.id); if (o && o.status === 'unpaid') o.status = 'closed'; return list; }, '关闭订单');
    return json({ ok: true });
  }
  /* ================= 31/42：订单支付 / 退款（金额与规则全部服务端判定） ================= */
  if (request.method === 'POST' && parts[0] === 'order' && parts[1] === 'act') {
    if (!token) return json({ error: '请先登录' }, 401);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const pyR = await loadArr(env, 'pays');
    const order = pyR.list.find(x => String(x.id) === String(body.id));
    if (!order) return json({ error: '订单不存在' }, 404);
    if (order.phone !== token.phone && !staff) return json({ error: '无权操作该订单' }, 403);
    const booking = (await loadArr(env, 'bookings')).list.find(x => x.id === order.bid);
    const st = await getSettings(env);
    const action = String(body.action || '');
    if (action === 'pay') {
      if (order.status !== 'unpaid') return json({ error: '该订单当前不可支付' }, 400);
      /* 6：会员余额支付（储值余额直接抵扣定金，服务端扣款并记流水） */
      if (body.useBalance) {
        const uu = (await loadArr(env, 'users')).list.find(x => x.phone === order.phone);
        const bal = Number((uu && uu.balance) || 0);
        if (bal < order.deposit) return json({ error: `余额不足：当前 ¥${bal}，需要 ¥${order.deposit}` }, 400);
        const wb = await mutate(env, 'users', list => {
          const t = list.find(x => x.phone === order.phone);
          if (t) {
            t.balance = bal - order.deposit;
            t.balanceLogs = Array.isArray(t.balanceLogs) ? t.balanceLogs : [];
            t.balanceLogs.unshift({ id: Date.now(), delta: -order.deposit, reason: '支付定金《' + order.title + '》', at: Date.now() });
            t.balanceLogs = t.balanceLogs.slice(0, 50);
          }
          return list;
        }, '余额支付定金');
        if (!wb.ok) return json({ error: wb.error }, 502);
        const w2 = await mutate(env, 'pays', list => {
          const o = list.find(x => x.id === order.id);
          if (o) { o.status = 'paid'; o.paidAt = Date.now(); o.tradeNo = 'BAL' + Date.now(); o.paidBy = 'balance'; }
          return list;
        }, '余额支付');
        if (!w2.ok) return json({ error: w2.error }, 502);
        await notify(env, order.phone, '定金已支付 ✅（会员余额）',
          `已从余额扣除 ¥${order.deposit}，《${order.title}》座位已锁定。`, { kind: 'pay' });
        return json({ ok: true, status: 'paid', by: 'balance' });
      }
      if (String(env.PAY_ENABLED || '') === 'true') {
        /* 51：真实通道 —— 状态只能由支付回调修改，前端无法「直接改已支付」 */
        return json({ error: '线上支付通道待开通，请选择线下支付或联系门店', needRealPay: true }, 400);
      }
      const w = await mutate(env, 'pays', list => {
        const o = list.find(x => x.id === order.id);
        if (o) { o.status = 'paid'; o.paidAt = Date.now(); o.tradeNo = 'DEMO' + Date.now(); }
        return list;
      }, '模拟支付');
      if (!w.ok) return json({ error: w.error }, 502);
      await notify(env, order.phone, '定金已支付 ✅', `《${order.title}》定金 ¥${order.deposit} 已确认，座位锁定，等你来玩～`, { kind: 'pay' });
      return json({ ok: true, status: 'paid' });
    }
    if (action === 'refund') {
      if (order.status !== 'paid' && order.status !== 'unpaid') return json({ error: '该订单不可退款' }, 400);
      const hours = booking && booking.ts ? (booking.ts - Date.now()) / 3600000 : 999;
      const free = hours >= (Number(st.freeCancelHours) || 24);
      if (!free && !staff) return json({
        error: `距离开场不足 ${st.freeCancelHours} 小时，定金按门店规则不退。如需特殊处理请联系门店，或按门店规则放弃定金取消。`,
        needConfirm: true,
      }, 200);
      const w = await mutate(env, 'pays', list => {
        const o = list.find(x => x.id === order.id);
        if (o) { o.status = free ? 'refunded' : 'closed'; o.refundAt = Date.now(); o.refundAmount = free ? o.deposit : 0; }
        return list;
      }, '退款处理');
      if (!w.ok) return json({ error: w.error }, 502);
      if (booking) {
        await mutate(env, 'bookings', list => {
          const t = list.find(x => x.id === booking.id);
          if (t) { t.status = 'cancelled'; t.cancelAt = Date.now(); t.cancelBy = staff ? 'staff' : 'user'; }
          return list;
        }, '取消预约');
        if (!free && !staff && Number(st.lateCancelPenalty) > 0) {
          let before = 100, after = 100;
          await mutate(env, 'users', list => {
            const u = list.find(x => x.phone === order.phone);
            if (!u) return list;
            before = typeof u.credit === 'number' ? u.credit : 100;
            after = Math.max(0, before - Number(st.lateCancelPenalty) * 10);
            u.credit = after;
            u.creditLogs = Array.isArray(u.creditLogs) ? u.creditLogs : [];
            u.creditLogs.unshift({ id: Date.now(), delta: after - before, reason: '临期取消（未达免费取消时限）', by: '系统', at: Date.now() });
            u.creditLogs = u.creditLogs.slice(0, 100);
            return list;
          }, '临期取消扣信用分');
          await notify(env, order.phone, '信用分变动',
            `因临期取消，信用分 ${before} → ${after} 分。按时到场完成开本可逐步恢复。`, { kind: 'credit' });
        }
      }
      await notify(env, order.phone, free ? '退款已处理' : '取消已登记',
        free ? `《${order.title}》定金 ¥${order.deposit} 已退回，预约已取消。`
          : `《${order.title}》预约已取消（超出免费取消时限，定金不退）。`, { kind: 'pay' });
      return json({ ok: true, refunded: free, amount: free ? order.deposit : 0 });
    }
    return json({ error: '未知操作' }, 400);
  }
  /* ================= 17/18/22：车队上车/退出/候补/聊天/标签 ================= */
  if (request.method === 'POST' && parts[0] === 'car' && parts[1]) {
    if (!token) return json({ error: '请先登录' }, 401);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const bkR = await loadArr(env, 'bookings');
    const ownerId = String(body.carId || '').replace('own-', '');
    const ob = bkR.list.find(x => String(x.id) === ownerId && x.carNew === true);
    if (!ob) return json({ error: '车队已失效' }, 404);
    const action = parts[1];
    const matesOf = () => bkR.list.filter(x => !x.carNew && x.carOwner === ob.username && x.sid === ob.sid &&
      x.ts === ob.ts && x.time === ob.time && x.status !== 'cancelled');
    const inCar = bkR.list.some(x => x.phone === token.phone && x.sid === ob.sid && x.ts === ob.ts &&
      x.time === ob.time && x.status !== 'cancelled');
    if (action === 'join') {
      if (inCar) return json({ error: '你已在该车队中' }, 409);
      const joined = (ob.players || 1) + matesOf().reduce((n, x) => n + (x.players || 1), 0);
      if ((ob.carCap || 8) - joined - (ob.reserved || 0) < 1) return json({ error: '车位已满，可加入候补队列' }, 409);
      const meU = (await loadArr(env, 'users')).list.find(u => u.phone === token.phone) || {};
      const rec = {
        id: Date.now(), phone: token.phone, username: meU.username || token.username,
        sid: ob.sid, title: ob.title, emoji: ob.emoji, g: ob.g, day: ob.day, ts: ob.ts, time: ob.time,
        players: 1, price: ob.price, status: 'booked', mode: '拼车', carNew: false, carOwner: ob.username,
        sessionId: ob.sessionId || 0, dmPhone: '', role: '', verifyCode: '', createdAt: Date.now(),
      };
      const w = await mutate(env, 'bookings', list => list.concat([rec]), '加入车队');
      if (!w.ok) return json({ error: w.error }, 502);
      await notify(env, ob.phone, '有人加入你的车队', `${rec.username} 加入了《${ob.title}》${ob.day} ${ob.time} 的车队。`, { kind: 'car' });
      if (joined + 1 >= (ob.carMin || 4)) {
        [ob].concat(matesOf(), [rec]).forEach(x => {
          if (x.phone) notify(env, x.phone, '车队已成局 🎉', `《${ob.title}》${ob.day} ${ob.time} 已达最低成局人数，准时到场哦～`, { kind: 'car' });
        });
      }
      return json({ ok: true });
    }
    if (action === 'quit') {
      if (!inCar) return json({ error: '你不在该车队中' }, 400);
      const w = await mutate(env, 'bookings', list => list.map(x => (x.phone === token.phone && !x.carNew &&
        x.carOwner === ob.username && x.sid === ob.sid && x.ts === ob.ts && x.time === ob.time && x.status === 'booked')
        ? Object.assign(x, { status: 'cancelled', cancelAt: Date.now() }) : x), '退出车队');
      if (!w.ok) return json({ error: w.error }, 502);
      await notify(env, ob.phone, '有人退出车队', `${token.username} 退出了《${ob.title}》${ob.day} ${ob.time} 的车队。`, { kind: 'car' });
      /* 17：候补队列自动递补 —— 通知最早候补的人 */
      const wl = (await loadArr(env, 'waitlist')).list.filter(x => x.carId === body.carId).sort((a, b) => a.at - b.at);
      if (wl[0]) await notify(env, wl[0].phone, '车队有空位啦 🚗', `《${ob.title}》${ob.day} ${ob.time} 出现空位，快去上车！`, { kind: 'car' });
      return json({ ok: true, waitNotified: !!wl[0] });
    }
    if (action === 'wait') {
      const wlAll = await loadArr(env, 'waitlist');
      if (wlAll.list.some(x => x.carId === body.carId && x.phone === token.phone)) {
        return json({ ok: true, already: true, position: wlAll.list.filter(x => x.carId === body.carId).length });
      }
      await mutate(env, 'waitlist', list => list.concat([{ id: Date.now(), carId: body.carId, phone: token.phone, username: token.username, at: Date.now() }]), '加入候补');
      const pos = (await loadArr(env, 'waitlist')).list.filter(x => x.carId === body.carId).length;
      return json({ ok: true, position: pos });
    }
    if (action === 'msg') {
      const txt = cleanText(body.text, 120);
      if (!txt) return json({ error: '内容不能为空' }, 400);
      if (await badHit(env, txt)) return json({ error: '内容包含敏感词，发送失败' }, 400);
      await mutate(env, 'carmsgs', list => list.concat([{ id: Date.now(), carId: body.carId, by: token.username, phone: token.phone, text: txt, at: Date.now() }]), '车队聊天');
      return json({ ok: true });
    }
    if (action === 'tags') {
      if (ob.phone !== token.phone && !staff) return json({ error: '仅车主可设置车队标签' }, 403);
      const tags = Array.isArray(body.tags) ? body.tags.slice(0, 4).map(t => cleanText(t, 8)) : [];
      const w = await mutate(env, 'bookings', list => {
        const t = list.find(x => x.id === ob.id);
        if (t) t.carTags = tags;
        return list;
      }, '设置车队标签');
      if (!w.ok) return json({ error: w.error }, 502);
      return json({ ok: true, tags });
    }
    if (action === 'reserved') {                 /* 21：熟人预留位（仅车主） */
      if (ob.phone !== token.phone && !staff) return json({ error: '仅车主可设置预留位' }, 403);
      const n = Math.max(0, Math.min(3, parseInt(body.n, 10) || 0));
      const w = await mutate(env, 'bookings', list => {
        const t = list.find(x => x.id === ob.id);
        if (t) t.reserved = n;
        return list;
      }, '设置预留位');
      if (!w.ok) return json({ error: w.error }, 502);
      return json({ ok: true, reserved: n });
    }
    return json({ error: '未知操作' }, 400);
  }

  /* ================= 39/49：留言 / 评价 / 社区（服务端落库 + 敏感词 + 防刷） ================= */
  if (request.method === 'POST' && parts[0] === 'msg' && parts[1] === 'create') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (!rate('msg:' + clientIp(request), 20, 3600000)) return json({ error: '提交过于频繁，请稍后再试' }, 429);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const text = cleanText(body.text, 300);
    if (!text) return json({ error: '留言内容不能为空' }, 400);
    const hidden = await badHit(env, text);
    const rec = {
      id: Date.now(), phone: token.phone, username: token.username,
      cat: cleanText(body.cat, 12) || '💡 建议', text,
      status: hidden ? 'hidden' : 'pending', reply: '', repliedBy: '', createdAt: Date.now(),
    };
    const w = await mutate(env, 'messages', list => list.concat([rec]), '新增留言');
    if (!w.ok) return json({ error: w.error }, 502);
    return json({ ok: true, hidden, msg: rec });
  }
  if (request.method === 'POST' && parts[0] === 'review' && parts[1] === 'create') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (!rate('rv:' + clientIp(request), 20, 3600000)) return json({ error: '提交过于频繁' }, 429);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const bk = (await loadArr(env, 'bookings')).list.find(x => String(x.id) === String(body.bid) && x.phone === token.phone);
    if (!bk) return json({ error: '只能评价自己的场次' }, 403);
    if ((await loadArr(env, 'reviews')).list.some(r => String(r.bid) === String(bk.id))) return json({ error: '这一场已经评价过啦' }, 409);
    const rating = Math.max(1, Math.min(5, parseInt(body.rating, 10) || 5));
    const text = cleanText(body.text, 500);
    const hidden = await badHit(env, text);
    const imgs = Array.isArray(body.imgs) ? body.imgs.filter(u => typeof u === 'string').slice(0, 3) : [];
    const rec = {
      id: Date.now(), sid: bk.sid, bid: bk.id, rating, text, anonymous: !!body.anonymous,
      username: body.anonymous ? '' : token.username,
      dims: (body.dims && typeof body.dims === 'object') ? body.dims : {},
      imgs, dmPhone: bk.dmPhone || '', followUps: [], likes: [], reply: '', hidden, createdAt: Date.now(),
    };
    const w = await mutate(env, 'reviews', list => list.concat([rec]), '新增评价');
    if (!w.ok) return json({ error: w.error }, 502);
    await mutate(env, 'bookings', list => {
      const t = list.find(x => String(x.id) === String(bk.id));
      if (t) { t.reviewed = true; t.reviewPending = false; }
      return list;
    }, '标记已评价');
    /* 10：评价 +5 积分 */
    await mutate(env, 'users', list => {
      const t = list.find(x => x.phone === token.phone);
      if (t) t.points = (Number(t.points) || 0) + 5;
      return list;
    }, '评价积分');
    if (rating <= 2) {                       /* 88：差评预警 */
      const admins = (await loadArr(env, 'users')).list.filter(u => u.role === 'admin' || u.role === 'super');
      for (const u of admins) await notify(env, u.phone, '⚠️ 差评预警', `《${bk.title}》收到 ${rating} 星评价${text ? '：' + text.slice(0, 30) : ''}，请及时处理。`, { kind: 'review' });
      if (bk.dmPhone) await notify(env, bk.dmPhone, '⚠️ 差评预警', `你带的《${bk.title}》收到 ${rating} 星评价，可查看并回复。`, { kind: 'review' });
    }
    return json({ ok: true, hidden, review: rec });
  }
  if (request.method === 'POST' && parts[0] === 'post' && parts[1] === 'create') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (!rate('post:' + clientIp(request), 10, 3600000)) return json({ error: '发帖过于频繁' }, 429);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const title = cleanText(body.title, 40), text = cleanText(body.text, 1000);
    if (!title || !text) return json({ error: '标题与内容都要填写' }, 400);
    const hidden = await badHit(env, title + text);
    const rec = {
      id: Date.now(), type: cleanText(body.type, 12) || 'diary', title, text,
      imgs: Array.isArray(body.imgs) ? body.imgs.filter(u => typeof u === 'string').slice(0, 3) : [],
      phone: token.phone, username: token.username, at: Date.now(), likes: [], reports: [], hidden,
      spoiler: ['diary', 'guide'].indexOf(body.type) >= 0,
    };
    const w = await mutate(env, 'posts', list => list.concat([rec]), '发布社区内容');
    if (!w.ok) return json({ error: w.error }, 502);
    return json({ ok: true, hidden, post: rec });
  }
  if (request.method === 'POST' && parts[0] === 'post' && parts[1] === 'like') {
    if (!token) return json({ error: '请先登录' }, 401);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    let likes = 0;
    const w = await mutate(env, 'posts', list => {
      const p = list.find(x => String(x.id) === String(body.id));
      if (!p) return list;
      p.likes = Array.isArray(p.likes) ? p.likes : [];
      const i = p.likes.indexOf(token.phone);
      if (i >= 0) p.likes.splice(i, 1); else p.likes.push(token.phone);
      likes = p.likes.length;
      return list;
    }, '社区点赞');
    if (!w.ok) return json({ error: w.error }, 502);
    return json({ ok: true, likes });
  }
  if (request.method === 'POST' && parts[0] === 'notice' && parts[1] === 'read') {
    if (!token) return json({ error: '请先登录' }, 401);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const ids = Array.isArray(body.ids) ? body.ids.map(String) : [];
    await mutate(env, 'notices', list => list.map(n => {
      if (ids.length && ids.indexOf(String(n.id)) < 0) return n;
      n.readBy = Array.isArray(n.readBy) ? n.readBy : [];
      if (n.readBy.indexOf(token.phone) < 0 && (!n.to || n.to.indexOf(token.phone) >= 0)) n.readBy.push(token.phone);
      return n;
    }), '标记通知已读');
    return json({ ok: true });
  }

  /* ================= 14：发布拼车需求（服务端自动撮合） ================= */
  if (request.method === 'POST' && parts[0] === 'want' && parts[1] === 'create') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (!rate('want:' + clientIp(request), 20, 3600000)) return json({ error: '操作过于频繁' }, 429);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const sc = (await loadArr(env, 'scripts')).list.find(x => String(x.id) === String(body.sid));
    if (!sc) return json({ error: '剧本不存在' }, 404);
    const ts = parseInt(body.ts, 10) || 0;
    const want = {
      id: Date.now(), phone: token.phone, username: token.username, sid: sc.id, title: sc.title,
      ts, time: String(body.time || '19:00'),
      players: Math.max(1, Math.min(8, parseInt(body.players, 10) || 1)),
      note: cleanText(body.note, 60), status: 'open', at: Date.now(),
    };
    const w = await mutate(env, 'wants', list => list.concat([want]), '发布拼车需求');
    if (!w.ok) return json({ error: w.error }, 502);
    const all = (await loadArr(env, 'wants')).list.filter(x => x.status === 'open' &&
      x.sid === want.sid && x.ts === want.ts && x.time === want.time && x.phone !== token.phone);
    for (const m of all) {
      await notify(env, m.phone, '有人想和你拼车 🚗',
        `${token.username} 也想玩《${sc.title}》${ts ? dayLabel(ts) : ''} ${want.time}，快去拼车页看看～`, { kind: 'car' });
    }
    return json({ ok: true, want, matched: all.map(m => ({ id: m.id, username: m.username, players: m.players })) });
  }
  /* ================= 15：店家协助撮合（把若干需求合成一车） ================= */
  if (request.method === 'POST' && parts[0] === 'want' && parts[1] === 'form') {
    const meF = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    if (!staff) return json({ error: '需要员工权限' }, 403);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const ids = (Array.isArray(body.ids) ? body.ids : []).map(String);
    const picks = (await loadArr(env, 'wants')).list.filter(x => ids.indexOf(String(x.id)) >= 0 && x.status === 'open');
    if (!picks.length) return json({ error: '没有可撮合的需求' }, 400);
    const first = picks[0];
    const sc = (await loadArr(env, 'scripts')).list.find(x => String(x.id) === String(first.sid)) || { price: 0, emoji: '🎭' };
    const total = picks.reduce((n, x) => n + (x.players || 1), 0);
    const now = Date.now();
    const st = await getSettings(env);
    const rows = picks.map((p, i) => ({
      id: now + i, phone: p.phone, username: p.username, sid: p.sid, title: p.title,
      emoji: sc.emoji || '🎭', g: sc.g || '', day: dayLabel(p.ts), ts: p.ts, time: p.time,
      players: p.players, price: Number(sc.price) || 0, status: 'booked', mode: '拼车',
      carNew: i === 0, carOwner: first.username, carCap: playerRange(sc).max, carMin: total,
      carTags: [], reserved: 0, sessionId: 0, dmPhone: '', role: '',
      verifyCode: String(Math.floor(100000 + Math.random() * 900000)), createdAt: now, formedBy: 'staff',
    }));
    const w1 = await mutate(env, 'bookings', list => list.concat(rows), '店家撮合成团');
    if (!w1.ok) return json({ error: w1.error }, 502);
    await mutate(env, 'wants', list => list.map(x => ids.indexOf(String(x.id)) >= 0
      ? Object.assign(x, { status: 'matched', matchedAt: now }) : x), '标记需求已撮合');
    const orders = rows.map((r, i) => ({
      id: now + 500 + i, bid: r.id, phone: r.phone, username: r.username, title: r.title, day: r.day,
      ts: r.ts, time: r.time, players: r.players, price: r.price, amount: r.price * r.players,
      deposit: Math.round(r.price * r.players * (Number(st.depositRatio) || 0.3)), couponId: 0,
      status: 'unpaid', channel: 'demo', createdAt: now, paidAt: 0, refundAt: 0, tradeNo: '',
    }));
    await mutate(env, 'pays', list => list.concat(orders), '撮合订单');
    for (const r of rows) {
      await notify(env, r.phone, '门店已为你撮合成团 🎉',
        `《${r.title}》${r.day} ${r.time} 已凑齐 ${total} 人，请尽快支付定金锁定座位。`, { kind: 'car' });
    }
    return json({ ok: true, created: rows.length });
  }

  /* ================= 54/55：账号自助（改密码 / 换绑手机 / 注销） ================= */
  if (request.method === 'POST' && parts[0] === 'account' && parts[1]) {
    if (!token) return json({ error: '请先登录' }, 401);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const meAcc = (await loadArr(env, 'users')).list.find(x => x.phone === token.phone);
    if (!meAcc) return json({ error: '账号不存在' }, 404);
    const act = parts[1];
    if (act === 'pwd') {
      const pw = String(body.password || '');
      if (pw.length < 6) return json({ error: '密码至少 6 位' }, 400);
      const vc = await checkCode(env, meAcc.email || meAcc.phone, body.code, 'reset');
      if (!vc.ok) return json({ error: vc.error }, 401);
      const h = await newPasswordHash(pw);
      const w = await mutate(env, 'users', list => {
        const t = list.find(x => x.phone === token.phone);
        if (t) t.password = h;
        return list;
      }, '修改密码');
      if (!w.ok) return json({ error: w.error }, 502);
      return json({ ok: true });
    }
    if (act === 'phone') {
      const np = String(body.newPhone || '').trim();
      if (!/^1\d{10}$/.test(np)) return json({ error: '手机号格式不正确' }, 400);
      const vc = await checkCode(env, np, body.code, 'bind');
      if (!vc.ok) return json({ error: vc.error }, 401);
      if ((await loadArr(env, 'users')).list.some(x => x.phone === np)) return json({ error: '该手机号已被使用' }, 409);
      await mutate(env, 'users', list => {
        const t = list.find(x => x.phone === token.phone);
        if (t) { t.oldPhone = t.phone; t.phone = np; }
        return list;
      }, '换绑手机号');
      for (const key of ['bookings', 'pays', 'messages', 'coupons', 'waitlist', 'wants']) {
        await mutate(env, key, list => list.map(x => x.phone === token.phone ? Object.assign(x, { phone: np }) : x), '迁移数据 ' + key);
      }
      await mutate(env, 'favs', list => list.map(x => (x && x.phone === token.phone) ? Object.assign(x, { phone: np }) : x), '迁移收藏');
      return json({ ok: true, newPhone: np });
    }
    if (act === 'delete') {
      const vc = await checkCode(env, meAcc.email || meAcc.phone, body.code, 'delete');
      if (!vc.ok) return json({ error: vc.error }, 401);
      await mutate(env, 'users', list => list.filter(x => x.phone !== token.phone), '注销账号');
      for (const key of ['bookings', 'pays', 'messages', 'coupons', 'waitlist', 'wants']) {
        await mutate(env, key, list => list.filter(x => x.phone !== token.phone), '注销清理 ' + key);
      }
      await mutate(env, 'favs', list => list.filter(x => !(x && x.phone === token.phone)), '注销清理收藏');
      return json({ ok: true });
    }
    return json({ error: '未知操作' }, 400);
  }

  /* ================= 21：核销（管理端 / DM 端，支持输入 6 位核销码） ================= */
  if (request.method === 'POST' && parts[0] === 'staff' && parts[1] === 'verify') {
    const meV = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    const role = meV ? meV.role : 'super';
    if (!staff && role !== 'dm') return json({ error: '需要员工权限' }, 403);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const code = String(body.code || '').trim();
    const bid  = body.id ? String(body.id) : '';
    let hit = null, action = 'done';
    const w = await mutate(env, 'bookings', list => {
      hit = bid ? list.find(x => String(x.id) === bid) : list.find(x => String(x.verifyCode) === code);
      if (!hit) return list;
      if (body.action === 'arrive') { hit.status = 'arrived'; hit.arriveAt = Date.now(); action = 'arrive'; }
      else { hit.status = 'done'; hit.doneAt = Date.now(); }
      hit.verifyBy = (meV && meV.username) || '员工';
      return list;
    }, '核销');
    if (!w.ok) return json({ error: w.error }, 502);
    if (!hit) return json({ error: '没有找到该核销码对应的预约' }, 404);
    await mutate(env, 'logs', list => list.concat([{
      id: Date.now(), by: (meV && meV.username) || '员工', role: meV ? meV.role : 'admin',
      text: `核销「${hit.title}」${hit.day} ${hit.time}（${hit.username || ''}）`, kind: 'verify', at: Date.now(),
    }]), '核销留痕');
    /* 10：完成开本 +10 积分（服务端计分，前端改不了） */
    if (action === 'done') {
      await mutate(env, 'users', list => {
        const t = list.find(x => x.phone === hit.phone);
        if (t) t.points = (Number(t.points) || 0) + 10;
        return list;
      }, '开本积分');
    }
    await notify(env, hit.phone, action === 'arrive' ? '已到店签到 ✅' : '开本完成，快来评价吧 ⭐',
      action === 'arrive' ? `《${hit.title}》已签到，祝你玩得开心～` : `《${hit.title}》已完成，给这次体验打个分吧～`, { kind: 'verify' });
    return json({ ok: true, booking: hit, action });
  }

  /* ================= 33：我的数据（客户只拿得到自己的信息） ================= */
  if (request.method === 'GET' && parts[0] === 'my' && parts[1]) {
    if (!token) return json({ error: '请先登录' }, 401);
    const cur = await readFile(env, 'users');
    const me = (Array.isArray(cur.data) ? cur.data : []).find(x => x.phone === token.phone);
    if (!me) return json({ error: '账号不存在' }, 404);
    const kind = parts[1];
    if (kind === 'bookings') {
      const r = await loadArr(env, 'bookings');
      return json(r.list.filter(b => b.phone === me.phone).sort((a, b) => (b.id || 0) - (a.id || 0)), 200);
    }
    if (kind === 'orders') {
      const r = await loadArr(env, 'pays');
      return json(r.list.filter(o => o.phone === me.phone).sort((a, b) => (b.id || 0) - (a.id || 0)), 200);
    }
    if (kind === 'messages') {
      const r = await loadArr(env, 'messages');
      return json(r.list.filter(m => m.phone === me.phone).sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0)), 200);
    }
    if (kind === 'notices') {
      const r = await loadArr(env, 'notices');
      return json(r.list.filter(n => !Array.isArray(n.to) || n.to.includes(me.phone))
        .map(n => Object.assign({}, n, { to: undefined })).slice(0, 100), 200);
    }
    if (kind === 'coupons') {
      const r = await loadArr(env, 'coupons');
      return json(r.list.filter(c => c.all || c.phone === me.phone).sort((a, b) => (b.id || 0) - (a.id || 0)), 200);
    }
    if (kind === 'favs') {
      const r = await loadArr(env, 'favs');
      const rec = r.list.find(x => x && typeof x === 'object' && !Array.isArray(x) && x.phone === me.phone);
      return json((rec && Array.isArray(rec.sids)) ? rec.sids : [], 200);
    }
    if (kind === 'carmsgs') {
      const r = await loadArr(env, 'carmsgs');
      const cid = url.searchParams.get('carId') || '';
      return json(r.list.filter(m => m.carId === cid).slice(-60)
        .map(m => Object.assign({}, m, { phone: undefined })), 200);
    }
    return json({ error: 'not found' }, 404);
  }

  /* ================= 33：公开聚合（评分/余位/车队/榜单，无手机号） ================= */
  if (request.method === 'GET' && parts[0] === 'agg' && parts[1] === 'summary') {
    return json(await summaryOf(env, token ? token.phone : ''), 200);
  }
  /* ================= 公开名册（昵称/头像/性别年龄段，用于同性同龄拼车） ================= */
  if (request.method === 'GET' && parts[0] === 'roster') {
    if (!token) return json({ error: '请先登录' }, 401);
    const r = await loadArr(env, 'users');
    return json(r.list.filter(u => !u.banned).map(publicUser), 200);
  }
  /* ================= 收藏切换（客户自助） ================= */
  if (request.method === 'POST' && parts[0] === 'fav' && parts[1] === 'toggle') {
    if (!token) return json({ error: '请先登录' }, 401);
    let body;
    try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const sid = String(body.sid);
    let out = [];
    const w = await mutate(env, 'favs', list => {
      let rec = list.find(x => x && !Array.isArray(x) && x.phone === token.phone);
      if (!rec) { rec = { phone: token.phone, sids: [] }; list.push(rec); }
      rec.sids = Array.isArray(rec.sids) ? rec.sids : [];
      const i = rec.sids.indexOf(sid);
      if (i >= 0) rec.sids.splice(i, 1); else rec.sids.push(sid);
      out = rec.sids.slice();
      return list;
    }, '更新收藏');
    if (!w.ok) return json({ error: w.error }, 502);
    return json({ ok: true, favs: out });
  }
  /* ================= 37/47/53：图片上传与读取（独立存储，不塞进 localStorage） ================= */
  if (request.method === 'POST' && parts[0] === 'upload') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (!rate('up:' + clientIp(request), 40, 3600000)) return json({ error: '上传过于频繁，请稍后再试' }, 429);
    let body;
    try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const r = await uploadImage(env, body.data);
    if (!r.ok) return json({ error: r.error }, 400);
    return json({ ok: true, url: r.url, size: r.size });
  }
  if (request.method === 'GET' && parts[0] === 'img' && parts[1]) {
    const p = parts.slice(1).join('/');
    if (!/^img\/\d{6}\/[\w.-]+$/.test(p)) return json({ error: 'bad path' }, 400);
    return await serveImage(env, p, request);
  }

  /* ================= 45：DM 专属视图（只能看自己场次的客户） ================= */
  if (parts[0] === 'dm' && (parts[1] === 'customers' || parts[1] === 'credit')) {
    const meD = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    const dmRole = meD ? meD.role : '';
    if (!staff && dmRole !== 'dm') return json({ error: '需要员工权限' }, 403);
    const bkAll = await loadArr(env, 'bookings');
    const sesAll = await loadArr(env, 'sessions');
    const mySes = staff ? null : new Set(sesAll.list.filter(s => s.dm === meD.phone).map(s => s.id));
    const mineOf = (b) => staff ? true
      : ((b.sessionId && mySes.has(b.sessionId)) || (meD && b.dmPhone === meD.phone));

    if (parts[1] === 'customers' && request.method === 'GET') {
      const us = await loadArr(env, 'users');
      const mine = bkAll.list.filter(mineOf);
      const phones = new Set(mine.map(b => b.phone));
      const out = us.list.filter(u => phones.has(u.phone)).map(u => {
        const bs = mine.filter(b => b.phone === u.phone);
        return {
          username: u.username, phone: u.phone, phoneMask: maskPhone(u.phone),
          credit: typeof u.credit === 'number' ? u.credit : 100,
          plays: bs.filter(b => b.status === 'done').length,
          spend: bs.reduce((n, b) => n + (Number(b.price) || 0) * (b.players || 1), 0),
        };
      }).sort((a, b) => b.plays - a.plays);
      return json(out);
    }

    if (parts[1] === 'credit' && request.method === 'POST') {
      let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
      const phone = String(body.phone || '');
      const delta = Math.max(-100, Math.min(100, parseInt(body.delta, 10) || 0));
      if (!delta) return json({ error: '请填写调整分值' }, 400);
      if (!staff && !bkAll.list.some(b => b.phone === phone && mineOf(b))) {
        return json({ error: '只能调整自己场次客户的信用分' }, 403);
      }
      const reason = cleanText(body.reason, 40) || (delta > 0 ? 'DM 加分' : 'DM 扣分');
      let before = 100, after = 100, uname = '';
      const w = await mutate(env, 'users', list => {
        const u = list.find(x => x.phone === phone);
        if (!u) return list;
        before = typeof u.credit === 'number' ? u.credit : 100;
        after = Math.max(0, Math.min(120, before + delta));
        u.credit = after;
        u.creditLogs = Array.isArray(u.creditLogs) ? u.creditLogs : [];
        u.creditLogs.unshift({ id: Date.now(), delta, reason, by: 'DM ' + ((meD && meD.username) || ''), at: Date.now() });
        u.creditLogs = u.creditLogs.slice(0, 100);
        uname = u.username;
        return list;
      }, 'DM 调整信用分');
      if (!w.ok) return json({ error: w.error }, 502);
      if (!uname) return json({ error: '客户不存在' }, 404);
      await mutate(env, 'logs', list => list.concat([{
        id: Date.now(), by: (meD && meD.username) || 'DM', role: 'dm',
        text: `调整「${uname}」信用分 ${delta > 0 ? '+' : ''}${delta}（${reason}）`, kind: 'credit', at: Date.now(),
      }]), '信用分留痕');
      await notify(env, phone, '信用分变动提醒',
        `因「${reason}」，你的信用分 ${before} → ${after} 分。${delta > 0 ? '感谢你的良好记录～' : '按时到场可逐步恢复。'}`, { kind: 'credit' });
      return json({ ok: true, before, after });
    }
  }

  /* ================= 员工操作台（拉黑 / 档案留痕 / 发券 / 结算 / 场次 / 清空） ================= */
  if (request.method === 'POST' && parts[0] === 'staff' && parts[1] && parts[1] !== 'verify') {
    if (!staff) return json({ error: '需要员工权限' }, 403);
    let body; try { body = JSON.parse(await request.text()); } catch (e) { return json({ error: '参数错误' }, 400); }
    const meS = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');
    const meName = (meS && meS.username) || '管理端';
    const meRole = (meS && meS.role) || 'super';
    const superOk = meRole === 'super' || (env.APP_KEY && request.headers.get('x-app-key') === env.APP_KEY);
    const log = (text, kind) => mutate(env, 'logs', list => list.concat([{
      id: Date.now(), by: meName, role: meRole, text, kind: kind || 'staff', at: Date.now(),
    }]), '写入操作日志');
    const op = parts[1];

    /* 30：拉黑 / 恢复账号（被拉黑者无法登录、无法预约） */
    if (op === 'ban') {
      const phone = String(body.phone || '');
      let banned = false, uname = '';
      const w = await mutate(env, 'users', list => {
        const u = list.find(x => x.phone === phone);
        if (!u) return list;
        if (u.super === true || u.role === 'super') return list;
        u.banned = !u.banned;
        banned = u.banned;
        u.banReason = banned ? (cleanText(body.reason, 60) || '违反门店规则') : '';
        uname = u.username;
        return list;
      }, '限制/恢复账号');
      if (!w.ok) return json({ error: w.error }, 502);
      if (!uname) return json({ error: '账号不存在或不可限制' }, 404);
      await log(`${banned ? '限制' : '恢复'}账号「${uname}」`, 'ban');
      if (banned) await notify(env, phone, '账号已被限制', `原因：${cleanText(body.reason, 60) || '违反门店规则'}。如有疑问请联系门店。`, { kind: 'ban' });
      return json({ ok: true, banned, username: uname });
    }
    /* 6：会员储值（后台充值，余额可直接抵扣定金） */
    if (op === 'recharge') {
      const phone = String(body.phone || '');
      const amount = parseInt(body.amount, 10) || 0;
      if (!amount) return json({ error: '请填写充值金额' }, 400);
      let before = 0, after = 0, uname = '';
      const w = await mutate(env, 'users', list => {
        const u = list.find(x => x.phone === phone);
        if (!u) return list;
        before = Number(u.balance) || 0;
        after = before + amount;
        u.balance = after;
        u.balanceLogs = Array.isArray(u.balanceLogs) ? u.balanceLogs : [];
        u.balanceLogs.unshift({ id: Date.now(), delta: amount, reason: cleanText(body.note, 40) || '门店充值', by: meName, at: Date.now() });
        u.balanceLogs = u.balanceLogs.slice(0, 50);
        uname = u.username;
        return list;
      }, '会员充值');
      if (!w.ok) return json({ error: w.error }, 502);
      if (!uname) return json({ error: '客户不存在' }, 404);
      await log(`为「${uname}」充值 ¥${amount}（${before} → ${after}）`, 'balance');
      await notify(env, phone, '💰 会员余额已到账', `充值 ¥${amount}，当前余额 ¥${after}。余额可直接抵扣定金。`, { kind: 'balance' });
      return json({ ok: true, before, after });
    }
    /* 57：查看客户档案（先留痕再返回数据） */
    if (op === 'customer') {
      const phone = String(body.phone || '');
      const u = (await loadArr(env, 'users')).list.find(x => x.phone === phone);
      if (!u) return json({ error: '客户不存在' }, 404);
      await log(`查看了客户「${u.username}」的档案`, 'privacy');
      const bk = await loadArr(env, 'bookings'), py = await loadArr(env, 'pays');
      return json({ ok: true, user: selfUser(u),
        bookings: bk.list.filter(x => x.phone === phone), orders: py.list.filter(x => x.phone === phone) });
    }
    /* 59：发放优惠券（全员或指定手机号） */
    if (op === 'coupon') {
      const amount = Math.max(1, Math.min(500, parseInt(body.amount, 10) || 0));
      const minAmount = Math.max(0, parseInt(body.minAmount, 10) || 0);
      const days = Math.max(1, Math.min(365, parseInt(body.days, 10) || 30));
      const all = !!body.all;
      const phone = String(body.phone || '').trim();
      if (!amount) return json({ error: '请填写抵扣金额' }, 400);
      if (!all && body.all !== 'sleeping' && !/^1\d{10}$/.test(phone)) return json({ error: '请填写正确的手机号，或选择发放对象' }, 400);
      /* 12：给「沉睡客户」发回访券（超过 N 天没到店） */
      if (body.all === 'sleeping') {
        const days = Math.max(7, Math.min(365, parseInt(body.sleepDays, 10) || 30));
        const cutoff = Date.now() - days * 86400000;
        const bkAll = await loadArr(env, 'bookings');
        const users = (await loadArr(env, 'users')).list.filter(u => !u.role || u.role === 'user');
        const sleepers = users.filter(u => {
          const bs = bkAll.list.filter(b => b.phone === u.phone && b.status !== 'cancelled');
          const last = bs.reduce((m, b) => Math.max(m, b.ts || 0, b.createdAt || 0), 0);
          return last > 0 && last < cutoff;
        });
        const rows = sleepers.map((u, i) => ({
          id: Date.now() + i, phone: u.phone, amount, minAmount, kind: 'deposit',
          exp: Date.now() + days * 86400000, used: false, by: meName + '(回访)', createdAt: Date.now(),
        }));
        if (!rows.length) return json({ ok: true, count: 0, msg: `${days} 天内没有沉睡客户` });
        const w0 = await mutate(env, 'coupons', list => list.concat(rows), '沉睡客户回访券');
        if (!w0.ok) return json({ error: w0.error }, 502);
        for (const u of sleepers) {
          await notify(env, u.phone, '好久不见，送你一张券 🎟️',
            `定金抵扣 ¥${amount}，${days} 天内有效。最近上新了不少好本，来看看吧～`, { kind: 'coupon' });
        }
        await log(`给 ${sleepers.length} 位沉睡客户（${days} 天未到店）发回访券 ¥${amount}`, 'coupon');
        return json({ ok: true, count: sleepers.length, msg: `${days} 天未到店 ${sleepers.length} 人` });
      }
      if (all) {
        const users = (await loadArr(env, 'users')).list.filter(u => !u.role || u.role === 'user');
        const rows = users.map((u, i) => ({
          id: Date.now() + i, phone: u.phone, amount, minAmount, kind: 'deposit',
          exp: Date.now() + days * 86400000, used: false, by: meName, createdAt: Date.now(),
        }));
        const w = await mutate(env, 'coupons', list => list.concat(rows), '批量发券');
        if (!w.ok) return json({ error: w.error }, 502);
        for (const u of users) await notify(env, u.phone, '🎟️ 门店送你一张券',
          `定金抵扣 ¥${amount}（满 ¥${minAmount} 可用），${days} 天内有效，下单时可直接使用。`, { kind: 'coupon' });
        await log(`全员发券：抵扣 ¥${amount} × ${users.length} 人`, 'coupon');
        return json({ ok: true, count: users.length });
      }
      const w = await mutate(env, 'coupons', list => list.concat([{
        id: Date.now(), phone, amount, minAmount, kind: 'deposit',
        exp: Date.now() + days * 86400000, used: false, by: meName, createdAt: Date.now(),
      }]), '发券');
      if (!w.ok) return json({ error: w.error }, 502);
      await notify(env, phone, '🎟️ 门店送你一张券', `定金抵扣 ¥${amount}（满 ¥${minAmount} 可用），${days} 天内有效。`, { kind: 'coupon' });
      await log(`给 ${phone} 发券 ¥${amount}`, 'coupon');
      return json({ ok: true, count: 1 });
    }
    /* 26：DM 结算单 */
    if (op === 'settle') {
      const rec = {
        id: Date.now(), ym: cleanText(body.ym, 7), phone: String(body.phone || ''),
        username: cleanText(body.username, 20), sessions: parseInt(body.sessions, 10) || 0,
        revenue: parseInt(body.revenue, 10) || 0, rate: Number(body.rate) || 0,
        amount: parseInt(body.amount, 10) || 0, status: 'paid', paidAt: Date.now(), by: meName,
      };
      const w = await mutate(env, 'settles', list => list.concat([rec]), '保存结算单');
      if (!w.ok) return json({ error: w.error }, 502);
      await log(`结算 DM「${rec.username}」${rec.ym} 分成 ¥${rec.amount}`, 'settle');
      if (rec.phone) await notify(env, rec.phone, '💰 分成已结算',
        `${rec.ym} 带本 ${rec.sessions} 场，分成 ¥${rec.amount} 已结算，辛苦了！`, { kind: 'settle' });
      return json({ ok: true, settle: rec });
    }
    /* 58：场次锁定 / 取消（带原因）；46：房间冲突服务端兜底 */
    if (op === 'session') {
      const id = String(body.id || '');
      const st = ['open', 'locked', 'ongoing', 'done', 'cancelled'].indexOf(body.status) >= 0 ? body.status : 'open';
      const reason = cleanText(body.reason, 60);
      let hit = null, clash = false;
      const w = await mutate(env, 'sessions', list => {
        const t = list.find(x => String(x.id) === id);
        if (!t) return list;
        if (st === 'open' && t.roomId && list.some(x => x.id !== t.id && x.roomId === t.roomId &&
          x.ts === t.ts && x.time === t.time && x.status !== 'cancelled')) { clash = true; return list; }
        t.status = st; t.statusReason = reason; t.statusBy = meName; t.statusAt = Date.now();
        hit = t;
        return list;
      }, '场次状态变更');
      if (!w.ok) return json({ error: w.error }, 502);
      if (clash) return json({ error: '该房间同一时段已有其它场次，无法开回「待开」状态' }, 409);
      if (!hit) return json({ error: '场次不存在' }, 404);
      if (st === 'cancelled') {
        const bk = await loadArr(env, 'bookings');
        for (const b of bk.list.filter(x => x.sessionId === hit.id && x.status === 'booked')) {
          await notify(env, b.phone, '场次变动通知',
            `《${hit.title}》${dayLabel(hit.ts)} ${hit.time} 的场次${reason ? '（' + reason + '）' : ''}已取消，请联系门店改约。`, { kind: 'session' });
        }
      }
      await log(`场次《${hit.title}》${hit.time} 改为 ${st}${reason ? '（' + reason + '）' : ''}`, 'session');
      return json({ ok: true, session: hit });
    }
    /* 44：清空全部业务数据（仅超级管理员；前端需二次确认） */
    if (op === 'purge') {
      if (!superOk) return json({ error: '仅超级管理员可清空数据' }, 403);
      const cleared = {};
      for (const key of ['bookings', 'pays', 'messages', 'reviews', 'posts', 'carmsgs', 'waitlist', 'wants', 'coupons', 'notices', 'logs', 'dmleave']) {
        const w = await mutate(env, key, () => [], '清空 ' + key);
        cleared[key] = w.ok;
      }
      await log('清空了全部业务数据（账号与剧本保留）', 'purge');
      return json({ ok: true, cleared });
    }
    return json({ error: '未知操作' }, 400);
  }

  /* ================= 51：支付（真实通道骨架；未配置商户号时保持演示模式） =================
     接入步骤见文件底部「支付接入说明」。要点：前端永远拿不到改状态的权限，
     支付成功只认 /api/pay/notify 回调（验签后由服务端把订单标为 paid）。 */
  if (request.method === 'POST' && parts[0] === 'pay' && parts[1] === 'create') {
    if (!token) return json({ error: '请先登录' }, 401);
    if (String(env.PAY_ENABLED || '') !== 'true') {
      return json({ ok: false, demo: true, error: '未开通线上支付，请使用模拟支付或到店支付' }, 400);
    }
    return json({ ok: false, error: '支付通道待配置：请在 Cloudflare 配置 PAY_MCHID / PAY_APIV3 / PAY_PRIVATE_KEY 后补全下单逻辑' }, 501);
  }
  if (request.method === 'POST' && parts[0] === 'pay' && parts[1] === 'notify') {
    if (!env.PAY_APIV3) return json({ code: 'FAIL', message: '未配置支付密钥' }, 400);
    return json({ code: 'FAIL', message: '回调验签待实现：配置商户号后补全验签与置「已支付」逻辑' }, 400);
  }

  return json({ error: 'not found' }, 404);
}
