# 甜薯网站 · 自动调试工具箱

装在 `网站/_调试工具/` 下，用来代替手工点网页：起服务 → 自动登录 → 遍历页面/跑写操作 → 把 4xx/5xx 和报错全列出来。
**只做检查，不动业务数据**（写操作脚本会在最后还原）。

## 装了什么

- `playwright`（Python 版）：`python -m pip install playwright`
- 浏览器用的是本机已有的 Playwright Chromium（无需再下载）：
  `C:\Users\junbo\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe`

## 怎么用

先起服务（另开一个窗口，一直开着）：

```
python app.py --no-browser --port 8099
```

然后按需跑（都在本目录下执行）：

| 脚本 | 作用 |
|---|---|
| `python crawl.py` | 浏览器登录 **FireFly**，遍历 90 个页面，列出所有 4xx/5xx |
| `python crawl_mobile.py` | 用**手机 UA** 走一遍，确认手机端没问题 |
| `python check_csrf_pages.py` | 逐页检查：有 POST 表单的页面是否都拿到了 CSRF 令牌（缺了必然 403） |
| `python scan_routes.py` | 进程内跑**全部路由 × 4 种身份**（游客/客户/DM/超管），抓 500 并打印堆栈 |
| `python scan_ui1.py` | 强制切「一代界面」再扫一遍路由，查模板缺失 |
| `python scan_forms.py` / `scan_hosts.py` | 静态扫描：哪些模板有 POST 表单却拿不到令牌 |
| `python flows_post.py` | 跑真实写操作：登录 → 预约 → 核销 → 完成 → 评价 |
| `python smoke_biz.py` | 用真实数据把 `business.py` 的函数挨个调一遍，抓"某类数据才炸"的隐藏 Bug |
| `python grep.py "关键词"` | UTF-8 安全的全项目搜索（替代对中文不靠谱的 findstr） |
| `python repro.py` / `check_me.py` | 复现单个页面的 500 并打印真实堆栈 |

## 2026-10 体检结果（已全部修复）

| 症状 | 根因 | 修复 |
|---|---|---|
| 每个页面控制台一条 **403** | `base.html` 用 `sendBeacon('/api/track')` 上报埋点，而 sendBeacon 发不了 CSRF 头 | `__init__.py` 把 `/api/track`、`/m/api/track` 列入 CSRF 豁免（只读埋点，不改数据） |
| 进「我的」**500** | `me.html` 显示收藏价格 `s.price`，但视图拼的收藏对象里漏了 `price` 字段 | `views/user.py` 补上 `price`，模板改成 `s.get('price') or 0` |
| 点「看 TA 主页」**404** | 14 条历史评价的 `username` 是"账号安全号"这类脏数据，不是真实账号 | `script.html` / `car_detail.html` 先判断该用户名是否真实存在，不存在就不显示链接 |

其余体检项（4 种身份 × 全部路由、业务函数烟雾测试、CSRF 覆盖率、手机端）均 **0 异常**。
