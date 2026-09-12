package io.cybersaarthi.fieldagent.data.connectivity

import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.auth.SessionManager
import io.cybersaarthi.fieldagent.data.config.ConnectionMode
import io.cybersaarthi.fieldagent.data.config.SettingsStore
import io.cybersaarthi.fieldagent.data.net.FieldApi
import io.cybersaarthi.fieldagent.data.net.FieldError
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Delay policy for the liveness beacon: a steady cadence on success and
 * exponential backoff on transient failures, capped at [MAX_BACKOFF_MS].
 */
object HeartbeatBackoff {
    const val BEAT_INTERVAL_MS = 60_000L
    const val IDLE_RETRY_MS = 5_000L
    const val MAX_BACKOFF_SHIFT = 4
    const val MAX_BACKOFF_MS = 10 * 60_000L

    fun nextDelayMs(consecutiveFailures: Int): Long {
        if (consecutiveFailures <= 1) return BEAT_INTERVAL_MS
        val exp = (consecutiveFailures - 1).coerceAtMost(MAX_BACKOFF_SHIFT)
        return minOf(BEAT_INTERVAL_MS * (1L shl exp), MAX_BACKOFF_MS)
    }
}

/**
 * Periodic approved-device liveness beacon.
 *
 * While the agent is ONLINE with a registered device for the active case, this
 * signs the canonical heartbeat message with the device key and reports it to
 * the server, which verifies it against the registered public key and records
 * a last-seen timestamp. Persistent approval/revocation transitions surface
 * through [ConnectionManager.exposeDeviceStatus].
 */
class HeartbeatManager(
    private val api: FieldApi,
    private val settings: SettingsStore,
    private val session: SessionManager,
    private val connection: ConnectionManager,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
) {

    private val _lastBeatAtEpochMillis = MutableStateFlow(0L)
    val lastBeatAtEpochMillis: StateFlow<Long> = _lastBeatAtEpochMillis.asStateFlow()

    private val _consecutiveFailures = MutableStateFlow(0)
    val consecutiveFailures: StateFlow<Int> = _consecutiveFailures.asStateFlow()

    @Volatile
    private var job: Job? = null

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch { loop() }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private suspend fun loop() {
        while (kotlin.coroutines.coroutineContext.isActive) {
            val auth = session.current() as? AuthState.Active
            val ready = auth != null &&
                settings.connectionMode == ConnectionMode.ONLINE &&
                settings.activeCaseId != null &&
                settings.deviceId != null
            if (!ready) {
                resetFailures()
                delay(HeartbeatBackoff.IDLE_RETRY_MS)
                continue
            }
            val caseId = settings.activeCaseId!!
            val deviceId = settings.deviceId!!
            val sent = sendBeat(auth!!, caseId, deviceId)
            delay(if (sent) HeartbeatBackoff.BEAT_INTERVAL_MS else HeartbeatBackoff.nextDelayMs(_consecutiveFailures.value))
        }
    }

    private suspend fun sendBeat(auth: AuthState.Active, caseId: String, deviceId: String): Boolean {
        val now = System.currentTimeMillis()
        return try {
            val result = api.heartbeat(auth.accessToken, caseId, deviceId, now)
            _lastBeatAtEpochMillis.value = now
            settings.lastSeenAtEpochMillis = now
            resetFailures()
            connection.exposeDeviceStatus(result.status)
            true
        } catch (t: Throwable) {
            _consecutiveFailures.value += 1
            when (t) {
                is FieldError.DevicePending -> connection.exposeDeviceStatus("pending")
                is FieldError.DeviceRevoked -> connection.exposeDeviceStatus("revoked")
                else -> Unit
            }
            false
        }
    }

    private fun resetFailures() {
        if (_consecutiveFailures.value != 0) _consecutiveFailures.value = 0
    }
}