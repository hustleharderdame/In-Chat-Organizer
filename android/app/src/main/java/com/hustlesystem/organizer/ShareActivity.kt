package com.hustlesystem.organizer

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * Share-to-capture: select text anywhere on the phone, Share -> Capture to graph.
 *
 * It posts to the same `/ingest` endpoint the PWA's Capture tab uses, so the
 * classification, reconciliation and ambiguity rules are identical — this is a
 * second *caller*, never a second implementation.
 *
 * Ambiguity is the one thing this path cannot resolve: there is no UI here to
 * choose between candidates. When the organizer asks a question, the text is
 * still safely filed as far as it can be, and the toast sends Dame to the app
 * to make the call.
 */
class ShareActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val text = when {
            intent?.action == Intent.ACTION_SEND && intent.type == "text/plain" ->
                intent.getStringExtra(Intent.EXTRA_TEXT)
            else -> null
        }

        if (text.isNullOrBlank()) {
            toastAndFinish(getString(R.string.capture_failed))
            return
        }

        thread {
            val message = try {
                postIngest(text)
            } catch (e: Exception) {
                getString(R.string.capture_failed)
            }
            runOnUiThread { toastAndFinish(message) }
        }
    }

    private fun postIngest(text: String): String {
        val url = URL(BuildConfig.ORGANIZER_URL.trimEnd('/') + "/ingest")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 4000
            readTimeout = 8000
            setRequestProperty("Content-Type", "application/json")
        }

        val payload = JSONObject()
            .put("text", text)
            .put("source_chat", "android-share")
            .toString()

        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(payload) }

        if (conn.responseCode !in 200..299) {
            return getString(R.string.capture_failed)
        }

        val body = conn.inputStream.bufferedReader().use { it.readText() }
        val result = JSONObject(body)
        val written = result.optJSONArray("written")?.length() ?: 0

        return when {
            result.optBoolean("needs_answer") ->
                "Filed $written — open Organizer to resolve a question"
            written == 0 -> "Nothing durable in that — skipped"
            else -> getString(R.string.captured)
        }
    }

    private fun toastAndFinish(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
        finish()
    }
}
