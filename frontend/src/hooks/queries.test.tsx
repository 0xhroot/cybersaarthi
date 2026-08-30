import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useUpdateFindingStatus } from "@/hooks/queries";
import { mockApi } from "@/api/mock";

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