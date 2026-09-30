# changelog-C-v6 · 动效 CSS 代理（代号 C）

> 规范：design-spec-v6.md §0「豆包动效质感规范」。
> 改动文件：仅 `tianshu/static/css/design3.css`、`tianshu/static/css/mobile-zine.css`。
> 未碰：mobile/styles.css（T2）、模板、JS、皮肤 skin-*、冻结块。

---

## 1. 微交互 token（design3.css `:root`）

在 `--d-ease` 之后、`:root` 收尾前追加（**不在冻结块内**）：

| 选择器 / 变量 | 值 | 用途 |
|---|---|---|
| `--d-pop` | `cubic-bezier(.16,1,.3,1)` | 弹层/Sheet 入场缓动 |
| `--d-pop-out` | `cubic-bezier(.4,0,1,1)` | 弹层退出缓动 |
| `--d-tap` | `.24s` | 弹层入场时长（按压节奏基准） |

reduced-motion 覆盖：全局 `*{animation-duration:.01ms !important;transition-duration:.01ms !important}`（design3.css 约 707 行）兜底，token 本身无动画无需单独关。

## 2. 弹层 / Sheet 动效类（design3.css，v6 新块，位于 v5 冻结块**之前**）

供 T1 模板新弹层（FAQ、发帖、发票、角色卡等）直接挂类；退出时由 JS 在关闭瞬间给根节点加 `[data-leave]`。

| 选择器 | 效果 | 时长 | 缓动 | reduced-motion |
|---|---|---|---|---|
| `.sheet--pop` | 入场 `opacity 0→1` + `translateY(28px)→0` | `var(--d-tap)` = .24s | `var(--d-pop)` | 显式 `animation:none` |
| `.sheet--mask` | 遮罩 `opacity 0→1` | .2s | ease | 显式 `animation:none` |
| `.sheet--pop[data-leave]` | 退出 `opacity 1→0` + `translateY(0→8px)` | .2s | `var(--d-pop-out)` | 显式 `animation:none` |
| `.sheet--mask[data-leave]` | 遮罩 `opacity 1→0` | .2s | ease | 显式 `animation:none` |

配套 keyframes：`d-sheet-in / d-sheet-out / d-sheet-mask-in / d-sheet-mask-out`。
只做位移+透明度，无渐变/毛玻璃/光晕。

## 3. 按钮微反馈（:active）

逐条核验既有规则，**只补缺、不重复加**：

| 类 | 现状 | 本次动作 |
|---|---|---|
| `.b3` | 已有 `transition:...transform .16s` 且 `.b3:active{transform:translateY(1px);box-shadow:none}`（design3.css ~561 行） | 无需改 |
| `.chip3` | 已有 `transition:...transform .18s` 且 `.chip3:active{transform:translateY(0)}`（hover 为 -1px，active 回中） | 无需改 |
| `.adm-tile` | mobile-zine.css 已有 `.adm-tile:active{transform:scale(.97);...}`（~435 行，冻结块内） | 无需改 |
| `.dm-tab` | 基础规则在冻结块（mobile-zine 328-475 行）内，**无 transition、无 :active** | **在 mobile-zine.css 末尾追加新规则块**（不动冻结行）：`.dm-tab{transition:transform .15s var(--d-ease)}` + `.dm-tab:active{transform:scale(.97)}` |
| `.btn3` | **两个 CSS 文件中均不存在该类**（grep 全 css 目录 0 命中），其样式应在 base style.css 或 T2 的 mobile/styles.css | 本所有权范围无法落地，留待 T2 / 全局样式层 |

## 4. 逐段揭示 `.rv--rise`（design3.css v6 块）

| 选择器 | 效果 | 时长 | 缓动 | 触发 | reduced-motion |
|---|---|---|---|---|---|
| `.rv--rise` | 初始 `opacity:0;transform:translateY(14px)` | — | — | 默认隐藏 | `opacity:1;transform:none;transition:none` |
| `.rv--rise.in` | `opacity 0→1` + `translateY(14px)→0` | .4s | `var(--d-ease)` | IntersectionObserver 加 `.in`（与既有 `.rv` 体系同用法） | 同上 |

移动端：该类全局定义、纯 opacity/transform，mobile-zine.css 无需重复覆盖。

## 5. 骨架屏 `.skeleton`（design3.css v6 块）

| 选择器 | 效果 | 时长 | 缓动 | reduced-motion |
|---|---|---|---|---|
| `.skeleton` | 底色 `color-mix(in srgb,var(--d-ink) 10%,transparent)`（随明暗主题自适应，不引入新色值）；`animation:d-pulse 1.4s ease-in-out infinite`（opacity .5↔1） | 1.4s 循环 | ease-in-out | 显式 `animation:none` |

## 6. reduced-motion 覆盖

- design3.css 全局兜底 `*{animation-duration:.01ms !important;transition-duration:.01ms !important}`（~707 行）已覆盖**全部**动画/过渡。
- v6 块内**另写显式媒体查询**点名 `.sheet--*` / `.rv--rise` / `.skeleton`，双保险。
- mobile-zine.css 末尾已有 `html[data-device="mobile"] *{animation:none !important;transition:none !important}`（~492 行），移动端新类自动被覆盖。

## 7. mobile-zine.css 移动端适配

- 弹层 / rise / skeleton 均由 design3.css 全局类提供，移动端直接生效，**不重复定义**。
- 仅在文件**末尾**追加 `.dm-tab` 按压反馈（见 §3）。
- 管理端导航块 328-475 行**一行未改**（Edit 为精确字符串替换，仅在文件末尾追加）。

---

## 与 T1 类名对齐结果

- 写作本 changelog 时，`changelog-T1-v6.md` **尚未产出**（`_analysis/` 目录无此文件，T1 并行中）。
- 已严格按 spec §0 命名实现：`.sheet--pop` / `.sheet--mask` / `[data-leave]` / `.rv--rise` / `.skeleton` / `--d-pop` / `--d-pop-out` / `--d-tap`。
- **待 T1 changelog 落地后核验**：若 T1 模板引用了别名（如 `.sheet`、`.modal--pop` 等），C 在本文件补别名规则（一行 mapping）即可，不改动既有语义。

## 自检结果

- 花括号配平（python 统计，去掉注释后）：design3.css `877/877` ✅；mobile-zine.css `102/102` ✅。
- 冻结值：`.adm-side .navi-no{color:rgba(255,255,255,.52)}` 仍为 `.52`（design3.css 863 行）✅；`--d-ink-4` 回退 `#6B655C` 未动（35 行）✅。
- design3.css 末尾 v5 块（keyframes d-tear-in / d-stamp / d-ink-drop / d-page-flip-in / d-unfold + .tear-in/.ink-drop/.unfold/.flip-in/.stamp3 + 其 reduced-motion）逐行原样，v6 块插在其前 ✅。
- mobile-zine.css 328-475 行管理端导航块未改（仅在文件末尾追加）✅。
- 未引入渐变/毛玻璃/霓虹/光晕；动效仅位移+透明度+比例；未改任何色值与字体 ✅。

## 未做项与原因

- `.btn3` 类不在本所有权 CSS 中，未落地（见 §3）。
- T1 别名对齐待 T1 changelog 落地后补。

---

# 附：T1 类名对齐补充（第二轮，对接 changelog-T1-v6.md §二）

> T1 changelog 已落地，其 §二「需要 C 代理补充的 CSS 类名清单」表格全部按 spec 命名实现于 design3.css v6 块内（仍在 v5 冻结块**之前**）。色值全走既有 token，未引入新色；动效只位移/透明度。

## 新增规则逐条（design3.css）

| 选择器 | 效果 | 时长/缓动 | reduced-motion |
|---|---|---|---|
| `.filterbar3` | flex wrap 横排筛选条，发丝线描边 + 纸白底，input/select 38px 高、聚焦朱红边 | —（静态布局） | 全局 * 兜底 |
| `.share-toast` | 固定底部居中 pill（--d-ink 底/--d-paper-3 字）；`.show` 淡入上移 12px→0 | opacity/transform 各 .2s，transform 用 `var(--d-pop)` | 显式 `transition:none;opacity:1;transform:translate(-50%,0)` |
| `.role3__ph` | 补 `position:relative`（为编号叠角定位；追加声明不改原规则） | — | — |
| `.role3__no` | 竖排（writing-mode:vertical-rl）mono 小编号，朱红，叠海报左上 6px | — | — |
| `.role3__line` | 一句话人设，12px、墨灰（--d-ink-3）、1.55 行高 | — | — |
| `.ccard3__count` | 倒计时 mono 朱红小字 | — | — |
| `.ccard3__like` | 「口味相近」提示：朱红 12px + 前置 6px 圆点（::before） | — | — |
| `.car-mem-av` | 30px 圆形成员头像位（与 .avatar 同款：--d-ink 底/--d-paper-3 字），内含 img cover | — | — |
| `.faq-layout` | grid 110px 侧栏 + 1fr 内容，max 880 居中 | — | — |
| `.faq-rail` / `.faq-rail__t` | 左侧 sticky 竖排 kicker（vertical-rl、.3em 字距、--d-ink-4） | — | — |
| `.faq-list` / `.faq-item` | 问答流纵向排列，项间发丝线分隔（首/尾各一条） | — | — |
| `.faq-item__no` / `__q` / `__a` | 编号朱红 mono / 问题衬线 18px / 答案 14.5px 墨灰 1.75 行高 | — | — |
| `.visit-bar` | 访问 top10 行：24px 编号 + 路径 + 次数，虚线分隔 | — | — |
| `.visit-bar__track` / `__track i` | 百分比条：6px 高圆角底（--d-paper-2）+ 朱红 `<i>`（宽度由模板内联百分比） | — | — |
| `@media(max-width:833px)` | `.filterbar3` input/select 弹性通栏；`.faq-layout` 塌成单栏、kicker 转横排 | — | — |

## 与 T1 清单的对齐结论

- `.rv--rise`：C 第一轮已提供，T1 直接复用 ✅。
- `.sheet3` 弹层化：**未做**。原因：`.sheet3` 在 design3.css 中已是「车次列表」组件（grid 行式，454 行起），T1 把复盘 `<details class="sheet3">` 复用了该类名，现有样式仅给 details 加一条上边框，视觉可接受；若后续要把复盘做成真弹层，T1 应另挂 `.sheet--pop`（C 已提供），不要复用 `.sheet3`。
- `.filterbar3/.share-toast/.role3__no/.role3__line/.ccard3__count/.ccard3__like/.car-mem-av/.faq-*/.visit-bar*`：全部按表落地 ✅。
- mobile-zine.css：本轮**未再追加**——以上类均为 design3.css 全局定义，且色值走 `--d-*` token（移动端由 mobile-zine 的 `--z-*` 桥接自动换色），窄屏断点已在 design3.css `@media(max-width:833px)` 覆盖。

## 第二轮自检

- 花括号配平：design3.css `911/911` ✅（mobile-zine.css 本轮未动，仍 `102/102`）。
- 冻结值：`.adm-side .navi-no` 仍 `.52`（863 行）✅；`--d-ink-4` 回退 `#6B655C`（35 行）✅；v5 块仍在文件末尾（1601 行起）逐行原样 ✅。
- mobile-zine.css 328-475 行管理端导航块：本轮零改动 ✅。
- 无渐变/毛玻璃/霓虹/光晕；未改色值、字体；未碰 mobile/styles.css / 模板 / JS / 皮肤 ✅。

