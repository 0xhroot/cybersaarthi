package io.cybersaarthi.fieldagent.ui.screen.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.config.ConnectionMode
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.launch

data class LoginUiState(
    val serverConfigured: Boolean = false,
    val serverHost: String = "",
    val serverInfo: String? = null,
    val busy: Boolean = false,
    val signedIn: Boolean = false,
    val errorRes: Int? = null,
    val deviceSerial: String = DeviceIdentity.serial,
    val loggingIn: Boolean = false
)

class LoginViewModel(private val container: AppContainer) : ViewModel() {

    private val settings = container.settings

    var ui by mutableStateOf(
        LoginUiState(
            serverConfigured = settings.serverUrl.isNotBlank(),
            serverHost = settings.trustedServer()?.hostLabel ?: settings.serverUrl,
            serverInfo = settings.trustedServer()?.hostname
        )
    )
        private set

    val connectionStatus = container.connection.status

    fun login(username: String, password: String) {
        if (username.isBlank() || password.isBlank()) {
            ui = ui.copy(errorRes = io.cybersaarthi.fieldagent.R.string.auth_credentials_required)
            return
        }
        if (!settings.serverUrl.isBlank()) {
            ui = ui.copy(serverConfigured = true)
        }
        ui = ui.copy(busy = true, errorRes = null)
        viewModelScope.launch {
            try {
                val token = container.api.login(username.trim(), password)
                container.session.save(
                    token.accessToken, token.expiresIn, token.user.id,
                    token.user.username, token.user.email, token.user.status
                )
                container.settings.connectionMode = ConnectionMode.ONLINE
                ui = ui.copy(busy = false, signedIn = true)
            } catch (t: Throwable) {
                ui = ui.copy(busy = false, errorRes = t.toFieldError().resourceId())
            }
        }
    }

    fun clearError() {
        ui = ui.copy(errorRes = null)
    }

    /** Migrates or re-applies a newly configured server address. */
    fun applyServer(url: String) {
        settings.serverUrl = url
        settings.trustServer(url, settings.serverHostname, settings.serverFingerprint)
        ui = ui.copy(
            serverConfigured = url.isNotBlank(),
            serverHost = settings.trustedServer()?.hostLabel ?: url,
            serverInfo = settings.trustedServer()?.hostname
        )
    }

    fun workOffline() {
        settings.connectionMode = ConnectionMode.OFFLINE
        settings.onboarded = true
        container.connection.notifySessionCleared()
    }
}