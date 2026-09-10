package io.cybersaarthi.fieldagent.ui.screen.collection

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import io.cybersaarthi.fieldagent.capture.CaptureCapabilities
import io.cybersaarthi.fieldagent.state.CollectionState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CollectionCaptureScreen(onBack: () -> Unit, onComplete: () -> Unit) {
    val context = LocalContext.current
    val capabilities = remember { CaptureCapabilities.detect(context) }
    var currentState by rememberSaveable { mutableStateOf(CollectionState.CAPTURED) }
    var capturedCount by rememberSaveable { mutableIntStateOf(0) }

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicturePreview()
    ) { bitmap ->
        if (bitmap != null) capturedCount++
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Capture Evidence") },
                navigationIcon = { TextButton(onClick = onBack) { Text("Back") } }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                "Current state: ${currentState.code}",
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                "Evidence captured: $capturedCount",
                style = MaterialTheme.typography.bodyLarge
            )
            HorizontalDivider()
            Text("Capabilities detected:", style = MaterialTheme.typography.titleSmall)
            capabilities.forEach { (cap, available) ->
                Text(
                    "$cap: ${if (available) "available" else "unavailable"}",
                    style = MaterialTheme.typography.bodySmall
                )
            }
            HorizontalDivider()

            when (currentState) {
                CollectionState.CAPTURED -> {
                    if (capabilities["camera"] == true) {
                        Button(onClick = { cameraLauncher.launch(null) }) {
                            Text("Take Photo")
                        }
                    }
                    if (capabilities["audio"] == true) {
                        OutlinedButton(onClick = {}) { Text("Record Audio") }
                    }
                    if (capabilities["document"] == true) {
                        OutlinedButton(onClick = {}) { Text("Capture Document") }
                    }
                    if (capturedCount > 0) {
                        Button(
                            onClick = { currentState = CollectionState.HASHED },
                            modifier = Modifier.padding(top = 16.dp)
                        ) {
                            Text("Hash All Evidence")
                        }
                    }
                }
                CollectionState.HASHED -> Button(onClick = { currentState = CollectionState.SEALED }) {
                    Text("Seal Evidence Bundle")
                }
                CollectionState.SEALED -> Button(onClick = { currentState = CollectionState.PACKAGED }) {
                    Text("Build Package")
                }
                CollectionState.PACKAGED -> Button(onClick = { currentState = CollectionState.TRANSFERRED }) {
                    Text("Export to USB / MTP")
                }
                CollectionState.TRANSFERRED -> OutlinedButton(onClick = onComplete) {
                    Text("Done — hand off to desktop importer")
                }
                else -> {
                    Text(
                        "Awaiting server verification (${currentState.code})",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    OutlinedButton(onClick = onComplete) { Text("Done") }
                }
            }
        }
    }
}