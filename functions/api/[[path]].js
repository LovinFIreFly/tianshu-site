/**
 * 甜薯剧本杀 · 云端数据代理（Cloudflare Pages Functions 版本）
 * ------------------------------------------------------------
 * 为什么用 Pages Functions 而不是 Workers：
 *   workers.dev 在部分网络环境会被拦截，而它运行在「你网站自己的域名」下
 *   （https://你的站点.pages.dev/api/...），客户访问稳定。
 *
 * 部署方式（GitHub 网页端 3 步，不用命令行）：
 * 1. 在 GitHub 的 tianshu-site 仓库里新建文件夹 functions/api，
 *    并在其中新建文件 [[path]].js，把本文件内容全部粘贴进去 → Commit
 *    （最终路径必须是：tianshu-site/functions/api/[[path]].js）
 * 2. 打开 Cloudflare → Workers & Pages → 你的 Pages 项目 tianshu-co8
 *    → Settings → Variables and secrets → 添加三条（Production 环境）：
 *        GITHUB_TOKEN = 你的 Fine-grained Token（Contents: Read and write）
 *        APP_KEY      = 自己设的管理密钥，如 tianshu-2026-x7k9q2
 *        REPO         = LovinFireFly/tianshu-data
 * 3. 回到项目的 Deployments 标签 → 点最新一次部署右侧「...」→ Retry deployment
 *    （或直接在 GitHub 提交一次改动触发重新部署）
 * 4. 验证：浏览器访问 https://你的站点.pages.dev/api/health
 *    正常返回 {"ok":true,...,"tokenSet":true,"appKeySet":true}
 *
 * 安全说明：
 *   · GITHUB_TOKEN 只存在于 Cloudflare 环境变量，网页源码和访客浏览器都拿不到
 *   · 访客可读全部数据、可写业务数据（预约/评价/留言/收藏等）
 *   · 修改设置类数据（账号权限/场次/敏感词等）需要管理密钥 x-app-key
 */

const DEFAULT_REPO = 'LovinFireFly/tianshu-data';
const DEFAULT_BRANCH = 'main';

const ALLOWED = ['users', 'bookings', 'reviews', 'settings', 'messages', 'notices',
  'rooms', 'sessions', 'carmsgs', 'pays', 'favs', 'taglib', 'dmleave', 'posts', 'badwords', 'logs', 'scripts'];

/* 访客无需密钥即可写入的业务数据 */
const PUBLIC_WRITE = ['bookings', 'messages', 'reviews', 'posts', 'favs', 'carmsgs', 'pays', 'users'];

/* 支持「服务端追加合并」的数据：访客只上报自己的记录，
   由服务端读出最新全量 → 按 id 合并 → 写回，避免覆盖其他设备的记录 */
const ALLOWED_APPEND = ['logs', 'bookings', 'messages', 'reviews', 'posts', 'carmsgs', 'pays'];

const MAX_BODY = 8 * 1024 * 1024;   // 8MB：剧本库含封面/角色图（base64）时体积较大

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,PUT,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type,x-app-key',
  'Access-Control-Max-Age': '86400',
};
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, CORS),
  });

function ghUrl(env, key, withRef) {
  const repo = env.REPO || DEFAULT_REPO;
  const branch = env.BRANCH || DEFAULT_BRANCH;
  return `https://api.github.com/repos/${repo}/contents/${key}.json${withRef ? '?ref=' + branch : ''}`;
}
/* 环境变量里粘贴的 Token 可能带上空格 / 换行，统一清理后再用 */
function cleanToken(env){
  return String(env.GITHUB_TOKEN || '').replace(/\s+/g, '');
}
function ghHeaders(env, extra) {
  return Object.assign({
    Authorization: 'Bearer ' + cleanToken(env),
    Accept: 'application/vnd.github+json',
    'User-Agent': 'tianshu-pages-fn',
  }, extra || {});
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
async function readFile(env, key) {
  const res = await fetch(ghUrl(env, key, true), { headers: ghHeaders(env) });
  if (res.status === 404) return { ok: true, data: null, sha: null, status: 404 };
  if (!res.ok) return { ok: false, data: null, sha: null, status: res.status };
  const d = await res.json();
  let parsed = null;
  try { parsed = JSON.parse(b64ToText(d.content)); } catch (e) { parsed = null; }
  return { ok: true, data: parsed, sha: d.sha, status: 200 };
}

export async function onRequest(context) {
  const { request, env } = context;

  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

  const url = new URL(request.url);
  const parts = url.pathname.replace(/^\/api\/?/, '').split('/').filter(Boolean);
  const staff = !!env.APP_KEY && (request.headers.get('x-app-key') || '') === env.APP_KEY;

  /* GET /api/health */
  if (parts[0] === 'health') {
    const r = await readFile(env, 'users');
    const raw = String(env.GITHUB_TOKEN || '');
    const tok = cleanToken(env);
    let hint = '';
    if (!tok) hint = '未配置 GITHUB_TOKEN';
    else if (!/^github_pat_/.test(tok) && !/^ghp_/.test(tok)) hint = '格式不对：应以 github_pat_ 或 ghp_ 开头';
    else if (tok.length < 40) hint = '长度异常：只有 ' + tok.length + ' 字符，可能复制不全';
    else if (tok !== raw) hint = '已自动清理空格/换行后仍 401，建议重新生成 Token';
    else if (r.status === 401) hint = 'Token 无效或已过期/被吊销，请重新生成';
    return json({
      ok: r.ok,
      repo: env.REPO || DEFAULT_REPO,
      branch: env.BRANCH || DEFAULT_BRANCH,
      github: r.status,
      tokenSet: !!env.GITHUB_TOKEN,
      appKeySet: !!env.APP_KEY,
      tokenPrefix: tok.slice(0, 12),      // 只暴露前 12 位，用于核对类型与开头
      tokenLength: tok.length,
      hint: hint || 'ok',
    });
  }

  /* POST /api/append/:key —— 追加合并（访客可用，用于上报自己的记录） */
  if (request.method === 'POST' && parts[0] === 'append' && parts[1]) {
    const akey = parts[1].replace(/\.json$/, '');
    if (!ALLOWED_APPEND.includes(akey)) return json({ error: 'append not allowed: ' + akey }, 400);

    const bodyText = await request.text();
    if (bodyText.length > 1024 * 1024) return json({ error: '单次上报过大' }, 413);
    let payload;
    try { payload = JSON.parse(bodyText); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }
    const items = Array.isArray(payload && payload.items) ? payload.items : [];
    if (!items.length) return json({ ok: true, merged: 0 });
    if (items.length > 500) return json({ error: '单次最多 500 条' }, 413);

    const cur = await readFile(env, akey);
    const map = new Map((Array.isArray(cur.data) ? cur.data : []).map(x => [String(x && x.id), x]));
    items.forEach(it => { if (it && it.id != null) map.set(String(it.id), it); });
    let merged = [...map.values()].sort((a, b) => (b.id || 0) - (a.id || 0));
    if (akey === 'logs') merged = merged.slice(0, 300);

    for (let attempt = 0; attempt < 3; attempt++) {
      const sha = attempt === 0 ? cur.sha : (await readFile(env, akey)).sha;
      const res = await fetch(ghUrl(env, akey, false), {
        method: 'PUT',
        headers: ghHeaders(env, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          message: '甜薯追加同步 ' + akey,
          branch: env.BRANCH || DEFAULT_BRANCH,
          sha: sha || undefined,
          content: textToB64(JSON.stringify(merged, null, 2)),
        }),
      });
      if (res.ok) return json({ ok: true, merged: merged.length, added: items.length });
      if (!res.ok && attempt < 2) { await new Promise(r => setTimeout(r, 200 * (attempt + 1))); continue; }
      return json({ error: 'github ' + res.status }, 502);
    }
    return json({ error: '写入冲突，请重试' }, 502);
  }

  if (parts[0] !== 'data' || !parts[1]) return json({ error: 'not found' }, 404);
  const key = parts[1].replace(/\.json$/, '');
  if (!ALLOWED.includes(key)) return json({ error: 'key not allowed: ' + key }, 400);

  /* 读取：所有访客可用 */
  if (request.method === 'GET') {
    const r = await readFile(env, key);
    if (!r.ok) return json({ error: 'github ' + r.status }, 502);
    if (r.data === null) return json(null, 404);
    return json(r.data, 200);
  }

  /* 写入 */
  if (request.method === 'PUT') {
    const isPublic = PUBLIC_WRITE.includes(key);
    if (!isPublic && !staff) return json({ error: '该数据需要管理密钥（请在云端同步配置中填写）' }, 403);

    const bodyText = await request.text();
    if (bodyText.length > MAX_BODY) return json({ error: '数据过大（上限 2MB）' }, 413);
    let payload;
    try { payload = JSON.parse(bodyText); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }

    const cur = await readFile(env, key);

    /* 防篡改：访客不允许减少账号数量（删账号必须用管理密钥） */
    if (key === 'users' && !staff && Array.isArray(cur.data) && Array.isArray(payload) && payload.length < cur.data.length) {
      return json({ error: '不允许删除账号（需管理密钥）' }, 403);
    }

    for (let attempt = 0; attempt < 2; attempt++) {
      const sha = attempt === 0 ? cur.sha : (await readFile(env, key)).sha;
      const res = await fetch(ghUrl(env, key, false), {
        method: 'PUT',
        headers: ghHeaders(env, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          message: '甜薯数据同步 ' + key + '（pages-fn）',
          branch: env.BRANCH || DEFAULT_BRANCH,
          sha: sha || undefined,
          content: textToB64(JSON.stringify(payload, null, 2)),
        }),
      });
      if (res.ok) return json({ ok: true, key });
      if ((res.status === 409 || res.status === 412 || res.status === 422) && attempt === 0) continue;
      const t = await res.text();
      return json({ error: 'github ' + res.status + ' ' + t.slice(0, 200) }, 502);
    }
    return json({ error: '写入冲突，请重试' }, 502);
  }

  return json({ error: 'method not allowed' }, 405);
}
