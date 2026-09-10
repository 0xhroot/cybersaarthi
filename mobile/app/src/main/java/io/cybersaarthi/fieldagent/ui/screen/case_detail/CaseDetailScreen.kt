package io.cybersaarthi.fieldagent.ui.screen.case_detail

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

data class CollectionSummary(
    val id: String,
    val name: String,
    val status: String,
    val itemCount: Int
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CaseDetailScreen(
    onCollectionClick: (caseId: String, collectionId: String) -> Unit,
    onBack: () -> Unit
) {
    // Data is fetched from the server in a real build via the collections API;
    // these placeholders demonstrate the collection card / status UX.
    val caseId = "2617f62d-e0d2-4d13-8e2a-1a28990b81de"
    val collections = listOf(
        CollectionSummary("a1b2c3", "Call Logs", "captured", 45),
        CollectionSummary("d4e5f6", "SMS Export", "hashed", 200),
        CollectionSummary("g7h8i9", "App Data", "sealed", 89)
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Collections") },
                navigationIcon = { TextButton(onClick = onBack) { Text("Back") } }
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
            items(collections.size) { idx ->
                val coll = collections[idx]
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onCollectionClick(caseId, coll.id) }
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(coll.name, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Status: ${coll.status}  •  ${coll.itemCount} items",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }
}