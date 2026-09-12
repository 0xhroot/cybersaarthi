package io.cybersaarthi.fieldagent.data.net

import io.cybersaarthi.fieldagent.domain.DeviceIdentity
import org.json.JSONObject
import java.io.File

private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

/** Typed facade over [ApiClient] for the endpoints the field agent uses. */
class FieldApi(private val client: ApiClient) {

    /** Unauthenticated health probe, used to verify server identity and reachability. */
    suspend fun health(): HealthInfo {
        val raw = client.requestJson("GET", "/api/v1/health")
        return HealthInfo.fromJson(raw)
    }

    /**
     * Challenge-response device key proof: signs [data] client-side and asks the
     * server whether the signature verifies against the registered device key.
     * The server expects both fields as UTF-8 strings / hex, not base64.
     */
    suspend fun verifyDeviceKey(
        token: String,
        caseId: String,
        deviceId: String,
        data: String,
        signature: ByteArray
    ): Boolean {
        val body = JSONObject().apply {
            put("data", data)
            put("signature", signature.toHex())
        }
        val raw = client.requestJson(
            "POST", "/api/v1/cases/$caseId/devices/$deviceId/verify-key",
            body.toString(), token
        )
        return JSONObject(raw).optBoolean("valid", false)
    }

    /**
     * Approved-device liveness beacon. Signs the canonical heartbeat message
     * with the device key and reports it to the server, which records the
     * last-seen timestamp when the signature verifies against the device key.
     */
    suspend fun heartbeat(
        token: String,
        caseId: String,
        deviceId: String,
        timestampEpochMillis: Long
    ): DeviceHeartbeatResult {
        val canonical = HeartbeatMessage.build(caseId, deviceId, timestampEpochMillis)
        val signature = DeviceIdentity.sign(canonical.toByteArray(Charsets.UTF_8))
        val body = JSONObject().apply {
            put("timestamp_epoch_ms", timestampEpochMillis)
            put("signature", signature.toHex())
        }
        val raw = client.requestJson(
            "POST", "/api/v1/cases/$caseId/devices/$deviceId/heartbeat",
            body.toString(), token
        )
        return DeviceHeartbeatResult.fromJson(raw)
    }

    suspend fun login(username: String, password: String): AuthToken {
        val body = JSONObject().apply {
            put("username", username)
            put("password", password)
        }
        val raw = client.requestJson("POST", "/api/v1/auth/login", body.toString())
        return AuthToken.fromJson(raw)
    }

    suspend fun me(token: String): UserOut {
        val raw = client.requestJson("GET", "/api/v1/auth/me", token = token)
        return UserOut.fromJson(JSONObject(raw).getJSONObject("user"))
    }

    suspend fun logout(token: String) {
        client.requestJson("POST", "/api/v1/auth/logout", token = token)
    }

    suspend fun listCases(token: String): List<CaseOut> {
        val raw = client.requestJson("GET", "/api/v1/cases?limit=200", token = token)
        return parsePage(raw) { CaseOut.fromJson(it) }
    }

    suspend fun getCase(token: String, caseId: String): CaseOut {
        val raw = client.requestJson("GET", "/api/v1/cases/$caseId", token = token)
        return CaseOut.fromJson(JSONObject(raw))
    }

    suspend fun listCollections(token: String, caseId: String): List<CollectionOut> {
        val raw = client.requestJson(
            "GET", "/api/v1/cases/$caseId/collections?limit=500", token = token
        )
        return parsePage(raw) { CollectionOut.fromJson(it) }
    }

    suspend fun createCollection(
        token: String,
        caseId: String,
        name: String,
        description: String? = null
    ): CollectionOut {
        val body = JSONObject().apply {
            put("name", name)
            put("description", description ?: JSONObject.NULL)
        }
        val raw = client.requestJson(
            "POST", "/api/v1/cases/$caseId/collections",
            body.toString(), token
        )
        return CollectionOut.fromJson(JSONObject(raw))
    }

    suspend fun listEvidence(token: String, caseId: String): List<EvidenceSummary> {
        val raw = client.requestJson(
            "GET", "/api/v1/cases/$caseId/evidence?limit=200", token = token
        )
        return parsePage(raw) { EvidenceSummary.fromJson(it) }
    }

    suspend fun listDevices(token: String, caseId: String): List<DeviceOut> {
        val raw = client.requestJson(
            "GET", "/api/v1/cases/$caseId/devices?limit=100", token = token
        )
        return parsePage(raw) { DeviceOut.fromJson(it) }
    }

    suspend fun registerDevice(
        token: String,
        caseId: String,
        platform: String,
        serial: String,
        model: String?,
        publicKeyPem: String
    ): DeviceOut {
        val body = JSONObject().apply {
            put("platform", platform)
            put("serial", serial)
            put("model", model ?: JSONObject.NULL)
            put("public_key", publicKeyPem)
            put("signature_algorithm", "RSA-SHA256")
        }
        val raw = client.requestJson(
            "POST", "/api/v1/cases/$caseId/devices",
            body.toString(), token
        )
        return DeviceOut.fromJson(JSONObject(raw))
    }

    suspend fun importPackage(
        token: String,
        caseId: String,
        manifestJson: String,
        signatureBytes: ByteArray,
        files: List<Pair<String, File>>
    ): ImportAccepted {
        val raw = client.requestMultipart(
            method = "POST",
            path = "/api/v1/cases/$caseId/import/packages",
            files = files.map { (name, file) -> "files" to file },
            blobs = listOf(
                Triple("manifest", "manifest.json", manifestJson.toByteArray()),
                Triple("manifest_signature", "manifest.sig", signatureBytes)
            ),
            token = token
        )
        return ImportAccepted.fromJson(raw)
    }
}