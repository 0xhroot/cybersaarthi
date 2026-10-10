import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useVictim, useUpdateVictim, useDeleteVictim } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/loading";
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
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { VictimClassification, VictimStatus, VictimUpdateRequest } from "@/types/domain";

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
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium", STATUS_COLORS[status] ?? "")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-dim">{label}</dt>
      <dd className="mt-0.5 text-sm text-foreground">{value ?? "—"}</dd>
    </div>
  );
}

function formatCurrency(amount: number | null, currency?: string | null) {
  if (amount === null || amount === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency ?? "INR", maximumFractionDigits: 0 }).format(amount);
}

export default function VictimDetailPage() {
  const { caseId = "", victimId = "" } = useParams();
  const navigate = useNavigate();
  const canUpdate = useCan("case.update");

  const victim = useVictim(caseId, victimId);
  const updateVictim = useUpdateVictim(caseId);
  const deleteVictim = useDeleteVictim(caseId);

  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [form, setForm] = useState<Partial<VictimUpdateRequest>>({});

  function startEdit() {
    if (!victim.data) return;
    const v = victim.data;
    setForm({
      name: v.name,
      classification: v.classification,
      phone: v.phone,
      email: v.email,
      status: v.status,
      incident_type: v.incident_type,
      fraud_category: v.fraud_category,
      amount_lost: v.amount_lost,
      description: v.description,
      investigator_notes: v.investigator_notes,
    });
    setEditing(true);
  }

  async function saveEdit() {
    try {
      await updateVictim.mutateAsync({ victimId, input: form });
      toast({ title: "Victim updated", variant: "success" });
      setEditing(false);
    } catch (err) {
      toast({ title: "Failed to update", description: (err as Error).message, variant: "error" });
    }
  }

  async function handleDelete() {
    try {
      await deleteVictim.mutateAsync(victimId);
      toast({ title: "Victim removed", variant: "success" });
      navigate(`/app/cases/${caseId}/victims`);
    } catch (err) {
      toast({ title: "Failed to delete", description: (err as Error).message, variant: "error" });
    }
  }

  function updateField<K extends keyof VictimUpdateRequest>(key: K, value: VictimUpdateRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  if (victim.isLoading) {
    return (
      <PageContainer className="py-10">
        <Skeleton className="mb-4 h-6 w-48" />
        <Skeleton className="h-48 w-full" />
      </PageContainer>
    );
  }

  if (victim.isError || !victim.data) {
    return (
      <PageContainer className="py-10">
        <ErrorState error={victim.error ?? new Error("Victim not found")} onRetry={() => void victim.refetch()} />
      </PageContainer>
    );
  }

  const v = victim.data;

  return (
    <PageContainer>
      <div className="mb-4 flex items-center gap-2">
        <Link to={`/app/cases/${caseId}/victims`} className="text-sm text-dim hover:text-foreground">
          <ArrowLeft className="mr-1 inline size-4" />
          Victims
        </Link>
        <span className="text-dim">/</span>
        <span className="text-sm font-medium text-foreground">{v.name}</span>
      </div>

      <PageHeader
        eyebrow={v.case_id}
        title={v.name}
        description={v.description ?? "No description"}
        actions={
          canUpdate && v.status !== "closed" ? (
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={startEdit}>
                <Pencil className="mr-1.5 size-3.5" /> Edit
              </Button>
              <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 className="mr-1.5 size-3.5" /> Delete
              </Button>
            </div>
          ) : null
        }
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {/* Main info */}
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-4">
              <VictimStatusBadge status={v.status} />
              <span className="text-xs text-dim capitalize">{v.classification}</span>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
              <Field label="Phone" value={v.phone} />
              <Field label="Email" value={v.email} />
              <Field label="Gender" value={v.gender} />
              <Field label="Incident type" value={v.incident_type} />
              <Field label="Fraud category" value={v.fraud_category} />
              <Field label="Amount lost" value={formatCurrency(v.amount_lost, v.currency)} />
              <Field label="Recovery amount" value={formatCurrency(v.recovery_amount, v.currency)} />
              <Field label="Reported amount" value={formatCurrency(v.reported_amount, v.currency)} />
              <Field label="Recovery status" value={v.recovery_status} />
            </dl>
            {v.statement && (
              <div className="mt-4 rounded-md bg-muted/50 p-3">
                <p className="text-xs font-medium text-dim">Victim statement</p>
                <p className="mt-1 text-sm leading-relaxed">{v.statement}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Sidebar */}
        <Card>
          <CardContent className="p-5 space-y-4">
            <div>
              <h3 className="text-xs font-medium text-dim mb-2">Investigator notes</h3>
              <p className="text-sm text-foreground whitespace-pre-wrap">{v.investigator_notes ?? "No notes yet."}</p>
            </div>
            <div>
              <h3 className="text-xs font-medium text-dim mb-2">Digital accounts</h3>
              {v.digital_accounts && v.digital_accounts.length > 0 ? (
                <ul className="space-y-1">
                  {v.digital_accounts.map((acc, i) => (
                    <li key={i} className="text-sm">{JSON.stringify(acc)}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-dim">None recorded.</p>
              )}
            </div>
            <div>
              <h3 className="text-xs font-medium text-dim mb-2">Wallet addresses</h3>
              {v.wallet_addresses && v.wallet_addresses.length > 0 ? (
                <ul className="space-y-1">
                  {v.wallet_addresses.map((w, i) => (
                    <li key={i} className="font-mono text-xs break-all">{w}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-dim">None recorded.</p>
              )}
            </div>
            <div className="border-t border-border pt-3">
              <Field label="Created" value={new Date(v.created_at).toLocaleString()} />
              <Field label="Updated" value={new Date(v.updated_at).toLocaleString()} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Edit dialog */}
      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit victim</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Name</label>
              <Input value={(form.name as string) ?? ""} onChange={(e) => updateField("name", e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-dim">Status</label>
                <Select value={(form.status as string) ?? ""} onValueChange={(val) => updateField("status", val as VictimStatus)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(["reported","under_investigation","evidence_collected","recovery_initiated","recovered","closed"] as const).map((s) => (
                      <SelectItem key={s} value={s}>{s.replace(/_/g, " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-dim">Classification</label>
                <Select value={(form.classification as string) ?? ""} onValueChange={(val) => updateField("classification", val as VictimClassification)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(["individual","organization","government","financial_institution","unknown"] as const).map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-dim">Phone</label>
                <Input value={(form.phone as string) ?? ""} onChange={(e) => updateField("phone", e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-dim">Email</label>
                <Input value={(form.email as string) ?? ""} onChange={(e) => updateField("email", e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-dim">Incident type</label>
                <Input value={(form.incident_type as string) ?? ""} onChange={(e) => updateField("incident_type", e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-dim">Amount lost</label>
                <Input type="number" value={String(form.amount_lost ?? "")} onChange={(e) => updateField("amount_lost", e.target.value ? parseFloat(e.target.value) : null)} />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Description</label>
              <textarea
                value={(form.description as string) ?? ""}
                onChange={(e) => updateField("description", e.target.value)}
                rows={2}
                className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-dim focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Investigator notes</label>
              <textarea
                value={(form.investigator_notes as string) ?? ""}
                onChange={(e) => updateField("investigator_notes", e.target.value)}
                rows={3}
                className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-dim focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            <Button onClick={() => void saveEdit()} loading={updateVictim.isPending}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove victim?</DialogTitle>
            <DialogDescription>This will permanently remove {v.name} from this case.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="danger" onClick={() => void handleDelete()} loading={deleteVictim.isPending}>
              <Trash2 className="mr-1.5 size-3.5" /> Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
