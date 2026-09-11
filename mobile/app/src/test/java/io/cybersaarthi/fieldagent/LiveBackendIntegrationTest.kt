package io.cybersaarthi.fieldagent

import io.cybersaarthi.fieldagent.data.net.ApiClient
import io.cybersaarthi.fieldagent.data.net.AuthToken
import io.cybersaarthi.fieldagent.data.net.FieldApi
import io.cybersaarthi.fieldagent.manifest.PackageManifest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.net.Socket
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.Signature
import java.util.Base64
import kotlinx.coroutines.runBlocking

/**
 * Live end-to-end test against the running backend (http://localhost:8000).
 *
 * Exercises the exact classes the field agent ships: OkHttp-backed [ApiClient],
 * [FieldApi] DTO parsing, manifest-lib packaging and the multipart import
 * endpoint. Skips (assumption) when the backend is not reachable, so regular
 * offline `gradle test` runs stay green.
 */
class LiveBackendIntegrationTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private val base = "http://localhost:8000"

    @Test
    fun `live round trip login device approval hashed sealed package import`() {
        org.junit.Assume.assumeTrue("backend not reachable on localhost:8000", reachable())

        val token: AuthToken = runBlocking { FieldApi(ApiClient({ base })).login("admin", "admin-dev-password") }
        assertNotNull(token.accessToken)

        runBlocking {
            val api = FieldApi(ApiClient({ base }))
            val cases = api.listCases(token.accessToken)
            assertTrue("seed data should contain at least one case", cases.isNotEmpty())
            val caseId = cases[0].id
            val collectionName = "it-collection-${System.currentTimeMillis()}"

            // --- register the device with a freshly minted RSA key ---
            val kp = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
            val pemBody = String(Base64.getMimeEncoder(76, "\n".toByteArray()).encode(kp.public.encoded))
            val publicKeyPem = "-----BEGIN PUBLIC KEY-----\n$pemBody\n-----END PUBLIC KEY-----"
            val serial = "ANDROID-IT-${System.currentTimeMillis()}"
            val device = api.registerDevice(
                token.accessToken, caseId, "android_mobile", serial, "Unit Test",
                publicKeyPem = publicKeyPem
            )
            assertEquals("pending", device.status)

            // --- approve (admin manages users) ---
            val approvePath = "/api/v1/cases/$caseId/devices/${device.id}/approve"
            val approvedRaw = apiClientRaw(token).requestJson("POST", approvePath, body = "{}", token = token.accessToken)
            assertTrue(approvedRaw.contains("\"approved\""))
            assertTrue(api.listDevices(token.accessToken, caseId).any { it.id == device.id && it.status == "approved" })

            // --- create a collection and import a packaged evidence file ---
            val collection = api.createCollection(token.accessToken, caseId, collectionName)
            val bytes = ByteArray(2048).also { SecureRandom().nextBytes(it) }
            val file = File(tmp.newFolder("evidence"), "it-scene1.jpg")
            file.writeBytes(bytes)

            val sha = MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it) }
            val manifest = PackageManifest.buildManifest(
                caseId = caseId,
                deviceSerial = serial,
                collectionName = collectionName,
                evidenceFiles = listOf(
                    PackageManifest.EvidenceFile(
                        filename = file.name,
                        sha256 = sha,
                        sizeBytes = bytes.size.toLong(),
                        capturedAt = "2026-09-11T00:00:00Z",
                        source = "photo"
                    )
                )
            )
            val canonical = PackageManifest.canonicalBytes(manifest)
            val signature = Signature.getInstance("SHA256withRSA").run {
                initSign(kp.private)
                update(canonical)
                sign()
            }
            val accepted = api.importPackage(
                token.accessToken, caseId, manifest, signature, listOf(file.name to file)
            )
            assertEquals(collectionName, accepted.collectionName)
            assertEquals(1, accepted.importedEvidenceCount)
            assertTrue(accepted.evidenceIds.isNotEmpty())
            val ids = api.listEvidence(token.accessToken, caseId).map { it.id }
            assertTrue(accepted.evidenceIds.all { id -> id in ids })
            val collections = api.listCollections(token.accessToken, caseId)
            assertTrue(collections.any { it.id == collection.id })
        }
    }

    private fun reachable(): Boolean = runCatching {
        Socket().use { it.connect(java.net.InetSocketAddress("localhost", 8000), 400); it.close() }
        true
    }.getOrDefault(false)

    private suspend fun apiClientRaw(token: AuthToken) = ApiClient({ base })
}