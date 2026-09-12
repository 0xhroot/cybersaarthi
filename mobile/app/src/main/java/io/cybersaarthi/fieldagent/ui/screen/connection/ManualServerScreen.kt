package io.cybersaarthi.fieldagent.ui.screen.connection

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import io.cybersaarthi.fieldagent.di.containerViewModel
import androidx.compose.foundation.text.KeyboardOptions

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManualServerScreen(
    onSaved: () -> Unit,
    onBack: () -> Unit
) {
    val vm = containerViewModel<ManualServerViewModel> { ManualServerViewModel(it) }
    val ui = vm.ui
    var url by rememberSaveable { mutableStateOf(ui.url) }

    LaunchedEffect(ui.saved) { if (ui.saved) onSaved() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.ms_title)) },
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
                .padding(horizontal = 24.dp, vertical = 16.dp)
        ) {
            Text(
                stringResource(R.string.ms_subtitle),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.height(16.dp))
            OutlinedTextField(
                value = url,
                onValueChange = { url = it; vm.updateUrl(it) },
                label = { Text(stringResource(R.string.ms_url_label)) },
                placeholder = { Text(stringResource(R.string.ms_url_hint)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(16.dp))
            OutlinedButton(
                onClick = { vm.testConnection() },
                enabled = !ui.testing && url.isNotBlank(),
                modifier = Modifier.fillMaxWidth()
            ) {
                if (ui.testing) CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                Text(stringResource(R.string.ms_test), modifier = Modifier.padding(start = if (ui.testing) 8.dp else 0.dp))
            }
            ui.serverInfo?.let {
                Spacer(Modifier.height(12.dp))
                Text(
                    stringResource(R.string.ms_reachable),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold
                )
                Text(it, style = MaterialTheme.typography.bodyMedium)
                ui.hostname?.let { svc ->
                    Text(
                        stringResource(R.string.ms_service_name, svc),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            ui.errorMessage?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.height(24.dp))
            Button(
                onClick = { vm.save() },
                enabled = url.isNotBlank(),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(stringResource(R.string.ms_save))
            }
        }
    }
}