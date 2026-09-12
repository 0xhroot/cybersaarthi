package io.cybersaarthi.fieldagent.data.config

import android.annotation.SuppressLint
import android.content.Context

/**
 * Synchronous (SharedPreferences-backed) settings + trust store.
 *
 * The app never waits on a recorded value — connection mode, server selection,
 * onboarding and case selection are all read/written directly, so this store is
 * deliberately non-suspending. The network layer polls a health endpoint and
 * this store simply records what it finds.
 */
@SuppressLint("ApplySharedPref")
class SettingsStore(context: Context, private val defaultServerUrl: String) {

    private val prefs =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, defaultServerUrl) ?: defaultServerUrl
        set(value) {
            prefs.edit().putString(KEY_SERVER_URL, value).apply()
        }

    val serverHostname: String?
        get() = prefs.getString(KEY_SERVER_HOSTNAME, null)

    val serverFingerprint: String?
        get() = prefs.getString(KEY_SERVER_FINGERPRINT, null)

    var connectionMode: ConnectionMode
        get() = prefs.getString(KEY_CONNECTION_MODE, null)
            ?.let { runCatching { ConnectionMode.valueOf(it) }.getOrNull() }
            ?: ConnectionMode.OFFLINE
        set(value) {
            prefs.edit().putString(KEY_CONNECTION_MODE, value.name).apply()
        }

    var onboarded: Boolean
        get() = prefs.getBoolean(KEY_ONBOARDED, false)
        set(value) {
            prefs.edit().putBoolean(KEY_ONBOARDED, value).apply()
        }

    var activeCaseId: String?
        get() = prefs.getString(KEY_ACTIVE_CASE_ID, null)
        set(value) {
            prefs.edit()
                .putString(KEY_ACTIVE_CASE_ID, value)
                .apply()
        }

    /** The case-level device record registered for this agent, or null. */
    var deviceId: String?
        get() = prefs.getString(KEY_DEVICE_ID, null)
        set(value) {
            prefs.edit()
                .putString(KEY_DEVICE_ID, value)
                .apply()
        }

    /** Epoch millis of the last successfully acknowledged liveness beacon. */
    var lastSeenAtEpochMillis: Long
        get() = prefs.getLong(KEY_LAST_SEEN_AT, 0L)
        set(value) {
            prefs.edit()
                .putLong(KEY_LAST_SEEN_AT, value)
                .apply()
        }

    /** Records a trusted server and switches the agent to [ConnectionMode.ONLINE]. */
    fun trustServer(url: String, hostLabel: String?, fingerprint: String?) {
        prefs.edit()
            .putString(KEY_SERVER_URL, url)
            .putString(KEY_SERVER_HOSTNAME, hostLabel)
            .putString(KEY_SERVER_FINGERPRINT, fingerprint)
            .putString(KEY_CONNECTION_MODE, ConnectionMode.ONLINE.name)
            .apply()
    }

    /** The server the operator has (recently) trusted, or null when none. */
    fun trustedServer(): TrustedServer? {
        val fp = prefs.getString(KEY_SERVER_FINGERPRINT, null) ?: return null
        return TrustedServer(
            hostLabel = prefs.getString(KEY_SERVER_HOSTNAME, null),
            hostname = serverUrl
        )
    }

    fun clearTrustServer() {
        prefs.edit()
            .remove(KEY_SERVER_URL)
            .remove(KEY_SERVER_HOSTNAME)
            .remove(KEY_SERVER_FINGERPRINT)
            .putString(KEY_CONNECTION_MODE, ConnectionMode.OFFLINE.name)
            .apply()
    }

    fun clearTrustedServer() = clearTrustServer()

    private companion object {
        const val PREFS_NAME = "io.cybersaarthi.fieldagent.config"
        const val KEY_SERVER_URL = "key.server_url"
        const val KEY_SERVER_HOSTNAME = "key.server_hostname"
        const val KEY_SERVER_FINGERPRINT = "key.server_fingerprint"
        const val KEY_CONNECTION_MODE = "key.connection_mode"
        const val KEY_ONBOARDED = "key.onboarded"
        const val KEY_ACTIVE_CASE_ID = "key.active_case_id"
        const val KEY_DEVICE_ID = "key.device_id"
        const val KEY_LAST_SEEN_AT = "key.last_seen_at"
    }
}
