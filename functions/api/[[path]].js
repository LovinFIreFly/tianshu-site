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
const TOKEN_DAYS = 30;

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

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,PUT,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type,x-app-key,x-auth',
  'Access-Control-Max-Age': '86400',
};
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, CORS),
  });

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

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

  const url = new URL(request.url);
  const parts = url.pathname.replace(/^\/api\/?/, '').split('/').filter(Boolean);
  const staff = await isStaff(request, env);
  const token = await readToken(request.headers.get('x-auth'), env.APP_KEY || '');

  /* ---------- POST /api/login 服务端登录 ---------- */
  if (request.method === 'POST' && parts[0] === 'login') {
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
    const role = (u.super === true || u.role === 'super') ? 'super' : (u.role || 'user');
    return json({ ok: true, user: { phone: u.phone, username: u.username, role } });
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

/* ---------- POST /api/code/send 发送验证码 ---------- */
if (request.method === 'POST' && parts[0] === 'code' && parts[1] === 'send') {
  let body;
  try { body = JSON.parse(await request.text()); } catch (e) { return json({ ok: false, error: '参数错误' }, 400); }
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

  /* ---------- POST /api/register 注册（服务端落库，强制客户身份） ---------- */
  if (request.method === 'POST' && parts[0] === 'register') {
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
    /* 服务端校验验证码（邮箱或短信） */
    const vc = await verifyCode(env, codeTarget, code, 'register');
    if (!vc.ok) return json({ ok: false, error: vc.error }, 401);

    const cur = await readFile(env, 'users');
    const users = Array.isArray(cur.data) ? cur.data : [];
    if (users.some(x => x.phone === phone)) return json({ ok: false, error: '该手机号已注册' }, 409);
    if (users.some(x => x.username === name)) return json({ ok: false, error: '用户名已被占用' }, 409);

    const now = Date.now();
    const u = {
      username: name, phone, email,
      password: await newPasswordHash(pw),
      role: 'user', super: false,           // ← 服务端强制：注册只能是客户
      invite: '', credit: 100, creditLogs: [], profile: { avatar: '🎭', nick: '', gender: '', age: null },
      first: now, last: now,
    };
    users.push(u);
    const ok = await writeWithRetry(env, 'users', cur, users, '注册新账号 ' + name);
    if (!ok) return json({ ok: false, error: '写入失败，请重试' }, 502);
    return json({ ok: true, token: await makeToken(u, env.APP_KEY || ''), user: { phone, username: name, role: 'user' } });
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
    if (!ALLOWED.includes(key)) return json({ error: 'key not allowed' }, 400);
    const r = await readFile(env, key);
    if (!r.ok) return json({ error: 'github ' + r.status }, 502);
    if (r.data === null) return json(null, 404);
    /* 用户表脱敏：不返回密码哈希 */
    const data = key === 'users'
      ? r.data.map(u => Object.assign({}, u, { password: undefined }))
      : r.data;
    return json(data, 200);
  }

  /* ---------- PUT /api/data/:key 全量写 ---------- */
  if (request.method === 'PUT' && parts[0] === 'data' && parts[1]) {
    const key = parts[1].replace(/\.json$/, '');
    if (!ALLOWED.includes(key)) return json({ error: 'key not allowed' }, 400);
    if (!PUBLIC_WRITE.includes(key) && !staff) return json({ error: '该数据需要管理员权限' }, 403);
    if (STAFF_ONLY.includes(key) && !staff) return json({ error: '该数据仅管理员可写' }, 403);

    const bodyText = await request.text();
    if (bodyText.length > MAX_BODY) return json({ error: '数据过大' }, 413);
    let payload;
    try { payload = JSON.parse(bodyText); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }

    const cur = await readFile(env, key);
    let data = payload;
    /* 关键：账号表净化
       - 非管理员不得改动 role / super
       - 任何情况下，客户端若没带密码就保留服务端原密码（防止误清空导致全站无法登录）
       - 改密码只能通过 /api/pwd/reset */
    if (key === 'users' && Array.isArray(payload)) {
      const old = new Map((Array.isArray(cur.data) ? cur.data : []).map(x => [String(x.phone), x]));
      data = payload.map(u => {
        const o = old.get(String(u && u.phone));
        if (!o) return Object.assign({}, u, { role: staff ? (u.role || 'user') : 'user', super: staff ? !!u.super : false });
        return Object.assign({}, u, {
          role: staff ? (u.role || o.role || 'user') : (o.role || 'user'),
          super: staff ? !!u.super : !!o.super,
          password: u.password || o.password,
        });
      });
      if (!staff && Array.isArray(cur.data) && data.length < cur.data.length) {
        return json({ error: '不允许删除账号（需管理员）' }, 403);
      }
    }
    const ok = await writeWithRetry(env, key, cur, data, '甜薯数据同步 ' + key);
    return ok ? json({ ok: true, key }) : json({ error: '写入冲突，请重试' }, 502);
  }

  /* ---------- POST /api/append/:key 追加合并 ---------- */
  if (request.method === 'POST' && parts[0] === 'append' && parts[1]) {
    const key = parts[1].replace(/\.json$/, '');
    if (!ALLOWED_APPEND.includes(key)) return json({ error: 'append not allowed' }, 400);
    if (STAFF_ONLY.includes(key) && !staff) return json({ error: '需要管理员权限' }, 403);

    let payload;
    try { payload = JSON.parse(await request.text()); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }
    const items = Array.isArray(payload && payload.items) ? payload.items : [];
    if (!items.length) return json({ ok: true, merged: 0 });
    if (items.length > 500) return json({ error: '单次最多 500 条' }, 413);

    const cur = await readFile(env, key);
    const kf = APPEND_KEYFIELD[key] || 'id';
    const old = Array.isArray(cur.data) ? cur.data : [];
    const map = new Map(old.map(x => [String(x && x[kf]), x]));
    items.forEach(it => {
      if (!it || it[kf] == null) return;
      let v = it;
      if (key === 'users') {                    // 同样做权限净化 + 保护密码
        const o = map.get(String(it[kf]));
        if (!o) {
          v = Object.assign({}, it, { role: staff ? (it.role || 'user') : 'user', super: staff ? !!it.super : false });
        } else {
          v = Object.assign({}, it, {
            role: staff ? (it.role || o.role || 'user') : (o.role || 'user'),
            super: staff ? !!it.super : !!o.super,
            password: it.password || o.password,
          });
        }
      }
      map.set(String(it[kf]), v);
    });
    let merged = [...map.values()].sort((a, b) => (b.id || 0) - (a.id || 0));
    if (key === 'logs') merged = merged.slice(0, 300);
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

  return json({ error: 'not found' }, 404);
}
