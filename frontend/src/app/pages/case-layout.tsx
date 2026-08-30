import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { Archive, ChevronDown, Settings2, MoreHorizontal } from "lucide-react";
import { useCase, useArchiveCase, useUpdateCase } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { useCaseNavStore } from "@/stores/case-nav";
import { PageContainer } from "@/components/layout/page";
import { CaseStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "", label: "Overview", end: true },
  { to: "entities", label: "Entities", end: false },
  { to: "evidence", label: "Evidence", end: false },
  { to: "graph", label: "Graph", end: false },
  { to: "analytics", label: "Analytics", end: false },
  { to: "hypotheses", label: "Hypotheses", end: false },
  { to: "findings", label: "Findings", end: false },
  { to: "timeline", label: "Timeline", end: false },
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

  async function changeStatus(value: string) {
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
    return (
      <PageContainer className="py-10">
        <div className="mx-auto max-w-xl rounded-lg border border-border bg-surface">
          <ErrorState error={caseQuery.error} onRetry={() => void caseQuery.refetch()} />
        </div>
      </PageContainer>
    );
  }

  return (
    <div>
      {/* Case header */}
      <div className="border-b border-border bg-surface/60">
        <PageContainer className="py-5">
          {caseQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-6 w-72" />
            </div>
          ) : caseQuery.data ? (
            <div className="flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-accent/80">
                    {caseQuery.data.case_number}
                  </p>
                  <CaseStatusBadge value={caseQuery.data.status} />
                </div>
                <h1 className="mt-1 truncate text-xl font-semibold tracking-tight text-foreground">
                  {caseQuery.data.title}
                </h1>
                <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-dim">
                  {caseQuery.data.description ?? "No description provided."}
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                {canUpdate && caseQuery.data.status !== "archived" ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="secondary" className="gap-1.5">
                        <Settings2 className="size-4" /> Manage <ChevronDown className="size-3.5 text-dim" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => changeStatus("open")}>
                        Mark open
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => changeStatus("in_progress")}>
                        Mark in progress
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => changeStatus("closed")}>
                        Mark closed
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
                {canArchive && caseQuery.data.status !== "archived" ? (
                  <Button variant="ghost" size="icon" aria-label="Archive case" onClick={() => setConfirmArchive(true)}>
                    <MoreHorizontal className="size-4" />
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
        </PageContainer>

        {/* Workspace tabs */}
        <div className="no-scrollbar overflow-x-auto border-t border-border/70">
          <PageContainer className="flex gap-0.5 py-0">
            {TABS.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.end}
                className={({ isActive }) =>
                  cn(
                    "relative whitespace-nowrap px-3 pb-3 pt-2 text-[13px] transition-colors",
                    isActive ? "font-medium text-accent" : "text-muted hover:text-foreground",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {tab.label}
                    {isActive ? (
                      <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" />
                    ) : null}
                  </>
                )}
              </NavLink>
            ))}
          </PageContainer>
        </div>
      </div>

      <Outlet />

      {/* Status change dialog */}
      <Dialog open={statusDialog} onOpenChange={setStatusDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change case status</DialogTitle>
            <DialogDescription>
              Moving this case to{" "}
              <span className="font-medium text-foreground">{pendingStatus?.replace("_", " ") ?? ""}</span> is
              recorded on the timeline.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setStatusDialog(false)}>
              Cancel
            </Button>
            <Button onClick={() => void commitStatus()} loading={updateCase.isPending}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Archive confirm */}
      <Dialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Archive this case?</DialogTitle>
            <DialogDescription>
              The case is closed to further updates and moves to the archive. Evidence and findings are retained.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmArchive(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void commitArchive()} loading={archiveCase.isPending}>
              <Archive className="size-4" /> Archive case
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}