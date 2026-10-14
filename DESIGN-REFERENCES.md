# 参考映射总表 · 甜薯剧本杀（unseen 版）

> 先说一句实话，免得你按错误的前提验收：

**「逐行都能在参考站找到出处」这件事做不到，而且不该做。** 原因三条，都是硬事实：

1. **技术栈不同。** 参考站是 Nuxt/Vue（hubtown、bienville）、Webflow+Lenis（whiteboard）、Next/React（unseen、cosmos）。我们是 Flask + Jinja 服务端渲染。他们的 JS 是打包压缩后的构建产物，直接搬过来既跑不动也侵版权。
2. **真正值得搬的不是代码，是"设计意图 + 技术手法"。** 比如 unseen.co 的换页，代码层面是 Nuxt 路由 + 一个 WebGL 位移贴图；我们做的是同一件事的等价实现：fetch 换 DOM + CSS animation 双向位移 + 三条光带做液面。**看见的是同一个东西，代码一行都不一样。**
3. **有三成的东西是参考站里根本没有的** —— 我们的业务（拼车、定金、DM 工作台、核销）他们不做。那些部分我标了「原创」，不硬编出处。

所以这份表做到的是：**每一块实现都能追溯到「人、站、具体手法」三件套；原创的部分我明说是原创。**

---

## 一、你给过我的所有网站（11 个，逐站列）

| # | 站点 | 你给的场合 | 我实际抓到的硬事实（不是猜） | 甜薯在哪用了它 |
|---|---|---|---|---|
| 1 | **unseen.co** | 最初指定"要学习的网站" | 克制 3D 沉浸 / 自定义光标 / 页面转场 / 胶片颗粒 | 转场、光标、暗场基调、逐字揭示 |
| 2 | **unseen.co/projects** | 你给的三张截图 | Selected Work 编辑网格、hover 才显色的缩略图、子页独立主题色 | 本本墙卡片、海报廊、详情页 |
| 3 | **symphonyofvines.unseen.co** | 早期给的 | 暗色沉浸 / 光标实时雕刻画面 / 分章滚动 / 胶片颗粒 | 全站 WebGL 暗场（追光 + 雕刻） |
| 4 | **blueyard.com** | 早期给的 | 浅色编辑式 / 开篇宣言 / 章节叙事 / WebGL 背景随滚动变 | 章节化布局、`.band` 抬头带、页脚目录、排版比例 |
| 5 | **whiteboard.is** | 你说的"这两个网站交互体验非常不错" | Webflow+Lenis；h1 `Apris` 129.5px **真斜体**；15 段 `<video loop muted>`；`PRESS S TO START` | 键盘入口（按 S 随机挑本）、`font-synthesis:none` 真斜体教训、循环视频素材位 |
| 6 | **bienvillecapital.com/vision** | 同上 | Nuxt/Vue；`bodyBg rgb(25,25,25)`；`bodyCursor:none`；**`scrollH === 视口高`（单屏固定视图）**；中央那个会变色的光点是 **DOM/CSS 做的，不是 WebGL** | 「固定视图 + 场景转场」方向、光色随进度变（`uChapter`） |
| 7 | **experiencethebestyou.com** | 早期给的 | 柔和渐变 / Lenis 平滑滚动 / 鼠标弱视差 / 3D 倾斜卡片 | 惯量滚动、`data-float` 视差 |
| 8 | **hubtown.co.in** | **本轮你指定**："布局和 UI 设计非常不错" | **底色 `rgb(2,10,24)` 深海军蓝黑**（技能文档里写的"暖调米白"是错的，我改了）；标签字体 `Commit Mono` **8.25px / letter-spacing 1.32px / uppercase**；`scrollH === 视口高`；内容主体在 canvas，DOM 只负责"图框" | 微型标签 `.micro`、图框行 `.frame`、首屏 loader 的极简方块语法 |
| 9 | **cosmos.so** | awwwards 技能内置标杆 | 12 列不对称栅格 / 排版做设计 / 速度感应横向 marquee | 滚动字幕条、数字滚动、节奏变化 |
| 10 | **poly.app** | 同上 | 深色极简 UI / 即时精准 hover 反馈 / 等宽数字 | 表单 focus 反馈、mono 数字 |
| 11 | **rspca animal futures** | 同上 | 游戏化 3D 探索 / 卡片弹出 + 进度条 | （低优先级，本项目未采用） |

外加 nova.js 注释里点名的两个外部库作者：**asscroll**（unseen 的平滑滚动实现）、**Lenis**（whiteboard/bienvenue 用的）。

---

## 二、逐块对照（甜薯每一块 → 出处 → 落在哪个文件）

### A. 框架 / 视觉系统

| 甜薯的实现 | 出处 | 落地位置 |
|---|---|---|
| 暗场设计令牌（`--paper #0E0C0A` / 朱砂 `--accent #CF5A32` / 暖陶土 `--accent-2`） | blueyard 的深色 + hubtown 的砖红强调 | `unseen.css:8-49` |
| 固定导航 + 印章字标（「薯」字方形印） | unseen.co 的顶部 nav | `layout.html:20-42`、`unseen.css` 的 `.nav` 段 |
| **图框行**（底部一行 10px 微标签，像图纸图签） | **hubtown** 底部三处微标签（`10 SCOPE ST.` / `SCROLL TO EXPLORE` / `CRAFT WITH ♥`） | `layout.html` 的 `.frame`、`unseen.css` 的 `.micro` |
| 页脚三栏目录 | blueyard 的注册/目录式页脚 | `layout.html` 的 `.foot` |
| `font-synthesis: none`（西文真斜体、中文保持正体） | **whiteboard.is** 用的是 Aptis 真斜体；Fraunces 的 `ital` 轴此前从没被请求，中文一直靠浏览器合成倾斜（最典型的廉价 AI 味） | `layout.html:10`（补 `ital` 轴）、`unseen.css` 的 `.h2/.h3/.stage__type` |

### B. 转场 / 进场（本轮重点）

| 甜薯的实现 | 出处 | 落地位置 |
|---|---|---|
| **场景流动式上移**：旧场景上移离场、新场景从下方 11vh 流上来 | **unseen.co** 的换页（你给的三张图，图 2 是过渡中态） | `unseen.css` 的 `@keyframes sceneOut/sceneIn/sceneOutKid` |
| **液面溶接**：三条纵横光带从屏下扫到屏外 | 你给的图 2 —— 整屏被"水"漫过 | `unseen.css` 的 `.transit__band` |
| **青/品红错位色散**：两条 1px 色带错开 35ms | 图 2 里水波折射出的彩色描边 | `unseen.css` 的 `.transit__disp--c/--m` |
| **fetch 换 DOM 实现真无缝**（不是播完动画再 `location.href`） | **nova.js 的 `Transit` 模块**（nova 已实现，我搬了架构） | `unseen.js` 的 `Transit` |
| 壳层/页面级脚本区分（换页时壳层不重跑） | nova 的 `SHELL_JS` 白名单 | `unseen.js` 的 `SHELL_JS` |
| 首屏 loader：一行方块进度 + 两个 mono 小标签 | **hubtown** 的 `LOADING CONTENT` + 16 格进度 + 右上 `413%` | `layout.html` 的 `.boot`、`unseen.js` 的 `initBoot` |
| **上下文转场表**：按 from→to 页面种类选不同转场（flow / rise / veil / sweep） | **unseen.co** 的 Highway *contextual transitions*（`homeToProject`/`toWorld`… 由 REA 逆向确认，见 `rea-runs/HIGHWAY-ASSCROLL-INSTANTIATION.md`） | `unseen.js` 的 `TR` / `pickTransition` / `applyTransition`；`unseen.css` 的 `.transit.tr-*` |

> **v11 增补（Lenis + 上下文转场）**：
> 1. **平滑滚动换成真正的 Lenis**（vendor `lenis.min.js`，暴露 `globalThis.Lenis`）。关键前提是它驱动**原生 scrollTo**
>    （`wrapper.scrollTo`），所以 `window.scrollY` / scroll 事件 / ScrollTrigger / sticky / 锚点照常工作——
>    这正是能安全替换旧手写实现的原因。与 ScrollTrigger 走官方同步：`lenis.on('scroll', ScrollTrigger.update)`
>    + `gsap.ticker.add(t => lenis.raf(t*1000))`。缺 Lenis 时**自动退回**原手写惯量滚动，行为不变。
> 2. **程序化滚动统一入口 `scrollToY(y, immediate)`**：海报廊拖拽、`S` 键挑选、换页复位都走它；
>    有 Lenis 时不让外部直接 `window.scrollTo`（会被 Lenis 每帧拉回去）。学 unseen.co 用 ASScroll 的同一架构：
>    **滚动只由一个引擎驱动，其余模块都读它的结果**。
> 3. **上下文转场**：`Transit` 按「页面种类」配对选转场——默认 `flow`（液面漫过，现状）、进详情 `rise`
>    （更快、单条主液面）、进表单/登录 `veil`（薄幕淡换）、回首页 `sweep`（液面反向回落）。
>    每个变体自带时长，JS 写根元素 `--tr-*`、CSS 只改几何与显隐，**时长仍只有一个来源**。

### C. 首页五幕

| 幕 | 甜薯的实现 | 出处 |
|---|---|---|
| 幕一·光缝 | 全屏巨字 + 一束随光标的暖色追光，未被照亮处压暗 | unseen.co 的光标作用 + symphonyofvines 的"光标雕刻场景" |
| 幕二·海报廊 | 钉住横向滚动的海报廊（ScrollTrigger pin + 拖拽） | **unseen.co/projects** 的 Selected Work 网格 |
| 幕三·时间轴 | 横向排期轴 + 悬浮点放大 | cosmos.so 的"节奏变化"（有快有慢的 section） |
| 幕四·路径 | 超大数字 + 编辑式列表（非重复小节头） | blueyard 的章节式排版 |
| 幕五·引言 | 大字引言轮播 + 进度点 | experiencethebestyou 的引用轮播 |
| 谢幕 CTA | 非居中的双按钮收尾 | blueyard |
| 滚动字幕条 | 速度感应（滚得越快带子越快的）横向 marquee | **cosmos.so** 的招牌（nova 里已实现，我保留） |

> **v10 增补（首页固定视图 + 场景流动进场）**：a3（夜场）/ a4（路径）/ a5（人声）/ 谢幕 curtain 现在带 `data-scene`，用和 v9 换页**同一套**"场景流动上移"语言进场；首屏 hero 滚出时后退淡出。单屏"场景感"借 bienville/hubtown，但**不**照搬 `scrollH===视口高`（我们有 12 个页面要列表要表单）。

### D. 组件

| 甜薯的实现 | 出处 | 落地位置 |
|---|---|---|
| 卡片/海报"默暗、hover 才显色" | **unseen.co/projects**：缩略图平时压暗降饱和，悬停才亮 | `unseen.css` 的 `.card__img` / `.poster__img` 的 `filter: grayscale(.30) saturate(.70) brightness(.60)` → hover 归零 |
| 详情页双栏 + 封面当主角（只做极轻暗角） | unseen.co 的子页 | `unseen/script.html`、`.detail__cover--pic` |
| 细线流水 `.feed`（消息 / 评价列表） | **blueyard** 的目录式列表（细分隔线 + 极小日期） | `unseen.css` 的 `.feed`；`notice.html` / `profile.html` / `dm_profile.html` |
| 暗色抬头带 `.band` | blueyard 的章节头 + unseen 子页的主题色块 | `unseen.css` 的 `.band`；`dm_profile.html` |
| 四格数据条 `.stats` | **hubtown** 的标签网格（横向等分 + 竖分隔线） | `unseen.css` 的 `.stats`；`dm_profile.html` |
| 支付页巨号金额 `¥400` | blueyard 的排版比例（129px 级巨字 + 极小注释） | `unseen.css` 的 `.amount`；`pay_deposit.html` |
| 认证页双栏 `.auth`（左宣言 + 右表单） | blueyard 的编辑式版面 | `unseen.css` 的 `.auth`；`login/register/forgot.html` |
| 表单 focus 光晕（3px 朱砂外圈） | **poly.app** 的即时精准 hover 反馈 | `unseen.css` 的 `.field input:focus` |

### E. 交互（本轮新增的用粗体）

| 甜薯的实现 | 出处 | 落地位置 |
|---|---|---|
| 情境软光标（点 + 环 lerp 跟随 + 文字标签） | unseen.co 的自定义光标 | `unseen.js` 的 `initCursor` |
| **点击落点涟漪** | **nova.js 的 `Cursor`**（"点下去往波纹场里打一发强涟漪"的 DOM 版） | `unseen.js` 的 `rippleAt` |
| **搜索框描边进度环**（巡航转圈 → 聚焦提速 → 提交转满一圈） | **nova.js 的 `Search` 模块** | `unseen.css` 的 `.u-search`、`unseen.js` 的 `initSearch` |
| **本本墙原地换网格**（不整页跳、网址同步） | nova 的前端筛选思路 + 后端早就写好的 `?partial=1` 接口 | `unseen.js` 的 `initLib`、`unseen/_scripts_grid.html` |
| 磁吸按钮 | nova / unseen.co | `unseen.js` 的 `initMagnetic` |
| 逐字遮罩揭示 | **unseen.co** 的招牌（nova.js 注释里自己都标了 "unseen 招牌"） | `unseen.js` 的 `initSplit` |
| `data-reveal` 编号揭示（错峰淡入上浮） | cosmos.so | `unseen.js` 的 `initReveal` |
| `data-float` 弱视差 | experiencethebestyou | `unseen.js` 的 `initFloat` |
| 键盘入口（按 `S` 随机挑一本） | **whiteboard.is** 的 `PRESS S TO START A PROJECT` | `unseen.js` 的 `initShortcut` |
| 惯量平滑滚动（驱动原生 `scrollTo`，保留 sticky/锚点） | experienthebestyou 的 Lenis / unseen 的 asscroll | `unseen.js` 的 `initSmooth` |
| 数字滚动 `data-count` | cosmos.so | `unseen.js` 的 `initCount` |
| 追光自动退场（静止 2.4s → 光退场） | **原创**（"你不动它就不动"这条是我们自己定的原则） | `unseen.js` 的 `initIdle` |

### F. 工程决策

| 甜薯的实现 | 出处 |
|---|---|
| `RENDER_SCALE = 0.55`（后缓冲降到半分辨率）、fbm 6→3 次 × 5→4 层 | **原创**，SwiftShader 实测定位 |
| 禁用 `backdrop-filter` / 全屏 `mix-blend-mode` | **原创**，掉帧真凶定位 |
| 转场时长唯一来源（CSS 变量 + JS 读同一个变量） | **原创**，本轮踩坑后改的 |
| 可重入 rAF（`loop(name,fn)`）+ 页面级监听登记（`pOn/pOff`） | **原创**，换页重跑的必要前提 |
| UiLoader 模板按目录回落 | **原创** |
| `SO_REUSEADDR` 部署修复 | **原创**，线上 TIME_WAIT 排查 |
| **不撞用属性名**（`.field` 撞车 / `data-count` 撞车） | **原创教训** —— 见 `DESIGN-PITFALLS` |
| 中文字体改**系统字族**（撤下 Google 的 Noto Sans/Serif SC 两个 CJK 家族） | 性能取舍：CJK webfont 是首屏最重的一块；见 `OPTIMIZATION-REPORT` §1.1 |
| hero 图**模板直出** + `preload` / `fetchpriority="high"`（不再等 JS 探测才加载） | 性能：让 LCP 候选早发现；见 `OPTIMIZATION-REPORT` §1.2 |
| 安全响应头（nosniff/Referrer-Policy/Permissions-Policy/X-Frame-Options + CSP Report-Only）、`/robots.txt`、`/sitemap.xml` | 2026 基线；CSP 先观察不阻断 |
| unseen 版补上 **Service Worker 注册**（此前只有 base/nova/v1 有） | 一致性修补 |
| 无障碍：`.skip` 跳转链接 + `:focus-visible` 全局焦点环 + 对比度提升（`--ink-3`/`--ink-dim`）+ 表单 label 配对 + flash `aria-live` | WCAG 2.2 AA；自绘光标不能替代键盘焦点 |
| 海报廊 **←/→ 键 + 前后按钮**（拖拽之外的另一条路） | WCAG 2.5.7 Dragging Movements |
| Core Web Vitals **自采**（`vitals.js` → `POST /vitals` → `data/vitals.log`） | 零依赖 RUM，不引第三方 |
| 体积预算 `tools/perf_budget.py` + Nginx 样例 `deploy/nginx.conf.sample` | 防回归 / 部署侧 |
| 标题结构：每页唯一 `h1`（首屏巨字改为 `.stage__type .base` 的 h1）+ 层级不跳 | WCAG 1.3.1 / 结构化 |
| 静态无障碍检查 `tools/a11y_check.py`（无浏览器，可挂 CI） | 自查 lang/alt/label/id/h1/地标/skip |
| CI 门禁 `.github/workflows/ci.yml` | 语法 + 体积预算 + 无障碍 |
| 去「AI 味」：全局圆角 14→2px、药丸按钮/角标/tag 全部改方、筛选 chip 改编辑式文字行、卡片去掉"上浮+大投影" | 对齐 unseen/blueyard 的编辑语汇（无圆角、发丝线、克制动效） |

---

## 三、找不到出处的（诚实标注为原创）

- **业务层全部**：拼车大厅、定金/尾款两段式支付、DM 段位与成长档案、核销码、唠嗑社区、组局排期、消息中心。参考站里没有一门生意和剧本杀有关。
- **中文排版的适配**：参考站全是西文。中文的断行、`font-synthesis: none`、以字型首字替代 emoji 图标、Noto Serif SC 的衬线搭配 —— 都是我们自己定的。
- **所有性能数值**（`0.55` 渲染缩放、`3` 次 fbm、`blur` 上限）。
- **部署与运维**（waitress 端口、systemd、Caddy 反代）。

---

## 四、参考站里有、我们故意没抄的

| 没抄的 | 为什么 |
|---|---|
| 满屏 WebGL 场景（hubtown 的 3D 水面、rspca 的 3D 探索） | 你的机器上软渲染就掉到 46fps；而且剧本杀用户是来看本的，不是来看渲染的。**把 WebGL 当氛围底噪，不当主角。** |
| 全站 `cursor: none` 强制隐藏原生光标 | 表单多的站点会让用户找不到输入点。我们只在鼠标设备上换软光标，触摸设备保留原生。 |
| `scrollH === 视口高` 的单屏固定视图 | bienville 和 hubtown 都是单页宣导站；我们有 12 个页面、要列表要表单。**只借鉴"场景感"，不照搬"单屏"。** |
| 加载 3D 资源期间的长 loader | hubtown 的 loader 会跑十几秒。我们 2.6s 兜底放行 —— 把人关在门外是最贵的错误。 |
| 全屏 `backdrop-filter` 毛玻璃 | 它下面是一块每帧都在变的 WebGL 画布，浏览器必须每帧重做一次全宽模糊。这是掉帧头号元凶。 |

---

## 五、这张表的维护方式

改任何一块之前，先在这里加一行（出处 + 文件 + 手法），再动代码。**下一版验收时你就照着这张表看：有出处的对出处，标"原创"的问我要理由。**
