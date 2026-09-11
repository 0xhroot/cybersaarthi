package io.cybersaarthi.fieldagent.ui.screen.collection

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.data.store.EvidenceKind
import io.cybersaarthi.fieldagent.data.store.LocalEvidence
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.time.Instant

data class CollectionUiState(
    val collectionName: String = "",
    val status: CollectionStatus = CollectionStatus.CAPTURING,
    val evidence: List<LocalEvidence> = emptyList(),
    val loading: Boolean = true,
    val busy: Boolean = false,
    val actionBusy: String? = null,
    val errorRes: Int? = null,
    val messageRes: Int? = null,
    val deviceApproved: Boolean? = null,
    val lastSubmit: ImportAccepted? = null,
) {
    val canHash: Boolean get() = status == CollectionStatus.CAPTURING && evidence.isNotEmpty()
    val canSeal: Boolean get() = status == CollectionStatus.HASHED && !busy
    val canPackage: Boolean get() = status == CollectionStatus.SEALED && !busy
    val canSubmit: Boolean get() =
        (status == CollectionStatus.PACKAGED || status == CollectionStatus.SEALED) && !busy
    val canCapture: Boolean get() = status == CollectionStatus.CAPTURING && !busy
}

class CollectionViewModel(
    private val caseId: String,
    private val collectionId: String,
    private val container: AppContainer
) : ViewModel() {

    private val store = container.store
    private val transfer = container.transfer

    var ui by mutableStateOf(CollectionUiState())
        private set

    fun start(collectionName: String) {
        store.initCollection(caseId, collectionId, collectionName)
        refresh()
        checkDevice()
    }

    fun refresh() {
        val coll = store.collection(caseId, collectionId)
        ui = ui.copy(
            collectionName = coll?.name ?: ui.collectionName,
            status = coll?.status ?: CollectionStatus.CAPTURING,
            evidence = store.listEvidence(caseId, collectionId),
            loading = false
        )
    }

    fun clearMessage() {
        ui = ui.copy(messageRes = null)
    }

    fun checkDevice() {
        viewModelScope.launch {
            val auth = container.session.current() as? AuthState.Active ?: return@launch
            runCatching {
                val devices = container.api.listDevices(auth.accessToken, caseId)
                devices.firstOrNull { it.serial == DeviceIdentity.serial }?.status
            }.onSuccess { status ->
                ui = ui.copy(deviceApproved = status == "approved")
                if (status == "revoked") {
                    ui = ui.copy(errorRes = io.cybersaarthi.fieldagent.R.string.err_device_revoked)
                }
            }
        }
    }

    // ---- capture --------------------------------------------------------------------------

    private suspend fun captureContext(): Pair<String?, String> {
        val auth = container.session.current() as? AuthState.Active
        return (auth?.userId to DeviceIdentity.serial)
    }

    fun writePhoto(bytes: ByteArray) = writeBlock("photo") {
        val (by, serial) = captureContext()
        store.writeEvidence(
            caseId, collectionId, EvidenceKind.PHOTO,
            bytes,
            originalName = "IMG_${Instant.now().toEpochMilli()}.jpg",
            mimeType = "image/jpeg",
            capturedAt = Instant.now().toString(),
            capturedBy = by, deviceSerial = serial
        )
    }

    fun writeCapturedMedia(
        kind: EvidenceKind,
        source: File,
        originalName: String,
        mimeType: String
    ) = writeBlock(kind.code) {
        val (by, serial) = captureContext()
        store.writeEvidenceFromFile(
            caseId, collectionId, kind, source, originalName,
            mimeType, Instant.now().toString(), by, serial
        )
    }

    fun writeNote(text: String) = writeBlock("note") {
        val (by, serial) = captureContext()
        store.writeEvidence(
            caseId, collectionId, EvidenceKind.NOTE,
            text.trim().toByteArray(),
            originalName = "note_${Instant.now().toEpochMilli()}.txt",
            mimeType = "text/plain",
            capturedAt = Instant.now().toString(),
            capturedBy = by, deviceSerial = serial,
            note = text.trim()
        )
    }

    fun writeAudio(source: File, originalName: String, mimeType: String) = writeBlock("audio") {
        val (by, serial) = captureContext()
        store.writeEvidenceFromFile(
            caseId, collectionId, EvidenceKind.AUDIO, source, originalName,
            mimeType, Instant.now().toString(), by, serial
        )
    }

    fun writeVideo(source: File, originalName: String, mimeType: String) = writeBlock("video") {
        val (by, serial) = captureContext()
        store.writeEvidenceFromFile(
            caseId, collectionId, EvidenceKind.VIDEO, source, originalName,
            mimeType, Instant.now().toString(), by, serial
        )
    }

    fun writeDocument(source: File, originalName: String, mimeType: String) = writeBlock("document") {
        val (by, serial) = captureContext()
        store.writeEvidenceFromFile(
            caseId, collectionId, EvidenceKind.DOCUMENT, source, originalName,
            mimeType, Instant.now().toString(), by, serial
        )
    }

    fun writeLocation(lat: Double, lon: Double, accuracyMeters: Double, provider: String) {
        writeBlock("location") {
            val (by, serial) = captureContext()
            val stamp = Instant.now().toString()
            val payload = JSONObject().apply {
                put("lat", lat)
                put("lon", lon)
                put("accuracy_m", accuracyMeters)
                put("provider", provider)
                put("timestamp", stamp)
            }
            store.writeEvidence(
                caseId, collectionId, EvidenceKind.LOCATION,
                payload.toString().toByteArray(),
                originalName = "location_${Instant.now().toEpochMilli()}.json",
                mimeType = "application/geo+json",
                capturedAt = stamp,
                capturedBy = by, deviceSerial = serial,
                extra = payload
            )
        }
    }

    fun deleteEvidence(ev: LocalEvidence) {
        store.deleteEvidence(caseId, collectionId, ev)
        refresh()
    }

    // ---- integrity pipeline ---------------------------------------------------------------

    fun hashAll() = action("hash") {
        val result = withContext(Dispatchers.IO) {
            transfer.hashAll(caseId, collectionId)
        }
        if (result.mismatches.isEmpty()) {
            ui = ui.copy(messageRes = R.string.col_digest_ok)
        } else {
            ui = ui.copy(messageRes = R.string.col_digest_mismatch)
        }
    }

    fun seal() = action("seal") {
        val coll = store.collection(caseId, collectionId) ?: throw IllegalStateException("missing")
        require(coll.status == CollectionStatus.HASHED) { "tr_not_hashed" }
        withContext(Dispatchers.IO) {
            transfer.seal(caseId, collectionId, coll.name)
        }
    }

    fun packageCollection() = action("package") {
        val coll = store.collection(caseId, collectionId) ?: throw IllegalStateException("missing")
        require(coll.status == CollectionStatus.SEALED) { "tr_not_sealed" }
        withContext(Dispatchers.IO) {
            transfer.packageDir(caseId, collectionId)
        }
    }

    fun verifySignature() = action("verify") {
        val ok = withContext(Dispatchers.IO) {
            transfer.verifyPackageSignature(caseId, collectionId)
        }
        ui = ui.copy(
            messageRes = if (ok) R.string.col_manifest_sig_ok else R.string.col_manifest_sig_bad
        )
    }

    fun submit() = action("submit") {
        val coll = store.collection(caseId, collectionId) ?: throw IllegalStateException("missing")
        require(coll.status == CollectionStatus.SEALED || coll.status == CollectionStatus.PACKAGED) {
            "tr_not_packaged"
        }
        val accepted = withContext(Dispatchers.IO) {
            transfer.submitPackage(caseId, collectionId)
        }
        ui = ui.copy(lastSubmit = accepted, messageRes = R.string.tr_submit_ok)
    }

    fun exportTo(targetDir: File) = action("export") {
        val count = withContext(Dispatchers.IO) {
            transfer.exportPackage(caseId, collectionId, targetDir)
        }
        ui = ui.copy(messageRes = R.string.tr_export_ok)
    }

    // ---------------------------------------------------------------------------------------

    private inline fun action(tag: String, crossinline block: suspend () -> Unit) {
        viewModelScope.launch {
            if (ui.busy) return@launch
            ui = ui.copy(busy = true, actionBusy = tag, errorRes = null)
            try {
                block()
            } catch (e: IllegalStateException) {
                ui = ui.copy(messageRes = messageIdFor(e.message))
            } catch (t: Throwable) {
                ui = ui.copy(errorRes = t.toFieldError().resourceId())
            } finally {
                refresh()
                ui = ui.copy(busy = false, actionBusy = null)
            }
        }
    }

    private inline fun writeBlock(tag: String, crossinline block: suspend () -> Unit) {
        action(tag) {
            withContext(Dispatchers.IO) { block() }
        }
    }

    private fun messageIdFor(tag: String?): Int = when (tag) {
        "tr_not_hashed" -> io.cybersaarthi.fieldagent.R.string.tr_not_hashed
        "tr_not_sealed" -> io.cybersaarthi.fieldagent.R.string.tr_not_sealed
        "tr_not_packaged" -> io.cybersaarthi.fieldagent.R.string.tr_not_packaged
        else -> io.cybersaarthi.fieldagent.R.string.common_error
    }
}