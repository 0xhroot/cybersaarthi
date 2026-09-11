package io.cybersaarthi.fieldagent.ui

import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.net.FieldError

/**
 * Translates a [FieldError] into a string-resource id for user-facing copy.
 * Keeps translation in resources and ViewModels free of Context.
 */
fun FieldError.resourceId(): Int = when (this) {
    FieldError.Network, FieldError.Timeout -> R.string.err_network
    FieldError.Unauthorized -> R.string.err_unauthorized
    FieldError.Forbidden -> R.string.err_forbidden
    is FieldError.DevicePending -> R.string.err_device_pending
    is FieldError.DeviceRevoked -> R.string.err_device_revoked
    FieldError.NotFound -> R.string.err_not_found
    is FieldError.Validation -> R.string.err_validation
    is FieldError.Server -> R.string.err_server
}