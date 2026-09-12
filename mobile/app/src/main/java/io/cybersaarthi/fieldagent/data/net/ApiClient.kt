package io.cybersaarthi.fieldagent.data.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

/**
 * Thin typed HTTP client for the CyberSaarthi backend.
 *
 * Requests are executed on the OkHttp dispatcher; the base URL is resolved
 * lazily so the operator can change the server from the UI without recreating
 * the client. All transport failures are mapped to [FieldError].
 */
class ApiClient(
    baseUrlProvider: () -> String,
    connectTimeoutSeconds: Long = 15,
    readTimeoutSeconds: Long = 60
) {
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(connectTimeoutSeconds, TimeUnit.SECONDS)
        .readTimeout(readTimeoutSeconds, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    @Volatile
    private var baseUrlProvider: () -> String = baseUrlProvider

    fun baseUrl(): String = baseUrlProvider()

    /**
     * Combines the configured base URL with an API path. The base URL may be
     * entered either with (e.g. `…:8000/api/v1`) or without (e.g. `…:8000`)
     * the trailing `/api/v1`, so an explicit `/api/v1` prefix on [path] is never
     * doubled into the final request URL.
     */
    private fun resolveUrl(path: String): String {
        val base = baseUrl().trimEnd('/')
        return if (path.startsWith("/api/v1") && base.endsWith("/api/v1")) {
            base + path.removePrefix("/api/v1")
        } else {
            base + path
        }
    }

    /** Executes a JSON request and returns the raw response body (or null when 204). */
    suspend fun requestJson(
        method: String,
        path: String,
        body: String? = null,
        token: String? = null
    ): String = withContext(Dispatchers.IO) {
        val url = resolveUrl(path)
        val jsonType = "application/json; charset=utf-8".toMediaType()
        val builder = Request.Builder().url(url).method(method, body?.toRequestBody(jsonType))
        token?.let { builder.header("Authorization", "Bearer $it") }
        execute(builder.build())
    }

    /** Executes a multipart/form-data request. Files are uploaded last. */
    suspend fun requestMultipart(
        method: String,
        path: String,
        fields: Map<String, String> = emptyMap(),
        files: List<Pair<String, File>> = emptyList(),
        token: String? = null,
        blobs: List<Triple<String, String, ByteArray>> = emptyList()
    ): String = withContext(Dispatchers.IO) {
        val url = resolveUrl(path)
        val mp = MultipartBody.Builder().setType(MultipartBody.FORM)
        fields.forEach { (k, v) -> mp.addFormDataPart(k, v) }
        files.forEach { (name, file) ->
            val media = contentTypeFor(file.name).toMediaType()
            mp.addFormDataPart(name, file.name, file.asRequestBody(media))
        }
        blobs.forEach { (partName, fileName, bytes) ->
            val media = if (partName == "manifest") "application/json; charset=utf-8".toMediaType()
            else "application/octet-stream".toMediaType()
            mp.addFormDataPart(partName, fileName, bytes.toRequestBody(media))
        }
        val builder = Request.Builder()
            .url(url)
            .method(method, mp.build())
        token?.let { builder.header("Authorization", "Bearer $it") }
        execute(builder.build())
    }

    private fun execute(request: Request): String {
        try {
            client.newCall(request).execute().use { response ->
                val code = response.code
                val bodyText = response.body?.string().orEmpty()
                if (code in 200..299) {
                    return bodyText
                }
                val detail = extractDetail(bodyText).orEmpty()
                throw when (code) {
                    HttpURLConnection.HTTP_UNAUTHORIZED -> FieldError.Unauthorized
                    HttpURLConnection.HTTP_FORBIDDEN -> {
                        if (detail.contains("pending", ignoreCase = true)) FieldError.DevicePending(detail)
                        else if (detail.contains("revoked", ignoreCase = true)) FieldError.DeviceRevoked(detail)
                        else FieldError.Forbidden
                    }
                    HttpURLConnection.HTTP_NOT_FOUND -> FieldError.NotFound
                    HttpURLConnection.HTTP_BAD_REQUEST -> FieldError.Validation(detail.ifBlank { bodyText })
                    422 -> FieldError.Validation(detail.ifBlank { bodyText })
                    else -> FieldError.Server(code, detail.ifBlank { bodyText })
                }
            }
        } catch (e: SocketTimeoutException) {
            throw FieldError.Timeout
        } catch (e: java.net.UnknownHostException) {
            throw FieldError.Network
        } catch (e: java.net.ConnectException) {
            throw FieldError.Network
        } catch (e: IOException) {
            throw FieldError.Network
        }
    }

    private fun extractDetail(raw: String): String? {
        return try {
            val obj = JSONObject(raw)
            obj.optString("detail").ifBlank { null }
        } catch (_: Exception) {
            null
        }
    }

    private fun contentTypeFor(name: String): String = when {
        name.endsWith(".jpg") || name.endsWith(".jpeg") -> "image/jpeg"
        name.endsWith(".png") -> "image/png"
        name.endsWith(".mp4") -> "video/mp4"
        name.endsWith(".m4a") || name.endsWith(".aac") -> "audio/mp4"
        name.endsWith(".webm") -> "audio/webm"
        name.endsWith(".pdf") -> "application/pdf"
        name.endsWith(".txt") || name.endsWith(".json") -> "text/plain"
        name.endsWith(".csv") -> "text/csv"
        else -> "application/octet-stream"
    }
}