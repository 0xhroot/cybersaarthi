# Multilingual complaint intelligence & digital forensics triage

```mermaid
flowchart TD
    subgraph ML[Multilingual complaint intelligence]
        UNIT["Complaint text units from<br/>ingested records"]
        UNIT --> SCRIPT["Deterministic Unicode script profile<br/>(Devanagari · Latin · …)"]
        UNIT --> LBL["Model labels the language"]
        LBL --> XCHK["Cross-check: label vs script profile<br/>mismatch → flagged, not trusted"]
        XCHK --> TR["Optional translation<br/>(always for non-English, on request for English)"]
        TR --> ORIG["Original text preserved unchanged"]
        XCHK --> FIELDS2["Source-verified extracted fields"]
        XCHK --> UNSUP["Unsupported script →<br/>typed 422 refusal, 0 artifacts"]
    end

    subgraph FT[Digital forensics triage]
        IN2["Manifest bytes · URL/history/header fields<br/>(URLs are NEVER fetched, nothing is executed)"]
        IN2 --> PROF["Deterministic structural profile<br/>forensic_triage.py"]
        PROF --> OBS["Structural observations only"]
        OBS --> NOTE["No malware or phishing verdict<br/>is ever produced"]
        NOTE --> EXP2["Bounded LLM explanation of<br/>the recorded observations"]
        NOTE --> FLAG["Artifact flagged for review"]
        PROF --> BAD["Unparseable content →<br/>typed failure, never empty success"]
    end
```

Boundaries, verbatim from the implementation:

- **The language label is not trusted on its own.** It is cross-checked
  against the deterministic script profile; a disagreement is surfaced as a
  finding rather than silently corrected.
- **Originals are immutable.** Translation creates a derived artifact; the
  source text and its hash are never rewritten.
- **Triage is structural, not judgemental.** It reports what the bytes and
  headers structurally contain. "This is malware" / "this is a phishing
  site" are outputs the system deliberately cannot produce.
- **No network fetches during triage.** URLs found in evidence are recorded
  and profiled as strings; the service does not resolve or download them.

Routes: `app/api/routes/evidence_intelligence.py`
(`…/multilingual`, `…/triage`).
Services: `app/services/multilingual.py`, `forensic_triage.py`.

See also: [report audit workflow](report-audit.md).
