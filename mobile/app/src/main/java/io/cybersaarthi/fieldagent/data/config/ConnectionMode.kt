package io.cybersaarthi.fieldagent.data.config

/**
 * User-chosen operating mode of the field agent.
 *
 * [ONLINE]  the agent talks to a trusted CyberSaarthi server (online/paired).
 * [OFFLINE] the agent works fully disconnected against local evidence only
 *           (field mode), without any server dependency.
 */
enum class ConnectionMode { ONLINE, OFFLINE }
