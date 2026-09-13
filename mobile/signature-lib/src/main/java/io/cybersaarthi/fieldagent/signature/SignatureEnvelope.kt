package io.cybersaarthi.fieldagent.signature

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.security.spec.X509EncodedKeySpec

/**
 * RSA-2048 + SHA-256 signing via Android Keystore.
 * Generates, stores, loads, and signs with device-bound keypairs.
 */
object SignatureEnvelope {

    private const val KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "cybersaarthi_evidence_key"
    private const val SIGNATURE_ALGO = "SHA256withRSA"

    fun generateKeyPairIfAbsent(): KeyPair {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        if (ks.containsAlias(KEY_ALIAS)) {
            val priv = ks.getEntry(KEY_ALIAS, null) as KeyStore.PrivateKeyEntry
            return KeyPair(
                java.security.KeyFactory.getInstance("RSA")
                    .generatePublic(java.security.spec.X509EncodedKeySpec(priv.certificate.publicKey.encoded)),
                priv.privateKey
            )
        }
        val kpg = KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_RSA, KEYSTORE
        )
        kpg.initialize(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
            )
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
                .setKeySize(2048)
                .setUserAuthenticationRequired(false)
                .build()
        )
        return kpg.generateKeyPair()
    }

    fun sign(privateKey: PrivateKey, data: ByteArray): ByteArray {
        val sig = Signature.getInstance(SIGNATURE_ALGO)
        sig.initSign(privateKey)
        sig.update(data)
        return sig.sign()
    }

    fun verify(publicKey: PublicKey, data: ByteArray, signatureBytes: ByteArray): Boolean {
        val sig = Signature.getInstance(SIGNATURE_ALGO)
        sig.initVerify(publicKey)
        sig.update(data)
        return sig.verify(signatureBytes)
    }

    fun publicKeyPem(publicKey: PublicKey): String {
        val b64 = java.util.Base64.getMimeEncoder()
            .encode(publicKey.encoded)
            .toString(Charsets.UTF_8)
            .replace("\r", "").replace("\n", "")
        return "-----BEGIN PUBLIC KEY-----\n$b64\n-----END PUBLIC KEY-----"
    }

    fun loadPrivateKey(): PrivateKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        return (ks.getEntry(KEY_ALIAS, null) as KeyStore.PrivateKeyEntry).privateKey
    }

    fun loadPublicKey(): PublicKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        return ks.getCertificate(KEY_ALIAS)?.publicKey
            ?: throw IllegalStateException("Key not generated yet")
    }
}
