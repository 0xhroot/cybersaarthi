# Architecture diagrams

Every diagram in this folder was drawn from the implementation as it exists
today — each one names real modules, real routes and real services, and links
back to them. Mermaid renders natively on GitHub and in most Markdown
previewers; no extra tooling is needed.

| Diagram | Shows | Read it when |
|---------|-------|--------------|
| [System architecture](system-architecture.md) | Clients, compose stack, local AI runtime and who may talk to whom | You want the big picture first |
| [AI request lifecycle](ai-request-lifecycle.md) | What happens after an investigator presses **Run**: authz → job → deterministic engine → bounded LLM → verification → reviewable artifact | You are reviewing or extending any AI feature |
| [Evidence ingestion & custody](evidence-ingestion-custody.md) | Fingerprinting, parsing, AI extraction copilot, hash verification, append-only custody events and the deterministic custody rule set | You touch uploads, integrity or chain of custody |
| [Entity resolution & timeline](entity-resolution-timeline.md) | Similarity *bands* (never auto-merge) and source-anchored timeline proposals (never invented times) | You work on entities or the timeline |
| [Financial flow & cross-case](financial-flow-cross-case.md) | Deterministic money-flow computation, verified-edge tracing, explicitly-scoped cross-case discovery | You work on analytics or linkage |
| [Multilingual & forensics triage](multilingual-forensics.md) | Script cross-checking, immutable originals, structural-only triage with no verdicts and no URL fetching | You work on complaints or triage |
| [Report audit](report-audit.md) | Claim extraction (model) vs verification (deterministic), and the human approve/reject step | You work on the report auditor |
| [Deployment & setup](deployment-setup.md) | Compose stack, local llama-server, startup order, health checks, model acquisition and clean shutdown | You are setting up or deploying |

## Rules the whole system follows

These invariants appear in nearly every diagram, because they are enforced in
every path:

1. **The LLM is never a source of truth.** Deterministic engines compute
   facts; the model explains them. Every model-produced number or id is
   verified against sources before it can render.
2. **The LLM cannot bypass authorization.** It holds no credentials and no
   route access; each request and each background job re-checks case
   membership itself.
3. **Nothing auto-applies.** AI output lands as a `pending_review` artifact;
   approval is a human decision recorded in the audit log.
4. **Failures are typed, never silent.** A disabled feature, an unavailable
   runtime, a refusal, a verification mismatch and a timeout each have a
   distinct code, and an empty success is treated as a bug.
5. **Originals are immutable.** Evidence bytes and source text are never
   rewritten; every derivation is a new, provenance-carrying artifact.

## Documentation index

- [All project documentation](../README.md)
- [Root README](../../README.md) — quick start, feature map, screenshots
- [AI feature status matrix](../ai/FEATURE_STATUS.md) — the ten capabilities with their routes, panels, tests and measured limits
- [Local model setup](../ai/LOCAL_MODEL_SETUP.md) · [troubleshooting](../ai/TROUBLESHOOTING.md) · [evaluation](../ai/EVALUATION.md)
