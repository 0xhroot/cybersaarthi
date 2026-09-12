package io.cybersaarthi.fieldagent.ui.screen.connection

import android.annotation.SuppressLint
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.di.LocalAppContainer
import io.cybersaarthi.fieldagent.di.containerViewModel
import com.google.zxing.BinaryBitmap
import com.google.zxing.MultiFormatReader
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer

/** Scans a CyberSaarthi pairing QR code via CameraX + ZXing. */
@SuppressLint("UnsafeOptInUsageError")
@OptIn(ExperimentalMaterial3Api::class, ExperimentalGetImage::class)
@Composable
fun QrPairingScreen(
    onPaired: () -> Unit,
    onBack: () -> Unit,
    onChooseAnother: () -> Unit
) {
    val vm = containerViewModel<QrPairingViewModel> { QrPairingViewModel(it) }
    val context = LocalContext.current
    val hasCameraPermission = remember { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasCameraPermission.value = granted }

    LaunchedEffect(Unit) {
        if (!hasCameraPermission.value) permissionLauncher.launch(android.Manifest.permission.CAMERA)
    }
    LaunchedEffect(vm.ui.paired) { if (vm.ui.paired) onPaired() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.qr_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back))
                    }
                }
            )
        }
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            if (hasCameraPermission.value) {
                var scanning by remember { mutableStateOf(true) }

                AndroidView(
                    factory = { ctx ->
                        PreviewView(ctx).apply {
                            val providerFuture = ProcessCameraProvider.getInstance(ctx)
                            providerFuture.addListener({
                                val provider = providerFuture.get()
                                val preview = Preview.Builder().build().also { it.surfaceProvider = surfaceProvider }
                                val analysis = ImageAnalysis.Builder()
                                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                                    .build()
                                    .also { image ->
                                        image.setAnalyzer(ContextCompat.getMainExecutor(ctx)) { proxy ->
                                            if (!scanning) { proxy.close(); return@setAnalyzer }
                                            val text = scanQr(proxy)
                                            if (text != null) {
                                                scanning = false
                                                vm.parsed(text)
                                            }
                                        }
                                    }
                                try {
                                    provider.unbindAll()
                                    provider.bindToLifecycle(ctx as androidx.lifecycle.LifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                                } catch (_: Exception) {}
                            }, ContextCompat.getMainExecutor(ctx))
                        }
                    },
                    modifier = Modifier.fillMaxWidth().weight(1f)
                )
            } else {
                Column(
                    Modifier.fillMaxWidth().weight(1f),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(Icons.Filled.QrCodeScanner, null, Modifier.size(48.dp), tint = MaterialTheme.colorScheme.outline)
                    Spacer(Modifier.height(12.dp))
                    Text(stringResource(R.string.qr_permission_required))
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = { permissionLauncher.launch(android.Manifest.permission.CAMERA) }) {
                        Text(stringResource(R.string.qr_grant_permission))
                    }
                }
            }

            vm.ui.errorMessage?.let { msg ->
                Text(
                    msg, color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(12.dp)
                )
            }
            if (vm.ui.verifying) {
                CircularProgressIndicator(Modifier.padding(12.dp).size(24.dp), strokeWidth = 2.dp)
                Text(stringResource(R.string.qr_verifying), style = MaterialTheme.typography.bodySmall)
            }
            if (vm.ui.failed) {
                OutlinedButton(onClick = { vm.reset() }, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                    Text(stringResource(R.string.qr_try_again))
                }
                Button(onClick = onChooseAnother, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
                    Text(stringResource(R.string.common_back))
                }
            }
        }
    }
}

/** Returns the decoded QR string or null if no QR in this frame. */
@ExperimentalGetImage
private fun scanQr(proxy: ImageProxy): String? {
    val image = proxy.image ?: return null
    val plane = image.planes[0]
    val buffer = plane.buffer
    val w = proxy.width
    val h = proxy.height
    val rowStride = plane.rowStride
    val bytes = ByteArray(rowStride * h)
    buffer.rewind()
    buffer.get(bytes)
    val lum = IntArray(w * h)
    for (row in 0 until h) {
        for (col in 0 until w) {
            val y = bytes[row * rowStride + col].toInt() and 0xFF
            lum[row * w + col] = (0xFF shl 24) or (y shl 16) or (y shl 8) or y
        }
    }
    proxy.close()
    return runCatching {
        val source = PlanarYUVLuminanceSource(bytes, w, h, 0, 0, w, h, false)
        val bitmap = BinaryBitmap(HybridBinarizer(source))
        MultiFormatReader().decode(bitmap).text
    }.getOrNull()
}