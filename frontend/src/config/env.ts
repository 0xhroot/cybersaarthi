export const apiConfig = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000",
  // Read at build time so the unused adapter can be tree-shaken out of the
  // production bundle: the real adapter must never silently fall back to mock
  // data. Default (unset) keeps the deterministic mock so `npm run dev` and
  // the vitest suite work without a backend.
  useMockApi: (import.meta.env.VITE_USE_MOCK_API as string | undefined) !== "false",
} as const;

export const isDev = import.meta.env.DEV;
export const isTest = import.meta.env.MODE === "test";