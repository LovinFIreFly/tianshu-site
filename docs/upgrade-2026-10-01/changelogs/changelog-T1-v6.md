# changelog-T1-v6 · 桌面模板与外壳（代号 T1）

> 范围：只动 `tianshu/templates/`（含 admin/、dm/）、`static/sw.js`、`static/manifest.webmanifest`。
> 未碰任何 .py / .css / mobile/ / v1/ / 冻结块。改前均已备份到 `_backup/` 镜像路径。

## 一、逐文件改动

### templates/base.html
- head 最前插入**主题三态内联脚本**：读 cookie `theme`（light/dark/auto，缺省 auto），用 matchMedia 驱动 `document.documentElement[data-theme]`，auto 时监听系统 `prefers-color-scheme` 变化。赶在 CSS 绘制前执行，避免闪白。
- head 追加 **OG meta 块**：`og:site_name`/`og:type`(block `og_type`)/`og:title`(block `og_title`)/`og:description`(block `og_description`)/`og:image`(block `og_image`，默认 `url_for(static icon.svg, _external=True)`)。子页可 override。
- head 追加**埋点 beacon 内联脚本**：`window.load` 后 1.5s 用 `navigator.sendBeacon('/api/track', Blob(JSON {path: location.pathname+search}))`，不阻塞渲染。
- 页脚「去挑本」列追加 `<li><a href="/faq">常见问题</a></li>`。
- 变量：`theme`、`settings.shopName`。

### templates/script.html
- 顶部 override 块：`og_title=sc.title`、`og_description=sc.desc|truncate(60)`、`og_image=sc.img`（http 原样，否则 `request.url_root + lstrip('/')`）。
- 角色卡：既有 `role3__c` 加竖排编号 `<span class="role3__no">` 与一句话人设 `{% if r.line %}<p class="role3__line">{{ r.line }}</p>{% endif %}`；无图 chips 行也补 `r.line`。
- 新增**演绎视频区块**：`{% if sc.videoUrl %}` 朱红外链按钮 `target=_blank rel=noopener`。
- 新增**演后复盘区块**：`{% if canSeeReview and sc.reviewDoc %}`，`<details class="sheet3">` 折叠 + `nl2p|safe` 渲染。
- 行动行加「分享这本」按钮 `#share-btn`（data-share-text）；页尾加 Web Share→clipboard 降级 + `.share-toast` toast 脚本。
- 重排分区编号：角色 01、(视频 02)、(复盘 03)、评价 04、预约 05。
- 变量：`sc.videoUrl`、`sc.reviewDoc`、`sc.roles[].line`、`canSeeReview`。

### templates/car.html
- 页头下加 **GET 筛选条 `.filterbar3`**：`q`(剧本名)/`players`(人数)/`time`(时段 上午/下午/晚上)/`diff`(难度 1-5)，值回显 `{{ q }}/{{ players }}/{{ time }}/{{ diff }}`，带「重置」。
- 车队卡：状态 badge 顺序改为 `closed→已截止`/`filled→补满发车`/`full→已满锁车`；新增倒计时行 `剩 {{ (c.deadlineIn/3600000)|round(ceil) }} 小时 · 还差 Y 人`（closed/filled 不显示）；`c.likeMind` 时显示「有和你口味相近的玩家在车上」。
- 空态 CTA 既有（去挑个本子）保留。
- 变量：`q/players/time/diff`、`c.deadlineIn/c.closed/c.filled/c.likeMind/c.need`。

### templates/car_detail.html
- 顶部 tag 行：状态改为 closed/filled/need；新增倒计时行；右侧加「分享这车」按钮 `#car-share-btn`（文案 `甜薯剧本杀｜《title》day time 还差 need 人，一起？`）。
- 成员列表加头像 `.car-mem-av` 与 `m.tags` chips；空成员态补提示。
- 新增车主/店员操作块 `{% if (is_owner or my_admin) and not car.closed and not car.filled %}`：POST `user.car_act action=close/fill`。
- 页尾加 Web Share→clipboard + `.share-toast` 脚本。
- 变量：`car.deadlineIn/c.closed/c.filled`、`m.tags/m.avatar`、`is_owner/my_admin`。

### templates/home.html
- 剧友圈后新增「这周在玩什么」聚合区：`{% if hotScripts or newScripts %}`，两栏 01/热玩本、02/新本首车，复用 `.pcard3` 结构，rv 揭示。
- 变量：`hotScripts`、`newScripts`。

### templates/me.html
- 资料表单加**风格标签多选胶囊**：`name="tags"`，循环 `PLAYER_TAGS`（缺省回退 菠萝头/水龙头/推理机/戏精/全类型），回显 `myTags or me.profile.tags`。
- 券/心愿单侧改写为**三组收藏**：want 想玩 / done 已玩 / avoid 避雷，渲染 `favGroups[g]` 剧本对象，每项「取消」按钮 POST `public.fav(sid)` + hidden `group`。
- 资料页加**联系店里块**：`serviceWechat` 复制按钮 `#svc-copy-btn`、「常见问题」`{{ faqUrl or '/faq' }}`、「给店家留言」`?tab=notices`；复制脚本 + toast。
- 变量：`myTags`、`PLAYER_TAGS`、`favGroups`、`serviceWechat`、`faqUrl`。

### templates/comm.html
- 页头下加 **GET 筛选条 `.filterbar3`**：type(全部/普通动态 chat/缺位招募 recruit)、topic(情感/硬核/恐怖/欢乐)，回显 `ftype/ftopic`。
- 发帖表单加话题 radio 胶囊 `name=topic` + 「缺位招募」开关 `#recruit-toggle`，勾选展开 `#recruit-fields`（recruitNeed/recruitRole/recruitScript），JS 显隐。
- 帖子卡 badge：`{% if p.postType=='recruit' %}` 显示「缺 X 人 · topic · recruitRole」。
- 变量：`ftype/ftopic`、`p.postType/p.recruitNeed/p.recruitRole/p.topic`。

### templates/faq.html（新建）
- 独立整页 extends base；顶部「← 回首页」；竖排 kicker `.faq-rail`；六条 FAQ（§5.4 原文）编号 `.faq-item__no` + rv 揭示；底部客服微信复制 + 留言入口（登录态判断）。

### templates/admin/index.html
- `NAVI` 末尾追加 `('talktips','话术库')/('invoices','开票')/('visits','访问统计')`；`NAVI_GROUPS`：内容组加 talktips、系统组加 invoices/visits。`NAVI_NO`/`ADM_NAME_MAP` 由 Jinja 循环自动含新 key（已核验）。

### templates/admin/panel_scripts.html
- script_save 表单「可选」details 内追加：`videoUrl` 输入、`reviewDoc` textarea、每个角色一行 `name="role_line_{{ loop.index0 }}"`（value 回显 `r.line`）。

### templates/admin/panel_bookings.html
- 顶部加「车主车队」块 `{% if cars is defined and cars %}`：列 剧本/时间/车主/人数/截止倒计时/状态 + 「提前截止」POST `/admin/bookings/<cid>/car-close`、「标记补满」POST `/admin/bookings/<cid>/car-fill`。
- 变量：`cars[]`（V2 提供，字段 deadlineIn/closed/filled/need/joined/cap）。

### templates/admin/panel_talktips.html（新建，admin/dm 共用）
- 分类胶囊 GET 过滤 `?cat=`；列表（title/text/author/at + 删除 POST `admin.talktip_del(tid)`）；新增表单 POST `admin.talktips`（cat/title/text）。

### templates/admin/panel_invoices.html（新建）
- status 过滤 pill（pending/done/全部）；列表（订单号/剧本/金额/抬头/税号/邮箱/状态/时间）；「标记已开」POST `/admin/invoices/<iid>/done`。
- 变量：`rows`、`status`。

### templates/admin/panel_visits.html（新建）
- 今日 PV/UV 大字 `.stats`；近 7 日趋势表；热门 top10 `.visit-bar` 宽度百分比条形。
- 变量：`stats.today.pv/uv`、`stats.trend[]`、`stats.top[{path,n}]`。

### templates/admin/panel_dash.html
- 「拼车与首页」段加：`carRewardThreshold`/`carRewardValue`/`carDeadlineHours` 输入；新增「外部触达（占位·未接入）」段：wechatSub/smsGateway 只读 disabled 说明行（§5.5 中文）。

### templates/dm/shell.html
- `NAVI` 追加 `('talktips','话术库')`，使 DM 抽屉/侧栏出现话术库（V2 在 dm._TAB_FUNCS 注册 talktips 渲染同一模板后即生效）。

### static/sw.js
- CACHE 升 `tianshu-shell-v4`；fetch 加导航分支：`req.mode=='navigate'` 或 Accept 含 `text/html` → 网络优先、失败回退 cache（再回退 `/`）；`/static` 维持网络优先回退。

### static/manifest.webmanifest
- 核验：name/short_name/start_url/scope/display/theme_color/background_color/icons 均已齐全，图标资源名沿用，无需改动。

## 二、需要 C 代理补充的 CSS 类名清单
（模板只加类名/结构，具体动效由 C 在 design3.css / mobile-zine.css 提供）

| 类名 | 预期效果 |
|------|---------|
| `.filterbar3` | 筛选条：横排 input/select + 按钮，发丝线底/留白，wrap 自适应 |
| `.share-toast` | 固定底部 pill 提示；`.show` 时淡入上移，1.8s 后自动隐；0.2s 渐隐 |
| `.role3__no` | 角色卡竖排小编号（朱红 mono），叠在海报角 |
| `.role3__line` | 角色一句话人设，小号墨灰 |
| `.ccard3__count` / `.ccard3__like` | 车队卡倒计时（朱红 mono）/ 口味相近提示（朱红小字） |
| `.car-mem-av` | 车队成员圆形头像位（与 `.avatar` 同款） |
| `.faq-layout` / `.faq-rail` / `.faq-rail__t` / `.faq-list` / `.faq-item` / `.faq-item__no` / `.faq-item__q` / `.faq-item__a` | FAQ 页：左竖排 kicker + 右侧编号问答流，细线分区 |
| `.visit-bar` / `.visit-bar__no` / `.visit-bar__path` / `.visit-bar__track` / `.visit-bar__n` | 访问统计 top10：编号+路径+百分比条（`<i>` 宽度）+次数 |
| `.rv--rise`（C 已规划） | 新区块轻量 fade+rise 0.4s，reduced-motion 关 |
| `.sheet3` 弹层化 | 复盘 details 内容区按 token `--d-pop` 质感（如后续要弹层） |

动效 token（C 提供，模板已预留类名钩子）：`--d-pop`/`--d-pop-out`/`--d-tap`；按钮 `:active{translateY(1px)/scale(.98)}`；新动画均需 `prefers-reduced-motion` 降级。模板内**未**硬编码时长，只挂类名。

## 三、模板变量使用清单（供 V1/V2 对齐）
- V1：`canSeeReview`、`sc.videoUrl/sc.reviewDoc/sc.roles[].line`、`car.html: q/players/time/diff`、`car_detail: car.deadlineIn/closed/filled + members[].tags`、`home: hotScripts/newScripts`、`me: myTags/PLAYER_TAGS/favGroups/serviceWechat/faqUrl`、`comm: ftype/ftopic + p.postType/recruitNeed/recruitRole/topic`、`/faq` GET 路由、`POST /api/track`、`POST /car/<cid>/close|fill`（user.car_act）。
- V2：`bookings 面板 cars[]`、`POST /admin/bookings/<cid>/car-close|car-fill`、`talktips 面板 rows[]+cat + admin.talktips/admin.talktip_del`、`invoices rows+status + POST /admin/invoices/<iid>/done`、`visits stats{today,trend,top}`、`settings: carRewardThreshold/carRewardValue/carDeadlineHours + wechatSub/smsGateway 只读`、dm._TAB_FUNCS 注册 talktips。

## 四、自检结果
- Jinja2 解析：全部 ~60 个模板 `env.parse`/`get_template` **零语法错误**。
- 面板渲染：admin panel_scripts/bookings/dash/talktips/invoices/visits、dm 各面板在 stub base + stub 全局下渲染通过；唯一残留 `dm/panel_growth.html` 因 stub 缺嵌套运行数据（int/str 比较）报错，属我未拥有的既有面板、与本轮改动无关。
- sw.js：人工核对花括号与分支（node --check 不可用于 SW 全局），CACHE 已升 v4。
- 冻结块：本轮 CSS 改动为 0，未碰 design3.css/mobile-zine.css/v1/。
- 备份：改动文件均已镜像到 `_backup/`。

## 五、未做项与原因
- manifest：已齐全，未改。
- 弹层 0.24s 滑入具体 CSS：按分工由 C 提供，模板只挂类名。
- dm/panel_growth 渲染报错：既有面板数据结构复杂，非本轮范围，stub 限制。
