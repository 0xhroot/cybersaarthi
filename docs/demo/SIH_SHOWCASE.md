# SIH Showcase — Presenter Guide

End-to-end walkthrough of every CyberSaarthi AI capability through one coherent,
fully synthetic case. Everything in this guide was produced by the real
workflows (`make demo-seed`) and verified against the running application; the
"expected" numbers below are what `make demo-status` and the UI actually show.

> All names, accounts, transactions, phone numbers and hashes in the showcase
> are fictional. No real victims, credentials, evidence or PII are used anywhere.

A 14-shot gallery captured from this exact UI (1440×900) lives in
[`docs/screenshots/sih-showcase/`](../screenshots/sih-showcase/) — re-generate
it any time with `node docs/scripts/capture_sih_showcase.mjs` while the stack,
frontend and model server are up.

---

## 1. What this showcase demonstrates

One fraud investigation, cases **SIH-2026-001** (primary) and **SIH-2026-002**
(labeled support fixture), exercising all ten AI capabilities through genuine
application workflows:

| # | Capability | Where to show it |
|---|------------|------------------|
| 1 | Evidence ingestion & hash integrity | Evidence tab |
| 2 | Entity extraction & resolution review | Entities tab |
| 3 | Timeline reconstruction | Timeline tab |
| 4 | Contradiction detection | Analytics / intelligence panels |
| 5 | Financial flow analysis | Analytics tab |
| 6 | Cross-case pattern candidates | Cross-case panel |
| 7 | Multilingual complaint analysis | Evidence / analysis panels |
| 8 | Forensic triage of indicators | Evidence intelligence |
| 9 | Chain of custody & tamper evidence | Evidence tab (custody) |
| 10 | AI report auditing | Analysis panel (report audit) |

No new AI features were built for this showcase; every capability is the
existing product driven with carefully engineered synthetic data.

## 2. Prerequisites

- The Docker stack (`docker compose up`) — postgres, backend, redis, neo4j,
  minio — all healthy.
- The local model server for AI-backed capabilities (multilingual, triage
  explanations, report audit): `./scripts/ai/run_server.sh` plus the socket
  bridge `./scripts/ai/socket_bridge.sh` (see README "Local AI runtime").
  `make demo-status` prints `model server: … ready=True` when it is reachable.
- Deterministic capabilities (ingestion, entities, resolution scoring,
  timeline reconstruction, contradictions, financial flow, cross-case,
  custody) work with the model server **down**; those steps are attempted and
  reported honestly either way.

## 3. The seed workflow

```bash
make demo-seed     # idempotent: creates anything missing, never duplicates
make demo-status   # read-only per-capability checklist
make demo-reset DEMO_RESET_CONFIRM=sih-showcase   # guarded destructive reset
```

- `demo-seed` authenticates as a real user over the public API — it never
  writes to the database directly. Exit code 0 means every step ended
  `created / existing / skipped`; the printed report lists every step.
- Re-running is always safe: evidence dedupes by filename + sha-256, custody
  and timeline events by normalized UTC instants, jobs by status, the report
  audit by draft hash.
- If the model server is down, AI-backed jobs are reported as `failed` (never
  silently skipped). Bring the model up, then `make demo-seed
  CS_SEED_RETRY_FAILED=1` to retry exactly those steps.
- `demo-reset` refuses without `DEMO_RESET_CONFIRM=sih-showcase`, refuses on
  `APP_ENV=production`, and deletes only the two SIH-2026-xxx cases (rows,
  audit logs, stored objects, graph projections).

## 4. The scenario (brief it before you demo)

A complainant (Ms. Ananya Deshpande, fictional) reported on 2026-04-02 that
an unauthorised debit of **INR 47,500.00** (TXN-SIH-1001, 2026-04-05) left
her **Prism Cooperative Bank** account for beneficiary account ACC-SIH-001
(Ravi Kulkarni). The statement holds six more debits (2026-04-06…2026-04-10),
one row with **no date at all** (TXN-SIH-1007, INR 999.00), and one row with
**no currency** (TXN-SIH-1006, 3,450.00). The merchant wallet ledger settles
the *same* TXN-SIH-1001 at **45,000.00** — the planted contradiction. Alias
rows (`R. Kulkarni` ↔ `Ravi Kulkarni`, `S. Pawar` ↔ `Suresh Pawar`) and a
second merchant name variant (`Sunrise Mercantile Traders Pvt Ltd`) set up
the resolution review. A phishing-lure text file and a hash manifest round
out the exhibits. The complaint itself is written in mixed Hindi/English.

## 5. Evidence inventory (7 exhibits, 6 + 1 support)

| File | Format | Designed signal |
|------|--------|-----------------|
| `complaint_mixed.txt` | txt | Mixed en/hi narrative; dates 2026-04-02/05; cites TXN-SIH-1001 and ACCSIH001 |
| `merchant_statement.csv` | csv | TXN-SIH-1001…1007; duplicate amount 47,500.00 (rows 1001 & 1004); row 1006 has no currency; row 1007 has no date |
| `wallet_ledger.json` | json | TXN-SIH-1001 at 45,000.00 → the amount contradiction |
| `entity_review.csv` | csv | Alias rows with incident dates → resolution candidates |
| `phishing_urls.txt` | txt | URL userinfo, raw IP host, punycode, nonstandard port 8443, mismatched return-path → triage observations |
| `hash_manifest.csv` | csv | Three synthetic sha-256 rows for the forensics manifest path |
| `supporting_payments.csv` (SIH-2026-002) | csv | Shares ACCSIH001 + one phone with the primary case → cross-case candidates |

## 6. Complaint & multilingual analysis

Open the complaint exhibit (Evidence tab → analysis panel). The multilingual
job splits mixed-language units, translates the Hindi material, and preserves
material values (`INR 47,500.00`, dates, account/transaction ids).
**Expected:** 3 extraction artifacts + 3 translation artifacts, source language
recorded as `mixed`, preserved-value checks passing. This step needs the model
server; without it the job fails honestly and can be retried.

## 7. Entity extraction & resolution review

Entities tab: ~25 entities extracted from all exhibits (persons, orgs,
accounts, phones). Two deterministic matches sit in the review queue with
scores in the review band — **approve them live**:

- `R. Kulkarni` → `Ravi Kulkarni` (≈79.5)
- `Sunrise Mercantile Traders Pvt Ltd` → `Sunrise Mercantile Pvt Ltd` (≈78.6)

The seed never auto-approves: every match waits for a human decision. Point
out that org canonicalization already merged the legal-suffix variants.

## 8. Timeline reconstruction & chain of custody

Timeline tab: **26 events** — 13 reconstruction proposals (8 dated transaction
rows + 5 incident-date rows, one per source record, each keeping its source
id), 3 curated narrative events (complaint received, exhibits sealed into
custody, custody verification), and 10 derived system events (case creation,
6 evidence ingests, analytics run, finding, report). Evidence tab →
statement → custody: a real
4-event chain (collected → transferred → received → verified, 2026-04-13/14),
each carrying the recomputed sha-256 of the exhibit. Recompute integrity live
via the evidence-integrity verify action — the hash matches, the chain is
clean (zero custody findings), which is the honest result for untampered data.

## 9. Contradiction detection (the planted conflict)

Analytics / intelligence panels: **exactly one contradiction artifact** —
`contradiction.amount_disagreement`, priority **high**: TXN-SIH-1001 shows
**45,000.00** (wallet ledger) vs **47,500.00** (bank statement), Δ 2,500.
Same field name, same transaction id — the engine reports one conflict, not
two facts. It stays `pending_review`; approve or reject it live.

## 10. Financial flow analysis

Analytics tab (financial flow): the deterministic pass scans **26 source
records**, extracts **14 facts** (9 with a transaction reference, 8 with a
currency, 8 with a timestamp), and buckets them into **2 currency groups** —
INR and one `unknown` (TXN-SIH-1006 has no currency). Five patterns
**fire**, each left `pending_review`:

- `duplicate_amount` — 47,500.00 appears on both TXN-SIH-1001 and TXN-SIH-1004
- `amount_threshold` — threshold 5,000; **7 records** matched across six distinct amounts
- `missing_currency` — TXN-SIH-1006 (the single record in the `unknown` bucket, 3,450.00)
- `missing_timestamp` — TXN-SIH-1007 (the 999.00 statement row with an empty date)
- `victim_loss_unmatched` — the reported loss (47,500.00 INR, victim `ACCVICTIM01`)
  has no transaction-level foreign key; it is matched by exact amount equality
  only, which the engine labels a limitation rather than a fact

Independently checkable totals (add the rows yourself):

- the **Prism Cooperative Bank** bucket holds the 7 statement rows summing to **126,699.00**
- every `completed` record totals **177,299.00** (the 7 statement rows + the wallet's 45,000.00 and 5,600.00)
- the INR bucket's distinct-group total is **81,349.00** — the conflicting
  TXN-SIH-1001 group (45,000.00 vs 47,500.00) is **excluded** from the
  distinct total and surfaced separately, rather than silently picking a side
- in/out/net flow: **not computed** — the engine reports
  `not_computable_no_direction` because no record states a payer→payee
  direction. Absent, never guessed to zero.

The seeded graph-trace call (target `ACCSIH001`, association edges, depth 3)
returns `status=ok` with **9 association paths and 0 matched transaction
facts** — an honest association walk, explicitly not a money trail.

## 11. Cross-case pattern candidates

Cross-case view (anchor SIH-2026-001): **6 candidates**, all honestly scored,
classified by signal kind, and left `pending_review`:

- **80 / 72** — shared account references (`ACC-SIH-001` ↔ `ACCSIH001` normalization)
- **70 / 70** — shared person/merchant names
- **65** — shared phone number (`+91 98200 00001` vs the dashed `+91-98200-00001` variant)
- **15** — a weak name-only similarity, explicitly left for the reviewer

Nothing is merged automatically; the engine ranks, the investigator decides.

## 12. Forensic triage

Evidence intelligence (phishing_urls exhibit): **8 observations** from the
deterministic ruleset — URL userinfo embedding a display name (high), raw-IP
host (high), auth-failure burst (high), punycode host (medium), return-path
mismatch (medium), missing Message-ID (low), and two nonstandard-port:8443
flags (low). With the model up, each observation carries a plain-language
explanation.

## 13. Report audit (the capstone)

Analysis panel → report audit: the seeded draft (1,787 chars) cites the real
evidence and timeline ids and contains **planted defects for the auditor to
catch**. Expected result: `status=succeeded`. The model's claim segmentation
is stochastic — the same seeded draft has split into **9 or 17 claims**
across real runs — but every designed flag fires in either split:

- `numeric_mismatch` (×1) — a claim states 15,300.00 where the source says 12,300.00
- `invalid_citation` (×1–2) — a claim cites a UUID that exists nowhere in the case
- `contradicted` (×3) — narrative claims contradicted by the sources (including the
  125,000.00 arithmetic total vs the real 126,699.00)
- `not_established` — the "director personally approved on 2026-04-04" and
  GST-document claims cite nothing (6–8 medium findings with the counter-evidence
  candidates at info)

As documented below, every claim also carries
`claim_extraction_invalid (char_span)` from the model's offset counting — that
flag describes extraction quality, not the case's evidence.

Review queue: the claim-review artifact is `pending_review` — decisions are
the presenter's to make live.

## 14. Expected outcomes, verification & known limitations

**Verification checklist** (all observed on a clean `make demo-seed`):

- 2 cases (SIH-2026-001 badge "SIH Showcase", SIH-2026-002 badge "Demo fixture")
- 6 parsed exhibits on the primary + 1 on the fixture; `make demo-status`
  prints every capability PRESENT
- 4 custody events, clean integrity; 25 entities; 2 pending resolution
  matches; 26 timeline events; 1 contradiction; 1 financial finding artifact
  with 5 firing patterns; 6 cross-case candidates; 3 translations;
  1 triage artifact (8 observations); 34 findings; 1 PDF report;
  1 succeeded audit (9 or 17 claims depending on the model's claim split;
  the designed defect flags fire either way); 1 presenter member per case
  (investigator account)
- `make demo-seed` re-run: `43 existing, 1 skipped, 0 created`, exit 0
- `make demo-reset` (guarded): both cases gone (rows, audit logs, objects,
  graph nodes), every other case untouched

**Known limitations (honest, documented):**

- Claim spans: the model sometimes paraphrases or miscounts character offsets,
  so claims also carry `claim_extraction_invalid (char_span)` flags. The
  deterministic verdicts (numeric mismatch, invalid citations, contradictions)
  are unaffected and are the showcase's point.
- The phone extraction rule matches any 8+ digit separator-joined group, so a
  few date-shaped strings (`2026-04-10`) appear as phone entities —
  product-wide behaviour on date-bearing evidence, not showcase data damage.
- NER output varies slightly between model runs (e.g., an occasional `INR`
  organization mention); entity lists are therefore not bit-identical across
  fresh seeds.
- The financial trace call is stateless: the seed verifies it on the first
  run only and reports `skipped` afterwards — run it live from the UI.
- The audit's claim-extraction budget was raised (1280 → 4096 output tokens)
  because real replies with UUID citations vary up to >2000 tokens and were
  truncated mid-JSON. Retry semantics (`CS_SEED_RETRY_FAILED=1`) remain the
  documented escape hatch for any residual model-side failure.
- The demo accounts are development credentials (`admin` / `investigator`
  with the README dev passwords); never seed or reset against a production
  deployment (both commands refuse `APP_ENV=production`).
