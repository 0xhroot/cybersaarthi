# REAL_MODE_DEMO — Day-of Runbook (CyberSaarthi SIH 2026)

A short, practical playbook for running the full-stack demo against the **real** stack
(no mock adapter). Rehearsed end-to-end on 2026-09-05 — see
`docs/architecture/real-mode-sih-demo-rehearsal.md` for the full evidence pack.

## 0. Quick checkoff before you start

```bash
docker compose ps              # all services healthy: backend, postgres, neo4j, redis, minio
curl -s localhost:8000/api/v1/health    # {"status":"ok",...}
```

## 1. Compute IDs (only once per environment)

- Case id `CASE_ID`:
  `7abf66e2-74c7-441a-a700-10005e7bc754` (creation recorded as **CS-133649C0**)
- Login: `admin` / `admin-dev-password` (admin sees every case; use an investigator only
  if you want to show case-membership access stories).

## 2. Launch the real frontend

```bash
cd frontend
VITE_USE_MOCK_API=false VITE_API_URL=http://localhost:8000 npm run dev
# http://localhost:5173
# Verify the flag took:
#   curl -s localhost:5173 | grep -o "id=\"root\""
```

## 3. Recreate the demo case from scratch (optional, ~45 s)

```bash
python3 docs/scripts/run_sih_seed.py        # creates case, uploads+ingests 3 files, runs analytics
```

It prints the new case id, per-file ingest timings and final counts. Old cases are left
untouched. If you re-seed, replace `CASE_ID` above.

## 4. Live demo script (≈6 min)

| # | What you do on screen | What the judges see | Typical time |
|---|---|---|---|
| 1 | Load `http://localhost:5173/app/cases` (not logged in) | Hard-refresh-safe: login gate, URL preserved | 0.3 s |
| 2 | Sign in as admin | Landed exactly on the route you requested | 0.5 s |
| 3 | Open **SIH 2026 Demonstration…** case | Case overview, status `in_progress` | 1 s |
| 4 | Evidence → show `persons.csv`/`transfers.json`/`associations.txt`, **Inspect** one | Provenance drawer: sha256, stored key, counts, per-source entities/rels/findings | 2 s |
| 5 | Evidence → **Upload record** a small CSV, then **Ingest** on its row | Live upload + ingestion, list refreshes instantly (fixed), timeline gains an entry | 15 s |
| 6 | Entities | 454 real entities, filter by type (person/account/…) | 1 s |
| 7 | Analytics → **Run** (if stale) | Network DNA, communities (38), profile tiers, priority, strength/patterns/hypotheses | 4 s |
| 8 | Findings | 55 findings; open one → approach + source-record provenance | 2–7 s |
| 9 | Graph | Interactive Neo4j-derived network; pan/zoom/click a node | 10 s render here, keep it short |
| 10 | Timeline + Audit | Every action above audit-logged | 2 s |

Power moves: **hard-refresh any page mid-demo** (guaranteed — the router fix), and open a
route you never visited directly (`/app/cases/{id}/graph`) — no dashboard fallback.

## 5. No-mock during the demo

The proof is on the wire: open devtools → Network, filter `fetch:` — every call goes to
`http://localhost:8000/api/v1/*`. Rehearsal captured 173 such calls.

## 6. If something fails on the day

| Symptom | Fix |
|---|---|
| 401/redirect to login everywhere | Token expired (~30 min). Sign in again; or `docker compose restart backend` |
| Evidence upload says duplicate | Content hash already stored → the 409 is *intended* dedupe; upload a file with a new row |
| Backend down | `docker compose up -d && docker compose ps`; give Neo4j ~20 s |
| Graph slow/blank | Wait for the canvas (heavy at 454 entities) or filter the network first |
| Screenshots missing | Re-run rehearsal driver (Playwright 1.62/Chromium 1234), see §7 |

## 7. Automated rehearsal & screenshots

```bash
node docs/scripts/rehearse_sih_demo.mjs   # prints per-step PASS/FAIL; 43 checks
```

Requires `playwright-core@1.62.0` (pins Chromium 1234; 1.63 downloads browser 1243 and is
incompatible with the cached set). Outputs 11 screenshots to
`docs/project-view/screenshots/real-mode/`.

## 8. Post-demo hygiene

- Stop nothing that isn't yours; leave the stack running if judges want a second look.
- To reset demo state: delete the case in the UI (Audit keeps records), then run §3.
- Never commit `.env` contents; local overrides (e.g., `NEO4J_PASSWORD=141`) stay local.