package io.cybersaarthi.fieldagent.ui.screen.profile

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.connectivity.ConnectionStatus
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import io.cybersaarthi.fieldagent.ui.components.ConnectionStatusChip
import io.cybersaarthi.fieldagent.ui.components.InfoCard
import io.cybersaarthi.fieldagent.ui.components.SectionHeader

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(
    onBack: () -> Unit,
    onSignedOut: () -> Unit
) {
    val vm = containerViewModel<ProfileViewModel> { ProfileViewModel(it) }
    val ui = vm.ui
    val container = LocalAppContainer.current
    val status by container.connection.status.collectAsStateWithLifecycle()
    var showSetPassphrase by rememberSaveable { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.pr_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                },
                actions = {
                    IconButton(onClick = vm::refreshConnection) {
                        Icon(Icons.Filled.Refresh, stringResource(R.string.common_refresh))
                    }
                }
            )
        }
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(horizontal = 8.dp)
                .verticalScroll(rememberScrollState())
        ) {
            ConnectionStatusChip(status, Modifier.padding(vertical = 8.dp, horizontal = 8.dp))
            SectionHeader(stringResource(R.string.pr_account))
            InfoCard(stringResource(R.string.pr_user, ui.username, ui.status), ui.email)

            SectionHeader(stringResource(R.string.pr_server))
            InfoCard(ui.serverHost.ifBlank { stringResource(R.string.auth_no_server) }, ui.serverUrl)

            SectionHeader(stringResource(R.string.enroll_my_device))
            InfoCard(stringResource(R.string.enroll_device_serial), ui.serial)
            InfoCard(
                stringResource(R.string.enroll_device_key),
                ui.fingerprint.chunked(8).joinToString(" ")
            )

            SectionHeader(stringResource(R.string.pr_offline))
            InfoCard(
                if (ui.unlockEnabled) stringResource(R.string.pr_unlock_enabled)
                else stringResource(R.string.pr_unlock_disabled),
                stringResource(R.string.pr_unlock_desc)
            )
            if (ui.unlockEnabled) {
                OutlinedButton(
                    onClick = { vm.lockOffline() },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                ) {
                    Icon(Icons.Filled.Lock, null, Modifier.size(18.dp))
                    Text(stringResource(R.string.pr_lock_now), Modifier.padding(start = 8.dp))
                }
                TextButton(
                    onClick = { vm.clearUnlockPassphrase() },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(stringResource(R.string.pr_remove_passphrase))
                }
            } else {
                OutlinedButton(
                    onClick = { showSetPassphrase = true },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                ) {
                    Text(stringResource(R.string.pr_set_passphrase))
                }
            }
            ui.unlockMessage?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
            }

            Spacer(Modifier.height(24.dp))
            OutlinedButton(
                onClick = {
                    vm.signOut()
                    onSignedOut()
                },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = MaterialTheme.colorScheme.error
                )
            ) {
                Icon(Icons.Filled.ExitToApp, null, Modifier.height(18.dp))
                Text(stringResource(R.string.pr_sign_out), modifier = Modifier.padding(start = 8.dp))
            }
            Text(
                stringResource(R.string.pr_about),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp),
                textAlign = TextAlign.Center
            )
        }
    }

    if (showSetPassphrase) {
        SetPassphraseDialog(
            onDismiss = { showSetPassphrase = false },
            onSave = { pass ->
                vm.setUnlockPassphrase(pass)
                showSetPassphrase = false
            }
        )
    }
}

@Composable
private fun SetPassphraseDialog(onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var value by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.pr_set_passphrase)) },
        text = {
            Column {
                Text(
                    stringResource(R.string.pr_unlock_desc),
                    style = MaterialTheme.typography.bodySmall
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = value,
                    onValueChange = { value = it },
                    label = { Text(stringResource(R.string.field_passphrase)) },
                    singleLine = true
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSave(value) },
                enabled = value.length >= 6
            ) {
                Text(stringResource(R.string.common_save))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.common_cancel))
            }
        }
    )
}