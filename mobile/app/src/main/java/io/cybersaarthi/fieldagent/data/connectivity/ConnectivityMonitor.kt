package io.cybersaarthi.fieldagent.data.connectivity

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Realtime connectivity signal backed by a [ConnectivityManager] network callback. */
class ConnectivityMonitor(context: Context) {

    private val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val _online = MutableStateFlow(false)
    val online: StateFlow<Boolean> = _online.asStateFlow()

    fun start() {
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                _online.tryEmit(true)
            }

            override fun onLost(network: Network) {
                _online.tryEmit(hasCapableNetwork())
            }

            override fun onUnavailable() {
                _online.tryEmit(hasCapableNetwork())
            }
        }
        // registerDefaultNetworkCallback is available from API 24.
        runCatching { cm.registerDefaultNetworkCallback(callback) }
            .onFailure { _online.value = hasCapableNetwork() }
    }

    fun hasCapableNetwork(): Boolean {
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}