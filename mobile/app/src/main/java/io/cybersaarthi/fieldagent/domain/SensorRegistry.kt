package io.cybersaarthi.fieldagent.domain

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONObject
import kotlin.coroutines.resume

/**
 * Field sensors, mapped to stable semantic codes (never fabricate a reading: if
 * a sensor is absent the snapshot records hasValue=false).
 */
enum class SensorKind(val code: String, val typeConstant: Int) {
    ACCELEROMETER("accelerometer", Sensor.TYPE_ACCELEROMETER),
    GYROSCOPE("gyroscope", Sensor.TYPE_GYROSCOPE),
    MAGNETOMETER("magnetometer", Sensor.TYPE_MAGNETIC_FIELD),
    ROTATION_VECTOR("rotation_vector", Sensor.TYPE_ROTATION_VECTOR),
    BAROMETER("barometer", Sensor.TYPE_PRESSURE);

    companion object {
        fun fromCode(code: String): SensorKind? = entries.firstOrNull { it.code == code }
    }
}

data class SensorInfo(
    val kind: SensorKind,
    val present: Boolean,
    val name: String?,
    val description: String?
)

/**
 * A single captured reading. JSON-serialisable so it can be stored as evidence
 * (kind "sensor") and appears in the sealed manifest.
 */
data class SensorSnapshot(
    val kind: String,
    val hasValue: Boolean,
    val values: List<Float>,
    val capturedAtEpochMillis: Long
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("kind", kind)
        put("has_value", hasValue)
        put("values", org.json.JSONArray().apply { values.forEach { put(it) } })
        put("captured_at", capturedAtEpochMillis)
    }

    companion object {
        fun fromJson(o: JSONObject) = SensorSnapshot(
            kind = o.optString("kind", "sensor"),
            hasValue = o.optBoolean("has_value", false),
            values = run {
                val a = o.optJSONArray("values") ?: org.json.JSONArray()
                (0 until a.length()).mapNotNull { a.optDouble(it, Double.NaN).takeIf { d -> !d.isNaN() }?.toFloat() }
            },
            capturedAtEpochMillis = o.optLong("captured_at", 0L)
        )
    }
}

/**
 * Reads live sensor samples through the platform [SensorManager]. Sensors are
 * read genuinely; a failing or absent sensor yields hasValue=false, never a
 * fabricated reading.
 */
class SensorRegistry(context: Context) {

    private val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager

    fun available(): List<SensorInfo> = SensorKind.entries.map { kind ->
        val s = sm.getDefaultSensor(kind.typeConstant)
        SensorInfo(
            kind = kind,
            present = s != null,
            name = s?.name ?: kind.code,
        description = s
            ?.let { sensor ->
                    buildList {
                        add("vendor=${sensor.vendor}")
                        add("res=${sensor.resolution}")
                        add("range=${sensor.maximumRange}")
                    }.joinToString(", ")
                } ?: "Not present on this device"
        )
    }

    fun isPresent(kind: SensorKind): Boolean = sm.getDefaultSensor(kind.typeConstant) != null

    /** Samples a sensor for [samplingMillis], keeping the latest reading. */
    suspend fun read(kind: SensorKind, samplingMillis: Long = 600): SensorSnapshot =
        suspendCancellableCoroutine { cont ->
            val sensor = sm.getDefaultSensor(kind.typeConstant)
            if (sensor == null) {
                cont.resume(SensorSnapshot(kind.code, false, emptyList(), System.currentTimeMillis()))
                return@suspendCancellableCoroutine
            }
            val holder = object {
                var latest: FloatArray? = null
            }
            val listener = object : SensorEventListener {
                private var samples = 0
                override fun onSensorChanged(event: SensorEvent) {
                    holder.latest = event.values.copyOf()
                    samples++
                }

                override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
            }
            val handler = android.os.Handler(android.os.Looper.getMainLooper())
            sm.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_NORMAL, handler)
            handler.postDelayed({
                sm.unregisterListener(listener)
                val values = holder.latest
                if (cont.isActive) {
                    cont.resume(
                        SensorSnapshot(
                            kind = kind.code,
                            hasValue = values != null,
                            values = values?.toList() ?: emptyList(),
                            capturedAtEpochMillis = System.currentTimeMillis()
                        )
                    )
                }
            }, samplingMillis)
            cont.invokeOnCancellation {
                sm.unregisterListener(listener)
            }
        }
}