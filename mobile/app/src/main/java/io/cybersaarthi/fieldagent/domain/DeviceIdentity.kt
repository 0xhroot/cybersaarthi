package io.cybersaarthi.fieldagent.domain

import io.cybersaarthi.fieldagent.hashing.EvidenceHasher
import io.cybersaarthi.fieldagent.signature.SignatureEnvelope

/**
 * Device identity bound to the Android hardware-backed Keystore.
 *
 * The serial is derived from the public key, so it is stable for the lifetime
 * of the key and cannot collide across devices. Enrollment registers the
 * public key with the case; every sealed package is signed with the same key.
 */
object DeviceIdentity {

    fun ensureKeyPair() = SignatureEnvelope.generateKeyPairIfAbsent()

    val serial: String by lazy {
        ensureKeyPair()
        val pub = SignatureEnvelope.loadPublicKey()
        val digest = EvidenceHasher.sha256Hex(pub.encoded)
        "ANDROID-" + digest.take(16).uppercase()
    }

    val keyFingerprint: String by lazy {
        ensureKeyPair()
        val pub = SignatureEnvelope.loadPublicKey()
        EvidenceHasher.sha256Hex(pub.encoded)
    }

    fun publicKeyPem(): String {
        ensureKeyPair()
        return SignatureEnvelope.publicKeyPem(SignatureEnvelope.loadPublicKey())
    }

    fun sign(data: ByteArray): ByteArray {
        ensureKeyPair()
        return SignatureEnvelope.sign(SignatureEnvelope.loadPrivateKey(), data)
    }
}