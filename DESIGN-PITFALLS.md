# 已知陷阱清单 · 甜薯（unseen 版）

> 都是**踩过、修过、有证据**的。每条都写清「现象 → 根因 → 怎么修 → 怎么验证」，
> 免得同一个坑再踩第二次。

---

## 1. `.field` 类名撞车 —— 影响全站每一个表单

**现象**：登录、注册、唠嗑发帖、约本、我的资料设置 —— 页面上**输入框和 label 凭空消失**。
页面照常 200、不报错，看起来就像"设计成这样"。

**根因**：全站画布是 `<canvas class="field">`，而 `.field` **同时是表单字段的类名**。
画布那条

```css
.field { position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; }
```

于是命中了**每一个** `.field` 表单字段：全部变成全屏浮层、被定到 `(0,0)`。
`pointer-events: none` 还让它们连点都点不到。

**修法**：画布类名改为 `.field-canvas`（JS 用的是 `[data-field]` 属性，不受影响）。

**验证**：`/forgot /login /register /me /comm` 上 `.field` 全部回到 `static` 且宽度小于视口。

**通用的教训**：**给全局浮层起类名前，先 grep 这个词有没有被表单/组件占用。**

---

## 2. `data-count` 属性撞车 —— 本本墙首屏直接空白

**现象**：本本墙首屏**一张剧本卡都没有**。但点任意分类标签之后卡片又正常出现。
服务端 HTML 里有 28 张卡，浏览器 DOM 里 0 张。

**根因**：网格容器上写了 `data-count="{{ scripts|length }}"`（照抄二代的约定）。
而 `unseen.js` 的 `initCount()` 会**无差别**地把所有 `[data-count]` 元素的 `textContent`
换成滚动数字 —— 因为 `data-count` 在首页是**有意**用来做"数字滚动"的。

MutationObserver 抓到的现场：

```
146ms  首次解析：28 张卡 / 18482 字符     ← 解析完全正常
650ms  removed:57  added:1  head:"0"      ← 整片卡片被换成数字 "0"
653ms  head:"-1"   771ms "9"   816ms "12" ← 数字在滚动
```

**修法**：容器属性改名 `data-lib-n`。

**验证**：`document.querySelectorAll('.card').length === 28`（首屏）。

**通用的教训**：**复用属性名之前，先确认它的语义和消费方。**
`data-count` 在本项目里等于"这里是数字滚动目标"。

---

## 3. `transition` 做出场动画会"跳过位移"

**现象**：转场做完了，但肉眼看不到"旧场景上移、新场景从下上来"，新页面像凭空出现。

**根因**：`transition` 需要一个**上一帧已画出的计算样式**当起点。而换页时新场景是刚
`replaceChild` 插进来的节点，浏览器往往还没为它画过任何一帧就被加上了终点类 —— 位移被跳过。

**修法**：离场/入场改用 `animation`。`animation` 的 `from` 是关键帧，元素一挂上类就从 `from`
开始播，完全不依赖起始帧。

**验证**：密集采样 `getComputedStyle(main).transform` 的 `m42`，能读到 `+99px → +26px → +3px → 0`
的中间值。

---

## 4. 清场定时器硬编码 → 动画被拦腰截断

**现象**：旧场景的"上移"只播了 10% 就被换掉了（实测 `translateY` 才到 `-7px`，目标是 `-67px`）。

**根因**：JS 里写死 `MIN_OUT = 430ms`，而 CSS 里的离场时长是 `520ms`。
两个数字各自独立，改一个忘一个。

**修法**：时长只留一个来源 —— CSS 变量 `--tr-out / --tr-in / --tr-band`，JS 用
`getComputedStyle(document.documentElement).getPropertyValue('--tr-out')` 读同一个值。

---

## 5. 换页重跑页面级模块 → 监听/rAF 累积

**现象**：连点十来次导航之后帧率崩掉，或者光标出现"双影"、滚轮变成双倍速。

**根因**：换页必须重跑页面级模块（新 DOM 要重新接上动效）。但有两类资源**不会**随 DOM 回收：

- 挂在 `window` 上的 `scroll / resize` 监听
- 模块自己开的常驻 `requestAnimationFrame` 循环

重跑几次就变成"滚一格触发五次回调"。

**修法**：
- `loop(name, fn)` —— 同名再次注册自动替换（可重入 rAF）
- `pOn(target, ev, fn, opt)` / `pOff()` —— 页面级监听登记处，换页前统一摘掉
- 轮播的 `setInterval` 存到模块级变量，重跑前 `clearInterval`

**验证**：连点 6 次站内链接，FPS 稳定（实测 43~47，无衰减）。

---

## 6. `.auth` 左栏第一行被固定导航压住

**现象**：登录/注册/忘密码页左栏那个 `eyebrow`（「甜薯剧本杀」）看不见。

**根因**：`.nav` 是 `position: fixed` 高 86px，而 `.auth__aside` 的 `padding-top` 只有 63px。

**修法**：`:root { --nav-h: 86px }`，两栏 `padding-top: calc(var(--nav-h) + clamp(24px,4.5vh,58px))`。

---

## 7. `html.smooth` 是"关掉平滑滚动"的开关，别乱摘

**现象**：换页之后新场景从半空中**缓慢滑下来**，而不是瞬时复位。

**根因**：`html.smooth { scroll-behavior: auto }` —— 这个类是**把 CSS 平滑滚动关掉**的。
摘掉它，`window.scrollTo(0,0)` 就变成一段平滑滚动。

**修法**：换页时**不要**摘 `smooth`，保持它不动，`scrollTo` 才是瞬时的。

---

## 8. `ss -ltn` 看不到 TIME_WAIT

**现象**：线上 `update.sh` 跑完，systemd 显示 `activating (auto-restart) (Result: exit-code)`，
日志刷"端口 8000 已被占用，且当前是 STRICT_PORT 模式"。

**根因**：两个判断互相骗 ——

- `app.py` 的 `port_in_use()` 探测套接字**没设** `SO_REUSEADDR`，而 waitress 给它的监听套接字**设了**
  （`wasyncore.py`）。旧进程刚被杀掉时端口上只剩 `TIME_WAIT` 连接（Linux 默认 60s）——
  waitress 完全绑得上，探测却报 `EADDRINUSE` → `STRICT_PORT` 下 `exit(1)`。
- `update.sh` 用 `ss -ltn` 判断"端口空了"也是错的：**`ss -ltn` 只列 LISTEN，看不到 TIME_WAIT**。

**修法**：`port_in_use()` 在非 Windows 上设 `SO_REUSEADDR`（POSIX 下它不允许绑上别人正在
LISTEN 的端口，判断依然准确；Windows 例外 —— 那边会真抢端口，所以只在非 Windows 加）。
`update.sh` 用 `_port_bindable()`（跑与 `app.py` **完全相同**的绑定测试）替代 `ss -ltn`。

**救急**：`fuser -k 8000/tcp ; sleep 2 ; systemctl restart tianshu`

---

## 9. 取证时"几何与截图要同一时刻取"

**现象**：同一页面的 `scrollHeight` 两次测出 `1281` 和 `2207`，自相矛盾，浪费了很久。

**根因**：页面里 `.veil` + `[data-reveal]` 在 2s 前后仍有过渡；而 `page.screenshot()` 在
软渲染下每张要 200~300ms，采样间隔远大于标称值 —— 分开两次跑必然对不上。

**修法**：每页**先 `evaluate` 读几何、紧接着 `screenshot`**，同一个循环里做完。
要抓动画中间态就**只 `evaluate` 不截图**，并把 CSS 时长临时放大再采样。

---

## 10. 转场点击拦截：同路径 + query 不能一刀切放行

**现象**：点首页「先瞅瞅有啥本」（`/` → `/?browse=1`，欢迎页→浏览页）时，整页被 reload（"整页 load 新增 = 1"），v9 的场景流动转场没生效，像退回了最原始的硬跳。

**根因**：`Transit` 的点击拦截里有一条早期规则：

```js
if (url.pathname === location.pathname && url.search) return;
```

本意是：本本墙原地换网格（`?partial=1` 只改 query）应当交给页面自己的 `[data-lib]` 处理，别被转场拦截。但它**没有区分"是不是本本墙"** —— 任何"同路径 + 改 query"的链接都被放行，于是 `/` → `/?browse=1` 这次"整页内容替换"也被放过了，走回整页 load。

**修法**：放行条件收紧到"页面真的有原地换内容的标记"才交给页面自己：

```js
if (url.pathname === location.pathname && url.search && document.querySelector('[data-lib]')) return;
```

只有本本墙（`[data-lib]`）才走页面内 swap；其它同路径改 query 一律照常走 fetch 换 DOM。

**验证**：playwright 点「先瞅瞅有啥本」，`整页 load 新增 = 0`，转场层正常工作；本本墙分类切换仍是原地换网格、不受影响。

---

## 11. 本节的方法论（怎么发现这些坑的）

| 手段 | 用途 |
|---|---|
| 「裸类名属性冲突扫描」脚本 | 专抓 `.field` 这类同名撞车（见项目技能 §5） |
| `MutationObserver` 埋点 | 定位"谁在什么时候把 DOM 改坏了"（`data-count` 就是这么抓到的） |
| `add_init_script` 在 `DOMContentLoaded` 抢测 | 区分"解析期丢的"还是"JS 删的" |
| `file://` 落盘对照 | 区分"HTML 内容问题"还是"加载路径问题" |
| `DOMParser` 二次解析 | 同一份 HTML 换个解析路径对照结果 |
| 密集 `evaluate`（不截图） | 抓动画中间值 |
| CSS 变量统一时长 | 让"取证时放慢"也能同步放大 JS 的清场时机 |
