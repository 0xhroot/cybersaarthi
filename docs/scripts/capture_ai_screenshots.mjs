/* Capture genuine AI-feature screenshots for the README gallery.

Phase A (prepare): through the real backend API only — uploads clearly
synthetic evidence (reserved example.* domains, seeded-style fake numbers),
records custody events, and runs the real AI jobs. No fixture files, no
database writes, no mocked responses.

Phase B (capture): Playwright drives the real UI at 1440x900 (light theme,
English) and screenshots each AI capability panel as it renders its own
job results.

Requires:
- backend stack on :8000 (docker compose up -d)
- frontend dev server in real mode on :5173 (VITE_USE_MOCK_API=false)
- Playwright + a local Chrome/Chromium (channel: "chrome") — no browser
  download needed. If playwright is not installed in this repo, point
  PLAYWRIGHT_PATH at an existing playwright package directory.

Run:
    node docs/scripts/capture_ai_screenshots.mjs \
      [--capture-only] [--base http://localhost:5173] [--no-llm]

Writes screenshots to docs/screenshots/web/ and prints per-step PASS/FAIL.
Rerunnable: duplicate uploads (409) and already-active jobs (409) are treated
as success and their existing ids are reused.
*/
import { mkdirSync } from "node:fs";
import path from "node:path";

// Playwright is an optional, capture-time-only dependency (it is not part of
// the application). Resolve it from the normal module graph first (which
// honours NODE_PATH), then fall back to PLAYWRIGHT_PATH pointing at an
// existing playwright package directory or entry file.
let chromium;
try {
  const { createRequire } = await import("node:module");
  const { pathToFileURL } = await import("node:url");
  const require_ = createRequire(import.meta.url);
  const target = process.env.PLAYWRIGHT_PATH ?? "playwright";
  const entry = require_.resolve(target); // honours NODE_PATH for directories
  const mod = await import(pathToFileURL(entry).href);
  chromium = mod.chromium ?? mod.default?.chromium;
} catch (err) {
  console.error(
    `playwright not found (${err.message.split("\n")[0]}).\n` +
      "Install it in this repo (npm i -D playwright), or run with\n" +
      "NODE_PATH=<dir containing playwright> or PLAYWRIGHT_PATH=<playwright\n" +
      "package directory or index.js>.",
  );
  process.exit(1);
}
if (!chromium) {
  console.error("playwright resolved but exports no chromium launcher");
  process.exit(1);
}

const arg = (name, fallback = null) => {
  const hit = process.argv.find((a) => a.startsWith(`${name}=`));
  return hit ? hit.slice(name.length + 1) : fallback;
};

const BASE = arg("--base", "http://localhost:5173");
const API = arg("--api", "http://localhost:8000/api/v1");
const OUT = path.resolve(arg("--out", "docs/screenshots/web"));
// --no-llm skips the two steps that need live generation (assistant chat and
// report-audit drafting); panels that display already-computed artifacts are
// still captured, so the gallery stays genuine either way.
const USE_LLM = !process.argv.includes("--no-llm");

const USERNAME = process.env.CS_USERNAME ?? "investigator";
const PASSWORD = process.env.CS_PASSWORD ?? "investigator-dev-password";

const PONZI_TITLE = "Ponzi investment racket";
const results = [];

function record(name, ok, note = "") {
  results.push({ name, ok, note });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${note ? ` — ${note}` : ""}`);
}

let token = null;

async function api(pathname, { method = "GET", body, form, expect = null } = {}) {
  const headers = { Authorization: `Bearer ${token}` };
  let payload;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${API}${pathname}`, { method, headers, body: payload });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON response — surfaced through expect */
  }
  if (expect && !expect.includes(res.status)) {
    throw new Error(`${method} ${pathname} -> ${res.status} ${text.slice(0, 300)}`);
  }
  return { status: res.status, json, text };
}

/** Login and resolve the showcase Ponzi case (visible to investigator). */
async function bootstrap() {
  const login = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  if (!login.ok) throw new Error(`login failed: ${login.status} ${await login.text()}`);
  token = (await login.json()).access_token;

  const cases = await api(`/cases?limit=100`, { expect: [200] });
  const ponzi = (cases.json.items ?? []).find((c) => c.title === PONZI_TITLE);
  if (!ponzi) throw new Error(`showcase case "${PONZI_TITLE}" not found`);
  return ponzi.id;
}

/** Find an evidence file by filename inside a case (for reruns). */
async function findEvidence(caseId, filename) {
  const list = await api(`/cases/${caseId}/evidence?limit=100`, { expect: [200] });
  return (list.json.items ?? []).find((e) => e.original_filename === filename) ?? null;
}

/**
 * Upload one clearly synthetic evidence file. All content uses IANA-reserved
 * documentation domains (example.com/org/net) and seeded-style fake numbers.
 */
async function uploadSynthetic(caseId, filename, content, dataSource = "txt") {
  const existing = await findEvidence(caseId, filename);
  if (existing) return existing.id;

  const form = new FormData();
  form.append("file", new Blob([content], { type: "text/plain" }), filename);
  form.append("data_source", dataSource);
  const res = await api(`/cases/${caseId}/evidence`, { method: "POST", form, expect: [201, 409] });
  if (res.status === 409) {
    const again = await findEvidence(caseId, filename);
    if (again) return again.id;
  }
  return res.json.id;
}

/** Poll the case intel jobs list until nothing is pending/queued/running. */
async function waitForJobs(caseId, timeoutMs = 240_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const jobs = await api(`/cases/${caseId}/evidence-intelligence/jobs?limit=100`, { expect: [200] });
    // "pending" is the submit response's initial state — missing it would let
    // prepare return while jobs are still in the queue.
    const active = (jobs.json.items ?? []).filter((j) => ["pending", "queued", "running"].includes(j.status));
    if (active.length === 0) return;
    if (Date.now() > deadline) throw new Error(`jobs still active after ${timeoutMs / 1000}s`);
    await new Promise((r) => setTimeout(r, 3000));
  }
}

/** Submit one intel job; an already-active job (409) counts as success. */
async function submit(caseId, suffix, body) {
  const res = await api(`/cases/${caseId}/evidence-intelligence/${suffix}`, {
    method: "POST",
    body: body ?? {},
    expect: [202, 409],
  });
  return res.status === 202;
}

/* ------------------------------------------------------------------ */
/* Phase A — prepare genuine demo data through the real API            */
/* ------------------------------------------------------------------ */

const HINDI_COMPLAINT = `complaint_ref: SHOW-2026-005-C1
Shikayat: Mujhe ek farzi loan app se call aaya jisme processing fees ke naam par 4500 rupaye ki mang ki gayi.
मुझे एक फर्जी लोन ऐप से कॉल आया जिसमें प्रोसेसिंग फीस के नाम पर 4500 रुपये की मांग की गई। आरोपी ने खुद को बैंक अधिकारी बताया।
phone mentioned: +91-90000-00007
account mentioned: 40210088773
`;

const URL_REFS = `GET http://secure-login.example.com/verify?id=88123
GET http://account.example.com.update-verify.example.org/login
GET https://user@example.org/session/restore?token=demo
GET http://example.net:8443/profile/confirm
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)
referer: http://example.com/
`;

// Two rows sharing a transaction anchor with a differing amount give the
// deterministic contradiction engine something real to evaluate (the seeded
// showcase data alone contains no conflicting claims), and the date columns
// give the reconstruction engine source timestamps to propose. Reserved
// numbers only, uploaded through the real API like every other file here.
const TXN_DISCREPANCY = `txn_ref,transfer_date,amount,currency,status,account_no
TXN-994251,2026-10-11T09:15:00+05:30,45000.00,INR,completed,40210088773
TXN-994251,2026-10-11T09:15:00+05:30,47500.00,INR,completed,40210088773
TXN-994252,2026-10-12T14:40:00+05:30,12000.00,INR,failed,40210088773
`;

// Two name-only person mentions (fuzz 80: above the 78 review threshold but
// below ingest's auto-merge score of 0.85*80=68) stay distinct entities, so
// the resolution job has a genuine near-duplicate pair to propose. No
// identifier columns on purpose: disjoint identifiers would reject the pair.
const ENTITY_REVIEW = `person_name
Ramesh Kumar Verma
Ramesh Verma
`;

// The same account number as the anchor case's complaint evidence, dropped
// into a second authorized case: cross-case discovery then finds a real
// shared-identifier group instead of an empty result.
const SHARED_LINK = `account_no,phone,name,txn_ref
40210088773,+91-90000-00007,Apex Trading LLP,TXN-994251
`;

async function prepare(caseId) {
  // 1. Synthetic evidence for the multilingual and triage panels.
  const complaintId = await uploadSynthetic(caseId, "showcase_complaint_hindi.txt", HINDI_COMPLAINT);
  const urlsId = await uploadSynthetic(caseId, "showcase_url_refs.txt", URL_REFS);
  // Deterministic engines need something real to find: a transaction anchor
  // with a conflicting amount (contradiction), source dates (reconstruction)
  // and a name-only near-duplicate (resolution candidates).
  const txnId = await uploadSynthetic(caseId, "showcase_txn_discrepancy.csv", TXN_DISCREPANCY, "csv");
  const reviewId = await uploadSynthetic(caseId, "showcase_entity_review.csv", ENTITY_REVIEW, "csv");
  record("upload synthetic complaint, url, txn-discrepancy and entity evidence",
    Boolean(complaintId && urlsId && txnId && reviewId));

  // 2. Ingest them (sync pipeline, as the app itself runs it).
  for (const [label, id] of [
    ["complaint", complaintId],
    ["url refs", urlsId],
    ["txn discrepancy", txnId],
    ["entity review", reviewId],
  ]) {
    const res = await api(`/cases/${caseId}/ingest`, {
      method: "POST",
      body: { evidence_file_id: id },
      expect: [200, 202, 409],
    });
    record(`ingest ${label}`, res.status !== 500);
  }

  // 3. Custody chronology on the seeded statements file (collected →
  //    transferred → verified, with a hash re-check against stored bytes).
  const statements = await findEvidence(caseId, "showcase_statements.txt");
  const custody = await api(`/cases/${caseId}/evidence/${statements.id}/custody`, {
    expect: [200],
  });
  if ((custody.json.events ?? []).length === 0) {
    const detail = await api(`/cases/${caseId}/evidence/${statements.id}`, { expect: [200] });
    const sha = detail.json.sha256;
    const events = [
      {
        event_type: "collected",
        occurred_at: "2026-10-12T09:15:00Z",
        collector: "Field Team Alpha",
        location: "Nagpur field office",
        method: "on-device capture",
        notes: "Synthetic showcase custody chain.",
      },
      {
        event_type: "transferred",
        occurred_at: "2026-10-12T14:40:00Z",
        transferor: "Field Team Alpha",
        recipient: "Forensics Desk",
        method: "signed handover",
      },
      {
        event_type: "verified",
        occurred_at: "2026-10-13T08:05:00Z",
        collector: "Forensics Desk",
        recorded_sha256: sha,
        notes: "Hash re-verified on receipt.",
      },
    ];
    for (const ev of events) {
      const res = await api(`/cases/${caseId}/evidence/${statements.id}/custody-events`, {
        method: "POST",
        body: ev,
        expect: [201, 409],
      });
      if (res.status >= 500) throw new Error(`custody event ${ev.event_type} failed: ${res.text}`);
    }
  }
  record("record custody chain (collected/transferred/verified)", true);

  // 4. Evidence-level AI jobs.
  await submit(caseId, "extract", { evidence_file_id: statements.id });
  await submit(caseId, "multilingual", { evidence_file_id: complaintId, translate: false });
  await submit(caseId, "triage", { evidence_file_id: urlsId });

  // 5. Case-level AI jobs + custody audit + cross-case discovery.
  await submit(caseId, "entity-resolution");
  await submit(caseId, "timeline-reconstruction");
  await submit(caseId, "contradiction-detection");
  await submit(caseId, "financial-flow");
  await api(`/cases/${caseId}/evidence-integrity/custody-audit`, {
    method: "POST",
    body: {},
    expect: [200, 202, 409],
  });

  const other = (await api(`/cases?limit=100`, { expect: [200] })).json.items.filter(
    (c) => c.title.startsWith("Synthetic KYC") || c.title.startsWith("Digital lending"),
  );
  // Discovery only groups *shared* identifiers, and the seeded cases share
  // none — plant the anchor case's account number in one other authorized
  // case (same synthetic values, real API) so the run finds a real group.
  if (other.length > 0) {
    const linkId = await uploadSynthetic(other[0].id, "showcase_shared_link.csv", SHARED_LINK, "csv");
    const res = await api(`/cases/${other[0].id}/ingest`, {
      method: "POST",
      body: { evidence_file_id: linkId },
      expect: [200, 202, 409],
    });
    record(`ingest shared-identifier link into ${other[0].title}`, res.status !== 500);
  } else {
    record("ingest shared-identifier link", true, "skipped (no second showcase case)");
  }
  await api(`/cross-case/discover`, {
    method: "POST",
    body: { anchor_case_id: caseId, case_ids: [caseId, ...other.map((c) => c.id)] },
    expect: [200, 202, 409],
  });
  record("submit evidence-level, case-level, custody and cross-case jobs", true);

  // 6. Report audit over a draft that embeds a real entity name, so the
  //    auditor has verifiable claims to check. Claim extraction is a bounded
  //    LLM call, so this step is skipped under --no-llm.
  if (USE_LLM) {
    const audits = await api(`/cases/${caseId}/report-audits`, { expect: [200] });
    if ((audits.json.items ?? []).length === 0) {
      const entities = await api(`/cases/${caseId}/entities?limit=3`, { expect: [200] });
      const name = entities.json.items?.[0]?.display_name ?? "the primary subject";
      const draft =
        `Investigation summary (synthetic showcase draft). The ${PONZI_TITLE} network ` +
        `centres on ${name}. Statement records link the group to repeated consignment ` +
        `payments. Cross-case review against the Synthetic KYC loan fraud ring is advised.`;
      const res = await api(`/cases/${caseId}/report-audits`, {
        method: "POST",
        body: { draft_text: draft },
        expect: [201, 202, 409],
      });
      if (res.status >= 500) throw new Error(`report audit failed: ${res.text}`);
    }
    record("queue AI report audit", true);
  } else {
    record("queue AI report audit", true, "skipped (--no-llm)");
  }

  await waitForJobs(caseId);
  record("all intel jobs reached a terminal state", true);
}

/* ------------------------------------------------------------------ */
/* Phase B — capture the UI at 1440x900                                */
/* ------------------------------------------------------------------ */

async function capture(caseId) {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "light",
    locale: "en-US",
  });
  await context.addInitScript(() => {
    localStorage.setItem("cybersaarthi-theme", "light");
    localStorage.setItem("cybersaarthi-language", "en");
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);

  async function shot(name) {
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
    console.log(`  captured ${name}.png`);
  }

  async function shootPanel(target, name) {
    // target: CSS string or a Playwright Locator (use .or() for alternatives —
    // comma-joining a CSS engine with a text engine is not valid).
    // If the target never rendered, fail loudly: screenshotting whatever is
    // on screen would silently commit a mislabeled panel (this happened once
    // for ai-report-audit, which duplicates the cross-case shot).
    const el = (typeof target === "string" ? page.locator(target) : target).first();
    const present = await el.count().then((n) => n > 0).catch(() => false);
    if (!present) {
      record(`capture ${name}`, false, "target panel not found — skipped");
      return;
    }
    await el.scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(600);
    await shot(name);
  }

  // Login through the real form.
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("Enter your username").fill(USERNAME);
  await page.getByPlaceholder("Enter your password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  // Redirect target is exactly /app (or /app/...) — match on pathname, not a
  // glob that would require a sub-path.
  await page.waitForURL((url) => url.pathname.startsWith("/app"), { timeout: 30_000 });
  await page.getByTestId("assistant-fab").waitFor({ timeout: 30_000 });
  record("login through UI", true);

  const caseBase = `${BASE}/app/cases/${caseId}`;

  // --- Evidence: extraction + custody (statements file) ---------------
  await page.goto(`${caseBase}/evidence`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "showcase_statements.txt" }).click();
  await page
    .locator('[data-testid="triage-panel"], div')
    .first()
    .waitFor({ timeout: 10_000 })
    .catch(() => {});
  await page.waitForTimeout(1500);
  await shootPanel("text=AI extraction copilot", "ai-extraction");
  await shootPanel("text=Integrity & chain of custody", "ai-custody");

  // --- Evidence: multilingual (Hindi complaint) + triage (url refs) ---
  await page.goto(`${caseBase}/evidence`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "showcase_complaint_hindi.txt" }).click();
  await page.waitForTimeout(2000);
  await shootPanel(
    page
      .locator('[data-testid="analysis-card"]')
      .or(page.getByText("Multilingual complaint intelligence"))
      .first(),
    "ai-multilingual",
  );

  await page.goto(`${caseBase}/evidence`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "showcase_url_refs.txt" }).click();
  await page.waitForTimeout(2000);
  await shootPanel('[data-testid="triage-panel"]', "ai-triage");

  // --- Entities: resolution ------------------------------------------
  await page.goto(`${caseBase}/entities`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await shootPanel("text=Candidate matches", "ai-entity-resolution");

  // --- Timeline: reconstruction --------------------------------------
  await page.goto(`${caseBase}/timeline`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await shootPanel(
    page
      .locator('[data-testid="reconstruction-proposal"]')
      .or(page.getByText("Reconstruction proposals"))
      .first(),
    "ai-timeline-reconstruction",
  );

  // --- Analytics: contradiction, financial flow, cross-case, audit ----
  await page.goto(`${caseBase}/analytics`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  // Exact heading match: the fuzzy "Contradiction" match lands on the
  // "Contradictions & gaps" action button higher in the DOM and screenshots
  // the analytics header instead of the panel. When conflicts exist, anchor
  // on the first conflict card so the claim comparison itself is in frame
  // (heading-only framing leaves the cards below the fold).
  const conflictCards = page.locator('[data-testid="contradiction-candidate"]');
  await shootPanel(
    (await conflictCards.count()) > 0
      ? conflictCards.first()
      : page.getByText("Contradictions", { exact: true }),
    "ai-contradiction-detection",
  );
  await shootPanel('[data-testid="financial-flow-panel"]', "ai-financial-flow");
  // Anchor on the first candidate card when discovery found something, so
  // the shot shows an actual cross-case candidate (not just the scope
  // picker); fall back to the panel top for a genuinely empty result.
  const ccCards = page.locator('[data-testid="cross-case-candidate"]');
  await shootPanel(
    (await ccCards.count()) > 0 ? ccCards.first() : '[data-testid="cross-case-panel"]',
    "ai-cross-case",
  );

  // ReportAuditPanel mounts only inside an in-session report draft
  // (analysis-panel.tsx renders it under `draft`), so drive the real flow:
  // draft the report, then audit *that* draft and wait for the findings card.
  // Without this the selector matches nothing and the shot would silently
  // duplicate whatever panel was already on screen.
  if (USE_LLM) {
    await page.getByTestId("analysis-report-draft").click();
    await page.getByTestId("analysis-draft").waitFor({ timeout: 240_000 });
    // Snapshot the latest audit, click run, then wait for a NEW audit to
    // appear and reach a terminal state. Waiting for the card alone races
    // twice over: the previous terminal audit resolves the wait instantly
    // (observed: the shot captured the new run mid-flight), and the panel
    // only refreshes on a 15s interval, so "running" can linger on screen
    // after the API already reports terminal.
    const auditsLatest = async () => {
      const res = await api(`/cases/${caseId}/report-audits`, { expect: [200] });
      return (res.json.items ?? [])[0] ?? null;
    };
    const auditHasArtifact = async (audit) => {
      if (!audit) return false;
      const res = await api(`/cases/${caseId}/report-audits/${audit.id}`, { expect: [200] });
      return Boolean(res.json.artifact);
    };
    const waitTerminal = async (before, waitForNew) => {
      const deadline = Date.now() + 240_000;
      // No click (or no prior audits) → the current latest is the one to await.
      let sawNew = !before || !waitForNew;
      for (;;) {
        const latest = await auditsLatest();
        if (latest && before && latest.id !== before.id) sawNew = true;
        if (sawNew && latest && !["pending", "running", "queued"].includes(latest.status)) {
          return latest;
        }
        if (Date.now() > deadline) return null;
        await new Promise((r) => setTimeout(r, 3000));
      }
    };
    // A single audit can flake at claim extraction (local model), ending
    // "partial" with 0 claims — the panel then honestly shows the flagged
    // empty card. Re-run like an investigator would, up to 4 times, and
    // shoot an audit that actually extracted claims; if every attempt
    // flakes, the last honest partial result is shot instead.
    const extractedClaims = (audit) => audit?.result_summary?.claims_extracted ?? 0;
    let terminal = null;
    for (let attempt = 1; attempt <= 4; attempt++) {
      const before = await auditsLatest();
      const runAudit = page.getByTestId("report-audit-run");
      const clicked =
        (await runAudit.count()) > 0 && (await runAudit.isEnabled().catch(() => false));
      if (clicked) await runAudit.click();
      terminal = await waitTerminal(before, clicked);
      record(
        `report audit attempt ${attempt} reached a terminal state`,
        Boolean(terminal),
        terminal
          ? `status: ${terminal.status}, claims: ${extractedClaims(terminal)}`
          : "timed out after 240s",
      );
      if (terminal && extractedClaims(terminal) > 0) break;
      if (attempt < 4 && terminal) {
        record(`report audit attempt ${attempt} produced no claims`, true,
          "claim extraction flaked; re-running");
      }
    }
    const hasArtifact = await auditHasArtifact(terminal);
    // Wait for the panel's 15s refetch to catch up: the run button reads
    // "Auditing…" while a job is active and the status badge shows the
    // terminal status afterwards.
    await page
      .getByTestId("report-audit-run")
      .filter({ hasText: /auditing/i })
      .waitFor({ state: "detached", timeout: 30_000 })
      .catch(() => {});
    if (terminal) {
      await page
        .getByTestId("report-audit-panel")
        .getByText(terminal.status, { exact: true })
        .waitFor({ timeout: 30_000 })
        .catch(() => {});
    }
    let card = false;
    if (hasArtifact) {
      card = await page
        .getByTestId("report-audit-card")
        .waitFor({ timeout: 60_000 })
        .then(() => true)
        .catch(() => false);
    }
    record("report draft -> audit findings rendered", card,
      card
        ? `status: ${terminal?.status}, claims: ${extractedClaims(terminal)}`
        : hasArtifact
          ? "audit card did not render in time"
          : "no artifact (claim extraction failed on every attempt)");
    if (card) {
      // Let the "Audit queued" toast auto-dismiss (4s) so it doesn't cover
      // the findings card in the shot.
      await page.waitForTimeout(5000);
      await shootPanel('[data-testid="report-audit-panel"]', "ai-report-audit");
    }
  } else {
    record("capture ai-report-audit", true,
      "skipped (--no-llm: the panel needs an in-session draft)");
  }

  // --- Assistant: a real grounded conversation ------------------------
  await page.goto(caseBase, { waitUntil: "domcontentloaded" }); // overview = index route
  await page.getByTestId("assistant-fab").click();
  const input = page.getByTestId("assistant-input");
  await input.waitFor();
  if (USE_LLM) {
    // The model occasionally emits a tool call with a made-up case id; the
    // tool layer refuses it (correct behaviour), but a README shot should
    // show a grounded answer. Verify the rendered reply and regenerate a
    // bounded number of times instead of screenshotting a refusal.
    const REFUSED = /not accessible|not found|unable to|cannot find|CASE-\d+/i;
    const messages = page.locator('[data-testid="assistant-messages"]');
    const lastAnswer = async () => {
      const articles = messages.locator("article");
      const count = await articles.count();
      return count ? await articles.last().innerText() : "";
    };
    let answer = "";
    const settled = async () => {
      // While generating, the Send button is swapped for "Stop"; its return
      // means the turn finished (or errored) — no stale-match race.
      const send = page.getByTestId("assistant-send");
      await send.waitFor({ state: "detached", timeout: 15_000 }).catch(() => {});
      await send.waitFor({ state: "visible", timeout: 120_000 }).catch(() => {});
    };
    for (let attempt = 0; attempt < 4; attempt++) {
      if (attempt === 0) {
        await input.fill("What are the strongest leads in this case? Answer briefly with sources.");
        await page.getByTestId("assistant-send").click();
      } else {
        // `retry` appears when the turn errored, `regenerate` otherwise.
        const retry = page.getByTestId("assistant-retry");
        await (await retry.count() ? retry : page.getByTestId("assistant-regenerate")).click();
      }
      await settled();
      await page.waitForTimeout(2000);
      answer = await lastAnswer();
      if (answer && !REFUSED.test(answer)) break;
    }
    record("assistant reply is grounded (no refusal)", !REFUSED.test(answer),
      REFUSED.test(answer) ? "still a refusal after 4 attempts" : "");
  }
  const expand = page.getByTestId("assistant-expand");
  if (await expand.count()) await expand.click();
  await page.waitForTimeout(800);
  await shot("ai-assistant");

  await browser.close();
}

/* ------------------------------------------------------------------ */

async function main() {
  const caseId = await bootstrap();
  console.log(`case: ${caseId}`);
  if (process.argv.includes("--capture-only")) {
    await capture(caseId);
  } else {
    await prepare(caseId);
    await capture(caseId);
  }
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} steps passed`);
  if (failed.length) process.exitCode = 1;
}

main().catch((err) => {
  console.error(`FATAL ${err.message}`);
  process.exitCode = 1;
});
