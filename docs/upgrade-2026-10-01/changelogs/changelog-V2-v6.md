# changelog-V2-v6 · 视图层（admin.py / dm.py / mobile_site.py）落地记录

> 代理代号 V2。只改这三个视图文件；business.py/config.py/db.py（D）、public.py/user.py（V1）、模板（T1）、mobile SPA（T2）、CSS/JS 均未碰。
> 改前备份：`_backup/tianshu/views/` 三个同名文件上一轮已存在，按「已有备份不覆盖」规则未重写。
> 面板懒加载契约（?partial=1&tab=）保持不变：新面板只要进 `_TAB_FUNCS` 即被 tabs.js 接管，无额外 JS 改动。

## 自检结果
- `python -m py_compile tianshu/views/admin.py tianshu/views/dm.py tianshu/views/mobile_site.py`：**零错误**（PY_COMPILE_OK）。
- flask stub 法（sys.modules 注入 flask/config/business/db/security 桩）真实 import 三模块，核对蓝图与路由注册：**IMPORT_OK**，新路由全部出现、`_TAB_FUNCS` 含新 key。
- 本环境无 flask，未做全栈启动；以 py_compile + stub 导入路由核对 + 字段逐一对齐 spec §3.2 为准（如实说明）。

## 一、admin.py

### 新增面板函数（注册进 `_TAB_FUNCS`）
1. `talktips_panel()`：`business.talktips(cat)` 列表 + 分类筛选，render `admin/panel_talktips.html`（变量 rows/cat/cats）。**未加 staff_required 装饰器**——它同时被 DM 端复用，权限由入口 dashboard(@staff_required) / dm.index(@dm_required) 闸门承担。
2. `invoices_panel()`：`business.invoices_list(status)`（pending/done 过滤），render `admin/panel_invoices.html`（rows/status）。
3. `visits_panel()`：`business.visit_stats()`，render `admin/panel_visits.html`（st）。
4. `_TAB_FUNCS` 追加 `'talktips'/'invoices'/'visits'` 三个 key（其余 15 个不变）。

### 新增 POST 路由
- `POST /admin/talktips/add`（@dm_required）→ `business.talktip_add(current_user, cat, title, text)`，flash 后回 referer。用 dm_required 而非 staff_required：DM 也要维护话术库，business 内二次判权 dm/admin。
- `POST /admin/talktips/<int:tid>/del`（@dm_required）→ `business.talktip_del(current_user, tid)`。
- `POST /admin/invoices/<int:iid>/done`（@staff_required，仅 admin）→ `business.invoice_mark_done(iid, username)`。
- `POST /admin/bookings/<int:cid>/car-close`（@staff_required）→ 构造 `u=dict(current_user(), _staff=True)`，`business.car_action(u, cid, 'close', request.form)`。
- `POST /admin/bookings/<int:cid>/car-fill`（@staff_required）→ 同上 action='fill'。

### 表单处理扩展
- `settings()`：循环接收 `carDeadlineHours/carRewardThreshold/carRewardValue`（`int(float(...))`，非法回退 24/5/10）；`wechatSub/smsGateway` **不接收不写**（§5.5 外部依赖占位，只读）。
- `script_save(sid)`：
  - 新增接收 `reviewDoc`（clean 5000）；
  - `videoUrl`（clean 200，非 http(s) 开头置空）；
  - 遍历表单键 `role_line_<index>`，按 roles 列表下标更新 `roles[i]['line']`（clean 60）。

## 二、dm.py
- 新增 `talktips_panel()`（@dm_required）：render **同一模板** `admin/panel_talktips.html`（变量 rows/cat/cats 与 admin 端一致）。
- `_TAB_FUNCS` 追加 `'talktips'`（其余 today/msgs/credit/sched/growth/guides 不变）。增删提交仍走 `/admin/talktips/*`（dm_required 闸门，DM 可达）。

## 三、mobile_site.py（新 API 与字段）

### 新端点
| 方法 | 路径 | 行为 | 关键字段 |
|---|---|---|---|
| GET | `/m/api/faq` | 静态六条（§5.4 逐字一致） | `{items:[{q,a}]}` |
| POST | `/m/api/track` | JSON `{path}` → `business.track_visit(remote_addr, path)` | `{ok:true}` |
| GET | `/m/api/posts` | `community_posts(30, me_phone, ftype, ftopic)`，?type=&topic= | 见下 |
| POST | `/m/api/post` | 登录；content/text clean 1000；topic 白名单；postType=recruit 时写 recruitNeed/recruitRole/recruitScript | `{ok:true}` |
| GET | `/m/api/scripts/<sid>` | sc 全字段 + canSeeReview(dm/admin) + rating/rating_n(byScript) + roles(对象含 name/line/img) | |
| POST | `/m/api/fav/<sid>` | form.group(want/done/avoid，默认 want) + form.on(1/0，缺省=加入) → `business.fav_set` | `{ok,msg,on,group}` |
| POST | `/m/api/invoice/apply` | oid/company/taxId/email → `business.invoice_apply(u, oid, form)` | `{ok,msg}` |

### 既有端点扩展
- `api_me`：调用 `business.reminder_scan(u)`；新增输出 `favGroups`（want/done/avoid 三组剧本对象列表 id/title/emoji/img/diff）、`myTags`(profile.tags)、顶层 `serviceWechat`、`canSeeReview`；profile 内追加 `tags`；原 `shop.serviceWechat`/`favs`/`notices` 等全部保留。
- `api_profile_save`：接收 `tags`（getlist 多选 或 逗号/顿号串）→ `business.set_player_tags(hit, tags)`。
- `api_cars`：支持 `?q=&players=&time=&diff=`（对 scriptTitle=title / min / time / scriptDiff 过滤）；每车透传 `deadline/deadlineIn/closed/filled/scriptDiff/scriptPlayers/likeMind/likeCount`，members 改为对象数组含 `{nick, tags}`；补 `day/startTime/min/need`。
- `api_car_detail`：从 `business.car_pool(me_phone)` 取同 id 车的扩展字段透传（deadline/deadlineIn/closed/filled/scriptDiff/scriptPlayers/likeMind/likeCount/need/joined/cap），members 改对象含 tags。

## 四、与 T2（changelog-T2-v6.md）字段对齐结果
- T2 表格要求的路径 **全部就位**：track/faq/posts/post/scripts\<sid\>/fav group/invoice apply/profile tags/cars 筛选/car detail 新字段/me 新字段。
- 字段名核对：
  - `/m/api/posts` 返回每条含 `nick/name/avatar/text/content/ago/at/topic/postType/recruitNeed/recruitRole/recruitScript/likeCount/liked`（T2 列的 nick/name/avatar/content/text/ago/at/topic/postType/recruitNeed/recruitRole 全覆盖，另补 recruitScript）。
  - `/m/api/scripts/<sid>` 返回 roles 为对象数组（T2 要 roles[{name,line,img}]）、videoUrl、reviewDoc、canSeeReview、rating/rating_n（sc 全字段透传）。
  - `/m/api/me` 返回 favGroups{want,done,avoid} 为对象列表、myTags[]、顶层 serviceWechat、canSeeReview（T2 四项全中）。
  - `/m/api/fav/<sid>` 接收 group+on（T2 发送方式一致）。
  - `/m/api/cars` 含 deadlineIn/closed/filled/likeMind/likeCount/members[].tags/need（T2 全中）。

## 五、未做项与原因
- **手机端 DM 工作台**：spec §3.2 明确本轮不做，保持。
- **模板（admin/panel_talktips.html、panel_invoices.html、panel_visits.html）**：属 T1 并行产物，本轮只按 spec §4.1 文件名 render；模板缺失的集成阶段由组织者统一补，未自行建模板。
- **wechatSub/smsGateway 真实发送**：§5.5 外部依赖占位，settings 只读不写。
- **全栈启动/截图验证**：环境无 flask，以 py_compile + stub 导入 + 字段对齐为准。
- **car-close/fill 的 UI 按钮**：面板模板内按钮属 T1（panel_bookings.html），本轮只保证后端路由与 flash 回跳就位。
