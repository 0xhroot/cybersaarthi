# Entity resolution & timeline reconstruction

Both features scan **already-ingested records only** — neither reads raw
files nor asks the model to invent entities or events.

```mermaid
flowchart TD
    subgraph ER[Entity resolution copilot]
        SCAN["Scan for candidates<br/>entity_matching.py"]
        SCAN --> BAND["Deterministic 0–100 similarity band<br/>name · alias · phone · account"]
        BAND --> PAIRS["Candidate pairs (reviewable)"]
        PAIRS -->|"investigator decides"| MERGE["Entity merge / alias link<br/>resolution.py"]
        MERGE --> PROV["Provenance kept:<br/>which records supported the link"]
    end

    subgraph TL[Timeline reconstruction copilot]
        SRC["Source-anchored time signals<br/>recorded dates · custody events · call logs"]
        SRC --> ORDER["Deterministic ordering<br/>timeline.py — no invented times"]
        ORDER --> PROP["Timeline proposal artifact<br/>(pending_review)"]
        PROP -->|"investigator reviews"| COMMIT["Commit proposal<br/>→ timeline_events"]
        COMMIT --> EV["Timeline events linked<br/>back to source record ids"]
    end

    PROV -.->|"resolved entities feed"| SRC
```

Boundaries, stated exactly:

- **Resolution proposes; people decide.** The panel shows a similarity
  *band*, never a confident "these are the same person". Merging is an
  explicit investigator action with the supporting records attached.
- **Reconstruction orders what exists.** Every proposed event cites the
  source record that carries the timestamp; a record without one yields no
  event rather than an estimated one.
- **Commit is auditable.** Committing a proposal writes `timeline_events`
  rows that each retain their source-record id, so the graph view and the
  report can cite them.

Routes: `app/api/routes/case_intelligence.py`
(`…/entity-resolution`, `…/timeline-reconstruction`,
`…/timeline-proposals/{id}/commit`).
Services: `app/services/entity_matching.py`, `resolution.py`, `timeline.py`.

See also: [financial flow & cross-case](financial-flow-cross-case.md).
