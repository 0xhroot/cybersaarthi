// Read at build time so the unused adapter can be tree-shaken out of the
// production bundle: the real adapter must never silently fall back to mock
// data, and a production build must never silently fall back to it either.
//
// - An explicit VITE_USE_MOCK_API always wins: "false" selects the real API,
//   anything else (truthy spellings such as "true"/"1") keeps the mock,
//   matching the historical tolerance.
// - When the variable is unset/empty the default depends on the mode:
//   dev and test keep the deterministic mock so `npm run dev` and the vitest
//   suite work without a backend, while a production build (`vite build`)
//   defaults to the real API — a fresh clone has no frontend/.env (it is
//   gitignored), so a deployed bundle must not silently serve demo data.
//
// Written as a plain expression (no helper call) so Rollup/esbuild constant-
// fold it at build time; env.test.ts re-imports this module with a stubbed
// environment to cover both branches.
const mockFlag: string | undefined = import.meta.env.VITE_USE_MOCK_API;
const isProduction =
  import.meta.env.PROD === true || import.meta.env.MODE === "production";

export const apiConfig = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000",
  useMockApi: mockFlag === undefined || mockFlag === ""
    ? !isProduction
    : mockFlag !== "false",
} as const;

export const isDev = import.meta.env.DEV;
export const isTest = import.meta.env.MODE === "test";
