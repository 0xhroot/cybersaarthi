package io.cybersaarthi.fieldagent.sync

import io.cybersaarthi.fieldagent.manifest.PackageManifest
import java.io.File

/**
 * Manages the collection-to-package-to-USB transfer lifecycle.
 * Called after a collection reaches the PACKAGED state.
 */
object SyncManager {

    data class SyncResult(val success: Boolean, val message: String, val packageDir: File?)

    fun buildPackage(
        collectionDir: File,
        caseId: String,
        deviceSerial: String,
        collectionName: String
    ): SyncResult {
        val evidenceDir = File(collectionDir, "evidence")
        if (!evidenceDir.exists() || evidenceDir.listFiles()?.isEmpty() == true) {
            return SyncResult(false, "No evidence files found in collection", null)
        }
        val evidenceFiles = PackageManifest.hashEvidenceFiles(evidenceDir)
        val manifestJson = PackageManifest.buildManifest(
            caseId = caseId,
            deviceSerial = deviceSerial,
            collectionName = collectionName,
            evidenceFiles = evidenceFiles
        )
        val canonical = PackageManifest.canonicalBytes(manifestJson)
        val signature = PackageManifest.signManifest(canonical)

        val packageDir = File(collectionDir.parentFile, "${collectionName}_package")
        PackageManifest.buildPackageDir(
            collectionDir = packageDir,
            manifestJson = manifestJson,
            signatureBytes = signature,
            evidenceFiles = evidenceDir.listFiles()
                ?.filter { it.isFile }
                ?.sortedBy { it.name }
                ?.map { it to it.name } ?: emptyList()
        )

        return SyncResult(true, "Package built: ${packageDir.absolutePath}", packageDir)
    }

    fun exportToUsb(packageDir: File, usbMount: File): SyncResult {
        if (!usbMount.exists() || !usbMount.isDirectory) {
            return SyncResult(false, "USB mount point not accessible", null)
        }
        val target = File(usbMount, packageDir.name)
        target.mkdirs()
        packageDir.copyRecursively(target, overwrite = true)
        return SyncResult(true, "Exported to USB: ${target.absolutePath}", target)
    }
}