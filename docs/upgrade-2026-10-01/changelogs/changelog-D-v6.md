# changelog-D-v6 · 数据层（business.py / config.py）落地记录

> 代理代号 D。只改 `tianshu/business.py`、`config.py`（db.py 未动）。模板/视图/CSS/JS/data//v1/上轮冻结块均未碰。
> 改前备份：`_backup/config.py`、`_backup/tianshu/business.py` 上一轮已存在，本轮按「已存在不覆盖」规则未重写。

## 自检结果
- `python -m py_compile config.py tianshu/business.py`：**零错误**。
- 本环境无 flask，无法全栈启动；按任务约定用 `sys.modules` 注入 flask stub 后真实 `import tianshu.business`，逐一核对了全部新函数/改签名的 `inspect.signature` 与 spec §2 一致。
- 额外跑了临时功能冒烟（用 TS_DATA_DIR 指到 temp 干净目录，已删脚本）：
  - visits dict 结构、PV/UV、top10 正确；
  - favs 旧 sids→want 迁移写回、want 移除同步 sids、done 分组正确；
  - talktips 仅 dm/admin 可加、普通用户被拒；
  - notify 同 key 未读只发一条（请求缓冲+落库两层查重生效）。

## 逐处改动（改了什么 / 为什么 / spec 编号）

### config.py
1. 新增 `PLAYER_TAGS = ['菠萝头','水龙头','推理机','戏精','全类型']`（在 TAG_PRESETS 下）——2.1。
2. `SETTINGS_DEFAULT` 新增 5 项：`carDeadlineHours=24`、`carRewardThreshold=5`、`carRewardValue=10`、`wechatSub=False`、`smsGateway=''`——2.2（后两项为外部依赖占位，后台只读，见 §5.5）。

### business.py
0. 顶部 `import hashlib`（2.8 ipHash 用）；config import 增 `PLAYER_TAGS`。

**2.1 玩家风格标签**
- `public_profile(u)` 返回追加 `'tags'`（读 profile.tags）。
- 新增 `set_player_tags(user, tags) -> (ok,msg)`：支持列表或逗号/顿号串，clean 去重、只留 PLAYER_TAGS 内值、限 3 个，写回 users.json 的 profile.tags。

**2.2 车队扩展**
- `_car_pool_base()`：新建 `sid→scripts` 映射 `scripts`；每车输出追加 `deadline / deadlineIn(=max(0,deadline-now)) / closed / filled / scriptDiff(sc.diff or 0) / scriptPlayers(sc.players 串)`；members[] 每成员追加 `tags`（来自 profile.tags）。这些字段均在缓存函数内算，沿用 15s TTL。
- `car_pool(me_phone='')`：按 me_phone 现算（不缓存）`likeCount`（排除自己后，成员 tags ∩ 我的 tags 人数）、`likeMind(=likeCount>0)`。
- `create_booking()`：新开车主车（carNew）时写入 `carDeadline`（=now+carDeadlineHours*3600e3；表单给 carDeadlineHours 则用表单值）、`carClosed=False`、`carFilled=False`。
- `car_action()` 新增三个 action（权限=车主本人 或 `user.get('_staff')`）：
  - `close`：carClosed=True，通知全体成员「这车提前截止了」；wants 里该 carId 的 waiting 行置 `status:'closed'` 并逐个 notify。
  - `fill`：carFilled=True，通知成员「已标记补满，准备发车」。
  - `deadline`：form.deadlineHours（1–168 int）重算 carDeadline。

**2.3 车主奖励**
- 新增 `_maybe_car_reward(phone)`：user.carCount+1；达 `carCount % carRewardThreshold == 0` 时发券（180 天有效，note='车主奖励'）+ notify「开满 N 车送券」。
- `verify_checkin()`：核销的是车主车（hit.carNew）时调用 `_maybe_car_reward(hit.phone)`。
- 备注：券同时写 `amount` 与 `value`——既有核销逻辑（order_action claim-bal）读 `amount`，spec 契约字段为 `value`，双写保证券可被正常抵扣。

**2.4 帖子扩展过滤**
- `community_posts(limit=60, me_phone='', ftype='', ftopic='')`：尾部加两个默认空参数（''=不过滤），先按 at 倒序，再按 postType / topic 过滤，最后截断。帖子新增字段 topic/postType/recruitNeed/recruitRole/recruitScript 由视图层写入，business 不改动写入路径（视图契约 §3.1）。

**2.5 话术库**
- 新增 `TALKTIP_CATS=('开场白','过渡','结尾','其他')`。
- `talktips(cat='') -> list`（按 at 倒序，可按 cat 过滤）；数据文件 talktips.json，`talktip_add`/`talktip_del` 落库 cap 300。
- `talktip_add(user, cat, title, text)`：仅 dm/admin；cat 限四类；title/text clean 限长。
- `talktip_del(user, tip_id)`：作者本人或 admin。
- scripts 的 reviewDoc/videoUrl/roles[].line 为字段透传，无需 business 代码（§2.5）。

**2.6 通知与触达**
- `notify(phone, title, text, kind='system', key=None)`：尾部加 key；同 key 已有**未读**通知（含本次请求缓冲 g._notify_buf 内、及已落库 notices）则跳过；row 存 key 字段。向后兼容（默认 None）。
- 新增 `reminder_scan(user)`：扫该用户 status=='booked' 且 ts>now 的预约，0–1h→key='open-<bid>-h1' kind='remind'；23–25h→key='open-<bid>-d1'。
- `my_notices(user, limit=30)`：开头先 `reminder_scan(user)`。
- `verify_checkin()` 末尾追加 notify「写个短评吧」kind='review' key='review-<bid>'。
- **退款核验（#150）结论**：order_action 的 refund 分支原本就有一条 kind='pay' 通知，无需补「缺失通知」；本轮仅把免费退定金文案由「退款已处理/退给你了」明确为「退款已发起，1-3 工作日到账」，对齐 spec「退款已发起/已到账」口径。临期取消分支文案保持「已取消，超时定金不退」。

**2.7 发票**
- 新增 `invoice_apply(user, oid, form) -> (ok,msg)`：订单须 paid 且属本人；同 oid 已申请则拒；写 company/taxId/email（clean 限长）；amount 取订单 amount。
- `invoices_list(status='')`：按 at 倒序，可按 pending/done 过滤。
- `invoice_mark_done(iid, by)`：置 status='done'/doneAt/by，并 notify 申请人。数据 invoices.json rows cap 300。

**2.8 埋点**
- 新增 `_ip_hash(ip)=sha256`（只存摘要不存原始 IP）。
- `track_visit(ip, path)`：visits.json 为 **dict**（用 db.read 非 rows），结构 `{'days':{day:{ipHash:{path:n}}},'updated':ms}`。
- `visit_stats(days=7)`：返回 `{'today':{pv,uv},'trend':[{day,pv,uv}...],'top':[{path,n}...top10]}`。

**2.9 收藏分组**
- favs.json rec 追加 `groups={'want':[],'done':[],'avoid':[]}`；旧 `sids` 保留兼容（=want）。
- `fav_groups(user) -> dict`：无 groups 时把旧 sids 迁入 want 并写回一次。
- `fav_set(user, sid, group, on)`：group∈want|done|avoid；改动 want 时同步写回 sids（=want），保证旧 my_fav_ids 不回退。

## 未做项与原因
- scripts 字段透传（reviewDoc/videoUrl/roles[].line）：纯数据透传，business 无需代码，由 V2 视图 script_save 写入、T1 模板渲染——非 D 范围。
- 微信订阅 / 短信真实发送：spec §5.5 明确为外部依赖占位，本轮不接入，settings 只读展示——非 D 范围。
- 未做全栈启动验证：环境无 flask，以 py_compile + stub 导入签名核对 + temp 目录功能冒烟为准（已如实记录）。
- db.py 未动（任务约定「不必要不动」）；wants 结构沿用现有 rows，close 分支仅改其 status 字段。
