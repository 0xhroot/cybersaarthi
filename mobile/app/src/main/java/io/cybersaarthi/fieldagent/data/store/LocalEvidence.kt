package io.cybersaarthi.fieldagent.data.store

import io.cybersaarthi.fieldagent.data.net.getLong
import io.cybersaarthi.fieldagent.data.net.getStr
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference

enum class EvidenceKind(val code: String) {
    PHOTO("photo"),
    VIDEO("video"),
    AUDIO("audio"),
    DOCUMENT("document"),
    NOTE("note"),
    LOCATION("location"),
    SENSOR("sensor");

    companion object {
        fun fromCode(code: String): EvidenceKind? =
            entries.firstOrNull { it.code == code }
    }
}

fun EvidenceKind.defaultExtension(): String = when (this) {
    EvidenceKind.PHOTO -> "jpg"
    EvidenceKind.VIDEO -> "mp4"
    EvidenceKind.AUDIO -> "m4a"
    EvidenceKind.DOCUMENT -> "bin"
    EvidenceKind.NOTE -> "txt"
    EvidenceKind.LOCATION -> "json"
    EvidenceKind.SENSOR -> "json"
}

/** Local (offline-first) evidence item. */
data class LocalEvidence(
    val id: String,
    val kind: EvidenceKind,
    val fileName: String,
    val originalName: String,
    val mimeType: String,
    val sizeBytes: Long,
    val capturedAt: String,
    val sha256: String,
    val capturedBy: String?,
    val deviceSerial: String?,
    val note: String?,
    val extra: JSONObject?
) {
    fun toDetailedJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("kind", kind.code)
        put("file_name", fileName)
        put("original_name", originalName)
        put("mime_type", mimeType)
        put("size_bytes", sizeBytes)
        put("captured_at", capturedAt)
        put("sha256", sha256)
        put("captured_by", capturedBy ?: JSONObject.NULL)
        put("device_serial", deviceSerial ?: JSONObject.NULL)
        put("note", note ?: JSONObject.NULL)
        put("extra", extra ?: JSONObject.NULL)
    }

    companion object {
        fun fromJson(o: JSONObject) = LocalEvidence(
            id = o.getString("id"),
            kind = EvidenceKind.fromCode(o.getStr("kind") ?: "document") ?: EvidenceKind.DOCUMENT,
            fileName = o.getString("file_name"),
            originalName = o.getStr("original_name") ?: "",
            mimeType = o.getStr("mime_type") ?: "application/octet-stream",
            sizeBytes = o.getLong("size_bytes") ?: 0L,
            capturedAt = o.getStr("captured_at") ?: "",
            sha256 = o.getStr("sha256") ?: "",
            capturedBy = o.getStr("captured_by"),
            deviceSerial = o.getStr("device_serial"),
            note = o.getStr("note"),
            extra = o.optJSONObject("extra")
        )
    }
}

/** Local collection lifecycle status. Mirrors the backend collection enum. */
enum class CollectionStatus(val code: String) {
    CAPTURING("captured"),
    HASHED("hashed"),
    SEALED("sealed"),
    PACKAGED("packaged"),
    SUBMITTED("transferred"),
    FAILED("failed");

    companion object {
        private val allowed: Map<CollectionStatus, Set<CollectionStatus>> = mapOf(
            CAPTURING to setOf(HASHED, FAILED),
            HASHED to setOf(CAPTURING, SEALED, FAILED),
            SEALED to setOf(HASHED, PACKAGED, SUBMITTED, FAILED),
            PACKAGED to setOf(SEALED, SUBMITTED, FAILED),
            SUBMITTED to setOf(PACKAGED, SEALED),
            FAILED to setOf(HASHED, SEALED, PACKAGED)
        )

        fun canTransition(from: CollectionStatus, to: CollectionStatus): Boolean =
            to in (allowed[from] ?: emptySet())

        fun fromCode(code: String): CollectionStatus =
            entries.firstOrNull { it.code == code } ?: CAPTURING
    }
}

data class LocalCollection(
    val id: String,
    val caseId: String,
    val name: String,
    val createdAt: String,
    val status: CollectionStatus,
    val statusMessage: String?
)