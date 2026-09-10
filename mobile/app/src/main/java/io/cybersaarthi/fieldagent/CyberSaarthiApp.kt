package io.cybersaarthi.fieldagent

import android.app.Application
import io.cybersaarthi.fieldagent.signature.SignatureEnvelope

class CyberSaarthiApp : Application() {
    override fun onCreate() {
        super.onCreate()
        SignatureEnvelope.generateKeyPairIfAbsent()
    }
}
