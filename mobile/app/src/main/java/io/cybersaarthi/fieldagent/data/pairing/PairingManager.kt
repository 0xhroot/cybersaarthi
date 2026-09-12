package io.cybersaarthi.fieldagent.data.pairing

import java.security.MessageDigest
import java.util.Base64

/**
 * QR pairing payload parser and server-identity fingerprint helpers.
 *
 * Payload URI:  cybersaarthi://connect?u=<base64url apiBase>&fp=<sha256 hex>&nonce=<hex>&exp=<epochMillis>
 * The payload never contains a password, private key or long-lived credential.
 * [u] is the full API base URL (scheme://host:port/api/v1, normalised if needed),
 * [fp] is the SHA-256 identity the server is expected to present on first contact.
 */
data class PairingPayload(
    val serverUrl: String?,
    val fingerprint: String?,
    val nonce: String?,
    val expiresAtEpochMillis: Long?
)

object PairingManager {

    const val SCHEME = "cybersaarthi"
    const val CONNECT_HOST = "connect"

    fun parse(raw: String): PairingPayload? {
        val text = raw.trim()
        val prefix = "$SCHEME://$CONNECT_HOST"
        if (!text.startsWith(prefix)) return null
        val query = text.removePrefix(prefix).removePrefix("?")
        val params = query.split('&').mapNotNull { param ->
            val idx = param.indexOf('=')
            if (idx < 0) return@mapNotNull null
            val rawKey = param.substring(0, idx)
            val rawValue = param.substring(idx + 1).replace('+', '%')
            rawKey to rawValue
        }.toMap()

        val uRaw = params["u"] ?: ""
        val u = decodeBase64Url(uRaw) ?: uRaw
        val serverUrl = u.trim().let { raw ->
            if (raw.isEmpty()) null
            else {
                val lower = raw.lowercase()
                if (!lower.startsWith("http://") && !lower.startsWith("https://")) null
                else raw.trimEnd('/').let { if (it.endsWith("/api/v1")) it else "$it/api/v1" }
            }
        }
        val fp = params["fp"]?.lowercase()?.takeIf { it.matches(Regex("[0-9a-f]{64}")) }
        val nonce = params["nonce"]?.takeIf { it.isNotBlank() }
        val exp = params["exp"]?.toLongOrNull()
        if (serverUrl == null) return null
        return PairingPayload(serverUrl = serverUrl, fingerprint = fp, nonce = nonce, expiresAtEpochMillis = exp)
    }

    fun isExpired(payload: PairingPayload, nowEpochMillis: Long): Boolean {
        val exp = payload.expiresAtEpochMillis ?: return false
        return nowEpochMillis > exp
    }

    /** Canonical identity fingerprint derived from the unauthenticated health response. */
    fun computeServerFingerprint(service: String?, version: String?): String =
        sha256Hex("cybersaarthi-identity/1\nservice=${service.orEmpty()}\nversion=${version.orEmpty()}")

    fun fingerprintMatches(expected: String?, actual: String): Boolean {
        if (expected == null) return false
        return MessageDigest.isEqual(expected.toByteArray(), actual.toByteArray())
    }

    fun sha256Hex(input: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(input)
        return digest.joinToString("") { "%02x".format(it) }
    }

    private fun sha256Hex(input: String): String = sha256Hex(input.toByteArray())

    private fun decodeBase64Url(value: String): String? = try {
        String(Base64.getUrlDecoder().decode(value.replace('+', '-').replace('/', '_')))
    } catch (_: IllegalArgumentException) {
        null
    }
}