import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BriefcaseBusiness,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Clock3,
  Filter,
  FolderPlus,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useCases, useCreateCase } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { useDebounce } from "@/hooks/ui";
import { api } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { CaseStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBoundary } from "@/components/error-boundary";
import { ErrorState } from "@/components/ui/error-state";
import { toast } from "@/components/ui/toast";
import { formatDate, cn } from "@/lib/utils";
import { useDocumentTitle } from "@/hooks/ui";
import type { CaseStatus } from "@/types/domain";

const STATUS_OPTIONS: Array<Exclude<CaseStatus, "archived">> = ["open", "in_progress", "closed"];
const PER_PAGE = 12;

function statusLabel(status: string) {
  return status === "in_progress" ? "In progress" : status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatCard({ label, value, icon, tone, active, onClick }: { label: string; value: number | undefined; icon: ReactNode; tone: string; active?: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={cn("group text-left", active && "")}>
      <Card className={cn("h-full transition-all duration-200 hover:-translate-y-0.5 hover:border-border-strong hover:shadow-sm", active && "border-accent/50 ring-1 ring-accent/15")}>
        <CardContent className="p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <span className={cn("flex size-9 items-center justify-center rounded-md border bg-surface-2", tone)}>{icon}</span>
            {active ? <span className="text-[10px] font-bold uppercase tracking-wider text-accent">Selected</span> : null}
          </div>
          <div className="mt-4 flex items-end justify-between gap-2">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-dim">{label}</p>
              <p className="mt-1 text-2xl font-bold tracking-tight tabular text-foreground">{value ?? "—"}</p>
            </div>
            <ArrowUpRight className="size-4 text-dim transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-accent" />
          </div>
        </CardContent>
      </Card>
    </button>
  );
}

export default function CasesPage() {
  useDocumentTitle("Cases");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const debounced = useDebounce(search, 250);
  const filterStatus = params.get("status") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? "1"));
  const canCreate = useCan("case.create");
  const createCase = useCreateCase();

  const cases = useCases({ search: debounced || undefined, status: filterStatus || undefined, limit: PER_PAGE, offset: (page - 1) * PER_PAGE });
  const allQuery = useQuery({ queryKey: ["cases", "summary", "all"], queryFn: () => api.cases.list({ limit: 1 }), staleTime: 30_000 });
  const openQuery = useQuery({ queryKey: ["cases", "summary", "open"], queryFn: () => api.cases.list({ status: "open", limit: 1 }), staleTime: 30_000 });
  const progressQuery = useQuery({ queryKey: ["cases", "summary", "in_progress"], queryFn: () => api.cases.list({ status: "in_progress", limit: 1 }), staleTime: 30_000 });
  const closedQuery = useQuery({ queryKey: ["cases", "summary", "closed"], queryFn: () => api.cases.list({ status: "closed", limit: 1 }), staleTime: 30_000 });

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced); else next.delete("q");
    if (filterStatus) next.set("status", filterStatus); else next.delete("status");
    if (page > 1) next.set("page", String(page)); else next.delete("page");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, filterStatus, page]);

  const openNew = params.get("new") === "1";
  const totalPages = cases.data ? Math.max(1, Math.ceil(cases.data.total / PER_PAGE)) : 1;
  const [draft, setDraft] = useState({ title: "", description: "", status: "open" as Exclude<CaseStatus, "archived"> });
  const canSubmit = useMemo(() => draft.title.trim().length >= 3, [draft.title]);
  const hasFilters = Boolean(debounced || filterStatus);

  function setStatus(status: string) {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (status && status !== "all") next.set("status", status); else next.delete("status");
      next.delete("page");
      return next;
    });
  }

  function clearFilters() {
    setSearch("");
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.delete("q"); next.delete("status"); next.delete("page");
      return next;
    });
  }

  async function onSubmitCreate(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      const created = await createCase.mutateAsync({ title: draft.title.trim(), description: draft.description.trim() || null, status: draft.status });
      toast({ title: "Case created", description: `${created.case_number} is ready to investigate.`, variant: "success" });
      navigate(`/app/cases/${created.id}`);
    } catch (err) {
      toast({ title: "Could not create case", description: (err as Error).message, variant: "error" });
    }
  }

  const summaryCards = [
    { label: "Total cases", value: allQuery.data?.total, icon: <BriefcaseBusiness className="size-4" />, tone: "text-accent", status: "" },
    { label: "Open", value: openQuery.data?.total, icon: <CircleDot className="size-4" />, tone: "text-high", status: "open" },
    { label: "In progress", value: progressQuery.data?.total, icon: <Clock3 className="size-4" />, tone: "text-info", status: "in_progress" },
    { label: "Closed", value: closedQuery.data?.total, icon: <CheckCircle2 className="size-4" />, tone: "text-success", status: "closed" },
  ];

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Investigation register"
        title="Cases"
        description="Review, filter and open the investigations available to your role."
        actions={canCreate ? <Button onClick={() => navigate("/app/cases?new=1")}><FolderPlus className="size-4" /> New case</Button> : undefined}
      />

      <section aria-label="Case summary" className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((item) => (
          <StatCard key={item.label} label={item.label} value={item.value} icon={item.icon} tone={item.tone} active={filterStatus === item.status} onClick={() => setStatus(item.status)} />
        ))}
      </section>

      <section className="mt-6 overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
        <div className="border-b border-border bg-surface-2/55 p-4 sm:p-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-dim"><Filter className="size-3.5" /> Case register</div>
              <p className="mt-1 text-sm text-muted">Search by case number or title, then narrow the register by status.</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative sm:w-[320px]">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
                <Input aria-label="Search cases" value={search} onChange={(e) => { setSearch(e.target.value); setParams((p) => { const next = new URLSearchParams(p); next.delete("page"); return next; }); }} placeholder="Search cases…" className="pl-9 bg-surface" />
              </div>
              <Select value={filterStatus || "all"} onValueChange={setStatus}>
                <SelectTrigger className="w-full bg-surface sm:w-[170px]"><SlidersHorizontal className="size-3.5 text-dim" /><SelectValue placeholder="All statuses" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {STATUS_OPTIONS.map((status) => <SelectItem key={status} value={status}>{statusLabel(status)}</SelectItem>)}
                </SelectContent>
              </Select>
              {hasFilters ? <Button variant="ghost" size="sm" onClick={clearFilters}><X className="size-3.5" /> Clear</Button> : null}
            </div>
          </div>
        </div>

        <ErrorBoundary>
          {cases.isLoading ? (
            <div className="space-y-2 p-4">{Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
          ) : cases.isError ? (
            <div className="p-5"><ErrorState error={cases.error} onRetry={() => void cases.refetch()} /></div>
          ) : (cases.data?.items ?? []).length === 0 ? (
            <EmptyState icon={<Search className="size-5" />} title="No cases found" description={debounced ? `Nothing found for “${debounced}”.` : filterStatus ? `There are no ${statusLabel(filterStatus).toLowerCase()} cases.` : "Create your first case to begin."} action={canCreate && !hasFilters ? { label: "Create a case", onClick: () => navigate("/app/cases?new=1") } : undefined} />
          ) : (
            <>
              <div className="hidden md:block">
                <Table>
                  <THead>
                    <TR><TH>Case</TH><TH>Status</TH><TH>Description</TH><TH>Updated</TH><TH className="w-10" /></TR>
                  </THead>
                  <TBody>
                    {(cases.data?.items ?? []).map((c) => (
                      <TR key={c.id} className="group cursor-pointer" onClick={() => navigate(`/app/cases/${c.id}`)}>
                        <TD>
                          <div className="min-w-0">
                            <p className="font-mono text-[10px] font-semibold tracking-wide text-accent">{c.case_number}</p>
                            <p className="mt-1 max-w-[360px] truncate font-semibold text-foreground">{c.title}</p>
                          </div>
                        </TD>
                        <TD><CaseStatusBadge value={c.status} /></TD>
                        <TD className="max-w-[360px] truncate text-xs text-dim">{c.description ?? "No description provided"}</TD>
                        <TD className="whitespace-nowrap"><div className="flex items-center gap-2 text-xs text-dim"><CalendarDays className="size-3.5" />{formatDate(c.updated_at)}</div></TD>
                        <TD><ArrowUpRight className="size-4 text-dim transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-accent" /></TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>

              <div className="divide-y divide-border md:hidden">
                {(cases.data?.items ?? []).map((c) => (
                  <button key={c.id} type="button" onClick={() => navigate(`/app/cases/${c.id}`)} className="group w-full p-4 text-left transition-colors hover:bg-surface-2/60">
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-[10px] font-semibold text-accent">{c.case_number}</span><CaseStatusBadge value={c.status} /></div>
                        <p className="mt-2 font-semibold text-foreground">{c.title}</p>
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-dim">{c.description ?? "No description provided."}</p>
                        <div className="mt-3 flex items-center gap-1.5 text-[11px] text-dim"><CalendarDays className="size-3.5" /> Updated {formatDate(c.updated_at)}</div>
                      </div>
                      <ArrowUpRight className="mt-1 size-4 shrink-0 text-dim group-hover:text-accent" />
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </ErrorBoundary>
      </section>

      {totalPages > 1 ? (
        <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4 text-xs text-dim sm:flex-row sm:items-center sm:justify-between">
          <span>Showing page <strong className="font-semibold text-foreground">{page}</strong> of <strong className="font-semibold text-foreground">{totalPages}</strong> · {cases.data?.total ?? 0} cases</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setParams((p) => { const next = new URLSearchParams(p); next.set("page", String(page - 1)); return next; })}><ChevronLeft className="size-3.5" /> Previous</Button>
            <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setParams((p) => { const next = new URLSearchParams(p); next.set("page", String(page + 1)); return next; })}>Next <ChevronRight className="size-3.5" /></Button>
          </div>
        </div>
      ) : null}

      <Dialog open={openNew} onOpenChange={(open) => navigate(open ? "/app/cases?new=1" : "/app/cases", { replace: true })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Open a new investigation</DialogTitle>
            <DialogDescription>Give the investigation a working title and establish its initial status. {api.src === "mock" ? "In demo mode the case number is generated for you." : "The case number is generated by the service."}</DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitCreate} className="space-y-4">
            <div className="space-y-1.5"><Label htmlFor="case-title">Case title</Label><Input id="case-title" autoFocus value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} placeholder="e.g. Operation Paper Citadel" /><p className="text-[11px] text-dim">Use a clear working title that will be easy to recognize in the register.</p></div>
            <div className="space-y-1.5"><Label htmlFor="case-description">Description</Label><Textarea id="case-description" value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} placeholder="Briefly describe the investigation mandate…" rows={4} /></div>
            <div className="space-y-1.5"><Label htmlFor="case-status">Initial status</Label><Select value={draft.status} onValueChange={(value) => setDraft((d) => ({ ...d, status: value as Exclude<CaseStatus, "archived"> }))}><SelectTrigger id="case-status"><SelectValue /></SelectTrigger><SelectContent>{STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{statusLabel(s)}</SelectItem>)}</SelectContent></Select></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => navigate("/app/cases", { replace: true })}>Cancel</Button><Button type="submit" disabled={!canSubmit} loading={createCase.isPending}>Create case</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
