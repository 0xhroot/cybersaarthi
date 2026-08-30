import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
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

export default function CasesPage() {
  useDocumentTitle("Cases");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const debounced = useDebounce(search, 250);
  const filterStatus = params.get("status") ?? "";
  const page = Number(params.get("page") ?? "1");
  const perPage = 12;

  const createCase = useCreateCase();
  const canCreate = useCan("case.create");

  const cases = useCases({
    search: debounced || undefined,
    status: filterStatus || undefined,
    limit: perPage,
    offset: (page - 1) * perPage,
  });

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced);
    else next.delete("q");
    if (filterStatus) next.set("status", filterStatus);
    else next.delete("status");
    if (page > 1) next.set("page", String(page));
    else next.delete("page");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, filterStatus, page]);

  const openNew = Boolean(params.get("new") === "1");
  const totalPages = cases.data ? Math.max(1, Math.ceil(cases.data.total / perPage)) : 1;

  const [draft, setDraft] = useState({ title: "", description: "", status: "open" as Exclude<CaseStatus, "archived"> });

  const canSubmit = useMemo(() => draft.title.trim().length >= 3, [draft.title]);

  async function onSubmitCreate(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      const created = await createCase.mutateAsync({
        title: draft.title.trim(),
        description: draft.description.trim() || null,
        status: draft.status,
      });
      toast({ title: "Case created", description: `${created.case_number} is ready to investigate.`, variant: "success" });
      navigate(`/app/cases/${created.id}`);
    } catch (err) {
      toast({ title: "Could not create case", description: (err as Error).message, variant: "error" });
    }
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Investigations"
        title="Cases"
        description="Every mandate you can access, in one place."
        actions={
          canCreate ? (
            <Button onClick={() => navigate("/app/cases?new=1")}>
              <Plus className="size-4" /> New case
            </Button>
          ) : undefined
        }
      />

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setParams((p) => {
                const next = new URLSearchParams(p);
                next.delete("page");
                return next;
              });
            }}
            placeholder="Search by title or case number…"
            className="pl-9"
          />
        </div>
        <Select
          value={filterStatus}
          onValueChange={(value) => {
            setParams((p) => {
              const next = new URLSearchParams(p);
              if (value && value !== "all") next.set("status", value);
              else next.delete("status");
              next.delete("page");
              return next;
            });
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-4">
        <ErrorBoundary>
          {cases.isLoading ? (
            <Card>
              <CardContent className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-11" />
                ))}
              </CardContent>
            </Card>
          ) : cases.isError ? (
            <Card>
              <ErrorState error={cases.error} onRetry={() => void cases.refetch()} />
            </Card>
          ) : (cases.data?.items ?? []).length === 0 ? (
            <Card>
              <EmptyState
                icon={<Search className="size-5" />}
                title="No cases match"
                description={debounced ? `Nothing found for “${debounced}”.` : "Create your first case to begin."}
                action={
                  canCreate && !debounced
                    ? { label: "Create a case", onClick: () => navigate("/app/cases?new=1") }
                    : undefined
                }
              />
            </Card>
          ) : (
            <Card>
              <Table>
                <THead>
                  <TR>
                    <TH>Case number</TH>
                    <TH>Title</TH>
                    <TH className="hidden sm:table-cell">Status</TH>
                    <TH className="hidden md:table-cell">Description</TH>
                    <TH className="text-right">Updated</TH>
                  </TR>
                </THead>
                <TBody>
                  {(cases.data?.items ?? []).map((c) => (
                    <TR
                      key={c.id}
                      className={cn("cursor-pointer")}
                      onClick={() => {
                        navigate(`/app/cases/${c.id}`);
                      }}
                    >
                      <TD className="font-mono text-[11px] text-muted">{c.case_number}</TD>
                      <TD className="max-w-[240px] whitespace-nowrap font-medium text-foreground">{c.title}</TD>
                      <TD className="hidden sm:table-cell">
                        <CaseStatusBadge value={c.status} />
                      </TD>
                      <TD className="hidden max-w-[280px] truncate text-xs text-dim md:table-cell">
                        {c.description ?? "—"}
                      </TD>
                      <TD className="whitespace-nowrap text-right text-xs text-dim">
                        {formatDate(c.updated_at)}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Card>
          )}
        </ErrorBoundary>
      </div>

      {totalPages > 1 ? (
        <div className="mt-4 flex items-center justify-between text-xs text-dim">
          <span>
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={page <= 1}
              onClick={() =>
                setParams((p) => {
                  const next = new URLSearchParams(p);
                  next.set("page", String(page - 1));
                  return next;
                })
              }
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= totalPages}
              onClick={() =>
                setParams((p) => {
                  const next = new URLSearchParams(p);
                  next.set("page", String(page + 1));
                  return next;
                })
              }
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <Dialog open={openNew} onOpenChange={(open) => navigate(open ? "/app/cases?new=1" : "/app/cases", { replace: true })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create a case</DialogTitle>
            <DialogDescription>
              Give the investigation a working title. Status and number can be adjusted later.
              {api.src === "mock" ? " In demo mode the case number is generated for you." : ""}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitCreate} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="case-title">Title</Label>
              <Input
                id="case-title"
                autoFocus
                value={draft.title}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                placeholder="e.g. Narco-finance trace — Central corridor"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="case-desc">Description</Label>
              <Textarea
                id="case-desc"
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                placeholder="Brief context for the team…"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={draft.status} onValueChange={(value) => setDraft((d) => ({ ...d, status: value as Exclude<CaseStatus, "archived"> }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="in_progress">In progress</SelectItem>
                  <SelectItem value="closed">Closed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => navigate("/app/cases", { replace: true })}
              >
                Cancel
              </Button>
              <Button type="submit" loading={createCase.isPending} disabled={!canSubmit}>
                Create case
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}