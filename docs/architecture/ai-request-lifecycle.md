# AI request lifecycle

Every AI feature — the assistant, the nine analysis panels, the report
auditor — follows the same bounded pipeline. This is the single diagram to
understand "what happens when an investigator presses Run".

```mermaid
sequenceDiagram
    autonumber
    participant U as Investigator (web)
    participant A as FastAPI route
    participant Z as Authorization service
    participant J as AnalysisJob (PostgreSQL)
    participant E as Deterministic engine
    participant M as Local llama-server
    participant V as Citation / rule verifier
    participant R as DerivedArtifact (pending_review)

    U->>A: POST …/evidence-intelligence/<feature>
    A->>Z: re-check case membership + permission
    alt not authorized
        Z-->>U: 401 anonymous / 403 non-member (typed code)
    end
    A->>J: queue bounded job (one active job per feature)
    A-->>U: 202 Accepted {job_id}

    J->>E: run engine (deterministic first)
    E->>E: parse · anchor · compute facts
    E->>M: bounded completion (extracted slice only, token cap)
    M-->>E: model output (text)
    E->>V: verify output against sources
    Note over V: ids/numbers checked · script cross-check<br/>fabrications rejected · unsupported = typed refusal
    V->>R: write artifact status=pending_review + provenance
    R->>J: job succeeded (or typed failure, never silent)

    U->>A: GET …/artifacts / …/jobs (panel polling)
    A-->>U: artifact list with validation_status
    U->>A: POST …/artifacts/{id}/review (approve / reject)
    A->>Z: reviewer permission re-checked
    A->>R: status transition + audit log entry
```

Invariants that hold for all ten capabilities:

1. **Deterministic engines compute; the model only explains.** Numbers,
   hashes, entity matches and flow facts come from Python services, never
   from the LLM.
2. **Nothing auto-applies.** Artifacts land as `pending_review`; approval or
   rejection is a human decision written to the audit log.
3. **Failures are typed.** Disabled feature, unavailable runtime, refusal,
   verification mismatch and timeout each have a distinct code — a failed
   run never renders as an empty success.
4. **Idempotent submission.** A second submit while a job is active returns
   409 `*_ACTIVE` instead of duplicating work; attempts are numbered so a
   retry after failure is safe.

Components: `app/ai/service.py` (bounded completions),
`app/services/analysis_jobs.py` (job rows), `app/services/artifacts.py`
(reviewable artifacts), `app/services/citations.py` (verification).

See also: [evidence ingestion & custody](evidence-ingestion-custody.md).
