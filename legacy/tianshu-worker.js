/**
 * 甜薯剧本杀 · 云端数据代理（Cloudflare Worker）
 * ------------------------------------------------------------
 * 作用：把 GitHub Token 藏在服务端，前端不再接触 Token。
 *   · 所有访客（客户）→ 可读取全部数据；可写入「公开」类数据（预约/评价/留言等）
 *   · 持有管理密钥的人（你 / 店长）→ 可写「设置」类数据（用户账号管理、场次、敏感词等）
 *
 * 部署步骤（约 3 分钟）：
 * 1. Cloudflare 控制台 → Compute (Workers & Pages) → Create → Workers → 选 Hello World 模板
 * 2. 名称填 tianshu-api → Deploy
 * 3. 部署后点 Edit code（或 Quick edit），把本文件内容【全部替换】进去 → Deploy
 * 4. 回到该 Worker → Settings → Variables and Secrets，添加以下变量（选 Secret 类型）：
 *      GITHUB_TOKEN = 你的 Fine-grained Token（Contents: Read and write）
 *      APP_KEY      = 自己设一串长密码，如 tianshu-2026-x7k9q2（管理密钥，别外传）
 *    （可选）REPO  = LovinFireFly/tianshu-data   BRANCH = main
 * 5. 复制 Worker 地址（形如 https://tianshu-api.你的子域.workers.dev）
 * 6. 打开网站 → 管理端 → 数据备份 → 云端同步配置 → 填入 Worker 地址 + 管理密钥 → 保存并测试
 *
 * 安全说明：
 *   · GITHUB_TOKEN 只存在于 Worker 环境变量，网页源码和访客浏览器都拿不到
 *   · 即使有人拿到管理密钥，也只能改这一个数据仓库的数据，无法访问你其他仓库
 */

const DEFAULT_REPO = 'LovinFireFly/tianshu-data';
const DEFAULT_BRANCH = 'main';

/* 允许读写的数据文件 */
const ALLOWED = ['users', 'bookings', 'reviews', 'settings', 'messages', 'notices',
  'rooms', 'sessions', 'carmsgs', 'pays', 'favs', 'taglib', 'dmleave', 'posts', 'badwords', 'logs', 'scripts'];

/* 访客无需密钥即可写入的「业务数据」（客户注册/预约/评价/留言/收藏/发帖等） */
const PUBLIC_WRITE = ['bookings', 'messages', 'reviews', 'posts', 'favs', 'carmsgs', 'pays', 'users'];

const MAX_BODY = 8 * 1024 * 1024;   // 单文件上限 8MB（剧本库含图片时较大）

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
function ghHeaders(env, extra) {
  return Object.assign({
    Authorization: 'Bearer ' + (env.GITHUB_TOKEN || ''),
    Accept: 'application/vnd.github+json',
    'User-Agent': 'tianshu-worker',
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
/* 读取云端文件：返回 { ok, data, sha, status } */
async function readFile(env, key) {
  const res = await fetch(ghUrl(env, key, true), { headers: ghHeaders(env) });
  if (res.status === 404) return { ok: true, data: null, sha: null, status: 404 };
  if (!res.ok) return { ok: false, data: null, sha: null, status: res.status };
  const d = await res.json();
  let parsed = null;
  try { parsed = JSON.parse(b64ToText(d.content)); } catch (e) { parsed = null; }
  return { ok: true, data: parsed, sha: d.sha, status: 200 };
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

    const url = new URL(request.url);
    const staff = !!env.APP_KEY && (request.headers.get('x-app-key') || '') === env.APP_KEY;

    /* 健康检查 */
    if (url.pathname === '/health') {
      const r = await readFile(env, 'users');
      return json({
        ok: r.ok,
        repo: env.REPO || DEFAULT_REPO,
        branch: env.BRANCH || DEFAULT_BRANCH,
        github: r.status,
        tokenSet: !!env.GITHUB_TOKEN,
        appKeySet: !!env.APP_KEY,
      });
    }

    const m = url.pathname.match(/^\/data\/([a-z]+)$/);
    if (!m) return json({ error: 'not found' }, 404);
    const key = m[1];
    if (!ALLOWED.includes(key)) return json({ error: 'key not allowed: ' + key }, 400);

    /* ---------- 读取：所有访客可用 ---------- */
    if (request.method === 'GET') {
      const r = await readFile(env, key);
      if (!r.ok) return json({ error: 'github ' + r.status }, 502);
      if (r.data === null) return json(null, 404);
      return json(r.data, 200);
    }

    /* ---------- 写入 ---------- */
    if (request.method === 'PUT') {
      const isPublic = PUBLIC_WRITE.includes(key);
      if (!isPublic && !staff) return json({ error: '该数据需要管理密钥（请在云端同步配置中填写）' }, 403);

      const bodyText = await request.text();
      if (bodyText.length > MAX_BODY) return json({ error: '数据过大（上限 2MB）' }, 413);
      let payload;
      try { payload = JSON.parse(bodyText); } catch (e) { return json({ error: '不是合法 JSON' }, 400); }

      const cur = await readFile(env, key);

      /* 防篡改：访客不允许删改账号（只允许新增/更新，不允许减少数量） */
      if (key === 'users' && !staff && Array.isArray(cur.data) && Array.isArray(payload) && payload.length < cur.data.length) {
        return json({ error: '不允许删除账号（需管理密钥）' }, 403);
      }

      /* 带 sha 写入，冲突自动重试一次 */
      for (let attempt = 0; attempt < 2; attempt++) {
        const sha = attempt === 0 ? cur.sha : (await readFile(env, key)).sha;
        const res = await fetch(ghUrl(env, key, false), {
          method: 'PUT',
          headers: ghHeaders(env, { 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            message: '甜薯数据同步 ' + key + '（worker）',
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
  },
};
