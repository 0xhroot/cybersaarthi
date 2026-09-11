package io.cybersaarthi.fieldagent.ui.screen.case_detail

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.net.CaseOut
import io.cybersaarthi.fieldagent.data.net.CollectionOut
import io.cybersaarthi.fieldagent.data.net.EvidenceSummary
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.launch

data class CaseDetailUiState(
    val caseDetail: CaseOut? = null,
    val collections: List<CollectionOut>? = null,
    val remoteEvidence: List<EvidenceSummary>? = null,
    val loading: Boolean = true,
    val creating: Boolean = false,
    val errorRes: Int? = null
)

class CaseDetailViewModel(
    private val caseId: String,
    private val container: AppContainer
) : ViewModel() {

    var ui by mutableStateOf(CaseDetailUiState())
        private set

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            ui = ui.copy(loading = true, errorRes = null)
            val auth = container.session.current() as? AuthState.Active
            if (auth == null) {
                ui = ui.copy(loading = false)
                return@launch
            }
            try {
                val detail = container.api.getCase(auth.accessToken, caseId)
                val collections = container.api.listCollections(auth.accessToken, caseId)
                val remote = container.api.listEvidence(auth.accessToken, caseId)
                ui = ui.copy(
                    caseDetail = detail,
                    collections = collections,
                    remoteEvidence = remote,
                    loading = false
                )
            } catch (t: Throwable) {
                ui = ui.copy(loading = false, errorRes = t.toFieldError().resourceId())
            }
        }
    }

    fun localStatusFor(remote: CollectionOut): CollectionStatus? =
        container.store.collection(caseId, remote.id)?.status

    fun createCollection(name: String, onCreated: (CollectionOut) -> Unit) {
        val trimmed = name.trim()
        if (trimmed.isBlank()) return
        viewModelScope.launch {
            ui = ui.copy(creating = true, errorRes = null)
            try {
                val auth = container.session.current() as? AuthState.Active
                    ?: throw IllegalStateException("Not signed in")
                val remote = container.api.createCollection(auth.accessToken, caseId, trimmed)
                container.store.initCollection(caseId, remote.id, remote.name)
                ui = ui.copy(creating = false, collections = (ui.collections ?: emptyList()) + remote)
                onCreated(remote)
            } catch (t: Throwable) {
                ui = ui.copy(creating = false, errorRes = t.toFieldError().resourceId())
            }
        }
    }
}