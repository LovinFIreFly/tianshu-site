# 甜薯剧本杀 · 安卓壳 App

打开 App 就进 `https://tianshu.lovinfirefly.cn` —— 里面就是网站本体（WebView 包壳）。
**网站改版、上剧本、改价格，App 里立刻是新的，不用重新打包。**

## 出 APK（两种方式）

### 方式一：Android Studio（推荐，最稳）

1. 装 [Android Studio](https://developer.android.com/studio)（装完第一次打开会自己下 SDK，要联网）
2. `File → Open` → 选这个 **`android` 文件夹** → 等右下角的 Gradle Sync 跑完
3. `Build → Build Bundle(s) / APK(s) → Build APK(s)`
4. 右下角点 `locate` 就能拿到 `app-debug.apk`，传到手机装上即可

> 第一次 Sync 要下载 Gradle 和依赖，慢（5~20 分钟），之后每次几十秒。

### 方式二：命令行（装好 SDK 后）

```bash
cd android
./gradlew assembleDebug          # Windows 用 gradlew.bat assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

## 上架前要改的两处

| 文件 | 现在 | 改成 |
|---|---|---|
| `app/build.gradle` 的 `versionCode / versionName` | 1 / 1.0 | 每次更新 +1，否则装不上（系统会拒绝降级） |
| `app/build.gradle` 的 `release` 签名 | 用默认的调试签名 | 正式发布要用自己的签名（`Build → Generate Signed Bundle / APK`），**签名文件务必备份**，丢了就没法再更新同一个 App |

调试签名的 APK 自己用没问题，但不能上架应用商店。

## 换域名 / 换图标

- 换域名：改 `app/src/main/res/values/strings.xml` 里的 `home_url`
- 换图标：改仓库根的 `tools/make_icons.py`，然后跑 `python tools/make_icons.py`
  （会同时更新网站图标、favicon 和安卓的 `mipmap-*`，一次到位）

## 已经处理好的几件小事

| 事 | 做法 |
|---|---|
| 转屏不重新加载网页 | Manifest 里 `configChanges`（重建会把登录态和填了一半的表单全丢） |
| 返回键 | 先网页后退，退到首页了才退出 App（一按就退出很烦） |
| 站外链接 | 交给系统浏览器，不在 App 里裸奔（没有地址栏很危险） |
| 启动白屏 | 开屏直接显示纸底 + 「薯」字图标（主题 `Theme.Tianshu.Launch`） |
| 下拉刷新 | 手机上习惯用它，没有会以为卡住了 |
| 只走 https | `usesCleartextTraffic=false` + `MIXED_CONTENT_NEVER_ALLOW` |
| 已经在 App 里 | 网页里那格「装到桌面」会自动隐藏 |
