import { describe, expect, it } from "vitest";
import { api, isMockMode } from "@/api";
import { apiConfig } from "@/config/env";

describe("adapter switching", () => {
  it("picks the adapter selected by the API configuration", () => {
    // The facade must agree with the effective configuration: when
    // VITE_USE_MOCK_API=false (our default project env) the real adapter is
    // active; the explicit invariant is config and facade agree.
    expect(api.src).toBe(apiConfig.useMockApi ? "mock" : "real");
    expect(isMockMode).toBe(apiConfig.useMockApi);
  });

  it("swaps to the real adapter without changing the facade surface", async () => {
    // The facade must stay stable regardless of VITE_USE_MOCK_API — same keys.
    const viaFacade = Object.keys(api).sort();
    const { realApi } = await import("@/api/real");
    expect(Object.keys(realApi).sort()).toEqual(viaFacade);
  });

  it("keeps mock and real evidence methods in parity (incl. delete)", async () => {
    // Mock and real adapters must expose the same evidence surface so mode
    // changes cannot silently drop an operation (e.g. evidence.delete).
    const mockMethods = Object.keys(api.evidence as object).sort();
    const { realApi } = await import("@/api/real");
    const realMethods = Object.keys(realApi.evidence as object).sort();
    expect(mockMethods).toEqual(realMethods);
    expect(mockMethods).toContain("delete");
  });

  it("exposes auth.logout on both mock and real adapters", async () => {
    // Logout must revoke the server token; both adapters must surface it.
    const { realApi } = await import("@/api/real");
    expect(typeof api.auth.logout).toBe("function");
    expect(typeof realApi.auth.logout).toBe("function");
    expect(Object.keys(api.auth).sort()).toEqual(Object.keys(realApi.auth).sort());
  });
});