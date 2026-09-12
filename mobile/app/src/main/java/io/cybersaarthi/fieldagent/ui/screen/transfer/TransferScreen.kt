package io.cybersaarthi.fieldagent.ui.screen.transfer

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Button
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import io.cybersaarthi.fieldagent.ui.components.ConnectionStatusChip
import io.cybersaarthi.fieldagent.ui.components.InfoCard
import io.cybersaarthi.fieldagent.ui.components.SectionHeader
import io.cybersaarthi.fieldagent.ui.components.localLabelRes

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransferScreen(
    caseId: String,
    collectionId: String,
    onBack: () -> Unit
) {
    val vm = containerViewModel<TransferViewModel> { TransferViewModel(caseId, collectionId, it) }
    val ui = vm.ui
    val container = LocalAppContainer.current
    val status by container.connection.status.collectAsStateWithLifecycle()
    val statusLabel = stringResource(ui.status.localLabelRes())

    LaunchedEffect(ui.lastSubmit) { if (ui.lastSubmit != null) vm.refresh() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.tr_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                }
            )
        }
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp)
        ) {
            ConnectionStatusChip(status)
            Spacer(Modifier.height(12.dp))

            SectionHeader(stringResource(R.string.tr_collection))
            InfoCard(ui.collectionName, ui.collectionId.take(8))

            SectionHeader(stringResource(R.string.tr_device))
            InfoCard(ui.deviceSerial, stringResource(R.string.enroll_device_serial))

            SectionHeader(stringResource(R.string.tr_package))
            InfoCard(
                stringResource(R.string.tr_evidence_count, ui.evidenceCount),
                stringResource(R.string.tr_status, statusLabel)
            )
            InfoCard(
                stringResource(R.string.tr_package_size, formatBytes(ui.packageSizeBytes)),
                stringResource(R.string.st_packaged)
            )
            ui.manifestSha256?.let {
                InfoCard(stringResource(R.string.tr_manifest_sha), it.take(16) + "\u2026")
            }

            Spacer(Modifier.height(8.dp))
            if (ui.canTransfer) {
                Button(
                    onClick = { vm.submit() },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !ui.busy
                ) {
                    if (ui.busyTag == "submit") {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Filled.Send, null, Modifier.size(18.dp))
                    }
                    Text(stringResource(R.string.tr_submit), Modifier.padding(start = 8.dp))
                }
                OutlinedButton(
                    onClick = { vm.verifyPackage() },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    enabled = !ui.busy
                ) {
                    Icon(Icons.Filled.Fingerprint, null, Modifier.size(18.dp))
                    Text(stringResource(R.string.tr_verify), Modifier.padding(start = 8.dp))
                }
            }

            ui.infoMessage?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 12.dp)
                )
            }
            ui.errorMessage?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 12.dp)
                )
            }

            if (ui.lastSubmit != null) {
                SectionHeader(stringResource(R.string.tr_result))
                InfoCard(
                    stringResource(R.string.tr_imported, ui.lastSubmit!!.importedEvidenceCount),
                    stringResource(R.string.tr_collection_name, ui.lastSubmit!!.collectionName ?: "")
                )
                InfoCard(
                    stringResource(R.string.tr_evidence_ids, ui.lastSubmit!!.evidenceIds.size),
                    ui.lastSubmit!!.evidenceIds.take(3).joinToString("\n")
                )
            }
        }
    }
}

private fun formatBytes(bytes: Long): String = when {
    bytes >= 1_048_576 -> String.format(java.util.Locale.US, "%.1f MB", bytes / 1_048_576.0)
    bytes >= 1024 -> String.format(java.util.Locale.US, "%.1f KB", bytes / 1024.0)
    else -> "$bytes B"
}