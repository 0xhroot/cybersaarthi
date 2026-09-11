package io.cybersaarthi.fieldagent.ui.capture

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Cameraswitch
import androidx.compose.material.icons.filled.FlashlightOff
import androidx.compose.material.icons.filled.FlashlightOn
import androidx.compose.material.icons.filled.RadioButtonChecked
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.auth.AuthState
import io.cybersaarthi.fieldagent.data.store.EvidenceKind
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.Instant
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CameraCaptureScreen(
    mode: CameraMode,
    caseId: String,
    collectionId: String,
    onBack: () -> Unit,
    onCaptured: () -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val container = LocalAppContainer.current
    val executor = remember { Executors.newSingleThreadExecutor() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    var torchOn by remember { mutableStateOf(false) }
    var useFront by remember { mutableStateOf(false) }
    var recording by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var fallbackMessage by remember { mutableStateOf<String?>(null) }
    val activeRecording = remember { AtomicReference<Recording?>(null) }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) {
            fallbackMessage = null
        }
    }
    LaunchedEffect(Unit) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    val preview = remember { Preview.Builder().build() }
    val imageCapture = remember {
        ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .setJpegQuality(92)
            .build()
    }
    val videoCapture = remember { buildVideoCapture() }
    val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }

    var camera by remember { mutableStateOf<Camera?>(null) }

    DisposableEffect(lifecycleOwner, useFront, mode) {
        cameraProviderFuture.addListener(
            {
                runCatching {
                    val provider = cameraProviderFuture.get()
                    provider.unbindAll()
                    val selector = if (useFront) CameraSelector.DEFAULT_FRONT_CAMERA
                    else CameraSelector.DEFAULT_BACK_CAMERA
                    val bound = when (mode) {
                        CameraMode.PHOTO -> provider.bindToLifecycle(
                            lifecycleOwner, selector, preview, imageCapture
                        )
                        CameraMode.VIDEO -> provider.bindToLifecycle(
                            lifecycleOwner, selector, preview, videoCapture
                        )
                    }
                    camera = bound
                }.onFailure {
                    fallbackMessage = context.getString(
                        if (mode == CameraMode.PHOTO) R.string.col_photo_failed
                        else R.string.col_video_failed
                    )
                    providerNullSafe(cameraProviderFuture)?.unbindAll()
                }
            },
            ContextCompat.getMainExecutor(context)
        )
        onDispose {
            runCatching { providerNullSafe(cameraProviderFuture)?.unbindAll() }
            camera = null
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            executor.shutdown()
        }
    }

    fun capturePhoto() {
        if (saving) return
        saving = true
        val file = File(context.cacheDir, "cap_${Instant.now().toEpochMilli()}.jpg")
        val options = ImageCapture.OutputFileOptions.Builder(file).build()
        imageCapture.takePicture(
            options, executor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFiles: ImageCapture.OutputFileResults) {
                    scope.launch {
                        runCatching {
                            withContext(Dispatchers.IO) {
                                captureCtx(container).let { ctx ->
                                    container.store.writeEvidenceFromFile(
                                        caseId, collectionId, EvidenceKind.PHOTO,
                                        file, file.name, "image/jpeg",
                                        Instant.now().toString(), ctx.first, ctx.second
                                    )
                                }
                            }
                            file.delete()
                        }
                        saving = false
                        onCaptured()
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    saving = false
                    fallbackMessage = context.getString(R.string.col_photo_failed)
                }
            }
        )
    }

    fun stopVideo() {
        activeRecording.get()?.stop()
    }

    fun startVideo() {
        if (recording || saving) return
        saving = true
        val file = File(context.cacheDir, "cap_${Instant.now().toEpochMilli()}.mp4")
        val options = FileOutputOptions.Builder(file).build()
        val pending = videoCapture.output
            .prepareRecording(context, options)
            .withAudioEnabled()
        activeRecording.set(
            pending.start(ContextCompat.getMainExecutor(context), androidx.core.util.Consumer { event ->
                when (event) {
                    is VideoRecordEvent.Start -> {
                        recording = true
                        saving = false
                    }
                    is VideoRecordEvent.Status -> Unit
                    is VideoRecordEvent.Finalize -> {
                        recording = false
                        activeRecording.set(null)
                        if (event.hasError()) {
                            saving = false
                            fallbackMessage = context.getString(R.string.col_video_failed)
                        } else {
                            val videoUri: android.net.Uri = event.outputResults.outputUri
                            scope.launch {
                                runCatching {
                                    val target = withContext(Dispatchers.IO) {
                                        resolveUriFile(context, videoUri, file)
                                    }
                                    withContext(Dispatchers.IO) {
                                        captureCtx(container).let { ctx ->
                                            container.store.writeEvidenceFromFile(
                                                caseId, collectionId, EvidenceKind.VIDEO,
                                                target, file.name, "video/mp4",
                                                Instant.now().toString(), ctx.first, ctx.second
                                            )
                                        }
                                    }
                                    target.delete()
                                }
                                saving = false
                                onCaptured()
                            }
                        }
                    }
                }
            })
        )
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Color.Black
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            AndroidView(
                factory = { ctx ->
                    PreviewView(ctx).also { v ->
                        preview.setSurfaceProvider(v.surfaceProvider)
                    }
                },
                modifier = Modifier.fillMaxSize()
            )

            IconButton(
                onClick = onBack,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(8.dp)
                    .background(Color(0x66000000), shape = androidx.compose.foundation.shape.CircleShape)
            ) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back), tint = Color.White)
            }

            if (mode == CameraMode.PHOTO) {
                IconButton(
                    onClick = {
                        torchOn = !torchOn
                        camera?.cameraControl?.enableTorch(torchOn)
                    },
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(8.dp)
                        .background(Color(0x66000000), shape = androidx.compose.foundation.shape.CircleShape)
                ) {
                    Icon(
                        if (torchOn) Icons.Filled.FlashlightOn else Icons.Filled.FlashlightOff,
                        stringResource(R.string.common_close),
                        tint = Color.White
                    )
                }
            }

            IconButton(
                onClick = { useFront = !useFront },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(16.dp)
                    .background(Color(0x66000000), shape = androidx.compose.foundation.shape.CircleShape)
            ) {
                Icon(Icons.Filled.Cameraswitch, stringResource(R.string.col_photo), tint = Color.White)
            }

            IconButton(
                onClick = {
                    if (mode == CameraMode.PHOTO) {
                        capturePhoto()
                    } else {
                        if (recording) stopVideo() else startVideo()
                    }
                },
                enabled = !(mode == CameraMode.PHOTO && saving),
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 24.dp)
            ) {
                if (saving && mode == CameraMode.PHOTO) {
                    CircularProgressIndicator(Modifier.size(72.dp), strokeWidth = 5.dp, color = Color.White)
                } else {
                    Icon(
                        if (mode == CameraMode.VIDEO && recording) Icons.Filled.Stop
                        else Icons.Filled.RadioButtonChecked,
                        stringResource(R.string.col_photo),
                        tint = Color.White,
                        modifier = Modifier.size(if (recording) 56.dp else 72.dp)
                    )
                }
            }

            if (recording) {
                Text(
                    "● REC",
                    color = Color(0xFFFF5252),
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = 12.dp)
                )
            }
        }
    }
}

private fun resolveUriFile(context: Context, uri: Uri, fallback: File): File {
    if (uri.scheme == "file") {
        uri.path?.let { runCatching { return File(it) } }
    }
    val tmp = File(context.cacheDir, fallback.name)
    context.contentResolver.openInputStream(uri)?.use { input ->
        tmp.outputStream().use { input.copyTo(it) }
    }
    return tmp
}

private fun captureCtx(container: io.cybersaarthi.fieldagent.AppContainer): Pair<String?, String> {
    val userId = (container.session.current() as? AuthState.Active)?.userId
    return userId to DeviceIdentity.serial
}

private fun buildVideoCapture(): VideoCapture<Recorder> {
    val quality = QualitySelector.from(
        Quality.SD,
        androidx.camera.video.FallbackStrategy.lowerQualityOrHigherThan(Quality.SD)
    )
    val recorder = Recorder.Builder()
        .setQualitySelector(quality)
        .build()
    return VideoCapture.withOutput(recorder)
}

private fun providerNullSafe(future: com.google.common.util.concurrent.ListenableFuture<ProcessCameraProvider>):
    ProcessCameraProvider? = runCatching { future.get() }.getOrNull()

enum class CameraMode { PHOTO, VIDEO }