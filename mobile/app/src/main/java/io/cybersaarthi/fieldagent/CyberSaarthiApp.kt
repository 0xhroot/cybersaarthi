package io.cybersaarthi.fieldagent

import android.app.Application

class CyberSaarthiApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(applicationContext)
        container.connectivity.start()
        container.startConnectionProbing()
        container.heartbeat.start()
    }
}