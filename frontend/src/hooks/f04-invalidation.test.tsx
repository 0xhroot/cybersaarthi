import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useIngestEvidence, useRunAnalytics } from "@/hooks/queries";
import { mockApi } from "@/api/mock";

const CASE_ID = "a0000000-0000-4000-8000-000000000001";

/** Collect the serialized query keys passed to invalidateQueries. */
async function invalidatedKeysAfter(
  trigger: (wrapper: ({ children }: { children: ReactNode }) => ReactNode) => void,
): Promise<string[]> {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  await trigger(wrapper);
  return spy.mock.calls
    .map(([opts]) => JSON.stringify(opts?.queryKey ?? []));
}

const ANALYTICS_KEYS = [
  "centrality",
  "communities",
  "network-dna",
  "priorities",
  "strength",
  "patterns",
  "hypotheses",
];

describe("F04 analytics cache invalidation", () => {
  it("refreshes every analytics-derived key after run-analytics", async () => {
    await mockApi.auth.login({ username: "admin", password: "admin-dev-password" });
    const keys = await invalidatedKeysAfter((wrapper) => {
      const { result } = renderHook(() => useRunAnalytics(CASE_ID), { wrapper });
      result.current.mutate();
      return waitFor(() => expect(result.current.isSuccess).toBe(true));
    });

    for (const key of ANALYTICS_KEYS) {
      expect(
        keys.some((k) => k.includes(CASE_ID) && k.includes(JSON.stringify(key))),
        `expected invalidate for analytics key ${key}`,
      ).toBe(true);
    }
  });

  it("refreshes every analytics-derived key after ingest", async () => {
    await mockApi.auth.login({ username: "admin", password: "admin-dev-password" });
    // Reuse an existing processed evidence file so ingestion succeeds.
    const evidence = await mockApi.evidence.list(CASE_ID, { limit: 50 });
    const file = evidence.items[0];
    // Ensure a stored file exists to ingest; else create one via the mock.
    const keys = await invalidatedKeysAfter((wrapper) => {
      const { result } = renderHook(() => useIngestEvidence(CASE_ID), { wrapper });
      result.current.mutate(file.id);
      return waitFor(() => expect(result.current.isSuccess).toBe(true));
    });

    for (const key of ANALYTICS_KEYS) {
      expect(
        keys.some((k) => k.includes(CASE_ID) && k.includes(JSON.stringify(key))),
        `expected invalidate for analytics key ${key}`,
      ).toBe(true);
    }
  });
});
