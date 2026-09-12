package io.cybersaarthi.fieldagent

import io.cybersaarthi.fieldagent.data.connectivity.ConnectionStatus
import io.cybersaarthi.fieldagent.data.connectivity.HeartbeatBackoff
import io.cybersaarthi.fieldagent.data.connectivity.deviceStatusOf
import io.cybersaarthi.fieldagent.data.net.HeartbeatMessage
import org.junit.Assert.assertEquals
import org.junit.Test

class HeartbeatLogicTest {

    @Test
    fun `canonical heartbeat message matches the backend format`() {
        assertEquals(
            "cybersaarthi-heartbeat/1\ncase_id=case-1\ndevice_id=dev-9\ntimestamp=1700000000123",
            HeartbeatMessage.build("case-1", "dev-9", 1700000000123L)
        )
    }

    @Test
    fun `status mapping derives device level states`() {
        assertEquals(ConnectionStatus.CONNECTED, deviceStatusOf("approved"))
        assertEquals(ConnectionStatus.DEVICE_REVOKED, deviceStatusOf("revoked"))
        assertEquals(ConnectionStatus.DEVICE_UNAPPROVED, deviceStatusOf("pending"))
        assertEquals(ConnectionStatus.DEVICE_UNAPPROVED, deviceStatusOf(null))
        assertEquals(ConnectionStatus.DEVICE_UNAPPROVED, deviceStatusOf("weird"))
        assertEquals(ConnectionStatus.CONNECTED, ConnectionStatus.CONNECTED)
        assert(ConnectionStatus.DEVICE_UNAPPROVED.isServerReachable)
        assert(ConnectionStatus.DEVICE_REVOKED.isServerReachable)
        assert(!ConnectionStatus.SERVER_UNREACHABLE.isServerReachable)
    }

    @Test
    fun `heartbeat cadence is steady on success and backoff on failure`() {
        assertEquals(HeartbeatBackoff.BEAT_INTERVAL_MS, HeartbeatBackoff.nextDelayMs(0))
        assertEquals(HeartbeatBackoff.BEAT_INTERVAL_MS, HeartbeatBackoff.nextDelayMs(1))
        assertEquals(120_000L, HeartbeatBackoff.nextDelayMs(2))
        assertEquals(240_000L, HeartbeatBackoff.nextDelayMs(3))
        assertEquals(480_000L, HeartbeatBackoff.nextDelayMs(4))
        assertEquals(HeartbeatBackoff.MAX_BACKOFF_MS, HeartbeatBackoff.nextDelayMs(5))
        // hard cap at ten minutes regardless of continued failures
        assertEquals(HeartbeatBackoff.MAX_BACKOFF_MS, HeartbeatBackoff.nextDelayMs(999))
        assertEquals(HeartbeatBackoff.MAX_BACKOFF_MS, HeartbeatBackoff.nextDelayMs(1000))
    }
}