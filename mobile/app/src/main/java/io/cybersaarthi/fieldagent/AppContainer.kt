package io.cybersaarthi.fieldagent

import android.content.Context
import io.cybersaarthi.fieldagent.data.auth.SessionManager
import io.cybersaarthi.fieldagent.data.auth.SettingsStore
import io.cybersaarthi.fieldagent.data.connectivity.ConnectivityMonitor
import io.cybersaarthi.fieldagent.data.net.ApiClient
import io.cybersaarthi.fieldagent.data.net.FieldApi
import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.data.store.EvidenceStore
import io.cybersaarthi.fieldagent.data.store.TransferManager
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import java.io.File

/**
 * Hand-rolled dependency container. Small enough that a framework is not
 * warranted and every dependency is explicit and easy to trace.
 */
class AppContainer(context: Context) {

    val settings = SettingsStore(context)
    val session = SessionManager(context)
    val connectivity = ConnectivityMonitor(context)

    private val apiClient = ApiClient(baseUrlProvider = { settings.serverUrl })
    val api = FieldApi(apiClient)

    val evidenceRoot = File(context.filesDir, "evidence")
    val store = EvidenceStore(evidenceRoot)

    val transfer: TransferManager = TransferManager(
        store = store,
        deviceSerial = { DeviceIdentity.serial },
        sign = { DeviceIdentity.sign(it) },
        submit = submitPackageForImport()
    )

    private fun submitPackageForImport():
        suspend (String, ByteArray, List<Pair<String, File>>) -> ImportAccepted = { manifest, signature, files ->
        val auth = session.current() as? io.cybersaarthi.fieldagent.data.auth.AuthState.Active
            ?: throw io.cybersaarthi.fieldagent.data.net.FieldError.Unauthorized
        val caseId = settings.activeCaseId
            ?: throw IllegalStateException("No active case selected.")
        api.importPackage(auth.accessToken, caseId, manifest, signature, files)
    }
}