# 甜薯剧本杀 · 项目架构与维护手册

> 写给"下次接手的人"（包括三个月后的自己）：照着这份文档能在 10 分钟内找到任何一个功能在哪改。

## 1. 项目概览

- **定位**：一家剧本杀小店的**预约 + 到店核销 + 评价**全流程网站，单机可跑（数据＝JSON 文件），也能搬到云上。
- **技术栈**：Python 3.12 + Flask 3（服务端渲染 Jinja2 模板）+ waitress（生产服务器）。没有前端框架、没有数据库、没有 npm。
- **运行**：`python app.py`（自动开浏览器，默认 8000 端口，被占用自动往后试）
  - `python app.py --lan` 手机同 WiFi 可访问
  - `python app.py --dev` 改模板免重启
  - `python app.py --stats` 看数据量与账号
  - `python app.py --backup` 把 `data/` 打包成 zip（**动手改数据前必跑**）
- **数据**：全部在 `data/*.json`；上传的图在 `data/img/`；会话密钥在 `data/secret.key`。

## 2. 目录职责表

| 路径 | 职责 | 关键文件 |
|---|---|---|
| `app.py` | 启动器：装依赖、选端口、起 waitress、`--stats/--backup` | `app.py:137 main()` |
| `config.py` | 所有可调参数：营业参数、内置账号、标签预设、发信配置 | `config.py:42 SETTINGS_DEFAULT`、`config.py:102 SEED_USERS` |
| `tianshu/__init__.py` | **应用工厂**：装配蓝图、CSRF、主题、设备判定、错误处理 | `tianshu/__init__.py:80 create_app()` |
| `tianshu/db.py` | 数据层：JSON 读（带 mtime 缓存）写（临时文件+原子替换+重试） | `db.py:29 class Store` |
| `tianshu/security.py` | 密码哈希、限流、登录态、权限装饰器、安全跳转 | `security.py:129 login_required`、`security.py:150 staff_required` |
| `tianshu/business.py` | ★ **业务规则**（2194 行，全站最核心）：算价/定金/退款/拼车/信用分/核销/通知 | 见第 4 节 |
| `tianshu/views/` | 路由：`public`(公开) `user`(客户) `dm`(主持人) `admin`(后台) `mobile_site`(`/m` 手机站) | 见第 3 节 |
| `tianshu/templates/` | 二代模板（22 个）+ `admin/`(20) `dm/`(7) `v1/`(19 一代界面) | `base.html` 是所有页面的骨架 |
| `tianshu/static/` | CSS（含 5 套款式 `skin-*.css`）+ JS（`csrf.js`/`tabs.js`/`upload.js`） | |
| `tools/` | 一次性脚本：冒烟测试、手机截图、云端导入等 | `tools/smoke_test.py`(1197 行) |
| `tests/` | pytest 自动化测试（21 项，用临时数据目录） | `tests/test_site.py` |
| `_调试工具/` | 浏览器自动化体检脚本（Playwright） | `_调试工具/README.md` |
| `legacy/` | **存档**：最早的单文件 `index.html` + 云函数版本，仅留档不运行 | |

## 3. 模块依赖方向

```
        app.py（启动）
            │
     create_app()  ←── config.py（配置）
            │
   ┌────────┼─────────┬──────────┐
   ▼        ▼         ▼          ▼
public   user      dm        admin / mobile_site   （路由层）
   └────────┴─────────┴──────────┘
            │  全部调用
            ▼
      business.py（业务规则）
            │
     ┌──────┴───────┐
     ▼              ▼
   db.py         security.py（密码/权限/限流）
（data/*.json）
```

规则：**路由层只做"取参数 → 调 business → 渲染模板"**，金额、人数、状态、权限一律由 `business.py` 在服务端重算，前端传什么都只当参考。

## 4. 关键链路（照着这条线改功能）

### 客人预约下单
`/scripts → /script/<id>`（`views/public.py:170 script_detail`）
→ 表单 POST `/book`（`views/user.py:395 book`）
→ `business.book()/car_book()` 校验人数/场次/拼车 → 写 `bookings.json` + 生成订单 `pays.json`
→ 通知 `business.notify()` → 重定向回预约页。

### 到店核销（你上次问的两步）
1. 后台「预约」面板 → 输 6 位核销码 → `POST /admin/verify`（`views/admin.py:71`）→ `business.verify_checkin()` → 状态 `booked → arrived`
2. 玩完 → 「确认完成」→ 状态 `arrived → done`，并给客人推一条评价邀请（`business.notify`）
3. 客人下次打开站点 → `business.my_notices` / 评价入口 → POST `/review/<bid>` → 写 `reviews.json`

### 评分展示的开关
`config.SETTINGS_DEFAULT['reviewsEnabled']`（后台「门店设置」里改）→ 模板 `script.html` 判断后决定是否渲染评分区。后台「评价」面板可单条隐藏/回复/删除。**评分永远由客人评价算出，后台不能直接改分**（要改只能删评价）。

### 后台面板是怎么拼起来的
`/admin?tab=xxx` 一个网址切 18 个面板（`views/admin.py:1374 _TAB_FUNCS`）：
- 首屏**只渲染当前 tab**，其余是 `<!-- panel:KEY -->` 占位
- 点标签时 `static/js/tabs.js:26 ensureLoaded()` 用 `?partial=1&tab=KEY` 把那一段 HTML 拉回来
- 加新功能三步：① 写面板函数 ② `_TAB_FUNCS` 补一行 ③ `templates/admin/index.html:12 NAVI` 补一行

## 5. 数据流与存储

| 文件 | 内容 |
|---|---|
| `users.json` | 账号（PBKDF2 密码哈希、角色、信用分、资料） |
| `scripts.json` | 剧本库（封面 `img`、人数区间、价格、角色） |
| `bookings.json` | 预约（状态 `booked/arrived/done/cancelled`、拼车、核销码） |
| `pays.json` | 订单（定金/尾款/退款） |
| `sessions.json` | 排期场次；`rooms.json` 房间 |
| `reviews.json` | 评价（星级、文字、匿名、回复、隐藏） |
| `coupons.json` | 优惠券；`notices.json` 站内通知；`logs.json` 操作日志 |
| `talktips.json` `messages.json` `posts.json` `carmsgs.json` | 话术库、留言、社区帖子、车队聊天 |

写入策略：`db.write()` 先写 `.tmp` 再 `os.replace` 原子替换，Windows 上遇"拒绝访问"重试 4 次（`db.py:64`）。读有 mtime 缓存，别在外部手改 JSON 后指望立刻生效（改完重启）。

## 6. 约定与风险清单

**约定**
- 权限判断用 `has_role(u, 'admin')` / `is_staff()`，**不要拿 `role()` 比等号**（一个人可以同时是 DM + 管理员）
- 所有写操作必须带 CSRF 令牌；`csrf.js` 自动注入表单与 fetch，新增表单不用管
- 模板骨架统一 `base.html`（一代界面是 `v1/layout_v1.html`，切换由 `business.ui_ver()` 决定）
- 手机端有独立站 `/m`（`mobile/` 目录 + `views/mobile_site.py`），与桌面站不共用模板

**已知风险 / 注意点**
- `data/` 是唯一数据源，**没有自动备份**，手改前务必 `python app.py --backup`
- 内置账号密码都是 `123123`（`config.py:102`），只适合本机/内网，上线必须改
- 验证码目前只打印在服务窗口（没配发信通道时），生产需配 `mailProvider`
- `tools/smoke_test.py` 有 24 项未通过，大多是**断言文案与实现不一致/UA 差异**导致（如"DM 成长档案"实际叫"DM 档案"、手机底栏需手机 UA），不是功能缺失——要逐条核对再改，别照着报错乱改功能
- 搜索中文内容别用 `findstr`（编码会乱码），用 `_调试工具/grep.py`

## 7. 2026-10 这轮修的问题（防止复发）

| 症状 | 根因 | 修复位置 |
|---|---|---|
| 每页控制台一条 403 | `sendBeacon('/api/track')` 带不了 CSRF 头 | `tianshu/__init__.py` 里 `_CSRF_FREE` 豁免埋点 |
| 进「我的」500 | 收藏对象漏 `price` 字段 | `views/user.py` 补字段 + `me.html` 用 `s.get('price')` |
| 点「看 TA 主页」404 | 历史评价用户名是脏数据 | `script.html`/`car_detail.html` 先判断用户存在 |
| 后台/DM「话术库」500 | `url_for('admin.talktips')` 端点不存在 | `panel_talktips.html` 改 `admin.talktip_add` |
| 登录后可被带到外站 | `next` 参数直接跳转（开放重定向） | `security.py` 新增 `safe_next()` |
| 手机站静态资源目录穿越 | `startswith` 前缀比较可被同前缀兄弟目录绕过 | `views/mobile_site.py` 改绝对路径 + 分隔符比较 |
