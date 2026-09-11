package io.cybersaarthi.fieldagent.data.store

import io.cybersaarthi.fieldagent.data.net.ImportAccepted
import io.cybersaarthi.fieldagent.manifest.PackageManifest
import java.io.File

data class HashResult(val checked: Int, val mismatches: List<String>)

/**
 * End-to-end integrity pipeline for a single collection:
 *
 *   capture -> hashAll (verify) -> seal (manifest + signature) -> package
 *   -> submit (backend import) |-> export (USB / SAF)
 *
 * Sealing, signing, and verification reuse the audited manifest + keystore
 * libraries so package bytes are identical to the desktop importer layout.
 */
class TransferManager(
    private val store: EvidenceStore,
    private val deviceSerial: () -> String,
    private val sign: (ByteArray) -> ByteArray,
    private val submit: suspend (manifestJson: String, signatureBytes: ByteArray, files: List<Pair<String, File>>) -> ImportAccepted
) {

    /** Re-reads every evidence file and compares digests against capture-time records. */
    fun hashAll(caseId: String, collectionId: String): HashResult {
        val items = store.listEvidence(caseId, collectionId)
        val mismatches = mutableListOf<String>()
        for (ev in items) {
            val actual = store.recomputeSha256(caseId, collectionId, ev)
            if (!actual.equals(ev.sha256, ignoreCase = true)) {
                mismatches.add(ev.fileName)
            }
        }
        if (mismatches.isEmpty()) {
            store.setStatus(caseId, collectionId, CollectionStatus.HASHED)
        } else {
            store.setStatus(caseId, collectionId, CollectionStatus.FAILED, "digest mismatch")
        }
        return HashResult(items.size, mismatches)
    }

    /** Builds the canonical manifest and signs it with the device key. */
    fun seal(caseId: String, collectionId: String, collectionName: String): String {
        val items = store.listEvidence(caseId, collectionId)
        val manifest = PackageManifest.buildManifest(
            caseId = caseId,
            deviceSerial = deviceSerial(),
            collectionName = collectionName,
            evidenceFiles = items.map { ev ->
                PackageManifest.EvidenceFile(
                    filename = ev.fileName,
                    sha256 = ev.sha256,
                    sizeBytes = ev.sizeBytes,
                    capturedAt = ev.capturedAt,
                    source = ev.kind.code
                )
            }
        )
        val canonical = PackageManifest.canonicalBytes(manifest)
        val sig = sign(canonical)
        val dir = store.collectionDir(caseId, collectionId)
        File(dir, "manifest.json").writeText(manifest)
        File(dir, "manifest.sig").writeBytes(sig)
        store.setStatus(caseId, collectionId, CollectionStatus.SEALED)
        return manifest
    }

    fun verifyPackageSignature(caseId: String, collectionId: String): Boolean {
        val dir = store.collectionDir(caseId, collectionId)
        val manifestFile = File(dir, "manifest.json")
        val sigFile = File(dir, "manifest.sig")
        if (!manifestFile.exists() || !sigFile.exists()) return false
        return PackageManifest.verifyManifest(manifestFile.readText(), sigFile.readBytes())
    }

    /** Materialises an immutable package snapshot for USB / server transfer. */
    fun packageDir(caseId: String, collectionId: String): File {
        val src = store.collectionDir(caseId, collectionId)
        val dest = store.packageDir(collectionId)
        dest.mkdirs()
        File(src, "manifest.json").copyTo(File(dest, "manifest.json"), overwrite = true)
        File(src, "manifest.sig").copyTo(File(dest, "manifest.sig"), overwrite = true)
        val evidenceDest = File(dest, "evidence").apply { mkdirs() }
        store.listEvidence(caseId, collectionId).forEach { ev ->
            val f = store.evidenceFile(ev, caseId, collectionId)
            f.copyTo(File(evidenceDest, ev.fileName), overwrite = true)
        }
        store.setStatus(caseId, collectionId, CollectionStatus.PACKAGED)
        return dest
    }

    fun exportPackage(caseId: String, collectionId: String, targetDir: File): Int {
        val src = store.collectionDir(caseId, collectionId)
        require(File(src, "manifest.json").exists()) { "tr_not_sealed" }
        require(File(src, "manifest.sig").exists()) { "tr_not_sealed" }
        targetDir.mkdirs()
        File(src, "manifest.json").copyTo(File(targetDir, "manifest.json"), overwrite = true)
        File(src, "manifest.sig").copyTo(File(targetDir, "manifest.sig"), overwrite = true)
        val evDest = File(targetDir, "evidence").apply { mkdirs() }
        var count = 0
        store.listEvidence(caseId, collectionId).forEach { ev ->
            store.evidenceFile(ev, caseId, collectionId)
                .copyTo(File(evDest, ev.fileName), overwrite = true)
            count++
        }
        return count
    }

    suspend fun submitPackage(caseId: String, collectionId: String): ImportAccepted {
        val dir = store.collectionDir(caseId, collectionId)
        val manifestFile = File(dir, "manifest.json")
        val sigFile = File(dir, "manifest.sig")
        require(manifestFile.exists()) { "tr_not_packaged" }
        require(sigFile.exists()) { "tr_not_packaged" }
        val files = store.listEvidence(caseId, collectionId).map { ev ->
            ev.fileName to store.evidenceFile(ev, caseId, collectionId)
        }
        val signature = sigFile.readBytes()
        val accepted = submit(manifestFile.readText(), signature, files)
        store.setStatus(caseId, collectionId, CollectionStatus.SUBMITTED)
        return accepted
    }
}