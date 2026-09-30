# changelog-V1-v6 · 视图层（public.py + user.py）落地记录

> 代理代号 V1。只改 `tianshu/views/public.py`、`tianshu/views/user.py`。
> business.py / config.py / admin·dm·mobile_site 视图 / 模板 / CSS·JS·mobile 均未碰。
> 改前备份：`_backup/tianshu/views/public.py`、`_backup/tianshu/views/user.py` 上轮已存在，按「已有不覆盖」保留。

## 自检结果
- `python -m py_compile tianshu/views/public.py tianshu/views/user.py`：**零错误**（最终一次复核通过）。
- flask stub 注入 `sys.modules`（Blueprint/request/session 等桩）后真实 `import tianshu.views.public`、`tianshu.views.user`：**两模块均导入成功，全部路由注册无报错**。路由清单见下。
- 与 T1 changelog 第三节「模板变量使用清单」逐一对齐，见本文末「与 T1 模板变量对齐」节。

---

## 一、public.py 逐处改动

### 1. toggle_theme() — 三态循环（§3.1）
- 原：light ↔ dark 二态。
- 改：`light → dark → auto → light` 三态循环，写 cookie `theme`（max_age 1 年）。
- 顶部 import 新增 `make_response`（原函数内局部 import 已移除）。
- 对应 base.html 内联脚本（T1 已建）：cookie=auto 时 matchMedia 驱动 data-theme。

### 2. home() — 追加 hotScripts / newScripts（§3.1 / §4.1）
- `hotScripts`：`business.stats()['hot']` 已是 `[(sid, {plays…})]` 按 plays 降序 top6，视图层把 sid 映射回 scripts 对象列表。
- `newScripts`：onSale 剧本按 id 倒序取 top6。
- 上下文新增两个变量，其余原有变量不变。

### 3. script_detail(sid) — 追加 canSeeReview（§2.5 / §3.1）
- `canSeeReview = bool(u) and (business.has_role(u,'dm') or business.has_role(u,'admin'))`；未登录 False。
- sc 本身是 dict 透传，reviewDoc/videoUrl/roles[].line 自动可用，视图层无需额外处理。

### 4. car() — GET 多维筛选（§3.1 / §4.1 car.html）
- 新增 GET 参数读取：`q`(剧本名模糊，匹配 car.title)、`players`(≥人数，按 car.min 即 carMin)、`time`(时段)、`diff`(1-5，匹配 car.scriptDiff)。
- time 筛选兼容两种入参：`上午/下午/晚上`（按 car.time 的小时数分类：<12 / 12-17 / ≥18）或精确时间串（如 "14:00"）精确匹配。
- 筛选后 cars 列表传入模板；上下文回显 `q/players/time/diff`；原有 `tags/mine` 保留。

### 5. comm() — GET type/topic 筛选（§3.1 / §4.1 comm.html）
- 新增 `type`(all|chat|recruit)、`topic`(情感/硬核/恐怖/欢乐)。
- 映射：type=all/空 → ftype=''（不过滤）；type=recruit → ftype='recruit'（business.community_posts 精确匹配 postType）；type=chat → ftype='' 后视图层排除 postType=='recruit' 的帖（business 层 ftype 只做精确匹配，无 chat 精确值，故视图补排除）。
- ftopic 直接透传 business.community_posts 的 ftopic 参数。
- counts 改用 200 条全量统计（原 60 条截断会导致筛选后 counts 不准）。
- 上下文新增 `ftype/ftopic` 回显；原 `t/counts/posts` 保留。

### 6. post_create() — 接收话题与招募字段（§2.4 / §3.1）
- 新增字段写入 posts：`topic`(clean 限 8)、`postType`('' 或 'recruit')、`recruitNeed`(int 限 1-12)、`recruitRole`(clean 限 16)、`recruitScript`(clean 限 30)。
- 校验：postType=='recruit' 时 recruitNeed 与 recruitRole 至少有其一，否则 flash warn 并 redirect 回 /comm。
- text 为空时提前 return（原逻辑是 fall-through 到 redirect，行为等价但更清晰）。
- 原 `type` 字段保留（默认 'chat'，原默认 'diary' 改为 'chat' 以匹配 comm counts 的 'chat' 键）。

### 7. fav(sid) — 改调 business.fav_set，支持 group（§2.9 / §3.1）
- 接收 `group` 参数（form 或 query）：want|done|avoid，默认 want，非法值回退 want。
- 先 `business.fav_groups(u)` 查当前 sid 是否在该组，决定 on=True/False，再调 `business.fav_set(u, sid, group, on)`。
- flash 文案按组：想玩 / 已玩 / 避雷（「已加入/已移出「X」」）。
- AJAX 分支返回 `{'on': on, 'group': group}`（原只返回 {'on': …}）。
- 不再直接操作 favs db（原手写 sids 逻辑全部移除，交给 business 层）。

### 8. 新路由 GET /faq（§3.1）
- `render_template('faq.html')`，传 `serviceWechat`（settings.serviceWechat）。
- 匿名可访问（无 login_required）。

### 9. 新路由 POST /api/track（§2.8 / §3.1）
- 读 JSON body {path}（或 form path），调 `business.track_visit(request.remote_addr, path)`。
- 返回 `jsonify({'ok': True})`；不记录任何用户信息。
- 匿名可访问。

---

## 二、user.py 逐处改动

### 10. me() — 追加 favGroups/myTags/serviceWechat/faqUrl（§3.1 / §4.1 me.html）
- `favGroups`：`business.fav_groups(u)` 返回三组 sid 列表，视图层映射为剧本对象列表 `[{id,title,emoji,cover,diff}]`（sid 不在 scripts 表的跳过）。
- `myTags`：`(u.profile or {}).get('tags')` 列表。
- `serviceWechat`：`business.get_settings()['serviceWechat']`。
- `faqUrl`：`url_for('public.faq')`。
- 原 `scripts=db.rows('scripts')` 改为复用本地 `scripts_all` 变量（同一对象，不重复读库）。
- notices 已调 `business.my_notices(u, 20)`（D 已在内部调 reminder_scan），无需改。

### 11. profile_save() — 接收 tags（§2.1 / §3.1）
- 在 db.write('users') 之后，若 form 含 `tags` 字段：先 `f.getlist('tags')`（多选 checkbox），为空则按逗号串 split（兼容逗号/顿号）。
- 调 `business.set_player_tags(u, tag_list)`（内部清洗去重限 3 个、只留 PLAYER_TAGS 内值）。
- tags 字段不在 form 中时（旧客户端/其他资料更新）跳过，不影响昵称/性别/年龄/头像保存。

### 12. 新路由 POST /invoice/apply（§2.7 / §3.1）
- `@login_required`；form 收 oid/company/taxId/email，调 `business.invoice_apply(u, oid, request.form)`。
- 成功 flash ok、失败 flash warn；redirect 回 referer 或 user.me。

### 13. notice_center() — 无需改（§3.1）
- 现有代码已调 `business.my_notices(u, 100)`，D 已在 my_notices 开头内置 reminder_scan。视图层零改动。

### 14. car_act / order_act — 无需改（§3.1）
- car_act 已透传 `dict(current_user(), _staff=is_staff())` 给 business.car_action，D 新增 close/fill/deadline action 自动生效。
- order_act 退款核验 D 已完成，视图层零改动。

---

## 三、与 T1 模板变量对齐结果

| T1 模板 | T1 期望变量 | V1 实际传入 | 对齐 |
|---------|------------|------------|------|
| script.html | canSeeReview | `canSeeReview`（bool） | ✅ |
| script.html | sc.reviewDoc / sc.videoUrl / sc.roles[].line | sc dict 透传，字段自动可用 | ✅ |
| car.html | q / players / time / diff（回显） | `q/players/time/diff` | ✅ |
| car.html | c.deadlineIn / closed / filled / likeMind / need | business.car_pool 已输出 | ✅（business 层） |
| home.html | hotScripts / newScripts | `hotScripts`(script obj 列表) / `newScripts`(script obj 列表) | ✅ |
| me.html | myTags | `myTags`（list[str]） | ✅ |
| me.html | PLAYER_TAGS | T1 模板内有缺省回退，视图未传（可选） | ✅ |
| me.html | favGroups[g] 剧本对象 | `favGroups={'want':[...],'done':[...],'avoid':[...]}`，每项 {id,title,emoji,cover,diff} | ✅ |
| me.html | serviceWechat | `serviceWechat`（str） | ✅ |
| me.html | faqUrl | `faqUrl`（url_for public.faq） | ✅ |
| comm.html | ftype / ftopic（回显） | `ftype`（all/chat/recruit）/ `ftopic` | ✅ |
| comm.html | p.postType / recruitNeed / recruitRole / topic | post_create 写入这些字段；community_posts 透传 | ✅ |
| faq.html（新） | GET /faq 路由 + serviceWechat | 路由已建，传 serviceWechat | ✅ |
| base.html | POST /api/track | 路由已建，收 {path} 返回 {ok:True} | ✅ |
| me.html 收藏取消按钮 | POST public.fav(sid) + hidden group | fav() 收 group 参数 | ✅ |

---

## 四、改动路由清单

### public.py
| 方法 | 路径 | 函数 | 本轮变更 |
|------|------|------|---------|
| GET | /theme | toggle_theme | 改三态循环 |
| GET | / | home | 追加 hotScripts/newScripts |
| GET | /scripts/<sid> | script_detail | 追加 canSeeReview |
| GET | /car | car | 追加 q/players/time/diff 筛选 |
| GET | /comm | comm | 追加 type/topic 筛选 + ftype/ftopic |
| POST | /post | post_create | 追加 topic/postType/recruit 字段 |
| POST | /fav/<sid> | fav | 改调 fav_set + group 参数 |
| GET | /faq | faq | **新增** |
| POST | /api/track | api_track | **新增** |

### user.py
| 方法 | 路径 | 函数 | 本轮变更 |
|------|------|------|---------|
| GET | /me | me | 追加 favGroups/myTags/serviceWechat/faqUrl |
| POST | /profile | profile_save | 追加 tags 处理 |
| POST | /invoice/apply | invoice_apply | **新增** |
| GET | /notice | notice_center | 无改动（已调 my_notices） |
| POST | /car/<cid>/<act> | car_act | 无改动 |
| POST | /order/<oid>/<act> | order_act | 无改动 |

---

## 五、未做项与原因
- **模板集成验证**：faq.html 等模板由 T1 并行创建，V1 按 spec 文件名 render，未做端到端渲染验证（集成阶段统一跑 Jinja 解析）。
- **players 筛选口径**：按 car.min（carMin）≥ 入参实现，即「开 4 人本」筛 players=4 能命中。若产品希望按「剩余空位」筛选，集成阶段可调一行。
- **PLAYER_TAGS 未传入模板**：T1 changelog 明确模板内有缺省回退列表，视图层不重复传常量；如需视图注入可后续补。
- **全栈启动验证**：环境无 flask，以 py_compile 零错误 + stub 导入路由注册通过为准（与 D 代理同口径）。
- **business.py / config.py / admin·dm·mobile 视图 / 模板 / CSS·JS**：严格按文件所有权未碰。
