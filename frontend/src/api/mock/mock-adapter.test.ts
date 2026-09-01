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
});