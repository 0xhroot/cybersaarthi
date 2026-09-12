package io.cybersaarthi.fieldagent.ui.screen.connection

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Lan
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.di.containerViewModel

data class LanService(val name: String, val host: String?, val port: Int)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LanDiscoveryScreen(
    onConnect: (String) -> Unit,
    onBack: () -> Unit,
    onManual: () -> Unit
) {
    val context = LocalContext.current
    val services = remember { mutableStateListOf<LanService>() }
    var scanning by remember { mutableStateOf(true) }
    var chosen by remember { mutableStateOf<LanService?>(null) }

    val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    val resolveListener = remember {
        object : NsdManager.ResolveListener {
            override fun onResolveFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {}
            override fun onServiceResolved(info: NsdServiceInfo) {
                val host = info.host?.hostAddress
                val port = info.port
                val idx = services.indexOfFirst { it.name == info.serviceName }
                if (idx >= 0 && host != null) {
                    services[idx] = LanService(info.serviceName, host, port)
                }
            }
        }
    }
    val discoveryListener = remember {
        object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String?) {}
            override fun onServiceFound(info: NsdServiceInfo) {
                services.add(LanService(info.serviceName, null, info.port))
                runCatching { nsdManager.resolveService(info, resolveListener) }
            }
            override fun onServiceLost(info: NsdServiceInfo) { services.removeAll { it.name == info.serviceName } }
            override fun onDiscoveryStopped(serviceType: String?) { scanning = false }
            override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) { scanning = false }
            override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {}
        }
    }

    DisposableEffect(Unit) {
        scanning = true
        try {
            nsdManager.discoverServices("_cybersaarthi._tcp", NsdManager.PROTOCOL_DNS_SD, discoveryListener)
        } catch (_: Exception) { scanning = false }
        onDispose { runCatching { nsdManager.stopServiceDiscovery(discoveryListener) } }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.lan_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                }
            )
        }
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (scanning) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Text(stringResource(R.string.lan_scanning), Modifier.padding(start = 8.dp))
                }
            } else if (services.isEmpty()) {
                Text(stringResource(R.string.lan_none_found))
                OutlinedButton(onClick = onManual, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.lan_enter_manually))
                }
            }
            LazyColumn(Modifier.weight(1f)) {
                items(services, key = { it.name }) { svc ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp)
                            .clickable { chosen = svc },
                        colors = if (chosen == svc) CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                        else CardDefaults.cardColors()
                    ) {
                        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.Lan, null, Modifier.size(24.dp), tint = MaterialTheme.colorScheme.primary)
                            Column(Modifier.padding(start = 12.dp).weight(1f)) {
                                Text(svc.name, style = MaterialTheme.typography.titleSmall)
                                svc.host?.let {
                                    Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
            if (chosen != null) {
                Button(
                    onClick = { chosen?.host?.let { onConnect("http://$it:${chosen!!.port}/api/v1") } },
                    enabled = chosen?.host != null,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(stringResource(R.string.lan_connect, chosen!!.name))
                }
            }
            if (!scanning) {
                OutlinedButton(
                    onClick = { scanning = true; try { nsdManager.discoverServices("_cybersaarthi._tcp", NsdManager.PROTOCOL_DNS_SD, discoveryListener) } catch (_: Exception) { scanning = false } },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(Icons.Filled.Refresh, null, Modifier.size(18.dp))
                    Text(stringResource(R.string.lan_retry), Modifier.padding(start = 8.dp))
                }
            }
        }
    }
}