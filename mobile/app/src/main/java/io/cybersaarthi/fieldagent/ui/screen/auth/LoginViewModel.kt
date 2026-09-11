package io.cybersaarthi.fieldagent.ui.screen.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.cybersaarthi.fieldagent.AppContainer
import io.cybersaarthi.fieldagent.R
import io.cybersaarthi.fieldagent.data.net.toFieldError
import io.cybersaarthi.fieldagent.ui.resourceId
import kotlinx.coroutines.launch
import java.net.URI

class LoginViewModel(private val container: AppContainer) : ViewModel() {

    var busy by mutableStateOf(false)
        private set
    var errorRes by mutableStateOf<Int?>(null)
        private set
    var signedIn by mutableStateOf(false)
        private set

    val serverUrl: String get() = container.settings.serverUrl

    fun login(username: String, password: String, server: String) {
        if (busy) return
        if (username.isBlank() || password.isBlank()) {
            errorRes = R.string.auth_credentials_required
            return
        }
        val clean = server.trim()
        if (!isValidServerUrl(clean)) {
            errorRes = R.string.auth_server_url_invalid
            return
        }
        viewModelScope.launch {
            busy = true
            errorRes = null
            try {
                val token = container.api.login(username.trim(), password)
                container.settings.serverUrl = clean
                container.session.save(
                    token = token.accessToken,
                    expiresInSeconds = token.expiresIn,
                    userId = token.user.id,
                    username = token.user.username,
                    email = token.user.email,
                    status = token.user.status
                )
                signedIn = true
            } catch (t: Throwable) {
                errorRes = t.toFieldError().resourceId()
            } finally {
                busy = false
            }
        }
    }

    companion object {
        fun isValidServerUrl(value: String): Boolean = try {
            val uri = URI(value)
            (uri.scheme == "http" || uri.scheme == "https") &&
                !uri.host.isNullOrBlank() &&
                !value.contains(' ')
        } catch (_: Exception) {
            false
        }
    }
}