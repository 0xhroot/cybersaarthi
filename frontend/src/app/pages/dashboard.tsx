import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FolderKanban, ArrowRight, Plus } from "lucide-react";
import { api } from "@/api";
import { useCases } from "@/hooks/queries";
import { useAuthStore } from "@/stores/auth";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CaseStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate, initials } from "@/lib/utils";
import { useDocumentTitle } from "@/hooks/ui";

function StatCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-dim">{label}</p>
          <p className="tabular mt-1 text-2xl font-semibold tracking-tight text-foreground">{value}</p>
        </div>
        <span className="grid size-9 place-items-center rounded-full" style={{ backgroundColor: "transparent", border: `1px solid color-mix(in srgb, ${tone} 30%, transparent)`, color: tone }}>
          <FolderKanban className="size-4" />
        </span>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  useDocumentTitle("Dashboard");
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const cases = useCases({ limit: 100 });
  const canCreate = useCan("case.create");
  const canAudit = useCan("audit.read");

  const featured = useQuery({
    queryKey: ["dashboard", "featured"],
    queryFn: async () => {
      const list = await api.cases.list({ limit: 100 });
      return list.items[0] ?? null;
    },
    staleTime: 60_000,
    enabled: cases.isSuccess,
  });

  const items = cases.data?.items ?? [];
  const open = items.filter((c) => c.status === "open").length;
  const inProgress = items.filter((c) => c.status === "in_progress").length;
  const closed = items.filter((c) => c.status === "closed" || c.status === "archived").length;

  const highlight = featured.data;

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace"
        title={`Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, ${user?.username ?? "analyst"}`}
        description="A single surface for every case, its evidence and its network."
        actions={
          canCreate ? (
            <Button onClick={() => navigate("/app/cases?new=1")}>
              <Plus className="size-4" /> New case
            </Button>
          ) : undefined
        }
      />

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {(cases.isLoading ? [0, 0, 0] : [open, inProgress, closed]).map((value, index) =>
          cases.isLoading ? (
            <Skeleton key={index} className="h-[88px]" />
          ) : (
            <StatCard
              key={index}
              label={["Open", "In progress", "Closed"][index] ?? ""}
              value={value}
              tone={["#d6a14e", "#6d9ec2", "#7e8a99"][index] ?? "#7e8a99"}
            />
          ),
        )}
      </div>

      {highlight ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="mt-6"
        >
          <Link
            to={`/app/cases/${highlight.id}`}
            className="group relative block overflow-hidden rounded-lg border border-accent/30 bg-gradient-to-br from-surface via-surface-2 to-surface p-6 transition-colors hover:border-accent/60"
          >
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(214,161,78,0.12),transparent_60%)]" />
            <div className="relative flex flex-wrap items-center gap-4">
              <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent/15 ring-1 ring-accent/30">
                <span className="text-sm font-semibold text-accent">{initials(highlight.title)}</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-medium uppercase tracking-wider text-accent/80">{highlight.case_number}</p>
                <h2 className="mt-0.5 truncate text-base font-semibold tracking-tight text-foreground">{highlight.title}</h2>
                <p className="mt-1 line-clamp-1 text-xs text-dim">{highlight.description ?? "No description provided."}</p>
              </div>
              <div className="flex items-center gap-3">
                <CaseStatusBadge value={highlight.status} />
                <span className="flex items-center gap-1 text-xs text-dim">
                  Updated {formatDate(highlight.updated_at)}
                  <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </div>
          </Link>
        </motion.div>
      ) : null}

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent cases</CardTitle>
            <Link to="/app/cases" className="text-xs text-accent hover:text-accent-strong">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {cases.isLoading ? (
              <div className="space-y-2">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                title="No cases yet"
                description="Create your first case to begin investigating."
                action={canCreate ? { label: "Create a case", onClick: () => navigate("/app/cases?new=1") } : undefined}
              />
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Case number</TH>
                    <TH>Title</TH>
                    <TH>Status</TH>
                    <TH className="text-right">Updated</TH>
                  </TR>
                </THead>
                <TBody>
                  {items.slice(0, 6).map((c) => (
                    <TR key={c.id} className="cursor-pointer" onClick={() => navigate(`/app/cases/${c.id}`)}>
                      <TD className="font-mono text-[11px] text-muted">{c.case_number}</TD>
                      <TD className="max-w-[260px] truncate font-medium text-foreground">{c.title}</TD>
                      <TD>
                        <CaseStatusBadge value={c.status} />
                      </TD>
                      <TD className="text-right text-xs text-dim">{formatDate(c.updated_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quick actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              <Button variant="secondary" className="w-full justify-between" onClick={() => navigate("/app/cases?new=1")}>
                Create a case <ArrowRight className="size-4" />
              </Button>
              <Button
                variant="ghost"
                className="w-full justify-between"
                onClick={() => navigate("/app/cases")}
              >
                Browse all cases <ArrowRight className="size-4" />
              </Button>
              {canAudit ? (
                <Button variant="ghost" className="w-full justify-between" onClick={() => navigate("/app/audit")}>
                  Review audit log <ArrowRight className="size-4" />
                </Button>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>About this build</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs leading-relaxed text-dim">
              <p>
                The workspace runs against a <span className="text-muted">deterministic mock adapter</span> by
                default. Point it at the backend with <code className="font-mono">VITE_USE_MOCK_API=false</code>.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}