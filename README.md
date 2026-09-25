# 甜薯剧本杀 · 门店管理系统

一个给线下剧本杀店用的小系统：**客人自己约本、拼车、看到店核销码；店里管排期、核销、客户信用分、发券做回访。**

纯 Python 写的（Flask 服务端渲染），**没有前端框架、没有数据库、没有构建步骤** —— 跑起来只需要 Python 和一个 `data/` 文件夹。
数据就是几个 json，用记事本就能看、能改、能备份。

```
python app.py        →  浏览器自动打开 http://localhost:8000
```

## 能干什么

**给客人的**
- 逛剧本库（标签/难度筛选、搜索、收藏「想玩」）
- 看剧本详情、角色列表、DM、玩家评价
- 在线预约：选日期时间、人数、拼车或包车、指定 DM、**提前挑角色**、用优惠券
- 自动算定金、到店核销码、**免费取消时限内可全额退定金**
- 拼车大厅：上别人的车、满员排候补、有人下车自动喊候补的人
- 「我的」页：预约、订单、券、余额、信用分、站内消息

**给店里的**
- 概览：今天几场、几个人、收了多少定金、今天谁要来
- **到店核销**：客人报 6 位码，输一下就行（预约表格里也能直接点核销）
- 预约管理：按状态筛、代客户取消并退款
- 客户档案：来过几次、花了多少、信用分流水、**拉黑/恢复**、会员充值
- 剧本管理：改价、上下架、填角色、**「可提前选角」开关**（开了客人才能在网页上挑角色）
- 发券回访：给「N 天没来」的客人批量发券
- 订单/日结、操作日志（谁动了什么一清二楚）

## 快速开始

```bash
# 1. 装依赖（第一次运行 app.py 会自动装，也可以手动来）
python -m pip install -r requirements.txt

# 2. 启动
python app.py

# 3. 浏览器打开 http://localhost:8000
```

内置账号（首次运行自动创建，密码都是 `123123`）：

| 账号 | 身份 |
|---|---|
| FireFly | 超级管理员 |
| FireFly2 | 管理员 |
| dm测试 | DM |
| 调试debug | 客户 |

常用参数：

```bash
python app.py --lan           # 让同一个 WiFi 下的手机也能访问（测手机端很方便）
python app.py --port 8081     # 换端口
python app.py --no-browser    # 不自动开浏览器
python app.py --stats         # 看数据统计
python app.py --backup        # 把 data 打包成 zip（改数据前先跑）
```

**把老数据搬过来**（线上那份 json → 本地 `data/`）：

```bash
# 从 GitHub 仓库下载 ZIP 解压后：
python tools/import_cloud.py --dir "C:\Users\你\Downloads\tianshu-data-main"
# 或者设置 Token 直接拉（仓库是私有的）
set GITHUB_TOKEN=ghp_xxx && python tools/import_cloud.py --remote
```

导入前会自动把现有 `data/` 备份成 `data_备份-时间戳/`，导坏了能回滚。账号密码照旧能用（老密码哈希也认）。

**想直接上线给人用**：双击 `启动上线版.bat`（本地起服务 + Cloudflare 隧道，见下面「部署」）。

## 目录结构

```
.
├── app.py                    入口：装依赖、挑端口、起服务（也带 --stats/--backup 小工具）
├── config.py                 配置：端口、经营参数默认值、内置账号
├── requirements.txt
├── tianshu/                  应用包
│   ├── __init__.py           应用工厂 create_app()
│   ├── db.py                 数据层：data/*.json 的读写
│   ├── security.py           密码哈希、登录态、限流、权限装饰器
│   ├── business.py         ★ 业务规则：算价 / 定金 / 退款 / 拼车 / 信用分 / 核销
│   ├── views/                路由（按角色分蓝图）
│   │   ├── public.py         首页、剧本库、详情、拼车大厅
│   │   ├── user.py           登录注册、我的、下单、付款退款
│   │   └── admin.py          后台：核销、预约、客户、剧本、订单、设置、日志
│   ├── templates/            页面模板（Jinja2，一个页面一个文件）
│   └── static/               样式表 + 少量脚本
├── tools/                    给自己的小工具
│   ├── smoke_test.py         自检（48+ 项，改完代码跑一下）
│   ├── import_cloud.py       老数据搬家（把线上那份 json 导进 data/）
│   └── make_bats.py          重新生成启动用的 .bat（必须是 CRLF+GBK，别手写）
├── data/                     运行后生成：账号、预约、订单、上传的图……（已 gitignore）
└── legacy/                   老版本存档（原来的单文件 HTML 前端，留个念想）
```

## 数据放在哪

全部在 `data/` 下，一个东西一个 json：

```
users.json      账号（密码是 PBKDF2 哈希，不是明文）
scripts.json    剧本库
bookings.json   预约（含拼车、核销码、角色）
pays.json       订单（定金/支付/退款）
coupons.json    优惠券
notices.json    站内通知
logs.json       操作日志
secret.key      会话签名密钥（别外传）
img/            上传的图片
```

- **备份**：`python app.py --backup`，会打个 zip 放项目目录
- **改数据**：记事本直接改 json；改前先备份
- **隐私**：`data/` 里有客人手机号，别把整个文件夹发出去（`.gitignore` 已经帮你挡住了）

## 自检

```bash
python app.py --no-browser     # 一个窗口起服务
python tools/smoke_test.py     # 另一个窗口跑自检
```

覆盖：页面能否打开、登录与权限、加剧本、下单算价、定金比例、核销、拼车、退款规则、客户看不到后台。

## 一些设计取舍

- **金额一律服务端算**：表单传过来的只是"意向"。以前吃过亏 —— 有人改前端把 288 的本订成 1 块钱
- **没有数据库**：店的量级（一天几十单）用 json 足够，好处是随时能打开看、能手工修
- **服务端渲染**：翻页会整页刷新，但换来的是"一个页面 = 一个模板文件"，改文案不用碰构建工具
- **本地优先**：先能在店里自己的电脑上稳定跑，线上部署是后面的事

## 路线图

- [x] 客户预约闭环（选本 → 下单 → 定金 → 核销码 → 退款）
- [x] 拼车大厅 + 候补 + 一键上车
- [x] 后台：核销 / 客户信用分 / 拉黑 / 充值 / 发券 / 日结 / 操作日志
- [x] 排期管理（防撞房、周视图、锁场、取消通知）+ 一键约场
- [x] 玩家评价（打分 + 门店回复 + 隐藏）
- [x] 店客留言（可回复、会推送）
- [x] 玩家社区（发帖 / 点赞 / 删帖）
- [x] DM 结算（按比例分成 / 每场固定场费，两种口径可切）
- [x] 图片上传（剧本封面、头像）
- [x] 会员余额抵扣定金（退单退回余额）
- [x] 剧本 CSV 批量导入导出（Excel 改完导回来）
- [x] 老数据搬家脚本 + 备份工具 + 一键上线脚本
- [ ] 手机端 PWA（加到桌面像 App）
- [ ] 评价追评 / 图片评价
- [ ] 多门店（分店数据隔离）

## 部署（让它上线，别人也能访问）

三种办法，从省事到正规：

### 1. Cloudflare 隧道（推荐，免费，不用服务器）

家里/店里那台电脑开着就能对外服务 —— 已经在用 Cloudflare 的话最顺：

```powershell
winget install --id Cloudflare.cloudflared -e     # 装隧道程序（一次就够）
```

然后**双击 `启动上线版.bat`**：它会起本地服务，再挂一条隧道，
窗口里会出现一个 `https://xxxx.trycloudflare.com` 的网址，发给朋友就能用。
（这个临时网址每次重启都变；想固定用自己域名，去 Cloudflare Zero Trust 建一条 Named Tunnel 绑 `lovinfirefly.cn`。）

注意：电脑要一直开着、别睡眠；隧道一开公网就能访问，后台密码别外传。

### 2. Railway / Render（有免费档，24 小时在线）

把仓库连上去，启动命令填 `python app.py --no-browser`，
监听端口读环境变量（现在写死 8000，改 `config.py` 可以从环境变量取）。
免费档会休眠，被访问时唤醒来着就要等几秒。

### 3. 云服务器（最稳，一年几十到几百块）

买台小机器（1核1G 够了），装 Python，`git clone` 下来跑
`nohup python app.py --no-browser &`，前面挂 Nginx + HTTPS。
数据就在 `data/` 里，定时 `python app.py --backup` 再同步走就行。

> 不管哪种：**数据都在 `data/`**，整个文件夹拷走就是完整备份。

## License

MIT，见 [LICENSE](LICENSE)
