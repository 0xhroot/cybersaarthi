import type { Api } from "./contract";
import { realApi } from "./real";
import { mockApi } from "./mock";
import { apiConfig } from "@/config/env";

/**
 * The single API facade.
 *
 * Set VITE_USE_MOCK_API=false (and VITE_API_URL to the backend base) to switch
 * to the real adapter. Neither the UI nor the query hooks change.
 */
export const api: Api = apiConfig.useMockApi ? mockApi : realApi;

/** True when the active adapter is the deterministic mock. */
export const isMockMode = api.src === "mock";