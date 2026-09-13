package io.cybersaarthi.fieldagent.ui.screen.field

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
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.cache.CachedCase
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.ui.components.ConnectionStatusChip

/** Offline field hub: local unlock gate + cached authorized cases + field entry. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FieldModeScreen(
    onOpenCase: (CachedCase) -> Unit,
    onSwitchOnline: () -> Unit,
    onBack: () -> Unit
) {
    val container = LocalAppContainer.current
    val unlocked by container.offlineUnlock.unlocked.collectAsStateWithLifecycle()
    var passphrase by rememberSaveable { mutableStateOf("") }
    var unlockError by remember { mutableStateOf(false) }

    var cases by remember { mutableStateOf(container.caseCache.all()) }

    LaunchedEffect(Unit) { cases = container.caseCache.all() }
    LaunchedEffect(unlocked) {
        if (unlocked) unlockError = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.field_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                }
            )
        }
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
            if (unlocked) {
                ConnectionStatusChip(io.cybersaarthi.fieldagent.data.connectivity.ConnectionStatus.OFFLINE)
                Spacer(Modifier.height(12.dp))
                if (cases.isEmpty()) {
                    Text(
                        stringResource(R.string.field_no_cached_cases),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = onSwitchOnline, modifier = Modifier.fillMaxWidth()) {
                        Icon(Icons.Filled.Wifi, null, Modifier.size(18.dp))
                        Text(stringResource(R.string.field_connect_online), Modifier.padding(start = 8.dp))
                    }
                } else {
                    Text(
                        stringResource(R.string.field_cached_title),
                        style = MaterialTheme.typography.titleSmall
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = onSwitchOnline, modifier = Modifier.fillMaxWidth()) {
                        Icon(Icons.Filled.Wifi, null, Modifier.size(18.dp))
                        Text(stringResource(R.string.field_connect_online), Modifier.padding(start = 8.dp))
                    }
                    Spacer(Modifier.height(4.dp))
                    LazyColumn(Modifier.fillMaxWidth().weight(1f)) {
                        items(cases, key = { it.id }) { c ->
                            Card(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).clickable { onOpenCase(c) },
                                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                            ) {
                                Column(Modifier.padding(16.dp)) {
                                    Text(c.caseNumber, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                                    Text(c.title, style = MaterialTheme.typography.titleSmall)
                                    Text(
                                        stringResource(R.string.field_cached_at, formatCached(c.cachedAtEpochMillis)),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }
                }
            } else {
                Column(
                    Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(Icons.Filled.Lock, null, Modifier.size(40.dp), tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.height(8.dp))
                    Text(stringResource(R.string.field_unlock_title), style = MaterialTheme.typography.titleMedium)
                    Text(
                        stringResource(R.string.field_unlock_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 4.dp)
                    )
                    OutlinedTextField(
                        value = passphrase,
                        onValueChange = { passphrase = it },
                        label = { Text(stringResource(R.string.field_passphrase)) },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (unlockError) {
                        Text(
                            stringResource(R.string.field_unlock_invalid),
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Button(
                        onClick = {
                            if (!container.offlineUnlock.unlock(passphrase)) unlockError = true
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(Icons.Filled.LockOpen, null, Modifier.size(18.dp))
                        Text(stringResource(R.string.field_unlock_button), Modifier.padding(start = 8.dp))
                    }
                    TextButton(onClick = onSwitchOnline) {
                        Text(stringResource(R.string.field_switch_online))
                    }
                }
            }
        }
    }
}

private fun formatCached(epochMillis: Long): String =
    runCatching {
        java.time.Instant.ofEpochMilli(epochMillis)
            .atZone(java.time.ZoneId.systemDefault())
            .toLocalDateTime()
            .toString().replace("T", " ").take(16)
    }.getOrDefault("recently")