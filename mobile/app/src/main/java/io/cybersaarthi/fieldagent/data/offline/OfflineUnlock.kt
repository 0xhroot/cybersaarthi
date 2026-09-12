package io.cybersaarthi.fieldagent.data.offline

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/**
 * Offline work gate. The operator may set a local passphrase that must be
 * entered (in OFFLINE mode, or before sealing) to prove it is the same field
 * operator. The passphrase is stored only as a PBKDF2-HMAC-SHA256 hash inside
 * [EncryptedSharedPreferences] (Keystore-encrypted at rest); it is never kept
 * in plaintext. When no passphrase is configured the gate is open by default.
 */
class OfflineUnlock(context: Context) {

    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "cybersaarthi_offline",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private val _unlocked = MutableStateFlow(!isEnabled())
    val unlocked: StateFlow<Boolean> = _unlocked.asStateFlow()

    /**
     * Configures or replaces the local passphrase. Returns false when the value
     * does not meet the minimum strength policy. Clears the gate state.
     */
    fun setPassphrase(passphrase: String): Boolean {
        val p = passphrase.trim()
        if (p.length < MIN_PASSPHRASE_LENGTH) return false
        val iterations = 120_000
        val salt = generateSaltHex(16)
        val hash = deriveHash(p, salt, iterations)
        prefs.edit()
            .putString("salt", salt)
            .putInt("iterations", iterations)
            .putString("hash", hash)
            .apply()
        _unlocked.value = true
        return true
    }

    fun unlock(passphrase: String): Boolean {
        if (!isEnabled()) {
            _unlocked.value = true
            return true
        }
        val salt = prefs.getString("salt", null) ?: return false
        val iterations = prefs.getInt("iterations", 0)
        val stored = prefs.getString("hash", null) ?: return false
        val candidate = deriveHash(passphrase.trim(), salt, iterations)
        val ok = MessageDigestBytes.equal(stored, candidate)
        if (ok) _unlocked.value = true
        else _unlocked.value = false
        return ok
    }

    fun lock() {
        _unlocked.value = !isEnabled()
    }

    /** Removes the passphrase entirely, returning the store to unlocked. */
    fun clearPassphrase() {
        prefs.edit().remove("salt").remove("iterations").remove("hash").apply()
        _unlocked.value = true
    }

    fun isEnabled(): Boolean = prefs.contains("salt")

    companion object {
        const val MIN_PASSPHRASE_LENGTH = 6

        fun generateSaltHex(bytes: Int = 16): String =
            ByteArray(bytes).also { SecureRandom().nextBytes(it) }
                .joinToString("") { "%02x".format(it) }

        /** Pure PBKDF2-HMAC-SHA256 derivation, unit-testable on the JVM. */
        fun deriveHash(passphrase: String, saltHex: String, iterations: Int): String {
            val salt = saltHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            val spec = PBEKeySpec(passphrase.toCharArray(), salt, iterations, 256)
            val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
            val bytes = factory.generateSecret(spec).encoded
            return bytes.joinToString("") { "%02x".format(it) }
        }
    }
}

private object MessageDigestBytes {
    fun equal(a: String, b: String): Boolean = java.security.MessageDigest.isEqual(
        a.toByteArray(Charsets.US_ASCII), b.toByteArray(Charsets.US_ASCII)
    )
}