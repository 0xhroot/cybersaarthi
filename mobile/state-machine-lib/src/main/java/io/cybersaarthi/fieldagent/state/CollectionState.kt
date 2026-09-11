package io.cybersaarthi.fieldagent.state

/**
 * Deterministic collection lifecycle state machine.
 * States match the backend Collection.status enum exactly.
 */
enum class CollectionState(val code: String) {
    CAPTURED("captured"),
    HASHED("hashed"),
    SEALED("sealed"),
    PACKAGED("packaged"),
    TRANSFERRED("transferred"),
    VERIFIED("verified"),
    IMPORTED("imported"),
    PROCESSED("processed"),
    GRAPH_READY("graph_ready");

    companion object {
        private val predecessors: Map<CollectionState, Set<CollectionState>> = mapOf(
            CAPTURED to emptySet(),
            HASHED to setOf(CAPTURED),
            SEALED to setOf(HASHED),
            PACKAGED to setOf(SEALED),
            TRANSFERRED to setOf(PACKAGED),
            VERIFIED to setOf(TRANSFERRED),
            IMPORTED to setOf(VERIFIED),
            PROCESSED to setOf(IMPORTED),
            GRAPH_READY to setOf(PROCESSED),
        )

        fun canTransition(from: CollectionState, to: CollectionState): Boolean {
            return from in (predecessors[to] ?: emptySet())
        }

        fun nextStates(current: CollectionState): Set<CollectionState> {
            return predecessors.filter { (_, preds) -> current in preds }.keys
        }
    }

    fun canTransitionTo(target: CollectionState): Boolean = canTransition(this, target)
    fun validNext(): Set<CollectionState> = nextStates(this)
}
