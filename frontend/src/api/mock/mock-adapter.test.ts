import { beforeEach, describe, expect, it } from "vitest";
import { mockApi } from "@/api/mock";
import { authSession } from "@/api/client/session";

const MAIN_CASE_ID = "a0000000-0000-4000-8000-000000000001";

async function signIn(username: string, password: string) {
  await mockApi.auth.login({ username, password });
}

beforeEach(() => {
  authSession.clear();
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
    expect(created.status).toBe("pending");

    const after = await mockApi.evidence.list(MAIN_CASE_ID, { limit: 50 });
    expect(after.total).toBe(before.total + 1);
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
});