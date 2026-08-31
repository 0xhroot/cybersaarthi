import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/app/layouts/app-shell";
import { useAuthStore } from "@/stores/auth";
import { useCan, type Permission } from "@/lib/permissions";
import { Brand } from "@/components/layout/brand";
import { SpinnerBlock } from "@/components/ui/loading";

const LoginPage = lazy(() => import("@/app/pages/login"));
const DashboardPage = lazy(() => import("@/app/pages/dashboard"));
const CasesPage = lazy(() => import("@/app/pages/cases"));
const CaseLayout = lazy(() => import("@/app/pages/case-layout"));
const CaseOverviewPage = lazy(() => import("@/app/pages/case-overview"));
const EntitiesPage = lazy(() => import("@/app/pages/entities"));
const EntityDetailPage = lazy(() => import("@/app/pages/entity-detail"));
const EvidencePage = lazy(() => import("@/app/pages/evidence"));
const GraphPage = lazy(() => import("@/app/pages/graph"));
const AnalyticsPage = lazy(() => import("@/app/pages/analytics"));
const HypothesesPage = lazy(() => import("@/app/pages/hypotheses"));
const FindingsPage = lazy(() => import("@/app/pages/findings"));
const FindingDetailPage = lazy(() => import("@/app/pages/finding-detail"));
const TimelinePage = lazy(() => import("@/app/pages/timeline"));
const AuditPage = lazy(() => import("@/app/pages/audit"));
const NoAccessPage = lazy(() => import("@/app/pages/no-access"));
const SettingsPage = lazy(() => import("@/app/pages/settings"));
const NotFoundPage = lazy(() => import("@/app/pages/not-found"));

function BootScreen() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
      <Brand />
      <div className="size-5 animate-spin rounded-full border-2 border-accent/40 border-t-accent" aria-hidden />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();
  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/** F03: a route that additionally demands a permission (e.g. audit.read). */
function RequirePermission({ permission, children }: { permission: Permission; children: ReactNode }) {
  const allowed = useCan(permission);
  if (!allowed) {
    return <NoAccessPage />;
  }
  return <>{children}</>;
}

function PageSuspense() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SpinnerBlock label="Loading workspace…" />
    </div>
  );
}

export function AppRouter() {
  const status = useAuthStore((s) => s.status);
  const bootstrap = useAuthStore((s) => s.bootstrap);

  useEffect(() => {
    if (status === "idle") void bootstrap();
  }, [status, bootstrap]);

  if (status === "idle") return <BootScreen />;

  return (
    <Suspense fallback={<PageSuspense />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="cases" element={<CasesPage />} />
          <Route path="cases/:caseId" element={<CaseLayout />}>
            <Route index element={<CaseOverviewPage />} />
            <Route path="entities" element={<EntitiesPage />} />
            <Route path="entities/:entityId" element={<EntityDetailPage />} />
            <Route path="evidence" element={<EvidencePage />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="hypotheses" element={<HypothesesPage />} />
            <Route path="findings" element={<FindingsPage />} />
            <Route path="findings/:findingId" element={<FindingDetailPage />} />
            <Route path="timeline" element={<TimelinePage />} />
          </Route>
          <Route
            path="audit"
            element={
              <RequirePermission permission="audit.read">
                <AuditPage />
              </RequirePermission>
            }
          />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="/" element={<Navigate to="/app" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}