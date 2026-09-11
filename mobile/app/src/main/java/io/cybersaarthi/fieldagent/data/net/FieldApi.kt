package io.cybersaarthi.fieldagent.data.net

import org.json.JSONObject
import java.io.File

/** Typed facade over [ApiClient] for the endpoints the field agent uses. */
class FieldApi(private val client: ApiClient) {

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