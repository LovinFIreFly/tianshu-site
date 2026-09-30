# changelog-T2-v6 · 手机 SPA 功能落地（代号 T2）

> 范围：仅改 `mobile/index.html`、`mobile/app.js`、`mobile/styles.css`（未碰 tianshu/、v1/）。
> 备份：`_backup/mobile/` 原有同名文件已存在，按规范「已有备份不覆盖」未重写。
> 后端 API 路径按 design-spec-v6 §3.2 冻结；字段缺失时前端空值兜底显示「待上线/待配置」，不造假数据。

## 一、styles.css（动效 token + 新组件）

1. `:root` 新增动效 token：`--d-pop:cubic-bezier(.16,1,.3,1)`、`--d-pop-out:cubic-bezier(.4,0,1,1)`、`--d-tap:.24s`，并加 `--dur-pop:240ms`、`--dur-mask:200ms`。→ 对应规范 §0「豆包动效质感」，微交互统一引用 token。
2. `.mask`/`.sheet` 动效重写：入场 0.24s `--d-pop` 上滑 28px、遮罩 0.2s 渐隐；退出走 `--d-pop-out`。所有新弹层（FAQ/客服/发帖/发票/角色卡/分享）复用同一 `.sheet/.mask`，天然统一。
3. `:active` 微反馈：补 `.chip/.dchip/.mitem/.tab/.coupon-opt/.copy-btn/.trow/.srow/.cmsg-input button` 的 `transform:scale(.98)`（已有 transition 的只补 active）。
4. 新组件样式：`.skeleton`（pulse 1.4s）、`.hscroll` 横滑（`.hcard` 热/新 badge）、`.carfilter` 筛选条、`.cdline`/`.cstatus-closed`/`.cstatus-filled`/`.likemind`/`.member-tags` 车队卡、`.favtabs`/`.favtab`/`.favrow-remove` 收藏三组、`.tagedit` 标签胶囊、`.comm-entry`/`.post-badge`/`.post-recruit-box` 社区、`.rolecard` 角色卡、`.faq-item`/`.faq-q` FAQ。
5. reduced-motion 覆盖：把 `.skeleton` 与新增过渡项一并纳入 `@media (prefers-reduced-motion: reduce)`。

## 二、index.html（结构）

1. 首页「大厅」在今日排期后插入两段横滑：`#home-hot`（热玩本 01·A）、`#home-new`（新本首车 01·B）。
2. 拼车页在 `#carpool-body` 前插入 `.carfilter`：剧本名输入 `#cf-q` + 人数 `#cf-players`/时段 `#cf-time`/难度 `#cf-diff` 下拉 + 「重置」(data-action=clear-cars)。
3. 我的页：
   - 账号菜单新增「常见问题」(open-faq)、「客服」(open-service) 两项 mitem。
   - 收藏区块 `#favs-sec` 内插入 `.favtabs`（想玩/已玩/避雷，data-favgroup）。
   - 新增社区区块 `#comm-sec`：`#comm-recent`（最近帖列表）+ 「去发帖」(open-post) 按钮。

## 三、app.js（逻辑与 API 接线）

1. **主题三态**：`applyTheme/initTheme` 重写，localStorage key 改为 `'theme'`（light|dark|auto）。auto 时移除 `data-theme` 走 CSS media query；`matchMedia('(prefers-color-scheme: dark)')` 监听实时切换；meta-theme 跟随；按钮按 日/夜/跟 循环（light→dark→auto）。
2. **埋点**：启动后 `setTimeout(sendTrack,1500)`，`navigator.sendBeacon('/m/api/track', Blob JSON {path})`，失败回退 keepalive fetch，不阻塞。
3. **热玩/新本**：`renderHomeHots()` 用 `/m/api/scripts` 全量前端按 hot/rating/id 排序各取 top 6，渲染 `.hcard`（热/新 badge）。
4. **拼车筛选**：`loadCars()` 组 query string（q/players/time/diff）请求 `/m/api/cars`，输入防抖 350ms；`renderCarpool()` 加 `carStatusLine()`（deadlineIn→「剩 X 小时·还差 Y 人」，closed→已截止，filled→补满发车，full→已满员）、likeMind 提示条、成员 tags、卡片「分享」按钮。
5. **车队分享**：`doShareCar()`，文案『甜薯剧本杀｜《本》day time 还差 need 人，一起？』+ `location.origin + /m/car/<id>`，`navigator.share` 降级 `copyText`。
6. **收藏三组**：`favGroups()/favGroupOf()/favGroupScripts()/setFavGroup()`。剧本 sheet 内 想玩/已玩/避雷/移出 四态按钮 → POST `/m/api/fav/<sid>` 带 `group`+`on`；我的页 `.favtabs` 切换 `favTab` 重渲染，每行「移出」→ on=0。兼容旧 `me.favs`（=want）。
7. **剧本详情扩展**：`fetchScriptDetail()` GET `/m/api/scripts/<sid>` 追加 角色卡（roles.name+line+img）、演绎视频外链按钮（videoUrl）、演后复盘（canSeeReview && reviewDoc，`<details>`）；加「分享这本」(share-script)。
8. **风格标签**：资料 sheet 加 PLAYER_TAGS 胶囊（`pfTags`，最多 3），提交时多选 append `tags` → POST `/m/api/profile`。
9. **FAQ**：`openFaqSheet()` GET `/m/api/faq`（items），失败兜底 spec §5.4 六条静态文案；附客服微信 `serviceWechat` 复制。`openServiceSheet()` 独立客服入口。
10. **社区**：`loadCommRecent()` GET `/m/api/posts` 渲染最近 3 帖（recruit badge：缺 X 人/话题/位）；`openPostSheet()` 话题胶囊 + 「缺位招募」开关展开 缺几人/缺什么位/哪本，POST `/m/api/post`。
11. **发票**：paid 订单卡片加「申请发票」→ `openInvoiceSheet(oid)`（抬头/税号/邮箱），POST `/m/api/invoice/apply`。

## 四、用到的 API 与字段（路径严格 §3.2）

| 方法 | 路径 | 字段 |
|---|---|---|
| POST | /m/api/track | body JSON {path: location.pathname+hash} |
| GET | /m/api/faq | {items:[{q,a}]} |
| GET | /m/api/posts | (?type=&topic=) → [{nick,name,avatar,content,text,ago,at,topic,postType,recruitNeed,recruitRole}] |
| POST | /m/api/post | topic, postType=recruit, recruitNeed, recruitRole, recruitScript, content |
| GET | /m/api/scripts/<sid> | 全字段 + roles[{name,line,img}], videoUrl, reviewDoc, canSeeReview, rating/rating_n |
| POST | /m/api/fav/<sid> | group(want/done/avoid), on(1/0) |
| POST | /m/api/invoice/apply | oid, company, taxId, email |
| GET | /m/api/cars | ?q=&players=&time=&diff=；车含 deadlineIn/closed/filled/likeMind/likeCount/members[].tags/need |
| GET | /m/api/me | 新字段 favGroups{want,done,avoid}, myTags[], serviceWechat, canSeeReview |
| POST | /m/api/profile | nick, age, gender, tags[]（多选） |

## 五、自检

- `node --check mobile/app.js` → 零错误（NODE_CHECK_OK）。
- 验证目录 `_verify/mobile-v6/`：复制 index/app/styles/data + 海报，`/m/` 资源与海报路径改相对。shot.py 390×844 截图：
  - 首页 `_shots/index_mobile.jpg`：热玩/新本横滑正常，海报加载，fullpage 宽 390（无横向溢出）。
  - 拼车 `_shots/view-carpool_mobile.jpg`：筛选条 + 空态 CTA 正常，宽 390。
  - 我的 `_shots/view-me_mobile.jpg`：社区入口 + 账号菜单（常见问题/客服）正常，宽 390。
- console 错误仅为 file:// 下 `/m/api/*` fetch 被拒（预期，生产由 Flask 提供；前端 catch 已兜底渲染）。

## 六、未做项与原因

- **PLAYER_TAGS 数量**：任务描述写「六项胶囊」，但冻结契约 §2.1 `config.PLAYER_TAGS` 为 5 项（菠萝头/水龙头/推理机/戏精/全类型）。为避免提交后端拒收的第 6 项，前端按冻结 5 项渲染；若 D 代理最终定为 6 项，只需改 app.js 顶部 `PLAYER_TAGS` 数组。
- **手机端 DM 工作台**：规范 §3.2 明确本轮不做，保持。
- **/m/api/posts 列表页**：本轮只在「我的页」放最近 3 帖入口 + 发帖 sheet，未做独立社区 tab 与完整筛选（type/topic 下拉），因底部 5 tab 已定；GET 参数 type/topic 已就绪，后续可扩。
- **发票状态回显**：申请后仅 toast，未拉取发票状态列表（属 admin 侧 invoices 面板职责）。
