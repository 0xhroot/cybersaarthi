import { useEffect, useState } from "react";
import { NavLink, useNavigate, Outlet } from "react-router-dom";
import {
  Activity,
  ChevronRight,
  ClipboardList,
  FileText,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import { useCan } from "@/lib/permissions";
import { api } from "@/api";
import { cn, initials } from "@/lib/utils";
import { Brand } from "@/components/layout/brand";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CommandPalette } from "@/components/commands/command-palette";
import { PreferencesMenu } from "@/components/layout/preferences-menu";
import { getLanguage, t, type Language } from "@/lib/i18n";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const roles = useAuthStore((s) => s.roles);
  const logout = useAuthStore((s) => s.logout);
  const paletteOpen = useUiStore((s) => s.paletteOpen);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);
  const canAudit = useCan("audit.read");
  const canManageUsers = useCan("users.manage");
  const navigate = useNavigate();
  const isDemo = api.src === "mock";
  const roleLabel = roles[0] ?? "analyst";
  const [language, setLang] = useState<Language>(getLanguage);

  useEffect(() => {
    const onLanguage = () => setLang(getLanguage());
    window.addEventListener("cybersaarthi-language-change", onLanguage);
    return () => window.removeEventListener("cybersaarthi-language-change", onLanguage);
  }, []);

  const navItems = [
    { to: "/app", label: t("dashboard", language), icon: LayoutDashboard, end: true },
    { to: "/app/cases", label: t("cases", language), icon: FolderKanban, end: false },
    ...(canAudit ? [{ to: "/app/audit", label: t("audit", language), icon: ClipboardList, end: false }] : []),
    ...(canManageUsers ? [{ to: "/app/users", label: t("users", language), icon: Users, end: false }] : []),
    { to: "/app/settings", label: t("settings", language), icon: Settings, end: false },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div className="gov-top-rule" aria-hidden="true" />

      {sidebarOpen ? (
        <button
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-[35] bg-slate-900/35 md:hidden"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-sidebar flex w-[268px] flex-col border-r border-border bg-surface transition-transform duration-300 md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-[76px] items-center justify-between border-b border-border px-5">
          <Brand />
          <button
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
            className="rounded-sm p-1.5 text-dim hover:bg-surface-2 hover:text-foreground md:hidden"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="border-b border-border bg-surface-2/60 px-4 py-4">
          <Button size="sm" variant="primary" className="h-9 w-full justify-center" onClick={() => navigate("/app/cases")}>
            <Plus className="size-4" />
            Create new case
          </Button>
        </div>

        <div className="px-4 pt-5">
          <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Main navigation</p>
          <nav className="space-y-0.5" aria-label="Primary navigation">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  cn(
                    "group flex min-h-10 items-center gap-3 border-l-2 px-3 text-sm transition-colors",
                    isActive
                      ? "border-accent bg-accent-soft font-semibold text-accent-strong"
                      : "border-transparent text-muted hover:bg-surface-2 hover:text-foreground",
                  )
                }
              >
                <item.icon className="size-[17px] shrink-0" aria-hidden="true" />
                <span className="truncate">{item.label}</span>
                <ChevronRight className="ml-auto size-3.5 opacity-0 transition-opacity group-[.active]:opacity-100" />
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="mt-auto border-t border-border p-4">
          <button
            type="button"
            className="flex w-full items-center gap-3 px-2 py-2 text-left hover:bg-surface-2"
            onClick={() => navigate("/app/settings")}
          >
            <span className="grid size-9 shrink-0 place-items-center border border-accent/20 bg-accent-soft text-xs font-bold text-accent-strong">
              {initials(user?.username ?? "SA")}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-foreground">{user?.username}</span>
              <span className="block truncate text-[11px] capitalize text-dim">{roleLabel.toLowerCase()}</span>
            </span>
            <Settings className="size-4 text-dim" aria-hidden="true" />
          </button>
        </div>
      </aside>

      <div className="flex min-h-[calc(100vh-3px)] min-w-0 flex-col md:pl-[268px]">
        <header className="sticky top-0 z-topbar border-b border-border bg-surface">
          <div className="flex min-h-[68px] items-center gap-3 px-4 sm:px-6">
            <button
              aria-label="Open navigation"
              onClick={() => setSidebarOpen(true)}
              className="rounded-sm p-2 text-muted hover:bg-surface-2 md:hidden"
            >
              <Menu className="size-5" />
            </button>

            <div className="min-w-0 flex-1">
              <div className="hidden sm:block"><Breadcrumbs /></div>
              <button
                type="button"
                onClick={() => setPaletteOpen(true)}
                className="mt-0.5 flex h-9 w-full max-w-[520px] items-center gap-2 border border-border bg-surface-2 px-3 text-left text-xs text-dim hover:border-border-strong hover:bg-surface"
              >
                <Search className="size-4 shrink-0" aria-hidden="true" />
                <span className="truncate">Search cases, entities, evidence...</span>
                <span className="ml-auto hidden items-center gap-1 sm:flex">
                  <kbd className="border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-dim">Ctrl</kbd>
                  <kbd className="border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-dim">K</kbd>
                </span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              <PreferencesMenu />
              <div className="hidden items-center gap-1.5 border-l border-border pl-3 sm:flex">
                <ShieldCheck className="size-4 text-success" aria-hidden="true" />
                <span className="text-[11px] font-medium text-muted">Secure workspace</span>
              </div>
              {isDemo ? <Badge tone="accent">Demo</Badge> : <Badge tone="info">Live</Badge>}
              <Button variant="ghost" size="icon-sm" aria-label="Sign out" onClick={logout} className="text-muted">
                <LogOut className="size-4" />
              </Button>
            </div>
          </div>
          <div className="gov-tricolour h-px opacity-80" aria-hidden="true" />
        </header>

        <div className="border-b border-border bg-surface px-4 py-2 sm:hidden">
          <Breadcrumbs />
        </div>

        <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 outline-none">
          <Outlet />
        </main>

        <footer className="border-t border-border bg-surface px-6 py-3 text-[10px] text-dim">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5"><Activity className="size-3" /> CyberSaarthi Investigation Platform</span>
            <span className="inline-flex items-center gap-1.5"><FileText className="size-3" /> Official workspace interface</span>
          </div>
        </footer>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
