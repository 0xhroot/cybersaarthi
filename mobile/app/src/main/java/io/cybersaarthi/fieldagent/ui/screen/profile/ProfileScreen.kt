package io.cybersaarthi.fieldagent.ui.screen.profile

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
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

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.pr_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                }
            )
        }
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(horizontal = 8.dp)
        ) {
            SectionHeader(stringResource(R.string.pr_account))
            InfoCard(stringResource(R.string.pr_user, ui.username, ui.status), ui.email)
            InfoCard(stringResource(R.string.pr_version, "2.0.0"), ui.username)
            SectionHeader(stringResource(R.string.enroll_my_device))
            InfoCard(stringResource(R.string.enroll_device_serial), ui.serial)
            InfoCard(
                stringResource(R.string.enroll_device_key),
                ui.fingerprint.chunked(8).joinToString(" ")
            )
            val server = LocalAppContainer.current.settings.serverUrl
            TitleValue(stringResource(R.string.pr_server), server)
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
}

@Composable
private fun TitleValue(title: String, value: String) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp)) {
        Text(title, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}