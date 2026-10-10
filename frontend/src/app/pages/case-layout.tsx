import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import {
  Activity,
  Archive,
  BarChart3,
  ChevronDown,
  ClipboardList,
  FileSearch,
  GitBranch,
  Layers3,
  ListChecks,
  Network,
  Settings2,
  Shield,
  Smartphone,
  Users,
} from "lucide-react";
import { useCase, useArchiveCase, useUpdateCase } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { useCaseNavStore } from "@/stores/case-nav";
import { PageContainer } from "@/components/layout/page";
import { CaseStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "", label: "Overview", icon: ClipboardList, end: true },
  { to: "entities", label: "Entities", icon: Users, end: false },
  { to: "evidence", label: "Evidence", icon: FileSearch, end: false },
  { to: "victims", label: "Victims", icon: Shield, end: false },
  { to: "devices", label: "Devices", icon: Smartphone, end: false },
  { to: "iot", label: "IoT", icon: Activity, end: false },
  { to: "graph", label: "Graph", icon: Network, end: false },
  { to: "analytics", label: "Analytics", icon: BarChart3, end: false },
  { to: "hypotheses", label: "Hypotheses", icon: Layers3, end: false },
  { to: "findings", label: "Findings", icon: ListChecks, end: false },
  { to: "reports", label: "Reports", icon: GitBranch, end: false },
  { to: "timeline", label: "Timeline", icon: ClipboardList, end: false },
];

export default function CaseLayout() {
  const { caseId = "" } = useParams();
  const caseQuery = useCase(caseId);
  const setActiveCaseId = useCaseNavStore((s) => s.setActiveCaseId);
  const canUpdate = useCan("case.update");
  const canArchive = useCan("case.archive");
  const archiveCase = useArchiveCase(caseId);
  const updateCase = useUpdateCase(caseId);
  const [statusDialog, setStatusDialog] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);

  useEffect(() => {
    setActiveCaseId(caseId);
    return () => setActiveCaseId(null);
  }, [caseId, setActiveCaseId]);

  function changeStatus(value: string) {
    if (value === caseQuery.data?.status) return;
    setPendingStatus(value);
    setStatusDialog(true);
  }

  async function commitStatus() {
    if (!pendingStatus) return;
    try {
      await updateCase.mutateAsync({ status: pendingStatus as "open" | "in_progress" | "closed" });
      toast({ title: "Status updated", variant: "success" });
      setStatusDialog(false);
    } catch (err) {
      toast({ title: "Could not update status", description: (err as Error).message, variant: "error" });
    }
  }

  async function commitArchive() {
    try {
      await archiveCase.mutateAsync();
      toast({ title: "Case archived", variant: "success" });
      setConfirmArchive(false);
    } catch (err) {
      toast({ title: "Could not archive case", description: (err as Error).message, variant: "error" });
    }
  }

  if (caseQuery.isError) {
    return <PageContainer className="py-10"><div className="mx-auto max-w-xl rounded-lg border border-border bg-surface"><ErrorState error={caseQuery.error} onRetry={() => void caseQuery.refetch()} /></div></PageContainer>;
  }

  return (
    <div className="min-w-0">
      <div className="border-b border-border bg-surface">
        <PageContainer className="py-5 sm:py-6">
          {caseQuery.isLoading ? (
            <div className="space-y-3"><Skeleton className="h-3 w-40" /><Skeleton className="h-8 w-80" /><Skeleton className="h-4 w-full max-w-2xl" /></div>
          ) : caseQuery.data ? (
            <>
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-accent">{caseQuery.data.case_number}</span>
                    <span className="text-border-strong">•</span>
                    <CaseStatusBadge value={caseQuery.data.status} />
                  </div>
                  <h1 className="mt-2 max-w-4xl text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{caseQuery.data.title}</h1>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{caseQuery.data.description ?? "No investigation description has been provided."}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-dim">
                    <span>Created {new Date(caseQuery.data.created_at).toLocaleDateString()}</span>
                    <span>Updated {new Date(caseQuery.data.updated_at).toLocaleDateString()}</span>
                    <span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-success" /> Protected workspace</span>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {canUpdate && caseQuery.data.status !== "archived" ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="secondary"><Settings2 className="size-4" /> Manage <ChevronDown className="size-3.5 text-dim" /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        <DropdownMenuItem onSelect={() => changeStatus("open")}>Mark open</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => changeStatus("in_progress")}>Mark in progress</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => changeStatus("closed")}>Mark closed</DropdownMenuItem>
                        {canArchive ? <><DropdownMenuSeparator /><DropdownMenuItem className="text-critical focus:text-critical" onSelect={() => setConfirmArchive(true)}><Archive className="size-4" /> Archive case</DropdownMenuItem></> : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-border pt-4 text-[11px] text-dim">
                <span className="mr-1 font-semibold uppercase tracking-[0.12em]">Investigation workspace</span>
                <span className="hidden text-border-strong sm:inline">•</span>
                <span>Use the sections below to move from case context to evidence, analysis and reporting.</span>
              </div>
            </>
          ) : null}
        </PageContainer>

        <div className="border-t border-border bg-surface-2/45">
          <PageContainer className="py-0">
            <nav aria-label="Case workspace" className="no-scrollbar flex overflow-x-auto">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                return <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => cn("relative flex shrink-0 items-center gap-2 border-b-2 border-transparent px-3 py-3 text-[12px] font-medium transition-colors", isActive ? "border-accent bg-surface text-accent" : "text-muted hover:bg-surface/70 hover:text-foreground")}>
                  <Icon className="size-3.5" />{tab.label}
                </NavLink>;
              })}
            </nav>
          </PageContainer>
        </div>
      </div>

      <Outlet />

      <Dialog open={statusDialog} onOpenChange={setStatusDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Change case status</DialogTitle><DialogDescription>Moving this case to <span className="font-medium text-foreground">{pendingStatus?.replace("_", " ") ?? ""}</span> is recorded on the timeline.</DialogDescription></DialogHeader>
          <DialogFooter><Button variant="ghost" onClick={() => setStatusDialog(false)}>Cancel</Button><Button onClick={() => void commitStatus()} loading={updateCase.isPending}>Confirm</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        <DialogContent>
          <DialogHeader><DialogTitle>Archive this case?</DialogTitle><DialogDescription>The case will move to the archive and stop accepting further updates. Existing evidence and findings remain retained.</DialogDescription></DialogHeader>
          <DialogFooter><Button variant="ghost" onClick={() => setConfirmArchive(false)}>Cancel</Button><Button variant="danger" onClick={() => void commitArchive()} loading={archiveCase.isPending}><Archive className="size-4" /> Archive case</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
