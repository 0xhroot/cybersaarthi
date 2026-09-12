package io.cybersaarthi.fieldagent.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.connectivity.ConnectionStatus

/** Compact global connection-state indicator (dot + label). */
@Composable
fun ConnectionStatusChip(
    status: ConnectionStatus,
    modifier: Modifier = Modifier
) {
    val (labelRes, color) = when (status) {
        ConnectionStatus.CONNECTED -> R.string.conn_connected to Color(0xFF2E7D32)
        ConnectionStatus.CONNECTING -> R.string.conn_connecting to Color(0xFFF9A825)
        ConnectionStatus.OFFLINE -> R.string.conn_offline to Color(0xFF616161)
        ConnectionStatus.SERVER_UNREACHABLE -> R.string.conn_unreachable to Color(0xFFC62828)
        ConnectionStatus.AUTH_EXPIRED -> R.string.conn_auth_expired to Color(0xFFEF6C00)
        ConnectionStatus.DEVICE_UNAPPROVED -> R.string.conn_device_unapproved to Color(0xFFEF6C00)
        ConnectionStatus.DEVICE_REVOKED -> R.string.conn_device_revoked to Color(0xFFB71C1C)
    }
    Row(
        modifier = modifier
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp))
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        androidx.compose.foundation.Canvas(Modifier.size(8.dp)) {
            drawCircle(color)
        }
        Text(
            stringResource(labelRes),
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(start = 6.dp)
        )
    }
}