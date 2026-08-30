import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppRouter } from "@/app/router";
import { useAuthStore } from "@/stores/auth";
import { authSession } from "@/api/client/session";

function renderApp(initialEntry = "/app") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AppRouter />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  authSession.clear();
  useAuthStore.setState({ status: "idle", user: null, roles: [], permissions: [], error: null });
});

describe("route guards", () => {
  it("sends anonymous visitors to /login instead of the workspace", async () => {
    useAuthStore.setState({
      status: "anonymous",
      user: null,
      roles: [],
      permissions: [],
      error: null,
    });
    renderApp("/app/cases");
    expect(await screen.findByText(/Sign in to continue/i)).toBeInTheDocument();
  });

  it("boots to the login screen when no session is stored", async () => {
    renderApp("/");
    expect(await screen.findByText(/Sign in to continue/i)).toBeInTheDocument();
  });

  it("renders the dashboard for an authenticated administrator", async () => {
    await useAuthStore.getState().login("admin", "admin-dev-password");
    expect(useAuthStore.getState().status).toBe("authenticated");

    renderApp("/app");
    expect(
      await screen.findByText(/Good (morning|afternoon|evening), admin/i, {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Sign in to continue/i)).not.toBeInTheDocument();
  });

  it("blocks the audit log for viewers whose role lacks audit.read", async () => {
    await useAuthStore.getState().login("viewer", "viewer-demo-password");
    expect(useAuthStore.getState().permissions).not.toContain("audit.read");

    renderApp("/app/audit");
    expect(await screen.findByText(/No access/i, {}, { timeout: 4000 })).toBeInTheDocument();
  });
});