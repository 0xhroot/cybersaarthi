# SIH showcase data flow

How one synthetic fixture set becomes a fully populated, review-ready
investigation through the real application — the data path behind
`make demo-seed` (see the [presenter guide](../demo/SIH_SHOWCASE.md)).

```mermaid
flowchart LR
    subgraph FIX["Synthetic fixtures (committed, fictional only)"]
        F1["complaint txt · statement csv<br/>ledger json"]
        F2["entity review csv · urls txt<br/>hash csv · support csv"]
    end

    SEED["`make demo-seed`<br/>backend/scripts/showcase_seed.py<br/>public API only · stable-id idempotent"]
    F1 --> SEED
    F2 --> SEED

    SEED -->|"login → POST /api/v1 …<br/>(real authz per request)"| API["FastAPI /api/v1<br/>case access control"]

    API --> ING["ingestion jobs<br/>parse · sha-256 fingerprint"]
    ING --> ENT["entity extraction<br/>rules + NER"]
    ENT --> RES["resolution scoring<br/>→ pending_review"]
    ENT --> TIME["timeline reconstruction<br/>approve → commit"]
    ENT --> FIN["financial flow<br/>5 patterns · 126,699.00"]
    ENT --> XC["cross-case candidates<br/>6 scored links"]
    ING --> TRI["forensic triage<br/>8 observations"]
    ING --> CUST["custody chain<br/>4 events · recompute hash"]
    TIME --> RPT["PDF report<br/>claims cite real ids"]
    RPT --> AUD["report audit<br/>9 claims → deterministic flags"]

    AUD --> REV["Review queue<br/>human approves / rejects"]
    RES --> REV
    TIME --> REV

    MODEL["local llama.cpp server<br/>unix-socket bridge · bounded calls"] -.->|multilingual · triage text<br/>claim extraction| ENT
    MODEL -.-> TRI
    MODEL -.-> AUD

    GRAPH["graph projection (Neo4j)<br/>+ findings · audit log"] --- API

    classDef engine fill:#0f2338,stroke:#3b82f6,color:#e2e8f0
    classDef ai fill:#241a33,stroke:#a78bfa,color:#e9d5ff
    class ING,ENT,RES,TIME,FIN,XC,TRI,CUST,AUD engine
    class MODEL ai
```

Reading it left to right: the seed never touches the database — every arrow
into the app is a normal authenticated request, so ingestion, custody,
findings and reviews behave exactly as they do for a human investigator. The
model server (dashed edges) only ever *explains or extracts under
verification*; every number a reviewer sees (totals, contradictions, custody
hashes) is computed deterministically and would survive the model being off.

## Documentation index

- [All architecture diagrams](README.md)
- [SIH showcase presenter guide](../demo/SIH_SHOWCASE.md)
- [Root README](../../README.md) — quick start, feature map, screenshots
