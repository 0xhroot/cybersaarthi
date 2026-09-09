export const apiConfig = {
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000",
  get useMockApi(): boolean {
    return (import.meta.env.VITE_USE_MOCK_API as string | undefined) !== "false";
  },
} as const;

export const isDev = import.meta.env.DEV;
export const isTest = import.meta.env.MODE === "test";