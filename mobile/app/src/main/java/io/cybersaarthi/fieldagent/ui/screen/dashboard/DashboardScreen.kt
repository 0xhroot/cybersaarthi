package io.cybersaarthi.fieldagent.ui.screen.dashboard

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.net.CaseOut
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import io.cybersaarthi.fieldagent.ui.components.EmptyScreen
import io.cybersaarthi.fieldagent.ui.components.ErrorScreen
import io.cybersaarthi.fieldagent.ui.components.LoadingScreen
import io.cybersaarthi.fieldagent.ui.components.OfflineBanner
import io.cybersaarthi.fieldagent.ui.components.StatusBadge

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onOpenCase: (CaseOut) -> Unit,
    onProfile: () -> Unit
) {
    val vm = containerViewModel<DashboardViewModel> { DashboardViewModel(it) }
    val ui = vm.ui
    val online by LocalAppContainer.current.connectivity.online.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.dd_title)) },
                actions = {
                    IconButton(onClick = vm::load) { Icon(Icons.Filled.Refresh, stringResource(R.string.common_refresh)) }
                    IconButton(onClick = onProfile) { Icon(Icons.Filled.AccountCircle, stringResource(R.string.pr_title)) }
                }
            )
        }
    ) { padding ->
        OfflineBanner(offline = !online)
        Column(Modifier.fillMaxSize().padding(padding)) {
            when {
                ui.loading && ui.cases == null -> LoadingScreen()
                ui.errorRes != null -> ErrorScreen(ui.errorRes!!, onRetry = vm::load)
                ui.cases?.isEmpty() == true -> EmptyScreen(stringResource(R.string.dd_no_cases))
                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(ui.cases.orEmpty(), key = { it.id }) { case ->
                        CaseCard(case, onClick = {
                            vm.openCase(case)
                            onOpenCase(case)
                        })
                    }
                }
            }
        }
    }
}

@Composable
private fun CaseCard(case: CaseOut, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    stringResource(R.string.dd_case_number, case.caseNumber),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    case.title.ifBlank { case.id },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 2.dp)
                )
            }
            StatusBadge(case.status)
        }
    }
}