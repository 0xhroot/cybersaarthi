package io.cybersaarthi.fieldagent

import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.data.store.EvidenceKind
import io.cybersaarthi.fieldagent.data.store.EvidenceStore
import io.cybersaarthi.fieldagent.data.store.LocalEvidence
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.Instant

class EvidenceStoreTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private fun store() = EvidenceStore(tmp.root)

    private val caseId = "case-1"
    private val collectionId = "coll-1"

    @Test
    fun `init writes collection meta and keeps it idempotent`() {
        val s = store()
        assertTrue(s.initCollection(caseId, collectionId, "Scene A"))
        assertFalse(s.initCollection(caseId, collectionId, "Scene A"))
        val coll = s.collection(caseId, collectionId)
        assertNotNull(coll)
        assertEquals("Scene A", coll!!.name)
        assertEquals(CollectionStatus.CAPTURING, coll.status)
    }

    @Test
    fun `write evidence persists bytes, meta and a matching digest`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        val ev = s.writeEvidence(
            caseId, collectionId, EvidenceKind.NOTE,
            "hello field".toByteArray(), "note1.txt", "text/plain",
            Instant.parse("2026-09-11T10:00:00Z").toString(), "user-1", "ANDROID-1"
        )
        val file = s.evidenceFile(ev, caseId, collectionId)
        assertTrue(file.exists())
        assertEquals("hello field", file.readText())
        assertEquals(11L, ev.sizeBytes)
        // digest was recorded at capture time
        assertEquals(s.recomputeSha256(caseId, collectionId, ev), ev.sha256)
        // original file was made read-only after capture
        assertFalse(file.canWrite())
    }

    @Test
    fun `list returns items sorted newest first with meta ignoring unknown files`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        s.writeEvidence(
            caseId, collectionId, EvidenceKind.LOCATION,
            """{"lat":1.0}""".toByteArray(), "a.json", "application/geo+json",
            "2026-09-10T10:00:00Z", null, "ANDROID-1"
        )
        s.writeEvidence(
            caseId, collectionId, EvidenceKind.NOTE,
            "b".toByteArray(), "b.txt", "text/plain",
            "2026-09-11T10:00:00Z", "u", "ANDROID-1"
        )
        // stray file that has no meta must not break listing
        File(s.evidenceDir(caseId, collectionId), "orphan.tmp").writeText("x")
        val items = s.listEvidence(caseId, collectionId)
        assertEquals(2, items.size)
        assertEquals("2026-09-11T10:00:00Z", items[0].capturedAt)
    }

    @Test
    fun `writeEvidenceFromFile streams large source and hashes identically`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        val src = File(tmp.newFolder("src"), "movie.mp4")
        src.writeBytes(ByteArray(1_000_000) { (it % 251).toByte() })
        val ev = s.writeEvidenceFromFile(
            caseId, collectionId, EvidenceKind.VIDEO, src, "movie.mp4", "video/mp4",
            Instant.now().toString(), null, "ANDROID-2"
        )
        assertEquals(src.length(), ev.sizeBytes)
        assertEquals(src.length(), s.evidenceFile(ev, caseId, collectionId).length())
        val expected = java.security.MessageDigest.getInstance("SHA-256")
            .digest(src.readBytes()).joinToString("") { "%02x".format(it) }
        assertEquals(expected, ev.sha256)
    }

    @Test
    fun `delete only allowed while capturing`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        val ev = s.writeEvidence(
            caseId, collectionId, EvidenceKind.NOTE, "x".toByteArray(), "x.txt", "text/plain",
            Instant.now().toString(), null, "A"
        )
        s.setStatus(caseId, collectionId, CollectionStatus.HASHED)
        assertFalse(s.deleteEvidence(caseId, collectionId, ev))
        s.setStatus(caseId, collectionId, CollectionStatus.SEALED)
        assertFalse(s.deleteEvidence(caseId, collectionId, ev))
        // roll to capturing via fresh collection
        val c2 = "coll-2"
        s.initCollection(caseId, c2, "C2")
        val ev2 = s.writeEvidence(
            caseId, c2, EvidenceKind.NOTE, "y".toByteArray(), "y.txt", "text/plain",
            Instant.now().toString(), null, "A"
        )
        assertTrue(s.deleteEvidence(caseId, c2, ev2))
        assertEquals(0, s.listEvidence(caseId, c2).size)
    }

    @Test
    fun `status transitions reject invalid sequences`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        s.setStatus(caseId, collectionId, CollectionStatus.HASHED)
        s.setStatus(caseId, collectionId, CollectionStatus.SEALED)
        s.setStatus(caseId, collectionId, CollectionStatus.PACKAGED)
        s.setStatus(caseId, collectionId, CollectionStatus.SUBMITTED)
        assertEquals(CollectionStatus.SUBMITTED, s.collection(caseId, collectionId)!!.status)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `sealing before hashing is rejected`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        s.setStatus(caseId, collectionId, CollectionStatus.SEALED)
    }

    @Test
    fun `corrupted evidence file is detected at verification time`() {
        val s = store()
        s.initCollection(caseId, collectionId, "C")
        val ev = s.writeEvidence(
            caseId, collectionId, EvidenceKind.NOTE, "original".toByteArray(), "n.txt",
            "text/plain", Instant.now().toString(), null, "A"
        )
        s.setStatus(caseId, collectionId, CollectionStatus.HASHED)
        // simulate external tampering (unlock, modify, restore)
        val file = s.evidenceFile(ev, caseId, collectionId)
        file.setWritable(true)
        file.writeText("tampered")
        file.setWritable(false)
        assertFalse(ev.sha256.equals(s.recomputeSha256(caseId, collectionId, ev), ignoreCase = true))
    }
}