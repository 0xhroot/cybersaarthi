package io.cybersaarthi.fieldagent.data.connectivity

import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.auth.SessionManager
import io.cybersaarthi.fieldagent.data.config.ConnectionMode
import io.cybersaarthi.fieldagent.data.config.SettingsStore
import io.cybersaarthi.fieldagent.data.net.FieldApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Single source of truth for the global connection state. Combines the OS
 * network signal, the trusted-server health probe and the session lifecycle.
 * Health probing is unauthenticated (`GET /api/v1/health`) so it never depends
 * on credentials being valid; session-derived states layer on top of it.
 */
class ConnectionManager(
    private val api: FieldApi,
    private val settings: SettingsStore,
    private val session: SessionManager,
    private val connectivity: ConnectivityMonitor
) {

    private val _status = MutableStateFlow(ConnectionStatus.CONNECTING)
    val status: StateFlow<ConnectionStatus> = _status.asStateFlow()

    /** Delegated OS-level network-online signal. */
    val online: StateFlow<Boolean> = connectivity.online

    private val _lastProbeAtEpochMillis = MutableStateFlow(0L)
    val lastProbeAtEpochMillis: StateFlow<Long> = _lastProbeAtEpochMillis.asStateFlow()

    private val _lastProbeError = MutableStateFlow<String?>(null)
    val lastProbeError: StateFlow<String?> = _lastProbeError.asStateFlow()

    /** Re-probes immediately; safe to call from any screen. */
    suspend fun probe() {
        if (settings.connectionMode == ConnectionMode.OFFLINE) {
            _status.value = ConnectionStatus.OFFLINE
            _lastProbeAtEpochMillis.value = System.currentTimeMillis()
            _lastProbeError.value = null
            return
        }
        val url = settings.serverUrl
        if (url.isBlank()) {
            _status.value = ConnectionStatus.SERVER_UNREACHABLE
            _lastProbeAtEpochMillis.value = System.currentTimeMillis()
            _lastProbeError.value = "No server configured"
            return
        }
        if (!connectivity.hasCapableNetwork()) {
            _status.value = ConnectionStatus.SERVER_UNREACHABLE
            _lastProbeAtEpochMillis.value = System.currentTimeMillis()
            _lastProbeError.value = "No network"
            return
        }
        _status.value = ConnectionStatus.CONNECTING
        try {
            api.health()
            _lastProbeError.value = null
            _status.value = derivePostAuthState()
        } catch (t: Throwable) {
            _status.value = ConnectionStatus.SERVER_UNREACHABLE
            _lastProbeError.value = t.message
        }
        _lastProbeAtEpochMillis.value = System.currentTimeMillis()
    }

    private fun derivePostAuthState(): ConnectionStatus {
        val auth = session.current() ?: return ConnectionStatus.CONNECTED
        return if (session.isExpired(auth as io.cybersaarthi.fieldagent.data.auth.AuthState.Active))
            ConnectionStatus.AUTH_EXPIRED
        else ConnectionStatus.CONNECTED
    }

    /** Device-level status layered over a reachable server, e.g. after an enrollment check. */
    fun exposeDeviceStatus(deviceStatus: String?) {
        if (_status.value != ConnectionStatus.CONNECTED) return
        _status.value = deviceStatusOf(deviceStatus)
    }

    fun resetDeviceStatus() {
        if (_status.value == ConnectionStatus.DEVICE_UNAPPROVED ||
            _status.value == ConnectionStatus.DEVICE_REVOKED
        ) {
            _status.value = ConnectionStatus.CONNECTED
        }
    }

    fun authExpired() {
        if (_status.value.isServerReachable) _status.value = ConnectionStatus.AUTH_EXPIRED
    }

    fun notifySessionCleared() {
        val auth = session.current() as? AuthState.Active
        if (auth == null) _status.value = if (settings.connectionMode == ConnectionMode.OFFLINE) {
            ConnectionStatus.OFFLINE
        } else {
            ConnectionStatus.CONNECTED
        }
    }
}