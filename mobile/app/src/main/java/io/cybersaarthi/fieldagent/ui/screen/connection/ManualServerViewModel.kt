package io.cybersaarthi.fieldagent.ui.screen.connection

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.pairing.PairingManager
import kotlinx.coroutines.launch

data class ManualServerUiState(
    val url: String = "",
    val testing: Boolean = false,
    val saved: Boolean = false,
    val hostname: String? = null,
    val serverInfo: String? = null,
    val errorMessage: String? = null
)

class ManualServerViewModel(private val container: AppContainer) : ViewModel() {

    var ui by mutableStateOf(
        ManualServerUiState(url = container.settings.serverUrl)
    )
        private set

    fun updateUrl(url: String) {
        ui = ui.copy(url = url, errorMessage = null)
    }

    fun testConnection() {
        val raw = ui.url.trim()
        if (raw.isBlank()) {
            ui = ui.copy(errorMessage = "Enter a server address.")
            return
        }
        val normalised = raw.trimEnd('/').let { base ->
            if (base.endsWith("/api/v1")) base else "$base/api/v1"
        }
        ui = ui.copy(testing = true, errorMessage = null, hostname = null, serverInfo = null)
        viewModelScope.launch {
            try {
                container.settings.serverUrl = normalised
                val health = container.api.health()
                ui = ui.copy(
                    testing = false,
                    hostname = health.service,
                    serverInfo = "${health.service ?: "Server"} v${health.version ?: "?"}",
                    url = normalised
                )
            } catch (t: Throwable) {
                container.settings.clearTrustedServer()
                ui = ui.copy(
                    testing = false,
                    errorMessage = "Server unreachable: ${t.message ?: "unknown error"}"
                )
            }
        }
    }

    fun save() {
        val raw = ui.url.trim()
        if (raw.isBlank()) return
        val url = raw.trimEnd('/').let { if (it.endsWith("/api/v1")) it else "$it/api/v1" }
        viewModelScope.launch {
            val fp = ui.hostname?.let {
                runCatching {
                    val health = container.api.health()
                    PairingManager.computeServerFingerprint(health.service, health.version)
                }.getOrNull()
            }
            container.settings.trustServer(url, ui.hostname, fp)
            container.connection.probe()
            ui = ui.copy(saved = true)
        }
    }
}