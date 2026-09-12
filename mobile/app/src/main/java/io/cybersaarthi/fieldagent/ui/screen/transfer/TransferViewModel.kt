package io.cybersaarthi.fieldagent.ui.screen.transfer

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

data class TransferUiState(
    val caseId: String = "",
    val collectionId: String = "",
    val collectionName: String = "",
    val deviceSerial: String = DeviceIdentity.serial,
    val status: CollectionStatus = CollectionStatus.CAPTURING,
    val evidenceCount: Int = 0,
    val packageSizeBytes: Long = 0L,
    val manifestSha256: String? = null,
    val busy: Boolean = false,
    val busyTag: String? = null,
    val errorMessage: String? = null,
    val infoMessage: String? = null,
    val lastSubmit: ImportAccepted? = null
) {
    val canTransfer: Boolean
        get() = (status == CollectionStatus.PACKAGED || status == CollectionStatus.SEALED) && !busy
}

class TransferViewModel(
    private val caseId: String,
    private val collectionId: String,
    private val container: AppContainer
) : ViewModel() {

    private val store = container.store
    private val transfer = container.transfer

    var ui by mutableStateOf(
        TransferUiState(
            caseId = caseId,
            collectionId = collectionId,
            collectionName = store.collection(caseId, collectionId)?.name ?: ""
        )
    )
        private set

    init {
        refresh()
    }

    fun refresh() {
        val coll = store.collection(caseId, collectionId)
        val dir = store.collectionDir(caseId, collectionId)
        val manifest = File(dir, "manifest.json")
        ui = ui.copy(
            caseId = caseId,
            collectionId = collectionId,
            collectionName = coll?.name ?: ui.collectionName,
            status = coll?.status ?: CollectionStatus.CAPTURING,
            evidenceCount = store.listEvidence(caseId, collectionId).size,
            packageSizeBytes = packageBytes(store.packageDir(collectionId)),
            manifestSha256 = if (manifest.exists()) io.cybersaarthi.fieldagent.hashing.EvidenceHasher.sha256Hex(manifest.readBytes()) else null
        )
    }

    fun verifyPackage() {
        viewModelScope.launch {
            ui = ui.copy(busy = true, busyTag = "verify", errorMessage = null)
            val ok = withContext(Dispatchers.IO) {
                transfer.verifyPackageSignature(caseId, collectionId)
            }
            ui = ui.copy(
                busy = false, busyTag = null,
                infoMessage = if (ok) "Signature and manifest verified locally." else "Signature verification FAILED."
            )
        }
    }

    fun submit() {
        viewModelScope.launch {
            if (ui.busy) return@launch
            ui = ui.copy(busy = true, busyTag = "submit", errorMessage = null)
            try {
                val accepted = withContext(Dispatchers.IO) {
                    transfer.submitPackage(caseId, collectionId)
                }
                ui = ui.copy(
                    busy = false, busyTag = null,
                    lastSubmit = accepted,
                    infoMessage = "Package accepted: ${accepted.importedEvidenceCount} evidence item(s) importing."
                )
                refresh()
            } catch (t: Throwable) {
                val e = t.toFieldError()
                ui = ui.copy(busy = false, busyTag = null, errorMessage = e.resourceIdMessage())
            }
        }
    }

    fun clearInfo() {
        ui = ui.copy(infoMessage = null)
    }

    private fun packageBytes(pkg: File): Long {
        if (!pkg.exists()) return 0L
        val manifest = File(pkg, "manifest.json")
        val sig = File(pkg, "manifest.sig")
        var total = manifest.length() + sig.length()
        val evDir = File(pkg, "evidence")
        if (evDir.exists()) {
            total += evDir.listFiles()?.sumOf { it.length() } ?: 0L
        }
        return total
    }
}

private fun io.cybersaarthi.fieldagent.data.net.FieldError.resourceIdMessage(): String =
    resourceIdMessageImpl(this)

private fun resourceIdMessageImpl(e: io.cybersaarthi.fieldagent.data.net.FieldError): String = when (e) {
    io.cybersaarthi.fieldagent.data.net.FieldError.Unauthorized -> "Session expired. Sign in again."
    is io.cybersaarthi.fieldagent.data.net.FieldError.DevicePending -> "Device enrollment is pending approval."
    is io.cybersaarthi.fieldagent.data.net.FieldError.DeviceRevoked -> "Device has been revoked."
    io.cybersaarthi.fieldagent.data.net.FieldError.Network -> "Server unreachable."
    io.cybersaarthi.fieldagent.data.net.FieldError.Timeout -> "Server did not respond."
    is io.cybersaarthi.fieldagent.data.net.FieldError.Server -> "Server error (${e.code})."
    is io.cybersaarthi.fieldagent.data.net.FieldError.Validation -> e.detail.ifBlank { "The server rejected the package." }
    else -> "Transfer failed."
}