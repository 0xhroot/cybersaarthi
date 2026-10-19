import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useUpdateFindingStatus, useReportAuditDetail } from "@/hooks/queries";
import { api } from "@/api";
import { mockApi } from "@/api/mock";
import type { ReportAuditDetailOut } from "@/types/domain";

const CASE_ID = "a0000000-0000-4000-8000-000000000001";

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("finding status mutation", () => {
  it("transitions a NEW finding to CONFIRMED and reports the reviewer", async () => {
    await mockApi.auth.login({ username: "admin", password: "admin-dev-password" });
    const before = await mockApi.findings.list(CASE_ID, { limit: 50 });
    const target = before.items.find((f) => f.status === "NEW")!;

    const { result } = renderHook(() => useUpdateFindingStatus(CASE_ID), { wrapper: createWrapper() });
    result.current.mutate({ findingId: target.id, status: "CONFIRMED", reason: "Matches two independent files" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const out = result.current.data;
    expect(out?.id).toBe(target.id);
    expect(out?.status).toBe("CONFIRMED");
    expect(out?.reviewed_by).toBeDefined();
    expect(out?.review_comment).toBe("Matches two independent files");
  });

  it("rejects a status change the role cannot perform", async () => {
    await mockApi.auth.login({ username: "viewer", password: "viewer-demo-password" });
    const { result } = renderHook(() => useUpdateFindingStatus(CASE_ID), { wrapper: createWrapper() });
    result.current.mutate({ findingId: "f_liquid_assets_03", status: "CONFIRMED" });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { status?: number }).status).toBe(403);
  });

  it("rejects any attempt to re-open a CONFIRMED finding without ADMIN overview", async () => {
    await mockApi.auth.login({ username: "admin", password: "admin-dev-password" });
    const before = await mockApi.findings.list(CASE_ID, { limit: 50 });
    const target = before.items.find((f) => f.status === "CONFIRMED")!;
    expect(target).toBeTruthy();

    // INVESTIGATOR holds findings.confirm but not the ADMIN override.
    await mockApi.auth.login({ username: "investigator", password: "investigator-dev-password" });
    const { result } = renderHook(() => useUpdateFindingStatus(CASE_ID), { wrapper: createWrapper() });
    result.current.mutate({ findingId: target.id, status: "NEW" });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { status?: number }).status).toBe(422);
  });
});

describe("report audit detail polling", () => {
  it(
    "refetches an in-flight audit's detail so the findings card appears on completion",
    async () => {
      // Regression: the detail is fetched while the run is still active and
      // caches "no artifact yet"; without the active-run poll, staleTime
      // holds that empty result and the audit card only appears on remount.
      const running = {
        id: "audit-1",
        case_id: CASE_ID,
        status: "running",
        artifact: null,
      } as unknown as ReportAuditDetailOut;
      const done = {
        ...running,
        status: "succeeded",
        artifact: { id: "art-1" },
      } as unknown as ReportAuditDetailOut;
      let calls = 0;
      const spy = vi.spyOn(api.evidence, "reportAuditDetail").mockImplementation(async () => {
        calls += 1;
        return calls === 1 ? running : done;
      });

      const { result } = renderHook(() => useReportAuditDetail(CASE_ID, "audit-1"), {
        wrapper: createWrapper(),
      });
      await waitFor(() => expect(result.current.data?.status).toBe("running"));
      // The 5s active-run poll flips the cached detail to the terminal payload.
      await waitFor(() => expect(result.current.data?.artifact).toBeTruthy(), {
        timeout: 10_000,
      });
      spy.mockRestore();
    },
    { timeout: 15_000 },
  );
});