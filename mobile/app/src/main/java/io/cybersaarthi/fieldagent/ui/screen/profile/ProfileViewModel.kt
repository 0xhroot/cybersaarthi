package io.cybersaarthi.fieldagent.ui.screen.profile

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.config.ConnectionMode
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import kotlinx.coroutines.launch

data class ProfileUiState(
    val username: String = "",
    val email: String? = null,
    val status: String = "",
    val serial: String = "",
    val fingerprint: String = "",
    val serverHost: String = "",
    val serverUrl: String = "",
    val connectionMode: ConnectionMode = ConnectionMode.ONLINE,
    val unlockEnabled: Boolean = false,
    val unlockMessage: String? = null
)

class ProfileViewModel(private val container: AppContainer) : ViewModel() {

    var ui by mutableStateOf(
        ProfileUiState(
            serverHost = container.settings.trustedServer()?.hostLabel ?: "",
            serverUrl = container.settings.serverUrl,
            connectionMode = container.settings.connectionMode,
            unlockEnabled = container.offlineUnlock.isEnabled()
        ).let { initial ->
            val auth = container.session.current() as? AuthState.Active
            initial.copy(
                username = auth?.username ?: "",
                email = auth?.userEmail,
                status = auth?.userStatus ?: "",
                serial = DeviceIdentity.serial,
                fingerprint = DeviceIdentity.keyFingerprint
            )
        }
    )
        private set

    fun signOut() {
        container.session.clear()
        container.settings.activeCaseId = null
        container.connection.notifySessionCleared()
    }

    fun setUnlockPassphrase(passphrase: String) {
        if (passphrase.length < io.cybersaarthi.fieldagent.data.offline.OfflineUnlock.MIN_PASSPHRASE_LENGTH) {
            ui = ui.copy(unlockMessage = "Passphrase must be at least 6 characters.")
            return
        }
        val ok = container.offlineUnlock.setPassphrase(passphrase)
        ui = ui.copy(unlockEnabled = ok, unlockMessage = if (ok) "Passphrase saved." else "Could not set passphrase.")
    }

    fun lockOffline() {
        container.offlineUnlock.lock()
        ui = ui.copy(unlockMessage = "Work session locked.")
    }

    fun clearUnlockPassphrase() {
        container.offlineUnlock.clearPassphrase()
        ui = ui.copy(unlockEnabled = false, unlockMessage = "Passphrase removed.")
    }

    fun refreshConnection() {
        viewModelScope.launch {
            try {
                val health = container.api.health()
                ui = ui.copy(
                    serverHost = container.settings.trustedServer()?.hostLabel ?: container.settings.serverUrl,
                    unlockMessage = "Server: ${health.service} v${health.version}"
                )
            } catch (t: Throwable) {
                ui = ui.copy(unlockMessage = "Server unreachable: ${t.message}")
            }
        }
    }
}