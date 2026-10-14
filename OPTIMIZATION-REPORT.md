# 甜薯剧本杀 · 网站优化清单（2026-10）

> 方法：先按 10 个方向做大范围检索（Core Web Vitals / CJK 字体 / 图片 / 无障碍 / SEO / 安全头 /
> WebGL 性能 / PWA / Flask 服务端 / 转化 UX），再**逐条对照本仓库真实代码**核对现状，
> 只留下"确实能改、且值得改"的项。每条给：现状 → 依据 → 动作 → 收益 → 风险。
>
> 检索要点来源见文末 §9。本报告只提**方法**，不改动线上行为；落地按 P0→P2 分批。

---

## 0. 一句话结论
最大的两块收益是 **① 中文字体（现在是 Google Fonts 带 2 个 CJK 家族，首屏最重）** 和
**② 图片 LCP 化（hero 无 preload/尺寸/优先级）**；其次是无障碍（自定义光标 + 暗场对比度）、
SEO/社交元信息、安全头、PWA 离线。WebGL 与滚动这块**已经调得不错**（DPR 上限 + 三级降级 + gzip），
不必大动。

---

## 1. P0 · 立刻做（高收益 / 低风险）

### 1.1 中文字体：自托管 + 子集化 + `font-display`
- **现状**：`templates/unseen/layout.html` 从 Google Fonts 一次拉 **5 个家族**——
  `Fraunces`（衬线展示）、`Inter`、`Noto Sans SC`、`Noto Serif SC`（两个中文字库）、`Space Mono`。
  中文家族覆盖上万汉字，即便浏览器只下需要的子集，**fonts.css 的体量与首字节竞争**仍很可观；
  且 2022 起浏览器 **cache partitioning 已让 Google Fonts 的跨站缓存优势消失**。
- **依据**：中文站字体优化通行做法——格式统一 WOFF2 → 子集化（`pyftsubset`/`font-spider`/`cn-font-split`）
  → `font-display: swap/optional` → 只 preload 首屏那一两个字重；实测十几 MB 完整包可裁到几十~几百 KB。
  来源：renrendaima 两篇、scga.hk 2026 Playbook、penchan.co「FCP 17s→2s」。
- **动作**：
  1. 正文中文**优先用系统字体栈**（PingFang / 微软雅黑 / Noto Sans CJK），自定义中文只用于**标题/品牌**；
  2. 真正要用的自定义中文家族**自托管 + 子集化**（只保留站内实际用字），配 `unicode-range` 分层；
  3. 拉丁展示体（Fraunces）可保留但自托管 + 子集化；
  4. `@font-face` 一律 `font-display: swap`（正文 CJK 可 `optional`/`fallback` + `size-adjust` 抹平跳变）；
  5. 只 `preload` 首屏一个关键 woff2，且带 `crossorigin`。
- **收益**：首屏字体字节可从 MB 级降到百 KB 级，直接改善 **LCP/FCP**；弱网不再 FOIT。
- **风险**：子集化后若出现子集外生僻字会回退系统字（建议把子集化纳入构建、随内容更新）。

### 1.2 首屏大图（hero）LCP 化
- **现状**：`static/media/hero.webp`(59KB)/`hero.jpg`(163KB) 由 `unseen.js` 的 `initHeroMedia()` 用 JS
  动态探测后插入 `<img class="stage__media">`/`<video>`；模板里 **无 `preload`、无 `fetchpriority`**。
  LCP 元素是"晚发现的"。
- **依据**：LCP 四段里"资源发现延迟"最易修——hero 图加 `fetchpriority="high"`（+ `preload`），
  **不要 lazy-load LCP 图**；用 AVIF/WebP + `srcset/sizes`；实测可提 LCP 100–400ms，图片任务整体常提 40–60%。
  来源：omegapix / minipx / clickwebstudio 2026。
- **动作**：hero 改由 HTML 直出（而非 JS 插入）以便 `preload`；加 `fetchpriority="high"` + `sizes`；
  保留 JS 的"有视频用视频、否则图片"降级；视频保持 `preload="none"`/`poster`。
- **收益**：LCP 直降；首屏不再"先空一下再出图"。
- **风险**：low——需保证 HTML 直出与 JS 逻辑不重复插入。

### 1.3 图片统一"尺寸 + 解码 + 格式"
- **现状**：`templates/unseen/*` 里 `<img>` 基本**没有 `width/height`**，无 `decoding=async`，
  `loading="lazy"` 仅 11 处（海报/网格）。
- **依据**：`width/height`（或 `aspect-ratio`）是**修 CLS 最高性价比**的一招；非首屏加 `decoding="async"`；
  文本/照片按类型选 AVIF/WebP。来源：nowztech / pixelseed / techinterview 2026。
- **动作**：给所有 `<img>` 补 `width/height`（或容器 `aspect-ratio`）；非 hero 图 `decoding="async"`；
  列表图统一 `loading="lazy"`；`alt` 已有（保持）。
- **收益**：CLS 归零；滚动不再"跳一下"。
- **风险**：low。

---

## 2. P1 · 接下来做（中收益）

### 2.1 无障碍（WCAG 2.2 AA）
- **现状**：`body.has-cursor { cursor: none }` + 自绘光标环；暗场暖色文字（`--ink-dim`/`--ink-3`）等淡色
  未验证对比度；海报廊是**纯拖拽**交互（`initGallery` pointerdown）；
  未发现"跳到主内容"链接、`aria-live` 状态区。
- **依据**：WCAG 2.2 新增项直接相关——**Target Size ≥24px、Dragging Movements 需单指针替代、
  Focus Not Obscured、Focus Appearance**；正文对比度 ≥4.5:1、非文本 ≥3:1；`prefers-reduced-motion`（你们已做）。
  来源：W3C WCAG 2.2 / ramidabdoub / theprojectjugaad / wangchenyu 2026。
- **动作**：
  1. 保留可见 **focus 环**（自定义光标不能替代键盘焦点）；顶部加"跳到主内容"；
  2. 海报廊除了拖拽，加**左右按钮/键盘 ←→**（满足 Dragging 替代）；
  3. 用 axe DevTools / Chrome CSS Overview **扫一遍全站对比度**，暗场淡色字调到 ≥4.5:1；
  4. 表单 label 关联 + 错误**文字**说明（不只红框）+ 提交后 `aria-live` 播报；
  5. 触控目标 ≥44px（导航/分页/关闭）。
- **收益**：合规、可键盘操作、低视力可读；也顺带提升所有人可用性。
- **风险**：medium——需要设计上让"薄"的排版与对比度共存（可只提暗色文字下限，不动版式）。

### 2.2 SEO / 社交元信息
- **现状**：`layout.html` 只有一条 `<meta name="description">`；**无 `canonical`、无 OG/Twitter、
  无 sitemap.xml / robots.txt**；`title` 有 block 但各页未细化；manifest 未在 layout 里引用。
- **依据**：开发者 SEO 清单——唯一 title/desc、canonical、OG(1200×630)、Twitter Card、
  schema（FAQPage/LocalBusiness/Organization）、robots+sitemap、结构化数据助 AI 摘要引用。
  来源：websyro / pwscoding / nowztech / digiroth 2026。
- **动作**：加 `canonical` + OG/Twitter（复用 hero 图）；法务/问答页加 **FAQPage** 结构化数据，
  首页加 **Organization/WebSite**；生成 `robots.txt` + `sitemap.xml`（Flask 路由或静态）。
  注：若站点定位为**内部/小圈层**，SEO 可降级为"只做 OG 分享卡片 + robots 挡爬"。
- **收益**：分享有卡片、搜索有摘要、AI 检索更易引用。
- **风险**：low。

### 2.3 安全响应头（一处中间件搞定）
- **现状**：`app.py`/`tianshu/__init__.py` 未设安全头（已有 gzip、Cache-Control、`SEND_FILE_MAX_AGE`）。
- **依据**：2026 基线六件套——`Content-Security-Policy`、`Strict-Transport-Security`、
  `X-Content-Type-Options: nosniff`、`Referrer-Policy: strict-origin-when-cross-origin`、
  `Permissions-Policy: camera=(), microphone=(), geolocation=()`、`X-Frame-Options: DENY`。
  来源：devtoolsdaily / domainposture / viewpagesource 2026。
- **动作**：在已有的 `@app.after_request` 里统一 `setdefault` 这些头；CSP 先用
  `Content-Security-Policy-Report-Only` 跑一周看违例再强制（注意 Google Fonts / 内联脚本）。
- **收益**：防 XSS/点击劫持/嗅探，低成本高杠杆。
- **风险**：medium——CSP 需按实际资源白名单调，别一把锁死。

### 2.4 PWA / 离线
- **现状**：`static/manifest.webmanifest` 存在但 **layout 未引用**；无 service worker。
- **依据**：PWA 三要素 HTTPS + manifest + SW；离线用 **app shell 预缓存 + 页面 network-first +
  stale-while-revalidate 静态资源**；缓存名带版本、activate 清旧。来源：freewebtoapp / scaler / stackpractices 2026。
- **动作**：layout 引 `manifest` + `theme-color` + `apple-touch-icon`；加一个极简 SW：
  预缓存壳层 CSS/JS/字体 + 一个 offline.html；页面用 network-first。
- **收益**：二次访问秒开、弱网可用、可"添加到主屏"。
- **风险**：medium——SW 缓存策略要防"更新卡住"（版本号 + 更新提示）。

---

## 3. P2 · 观察/渐进（已有基础，别过度）

### 3.1 WebGL 暗场（现状良好，勿大动）
- **现状**：`unseen-field.js` 已 **DPR 上限 `min(1,dpr)*0.55`**、WebGL2→WebGL1(fbm)→`no-field` **三级降级**、
  `REDUCE` 时降帧。属于已经踩过坑并修好的部分。
- **可再进一步**（低优先）：`WebGLRenderer` 换 WebGPU（2026 已生产可用，Three.js 自动回退 WebGL2，
  复杂场景 2–10× ），或 `OffscreenCanvas` 把渲染移出主线程护 INP。**但在当前规模下收益有限，先不做。**
- 来源：meta-sense 2026 / claudecodeguides / playgama。

### 3.2 CSS 合成纪律（例行自查）
- 只动 `transform`/`opacity`（你们已基本遵守）；`will-change` **用时加、用完撤**，别常驻；
  `filter: blur()`/`box-shadow`/`clip-path` 在无 GPU 设备上是重绘，慎做大面积动画。
- 来源：ai-unchained / csdn GPU 加速指南。

### 3.3 服务端/部署
- **现状**：本地用 **waitress（threads=16）**，gzip 已开（标准库）。生产建议前置 **Nginx**：
  静态文件交给 Nginx（开 `expires` 长缓存 + **Brotli**）、HTTP/2、把 `/static/*` 的 `Cache-Control` 拉长。
- 来源：idctop / johal / compilenrun 2026。

### 3.4 转化 UX（若面向顾客）
- 表单"减法"：初次只留 **姓名 + 联系方式 + 需求**（每多一栏转化约降 5–15%）；
  CTA 具体化（"预约 15 分钟"优于"联系我们"）；提交后明确"下一步 + 回复时间"；加社会证明。
- 来源：oui.digital / howdy-creative / jhkuo / bomcreation 2026。

### 3.5 监控 / 防回归
- 加 `web-vitals` 上报（LCP/INP/CLS 真实字段数据）+ Lighthouse CI + **性能预算**（每页 JS/CSS 上限），
  把 §1 的收益锁住，别再被新脚本吃掉。来源：schedars / launchmind 2026。

---

## 4. 与本仓库现状的对照速查
| 方向 | 现状 | 结论 |
|---|---|---|
| 中文字体 | Google Fonts 带 Noto Sans/Serif SC（CJK） | **P0 改**（自托管+子集化） |
| hero LCP | JS 插入图片，无 preload/fetchpriority | **P0 改** |
| 图片尺寸/解码 | 多数无 width/height、无 decoding | **P0 改** |
| WebGL | DPR 上限 + 三级降级 + REDUCE 降帧 | 已达标，勿动 |
| 滚动/动画 | Lenis + GSAP，transform/opacity 为主 | 良好 |
| gzip | 标准库 gzip（app 层） | 良好，生产建议 Nginx+Brotli |
| 安全头 | 无 | **P1 加** |
| SEO/OG/canonical | 仅 1 条 description | **P1 加** |
| robots/sitemap | 无 | P1（或按定位降级） |
| PWA | manifest 未引用、无 SW | P1 |
| 无障碍 | 自绘光标、拖拽交互、暗场淡字对比度未验 | **P1 改** |

---

## 5. 建议实施顺序（两周节奏，取自 CWV 通行打法）
- D1–2：字体自托管+子集化、hero preload/fetchpriority、图片 width/height（**P0 三连**）→ 实测 LCP/CLS。
- D3–5：安全头（CSP report-only 起步）、OG/canonical、manifest 引用。
- D6–9：无障碍（skip link / 焦点环 / 海报廊键盘替代 / 对比度扫描）。
- D10–14：PWA SW + 监控（web-vitals）+ 性能预算，复测并记录。

---

## 6. 检索来源（按主题）
- **Core Web Vitals**：dbestechno.com、launchmind.io、schedars.com、webscore.now、sensussoft.com
- **CJK 字体**：renrendaima.com（两篇）、scga.hk、penchan.co、hkweb font playbook
- **图片优化**：omegapix.app、minipx.com、clickwebstudio.com、pixelseed.net、techinterview.org
- **无障碍**：W3C WCAG 2.2、ramidabdoub.com、theprojectjugaad.com、wangchenyu.com、mivibzzz.com
- **SEO**：websyro.com、pwscoding.co.in、nowztech.com、digiroth.com、orvirt.com
- **WebGL/动画性能**：meta-sense.fr、claudecodeguides.com、playgama.com、ai-unchained.com
- **安全头**：devtoolsdaily.com、domainposture.com、viewpagesource.online、cavarette.com
- **PWA/离线**：freewebtoapp.com、scaler.com、stackpractices.com、azimuddin.bd
- **Flask/部署**：idctop.com、johal.in、compilenrun.com、CSDN Flask 性能
- **转化 UX**：oui.digital、howdy-creative.co、jhkuo.com、leononline.com.tw、bomcreation.com

---

## 7. 落地进度（v12 已实施）

| 项 | 状态 | 落点 |
|---|---|---|
| 中文字体瘦身 | ✅ 已做 | 从 Google Fonts **移除 Noto Sans/Serif SC 两个 CJK 家族**，中文交系统字族；Fraunces 去掉未用字重。`templates/unseen/layout.html` + `static/css/unseen.css` 的 `--font-display/--font-sans` |
| hero LCP | ✅ 已做 | hero 图改**模板直出** + `<link rel=preload as=image fetchpriority=high>` + `width/height/decoding`；`unseen.js` 的 `initHeroMedia` 改为"图片直出、有视频才升级" |
| 图片尺寸/解码 | ✅ 已做 | unseen 各模板补 `decoding="async"`、`loading="lazy"`、关键图 `width/height`（容器本就有 `aspect-ratio`，CLS 已基本解决） |
| 安全头 | ✅ 已做 | `tianshu/__init__.py` 的 `after_request` 统一加 nosniff / Referrer-Policy / Permissions-Policy / X-Frame-Options（HTTPS 下加 HSTS）+ CSP **Report-Only** |
| OG/canonical/manifest/theme-color | ✅ 已做 | `templates/unseen/layout.html`（unseen 版此前只有一条 description） |
| robots.txt / sitemap.xml | ✅ 已做 | `tianshu/__init__.py` 新增 `/robots.txt` 与 `/sitemap.xml` 两个路由 |
| PWA / service worker | ✅ 已补 | unseen 版此前**漏了 SW 注册**，已在 layout 末尾补上（与 base/nova/v1 一致） |
| 无障碍（skip link / 焦点环 / 海报廊键盘替代 / 对比度扫描） | ⏳ 待做 | P1 中风险项，需要设计侧配合，单独排期 |
| Nginx 前置 / Brotli / HTTP2 | ⏳ 待做 | 部署侧 |
| web-vitals RUM + Lighthouse CI + 性能预算 | ⏳ 待做 | 监控侧 |

**验证**：17 路由 sweep 全绿（`unseen` / 坏图 0 / JS 报错 0）；`curl` 复核安全头、robots、sitemap、
`preload/fetchpriority/manifest/SW/canonical/og`、字体 URL 已无 Noto。
