package io.cybersaarthi.fieldagent.ui.screen.case_detail

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.net.CollectionOut
import io.cybersaarthi.fieldagent.data.net.EvidenceSummary
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import io.cybersaarthi.fieldagent.ui.components.EmptyScreen
import io.cybersaarthi.fieldagent.ui.components.ErrorScreen
import io.cybersaarthi.fieldagent.ui.components.LoadingScreen
import io.cybersaarthi.fieldagent.ui.components.OfflineBanner
import io.cybersaarthi.fieldagent.ui.components.StatusBadge
import io.cybersaarthi.fieldagent.ui.components.localLabelRes

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CaseDetailScreen(
    caseId: String,
    onBack: () -> Unit,
    onOpenCollection: (CollectionOut) -> Unit
) {
    val vm = containerViewModel<CaseDetailViewModel> { CaseDetailViewModel(caseId, it) }
    val ui = vm.ui
    val online by LocalAppContainer.current.connectivity.online.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var showCreate by rememberSaveable { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(ui.caseDetail?.caseNumber?.let { stringResource(R.string.dd_case_number, it) }
                        ?: stringResource(R.string.cd_collections))
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                },
                actions = {
                    IconButton(onClick = vm::load) { Icon(Icons.Filled.Refresh, stringResource(R.string.common_refresh)) }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showCreate = true }) {
                Icon(Icons.Filled.Add, stringResource(R.string.cd_new_collection))
            }
        }
    ) { padding ->
        OfflineBanner(offline = !online, modifier = Modifier.padding(top = padding.calculateTopPadding()))
        Column(Modifier.fillMaxSize().padding(padding)) {
            when {
                ui.loading && ui.collections == null -> LoadingScreen()
                ui.errorRes != null -> ErrorScreen(ui.errorRes!!, onRetry = vm::load)
                else -> {
                    TabRow(selectedTabIndex = tab) {
                        Tab(selected = tab == 0, onClick = { tab = 0 },
                            text = { Text(stringResource(R.string.cd_collections)) })
                        Tab(selected = tab == 1, onClick = { tab = 1 },
                            text = { Text(stringResource(R.string.cd_evidence)) })
                    }
                    if (tab == 0) {
                        if (ui.collections?.isEmpty() == true) {
                            EmptyScreen(stringResource(R.string.cd_no_collections))
                        } else {
                            LazyColumn(
                                modifier = Modifier.fillMaxSize(),
                                contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                items(ui.collections.orEmpty(), key = { it.id }) { collection ->
                                    CollectionRow(
                                        collection = collection,
                                        localStatusRes = vm.localStatusFor(collection)?.localLabelRes(),
                                        onClick = { onOpenCollection(collection) }
                                    )
                                }
                            }
                        }
                    } else {
                        if (ui.remoteEvidence?.isEmpty() == true) {
                            EmptyScreen(stringResource(R.string.cd_no_evidence))
                        } else {
                            LazyColumn(
                                modifier = Modifier.fillMaxSize(),
                                contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                items(ui.remoteEvidence.orEmpty(), key = { it.id }) { evidence ->
                                    EvidenceRow(evidence)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showCreate) {
        NewCollectionDialog(
            creating = ui.creating,
            onDismiss = { if (!ui.creating) showCreate = false },
            onCreate = { name ->
                vm.createCollection(name) { remote ->
                    showCreate = false
                    onOpenCollection(remote)
                }
            }
        )
    }
}

@Composable
private fun CollectionRow(
    collection: CollectionOut,
    localStatusRes: Int?,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    collection.name,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    "· ${collection.id.take(8)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            StatusBadge(collection.status)
            localStatusRes?.let {
                androidx.compose.material3.Text(
                    stringResource(it),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(start = 8.dp)
                )
            }
        }
    }
}

@Composable
private fun EvidenceRow(evidence: EvidenceSummary) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    evidence.originalFilename,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1
                )
                Text(
                    "${evidence.format ?: "file"} · ${evidence.fileSize} B",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    "SHA-256 ${evidence.sha256.take(16)}\u2026",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary
                )
            }
            StatusBadge(evidence.status)
        }
    }
}

@Composable
private fun NewCollectionDialog(
    creating: Boolean,
    onDismiss: () -> Unit,
    onCreate: (String) -> Unit
) {
    var name by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.cd_new_collection)) },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text(stringResource(R.string.cd_collection_name)) },
                    placeholder = { Text(stringResource(R.string.cd_collection_name_hint)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    enabled = !creating
                )
                if (creating) {
                    Text(
                        stringResource(R.string.cd_creating),
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
            }
        },
        confirmButton = {
            Button(onClick = { onCreate(name) }, enabled = name.isNotBlank() && !creating) {
                Text(stringResource(R.string.common_save))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !creating) {
                Text(stringResource(R.string.common_cancel))
            }
        }
    )
}