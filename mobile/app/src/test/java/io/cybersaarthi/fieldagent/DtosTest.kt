package io.cybersaarthi.fieldagent

import io.cybersaarthi.fieldagent.data.net.AuthToken
import io.cybersaarthi.fieldagent.data.net.CaseOut
import io.cybersaarthi.fieldagent.data.net.CollectionOut
import io.cybersaarthi.fieldagent.data.net.DeviceOut
import io.cybersaarthi.fieldagent.data.net.EvidenceSummary
import io.cybersaarthi.fieldagent.data.net.FieldError
import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.data.net.parsePage
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.ui.resourceId
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class DtosTest {

    @Test
    fun `login token parses the OpenAPI shape`() {
        val raw = """
            {"access_token":"abc.def.ghi","token_type":"bearer","expires_in":900,
             "user":{"id":"u1","username":"investigator","email":"i@example.com","status":"active"}}
        """.trimIndent()
        val t = AuthToken.fromJson(raw)
        assertEquals("abc.def.ghi", t.accessToken)
        assertEquals(900L, t.expiresIn)
        assertEquals("u1", t.user.id)
        assertEquals("investigator", t.user.username)
        assertEquals("active", t.user.status)
    }

    @Test
    fun `case page parses items with pagination metadata`() {
        val raw = """
            {"items":[{"id":"c1","case_number":"CASE-1","title":"Alpha","description":null,
                       "status":"open","owner_id":"u1","created_at":"2026-01-01T00:00:00Z",
                       "updated_at":"2026-01-01T00:00:00Z"}],
             "total":1,"limit":200,"offset":0}
        """.trimIndent()
        val cases = parsePage(raw) { CaseOut.fromJson(it) }
        assertEquals(1, cases.size)
        assertEquals("CASE-1", cases[0].caseNumber)
        assertEquals("Alpha", cases[0].title)
    }

    @Test
    fun `collection and evidence records parse`() {
        val c = CollectionOut.fromJson(JSONObject("""
            {"id":"k1","case_id":"c1","name":"Scene","description":null,"status":"sealed",
             "sealed_at":"2026-01-02T00:00:00Z","created_at":"x","updated_at":"x"}
        """.trimIndent()))
        assertEquals("sealed", c.status)
        assertEquals("Scene", c.name)

        val e = EvidenceSummary.fromJson(JSONObject("""
            {"id":"e1","original_filename":"a.jpg","sha256":"aa","format":"jpeg",
             "file_size":100,"status":"verified","created_at":"x"}
        """.trimIndent()))
        assertEquals("aa", e.sha256)
        assertEquals(100L, e.fileSize)
    }

    @Test
    fun `device and import accepted parse`() {
        val d = DeviceOut.fromJson(JSONObject("""
            {"id":"d1","case_id":"c1","platform":"android","serial":"ANDROID-A","model":"Pixel",
             "status":"approved","created_at":"x"}
        """.trimIndent()))
        assertEquals("ANDROID-A", d.serial)
        assertEquals("approved", d.status)

        val accepted = ImportAccepted.fromJson("""
            {"case_id":"c1","device_serial":"ANDROID-A","imported_evidence_count":3,
             "evidence_ids":["a","b","c"],"collection_name":"Scene"}
        """.trimIndent())
        assertEquals(3, accepted.importedEvidenceCount)
        assertEquals(listOf("a", "b", "c"), accepted.evidenceIds)
    }

    @Test
    fun `transport failures map to typed domain errors`() {
        assertEquals(FieldError.Network, IOException("boom").toFieldError())
        assertNotNull(FieldError.Unauthorized.asUserMessage())
        assertTrue(FieldError.Unauthorized.resourceId() != 0)
        assertTrue(FieldError.Network.resourceId() != 0)
        assertTrue(FieldError.DevicePending("pending approval").resourceId() != 0)
    }

    @Test
    fun `collection status codes round trip`() {
        assertEquals(io.cybersaarthi.fieldagent.data.store.CollectionStatus.HASHED,
            io.cybersaarthi.fieldagent.data.store.CollectionStatus.fromCode("hashed"))
        assertEquals(io.cybersaarthi.fieldagent.data.store.CollectionStatus.CAPTURING,
            io.cybersaarthi.fieldagent.data.store.CollectionStatus.fromCode("bogus"))
    }
}