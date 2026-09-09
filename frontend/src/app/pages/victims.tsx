import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Plus, Search, UserX } from "lucide-react";
import { useVictims, useCreateVictim } from "@/hooks/queries";
import { useDebounce } from "@/hooks/ui";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { toast } from "@/components/ui/toast";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { VictimClassification, VictimStatus } from "@/types/domain";

const STATUSES: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "reported", label: "Reported" },
  { value: "under_investigation", label: "Under investigation" },
  { value: "evidence_collected", label: "Evidence collected" },
  { value: "recovery_initiated", label: "Recovery initiated" },
  { value: "recovered", label: "Recovered" },
  { value: "closed", label: "Closed" },
];

const STATUS_COLORS: Record<VictimStatus, string> = {
  reported: "bg-muted text-muted-foreground",
  under_investigation: "bg-blue-500/15 text-blue-500",
  evidence_collected: "bg-amber-500/15 text-amber-500",
  recovery_initiated: "bg-purple-500/15 text-purple-500",
  recovered: "bg-emerald-500/15 text-emerald-500",
  closed: "bg-muted text-muted-foreground",
};

function VictimStatusBadge({ status }: { status: VictimStatus }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_COLORS[status] ?? "")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function formatCurrency(amount: number | null, currency?: string | null) {
  if (amount === null || amount === undefined) return "—";
  const fmt = new Intl.NumberFormat("en-IN", { style: "currency", currency: currency ?? "INR", maximumFractionDigits: 0 });
  return fmt.format(amount);
}

export default function VictimsPage() {
  const { caseId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const debounced = useDebounce(query, 300);
  const status = params.get("status") ?? "";
  const [showCreate, setShowCreate] = useState(false);
  const canUpdate = useCan("case.update");

  const victims = useVictims(caseId, {
    status: status || undefined,
    search: debounced || undefined,
    limit: 200,
  });

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced);
    else next.delete("q");
    if (status) next.set("status", status);
    else next.delete("status");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, status]);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Case intelligence"
        title="Victims"
        description="People and organizations harmed in this investigation."
        actions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-dim">{victims.data?.total ?? "…"} victims</span>
            {canUpdate && (
              <Button size="sm" onClick={() => setShowCreate(true)}>
                <Plus className="mr-1.5 size-3.5" /> Add victim
              </Button>
            )}
          </div>
        }
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search victims…" className="pl-9" />
        </div>
        <Select
          value={status}
          onValueChange={(v) => {
            setParams((p) => {
              const next = new URLSearchParams(p);
              if (v && v !== "all") next.set("status", v);
              else next.delete("status");
              return next;
            });
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="mt-4">
        <CardContent className="p-0">
          {victims.isLoading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-16" />
                </div>
              ))}
            </div>
          ) : victims.isError ? (
            <ErrorState error={victims.error} onRetry={() => void victims.refetch()} />
          ) : victims.data?.items.length === 0 ? (
            <EmptyState
              icon={<UserX className="size-10" />}
              title="No victims yet"
              description="Add a victim to track the people harmed in this case."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Name</TH>
                    <TH>Classification</TH>
                    <TH>Status</TH>
                    <TH>Amount Lost</TH>
                    <TH>Incident Type</TH>
                    <TH>Added</TH>
                  </TR>
                </THead>
                <TBody>
                  {victims.data?.items.map((v) => (
                    <TR key={v.id}>
                      <TD>
                        <Link
                          to={`/app/cases/${caseId}/victims/${v.id}`}
                          className="font-medium text-accent hover:underline"
                        >
                          {v.name}
                        </Link>
                        {v.email && (
                          <p className="text-xs text-dim">{v.email}</p>
                        )}
                      </TD>
                      <TD className="capitalize">{v.classification}</TD>
                      <TD><VictimStatusBadge status={v.status} /></TD>
                      <TD>{formatCurrency(v.amount_lost, v.currency)}</TD>
                      <TD>{v.incident_type ?? "—"}</TD>
                      <TD className="text-xs text-dim">
                        {new Date(v.created_at).toLocaleDateString()}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {showCreate && (
        <CreateVictimDialog caseId={caseId} onClose={() => setShowCreate(false)} />
      )}
    </PageContainer>
  );
}

function CreateVictimDialog({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const createVictim = useCreateVictim(caseId);
  const [name, setName] = useState("");
  const [classification, setClassification] = useState<VictimClassification>("individual");
  const [incidentType, setIncidentType] = useState("");
  const [description, setDescription] = useState("");
  const [amountLost, setAmountLost] = useState("");
  const [statement, setStatement] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createVictim.mutateAsync({
        name: name.trim(),
        classification,
        incident_type: incidentType || null,
        description: description || null,
        amount_lost: amountLost ? parseFloat(amountLost) : null,
        statement: statement || null,
      });
      toast({ title: "Victim added", variant: "success" });
      onClose();
    } catch (err) {
      toast({ title: "Failed to add victim", description: (err as Error).message, variant: "error" });
    }
  }

  return (
    <Dialog open onOpenChange={() => onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add victim</DialogTitle>
          <DialogDescription>Record information about a person or organization harmed in this case.</DialogDescription>
        </DialogHeader>
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-dim">Name *</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Full name or organization" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Classification</label>
              <Select value={classification} onValueChange={(v) => setClassification(v as VictimClassification)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="individual">Individual</SelectItem>
                  <SelectItem value="organization">Organization</SelectItem>
                  <SelectItem value="government">Government</SelectItem>
                  <SelectItem value="financial_institution">Financial institution</SelectItem>
                  <SelectItem value="unknown">Unknown</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Incident type</label>
              <Input value={incidentType} onChange={(e) => setIncidentType(e.target.value)} placeholder="e.g. phishing, UPI fraud" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Amount lost</label>
              <Input type="number" value={amountLost} onChange={(e) => setAmountLost(e.target.value)} placeholder="0" min="0" step="0.01" />
            </div>
            <div />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-dim">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-dim focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="Brief description of what happened…"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-dim">Victim statement</label>
            <textarea
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-dim focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="Direct account from the victim…"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={createVictim.isPending}>Add victim</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
