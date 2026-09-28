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
- [x] 图片上传（剧本封面、头像、DM 形象照）
- [x] 邀请返利（填邀请码，双方各得一张抵扣券，金额后台可改）
- [x] 定金流程：支付页（加小客服微信）→ 待客服确认 → 管理员确认后才给客人看核销码
- [x] 后台 DM 成长档案（段位 / 擅长本 / 带本情况 / 客人反馈 / 本月分成）
- [ ] 会员余额抵扣定金（后端逻辑都留着，界面已撤 —— 要做的话把 7 处 UI 加回来）
- [x] 剧本 CSV 批量导入导出（Excel 改完导回来）
- [x] 老数据搬家脚本 + 备份工具 + 一键上线脚本
- [ ] 手机端 PWA（加到桌面像 App）
- [ ] 评价追评 / 图片评价
- [ ] 多门店（分店数据隔离）

## 部署（让它上线，别人也能访问）

**先把"现在有哪些东西"说清楚**（2026-09），不然容易改错地方：

| | 在哪 | 是什么 | 能跑新版吗 |
|---|---|---|---|
| 代码（新） | GitHub `LovinFireFly/tianshu-site` → `python-rewrite` 分支 | 现在这套 Python 版（Flask + `data/*.json`） | — |
| 代码（老）+ **现在的线上站** | 同仓库 `main` 分支 → Cloudflare **Pages** 项目 `tianshu-co8` → 域名 `lovinfirefly.cn` | 老的单文件 `index.html` + `functions/`，数据存在 `LovinFireFly/tianshu-data` | ❌ Pages 只能跑静态文件 + JS，跑不了 Python |
| 公网入口（新） | 本机 `cloudflared` 隧道 → 自己的域名 | 这套 Python 版 | ✅ |

所以新版上线有两条路，**别的都别考虑**：

| | 适合谁 | 代价 |
|---|---|---|
| **云服务器（第 3 节）★ 现在用的** | 想 24 小时在线、不用管电脑 | 一年 ¥200–400 |
| **本机隧道（第 1 节）** | 先试水 / 临时给朋友看 | 家里电脑得一直开着 |

老的 Pages 站（`main` 分支）留在那儿当备份；哪天不想留了，去 Cloudflare 把 `tianshu-co8` 项目停掉就行。

> 别把 `python-rewrite` 合并进 `main` —— 那会触发 Pages 用老架构重新部署，两边对不上。

### 1. Cloudflare 隧道（推荐，免费，不用服务器）

**① 临时网址（零配置，先用起来）：**

```powershell
winget install --id Cloudflare.cloudflared -e     # 装隧道程序（一次就够）
```

然后**双击 `启动上线版.bat`** → 起本地服务 + 挂隧道，窗口里出现
`https://xxxx.trycloudflare.com`，发给朋友就能用（这个网址每次重启都会变）。

**② 固定域名（配一次，一劳永逸）** —— 用已有的 `lovinfirefly.cn`：

```powershell
cloudflared tunnel login                                        # 浏览器里授权一次，选 lovinfirefly.cn
cloudflared tunnel create tianshu                               # 建隧道，记住打印的隧道 ID
cloudflared tunnel route dns tianshu tianshu.lovinfirefly.cn    # 自动加一条 CNAME（子域名随你起）
```

再建 `C:\Users\junbo\.cloudflared\config.yml`：

```yaml
tunnel: tianshu
credentials-file: C:\Users\junbo\.cloudflared\<隧道ID>.json
ingress:
  - hostname: tianshu.lovinfirefly.cn
    service: http://localhost:8000
  - service: http_status:404
```

之后**双击 `启动上线版.bat`** 就会自动走固定域名（脚本一看有 config.yml 就切模式，
没有就还是临时网址）。想后台常驻 + 开机自启：`cloudflared service install`（一次就够）。

> · 隧道是从本机连出去的，所以**不用**改 `LAN_MODE`、也不用在路由器开端口；
>   Cloudflare 那边自动给 HTTPS 证书，外面只能通过你的域名进来，比直接暴露端口安全。
> · 数据仍在本地 `data/`；要把老线上（`tianshu-data`）的数据搬过来跑 `python tools/import_cloud.py`。
> · 电脑要一直开着、别睡眠；隧道一开公网就能访问，后台密码别外传。

### 2. Railway / Render（有免费档，24 小时在线）

把仓库连上去，启动命令填 `python app.py --no-browser`，
监听端口读环境变量（现在写死 8000，改 `config.py` 可以从环境变量取）。
免费档会休眠，被访问时唤醒来着就要等几秒。

### 3. 云服务器（最稳，24 小时在线）★ 现在用这套

**为什么选它**：不用管家里电脑开没开、不用改 `LAN_MODE`；香港/新加坡机房**免备案**，
国内访问比 Cloudflare 免费节点稳。一年约 ¥200–400（轻量 2核2G）。

**① 买机器**（阿里云 / 腾讯云的「轻量应用服务器」，5 分钟）
- 地域：**香港**或**新加坡**（免备案）；镜像选 **Ubuntu 22.04 / 24.04**
- 配置：1核1G 也够用（一天几十单），2核2G 更宽松
- **安全组 / 防火墙放行**：`22`（SSH）、`80`、`443` —— **不要**开放 8000
- 记下**公网 IP** 和 root 密码

**② 把本机数据搬上去**（想保留现有的剧本/账号/预约就做这步）

```
图形化最省事：WinSCP 连上服务器，把本机 data 文件夹拖到 /opt/tianshu/
或者命令行（在本机 PowerShell 里跑）：
scp -r "C:\Users\junbo\Desktop\网站\data" root@<公网IP>:/opt/tianshu/
```

**③ 服务器上跑一键脚本**（用阿里云控制台的「远程连接」网页终端也行）

```bash
apt update && apt install -y git
git clone -b python-rewrite https://github.com/LovinFireFly/tianshu-site.git /opt/tianshu
bash /opt/tianshu/deploy/install.sh tianshu.lovinfirefly.cn
```

这个脚本会把该做的都做完：装依赖 → 拉代码 → 建虚拟环境 → 装 **Caddy**（自动 HTTPS、自动续期）
→ 写 systemd（崩溃自启、开机自启）→ 加每天 4:10 自动备份、4:40 清 14 天前旧备份。
跑完它会打印本机自测结果和"下一步要做什么"。

**④ 阿里云 DNS 加一条 A 记录**

控制台 → 域名 → `lovinfirefly.cn` → 解析设置 → 添加记录：
`主机记录 = tianshu`、`类型 = A`、`记录值 = 服务器公网 IP`

> **不用改 NS** —— 域名继续留在阿里云，以后要拿它发验证码邮件也不受影响（在阿里云 DNS 里加 SPF/DKIM 就行）。

**⑤ 手机流量打开 `https://tianshu.lovinfirefly.cn`** —— 证书是 Caddy 自动申请的，第一次打开等 10 秒左右。

**以后怎么更新网站**：本机改完 → `git push` → 服务器上再跑一次
`bash /opt/tianshu/deploy/install.sh tianshu.lovinfirefly.cn`
（这条命令重复跑没事，等于"拉最新代码 + 重启服务"）

> 不管哪种：**数据都在 `data/`**，整个文件夹拷走就是完整备份。

## License

MIT，见 [LICENSE](LICENSE)
