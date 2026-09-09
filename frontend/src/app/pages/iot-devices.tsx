import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Plus, Search, Cpu } from "lucide-react";
import { useIoTDevices, useRegisterIoTDevice } from "@/hooks/queries";
import { useDebounce } from "@/hooks/ui";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
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

const STATUS_COLORS: Record<IoTDeviceStatus, string> = {
  registered: "bg-muted text-muted-foreground",
  active: "bg-emerald-500/15 text-emerald-500",
  inactive: "bg-amber-500/15 text-amber-500",
  seized: "bg-blue-500/15 text-blue-500",
  removed: "bg-muted text-muted-foreground",
};

function DeviceStatusBadge({ status }: { status: IoTDeviceStatus }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_COLORS[status] ?? "")}>
      {status}
    </span>
  );
}

export default function IoTDevicesPage() {
  const { caseId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const debounced = useDebounce(query, 300);
  const status = params.get("status") ?? "";
  const [showRegister, setShowRegister] = useState(false);
  const canUpdate = useCan("case.update");

  const devices = useIoTDevices(caseId, {
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
        eyebrow="Field intelligence"
        title="IoT devices"
        description="Phones, routers, trackers and other devices being monitored in this investigation."
        actions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-dim">{devices.data?.total ?? "…"} devices</span>
            {canUpdate && (
              <Button size="sm" onClick={() => setShowRegister(true)}>
                <Plus className="mr-1.5 size-3.5" /> Register device
              </Button>
            )}
          </div>
        }
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search devices…" className="pl-9" />
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
            <SelectItem value="all">All statuses</SelectItem>
            {(["registered", "active", "inactive", "seized", "removed"] as const).map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="mt-4">
        <CardContent className="p-0">
          {devices.isLoading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3">
                  <Skeleton className="h-4 w-36" />
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-4 w-16" />
                </div>
              ))}
            </div>
          ) : devices.isError ? (
            <ErrorState error={devices.error} onRetry={() => void devices.refetch()} />
          ) : devices.data?.items.length === 0 ? (
            <EmptyState
              icon={<Cpu className="size-10" />}
              title="No devices registered"
              description="Register a device to start collecting telemetry for this case."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Name</TH>
                    <TH>Type</TH>
                    <TH>Status</TH>
                    <TH>Serial / IMEI</TH>
                    <TH>Owner</TH>
                    <TH>Last seen</TH>
                  </TR>
                </THead>
                <TBody>
                  {devices.data?.items.map((d) => (
                    <TR key={d.id}>
                      <TD>
                        <Link to={`/app/cases/${caseId}/iot/${d.id}`} className="font-medium text-accent hover:underline">
                          {d.name}
                        </Link>
                        {d.model && <p className="text-xs text-dim">{d.make} {d.model}</p>}
                      </TD>
                      <TD className="capitalize">{d.device_type.replace(/_/g, " ")}</TD>
                      <TD><DeviceStatusBadge status={d.status} /></TD>
                      <TD className="font-mono text-xs">{d.imei ?? d.serial_number}</TD>
                      <TD>{d.owner_name ?? "—"}</TD>
                      <TD className="text-xs text-dim">{d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "—"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {showRegister && <RegisterDeviceDialog caseId={caseId} onClose={() => setShowRegister(false)} />}
    </PageContainer>
  );
}

function RegisterDeviceDialog({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const register = useRegisterIoTDevice(caseId);
  const [name, setName] = useState("");
  const [deviceType, setDeviceType] = useState<IoTDeviceType>("mobile");
  const [serialNumber, setSerialNumber] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [description, setDescription] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !serialNumber.trim()) return;
    try {
      await register.mutateAsync({
        name: name.trim(),
        device_type: deviceType,
        serial_number: serialNumber.trim(),
        make: make || null,
        model: model || null,
        owner_name: ownerName || null,
        description: description || null,
      });
      toast({ title: "Device registered", variant: "success" });
      onClose();
    } catch (err) {
      toast({ title: "Failed to register device", description: (err as Error).message, variant: "error" });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-2xl">
        <h2 className="text-lg font-semibold text-foreground">Register device</h2>
        <p className="mt-1 text-xs text-dim">Log a phone, router, tracker or other equipment involved in this case.</p>
        <form onSubmit={(e) => void handleSubmit(e)} className="mt-5 space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-dim">Name *</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Suspect's phone" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Device type</label>
              <Select value={deviceType} onValueChange={(v) => setDeviceType(v as IoTDeviceType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(["mobile","router","gps_tracker","smart_device","vehicle","cctv","computer","other"] as const).map((t) => (
                    <SelectItem key={t} value={t}>{t.replace(/_/g, " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Serial / IMEI *</label>
              <Input value={serialNumber} onChange={(e) => setSerialNumber(e.target.value)} required placeholder="IMEI or serial number" className="font-mono" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Make</label>
              <Input value={make} onChange={(e) => setMake(e.target.value)} placeholder="e.g. Samsung" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-dim">Model</label>
              <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. Galaxy M13" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-dim">Owner</label>
            <Input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} placeholder="Name of the owner" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-dim">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-dim focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="How is this device relevant to the case?"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={register.isPending}>Register</Button>
          </div>
        </form>
      </div>
    </div>
  );
}