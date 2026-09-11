package io.cybersaarthi.fieldagent.ui.screen.profile

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.domain.DeviceIdentity

data class ProfileUiState(
    val username: String = "",
    val email: String? = null,
    val status: String = "",
    val serial: String = "",
    val fingerprint: String = ""
)

class ProfileViewModel(private val container: AppContainer) : ViewModel() {

    var ui by mutableStateOf(ProfileUiState())
        private set

    init {
        val auth = container.session.current() as? AuthState.Active
        ui = ProfileUiState(
            username = auth?.username ?: "",
            email = auth?.userEmail,
            status = auth?.userStatus ?: "",
            serial = DeviceIdentity.serial,
            fingerprint = DeviceIdentity.keyFingerprint
        )
    }

    fun signOut() {
        container.session.clear()
        container.settings.activeCaseId = null
    }
}