package io.cybersaarthi.fieldagent.data.connectivity

/**
 * Granular global connectivity state shown across the app.
 *  - CONNECTED: server reachable and, when signed in, session still valid.
 *  - CONNECTING: actively probing the server.
 *  - OFFLINE:       deliberate offline mode, no probing happens.
 *  - SERVER_UNREACHABLE: network up but the trusted server did not answer.
 *  - AUTH_EXPIRED:  server reachable but the access token has expired.
 *  - DEVICE_UNAPPROVED / DEVICE_REVOKED: device identity not usable (derived by flows
 *    that know the case-level device record).
 */
enum class ConnectionStatus {
    CONNECTED,
    CONNECTING,
    OFFLINE,
    SERVER_UNREACHABLE,
    AUTH_EXPIRED,
    DEVICE_UNAPPROVED,
    DEVICE_REVOKED;

    val isServerReachable: Boolean
        get() = this == CONNECTED || this == AUTH_EXPIRED || this == DEVICE_UNAPPROVED || this == DEVICE_REVOKED
}

/** Derives the device-level status from the case device record, if any. */
fun deviceStatusOf(deviceStatus: String?): ConnectionStatus = when (deviceStatus) {
    "revoked" -> ConnectionStatus.DEVICE_REVOKED
    "approved" -> ConnectionStatus.CONNECTED
    else -> ConnectionStatus.DEVICE_UNAPPROVED
}