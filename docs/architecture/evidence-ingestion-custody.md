# Evidence ingestion & chain of custody

Two features share this path: the **ingestion copilot** (structured
extraction with page-aware AI assistance) and the **integrity / custody
audit** (hash verification plus a deterministic custody rule set).

```mermaid
flowchart TD
    UP[Upload evidence file<br/>POST /cases/{id}/evidence] --> FP["Fingerprint<br/>SHA-256 of stored bytes"]
    FP --> DUP{Duplicate<br/>in case?}
    DUP -->|yes| REFUSE["409 duplicate — original kept"]
    DUP -->|no| OBJ["Bytes → MinIO<br/>hash + metadata → PostgreSQL"]

    OBJ --> ING["Ingest job<br/>POST /cases/{id}/ingest"]
    ING --> PARSE["Deterministic parsers<br/>csv · json · txt (parsing.py)"]
    PARSE --> NORM["Normalisation<br/>normalization.py"]
    NORM --> ENT["Entity + relationship extraction<br/>relationships.py → entities / relationships"]
    NORM --> AIEX["AI extraction copilot<br/>page-aware, bounded slices"]
    AIEX --> VER["Verified against the page text"]
    VER --> ART["DerivedArtifact (pending_review)"]

    OBJ -.-> HV{"Integrity check"}
    HV -->|"re-hash stored bytes"| CMP{"compare_hashes<br/>stored vs recorded"}
    CMP -->|match| OK["verified"]
    CMP -->|mismatch| FLAG["typed integrity finding"]

    OBJ --> CE["Custody events (append-only)<br/>collected · transferred · sealed · verified …"]
    CE --> AUD["Custody audit<br/>deterministic rule set v1.0.0"]
    AUD --> FIND["custody_finding artifacts<br/>severity · missing fields · event ids"]
    FIND --> EXPL["Bounded LLM explanation<br/>explains the finding, cannot add one"]
```

Notes that matter in review:

- **Hashes are computed on the stored bytes**, not on the upload stream, so
  integrity is re-checkable at any time (`Verify integrity` in the UI).
- **Custody events are append-only.** Each event type has required party
  fields enforced by policy (`CUSTODY_FIELD_REQUIRED`); timestamps must
  carry an explicit time zone and cannot be in the future.
- **The custody rule set is deterministic.** The model may write a plain
  explanation of a finding but can never introduce, dismiss or re-severity
  a finding.
- **Deletion is never an option in this path** — evidence is archived, not
  removed, and every state change is an audit-log row.

Routes: `app/api/routes/evidence.py`, `evidence_integrity.py`.
Services: `app/services/ingestion.py`, `integrity.py`, `custody.py`,
`evidence_extraction.py`.

See also: [entity resolution & timeline](entity-resolution-timeline.md).
