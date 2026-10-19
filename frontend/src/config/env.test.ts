import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Regression tests for the mock/real default.
 *
 * The defect these guard against: a fresh clone has no `frontend/.env`
 * (gitignored), so `VITE_USE_MOCK_API` is unset. A production build made in
 * that state used to default to the deterministic mock adapter — a deployed
 * bundle silently serving demo data. The default is now mode-aware:
 * dev/test keep the mock (so `npm run dev` and vitest work without a
 * backend), production builds default to the real API.
 *
 * `resolve()` below re-imports `@/config/env` under a stubbed
 * `import.meta.env`, so these tests exercise the module's real expression —
 * not a copy of it.
 */
async function resolve(env: Record<string, string | boolean>): Promise<boolean> {
  vi.resetModules();
  for (const [key, value] of Object.entries(env)) {
    vi.stubEnv(key, value as string);
  }
  try {
    const { apiConfig } = await import("@/config/env");
    return apiConfig.useMockApi;
  } finally {
    vi.unstubAllEnvs();
  }
}

describe("apiConfig.useMockApi defaults", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("keeps the mock in dev/test when the variable is unset (npm run dev, vitest)", async () => {
    await expect(
      resolve({ VITE_USE_MOCK_API: "", MODE: "development", PROD: false }),
    ).resolves.toBe(true);
    await expect(
      resolve({ VITE_USE_MOCK_API: "", MODE: "test", PROD: false }),
    ).resolves.toBe(true);
  });

  it("defaults to the REAL adapter in a production build when unset (the regression)", async () => {
    // Fresh clone → no frontend/.env → `vite build` must not ship demo data.
    await expect(
      resolve({ VITE_USE_MOCK_API: "", MODE: "production", PROD: true }),
    ).resolves.toBe(false);
    await expect(resolve({ VITE_USE_MOCK_API: "", MODE: "production" })).resolves.toBe(
      false,
    );
  });

  it("honours an explicit VITE_USE_MOCK_API=false in every mode", async () => {
    await expect(
      resolve({ VITE_USE_MOCK_API: "false", MODE: "production", PROD: true }),
    ).resolves.toBe(false);
    await expect(
      resolve({ VITE_USE_MOCK_API: "false", MODE: "development", PROD: false }),
    ).resolves.toBe(false);
  });

  it("honours an explicit VITE_USE_MOCK_API=true even in a production build", async () => {
    // An intentional mock/demo deployment must keep working.
    await expect(
      resolve({ VITE_USE_MOCK_API: "true", MODE: "production", PROD: true }),
    ).resolves.toBe(true);
  });

  it("keeps the historical tolerance for truthy spellings", async () => {
    await expect(
      resolve({ VITE_USE_MOCK_API: "1", MODE: "development", PROD: false }),
    ).resolves.toBe(true);
    await expect(
      resolve({ VITE_USE_MOCK_API: "anything", MODE: "development", PROD: false }),
    ).resolves.toBe(true);
  });
});
