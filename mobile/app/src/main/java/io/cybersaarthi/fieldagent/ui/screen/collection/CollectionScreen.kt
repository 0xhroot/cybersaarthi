package io.cybersaarthi.fieldagent.ui.screen.collection

import android.annotation.SuppressLint

import android.content.Context
import android.location.Location
import android.location.LocationManager
import android.media.MediaRecorder
import android.os.Looper
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Notes
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.SdCard
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.data.store.EvidenceKind
import io.cybersaarthi.fieldagent.data.store.LocalEvidence
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import io.cybersaarthi.fieldagent.ui.components.EmptyScreen
import io.cybersaarthi.fieldagent.ui.components.ErrorScreen
import io.cybersaarthi.fieldagent.ui.components.LocalStatusBadge
import io.cybersaarthi.fieldagent.ui.components.OfflineBanner
import io.cybersaarthi.fieldagent.ui.components.SectionHeader
import io.cybersaarthi.fieldagent.ui.components.localLabelRes
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import java.io.FileOutputStream
import java.time.Instant
import kotlin.coroutines.resume

private fun io.cybersaarthi.fieldagent.data.store.CollectionStatus.isAtLeastSealed(): Boolean =
    ordinal >= io.cybersaarthi.fieldagent.data.store.CollectionStatus.SEALED.ordinal

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CollectionScreen(
    caseId: String,
    collectionId: String,
    collectionName: String,
    onBack: () -> Unit,
    onPhoto: () -> Unit,
    onVideo: () -> Unit
) {
    val vm = containerViewModel<CollectionViewModel> { CollectionViewModel(caseId, collectionId, it) }
    val ui = vm.ui
    val context = LocalContext.current
    val online by LocalAppContainer.current.connectivity.online.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val locationHelper = remember { LocationHelper() }
    var showNote by rememberSaveable { mutableStateOf(false) }
    var showAudio by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(Unit) { vm.start(collectionName) }

    LaunchedEffect(ui.messageRes) {
        ui.messageRes?.let {
            snackbar.showSnackbar(context.getString(it))
            vm.clearMessage()
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { /* permission result handled by the requesting action below */ }

    val documentPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            val name = queryDisplayName(context, uri) ?: "document.bin"
            val mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
            val tmp = copyUriToCache(context, uri, name)
            vm.writeDocument(tmp, name, mime)
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(collectionName.ifBlank { stringResource(R.string.cd_collections) })
                        Text(
                            stringResource(ui.status.localLabelRes()) + " · " + collectionId.take(8),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                }
            )
        }
    ) { padding ->
        OfflineBanner(offline = !online, modifier = Modifier.padding(top = padding.calculateTopPadding()))
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (ui.loading) {
                androidx.compose.material3.CircularProgressIndicator(Modifier.padding(24.dp))
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 24.dp)
                ) {
                    item {
                        Row(
                            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            LocalStatusBadge(ui.status)
                            if (ui.deviceApproved == false) {
                                androidx.compose.material3.Text(
                                    stringResource(R.string.enroll_status_pending),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.error
                                )
                            }
                        }
                    }

                    if (ui.canCapture) {
                        item { SectionHeader(stringResource(R.string.col_capture)) }
                        item {
                            Row(
                                Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                CaptureTile(
                                    Icons.Filled.PhotoCamera, stringResource(R.string.col_photo),
                                    Modifier.weight(1f), enabled = ui.canCapture && !ui.busy,
                                    onClick = onPhoto
                                )
                                CaptureTile(
                                    Icons.Filled.Videocam, stringResource(R.string.col_video),
                                    Modifier.weight(1f), enabled = ui.canCapture && !ui.busy,
                                    onClick = onVideo
                                )
                            }
                        }
                        item {
                            Row(
                                Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                CaptureTile(
                                    Icons.Filled.Mic, stringResource(R.string.col_audio),
                                    Modifier.weight(1f), enabled = ui.canCapture && !ui.busy,
                                    onClick = {
                                        permissionLauncher.launch(arrayOf(android.Manifest.permission.RECORD_AUDIO))
                                        showAudio = true
                                    }
                                )
                                CaptureTile(
                                    Icons.Filled.Notes, stringResource(R.string.col_note),
                                    Modifier.weight(1f), enabled = ui.canCapture && !ui.busy,
                                    onClick = { showNote = true }
                                )
                            }
                        }
                        item {
                            Row(
                                Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                CaptureTile(
                                    Icons.Filled.LocationOn, stringResource(R.string.col_location),
                                    Modifier.weight(1f), enabled = ui.canCapture && !ui.busy,
                                    onClick = {
                                        permissionLauncher.launch(
                                            arrayOf(
                                                android.Manifest.permission.ACCESS_FINE_LOCATION,
                                                android.Manifest.permission.ACCESS_COARSE_LOCATION
                                            )
                                        )
                                        scope.launch {
                                            val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
                                            val fix = withContext(Dispatchers.IO) {
                                                locationHelper.awaitFix(lm)
                                            }
                                            if (fix != null) {
                                                vm.writeLocation(
                                                    fix.latitude, fix.longitude,
                                                    fix.accuracy.toDouble(), fix.provider ?: "gps"
                                                )
                                            } else {
                                                snackbar.showSnackbar(
                                                    context.getString(R.string.col_location_fixing)
                                                )
                                            }
                                        }
                                    }
                                )
                                CaptureTile(
                                    Icons.Filled.Description, stringResource(R.string.col_document),
                                    Modifier.weight(1f), enabled = ui.canCapture && !ui.busy,
                                    onClick = { documentPicker.launch(arrayOf("*/*")) }
                                )
                            }
                        }
                    }

                    item { SectionHeader(stringResource(R.string.col_actions)) }
                    item {
                        Column(
                            Modifier.padding(horizontal = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            ActionButtons(ui, vm)
                            if (ui.status.isAtLeastSealed()) {
                                ExportAction(caseId, collectionId, vm, snackbar)
                            }
                        }
                    }

                    item { SectionHeader(stringResource(R.string.col_evidence_items)) }
                    if (ui.evidence.isEmpty()) {
                        item { EmptyScreen(stringResource(R.string.col_empty)) }
                    } else {
                        items(ui.evidence, key = { it.id }) { ev ->
                            EvidenceRow(
                                ev,
                                deletable = canDeleteEvidence(ui, ev),
                                onDelete = { vm.deleteEvidence(ev) }
                            )
                        }
                    }
                }
            }
        }
    }

    if (showNote) {
        NoteDialog(
            busy = ui.busy,
            onDismiss = { if (!ui.busy) showNote = false },
            onSave = { text ->
                vm.writeNote(text)
                showNote = false
            }
        )
    }

    if (showAudio) {
        AudioCaptureSheet(
            busy = ui.busy,
            onDismiss = { if (!ui.busy) showAudio = false },
            onCaptured = { file, name, mime ->
                vm.writeAudio(file, name, mime)
                showAudio = false
            }
        )
    }
}

private fun canDeleteEvidence(ui: CollectionUiState, ev: LocalEvidence): Boolean =
    ui.status == CollectionStatus.CAPTURING

@Composable
private fun CaptureTile(
    icon: ImageVector,
    label: String,
    modifier: Modifier = Modifier,
    enabled: Boolean,
    onClick: () -> Unit
) {
    Card(
        modifier = modifier
            .height(96.dp)
            .clickable(enabled = enabled, onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (enabled) MaterialTheme.colorScheme.primaryContainer
            else MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Icon(
                icon, null, Modifier.size(28.dp),
                tint = if (enabled) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.outline
            )
            Spacer(Modifier.height(6.dp))
            Text(
                label,
                style = MaterialTheme.typography.labelMedium,
                color = if (enabled) MaterialTheme.colorScheme.onSurface
                else MaterialTheme.colorScheme.outline
            )
        }
    }
}

@Composable
private fun ActionButtons(ui: CollectionUiState, vm: CollectionViewModel) {
    if (ui.busy) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
            Spacer(Modifier.size(10.dp))
            Text(stringResource(R.string.common_loading), style = MaterialTheme.typography.bodyMedium)
        }
    }
    if (ui.canHash) {
        FilledTonalButton(onClick = vm::hashAll, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Filled.Fingerprint, null, Modifier.size(18.dp))
            Text(stringResource(R.string.col_hash), modifier = Modifier.padding(start = 8.dp))
        }
    }
    if (ui.canSeal) {
        FilledTonalButton(onClick = vm::seal, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Filled.VerifiedUser, null, Modifier.size(18.dp))
            Text(stringResource(R.string.col_seal), modifier = Modifier.padding(start = 8.dp))
        }
    }
    if (ui.canPackage) {
        FilledTonalButton(onClick = vm::packageCollection, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Filled.SdCard, null, Modifier.size(18.dp))
            Text(stringResource(R.string.col_package), modifier = Modifier.padding(start = 8.dp))
        }
    }
    if (ui.status.isAtLeastSealed() && !ui.busy) {
        OutlinedButton(onClick = vm::verifySignature, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Filled.Fingerprint, null, Modifier.size(18.dp))
            Text(stringResource(R.string.col_verify_integrity), modifier = Modifier.padding(start = 8.dp))
        }
    }
    if (ui.canSubmit) {
        Button(onClick = vm::submit, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Filled.Send, null, Modifier.size(18.dp))
            Text(stringResource(R.string.col_submit), modifier = Modifier.padding(start = 8.dp))
        }
    }
    ui.errorRes?.let {
        Text(
            stringResource(it),
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 4.dp)
        )
    }
}

@Composable
private fun ExportAction(
    caseId: String,
    collectionId: String,
    vm: CollectionViewModel,
    snackbar: SnackbarHostState
) {
    val context = LocalContext.current
    val container = LocalAppContainer.current
    val scope = rememberCoroutineScope()
    var exporting by remember { mutableStateOf(false) }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { tree ->
        if (tree != null) {
            scope.launch {
                exporting = true
                val tmp = withContext(Dispatchers.IO) {
                    val dir = File.createTempFile("pkg", "").apply { delete(); mkdirs() }
                    container.transfer.exportPackage(caseId, collectionId, dir)
                    dir
                }
                withContext(Dispatchers.IO) {
                    tmp.listFiles()?.forEach { f -> copyToExternal(context, tree, f) }
                }
                tmp.deleteRecursively()
                exporting = false
                snackbar.showSnackbar(context.getString(R.string.tr_export_ok))
            }
        }
    }
    OutlinedButton(
        onClick = { exporter.launch(null) },
        enabled = !exporting,
        modifier = Modifier.fillMaxWidth()
    ) {
        Icon(Icons.Filled.SdCard, null, Modifier.size(18.dp))
        Text(stringResource(R.string.col_export), modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
private fun EvidenceRow(ev: LocalEvidence, deletable: Boolean, onDelete: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(
                iconForKind(ev.kind), null, Modifier.size(22.dp),
                tint = MaterialTheme.colorScheme.primary
            )
            Column(Modifier.weight(1f).padding(horizontal = 8.dp)) {
                Text(ev.originalName, style = MaterialTheme.typography.titleSmall, maxLines = 1)
                Text(
                    "${ev.sizeBytes} B · ${shortTime(ev.capturedAt)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    "SHA-256 ${ev.sha256.take(16)}\u2026",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary
                )
            }
            if (deletable) {
                IconButton(onClick = onDelete) {
                    Icon(Icons.Filled.Delete, stringResource(R.string.common_delete), tint = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

@Composable
fun NoteDialog(busy: Boolean, onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.col_note)) },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text(stringResource(R.string.col_note_hint)) },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth()
            )
        },
        confirmButton = {
            TextButton(onClick = { onSave(text) }, enabled = text.isNotBlank() && !busy) {
                Text(stringResource(R.string.common_save))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !busy) {
                Text(stringResource(R.string.common_cancel))
            }
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AudioCaptureSheet(busy: Boolean, onDismiss: () -> Unit, onCaptured: (File, String, String) -> Unit) {
    val context = LocalContext.current
    var recording by rememberSaveable { mutableStateOf(false) }
    var startedAt by rememberSaveable { mutableLongStateOf(0L) }
    var now by rememberSaveable { mutableLongStateOf(0L) }
    var error by rememberSaveable { mutableStateOf(false) }
    val output = remember { File.createTempFile("audio", ".m4a", context.cacheDir) }

    LaunchedEffect(recording) {
        while (recording) {
            kotlinx.coroutines.delay(1000)
            now = System.currentTimeMillis()
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.fillMaxWidth().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(Icons.Filled.Mic, null, Modifier.size(40.dp), tint = MaterialTheme.colorScheme.primary)
            Text(
                if (recording) {
                    val secs = (now - startedAt) / 1000
                    stringResource(R.string.col_recording, "%02d:%02d".format(secs / 60, secs % 60))
                } else {
                    stringResource(R.string.col_audio)
                },
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(vertical = 12.dp)
            )
            if (error) {
                Text(
                    stringResource(R.string.col_permission_required),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }
            Button(
                onClick = {
                    if (recording) {
                        stopRecorder(context, output)
                        recording = false
                        if (output.length() > 0) {
                            onCaptured(output, output.name, "audio/mp4")
                        }
                    } else {
                        error = !startRecorder(context, output)
                        if (!error) {
                            recording = true
                            startedAt = System.currentTimeMillis()
                            now = startedAt
                        }
                    }
                },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (recording) stringResource(R.string.col_record_stop) else stringResource(R.string.col_record_start))
            }
        }
    }
}

// ---- media primitives --------------------------------------------------------------------

private var recorder: MediaRecorder? = null

private fun startRecorder(context: Context, file: File): Boolean {
    return runCatching {
        val r = MediaRecorder()
        r.setAudioSource(MediaRecorder.AudioSource.MIC)
        r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        r.setAudioEncodingBitRate(96_000)
        r.setAudioSamplingRate(44_100)
        r.setOutputFile(file.absolutePath)
        r.prepare()
        r.start()
        recorder = r
        true
    }.getOrDefault(false)
}

private fun stopRecorder(context: Context, file: File) {
    recorder?.let {
        runCatching { it.stop() }
        runCatching { it.reset() }
        runCatching { it.release() }
    }
    recorder = null
}

class LocationHelper {
    @SuppressLint("MissingPermission")
    suspend fun awaitFix(lm: LocationManager, timeoutMs: Long = 30_000): Location? =
        suspendCancellableCoroutine { cont ->
            if (cont.isActive) {
                val listener = object : android.location.LocationListener {
                    override fun onLocationChanged(location: Location) = cont.resume(location)
                    @Deprecated("Deprecated in Java")
                    override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) {}
                    override fun onProviderEnabled(provider: String) {}
                    override fun onProviderDisabled(provider: String) {}
                }
                runCatching {
                    lm.requestSingleUpdate(
                        if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) LocationManager.GPS_PROVIDER
                        else LocationManager.NETWORK_PROVIDER,
                        listener, Looper.getMainLooper()
                    )
                }.onFailure { cont.resume(null) }
                cont.invokeOnCancellation { runCatching { lm.removeUpdates(listener) } }
            }
        }
}

private fun copyUriToCache(context: Context, uri: android.net.Uri, name: String): File {
    val out = File.createTempFile("doc", name.takeLast(12), context.cacheDir)
    context.contentResolver.openInputStream(uri)?.use { input ->
        FileOutputStream(out).use { output -> input.copyTo(output) }
    }
    return out
}

private fun copyToExternal(context: Context, tree: android.net.Uri, file: File) {
    val doc = androidx.documentfile.provider.DocumentFile.fromTreeUri(context, tree) ?: return
    val target = doc.findFile(file.name) ?: doc.createFile("application/octet-stream", file.name) ?: return
    context.contentResolver.openOutputStream(target.uri, "w")?.use { out ->
        file.inputStream().use { it.copyTo(out) }
    }
}

private fun queryDisplayName(context: Context, uri: android.net.Uri): String? = runCatching {
    context.contentResolver.query(
        uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null
    )?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
}.getOrNull()

private fun iconForKind(kind: EvidenceKind): ImageVector = when (kind) {
    EvidenceKind.PHOTO -> Icons.Filled.PhotoCamera
    EvidenceKind.VIDEO -> Icons.Filled.Videocam
    EvidenceKind.AUDIO -> Icons.Filled.Mic
    EvidenceKind.DOCUMENT -> Icons.Filled.Description
    EvidenceKind.NOTE -> Icons.Filled.Notes
    EvidenceKind.LOCATION -> Icons.Filled.LocationOn
}

private fun shortTime(iso: String): String = runCatching {
    Instant.parse(iso).toString().replace("T", " ").take(16)
}.getOrDefault(iso.take(16))