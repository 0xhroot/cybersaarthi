package io.cybersaarthi.fieldagent.ui.screen.dashboard

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class CaseSummary(
    val id: String,
    val caseNumber: String,
    val title: String,
    val evidenceCount: Int
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(onCaseClick: (String) -> Unit, onLogout: () -> Unit) {
    val cases = listOf(
        CaseSummary(
            id = "2617f62d-e0d2-4d13-8e2a-1a28990b81de",
            caseNumber = "DEMO-2026-001",
            title = "Demo Investigation",
            evidenceCount = 12
        )
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Cases") },
                actions = { TextButton(onClick = onLogout) { Text("Logout") } }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(cases.size) { idx ->
                val c = cases[idx]
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onCaseClick(c.id) }
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(c.title, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${c.caseNumber}  •  ${c.evidenceCount} evidence items",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }
}