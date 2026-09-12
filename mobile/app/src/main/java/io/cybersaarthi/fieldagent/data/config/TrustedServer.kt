package io.cybersaarthi.fieldagent.data.config

import org.json.JSONObject
import java.security.MessageDigest

/**
 * Identity of a server the operator has explicitly trusted (via manual entry or
 * QR pairing). `hostLabel` is the human-readable label the server reports for
 * itself; hostname is the url that was trusted.
 */
data class TrustedServer(
    val hostLabel: String?,
    val hostname: String,
)
