package io.cybersaarthi.fieldagent.data.net

/**
 * Canonical bytes signed for the approved-device liveness beacon.
 *
 * The backend re-derives this exact string (`_heartbeat_message` in
 * `backend/app/api/routes/devices.py`) before verifying the signature, so the
 * protocol banner and field/ordering must stay in sync with the server.
 */
object HeartbeatMessage {

    const val PROTOCOL = "cybersaarthi-heartbeat/1"

    fun build(caseId: String, deviceId: String, timestampEpochMillis: Long): String =
        "$PROTOCOL\ncase_id=$caseId\ndevice_id=$deviceId\ntimestamp=$timestampEpochMillis"
}