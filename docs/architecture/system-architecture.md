# System architecture

The whole platform runs from one `docker compose` stack plus a local AI
runtime. Every arrow below is a real, currently-implemented dependency —
there is no cloud LLM call anywhere in the request path: the backend talks
only to a local `llama-server` process (see [local model setup](deployment-setup.md)).

```mermaid
flowchart LR
    subgraph clients[Clients]
        WEB["Web app<br/>React + Vite :5173"]
        AND["Android agent<br/>offline capture + signing"]
    end

    subgraph stack[docker compose stack]
        API["FastAPI backend<br/>:8000 — auth, RBAC, routes"]
        PG[("PostgreSQL 16<br/>cases · evidence · artifacts")]
        RD[("Redis 7<br/>cache · rate limits")]
        MN[("MinIO / S3<br/>evidence object bytes")]
        NEO[("Neo4j 5<br/>graph projection")]
    end

    subgraph airuntime[Local AI runtime — host process]
        RT["llama-server :8081<br/>llama.cpp + Qwen3-8B Q4_K_M GGUF<br/>API-key protected"]
    end

    WEB -->|HTTPS · JWT| API
    AND -->|device enrolment · signed uploads| API
    API --> PG
    API --> RD
    API --> MN
    API -->|graph sync service| NEO
    API -->|"AIClient (HTTP/UDS, bearer key)<br/>bounded completions only"| RT

    RT -.->|"never reads the database<br/>never bypasses authz"| PG
```

Key properties the diagram encodes:

- **The LLM is not a data source.** `AIClient` sends bounded prompts and
  receives text; every number and id in an answer is verified afterwards by
  the deterministic citation checker (`app/services/citations.py`). The model
  has no database credentials and no route access.
- **Authz is enforced per request.** Every case/evidence route resolves
  membership through `app/services/authorization.py` before any work runs;
  background jobs re-check authorization when they execute, not only at
  submit time.
- **Evidence bytes live in MinIO**, hashes in PostgreSQL; the AI runtime sees
  only extracted text slices that a job explicitly passes to it.

See also: [AI request lifecycle](ai-request-lifecycle.md) and
[deployment and setup](deployment-setup.md).
