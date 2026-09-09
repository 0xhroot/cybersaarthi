import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { AdminUserOut } from "@/types/domain";

const mutationMutate = vi.hoisted(() => vi.fn());

// Replace Radix DropdownMenu with lightweight buttons so the menu open is
// deterministic in jsdom (Radix pointer/portal behavior is not test-friendly).
vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="menu-content">{children}</div>
  ),
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: () => void;
  }) => (
    <button type="button" onClick={() => onSelect?.()}>
      {children}
    </button>
  ),
}));

vi.mock("@/hooks/queries", () => ({
  useAdminPendingUsers: () => ({
    data: { items: [] as AdminUserOut[] },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useAdminUsers: () => ({
    data: {
      items: [
        {
          id: "u1",
          username: "analyst",
          email: "analyst@cybersaarthi.test",
          status: "ACTIVE" as const,
          roles: ["ANALYST"],
          created_at: "2026-01-01T00:00:00Z",
        },
      ] as AdminUserOut[],
    },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useAdminUserMutation: () => ({ mutate: mutationMutate, isPending: false }),
}));

import AdminUsersPage from "@/app/pages/admin-users";

describe("admin user action error visibility", () => {
  it("surfaces a visible error when an admin mutation fails", async () => {
    mutationMutate.mockImplementation((_action: unknown, opts: { onError?: (e: Error) => void }) => {
      opts.onError?.(new Error("disk quorum unavailable"));
    });
    render(<AdminUsersPage />);

    // Switch to "All users" so the ACTIVE user's action menu is visible.
    fireEvent.click(screen.getByRole("button", { name: /all users/i }));
    const menuTrigger = await screen.findByRole("button", { name: /manage analyst/i });
    fireEvent.click(menuTrigger);

    // Choose a failing action ("Suspend") from the menu.
    fireEvent.click(screen.getByRole("button", { name: /suspend/i }));

    // The error must be surfaced to the operator, not swallowed.
    const alert = await waitFor(() => screen.getByRole("alert"));
    expect(alert.textContent).toContain("disk quorum unavailable");
  });
});