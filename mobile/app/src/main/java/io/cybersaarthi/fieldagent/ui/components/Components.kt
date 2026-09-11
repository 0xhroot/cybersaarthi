package io.cybersaarthi.fieldagent.ui.components

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.store.CollectionStatus

/** Human label for a local collection status. */
fun CollectionStatus.localLabelRes(): Int = when (this) {
    CollectionStatus.CAPTURING -> R.string.st_collecting
    CollectionStatus.HASHED -> R.string.st_hashed
    CollectionStatus.SEALED -> R.string.st_sealed
    CollectionStatus.PACKAGED -> R.string.st_packaged
    CollectionStatus.SUBMITTED -> R.string.st_submitted
    CollectionStatus.FAILED -> R.string.st_failed
}

@Composable
fun LoadingScreen(
    @StringRes labelRes: Int = R.string.common_loading,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(16.dp))
        Text(stringResource(labelRes), style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun EmptyScreen(
    text: String = stringResource(R.string.common_empty),
    modifier: Modifier = Modifier,
    icon: ImageVector = Icons.Filled.VerifiedUser
) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(icon, null, Modifier.size(40.dp), tint = MaterialTheme.colorScheme.outline)
        Spacer(Modifier.height(12.dp))
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
fun ErrorScreen(
    @StringRes errorRes: Int,
    onRetry: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Filled.Warning, null, Modifier.size(40.dp),
            tint = MaterialTheme.colorScheme.error
        )
        Spacer(Modifier.height(12.dp))
        Text(
            stringResource(errorRes),
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center
        )
        if (onRetry != null) {
            Spacer(Modifier.height(16.dp))
            androidx.compose.material3.TextButton(onClick = onRetry) {
                Text(stringResource(R.string.common_retry))
            }
        }
    }
}

@Composable
fun SectionHeader(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
    )
}

@Composable
fun StatusBadge(
    status: String,
    modifier: Modifier = Modifier
) {
    val (color, res) = when (status.lowercase()) {
        "open", "captured", "capturing", "approved" ->
            MaterialTheme.colorScheme.primary to R.string.dd_status_open
        "in_progress", "hashed", "ready", "pending" ->
            MaterialTheme.colorScheme.secondary to R.string.st_hashed
        "sealed", "closed", "archived" -> MaterialTheme.colorScheme.tertiary to R.string.st_sealed
        "packaged", "verified", "verifying" -> MaterialTheme.colorScheme.primary to R.string.st_packaged
        "submitted", "transferred", "imported", "processed", "graph_ready" ->
            MaterialTheme.colorScheme.tertiary to R.string.st_submitted
        "failed", "rejected", "revoked", "suspended" -> MaterialTheme.colorScheme.error to R.string.st_failed
        else -> MaterialTheme.colorScheme.outline to R.string.common_unknown
    }
    Badge(color, stringResource(res), modifier)
}

@Composable
fun LocalStatusBadge(status: CollectionStatus, modifier: Modifier = Modifier) {
    StatusBadge(status.code, modifier)
}

@Composable
fun Badge(color: Color, text: String, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .background(color.copy(alpha = 0.14f), MaterialTheme.shapes.small)
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = color
        )
    }
}

@Composable
fun IntegrityBadge(ok: Boolean, positive: String, negative: String) {
    Badge(
        color = if (ok) Color(0xFF2E7D32) else MaterialTheme.colorScheme.error,
        text = if (ok) positive else negative
    )
}

@Composable
fun SignatureBadge(ok: Boolean, @StringRes labelRes: Int) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
    ) {
        Icon(
            if (ok) Icons.Filled.VerifiedUser else Icons.Filled.Warning,
            null,
            Modifier.size(16.dp),
            tint = if (ok) Color(0xFF2E7D32) else MaterialTheme.colorScheme.error
        )
        Text(
            stringResource(labelRes),
            style = MaterialTheme.typography.labelMedium,
            color = if (ok) Color(0xFF2E7D32) else MaterialTheme.colorScheme.error
        )
    }
}

@Composable
fun OfflineBanner(offline: Boolean, modifier: Modifier = Modifier) {
    if (offline) {
        Box(
            modifier = modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.errorContainer)
                .padding(horizontal = 16.dp, vertical = 8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.Lock, null, Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.onErrorContainer
                )
                Spacer(Modifier.size(8.dp))
                Text(
                    stringResource(R.string.common_offline),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onErrorContainer
                )
            }
        }
    }
}

@Composable
fun InfoCard(title: String, body: String?) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.labelLarge)
            if (body != null) {
                Spacer(Modifier.height(4.dp))
                Text(body, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}