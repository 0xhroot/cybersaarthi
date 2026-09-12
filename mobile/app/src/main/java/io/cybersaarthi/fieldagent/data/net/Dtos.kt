package io.cybersaarthi.fieldagent.data.net

import org.json.JSONArray
import org.json.JSONObject

fun JSONObject.getStr(key: String): String? {
    if (!has(key)) return null
    val v = opt(key)
    return if (v === JSONObject.NULL) null else v.toString()
}

fun JSONObject.getLong(key: String): Long? {
    if (!has(key)) return null
    val v = opt(key)
    return if (v === JSONObject.NULL || v is JSONArray || v is JSONObject) null
    else (v as? Number)?.toLong()
}

fun JSONObject.getInt(key: String): Int? = getLong(key)?.toInt()

fun JSONObject.getBool(key: String): Boolean = optBoolean(key, false)

fun JSONObject.getObj(key: String): JSONObject? =
    if (has(key) && opt(key) is JSONObject) optJSONObject(key) else null

fun JSONObject.getStringList(key: String): List<String> {
    val a = optJSONArray(key) ?: return emptyList()
    return (0 until a.length()).mapNotNull { a.optString(it).ifBlank { null } }
}

fun JSONObject.getObjects(key: String): List<JSONObject> {
    val a = optJSONArray(key) ?: return emptyList()
    return (0 until a.length()).mapNotNull { a.optJSONObject(it) }
}

inline fun <reified T> parsePage(raw: String, item: (JSONObject) -> T): List<T> {
    val obj = JSONObject(raw)
    return obj.getObjects("items").map(item)
}

data class UserOut(
    val id: String,
    val username: String,
    val email: String?,
    val status: String
) {
    companion object {
        fun fromJson(o: JSONObject) = UserOut(
            id = o.getString("id"),
            username = o.getString("username"),
            email = o.getStr("email"),
            status = o.getStr("status") ?: "active"
        )
    }
}

data class AuthToken(
    val accessToken: String,
    val tokenType: String,
    val expiresIn: Long,
    val user: UserOut
) {
    companion object {
        fun fromJson(raw: String) = run {
            val o = JSONObject(raw)
            AuthToken(
                accessToken = o.getString("access_token"),
                tokenType = o.getStr("token_type") ?: "bearer",
                expiresIn = o.getLong("expires_in") ?: 0L,
                user = UserOut.fromJson(o.getJSONObject("user"))
            )
        }
    }
}

data class CaseOut(
    val id: String,
    val caseNumber: String,
    val title: String,
    val description: String?,
    val status: String,
    val ownerId: String?,
    val createdAt: String,
    val updatedAt: String
) {
    companion object {
        fun fromJson(o: JSONObject) = CaseOut(
            id = o.getString("id"),
            caseNumber = o.getStr("case_number") ?: "",
            title = o.getStr("title") ?: "",
            description = o.getStr("description"),
            status = o.getStr("status") ?: "open",
            ownerId = o.getStr("owner_id"),
            createdAt = o.getStr("created_at") ?: "",
            updatedAt = o.getStr("updated_at") ?: ""
        )
    }
}

data class CollectionOut(
    val id: String,
    val caseId: String,
    val name: String,
    val description: String?,
    val status: String,
    val sealedAt: String?,
    val createdAt: String,
    val updatedAt: String
) {
    companion object {
        fun fromJson(o: JSONObject) = CollectionOut(
            id = o.getString("id"),
            caseId = o.getStr("case_id") ?: "",
            name = o.getStr("name") ?: "",
            description = o.getStr("description"),
            status = o.getStr("status") ?: "captured",
            sealedAt = o.getStr("sealed_at"),
            createdAt = o.getStr("created_at") ?: "",
            updatedAt = o.getStr("updated_at") ?: ""
        )
    }
}

data class EvidenceSummary(
    val id: String,
    val originalFilename: String,
    val sha256: String,
    val format: String?,
    val fileSize: Long,
    val status: String,
    val createdAt: String
) {
    companion object {
        fun fromJson(o: JSONObject) = EvidenceSummary(
            id = o.getString("id"),
            originalFilename = o.getStr("original_filename") ?: "",
            sha256 = o.getStr("sha256") ?: "",
            format = o.getStr("format"),
            fileSize = o.getLong("file_size") ?: 0L,
            status = o.getStr("status") ?: "pending",
            createdAt = o.getStr("created_at") ?: ""
        )
    }
}

data class DeviceOut(
    val id: String,
    val caseId: String,
    val platform: String,
    val serial: String,
    val model: String?,
    val status: String,
    val createdAt: String
) {
    companion object {
        fun fromJson(o: JSONObject) = DeviceOut(
            id = o.getString("id"),
            caseId = o.getStr("case_id") ?: "",
            platform = o.getStr("platform") ?: "android",
            serial = o.getStr("serial") ?: "",
            model = o.getStr("model"),
            status = o.getStr("status") ?: "pending",
            createdAt = o.getStr("created_at") ?: ""
        )
    }
}

data class ImportAccepted(
    val caseId: String,
    val deviceSerial: String,
    val importedEvidenceCount: Int,
    val evidenceIds: List<String>,
    val collectionName: String?
) {
    companion object {
        fun fromJson(raw: String): ImportAccepted {
            val o = JSONObject(raw)
            return ImportAccepted(
                caseId = o.getStr("case_id") ?: "",
                deviceSerial = o.getStr("device_serial") ?: "",
                importedEvidenceCount = o.getInt("imported_evidence_count") ?: 0,
                evidenceIds = o.getStringList("evidence_ids"),
                collectionName = o.getStr("collection_name")
            )
        }
    }
}

/** Response payload of the approved-device liveness beacon (`POST .../heartbeat`). */
data class DeviceHeartbeatResult(
    val ok: Boolean,
    val status: String,
    val lastSeenAt: String?
) {
    companion object {
        fun fromJson(raw: String): DeviceHeartbeatResult {
            val o = JSONObject(raw)
            return DeviceHeartbeatResult(
                ok = o.optBoolean("ok"),
                status = o.getStr("status") ?: "",
                lastSeenAt = o.getStr("last_seen_at")
            )
        }
    }
}

data class TimelineEvent(
    val id: String,
    val occurredAt: String,
    val kind: String,
    val title: String,
    val description: String?
) {
    companion object {
        fun fromJson(o: JSONObject) = TimelineEvent(
            id = o.getString("id"),
            occurredAt = o.getStr("occurred_at") ?: "",
            kind = o.getStr("kind") ?: "",
            title = o.getStr("title") ?: "",
            description = o.getStr("description")
        )
    }
}

/** Unauthenticated server identity probe payload (`GET /api/v1/health`). */
data class HealthInfo(
    val status: String,
    val service: String?,
    val version: String?
) {
    companion object {
        fun fromJson(raw: String): HealthInfo {
            val o = JSONObject(raw)
            return HealthInfo(
                status = o.getStr("status") ?: "",
                service = o.getStr("service"),
                version = o.getStr("version")
            )
        }
    }
}