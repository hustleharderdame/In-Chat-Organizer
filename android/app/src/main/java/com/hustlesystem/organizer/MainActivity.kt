package com.hustlesystem.organizer

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * The whole app: a WebView over the organizer's PWA, which the Flask app in
 * Termux serves on loopback.
 *
 * There is deliberately no native UI duplicating the graph views. The PWA is
 * the single source for the front-end — shipping a second implementation here
 * would mean every change to a node card had to be made twice.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var refresh: SwipeRefreshLayout
    private lateinit var offline: LinearLayout

    /** True once a load has failed, so we don't flash the offline screen on a
     *  sub-resource error that the page itself recovered from. */
    private var lastLoadFailed = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        web = findViewById(R.id.web)
        refresh = findViewById(R.id.refresh)
        offline = findViewById(R.id.offline)

        web.settings.apply {
            javaScriptEnabled = true
            // The PWA remembers the active tab in localStorage.
            domStorageEnabled = true
            // Everything is served from loopback; no reason to allow file access.
            allowFileAccess = false
            allowContentAccess = false
            cacheMode = android.webkit.WebSettings.LOAD_DEFAULT
        }

        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                lastLoadFailed = false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                refresh.isRefreshing = false
                if (!lastLoadFailed) showOffline(false)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                // Only the main document failing means the server is down; a
                // failed icon fetch is not worth blanking the screen for.
                if (request?.isForMainFrame == true) {
                    lastLoadFailed = true
                    refresh.isRefreshing = false
                    showOffline(true)
                }
            }
        }

        refresh.setOnRefreshListener { web.reload() }
        findViewById<Button>(R.id.retry).setOnClickListener { load() }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })

        if (savedInstanceState == null) load() else web.restoreState(savedInstanceState)
    }

    private fun load() {
        showOffline(false)
        web.loadUrl(BuildConfig.ORGANIZER_URL)
    }

    private fun showOffline(visible: Boolean) {
        offline.visibility = if (visible) View.VISIBLE else View.GONE
        refresh.visibility = if (visible) View.GONE else View.VISIBLE
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }
}
