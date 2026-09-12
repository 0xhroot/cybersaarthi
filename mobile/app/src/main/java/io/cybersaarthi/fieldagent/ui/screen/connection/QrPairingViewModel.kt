package io.cybersaarthi.fieldagent.ui.screen.connection

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.pairing.PairingManager
import kotlinx.coroutines.launch

data class QrUiState(
    val verifying: Boolean = false,
    val paired: Boolean = false,
    val failed: Boolean = false,
    val errorMessage: String? = null
)

class QrPairingViewModel(private val container: AppContainer) : ViewModel() {

    var ui by mutableStateOf(QrUiState())
        private set

    fun parsed(text: String) {
        if (ui.verifying || ui.paired) return
        val payload = PairingManager.parse(text)
        if (payload == null) {
            ui = ui.copy(failed = true, errorMessage = "QR code is not a valid CyberSaarthi pairing code.")
            return
        }
        if (PairingManager.isExpired(payload, System.currentTimeMillis())) {
            ui = ui.copy(failed = true, errorMessage = "This pairing code has expired. Request a new one.")
            return
        }
        val fp = payload.fingerprint
        if (fp.isNullOrBlank()) {
            ui = ui.copy(failed = true, errorMessage = "Pairing code is missing the server fingerprint.")
            return
        }
        verify(payload.serverUrl!!, fp)
    }

    private fun verify(url: String, expectedFingerprint: String) {
        ui = ui.copy(verifying = true, failed = false, errorMessage = null)
        viewModelScope.launch {
            try {
                container.settings.serverUrl = url
                val health = container.api.health()
                val actualFp = PairingManager.computeServerFingerprint(health.service, health.version)
                if (!PairingManager.fingerprintMatches(expectedFingerprint, actualFp)) {
                    ui = ui.copy(
                        verifying = false, failed = true,
                        errorMessage = "Server identity mismatch — possible interception. Aborting."
                    )
                    container.settings.clearTrustedServer()
                    return@launch
                }
                container.settings.trustServer(url, health.service, expectedFingerprint)
                ui = ui.copy(verifying = false, paired = true)
            } catch (t: Throwable) {
                container.settings.clearTrustedServer()
                ui = ui.copy(
                    verifying = false, failed = true,
                    errorMessage = "Could not verify server: ${t.message ?: "unknown error"}"
                )
            }
        }
    }

    fun reset() {
        ui = QrUiState()
    }
}