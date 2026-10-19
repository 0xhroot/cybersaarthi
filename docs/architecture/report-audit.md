# AI report auditing workflow

```mermaid
sequenceDiagram
    autonumber
    participant I as Investigator
    participant P as Report audit panel
    participant A as POST /cases/{id}/report-audits
    participant X as Claim extractor (bounded LLM)
    participant S as Source verifier (deterministic)
    participant AR as report_claim_review artifact
    participant R as Reviewer decision

    I->>P: paste/edit a draft (or use an assistant draft)
    P->>A: submit { draft_text } — exactly one source
    Note over A: conversation_id+message_id XOR draft_text;<br/>original draft is never modified
    A-->>P: 202 audit queued

    A->>X: extract checkable claims (capped count)
    X-->>A: claim list (text spans only)
    loop each claim
        A->>S: verify claim against case sources
        S-->>A: supported / contradicted / unverifiable + citation ids
    end
    A->>AR: write findings (pending_review)

    P->>A: GET /report-audits/{audit_id}
    A-->>P: claims + verdicts + citations
    I->>R: approve or reject each claim (note required on reject)
    R->>AR: decision recorded in audit log
```

What the auditor **cannot** do, by construction:

- It never edits, files or publishes the report — approval and rejection
  are human decisions recorded in the audit log.
- It never grades its own work: claim extraction is the model, verification
  is deterministic source matching, so a "supported" verdict always carries
  the record ids that support it.
- A draft submitted by two routes (assistant draft or pasted text) is
  treated identically; the stored draft is immutable, and re-auditing
  creates a new audit rather than mutating an old one.

Routes: `app/api/routes/report_audits.py`.
Service: `app/services/report_audit.py`.
UI: `frontend/src/components/ai/report-audit-panel.tsx` (rendered inside the
analysis panel on the Analytics page).

See also: [deployment & local model setup](deployment-setup.md).
