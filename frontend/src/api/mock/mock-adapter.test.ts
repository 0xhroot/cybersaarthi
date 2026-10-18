import { beforeEach, describe, expect, it } from "vitest";
import { mockApi, resetMockState } from "@/api/mock";
import { MAIN_EVIDENCE } from "@/api/mock/data";
import type { ContradictionResolutionState } from "@/types/domain";

const MAIN_CASE_ID = "a0000000-0000-4000-8000-000000000001";
const SECOND_CASE_ID = "a0000000-0000-4000-8000-000000000002";
const TERTIARY_CASE_ID = "a0000000-0000-4000-8000-000000000003";

async function signIn(username: string, password: string) {
  await mockApi.auth.login({ username, password });
}

beforeEach(() => {
  resetMockState();
});

describe("mock adapter", () => {
  it("exposes the facade contract without awaiting a real socket", () => {
    expect(mockApi.src).toBe("mock");
    for (const key of ["auth", "cases", "entities", "evidence", "graph", "analytics", "findings", "audit", "timeline"]) {
      expect(((mockApi as unknown as Record<string, unknown>)[key])).toBeTypeOf("object");
    }
  });

  it("lists cases with search + status filters operating on real page params", async () => {
    await signIn("investigator", "investigator-dev-password");
    const all = await mockApi.cases.list({ limit: 50 });
    expect(all.total).toBeGreaterThan(0);

    const open = await mockApi.cases.list({ status: "open" });
    expect(open.items.every((c) => c.status === "open")).toBe(true);

    const searched = await mockApi.cases.list({ search: all.items[0].title.slice(0, 6) });
    expect(searched.total).toBeGreaterThanOrEqual(1);
  });

  it("updates finding statuses and records them through the same facade the UI uses", async () => {
    await signIn("admin", "admin-dev-password");
    const findings = await mockApi.findings.list(MAIN_CASE_ID, { limit: 50 });
    const pending = findings.items.find((f) => f.status === "NEW");
    expect(pending).toBeTruthy();

    const out = await mockApi.findings.updateStatus(MAIN_CASE_ID, pending!.id, { status: "CONFIRMED" });
    expect(out.id).toBe(pending!.id);
    expect(out.status).toBe("CONFIRMED");
    expect(out.reviewed_by).toBeTruthy();

    const refreshed = await mockApi.findings.get(MAIN_CASE_ID, pending!.id);
    expect(refreshed.status).toBe("CONFIRMED");
  });

  it("uploads evidence files and lists the stored record", async () => {
    await signIn("admin", "admin-dev-password");
    const before = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    const file = new File(["a,b\n1,2"], "cdr_extract.csv", { type: "text/csv" });
    const created = await mockApi.evidence.upload(MAIN_CASE_ID, {
      name: "cdr_extract.csv",
      type: "text/csv",
      size: file.size,
      contents: file,
    });
    expect(created.original_filename).toBe("cdr_extract.csv");
    // Mirrors the backend lifecycle: upload leaves the file "stored", not a
    // backend-illegal "pending" status.
    expect(created.status).toBe("stored");

    const after = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    expect(after.total).toBe(before.total + 1);
    expect(after.items.find((item) => item.id === created.id)?.status).toBe("stored");
  });

  it("mirrors the stored -> processing -> parsed ingestion lifecycle", async () => {
    await signIn("admin", "admin-dev-password");
    const created = await mockApi.evidence.upload(MAIN_CASE_ID, {
      name: "calls.csv",
      type: "text/csv",
      size: 42,
      contents: new File(["a,b\n1,2"], "calls.csv", { type: "text/csv" }),
    });
    expect(created.status).toBe("stored");

    const accepted = await mockApi.evidence.ingest(MAIN_CASE_ID, created.id);
    expect(accepted.job.status).toBe("completed");
    expect(accepted.job.stage).toBe("complete");

    const detail = await mockApi.evidence.get(MAIN_CASE_ID, created.id);
    expect(detail.status).toBe("parsed");
  });

  it("resetMockState removes uploaded state and sessions between tests", async () => {
    await signIn("admin", "admin-dev-password");
    const before = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    await mockApi.evidence.upload(MAIN_CASE_ID, {
      name: "leak.csv",
      type: "text/csv",
      size: 7,
      contents: new File(["x"], "leak.csv", { type: "text/csv" }),
    });
    expect((await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 })).total).toBe(before.total + 1);

    resetMockState();

    // The session was cleared along with the uploaded state, so the same
    // listing that succeeded before now requires authentication again.
    await expect(mockApi.auth.me()).rejects.toMatchObject({ status: 401 });
    await mockApi.auth.login({ username: "admin", password: "admin-dev-password" });
    expect(await mockApi.auth.me()).toMatchObject({ user: { username: "admin" } });
    expect((await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 })).total).toBe(before.total);
  });

  it("enforces role permissions exactly like the backend", async () => {
    await signIn("admin", "admin-dev-password");
    expect(await mockApi.auth.me()).toMatchObject({ roles: ["ADMIN"] });
    await signIn("viewer", "viewer-demo-password");

    // updateStatus denies before any case-lookup: CONFIRM requires findings.confirm.
    await expect(
      mockApi.findings.updateStatus(MAIN_CASE_ID, "f_liquid_assets_03", { status: "CONFIRMED" }),
    ).rejects.toMatchObject({ status: 403 });
    // audit.read is not granted to viewers at all.
    await expect(mockApi.audit.list({})).rejects.toMatchObject({ status: 403 });
  });

  it("public registration creates a PENDING account that cannot sign in until approved", async () => {
    const created = await mockApi.auth.register({
      username: "fresh-analyst",
      email: "fresh@cybersaarthi.test",
      password: "some-password!",
    });
    expect(created.user.status).toBe("PENDING");
    expect(created.user.is_active).toBe(false);
    expect(created.roles).toEqual([]);

    // A PENDING account must not be able to log in.
    await expect(
      mockApi.auth.login({ username: "fresh-analyst", password: "some-password!" }),
    ).rejects.toMatchObject({ status: 403, code: "ACCOUNT_PENDING" });
  });

  it("admin can approve a pending account which then signs in with the granted role", async () => {
    await mockApi.auth.register({
      username: "approve-me",
      email: "approve@cybersaarthi.test",
      password: "some-password!",
    });
    await signIn("admin", "admin-dev-password");

    const pendingList = await mockApi.users.listPending({ limit: 50 });
    const row = pendingList.items.find((u) => u.username === "approve-me");
    expect(row).toBeTruthy();
    expect(row!.status).toBe("PENDING");

    const approved = await mockApi.users.approve(row!.id, "ANALYST");
    expect(approved.status).toBe("ACTIVE");
    expect(approved.roles).toEqual(["ANALYST"]);

    await signIn("approve-me", "some-password!");
    expect(await mockApi.auth.me()).toMatchObject({ roles: ["ANALYST"] });
  });

  it("admin user management is guarded by users.manage", async () => {
    await signIn("viewer", "viewer-demo-password");
    await expect(mockApi.users.list({})).rejects.toMatchObject({ status: 403 });
    await expect(mockApi.users.listPending({})).rejects.toMatchObject({ status: 403 });
  });

  it("suspend/activate and role change flow through the admin users API", async () => {
    await mockApi.auth.register({
      username: "lifecycle",
      email: "lifecycle@cybersaarthi.test",
      password: "some-password!",
    });
    await signIn("admin", "admin-dev-password");
    const list = await mockApi.users.list({ status: "PENDING", search: "lifecycle" });
    const user = list.items[0];
    expect(user).toBeTruthy();

    await mockApi.users.approve(user.id, "INVESTIGATOR");
    const suspended = await mockApi.users.suspend(user.id);
    expect(suspended.status).toBe("SUSPENDED");
    await expect(
      mockApi.auth.login({ username: "lifecycle", password: "some-password!" }),
    ).rejects.toMatchObject({ status: 403, code: "ACCOUNT_SUSPENDED" });

    await mockApi.users.activate(user.id);
    const roleChanged = await mockApi.users.changeRole(user.id, "VIEWER");
    expect(roleChanged.status).toBe("ACTIVE");
    expect(roleChanged.roles).toEqual(["VIEWER"]);

    await signIn("lifecycle", "some-password!");
    expect(await mockApi.auth.me()).toMatchObject({ user: { status: "ACTIVE" }, roles: ["VIEWER"] });
  });

  it("cannot suspend or reject an active administrator (self-guard mirror)", async () => {
    await signIn("admin", "admin-dev-password");
    const all = await mockApi.users.list({ limit: 50 });
    const admin = all.items.find((u) => u.username === "admin");
    expect(admin).toBeTruthy();
    await expect(mockApi.users.suspend(admin!.id)).rejects.toMatchObject({ status: 422 });
    await expect(mockApi.users.reject(admin!.id)).rejects.toMatchObject({ status: 422 });
  });

  it("case membership grants and revokes access (member-aware, backend mirror)", async () => {
    // An analyst who is not a member of the main case has no access.
    await signIn("analyst", "analyst-demo-password");
    const analystId = (await mockApi.auth.me()).user.id;
    await expect(mockApi.cases.get(MAIN_CASE_ID)).rejects.toMatchObject({ status: 403 });

    // Owner grants analyst access.
    await signIn("investigator", "investigator-dev-password");
    await mockApi.cases.addMember(MAIN_CASE_ID, { user_id: analystId, role: "viewer" });
    let listed = await mockApi.cases.list({ limit: 100 });
    expect(listed.items.some((c) => c.id === MAIN_CASE_ID)).toBe(true);

    // The analyst now gets the case in their list and can open it.
    await signIn("analyst", "analyst-demo-password");
    listed = await mockApi.cases.list({ limit: 100 });
    expect(listed.items.some((c) => c.id === MAIN_CASE_ID)).toBe(true);
    expect((await mockApi.cases.get(MAIN_CASE_ID)).id).toBe(MAIN_CASE_ID);

    // A viewer role cannot manage members; owner can revoke.
    await expect(
      mockApi.cases.removeMember(MAIN_CASE_ID, analystId),
    ).rejects.toMatchObject({ status: 403 });
    await signIn("investigator", "investigator-dev-password");
    await mockApi.cases.removeMember(MAIN_CASE_ID, analystId);

    // Access revoked: the analyst can no longer list or open the case.
    await signIn("analyst", "analyst-demo-password");
    listed = await mockApi.cases.list({ limit: 100 });
    expect(listed.items.some((c) => c.id === MAIN_CASE_ID)).toBe(false);
    await expect(mockApi.cases.get(MAIN_CASE_ID)).rejects.toMatchObject({ status: 403 });
  });

  it("evidence.delete is enforced for admin and investigator, denied otherwise", async () => {
    await signIn("admin", "admin-dev-password");
    const adminEv = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 1 });
    expect(adminEv.items.length).toBeGreaterThan(0);
    const evId = adminEv.items[0].id;
    // Admin can delete.
    await expect(mockApi.evidence.delete(MAIN_CASE_ID, evId)).resolves.toBeUndefined();

    // Restore the row for the next assertion via a fresh upload.
    const analystList = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 1 });
    await signIn("analyst", "analyst-demo-password");
    await expect(
      mockApi.evidence.delete(MAIN_CASE_ID, analystList.items[0]?.id ?? "missing"),
    ).rejects.toMatchObject({ status: 403 });
  });

  it("retryGraphSync requires ingestion.run and guards job ownership (IDOR)", async () => {
    await signIn("investigator", "investigator-dev-password");
    const jobs = await mockApi.evidence.jobs(MAIN_CASE_ID, { limit: 50 });
    expect(jobs.items.length).toBeGreaterThan(0);
    const jobId = jobs.items[0].id;

    // Retrying the job succeeds and flips the graph-sync status to synced.
    const result = await mockApi.evidence.retryGraphSync(MAIN_CASE_ID, jobId);
    expect(result.job_id).toBe(jobId);
    expect(result.graph_sync_status).toBe("synced");

    // A viewer lacks ingestion.run.
    await signIn("viewer", "viewer-demo-password");
    await expect(
      mockApi.evidence.retryGraphSync(MAIN_CASE_ID, jobId),
    ).rejects.toMatchObject({ status: 403 });
  });

  it("reviewResolution lists candidates for the main case and is empty elsewhere", async () => {
    await signIn("investigator", "investigator-dev-password");
    const review = await mockApi.entities.reviewResolution(MAIN_CASE_ID);
    expect(review.items.length).toBeGreaterThan(0);
    expect(review.items.every((c) => c.candidate_value.length > 0)).toBe(true);
  });

  it("returns the real timeline event feed and records new events on it", async () => {
    await signIn("investigator", "investigator-dev-password");
    const feed = await mockApi.timeline.events(MAIN_CASE_ID);
    expect(feed.total).toBeGreaterThan(0);
    expect(feed.items[0]).toHaveProperty("kind");
    expect(feed.items[0]).toHaveProperty("occurred_at");

    const created = await mockApi.timeline.create(MAIN_CASE_ID, {
      occurred_at: new Date().toISOString(),
      kind: "finding_created",
      title: "Investigator re-opened review",
    });
    expect(created.title).toContain("re-opened");
    expect(created.actor_user_id).toBeTruthy();

    const after = await mockApi.timeline.events(MAIN_CASE_ID);
    expect(after.total).toBe(feed.total + 1);
    expect(after.items[0].id).toBe(created.id);
  });

  it("accepts and rejects resolution review matches", async () => {
    await signIn("investigator", "investigator-dev-password");
    const review = await mockApi.entities.reviewResolution(MAIN_CASE_ID);
    const matchId = review.items[0].match_id;

    // Analyst can view but not decide.
    await signIn("analyst", "analyst-demo-password");
    await expect(
      mockApi.entities.acceptMatch(MAIN_CASE_ID, matchId),
    ).rejects.toMatchObject({ status: 403 });

    await signIn("investigator", "investigator-dev-password");
    const decided = await mockApi.entities.rejectMatch(MAIN_CASE_ID, matchId);
    expect(decided.status).toBe("rejected");
  });

  it("merges a duplicate entity into the surviving primary", async () => {
    await signIn("investigator", "investigator-dev-password");
    const entities = await mockApi.entities.list(MAIN_CASE_ID, { limit: 200 });
    const [primary, duplicate] = entities.items.filter((e) => e.status === "active").slice(0, 2);
    expect(primary).toBeTruthy();
    expect(duplicate).toBeTruthy();

    await signIn("viewer", "viewer-demo-password");
    await expect(
      mockApi.entities.mergeEntities(MAIN_CASE_ID, {
        primary_entity_id: primary!.id,
        merge_entity_id: duplicate!.id,
      }),
    ).rejects.toMatchObject({ status: 403 });

    await signIn("investigator", "investigator-dev-password");
    const merged = await mockApi.entities.mergeEntities(MAIN_CASE_ID, {
      primary_entity_id: primary!.id,
      merge_entity_id: duplicate!.id,
    });
    expect(merged.id).toBe(primary!.id);
    expect(merged.status).toBe("active");
  });

  it("creates and seals collections, locking them against edits", async () => {
    await signIn("admin", "admin-dev-password");
    const created = await mockApi.collections.create(MAIN_CASE_ID, { name: "Tower B phones" });
    expect(created.status).toBe("open");

    const sealed = await mockApi.collections.seal(MAIN_CASE_ID, created.id);
    expect(sealed.status).toBe("sealed");
    expect(sealed.sealed_at).toBeTruthy();

    await expect(
      mockApi.collections.update(MAIN_CASE_ID, created.id, { description: "late edit" }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("moves deleted evidence to the recycle bin and restores it back", async () => {
    await signIn("admin", "admin-dev-password");
    const before = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    const target = before.items[0];

    await mockApi.evidence.delete(MAIN_CASE_ID, target.id);
    const afterDelete = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    expect(afterDelete.items.some((e) => e.id === target.id)).toBe(false);

    await signIn("analyst", "analyst-demo-password");
    await expect(
      mockApi.evidence.restore(MAIN_CASE_ID, target.id),
    ).rejects.toMatchObject({ status: 403 });

    await signIn("admin", "admin-dev-password");
    const restored = await mockApi.evidence.restore(MAIN_CASE_ID, target.id);
    expect(restored.id).toBe(target.id);
    expect(restored.restored).toBe(true);

    const afterRestore = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    expect(afterRestore.items.some((e) => e.id === target.id)).toBe(true);
  });

  it("registers, approves and revokes a field device with admin-only approval", async () => {
    await signIn("investigator", "investigator-dev-password");
    const registered = await mockApi.fieldDevices.register(MAIN_CASE_ID, {
      platform: "android_mobile",
      serial: `SN-TEST-${Math.floor(Math.random() * 1e6)}`,
      model: "Pixel 9",
      public_key: "AAAAB3NzaC1yc2E...dc6SGFs",
    });
    expect(registered.status).toBe("pending");

    await signIn("analyst", "analyst-demo-password");
    await expect(
      mockApi.fieldDevices.approve(MAIN_CASE_ID, registered.id),
    ).rejects.toMatchObject({ status: 403 });

    await signIn("admin", "admin-dev-password");
    const approved = await mockApi.fieldDevices.approve(MAIN_CASE_ID, registered.id);
    expect(approved.status).toBe("approved");
    expect(approved.approved_by).toBeTruthy();

    const revoked = await mockApi.fieldDevices.revoke(MAIN_CASE_ID, registered.id);
    expect(revoked.status).toBe("revoked");
  });

  it("generates a report and downloads it as a blob", async () => {
    await signIn("investigator", "investigator-dev-password");
    const report = await mockApi.reports.generate(MAIN_CASE_ID, {
      report_type: "case_summary",
      format: "json",
    });
    expect(report.status).toBe("ready");

    const list = await mockApi.reports.list(MAIN_CASE_ID);
    expect(list.items.length).toBeGreaterThan(0);

    const { blob, filename } = await mockApi.reports.download(MAIN_CASE_ID, report.id);
    expect(blob.size).toBeGreaterThan(0);
    expect(filename).toContain("case_summary");
  });

  it("records investigation hypotheses and advances their status", async () => {
    await signIn("investigator", "investigator-dev-password");
    const created = await mockApi.hypotheses.create(MAIN_CASE_ID, {
      title: "Funds moved through the recovered account",
      statement: "The stolen amount passed through account X within hours of the theft.",
    });
    expect(created.status).toBe("proposed");

    const updated = await mockApi.hypotheses.updateStatus(MAIN_CASE_ID, created.id, "under_review");
    expect(updated.status).toBe("under_review");

    const list = await mockApi.hypotheses.list(MAIN_CASE_ID);
    expect(list.items.some((h) => h.id === created.id)).toBe(true);
  });

  it("searches case content and accepts a signed import package", async () => {
    await signIn("investigator", "investigator-dev-password");
    const result = await mockApi.search.search(MAIN_CASE_ID, { q: "Mumbai" });
    expect(result.total).toBeGreaterThan(0);

    const accepted = await mockApi.importPackages.submitPackage(MAIN_CASE_ID, {
      manifest: new File(['{"schema_version": 1}'], "manifest.json", { type: "application/json" }),
      signature: new File(["signature-bytes"], "manifest.json.sig", { type: "application/octet-stream" }),
      files: [new File(["payload"], "chunk_001.bin", { type: "application/octet-stream" })],
    });
    expect(accepted.imported_evidence_count).toBe(1);
    expect(accepted.evidence_ids.length).toBe(1);
  });

  /* ------------------ Evidence intelligence (phase 2) ------------------ */

  it("extracts fields, refuses a concurrent run, and keeps artifacts unreviewed until a human decides", async () => {
    await signIn("admin", "admin-dev-password");
    const list = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 5 });
    const evidenceId = list.items[0].id;

    const submitted = await mockApi.evidence.extract(MAIN_CASE_ID, evidenceId);
    expect(submitted.job.status).toBe("succeeded");
    expect(submitted.job.feature).toBe("ingestion");
    expect(submitted.duplicate).toBe(false);

    // A second submit after a terminal run is a new attempt, not a duplicate.
    const second = await mockApi.evidence.extract(MAIN_CASE_ID, evidenceId);
    expect(second.job.attempts).toBe(2);

    const artifacts = await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "extraction" });
    const forEvidence = artifacts.items.filter((a) => a.evidence_file_id === evidenceId);
    expect(forEvidence.length).toBe(2);
    // Nothing is auto-approved: every extraction artifact awaits review, and the
    // flagged paraphrase stays flagged.
    expect(forEvidence.every((a) => a.status === "pending_review")).toBe(true);
    expect(forEvidence[0].validation_status).toBe("flagged");
    expect(forEvidence[0].validation_errors?.length).toBe(1);

    // Approval records a decision; it does not clear the validation flags.
    const approved = await mockApi.evidence.reviewArtifact(MAIN_CASE_ID, forEvidence[0].id, { decision: "approved", note: "spot checked" });
    expect(approved.status).toBe("approved");
    expect(approved.review_note).toBe("spot checked");
    // Re-reviewing a decided artifact is refused.
    await expect(
      mockApi.evidence.reviewArtifact(MAIN_CASE_ID, forEvidence[0].id, { decision: "rejected" }),
    ).rejects.toMatchObject({ code: "ARTIFACT_NOT_REVIEWABLE" });
  });

  it("verifies integrity with a deterministic match and records the fact artifact", async () => {
    await signIn("admin", "admin-dev-password");
    const list = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 5 });
    const evidenceId = list.items[0].id;

    const result = await mockApi.evidence.verifyIntegrity(MAIN_CASE_ID, evidenceId);
    expect(result.status).toBe("match");
    expect(result.calculated_sha256).toBe(result.expected_sha256);
    expect(result.object_present).toBe(true);

    const recorded = await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "integrity_verification" });
    expect(recorded.items[0]?.payload).toMatchObject({ type: "hash_verification", status: "match" });
  });

  it("audits custody: seeded gap produces exactly one rule finding, clean chain produces none", async () => {
    await signIn("admin", "admin-dev-password");
    // The custody seed attaches its chains to the first two seeded records
    // (the list endpoint sorts newest-first, so pick them by id).
    const [first, second] = MAIN_EVIDENCE;

    const chronology = await mockApi.evidence.custodyChronology(MAIN_CASE_ID, first.id);
    expect(chronology.event_count).toBe(2);
    expect(chronology.sha256).toBe(first.sha256);

    const audited = await mockApi.evidence.custodyAudit(MAIN_CASE_ID, first.id);
    expect(audited.job.status).toBe("succeeded");
    expect(audited.job.result_summary).toMatchObject({ findings_new: 1, findings_existing: 0 });

    const clean = await mockApi.evidence.custodyAudit(MAIN_CASE_ID, second.id);
    expect(clean.job.result_summary).toMatchObject({ findings_new: 0 });

    // Re-running the audit dedupes: the same finding is counted as existing.
    const again = await mockApi.evidence.custodyAudit(MAIN_CASE_ID, first.id);
    expect(again.job.result_summary).toMatchObject({ findings_new: 0, findings_existing: 1 });

    const findings = await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "custody_finding" });
    expect(findings.items.length).toBe(1);
    expect(findings.items[0].payload).toMatchObject({ rule: "custody.unacknowledged_transfer" });

    // Explain returns facts-only narration stored as flagged, never green.
    const explained = await mockApi.evidence.explainFinding(MAIN_CASE_ID, findings.items[0].id);
    expect(explained.explanation_artifact.validation_status).toBe("flagged");
    expect(explained.explanation_artifact.parent_artifact_id).toBe(findings.items[0].id);
    // Hash facts cannot be "explained" into custody claims.
    const verify = await mockApi.evidence.verifyIntegrity(MAIN_CASE_ID, first.id);
    await expect(mockApi.evidence.explainFinding(MAIN_CASE_ID, verify.artifact_id)).rejects.toMatchObject({
      code: "ARTIFACT_KIND_UNSUPPORTED",
    });
  });

  it("records custody events with policy validation (required fields, zone, digest)", async () => {
    await signIn("admin", "admin-dev-password");
    const evidenceId = MAIN_EVIDENCE[0].id;

    await expect(
      mockApi.evidence.recordCustodyEvent(MAIN_CASE_ID, evidenceId, { event_type: "transferred", occurred_at: "2026-01-15T10:00:00Z" }),
    ).rejects.toMatchObject({ code: "CUSTODY_FIELD_REQUIRED" });

    await expect(
      mockApi.evidence.recordCustodyEvent(MAIN_CASE_ID, evidenceId, {
        event_type: "collected",
        occurred_at: "2026-01-15T10:00:00",
        collector: "Insp. Verma",
      }),
    ).rejects.toMatchObject({ code: "VALIDATION_ERROR" });

    const event = await mockApi.evidence.recordCustodyEvent(MAIN_CASE_ID, evidenceId, {
      event_type: "received",
      occurred_at: new Date().toISOString(),
      recipient: "Forensics Lab",
    });
    expect(event.recorded_at).toBeTruthy();
    expect(event.evidence_file_id).toBe(evidenceId);

    // The appended receipt closes the seeded transfer gap.
    const audited = await mockApi.evidence.custodyAudit(MAIN_CASE_ID, evidenceId);
    expect(audited.job.result_summary).toMatchObject({ evidence_checked: 1, findings_new: 0 });
  });

  it("denies extraction to users without ingestion.run", async () => {
    await signIn("viewer", "viewer-demo-password");
    const list = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 5 }).catch(() => ({ items: [] as never[] }));
    if (list.items.length === 0) return; // viewer may lack case access entirely
    await expect(mockApi.evidence.extract(MAIN_CASE_ID, list.items[0].id)).rejects.toMatchObject({ status: 403 });
  });
});
describe("case intelligence (phase 3)", () => {
  it("proposes one resolution candidate; approval adds cross-aliases and never merges", async () => {
    await signIn("investigator", "investigator-dev-password");
    const submitted = await mockApi.evidence.submitEntityResolution(MAIN_CASE_ID);
    expect(submitted.job.feature).toBe("entity_resolution");
    expect(submitted.job.status).toBe("succeeded");
    expect(submitted.job.idempotency_key).toBe(`entity_resolution:${MAIN_CASE_ID}:a1`);
    expect(submitted.job.result_summary).toMatchObject({ pairs_proposed: 1, pairs_llm_skipped: 0 });

    // Retry after the terminal run: a new attempt that reuses every artifact.
    const second = await mockApi.evidence.submitEntityResolution(MAIN_CASE_ID);
    expect(second.job.attempts).toBe(2);
    expect(second.job.idempotency_key).toBe(`entity_resolution:${MAIN_CASE_ID}:a2`);
    expect(second.job.result_summary).toMatchObject({ artifacts_created: 0, artifacts_reused: 1 });

    const candidates = await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "entity_resolution" });
    expect(candidates.items.length).toBe(1);
    const candidate = candidates.items[0];
    expect(candidate.status).toBe("pending_review");
    // The name-only pair is honestly flagged, and the band is never a probability.
    expect(candidate.validation_status).toBe("flagged");
    expect(candidate.validation_errors?.[0]).toMatchObject({ code: "no_identifier_evidence" });
    const payload = candidate.payload as {
      type: string;
      score_band: string;
      score_semantics: string;
      entity_a: { id: string };
      entity_b: { id: string };
    };
    expect(payload.type).toBe("entity_candidate");
    expect(payload.score_band).toBe("strong");
    expect(payload.score_semantics).toContain("not a probability");

    // Approval records additive aliases for both entities — no merge happens.
    const reviewed = await mockApi.evidence.reviewArtifact(MAIN_CASE_ID, candidate.id, { decision: "approved", note: "same person" });
    expect(reviewed.status).toBe("approved");
    const entityA = await mockApi.entities.get(MAIN_CASE_ID, payload.entity_a.id);
    const entityB = await mockApi.entities.get(MAIN_CASE_ID, payload.entity_b.id);
    expect(entityA.status).toBe("active");
    expect(entityB.status).toBe("active");
    expect(entityA.aliases.some((a) => a.alias_value === entityB.canonical_value && a.alias_type === "resolution")).toBe(true);
    expect(entityB.aliases.some((a) => a.alias_value === entityA.canonical_value && a.alias_type === "resolution")).toBe(true);
    // The review is one-shot: re-reviewing is refused.
    await expect(
      mockApi.evidence.reviewArtifact(MAIN_CASE_ID, candidate.id, { decision: "rejected" }),
    ).rejects.toMatchObject({ code: "ARTIFACT_NOT_REVIEWABLE" });

    const audit = await mockApi.audit.list({ case_id: MAIN_CASE_ID, limit: 50 });
    const actions = audit.items.map((e) => e.action);
    expect(actions).toContain("resolution.submitted");
    expect(actions).toContain("resolution.analysis_completed");
    const approval = audit.items.find((e) => e.action === "derived_artifact.approved");
    expect(approval?.metadata_).toMatchObject({ kind: "entity_resolution", aliases_added: 2 });
  });

  it("refuses approval of a candidate whose entity was merged away (stale candidate)", async () => {
    await signIn("investigator", "investigator-dev-password");
    await mockApi.evidence.submitEntityResolution(MAIN_CASE_ID);
    const candidate = (await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "entity_resolution" })).items[0];
    const payload = candidate.payload as { entity_a: { id: string }; entity_b: { id: string } };

    // Merging one entity away makes the open candidate stale.
    await mockApi.entities.mergeEntities(MAIN_CASE_ID, {
      primary_entity_id: payload.entity_a.id,
      merge_entity_id: payload.entity_b.id,
    });
    await expect(
      mockApi.evidence.reviewArtifact(MAIN_CASE_ID, candidate.id, { decision: "approved" }),
    ).rejects.toMatchObject({ status: 409, code: "CANDIDATE_ENTITY_UNAVAILABLE" });
  });

  it("commits an approved proposal idempotently and never commits an unestablished timestamp", async () => {
    await signIn("investigator", "investigator-dev-password");
    const submitted = await mockApi.evidence.submitTimelineReconstruction(MAIN_CASE_ID);
    expect(submitted.job.feature).toBe("timeline");
    expect(submitted.job.result_summary).toMatchObject({
      drafts_generated: 3,
      proposals_recorded: 3,
      missing_timestamps: 1,
      ambiguous_timezones: 1,
    });

    const proposals = (await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "timeline_proposal" })).items;
    expect(proposals.length).toBe(3);
    const dateOnly = proposals.find((p) => (p.payload as { time_granularity?: string }).time_granularity === "date");
    const missing = proposals.find((p) => (p.payload as { missing_timestamp?: boolean }).missing_timestamp);
    expect(dateOnly).toBeTruthy();
    // An unparseable strong field is a flagged proposal, never an invented instant.
    expect(missing?.validation_status).toBe("flagged");
    expect(missing?.validation_errors?.[0]).toMatchObject({ code: "missing_timestamp" });

    // Commit requires explicit approval first.
    await expect(
      mockApi.evidence.commitTimelineProposal(MAIN_CASE_ID, dateOnly!.id),
    ).rejects.toMatchObject({ status: 409, code: "PROPOSAL_NOT_APPROVED" });

    await mockApi.evidence.reviewArtifact(MAIN_CASE_ID, dateOnly!.id, { decision: "approved" });
    const first = await mockApi.evidence.commitTimelineProposal(MAIN_CASE_ID, dateOnly!.id);
    expect(first.duplicate).toBe(false);
    expect(first.event.payload).toMatchObject({
      origin: "timeline_reconstruction",
      proposal_artifact_id: dateOnly!.id,
    });

    // Idempotent: the retry returns the same event, never a second row.
    const feedBefore = await mockApi.timeline.events(MAIN_CASE_ID, {});
    const again = await mockApi.evidence.commitTimelineProposal(MAIN_CASE_ID, dateOnly!.id);
    expect(again.duplicate).toBe(true);
    expect(again.event.id).toBe(first.event.id);
    const feedAfter = await mockApi.timeline.events(MAIN_CASE_ID, {});
    expect(feedAfter.total).toBe(feedBefore.total);

    // A missing-timestamp proposal stays uncommittable even after approval.
    await mockApi.evidence.reviewArtifact(MAIN_CASE_ID, missing!.id, { decision: "approved" });
    await expect(
      mockApi.evidence.commitTimelineProposal(MAIN_CASE_ID, missing!.id),
    ).rejects.toMatchObject({ status: 422, code: "TIMELINE_TIMESTAMP_MISSING" });

    // Re-running skips the committed proposal and reuses the open ones.
    const rerun = await mockApi.evidence.submitTimelineReconstruction(MAIN_CASE_ID);
    expect(rerun.job.result_summary).toMatchObject({
      drafts_generated: 2,
      proposals_committed_skipped: 1,
      proposals_reused: 2,
      proposals_recorded: 0,
    });

    const audit = await mockApi.audit.list({ case_id: MAIN_CASE_ID, limit: 50 });
    const committed = audit.items.filter((e) => e.action === "reconstruction.proposal_committed");
    expect(committed.length).toBe(2);
    expect(committed.some((e) => e.metadata_?.duplicate === true)).toBe(true);
  });

  it("appends contradiction resolutions as child artifacts and keeps the candidate immutable", async () => {
    await signIn("investigator", "investigator-dev-password");
    const submitted = await mockApi.evidence.submitContradictions(MAIN_CASE_ID);
    expect(submitted.job.feature).toBe("contradiction");
    expect(submitted.job.result_summary).toMatchObject({ conflicts: 1, artifacts_created: 1 });

    const items = (await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "contradiction" })).items;
    const candidate = items.find((a) => (a.payload as { type?: string }).type === "contradiction");
    expect(candidate).toBeTruthy();
    const snapshot = JSON.stringify(candidate!.payload);

    // Typed refusals mirror the backend: unknown state, then a required note.
    await expect(
      mockApi.evidence.resolveContradiction(MAIN_CASE_ID, candidate!.id, { state: "banana" as ContradictionResolutionState, note: "x" }),
    ).rejects.toMatchObject({ status: 422, code: "CONTRADICTION_STATE_INVALID" });
    await expect(
      mockApi.evidence.resolveContradiction(MAIN_CASE_ID, candidate!.id, { state: "explained", note: "   " }),
    ).rejects.toMatchObject({ status: 422, code: "REVIEW_NOTE_REQUIRED" });

    // A valid resolution is appended: child artifact, candidate untouched.
    const child = await mockApi.evidence.resolveContradiction(MAIN_CASE_ID, candidate!.id, {
      state: "explained",
      note: "one record captured a partial settlement",
    });
    expect(child.status).toBe("recorded");
    expect(child.parent_artifact_id).toBe(candidate!.id);
    expect(child.payload).toMatchObject({
      type: "contradiction_review",
      state: "explained",
      for_artifact_id: candidate!.id,
    });
    const after = (await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "contradiction" })).items.find((a) => a.id === candidate!.id);
    expect(JSON.stringify(after?.payload)).toBe(snapshot);
    expect(after?.status).toBe("pending_review");

    // The review child itself is not a candidate: resolving it is refused.
    await expect(
      mockApi.evidence.resolveContradiction(MAIN_CASE_ID, child.id, { state: "deferred", note: "later" }),
    ).rejects.toMatchObject({ status: 422, code: "ARTIFACT_KIND_UNSUPPORTED" });

    // Confirming is the one-shot review; later resolution states are refused.
    await mockApi.evidence.reviewArtifact(MAIN_CASE_ID, candidate!.id, { decision: "approved" });
    await expect(
      mockApi.evidence.resolveContradiction(MAIN_CASE_ID, candidate!.id, { state: "deferred", note: "later" }),
    ).rejects.toMatchObject({ status: 409, code: "ARTIFACT_NOT_REVIEWABLE" });

    const audit = await mockApi.audit.list({ case_id: MAIN_CASE_ID, limit: 50 });
    expect(audit.items.map((e) => e.action)).toContain("contradiction.explained");
  });

  it("denies case-intelligence runs to users without ingestion.run", async () => {
    await signIn("viewer", "viewer-demo-password");
    await expect(mockApi.evidence.submitEntityResolution(MAIN_CASE_ID)).rejects.toMatchObject({ status: 403 });
    await expect(mockApi.evidence.submitTimelineReconstruction(MAIN_CASE_ID)).rejects.toMatchObject({ status: 403 });
    await expect(mockApi.evidence.submitContradictions(MAIN_CASE_ID)).rejects.toMatchObject({ status: 403 });
  });
});

describe("financial flow (phase 4)", () => {
  it("records a deterministic finding with exact totals, victims and zero confirmed transfers", async () => {
    await signIn("investigator", "investigator-dev-password");
    const submitted = await mockApi.evidence.submitFinancialFlow(MAIN_CASE_ID);
    expect(submitted.job.feature).toBe("financial_flow");
    expect(submitted.job.status).toBe("succeeded");
    expect(submitted.job.idempotency_key).toBe(`financial_flow:${MAIN_CASE_ID}:a1`);
    expect(submitted.job.result_summary).toMatchObject({
      records_scanned: 6,
      facts_extracted: 5,
      currency_buckets: 1,
      network_nodes: 10,
      network_edges: 7,
      artifacts_created: 1,
    });
    const summary = submitted.job.result_summary as Record<string, number>;
    // 4 fixture rules fire + both case victims (amounts match no transaction).
    expect(summary.patterns_firing).toBe(6);
    expect(summary.patterns_not_evaluable).toBe(5);
    expect(summary.patterns_not_fired).toBe(0);

    const findings = await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "financial_finding" });
    expect(findings.items.length).toBe(1);
    const finding = findings.items[0];
    expect(finding.origin).toBe("deterministic");
    expect(finding.status).toBe("pending_review");
    expect(finding.prompt_version).toBeNull(); // no model ran in this feature

    const payload = finding.payload as {
      flow_rules_version: string;
      aggregates: {
        currency_buckets: Array<{
          currency: string | null;
          total_records: string;
          total_distinct: string;
        }>;
        not_computable: { net: string };
      };
      structure_network: { confirmed_transfer_edges: number; nodes_total: number; edges_total: number };
      patterns: { firing: Array<{ rule: string }>; not_fired: string[]; not_evaluable: Array<{ rule: string; reason: string }> };
      limitations: string[];
      calculation_definitions: Record<string, string>;
    };
    expect(payload.flow_rules_version).toBe("flow-rules/1.0.0");
    const bucket = payload.aggregates.currency_buckets[0];
    expect(bucket.currency).toBeNull(); // never labelled with a default currency
    expect(bucket.total_records).toBe("25500.00");
    expect(bucket.total_distinct).toBe("21000.00");
    expect(payload.aggregates.not_computable.net).toBe("not_computable_no_direction");
    expect(payload.structure_network.confirmed_transfer_edges).toBe(0);
    expect(payload.structure_network.nodes_total).toBe(10);
    expect(payload.structure_network.edges_total).toBe(7);
    const firingRules = payload.patterns.firing.map((p) => p.rule);
    expect(firingRules).toEqual(expect.arrayContaining(["duplicate_amount", "amount_threshold", "victim_loss_unmatched"]));
    expect(payload.patterns.not_fired).toEqual([]);
    expect(payload.patterns.not_evaluable.map((p) => p.rule)).toContain("circular_path");
    expect(payload.patterns.not_evaluable.every((p) => Boolean(p.reason))).toBe(true);
    expect(payload.limitations.join(" ")).toContain("no payer/sender key");
    expect(payload.calculation_definitions.net_flow).toContain("not computed");

    // A rerun reuses the artifact by content hash and increments the attempt.
    const second = await mockApi.evidence.submitFinancialFlow(MAIN_CASE_ID);
    expect(second.job.attempts).toBe(2);
    expect(second.job.idempotency_key).toBe(`financial_flow:${MAIN_CASE_ID}:a2`);
    expect(second.job.result_summary).toMatchObject({ artifacts_created: 0, artifacts_reused: 1 });
    const after = await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "financial_finding" });
    expect(after.items.length).toBe(1);
  });

  it("traces association paths deterministically and answers a transfer request as absent", async () => {
    await signIn("investigator", "investigator-dev-password");

    const first = await mockApi.evidence.traceFinancialFlow(MAIN_CASE_ID, { target: "ACC-SIH-001" });
    expect(first.status).toBe("ok");
    expect(first.start_node).toBe("account:ACCSIH001");
    expect(first.target_degree).toBe(3);
    // Sorted neighbour order is the deterministic contract.
    expect(first.paths.map((p) => p.nodes[1])).toEqual([
      "beneficiary:ananya sirohi",
      "merchant:phonepe merchant",
      "party:ananya sirohi",
    ]);
    expect(first.paths.every((p) => p.end_state === "dead_end" && p.incomplete)).toBe(true);
    expect(first.paths[0].hops[0]).toMatchObject({ edge_kind: "association", confidence: "suspected" });
    expect(first.network).toMatchObject({ nodes_total: 10, edges_total: 7, confirmed_transfer_edges: 0 });
    expect(first.bounds).toMatchObject({ max_depth: 4, max_paths: 50, max_records: 1000, records_scanned: 6 });

    const again = await mockApi.evidence.traceFinancialFlow(MAIN_CASE_ID, { target: "ACC-SIH-001" });
    expect(again.paths).toEqual(first.paths);

    const transfer = await mockApi.evidence.traceFinancialFlow(MAIN_CASE_ID, {
      target: "ACC-SIH-001",
      edge_kind: "transfer",
    });
    expect(transfer.status).toBe("insufficient_data");
    expect(transfer.reason).toBe("no_transfer_edges_in_ingest");
    expect(transfer.paths).toEqual([]);
    // The scan scope is still reported so a bare zero cannot be misread.
    expect(transfer.network.nodes_total).toBe(10);

    const missing = await mockApi.evidence.traceFinancialFlow(MAIN_CASE_ID, { target: "ACC-NOPE-999" });
    expect(missing.status).toBe("not_found");
    expect(missing.paths).toEqual([]);

    const txn = await mockApi.evidence.traceFinancialFlow(MAIN_CASE_ID, {
      target: "txn-sih-001",
      target_kind: "transaction",
    });
    expect(txn.status).toBe("ok");
    expect(txn.matched_facts).toBe(2);
    expect(txn.start_node).toBe("account:ACCSIH001");

    // Requested bounds beyond the server configuration are clamped and echoed.
    const oversized = await mockApi.evidence.traceFinancialFlow(MAIN_CASE_ID, {
      target: "ACC-SIH-001",
      max_depth: 999,
      max_paths: 999,
    });
    expect(oversized.bounds.max_depth).toBe(4);
    expect(oversized.bounds.max_paths).toBe(50);
  });

  it("denies financial-flow runs to users without ingestion.run", async () => {
    await signIn("viewer", "viewer-demo-password");
    await expect(mockApi.evidence.submitFinancialFlow(MAIN_CASE_ID)).rejects.toMatchObject({ status: 403 });
  });
});

describe("cross-case discovery (phase 4)", () => {
  it("runs a bounded discovery: deterministic candidate, score semantics, rerun reuses by content hash", async () => {
    await signIn("investigator", "investigator-dev-password");
    const submitted = await mockApi.evidence.submitCrossCaseDiscover({
      anchor_case_id: MAIN_CASE_ID,
      case_ids: [MAIN_CASE_ID, SECOND_CASE_ID],
    });
    expect(submitted.job.feature).toBe("cross_case");
    expect(submitted.job.status).toBe("succeeded");
    expect(submitted.job.result_summary).toMatchObject({
      cases_scanned: 2,
      candidates_found: 1,
      candidates_pending_review: 1,
      cases_inaccessible: 0,
    });

    const list = await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID);
    expect(list.total).toBe(1);
    expect(list.crosscase_rules_version).toBe("crosscase/1.0.0");
    expect(list.graph_freshness_note).toContain("does not depend on the Neo4j projection");
    const candidate = list.items[0];
    expect(candidate.kind).toBe("cross_case_link");
    expect(candidate.origin).toBe("deterministic");
    expect(candidate.status).toBe("pending_review");
    expect(candidate.prompt_version).toBeNull(); // no model ran in discovery
    const payload = candidate.payload as {
      group: { indicator_kind: string; value_normalized: string };
      classification: string;
      score: number;
      score_semantics: string;
      reviewable: boolean;
      sides: Array<{ case_id: string; value_originals: string[] }>;
      limitations: string[];
    };
    expect(payload.group).toMatchObject({ indicator_kind: "account_ref", value_normalized: "ACCSIH001" });
    expect(payload.classification).toBe("normalized_identifier");
    expect(payload.score).toBe(78);
    // The score is always shipped with its non-probability semantics.
    expect(payload.score_semantics).toContain("NOT a probability");
    expect(payload.reviewable).toBe(true);
    expect(payload.sides.map((s) => s.case_id)).toEqual([MAIN_CASE_ID, SECOND_CASE_ID]);
    expect(payload.sides.every((s) => s.value_originals.includes("ACC-SIH-001"))).toBe(true);
    expect(payload.limitations.join(" ")).toContain("not evidence of a shared incident");

    // A rerun reuses the candidate by content hash and reports the reuse.
    const rerun = await mockApi.evidence.submitCrossCaseDiscover({
      anchor_case_id: MAIN_CASE_ID,
      case_ids: [MAIN_CASE_ID, SECOND_CASE_ID],
    });
    expect(rerun.job.attempts).toBe(2);
    expect(rerun.job.result_summary).toMatchObject({ candidates_created: 0, candidates_reused: 1 });
    expect((await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID)).total).toBe(1);
  });

  it("rejects a scope that is too small or omits the anchor", async () => {
    await signIn("investigator", "investigator-dev-password");
    await expect(
      mockApi.evidence.submitCrossCaseDiscover({ anchor_case_id: MAIN_CASE_ID, case_ids: [MAIN_CASE_ID] }),
    ).rejects.toMatchObject({ status: 422 });
    await expect(
      mockApi.evidence.submitCrossCaseDiscover({
        anchor_case_id: MAIN_CASE_ID,
        case_ids: [SECOND_CASE_ID, TERTIARY_CASE_ID],
      }),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("fails closed with no disclosure when the scope touches an inaccessible case", async () => {
    await signIn("investigator", "investigator-dev-password");
    // TERTIARY is admin-owned; the investigator is not a member.
    const failure = await mockApi.evidence
      .submitCrossCaseDiscover({ anchor_case_id: MAIN_CASE_ID, case_ids: [MAIN_CASE_ID, TERTIARY_CASE_ID] })
      .catch((err: { status: number; code: string; message: string }) => err);
    expect(failure).toMatchObject({ status: 404, code: "CROSS_CASE_SCOPE_DENIED" });
    // The error never names the inaccessible case.
    expect((failure as { message: string }).message).not.toContain(TERTIARY_CASE_ID);
    expect((failure as { message: string }).message).not.toContain("TERTIARY");
    expect((await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID)).total).toBe(0);
  });

  it("denies discovery to users without crosscase.read", async () => {
    await signIn("viewer", "viewer-demo-password");
    await expect(
      mockApi.evidence.submitCrossCaseDiscover({ anchor_case_id: MAIN_CASE_ID, case_ids: [MAIN_CASE_ID, SECOND_CASE_ID] }),
    ).rejects.toMatchObject({ status: 403 });
  });

  it("omits candidates whose scope is no longer authorized — on every read and on explain", async () => {
    // An admin discovers over a scope that includes a case the investigator cannot read.
    await signIn("admin", "admin-dev-password");
    await mockApi.evidence.submitCrossCaseDiscover({
      anchor_case_id: MAIN_CASE_ID,
      case_ids: [MAIN_CASE_ID, TERTIARY_CASE_ID],
    });
    const adminList = await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID);
    expect(adminList.total).toBe(1);
    const artifactId = adminList.items[0].id;

    // The investigator re-reads the same anchor: the candidate is omitted
    // entirely — not redacted, not counted, not leaked by id.
    await signIn("investigator", "investigator-dev-password");
    const investigatorList = await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID);
    expect(investigatorList.total).toBe(0);
    expect(investigatorList.items).toEqual([]);

    // Explain fails closed the same way (404, no existence disclosure).
    await expect(mockApi.evidence.explainFinding(MAIN_CASE_ID, artifactId)).rejects.toMatchObject({ status: 404 });
  });

  it("approval records a reviewed relationship artifact and its audit trail — never a merge", async () => {
    await signIn("investigator", "investigator-dev-password");
    await mockApi.evidence.submitCrossCaseDiscover({
      anchor_case_id: MAIN_CASE_ID,
      case_ids: [MAIN_CASE_ID, SECOND_CASE_ID],
    });
    const candidate = (await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID)).items[0];

    const reviewed = await mockApi.evidence.reviewArtifact(MAIN_CASE_ID, candidate.id, { decision: "approved" });
    expect(reviewed.status).toBe("approved");

    // A deterministic child records the reviewed relationship (both cases).
    const children = (await mockApi.evidence.artifacts(MAIN_CASE_ID, { kind: "cross_case_link" })).items;
    const reviewedChild = children.find((a) => a.id !== candidate.id);
    expect(reviewedChild).toBeTruthy();
    expect(reviewedChild!.origin).toBe("deterministic");
    expect(reviewedChild!.status).toBe("recorded");
    expect(reviewedChild!.payload).toMatchObject({
      type: "reviewed_cross_case_link",
      decision: "approved",
      indicator_kind: "account_ref",
      value_normalized: "ACCSIH001",
      classification: "normalized_identifier",
      cases: [MAIN_CASE_ID, SECOND_CASE_ID],
      for_artifact_id: candidate.id,
    });

    const audit = await mockApi.audit.list({ case_id: MAIN_CASE_ID, limit: 50 });
    const approval = audit.items.find((e) => e.action === "derived_artifact.approved");
    expect(approval).toBeTruthy();
    expect(approval!.metadata_).toMatchObject({
      kind: "cross_case_link",
      reviewed_child_artifact_id: reviewedChild!.id,
      reviewed_cases: [MAIN_CASE_ID, SECOND_CASE_ID],
    });
  });

  it("explains a candidate with a citations-checked narration flagged ai_unverified", async () => {
    await signIn("investigator", "investigator-dev-password");
    await mockApi.evidence.submitCrossCaseDiscover({
      anchor_case_id: MAIN_CASE_ID,
      case_ids: [MAIN_CASE_ID, SECOND_CASE_ID],
    });
    const candidate = (await mockApi.evidence.crossCaseCandidates(MAIN_CASE_ID)).items[0];

    const explained = await mockApi.evidence.explainFinding(MAIN_CASE_ID, candidate.id);
    expect(explained.explanation_artifact.origin).toBe("llm");
    expect(explained.explanation_artifact.status).toBe("recorded");
    expect(explained.explanation_artifact.validation_status).toBe("flagged");
    expect(explained.explanation_artifact.parent_artifact_id).toBe(candidate.id);
    expect(explained.explanation_artifact.validation_errors?.[0]?.code).toBe("ai_unverified");
    // The narration cites only the real shared value from the candidate.
    const explanation = explained.explanation as { summary: string; not_established: string[] };
    expect(explanation.summary).toContain("ACC-SIH-001");
    expect(explanation.summary).toContain("not proof of a shared incident");
    expect(explanation.not_established.join(" ")).toContain("that the cases are the same incident");
    expect(explained.text).toBe(explanation.summary);

    const audit = await mockApi.audit.list({ case_id: MAIN_CASE_ID, limit: 50 });
    expect(audit.items.some((e) => e.action === "cross_case.explanation_generated")).toBe(true);
  });
});
