package io.cybersaarthi.fieldagent.ui.screen.auth

import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.net.CaseOut
import io.cybersaarthi.fieldagent.data.net.DeviceOut
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.launch

data class EnrollUiState(
    val cases: List<CaseOut> = emptyList(),
    val activeCaseId: String? = null,
    val device: DeviceOut? = null,
    val loading: Boolean = true,
    val registering: Boolean = false,
    val errorRes: Int? = null
) {
    val approved: Boolean get() = device?.status == "approved"
    val isRegistered: Boolean get() = device != null
}

class EnrollViewModel(private val container: AppContainer) : ViewModel() {

    var ui by mutableStateOf(EnrollUiState())
        private set

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    private suspend fun load() {
        ui = ui.copy(loading = true, errorRes = null, device = ui.device)
        val auth = container.session.current() as? AuthState.Active
        if (auth == null) {
            ui = ui.copy(loading = false)
            return
        }
        try {
            val cases = container.api.listCases(auth.accessToken)
            var active = ui.activeCaseId ?: container.settings.activeCaseId
            if (active == null || cases.none { it.id == active }) {
                active = cases.firstOrNull()?.id
            }
            if (active != null) container.settings.activeCaseId = active
            ui = ui.copy(cases = cases, activeCaseId = active, loading = false)
            if (active != null) loadDevice(auth, active)
        } catch (t: Throwable) {
            ui = ui.copy(loading = false, errorRes = t.toFieldError().resourceId())
        }
    }

    private suspend fun loadDevice(auth: AuthState.Active, caseId: String) {
        try {
            val devices = container.api.listDevices(auth.accessToken, caseId)
            val mine = devices.firstOrNull { it.serial == DeviceIdentity.serial }
            container.settings.deviceId = mine?.id
            ui = ui.copy(device = mine)
        } catch (t: Throwable) {
            ui = ui.copy(errorRes = t.toFieldError().resourceId())
        }
    }

    fun selectCase(caseId: String) {
        container.settings.activeCaseId = caseId
        ui = ui.copy(activeCaseId = caseId, device = null)
        viewModelScope.launch {
            val auth = container.session.current() as? AuthState.Active ?: return@launch
            loadDevice(auth, caseId)
        }
    }

    fun register() {
        val caseId = ui.activeCaseId ?: return
        viewModelScope.launch {
            ui = ui.copy(registering = true, errorRes = null)
            try {
                val auth = container.session.current() as? AuthState.Active
                    ?: throw IllegalStateException("Not signed in")
                val device = container.api.registerDevice(
                    token = auth.accessToken,
                    caseId = caseId,
                    platform = "android_mobile",
                    serial = DeviceIdentity.serial,
                    model = "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
                    publicKeyPem = DeviceIdentity.publicKeyPem()
                )
                container.settings.deviceId = device.id
                ui = ui.copy(registering = false, device = device)
            } catch (t: Throwable) {
                ui = ui.copy(registering = false, errorRes = t.toFieldError().resourceId())
            }
        }
    }
}