import { describe, expect, it } from "vitest";
import { api, isMockMode } from "@/api";
import { apiConfig } from "@/config/env";

describe("adapter switching", () => {
  it("defaults to the deterministic mock adapter", () => {
    expect(apiConfig.useMockApi).toBe(true);
    expect(api.src).toBe("mock");
    expect(isMockMode).toBe(true);
  });

  it("swaps to the real adapter without changing the facade surface", async () => {
    // The facade must stay stable regardless of VITE_USE_MOCK_API — same keys.
    const viaFacade = Object.keys(api).sort();
    const { realApi } = await import("@/api/real");
    expect(Object.keys(realApi).sort()).toEqual(viaFacade);
  });
});