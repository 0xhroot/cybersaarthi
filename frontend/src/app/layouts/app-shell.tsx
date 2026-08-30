import { NavLink, useNavigate, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  FolderKanban,
  ScrollText,
  Settings,
  Search,
  LogOut,
  Menu,
  X,
  Plus,
  ChevronRight,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import { useCan } from "@/lib/permissions";
import { api } from "@/api";
import { cn, initials } from "@/lib/utils";
import { Brand } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { CommandPalette } from "@/components/commands/command-palette";

const NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/app/cases", label: "Cases", icon: FolderKanban, end: false },
];

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const roles = useAuthStore((s) => s.roles);
  const logout = useAuthStore((s) => s.logout);
  const paletteOpen = useUiStore((s) => s.paletteOpen);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);
  const canAudit = useCan("audit.read");
  const navigate = useNavigate();
  const isDemo = api.src === "mock";

  const navItems = [
    ...NAV,
    ...(canAudit
      ? [{ to: "/app/audit", label: "Audit log", icon: ScrollText, end: false }]
      : []),
    { to: "/app/settings", label: "Settings", icon: Settings, end: false },
  ];

  const roleLabel = roles[0] ?? "analyst";

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      {/* Mobile scrim */}
      {sidebarOpen ? (
        <button
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-[35] bg-black/60 backdrop-blur-[1px] md:hidden"
        />
      ) : null}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-sidebar flex w-56 flex-col border-r border-border bg-surface transition-transform duration-300",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
          "md:translate-x-0",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <Brand />
          <button
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
            className="rounded-md p-1 text-dim hover:bg-surface-2 hover:text-foreground md:hidden"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="px-3 pt-3">
          <Button
            size="sm"
            variant="primary"
            className="w-full justify-start"
            onClick={() => navigate("/app/cases")}
          >
            <Plus className="size-4" />
            New case
          </Button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-surface-3 font-medium text-foreground shadow-[inset_2px_0_0_var(--color-accent)]"
                    : "text-muted hover:bg-surface-2 hover:text-foreground",
                )
              }
            >
              <item.icon className="size-4 shrink-0" />
              <span className="truncate">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border p-3">
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-surface-2"
                  onClick={() => navigate("/app/settings")}
                >
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent/15 text-[11px] font-medium text-accent-strong ring-1 ring-accent/25">
                    {initials(user?.username ?? "SA")}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">
                      {user?.username}
                    </span>
                    <span className="block truncate text-[11px] capitalize text-dim">
                      {roleLabel.toLowerCase()}
                    </span>
                  </span>
                  <ChevronRight className="size-3.5 text-dim" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">Account & settings</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col md:pl-56">
        {/* Topbar */}
        <header className="sticky top-0 z-topbar flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-md">
          <button
            aria-label="Open navigation"
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-foreground md:hidden"
          >
            <Menu className="size-5" />
          </button>

          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="group flex h-8 min-w-0 flex-1 max-w-md items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-sm text-dim transition-colors hover:border-border-strong hover:text-muted"
          >
            <Search className="size-3.5 shrink-0" />
            <span className="truncate">Search cases, entities, evidence…</span>
            <span className="ml-auto hidden shrink-0 items-center gap-1 sm:flex">
              <kbd className="rounded border border-border-strong bg-surface-2 px-1.5 font-mono text-[10px] text-dim">
                Ctrl
              </kbd>
              <kbd className="rounded border border-border-strong bg-surface-2 px-1.5 font-mono text-[10px] text-dim">
                K
              </kbd>
            </span>
          </button>

          <div className="ml-auto flex items-center gap-2">
            {isDemo ? <Badge tone="accent">Demo</Badge> : <Badge tone="info">Live</Badge>}
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Sign out"
              onClick={logout}
              className="text-muted"
            >
              <LogOut className="size-4" />
            </Button>
          </div>
        </header>

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}