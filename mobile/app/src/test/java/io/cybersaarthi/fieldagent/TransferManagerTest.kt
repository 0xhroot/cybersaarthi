package io.cybersaarthi.fieldagent

import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.data.store.CollectionStatus
import io.cybersaarthi.fieldagent.data.store.EvidenceKind
import io.cybersaarthi.fieldagent.data.store.EvidenceStore
import io.cybersaarthi.fieldagent.data.store.TransferManager
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlinx.coroutines.runBlocking

class TransferManagerTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private val caseId = "case-x"
    private val collectionId = "coll-x"

    private suspend fun noopSubmit(
        manifest: String,
        signatureBytes: ByteArray,
        files: List<Pair<String, File>>
    ): ImportAccepted = ImportAccepted(caseId, "ANDROID-TEST", files.size, emptyList(), "C")

    private fun buildStore(evidence: List<Pair<EvidenceKind, ByteArray>>): EvidenceStore {
        val st = EvidenceStore(tmp.root)
        st.initCollection(caseId, collectionId, "Scene C")
        evidence.forEachIndexed { i, (kind, bytes) ->
            st.writeEvidence(
                caseId, collectionId, kind, bytes,
                "file_$i.dat", "application/octet-stream",
                "2026-09-11T0${i}:00:00Z", "user-1", "ANDROID-TEST"
            )
        }
        return st
    }

    private fun manager(store: EvidenceStore): TransferManager = TransferManager(
        store = store,
        deviceSerial = { "ANDROID-TEST" },
        sign = { canonical -> canonical + canonical }, // deterministic, verifiable payload
        submit = ::noopSubmit
    )

    @Test
    fun `hashAll verifies digests and advances status`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "a".toByteArray()))
        val m = manager(st)
        val result = m.hashAll(caseId, collectionId)
        assertEquals(1, result.checked)
        assertEquals(0, result.mismatches.size)
        assertEquals(CollectionStatus.HASHED, st.collection(caseId, collectionId)!!.status)
    }

    @Test
    fun `hashAll flags a tampered file as mismatch and fails`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "clean".toByteArray()))
        val ev = st.listEvidence(caseId, collectionId).first()
        ev.let {
            val f = st.evidenceFile(it, caseId, collectionId)
            f.setWritable(true)
            f.writeText("dirty")
            f.setWritable(false)
        }
        val m = manager(st)
        val result = m.hashAll(caseId, collectionId)
        assertEquals(1, result.mismatches.size)
        assertEquals(CollectionStatus.FAILED, st.collection(caseId, collectionId)!!.status)
    }

    @Test
    fun `seal writes canonical manifest and signature snapshot`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "x".toByteArray()))
        val m = manager(st)
        m.hashAll(caseId, collectionId)
        val manifest = m.seal(caseId, collectionId, "Scene C")
        assertTrue(manifest.contains("\"case_id\":\"$caseId\""))
        assertTrue(manifest.contains("\"device_serial\":\"ANDROID-TEST\""))
        assertTrue(manifest.contains(st.listEvidence(caseId, collectionId).first().fileName))
        val dir = st.collectionDir(caseId, collectionId)
        assertTrue(File(dir, "manifest.json").exists())
        assertTrue(File(dir, "manifest.sig").exists())
        assertEquals(CollectionStatus.SEALED, st.collection(caseId, collectionId)!!.status)
    }

    @Test
    fun `packaging snapshots evidence into an immutable package dir`() {
        val st = buildStore(listOf(EvidenceKind.PHOTO to ByteArray(64)))
        val m = manager(st)
        m.hashAll(caseId, collectionId)
        m.seal(caseId, collectionId, "Scene C")
        val pkg = m.packageDir(caseId, collectionId)
        assertTrue(File(pkg, "manifest.json").exists())
        assertTrue(File(pkg, "manifest.sig").exists())
        val files = File(pkg, "evidence").listFiles() ?: emptyArray()
        assertEquals(1, files.size)
        assertEquals(CollectionStatus.PACKAGED, st.collection(caseId, collectionId)!!.status)
    }

    @Test
    fun `submit sends manifest, base64 signature and files to the backend`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "hello".toByteArray()))
        var receivedSig: ByteArray? = null
        var receivedFiles: List<Pair<String, File>>? = null
        var receivedManifest: String? = null
        val m = TransferManager(
            store = st,
            deviceSerial = { "ANDROID-TEST" },
            sign = { canonical -> canonical + canonical },
            submit = { manifest, sigBytes, files ->
                receivedManifest = manifest
                receivedSig = sigBytes
                receivedFiles = files
                noopSubmit(manifest, sigBytes, files)
            }
        )
        m.hashAll(caseId, collectionId)
        m.seal(caseId, collectionId, "Scene C")
        val accepted = runBlocking { m.submitPackage(caseId, collectionId) }
        assertEquals(1, accepted.importedEvidenceCount)
        val expectedFileName = st.listEvidence(caseId, collectionId).first().fileName
        assertEquals(1, (receivedFiles ?: emptyList()).size)
        assertEquals(expectedFileName, (receivedFiles ?: emptyList())[0].first)
        assertTrue((receivedManifest ?: "").contains("ANDROID-TEST"))
        assertNotNull(receivedSig)
        assertTrue((receivedSig ?: ByteArray(0)).isNotEmpty())
        assertEquals(CollectionStatus.SUBMITTED, st.collection(caseId, collectionId)!!.status)
    }

    @Test
    fun `export copies the sealed package layout to a target directory`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "z".toByteArray()))
        val m = manager(st)
        m.hashAll(caseId, collectionId)
        m.seal(caseId, collectionId, "Scene C")
        val target = File(tmp.newFolder("usb"), "export")
        val count = m.exportPackage(caseId, collectionId, target)
        assertEquals(1, count)
        assertTrue(File(target, "manifest.json").exists())
        assertTrue(File(target, "manifest.sig").exists())
        assertTrue(
            File(target, "evidence").listFiles()!!
                .any { it.name == st.listEvidence(caseId, collectionId).first().fileName }
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `submit before sealing is rejected`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "p".toByteArray()))
        val m = manager(st)
        runBlocking { m.submitPackage(caseId, collectionId) }
    }

    @Test
    fun `signature check is false when not sealed yet`() {
        val st = buildStore(listOf(EvidenceKind.NOTE to "q".toByteArray()))
        val m = manager(st)
        assertFalse(m.verifyPackageSignature(caseId, collectionId))
    }
}