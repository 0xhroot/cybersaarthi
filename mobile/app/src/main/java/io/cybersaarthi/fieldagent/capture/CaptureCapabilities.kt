package io.cybersaarthi.fieldagent.capture

import android.content.Context
import android.content.pm.PackageManager

/**
 * Detects which capture capabilities are available on the current device.
 * Uses PackageManager to probe for camera, microphone, GPS, and sensors.
 */
object CaptureCapabilities {
    fun detect(context: Context): Map<String, Boolean> {
        val pm = context.packageManager
        return mapOf(
            "camera" to pm.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY),
            "audio" to pm.hasSystemFeature(PackageManager.FEATURE_MICROPHONE),
            "gps" to pm.hasSystemFeature(PackageManager.FEATURE_LOCATION),
            "document" to true,
            "bluetooth" to pm.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH),
            "nfc" to pm.hasSystemFeature(PackageManager.FEATURE_NFC),
            "sensors" to pm.hasSystemFeature(PackageManager.FEATURE_SENSOR_ACCELEROMETER)
        )
    }
}