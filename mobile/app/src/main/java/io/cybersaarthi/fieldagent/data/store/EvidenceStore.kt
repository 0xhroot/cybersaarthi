package io.cybersaarthi.fieldagent.data.store

import io.cybersaarthi.fieldagent.hashing.EvidenceHasher
import io.cybersaarthi.fieldagent.data.net.getStr
import org.json.JSONObject
import java.util.UUID
import java.io.File
import java.io.FileNotFoundException

/**
 * Offline-first evidence store rooted at an app-private directory.
 *
 * Layout:
 *   <root>/cases/<caseId>/<collectionId>/
 *     collection.meta.json
 *     evidence/<uuid>.<ext>        (immutable original, write-once)
 *     evidence/<uuid>.meta.json    (digest + provenance)
 *     manifest.json / manifest.sig (after sealing)
 *   <root>/packages/<collectionId>-<stamp>/  (sealed package snapshot)
 *
 * The store is pure JVM (no Android APIs) so the core can be unit-tested and
 * the media files are never modified after capture.
 */
class EvidenceStore(val root: File) {

    fun casesDir(): File = File(root, "cases")
    fun collectionDir(caseId: String, collectionId: String): File =
        File(File(casesDir(), caseId), collectionId)

    fun evidenceDir(caseId: String, collectionId: String): File =
        File(collectionDir(caseId, collectionId), "evidence")

    private fun collectionMetaFile(caseId: String, collectionId: String): File =
        File(collectionDir(caseId, collectionId), "collection.meta.json")

    fun initCollection(caseId: String, collectionId: String, name: String): Boolean {
        val dir = collectionDir(caseId, collectionId)
        evidenceDir(caseId, collectionId).mkdirs()
        if (collectionMetaFile(caseId, collectionId).exists()) return false
        val meta = JSONObject().apply {
            put("id", collectionId)
            put("case_id", caseId)
            put("name", name)
            put("created_at", java.time.Instant.now().toString())
            put("status", CollectionStatus.CAPTURING.code)
            put("status_message", JSONObject.NULL)
        }
        collectionMetaFile(caseId, collectionId).writeText(meta.toString())
        return true
    }

    fun collection(caseId: String, collectionId: String): LocalCollection? {
        val file = collectionMetaFile(caseId, collectionId)
        if (!file.exists()) return null
        val o = JSONObject(file.readText())
        return LocalCollection(
            id = o.getString("id"),
            caseId = o.getString("case_id"),
            name = o.getStr("name") ?: "",
            createdAt = o.getStr("created_at") ?: "",
            status = CollectionStatus.fromCode(o.getStr("status") ?: "captured"),
            statusMessage = o.getStr("status_message")
        )
    }

    fun setStatus(caseId: String, collectionId: String, target: CollectionStatus, message: String? = null) {
        val current = collection(caseId, collectionId) ?: return
        if (current.status != target) {
            require(CollectionStatus.canTransition(current.status, target)) {
                "Invalid transition ${current.status} -> $target"
            }
        }
        val file = collectionMetaFile(caseId, collectionId)
        val o = JSONObject(file.readText())
        o.put("status", target.code)
        o.put("status_message", message ?: JSONObject.NULL)
        file.writeText(o.toString())
    }

    fun listCollections(caseId: String): List<LocalCollection> {
        val base = File(casesDir(), caseId)
        if (!base.isDirectory) return emptyList()
        return base.listFiles { f -> f.isDirectory }
            ?.filter { collectionMetaFile(caseId, it.name).exists() }
            ?.map { collection(caseId, it.name)!! }
            ?.sortedByDescending { it.createdAt } ?: emptyList()
    }

    fun evidenceFile(evidence: LocalEvidence, caseId: String, collectionId: String): File =
        File(evidenceDir(caseId, collectionId), evidence.fileName)

    /** Streams a source file into the store (avoids loading large media into RAM). */
    fun writeEvidenceFromFile(
        caseId: String,
        collectionId: String,
        kind: EvidenceKind,
        sourceFile: File,
        originalName: String,
        mimeType: String,
        capturedAt: String,
        capturedBy: String?,
        deviceSerial: String?,
        note: String? = null,
        extra: JSONObject? = null
    ): LocalEvidence {
        val ed = evidenceDir(caseId, collectionId).apply { mkdirs() }
        val id = UUID.randomUUID().toString()
        val fileName = "$id.${kind.defaultExtension()}"
        val target = File(ed, fileName)
        sourceFile.copyTo(target, overwrite = true)
        target.setWritable(false)
        val digest = EvidenceHasher.sha256File(target)
        val ev = LocalEvidence(
            id = id,
            kind = kind,
            fileName = fileName,
            originalName = originalName,
            mimeType = mimeType,
            sizeBytes = target.length(),
            capturedAt = capturedAt,
            sha256 = digest,
            capturedBy = capturedBy,
            deviceSerial = deviceSerial,
            note = note,
            extra = extra
        )
        File(ed, "$fileName.meta.json").writeText(ev.toDetailedJson().toString())
        return ev
    }

    fun writeEvidence(
        caseId: String,
        collectionId: String,
        kind: EvidenceKind,
        contentBytes: ByteArray,
        originalName: String,
        mimeType: String,
        capturedAt: String,
        capturedBy: String?,
        deviceSerial: String?,
        note: String? = null,
        extra: JSONObject? = null
    ): LocalEvidence {
        val ed = evidenceDir(caseId, collectionId).apply { mkdirs() }
        val id = UUID.randomUUID().toString()
        val fileName = "$id.${kind.defaultExtension()}"
        val target = File(ed, fileName)
        target.writeBytes(contentBytes)
        // Original evidence is write-once; future accidental edits are blocked.
        target.setWritable(false)
        val digest = EvidenceHasher.sha256File(target)
        val ev = LocalEvidence(
            id = id,
            kind = kind,
            fileName = fileName,
            originalName = originalName,
            mimeType = mimeType,
            sizeBytes = target.length(),
            capturedAt = capturedAt,
            sha256 = digest,
            capturedBy = capturedBy,
            deviceSerial = deviceSerial,
            note = note,
            extra = extra
        )
        File(ed, "$fileName.meta.json").writeText(ev.toDetailedJson().toString())
        return ev
    }

    fun listEvidence(caseId: String, collectionId: String): List<LocalEvidence> {
        val ed = evidenceDir(caseId, collectionId)
        if (!ed.isDirectory) return emptyList()
        return ed.listFiles { f ->
            f.isFile && f.name.endsWith(".meta.json")
        }?.mapNotNull { f ->
            try {
                LocalEvidence.fromJson(JSONObject(f.readText()))
            } catch (_: Exception) {
                null
            }
        }?.sortedByDescending { it.capturedAt }
            ?: emptyList()
    }

    fun recomputeSha256(caseId: String, collectionId: String, ev: LocalEvidence): String {
        val file = evidenceFile(ev, caseId, collectionId)
        if (!file.exists()) throw FileNotFoundException(ev.fileName)
        return EvidenceHasher.sha256File(file)
    }

    fun deleteEvidence(caseId: String, collectionId: String, ev: LocalEvidence): Boolean {
        val coll = collection(caseId, collectionId) ?: return false
        if (coll.status != CollectionStatus.CAPTURING) return false
        val file = evidenceFile(ev, caseId, collectionId)
        val meta = File(evidenceDir(caseId, collectionId), "${ev.fileName}.meta.json")
        return file.delete() && meta.delete()
    }

    fun ensurePackageRoot(): File = File(root, "packages").apply { mkdirs() }

    fun packageDir(collectionId: String): File {
        val stamp = java.time.Instant.now().toString()
            .replace(":", "").replace(".", "").replace("-", "")
        return File(ensurePackageRoot(), "${collectionId}-$stamp")
    }
}