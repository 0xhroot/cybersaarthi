import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommandPalette } from "@/components/commands/command-palette";
import { mockApi } from "@/api/mock";
import { authSession } from "@/api/client/session";
import { useUiStore } from "@/stores/ui";
import { useCaseNavStore } from "@/stores/case-nav";

function Harness() {
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  return <CommandPalette open={open} onOpenChange={setOpen} />;
}

beforeEach(async () => {
  authSession.clear();
  useUiStore.setState({ paletteOpen: true, sidebarOpen: true });
  useCaseNavStore.setState({ activeCaseId: null });
  await mockApi.auth.login({ username: "investigator", password: "investigator-dev-password" });
});

describe("command palette", () => {
  it("surfaces case search results against the active adapter", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/app"]}>
          <Harness />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const input = screen.getByPlaceholderText(/Search cases and entities/i);
    expect(input).toBeInTheDocument();

    await userEvent.type(input, "Paper Citadel");

    expect(await screen.findByText(/Operation Paper Citadel/i)).toBeInTheDocument();
  });
});