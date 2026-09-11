package io.cybersaarthi.fieldagent.ui.screen.auth

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.net.CaseOut
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import io.cybersaarthi.fieldagent.ui.components.EmptyScreen
import io.cybersaarthi.fieldagent.ui.components.ErrorScreen
import io.cybersaarthi.fieldagent.ui.components.InfoCard
import io.cybersaarthi.fieldagent.ui.components.LoadingScreen
import io.cybersaarthi.fieldagent.ui.components.OfflineBanner
import io.cybersaarthi.fieldagent.ui.components.SectionHeader
import io.cybersaarthi.fieldagent.ui.components.StatusBadge

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EnrollScreen(
    onContinue: () -> Unit,
    onBack: () -> Unit
) {
    val vm = containerViewModel<EnrollViewModel> { EnrollViewModel(it) }
    val ui = vm.ui
    val online by LocalAppContainer.current.connectivity.online.collectAsStateWithLifecycle()

    LaunchedEffect(ui.approved) {
        // Do not auto-advance; the operator chooses when to continue.
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.enroll_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                },
                actions = {
                    IconButton(onClick = vm::refresh, enabled = !ui.registering) {
                        Icon(Icons.Filled.Refresh, stringResource(R.string.enroll_refresh))
                    }
                }
            )
        }
    ) { padding ->
        OfflineBanner(offline = !online, modifier = Modifier.padding(top = padding.calculateTopPadding()))
        Column(Modifier.fillMaxSize().padding(padding)) {
            SectionHeader(stringResource(R.string.enroll_choose_case))
            if (ui.loading) {
                LoadingScreen()
            } else {
                if (ui.errorRes != null) {
                    ErrorScreen(ui.errorRes!!, onRetry = vm::refresh)
                } else {
                    if (ui.cases.isEmpty()) {
                        EmptyScreen(stringResource(R.string.enroll_no_cases))
                    } else {
                        LazyColumn(
                            modifier = Modifier.weight(1f),
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(ui.cases, key = { it.id }) { case ->
                                CaseRow(
                                    case = case,
                                    selected = case.id == ui.activeCaseId,
                                    onClick = { vm.selectCase(case.id) }
                                )
                            }
                        }
                    }
                }
            }

            if (!ui.cases.isEmpty()) {
                DeviceCard(
                    model = ui.device?.model,
                    serial = DeviceIdentity.serial,
                    fingerprint = DeviceIdentity.keyFingerprint,
                    registered = ui.isRegistered,
                    approved = ui.approved,
                    revoked = ui.device?.status == "revoked",
                    registering = ui.registering,
                    onRegister = vm::register
                )
                if (ui.approved && !ui.registering) {
                    Button(
                        onClick = onContinue,
                        modifier = Modifier.fillMaxWidth().padding(16.dp)
                    ) {
                        Text(stringResource(R.string.common_continue))
                    }
                }
            }
        }
    }
}

@Composable
private fun CaseRow(case: CaseOut, selected: Boolean, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) MaterialTheme.colorScheme.primaryContainer
            else MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(
            Modifier.padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    stringResource(R.string.dd_case_number, case.caseNumber),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold
                )
                if (case.title.isNotBlank()) {
                    Text(
                        case.title,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            StatusBadge(case.status)
        }
    }
}

@Composable
private fun DeviceCard(
    model: String?,
    serial: String,
    fingerprint: String,
    registered: Boolean,
    approved: Boolean,
    revoked: Boolean,
    registering: Boolean,
    onRegister: () -> Unit
) {
    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
        Text(
            stringResource(R.string.enroll_my_device),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold
        )
        Spacer(Modifier.height(8.dp))
        InfoCard(stringResource(R.string.enroll_device_serial), serial)
        InfoCard(stringResource(R.string.enroll_device_model), model ?: "—")
        InfoCard(
            stringResource(R.string.enroll_device_key),
            fingerprint.chunked(8).joinToString(" ")
        )
        Spacer(Modifier.height(8.dp))
        when {
            registered && approved -> StatusBadge("approved")
            registered && revoked -> StatusBadge("revoked")
            registered -> StatusBadge("pending")
            else -> Button(
                onClick = onRegister,
                enabled = !registering,
                modifier = Modifier.fillMaxWidth()
            ) {
                if (registering) {
                    CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                } else {
                    Text(stringResource(R.string.enroll_register))
                }
            }
        }
    }
}