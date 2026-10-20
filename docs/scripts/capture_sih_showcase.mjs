/* Capture genuine SIH showcase screenshots from the real UI.

Unlike capture_ai_screenshots.mjs (which prepares its own data), this script
captures the *seeded* showcase exactly as `make demo-seed` leaves it: cases
SIH-2026-001 (badge "SIH Showcase") and SIH-2026-002 (badge "Demo fixture"),
their exhibits, custody chain, entities, timeline, contradictions, financial
flow, cross-case candidates, findings and the succeeded report audit.

Everything is driven through the real UI at 1440x900 (light theme, English)
with real login; the only non-UI calls are read-only status polls.

Requires:
- backend stack on :8000 (docker compose up -d)
- local model server up (the report-draft step, and --audit's fresh run, are
  real model calls; everything else is deterministic data already seeded)
- `make demo-seed` already run (the script fails loudly if the case is missing)
- frontend dev server in real mode on :5173 (VITE_USE_MOCK_API=false)
- Playwright + a local Chrome/Chromium (channel: "chrome")

Run:
    node docs/scripts/capture_sih_showcase.mjs \
      [--base http://localhost:5173] [--api http://localhost:8000/api/v1] \
      [--out docs/screenshots/sih-showcase] [--audit]

Writes screenshots to --out and prints per-step PASS/FAIL. Without --audit,
the report-audit panel is shot from the seeded succeeded audit; with --audit,
a fresh audit is run live like a presenter would (uses the local model).
*/
import { mkdirSync } from "node:fs";
import path from "node:path";

// Playwright is an optional, capture-time-only dependency (it is not part of
// the application). Resolve it from the normal module graph first (which
// honours NODE_PATH), then fall back to PLAYWRIGHT_PATH.
let chromium;
try {
  const { createRequire } = await import("node:module");
  const { pathToFileURL } = await import("node:url");
  const require_ = createRequire(import.meta.url);
  const target = process.env.PLAYWRIGHT_PATH ?? "playwright";
  const entry = require_.resolve(target);
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
const OUT = path.resolve(arg("--out", "docs/screenshots/sih-showcase"));
const RUN_AUDIT = process.argv.includes("--audit");

const USERNAME = process.env.CS_USERNAME ?? "investigator";
const PASSWORD = process.env.CS_PASSWORD ?? "investigator-dev-password";

const PRIMARY_NUMBER = "SIH-2026-001";
const SUPPORT_NUMBER = "SIH-2026-002";
const results = [];

function record(name, ok, note = "") {
  results.push({ name, ok, note });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${note ? ` — ${note}` : ""}`);
}

let token = null;

async function api(pathname, { method = "GET", expect = null } = {}) {
  const res = await fetch(`${API}${pathname}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
  });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    /* surfaced through expect */
  }
  if (expect && !expect.includes(res.status)) {
    throw new Error(`${method} ${pathname} -> ${res.status} ${text.slice(0, 300)}`);
  }
  return { status: res.status, json, text };
}

/** Login and resolve the seeded showcase cases (fail loudly if missing). */
async function bootstrap() {
  const login = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  if (!login.ok) throw new Error(`login failed: ${login.status} ${await login.text()}`);
  token = (await login.json()).access_token;

  const cases = await api(`/cases?limit=200`, { expect: [200] });
  const primary = (cases.json.items ?? []).find((c) => c.case_number === PRIMARY_NUMBER);
  const support = (cases.json.items ?? []).find((c) => c.case_number === SUPPORT_NUMBER);
  if (!primary || !support) {
    throw new Error(
      `showcase cases ${PRIMARY_NUMBER}/${SUPPORT_NUMBER} not found — run \`make demo-seed\` first`,
    );
  }
  return { primaryId: primary.id, supportId: support.id };
}

async function findEvidence(caseId, filename) {
  const list = await api(`/cases/${caseId}/evidence?limit=100`, { expect: [200] });
  return (list.json.items ?? []).find((e) => e.original_filename === filename) ?? null;
}

async function capture(primaryId, supportId) {
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
    // Fail loudly when the target never rendered: screenshotting whatever is
    // on screen would silently commit a mislabeled panel. Poll for up to 20s
    // so a transient skeleton/refetch window (detail switches to the newest
    // audit on the panel's 15s interval) is not mistaken for absence.
    const el = (typeof target === "string" ? page.locator(target) : target).first();
    let present = false;
    const deadline = Date.now() + 20_000;
    for (;;) {
      present = await el
        .count()
        .then((n) => n > 0)
        .catch(() => false);
      if (present || Date.now() > deadline) break;
      await page.waitForTimeout(500);
    }
    if (!present) {
      record(`capture ${name}`, false, "target panel not found — skipped");
      return;
    }
    // Anchor the target's top just under the sticky breadcrumb/tab strip
    // (scrollIntoViewIfNeeded centers tall cards, cutting off their headers).
    await el.evaluate((e) => e.scrollIntoView({ block: "start" })).catch(() => {});
    await page.evaluate(() => window.scrollBy(0, -150)).catch(() => {});
    await page.waitForTimeout(600);
    await shot(name);
    record(`capture ${name}`, true);
  }

  // Real login through the form.
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("Enter your username").fill(USERNAME);
  await page.getByPlaceholder("Enter your password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((url) => url.pathname.startsWith("/app"), { timeout: 30_000 });
  await page.getByTestId("assistant-fab").waitFor({ timeout: 30_000 });
  record("login through UI", true);

  const caseBase = `${BASE}/app/cases/${primaryId}`;

  // --- Cases list: both showcase badges ---------------------------------
  await page.goto(`${BASE}/app/cases?q=SIH-2026`, { waitUntil: "domcontentloaded" });
  await page.getByText("SIH Showcase").first().waitFor({ timeout: 15_000 });
  await page.waitForTimeout(800);
  await shot("sih-cases-list");
  record("capture sih-cases-list (SIH Showcase + Demo fixture badges)", true);

  // --- Case header with badge -------------------------------------------
  await page.goto(caseBase, { waitUntil: "domcontentloaded" });
  await page.getByText("SIH Showcase").first().waitFor({ timeout: 15_000 });
  await page.waitForTimeout(800);
  await shot("sih-case-overview");
  record("capture sih-case-overview (header badge)", true);

  // --- Evidence: all six exhibits ---------------------------------------
  await page.goto(`${caseBase}/evidence`, { waitUntil: "domcontentloaded" });
  await page
    .getByRole("button", { name: "merchant_statement.csv" })
    .waitFor({ timeout: 15_000 });
  await page.waitForTimeout(1200);
  await shot("sih-evidence");
  record("capture sih-evidence (six parsed exhibits)", true);

  // --- Custody: 4-event chain with recomputed hashes --------------------
  await page.getByRole("button", { name: "merchant_statement.csv" }).click();
  await page.waitForTimeout(2000);
  await shootPanel("text=Integrity & chain of custody", "sih-custody");

  // --- Multilingual: mixed en/hi complaint ------------------------------
  await page.goto(`${caseBase}/evidence`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "complaint_mixed.txt" }).click();
  await page.waitForTimeout(2500);
  await shootPanel(
    page
      .locator('[data-testid="analysis-card"]')
      .or(page.getByText("Multilingual complaint intelligence"))
      .first(),
    "sih-multilingual",
  );

  // --- Forensic triage: phishing URL observations -----------------------
  await page.goto(`${caseBase}/evidence`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "phishing_urls.txt" }).click();
  await page.waitForTimeout(2500);
  await shootPanel('[data-testid="triage-panel"]', "sih-triage");

  // --- Entities + resolution review queue -------------------------------
  await page.goto(`${caseBase}/entities`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await shot("sih-entities");
  record("capture sih-entities", true);
  await shootPanel("text=Candidate matches", "sih-entity-resolution");

  // --- Timeline: committed proposals + curated events -------------------
  await page.goto(`${caseBase}/timeline`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  await shot("sih-timeline");
  record("capture sih-timeline (reconstructed events)", true);

  // --- Analytics: contradiction, financial flow, cross-case --------------
  await page.goto(`${caseBase}/analytics`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  // Anchor on the conflict card itself so the 45,000 vs 47,500 comparison is
  // in frame (heading-only framing leaves the cards below the fold).
  await shootPanel(
    page.locator('[data-testid="contradiction-candidate"]').first(),
    "sih-contradiction",
  );
  await shootPanel('[data-testid="financial-flow-panel"]', "sih-financial-flow");
  await shootPanel(
    page.locator('[data-testid="cross-case-candidate"]').first(),
    "sih-cross-case",
  );

  // --- Findings: analytics output ---------------------------------------
  await page.goto(`${caseBase}/findings`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  await shot("sih-findings");
  record("capture sih-findings", true);

  // --- Report audit: real draft -> audit findings --------------------------
  // ReportAuditPanel mounts only inside AnalysisPanel (analytics tab) and only
  // shows audit findings once a draft is in session, so drive the real flow:
  // open the analytics tab, generate the report draft, then audit it.
  await page.goto(`${caseBase}/analytics`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("analysis-panel").waitFor({ timeout: 30_000 });
  await page.getByTestId("analysis-report-draft").click();
  await page.getByTestId("analysis-draft").waitFor({ timeout: 240_000 });
  if (RUN_AUDIT) {
    const runAudit = page.getByTestId("report-audit-run");
    const clickForAudit = async () => {
      if ((await runAudit.count()) > 0 && (await runAudit.isEnabled().catch(() => false))) {
        await runAudit.click();
      }
    };
    await clickForAudit();
    const card = page.locator('[data-testid="report-audit-card"]').first();
    const deadline = Date.now() + 240_000;
    for (;;) {
      // The panel refreshes on an interval, so re-click a still-enabled Run if a
      // prior terminal audit resolved the wait before the new run registered.
      if ((await card.count()) > 0) break;
      if (Date.now() > deadline) {
        record("live report audit rendered findings", false, "timed out after 240s");
        break;
      }
      await clickForAudit();
      await page.waitForTimeout(3000);
    }
    // Let any queued-toast auto-dismiss so it doesn't cover the card.
    await page.waitForTimeout(5000);
  } else {
    // Seeded audit is already on file; give the panel's refetch interval a
    // moment to render the findings card.
    await page.waitForTimeout(3000);
  }
  await shootPanel('[data-testid="report-audit-card"]', "sih-report-audit");

  await browser.close();
}

async function main() {
  const { primaryId, supportId } = await bootstrap();
  console.log(`primary: ${primaryId} · support: ${supportId}`);
  await capture(primaryId, supportId);
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} steps passed`);
  if (failed.length) process.exitCode = 1;
}

main().catch((err) => {
  console.error(`FATAL ${err.message}`);
  process.exitCode = 1;
});
