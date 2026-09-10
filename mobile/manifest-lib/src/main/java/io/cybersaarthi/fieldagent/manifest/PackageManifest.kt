package io.cybersaarthi.fieldagent.manifest

import io.cybersaarthi.fieldagent.hashing.EvidenceHasher
import io.cybersaarthi.fieldagent.signature.SignatureEnvelope
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant

/**
 * Builds, signs, and verifies the canonical USB package layout.
 *
 *   collection/
 *     manifest.json
 *     manifest.sig
 *     evidence/
 *       001.txt
 *       002.jpg
 *
 * manifest.json canonical form: deterministic JSON with sorted top-level keys,
 * compact separators. Signature is SHA256withRSA over canonical bytes.
 */
object PackageManifest {
    const val SCHEMA_VERSION = "1.0"
    private val CANONICAL_KEYS = listOf(
        "schema_version", "case_id", "device_serial",
        "collection_name", "evidence_files"
    )

    data class EvidenceFile(
        val filename: String,
        val sha256: String,
        val sizeBytes: Long,
        val capturedAt: String,
        val source: String = "field_capture"
    )

    fun buildManifest(
        caseId: String,
        deviceSerial: String,
        collectionName: String,
        evidenceFiles: List<EvidenceFile>,
        agentName: String = "android-field-agent"
    ): String {
        val obj = JSONObject().apply {
            put("schema_version", SCHEMA_VERSION)
            put("case_id", caseId)
            put("device_serial", deviceSerial)
            put("collection_name", collectionName)
            put("generated_at", Instant.now().toString())
            put("generated_by", agentName)
            put("evidence_files", JSONArray().apply {
                evidenceFiles.forEach { ef ->
                    put(JSONObject().apply {
                        put("filename", ef.filename)
                        put("sha256", ef.sha256)
                        put("size_bytes", ef.sizeBytes)
                        put("captured_at", ef.capturedAt)
                        put("source", ef.source)
                    })
                }
            })
        }
        return obj.toString()
    }

    fun canonicalBytes(jsonStr: String): ByteArray {
        val obj = JSONObject(jsonStr)
        val filtered = JSONObject()
        CANONICAL_KEYS.forEach { key ->
            if (obj.has(key)) filtered.put(key, obj.get(key))
        }
        return canonicalDump(filtered).toByteArray(Charsets.UTF_8)
    }

    /** Deterministic JSON dump mirroring Python's json.dumps(sort_keys=True, separators=(",", ":")) */
    private fun canonicalDump(value: Any): String = when (value) {
        is JSONObject -> {
            val keys = value.keys().asSequence().toList().sorted()
            "{" + keys.joinToString(",") { key ->
                "\"${escape(key)}\":${canonicalDump(value.get(key))}"
            } + "}"
        }
        is JSONArray -> {
            val items = (0 until value.length()).map { value.get(it) }
            "[" + items.joinToString(",") { canonicalDump(it) } + "]"
        }
        is String -> "\"${escape(value)}\""
        is Boolean -> if (value) "true" else "false"
        is Int -> value.toString()
        is Long -> value.toString()
        is Double -> {
            if (java.lang.Double.isFinite(value)) value.toString() else "null"
        }
        JSONObject.NULL -> "null"
        else -> {
            val str = value.toString()
            if (str == "null") "null" else "\"${escape(str)}\""
        }
    }

    private fun escape(s: String): String = buildString {
        for (c in s) {
            when (c) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> append(c)
            }
        }
    }

    fun signManifest(canonicalBytes: ByteArray): ByteArray {
        val privateKey = SignatureEnvelope.loadPrivateKey()
        return SignatureEnvelope.sign(privateKey, canonicalBytes)
    }

    fun verifyManifest(manifestJson: String, signatureBytes: ByteArray): Boolean {
        val canonical = canonicalBytes(manifestJson)
        val publicKey = SignatureEnvelope.loadPublicKey()
        return SignatureEnvelope.verify(publicKey, canonical, signatureBytes)
    }

    fun buildPackageDir(
        collectionDir: File,
        manifestJson: String,
        signatureBytes: ByteArray,
        evidenceFiles: List<Pair<File, String>>
    ) {
        val evidenceDir = File(collectionDir, "evidence")
        evidenceDir.mkdirs()
        File(collectionDir, "manifest.json").writeText(manifestJson)
        File(collectionDir, "manifest.sig").writeBytes(signatureBytes)
        evidenceFiles.forEach { (source, targetName) ->
            source.copyTo(File(evidenceDir, targetName), overwrite = true)
        }
    }

    fun hashEvidenceFiles(evidenceDir: File): List<EvidenceFile> {
        return evidenceDir.listFiles()
            ?.filter { it.isFile }
            ?.sortedBy { it.name }
            ?.map { file ->
                EvidenceFile(
                    filename = file.name,
                    sha256 = EvidenceHasher.sha256File(file),
                    sizeBytes = file.length(),
                    capturedAt = Instant.ofEpochMilli(file.lastModified()).toString()
                )
            } ?: emptyList()
    }
}
