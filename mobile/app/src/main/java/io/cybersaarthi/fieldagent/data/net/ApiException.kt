package io.cybersaarthi.fieldagent.data.net

import java.io.IOException

/** Domain errors surfaced to the UI. No raw exceptions leak to composables. */
sealed class FieldError(message: String, cause: Throwable? = null) : Exception(message, cause) {
    data object Network : FieldError("Network unreachable.")
    data object Timeout : FieldError("Request timed out.")
    data object Unauthorized : FieldError("Not authenticated.")
    data object Forbidden : FieldError("Forbidden.")
    data object NotFound : FieldError("Not found.")
    data class DevicePending(val detail: String) :
        FieldError("DevicePending: $detail")

    data class DeviceRevoked(val detail: String) :
        FieldError("DeviceRevoked: $detail")

    data class Server(val code: Int, val detail: String) :
        FieldError("Server $code: $detail")

    data class Validation(val detail: String) : FieldError("Validation: $detail")

    fun asUserMessage(): String = when (this) {
        Network, Timeout -> "network"
        Unauthorized -> "unauthorized"
        Forbidden -> "forbidden"
        is DevicePending -> "device_pending"
        is DeviceRevoked -> "device_revoked"
        NotFound -> "not_found"
        is Server -> "server"
        is Validation -> "validation"
    }
}

fun Throwable.toFieldError(): FieldError = when (this) {
    is FieldError -> this
    is IOException -> FieldError.Network
    else -> FieldError.Server(0, message ?: "unknown error")
}