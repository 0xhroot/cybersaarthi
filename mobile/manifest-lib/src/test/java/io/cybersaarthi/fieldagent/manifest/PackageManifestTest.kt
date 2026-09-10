package io.cybersaarthi.fieldagent.manifest

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.charset.StandardCharsets
import kotlin.io.createTempDir

class PackageManifestTest {

    private val evidence = listOf(
        PackageManifest.EvidenceFile(
            filename = "001.txt",
            sha256 = "aaaa",
            sizeBytes = 42,
            capturedAt = "2026-01-01T00:00:00Z"
        )
    )

    @Test
    fun `manifest contains schema and required fields`() {
        val json = PackageManifest.buildManifest(
            caseId = "case-1",
            deviceSerial = "DEV-001",
            collectionName = "Call Logs",
            evidenceFiles = evidence
        )
        val obj = JSONObject(json)
        assertEquals("1.0", obj.getString("schema_version"))
        assertEquals("case-1", obj.getString("case_id"))
        assertEquals("DEV-001", obj.getString("device_serial"))
        assertEquals("Call Logs", obj.getString("collection_name"))
        assertEquals(1, obj.getJSONArray("evidence_files").length())
    }

    @Test
    fun `canonical bytes are deterministic regardless of key order`() {
        val a = PackageManifest.buildManifest(
            caseId = "case-1", deviceSerial = "D", collectionName = "C", evidenceFiles = evidence
        )
        val canonicalA = PackageManifest.canonicalBytes(a)
        val permuted = JSONObject(a).toString().reversed() // mutate representation
        val canonicalB = PackageManifest.canonicalBytes(permuted)
        assertEquals(
            String(canonicalA, StandardCharsets.UTF_8),
            String(canonicalB, StandardCharsets.UTF_8)
        )
    }

    @Test
    fun `canonical bytes do not include generated_at or generated_by`() {
        val json = PackageManifest.buildManifest(
            caseId = "case-1", deviceSerial = "D", collectionName = "C", evidenceFiles = evidence
        )
        val canonical = String(PackageManifest.canonicalBytes(json), StandardCharsets.UTF_8)
        assertTrue(!canonical.contains("generated_at"))
        assertTrue(!canonical.contains("generated_by"))
    }

    @Test
    fun `hash evidence files lists and hashes directory contents`() {
        val dir = createTempDir()
        try {
            File(dir, "a.txt").writeText("alpha")
            File(dir, "b.txt").writeText("beta")
            val files = PackageManifest.hashEvidenceFiles(dir)
            assertEquals(2, files.size)
            assertEquals(listOf("a.txt", "b.txt"), files.map { it.filename })
            assertEquals(40L, files.map { it.sizeBytes }.sum())
        } finally {
            dir.deleteRecursively()
        }
    }
}