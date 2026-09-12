package io.cybersaarthi.fieldagent.data.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

sealed interface AuthState {
    data object Anonymous : AuthState
    data class Active(
        val accessToken: String,
        val expiresAtEpochMillis: Long,
        val username: String,
        val userId: String,
        val userEmail: String?,
        val userStatus: String
    ) : AuthState
}

/** Encrypted-at-rest holder for the access token and the signed-in user. */
class SessionManager(context: Context) {

    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "cybersaarthi_session",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private val _state = MutableStateFlow<AuthState>(load())
    val state: StateFlow<AuthState> = _state.asStateFlow()

    fun current(): AuthState? = _state.value.takeIf { it is AuthState.Active }

    fun save(token: String, expiresInSeconds: Long, userId: String, username: String, email: String?, status: String) {
        val expiresAt = System.currentTimeMillis() + expiresInSeconds.coerceAtLeast(0) * 1000L
        prefs.edit()
            .putString("access_token", token)
            .putLong("expires_at", expiresAt)
            .putString("user_id", userId)
            .putString("username", username)
            .putString("user_email", email.orEmpty())
            .putString("user_status", status)
            .apply()
        _state.value = AuthState.Active(
            accessToken = token,
            expiresAtEpochMillis = expiresAt,
            userId = userId,
            username = username,
            userEmail = email,
            userStatus = status
        )
    }

    fun clear() {
        prefs.edit().clear().apply()
        _state.value = AuthState.Anonymous
    }

    fun isExpired(auth: AuthState.Active): Boolean =
        System.currentTimeMillis() > auth.expiresAtEpochMillis

    private fun load(): AuthState {
        val token = prefs.getString("access_token", null) ?: return AuthState.Anonymous
        val expiresAt = prefs.getLong("expires_at", 0L)
        val userId = prefs.getString("user_id", null) ?: return AuthState.Anonymous
        val username = prefs.getString("username", null) ?: return AuthState.Anonymous
        return AuthState.Active(
            accessToken = token,
            expiresAtEpochMillis = expiresAt,
            userId = userId,
            username = username,
            userEmail = prefs.getString("user_email", null)?.takeIf { !it.isNullOrBlank() },
            userStatus = prefs.getString("user_status", null) ?: "active"
        )
    }
}