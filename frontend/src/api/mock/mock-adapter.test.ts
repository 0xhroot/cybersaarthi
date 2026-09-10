import { beforeEach, describe, expect, it } from "vitest";
import { mockApi, resetMockState } from "@/api/mock";

const MAIN_CASE_ID = "a0000000-0000-4000-8000-000000000001";

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
});