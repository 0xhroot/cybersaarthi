package io.cybersaarthi.fieldagent

import android.content.Context
import io.cybersaarthi.fieldagent.data.auth.SessionManager
import io.cybersaarthi.fieldagent.data.cache.CaseCache
import io.cybersaarthi.fieldagent.data.config.SettingsStore
import io.cybersaarthi.fieldagent.data.connectivity.ConnectivityMonitor
import io.cybersaarthi.fieldagent.data.connectivity.ConnectionManager
import io.cybersaarthi.fieldagent.data.connectivity.HeartbeatManager
import io.cybersaarthi.fieldagent.data.net.ApiClient
import io.cybersaarthi.fieldagent.data.net.FieldApi
import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.data.offline.OfflineUnlock
import io.cybersaarthi.fieldagent.data.store.EvidenceStore
import io.cybersaarthi.fieldagent.data.store.TransferManager
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import io.cybersaarthi.fieldagent.domain.SensorRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.io.File

/**
 * Hand-rolled dependency container. Small enough that a framework is not
 * warranted and every dependency is explicit and easy to trace.
 */
class AppContainer(context: Context) {

    /** Application-scoped background scope for the connection probe loop. */
    val coreScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val settings = SettingsStore(context, BuildConfig.DEFAULT_SERVER_URL)
    val session = SessionManager(context)
    val connectivity = ConnectivityMonitor(context)

    private val apiClient = ApiClient(baseUrlProvider = { settings.serverUrl })
    val api = FieldApi(apiClient)

    val connection = ConnectionManager(
        api = api,
        settings = settings,
        session = session,
        connectivity = connectivity
    )

    val heartbeat = HeartbeatManager(
        api = api,
        settings = settings,
        session = session,
        connection = connection,
        scope = coreScope
    )

    val evidenceRoot = File(context.filesDir, "evidence")
    val store = EvidenceStore(evidenceRoot)

    val caseCache = CaseCache(File(context.filesDir, "casecache/cases.json"))

    val offlineUnlock = OfflineUnlock(context)

    val sensors = SensorRegistry(context)

    val transfer: TransferManager = TransferManager(
        store = store,
        deviceSerial = { DeviceIdentity.serial },
        sign = { DeviceIdentity.sign(it) },
        submit = submitPackageForImport()
    )

    /** Starts periodic server health probing and reacts to network changes. */
    fun startConnectionProbing() {
        coreScope.launch {
            connectivity.online.collectLatest { online ->
                if (online) connection.probe()
            }
        }
        coreScope.launch {
            while (true) {
                delay(30_000)
                connection.probe()
            }
        }
    }

    private fun submitPackageForImport():
        suspend (String, ByteArray, List<Pair<String, File>>) -> ImportAccepted = { manifest, signature, files ->
        val auth = session.current() as? io.cybersaarthi.fieldagent.data.auth.AuthState.Active
            ?: throw io.cybersaarthi.fieldagent.data.net.FieldError.Unauthorized
        val caseId = settings.activeCaseId
            ?: throw IllegalStateException("No active case selected.")
        api.importPackage(auth.accessToken, caseId, manifest, signature, files)
    }
}