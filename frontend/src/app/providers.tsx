import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { authSession } from "@/api/client/session";
import { useAuthStore } from "@/stores/auth";

const RETRY_DISABLED_STATUSES = new Set([400, 401, 403, 404, 422, 429]);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        RETRY_DISABLED_STATUSES.has((error as { status?: number }).status ?? 0)
          ? false
          : failureCount < 2,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      gcTime: 5 * 60_000,
    },
    mutations: {
      retry: false,
    },
  },
});

function registerUnauthorizedHandler() {
  authSession.setOnUnauthorized(() => {
    useAuthStore.getState().logout();
  });
}

export function AppProviders({ children }: { children: ReactNode }) {
  useEffect(() => {
    registerUnauthorizedHandler();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}