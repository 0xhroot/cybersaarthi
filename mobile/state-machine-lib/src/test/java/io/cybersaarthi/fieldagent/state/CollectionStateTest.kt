package io.cybersaarthi.fieldagent.state

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CollectionStateTest {

    @Test
    fun `states have stable codes matching backend enum`() {
        assertEquals("captured", CollectionState.CAPTURED.code)
        assertEquals("hashed", CollectionState.HASHED.code)
        assertEquals("sealed", CollectionState.SEALED.code)
        assertEquals("packaged", CollectionState.PACKAGED.code)
        assertEquals("transferred", CollectionState.TRANSFERRED.code)
        assertEquals("verified", CollectionState.VERIFIED.code)
        assertEquals("imported", CollectionState.IMPORTED.code)
        assertEquals("processed", CollectionState.PROCESSED.code)
        assertEquals("graph_ready", CollectionState.GRAPH_READY.code)
    }

    @Test
    fun `valid transitions succeed`() {
        assertTrue(CollectionState.CAPTURED.canTransitionTo(CollectionState.HASHED))
        assertTrue(CollectionState.HASHED.canTransitionTo(CollectionState.SEALED))
        assertTrue(CollectionState.SEALED.canTransitionTo(CollectionState.PACKAGED))
        assertTrue(CollectionState.PACKAGED.canTransitionTo(CollectionState.TRANSFERRED))
        assertTrue(CollectionState.TRANSFERRED.canTransitionTo(CollectionState.VERIFIED))
        assertTrue(CollectionState.VERIFIED.canTransitionTo(CollectionState.IMPORTED))
        assertTrue(CollectionState.IMPORTED.canTransitionTo(CollectionState.PROCESSED))
        assertTrue(CollectionState.PROCESSED.canTransitionTo(CollectionState.GRAPH_READY))
    }

    @Test
    fun `invalid transitions are rejected`() {
        assertFalse(CollectionState.CAPTURED.canTransitionTo(CollectionState.SEALED))
        assertFalse(CollectionState.CAPTURED.canTransitionTo(CollectionState.GRAPH_READY))
        assertFalse(CollectionState.HASHED.canTransitionTo(CollectionState.HASHED))
        assertFalse(CollectionState.HASHED.canTransitionTo(CollectionState.CAPTURED))
        assertFalse(CollectionState.GRAPH_READY.canTransitionTo(CollectionState.PROCESSED))
    }

    @Test
    fun `state never moves backwards`() {
        val states = CollectionState.entries
        for (from in states) {
            for (to in states) {
                if (to.ordinal <= from.ordinal) {
                    assertFalse(
                        "backwards transition $from -> $to must be rejected",
                        from.canTransitionTo(to)
                    )
                }
            }
        }
    }
}