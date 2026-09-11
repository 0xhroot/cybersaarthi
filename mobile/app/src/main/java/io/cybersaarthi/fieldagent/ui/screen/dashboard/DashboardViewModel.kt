package io.cybersaarthi.fieldagent.ui.screen.dashboard

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.net.CaseOut
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.launch

data class DashboardUiState(
    val loading: Boolean = true,
    val cases: List<CaseOut>? = null,
    val errorRes: Int? = null
)

class DashboardViewModel(private val container: AppContainer) : ViewModel() {

    var ui by mutableStateOf(DashboardUiState())
        private set

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            ui = ui.copy(loading = true, errorRes = null)
            val auth = container.session.current() as? AuthState.Active
            if (auth == null) {
                ui = ui.copy(loading = false, errorRes = null)
                return@launch
            }
            try {
                val cases = container.api.listCases(auth.accessToken)
                ui = ui.copy(loading = false, cases = cases)
            } catch (t: Throwable) {
                ui = ui.copy(loading = false, errorRes = t.toFieldError().resourceId())
            }
        }
    }

    fun openCase(c: CaseOut) {
        container.settings.activeCaseId = c.id
        container.settings.storeCase(c.id, c.caseNumber)
    }
}