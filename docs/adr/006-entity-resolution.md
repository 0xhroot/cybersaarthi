# ADR-006: Deterministic entity resolution (blocking + fuzzy + context)

- **Status:** Accepted
- **Date:** Phase 2 (SIH 26189)
- **Decision makers:** backend engineering

## Context

Raw records reference the same real-world person, phone or vehicle with different spellings
("Arjun Mehra" vs. "Arjun Mehta", `+91-98765-43210` vs. `09876543210`). Phase 2 must decide,
per case, whether each extracted mention is a known entity or a new one — deterministically,
cheaply, and without cross-case leakage.

## Decision

Resolution runs only inside a case and never compares against a full-table scan:

1. **Blocking.** Only entities whose `blocking_key` equals the mention's bucket are candidates
   (`MAX_CANDIDATE_TARGETS_PER_KEY = 25` cap). Person buckets use surname prefix + initial
   (`arjun mehra` → `meh_a`), so spelling variants of a surname stay comparable.
2. **Signals.** Exact canonical equality, RapidFuzz `ratio`, and shared-context overlap
   (co-mentioned values from the same source records) are computed per candidate.
3. **Score.** `0.85 × fuzzy_ratio + 0.15 × context_overlap`; exact matches score 100.
4. **Decision.**
   - `AUTO_MATCH` (≥92): link the candidate, record an alias for the variant spelling, merge
     context, create an `entity_match` row.
   - `REVIEW` (78–92): leave the candidate unresolved and file an `entity_match` for the analyst
     review queue.
   - `NO_MATCH` (<78): create a new entity.

The score weights and thresholds are configuration (`RESOLUTION_AUTO_THRESHOLD` /
`RESOLUTION_REVIEW_THRESHOLD`) so they can be tuned per deployment without code changes.

## Consequences

- Deterministic results: identical input + identical database state ⇒ identical decisions.
- Per-case isolation: entities never leak between investigations.
- Surname-prefix blocking means real spelling variants still reach review instead of being
  silently missed, at the cost of occasionally comparing entities that only look-alike.
- Fuzzy matching is `rapidfuzz` (C++) — fast enough for the current data volumes and local
  stack; a distance-index or ML matcher is a later-phase concern if volumes grow.