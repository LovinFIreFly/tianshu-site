package cn.lovinfirefly.tianshu

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * 甜薯剧本杀 · 壳 App。
 *
 * 就做一件事：打开就进 https://tianshu.lovinfirefly.cn
 * 网站改版、上剧本、改价格，App 里立刻是新的 —— 不用重新打包、不用重新装。
 *
 * 三条刻意的设计：
 *  ① 站外链接交给系统浏览器 —— 别在 App 里裸奔（跳到陌生网站还没有地址栏，很危险）
 *  ② 返回键先网页后退，退不动了才退出 —— 一按返回就退出 App 让人抓狂
 *  ③ 转屏不重建 Activity（写在 Manifest 的 configChanges 里）—— 重建会重新加载网页，
 *     登录态和填了一半的表单全丢
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var swipe: SwipeRefreshLayout
    // 必须懒加载：Activity 的 Context 是框架在 attach() 里塞进来的，
    // 字段初始化的那一刻还没有 —— 直接写 getString() 会在启动时崩。
    private val home: String by lazy { getString(R.string.home_url) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        // 启动画面（纸底 + 薯字图标）是 Activity 的主题给的，这里换回正常主题再铺网页
        setTheme(R.style.Theme_Tianshu)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        swipe = findViewById(R.id.swipe)
        web = findViewById(R.id.web)

        web.settings.apply {
            javaScriptEnabled = true          // 网站是服务端渲染 + 少量 JS，必须开
            domStorageEnabled = true          // 登录态、深色模式、CSRF cookie 都靠它
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW   // 只认 https
            userAgentString = "$userAgentString TianshuApp/1.0"          // 让网站知道是 App 里打开的
        }

        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                // 只认自己的域名，其它一律丢给系统浏览器（微信支付、外链等）
                return if (url.startsWith(home) || url.startsWith("https://tianshu.lovinfirefly.cn")) {
                    false
                } else {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    true
                }
            }

            override fun onPageFinished(view: WebView, url: String) {
                swipe.isRefreshing = false
                // 已经在 App 里了，就别再显示「装到桌面」那一格
                view.evaluateJavascript(
                    "var b=document.getElementById('install-btn'); if(b) b.style.display='none';", null
                )
            }
        }

        web.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, progress: Int) {
                if (progress in 1..99) swipe.isRefreshing = true
            }
        }

        swipe.setOnRefreshListener { web.reload() }

        web.loadUrl(home)

        // 返回键：先网页后退，退不动了才退出 App
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
    }
}
