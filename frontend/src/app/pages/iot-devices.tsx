import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Activity, Cpu, Plus, Search, ShieldAlert, Smartphone, Wifi } from "lucide-react";
import { useIoTDevices, useRegisterIoTDevice } from "@/hooks/queries";
import { useDebounce } from "@/hooks/ui";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { DeviceStatusBadge } from "@/components/layout/device-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { IoTDeviceStatus, IoTDeviceType } from "@/types/domain";

const STATUS_OPTIONS = ["registered", "active", "inactive", "seized", "removed"] as const;

export default function IoTDevicesPage() {
  const { caseId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const debounced = useDebounce(query, 300);
  const status = params.get("status") ?? "";
  const [showRegister, setShowRegister] = useState(false);
  const canUpdate = useCan("case.update");

  const devices = useIoTDevices(caseId, { status: status || undefined, search: debounced || undefined, limit: 200 });

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced); else next.delete("q");
    if (status) next.set("status", status); else next.delete("status");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, status]);

  const items = devices.data?.items ?? [];
  const counts = STATUS_OPTIONS.reduce<Record<string, number>>((acc, key) => {
    acc[key] = items.filter((d) => d.status === key).length;
    return acc;
  }, {});
  const liveCount = counts.active ?? 0;
  const attentionCount = (counts.inactive ?? 0) + (counts.seized ?? 0);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Field intelligence · device registry"
        title="Connected devices"
        description="Maintain a clear operational picture of phones, trackers, routers and other devices associated with this investigation."
        actions={canUpdate ? <Button size="sm" onClick={() => setShowRegister(true)}><Plus className="mr-1.5 size-3.5" /> Register device</Button> : null}
      />

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={Cpu} label="Registered" value={devices.data?.total ?? "…"} detail="Known devices" />
        <Metric icon={Activity} label="Active" value={devices.isLoading ? "…" : liveCount} detail="Currently active" tone="green" />
        <Metric icon={ShieldAlert} label="Needs review" value={devices.isLoading ? "…" : attentionCount} detail="Inactive or seized" tone={attentionCount ? "amber" : "slate"} />
        <Metric icon={Wifi} label="Search scope" value={status ? status.replace(/_/g, " ") : "All"} detail="Current filter" tone="blue" />
      </div>

      <Card className="mt-5 overflow-hidden">
        <CardContent className="border-b border-border bg-surface-2/60 p-3 sm:p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-foreground">Device registry</h2>
              <p className="mt-0.5 text-xs text-dim">Search by device name, identifier or owner.</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 sm:w-72">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
                <Input aria-label="Search devices" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search devices…" className="bg-surface pl-9" />
              </div>
              <Select value={status || "all"} onValueChange={(v) => setParams((p) => { const next = new URLSearchParams(p); if (v && v !== "all") next.set("status", v); else next.delete("status"); return next; })}>
                <SelectTrigger className="w-full bg-surface sm:w-44"><SelectValue placeholder="All statuses" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>

        {devices.isLoading ? (
          <div className="divide-y divide-border p-1">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="flex gap-4 px-4 py-4"><Skeleton className="h-5 w-40" /><Skeleton className="h-5 w-20" /><Skeleton className="h-5 w-24" /></div>)}</div>
        ) : devices.isError ? (
          <ErrorState error={devices.error} onRetry={() => void devices.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState icon={<Cpu className="size-10" />} title={query || status ? "No matching devices" : "No devices registered"} description={query || status ? "Try a different search or clear the status filter." : "Register a device to start collecting telemetry for this case."} />
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <Table>
                <THead><TR><TH>Device</TH><TH>Status</TH><TH>Identifier</TH><TH>Owner</TH><TH>Last seen</TH></TR></THead>
                <TBody>
                  {items.map((d) => (
                    <TR key={d.id}>
                      <TD><Link to={`/app/cases/${caseId}/iot/${d.id}`} className="group flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg border border-border bg-surface-2 text-dim group-hover:border-accent/40 group-hover:text-accent"><Smartphone className="size-4" /></span><span><span className="block font-medium text-foreground group-hover:text-accent">{d.name}</span><span className="text-xs capitalize text-dim">{d.make} {d.model ?? d.device_type.replace(/_/g, " ")}</span></span></Link></TD>
                      <TD><DeviceStatusBadge status={d.status as IoTDeviceStatus} /></TD>
                      <TD className="font-mono text-xs text-dim">{d.imei ?? d.serial_number}</TD>
                      <TD>{d.owner_name ?? "—"}</TD>
                      <TD className="text-xs text-dim">{d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "Never seen"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
            <div className="divide-y divide-border md:hidden">
              {items.map((d) => <Link key={d.id} to={`/app/cases/${caseId}/iot/${d.id}`} className="block p-4 hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"><div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl border border-border bg-surface-2"><Smartphone className="size-4 text-dim" /></span><div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-foreground">{d.name}</p><p className="mt-0.5 text-xs capitalize text-dim">{d.device_type.replace(/_/g, " ")}</p></div><DeviceStatusBadge status={d.status as IoTDeviceStatus} /></div><div className="mt-3 grid grid-cols-2 gap-3 text-xs"><span><span className="block text-dim">Identifier</span><span className="font-mono text-foreground">{d.imei ?? d.serial_number}</span></span><span><span className="block text-dim">Last seen</span><span className="text-foreground">{d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "Never"}</span></span></div></div></div></Link>)}
            </div>
          </>
        )}
      </Card>

      {showRegister && <RegisterDeviceDialog caseId={caseId} onClose={() => setShowRegister(false)} />}
    </PageContainer>
  );
}

function Metric({ icon: Icon, label, value, detail, tone = "slate" }: { icon: typeof Cpu; label: string; value: string | number; detail: string; tone?: "slate" | "green" | "amber" | "blue" }) {
  const toneClass = { slate: "bg-slate-50 text-slate-700", green: "bg-emerald-50 text-emerald-700", amber: "bg-amber-50 text-amber-700", blue: "bg-blue-50 text-blue-700" }[tone];
  return <div className="rounded-xl border border-border bg-surface p-4"><div className="flex items-start justify-between"><span className={cn("grid size-9 place-items-center rounded-lg", toneClass)}><Icon className="size-4" /></span><span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-dim">{label}</span></div><p className="mt-4 text-2xl font-semibold tracking-tight text-foreground">{value}</p><p className="mt-0.5 text-xs text-dim">{detail}</p></div>;
}

function RegisterDeviceDialog({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const register = useRegisterIoTDevice(caseId);
  const [name, setName] = useState(""); const [deviceType, setDeviceType] = useState<IoTDeviceType>("mobile"); const [serialNumber, setSerialNumber] = useState(""); const [make, setMake] = useState(""); const [model, setModel] = useState(""); const [ownerName, setOwnerName] = useState(""); const [description, setDescription] = useState("");
  async function handleSubmit(e: React.FormEvent) { e.preventDefault(); if (!name.trim() || !serialNumber.trim()) return; try { await register.mutateAsync({ name: name.trim(), device_type: deviceType, serial_number: serialNumber.trim(), make: make || null, model: model || null, owner_name: ownerName || null, description: description || null }); toast({ title: "Device registered", variant: "success" }); onClose(); } catch (err) { toast({ title: "Failed to register device", description: (err as Error).message, variant: "error" }); } }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]"><div role="dialog" aria-modal="true" aria-labelledby="register-device-title" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-surface shadow-2xl"><div className="border-b border-border px-6 py-5"><div className="flex items-start gap-3"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700"><Cpu className="size-5" /></span><div><h2 id="register-device-title" className="text-lg font-semibold text-foreground">Register device</h2><p className="mt-1 text-xs leading-relaxed text-dim">Create a device record for equipment relevant to this investigation.</p></div></div></div><form onSubmit={(e) => void handleSubmit(e)} className="space-y-5 p-6"><Field label="Device name" required><Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Suspect's phone" /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Device type"><Select value={deviceType} onValueChange={(v) => setDeviceType(v as IoTDeviceType)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(["mobile","router","gps_tracker","smart_device","vehicle","cctv","computer","other"] as const).map((t) => <SelectItem key={t} value={t}>{t.replace(/_/g, " ")}</SelectItem>)}</SelectContent></Select></Field><Field label="Serial / IMEI" required><Input value={serialNumber} onChange={(e) => setSerialNumber(e.target.value)} required placeholder="IMEI or serial number" className="font-mono" /></Field></div><div className="grid gap-4 sm:grid-cols-2"><Field label="Make"><Input value={make} onChange={(e) => setMake(e.target.value)} placeholder="e.g. Samsung" /></Field><Field label="Model"><Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. Galaxy M13" /></Field></div><Field label="Owner"><Input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} placeholder="Name of the owner" /></Field><Field label="Case relevance"><textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none placeholder:text-dim focus:border-accent focus:ring-2 focus:ring-accent/10" placeholder="How is this device relevant to the case?" /></Field><div className="flex justify-end gap-2 border-t border-border pt-4"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={register.isPending}>Register device</Button></div></form></div></div>;
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) { return <div><label className="mb-1.5 block text-xs font-semibold text-foreground">{label}{required && <span className="ml-1 text-rose-600">*</span>}</label>{children}</div>; }
