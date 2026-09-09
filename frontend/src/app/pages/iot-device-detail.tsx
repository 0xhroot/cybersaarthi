import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, MapPin, RadioTower, Smartphone, Trash2, Plus } from "lucide-react";
import { useIoTDevice, useIoTDeviceStats, useIoTEvents, useUpdateIoTDevice, useDeleteIoTDevice, useRecordIoTEvent } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { Input } from "@/components/ui/input";
import { toast as toaster } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/ui";
import { cn } from "@/lib/utils";
import type { IoTDeviceStatus, IoTEventType } from "@/types/domain";

const EVENT_ICONS: Record<IoTEventType, typeof MapPin> = {
  location: MapPin,
  connectivity: RadioTower,
  message: Smartphone,
  call: Smartphone,
  app_use: Smartphone,
  tamper: Smartphone,
  power: Smartphone,
  network: RadioTower,
  custom: Smartphone,
};

const EVENT_TONES: Record<IoTEventType, string> = {
  location: "text-blue-500 bg-blue-500/10",
  connectivity: "text-emerald-500 bg-emerald-500/10",
  message: "text-amber-500 bg-amber-500/10",
  call: "text-purple-500 bg-purple-500/10",
  app_use: "text-cyan-500 bg-cyan-500/10",
  tamper: "text-red-500 bg-red-500/10",
  power: "text-slate-400 bg-slate-400/10",
  network: "text-teal-500 bg-teal-500/10",
  custom: "text-muted bg-muted",
};

function KeyVal({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-dim">{label}</dt>
      <dd className="mt-0.5 text-sm text-foreground break-words">{value ?? "—"}</dd>
    </div>
  );
}

export default function IoTDeviceDetailPage() {
  const { caseId = "", deviceId = "" } = useParams();
  const navigate = useNavigate();
  useDocumentTitle("Device");
  const canUpdate = useCan("case.update");

  const device = useIoTDevice(caseId, deviceId);
  const stats = useIoTDeviceStats(caseId, deviceId);
  const events = useIoTEvents(caseId, { device_id: deviceId, limit: 200 });
  const updateDevice = useUpdateIoTDevice(caseId);
  const deleteDevice = useDeleteIoTDevice(caseId);
  const recordEvent = useRecordIoTEvent(caseId);

  const [newStatus] = useState<IoTDeviceStatus>("active");
  const [showNoteForm, setShowNoteForm] = useState(false);
  const [noteDesc, setNoteDesc] = useState("");
  const [noteType, setNoteType] = useState<IoTEventType>("custom");
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (device.isLoading) {
    return <PageContainer className="py-10"><Skeleton className="h-6 w-48" /><Skeleton className="mt-4 h-56 w-full" /></PageContainer>;
  }
  if (device.isError || !device.data) {
    return <PageContainer className="py-10"><ErrorState error={device.error ?? new Error("Device not found")} onRetry={() => void device.refetch()} /></PageContainer>;
  }

  const d = device.data;

  async function changeStatus(next: IoTDeviceStatus) {
    try {
      await updateDevice.mutateAsync({ deviceId, input: { status: next } });
      toaster({ title: "Device status updated", variant: "success" });
    } catch (err) {
      toaster({ title: "Update failed", description: (err as Error).message, variant: "error" });
    }
  }

  async function submitEvent() {
    if (!noteDesc.trim()) return;
    try {
      await recordEvent.mutateAsync({
        device_id: deviceId,
        event_type: noteType,
        event_time: new Date().toISOString(),
        description: noteDesc.trim(),
      });
      toaster({ title: "Event recorded", variant: "success" });
      setNoteDesc("");
      setShowNoteForm(false);
    } catch (err) {
      toaster({ title: "Record failed", description: (err as Error).message, variant: "error" });
    }
  }

  async function handleDelete() {
    try {
      await deleteDevice.mutateAsync(deviceId);
      toaster({ title: "Device removed", variant: "success" });
      navigate(`/app/cases/${caseId}/iot`);
    } catch (err) {
      toaster({ title: "Delete failed", description: (err as Error).message, variant: "error" });
    }
  }

  return (
    <PageContainer>
      <div className="mb-4 flex items-center gap-2">
        <Link to={`/app/cases/${caseId}/iot`} className="text-sm text-dim hover:text-foreground">
          <ArrowLeft className="mr-1 inline size-4" /> IoT devices
        </Link>
        <span className="text-dim">/</span>
        <span className="text-sm font-medium text-foreground">{d.name}</span>
      </div>

      <PageHeader
        eyebrow={`${d.device_type} · ${d.status}`}
        title={d.name}
        description={d.description ?? "No description."}
        actions={
          canUpdate && d.status !== "removed" ? (
            <div className="flex items-center gap-2">
              <select
                value={newStatus}
                onChange={(e) => void changeStatus(e.target.value as IoTDeviceStatus)}
                className="rounded-lg border border-border-strong bg-surface px-3 py-1.5 text-xs text-foreground outline-none focus:border-accent"
              >
                {(["active", "inactive", "seized", "removed"] as const).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ) : null
        }
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
              <KeyVal label="Type" value={d.device_type.replace(/_/g, " ")} />
              <KeyVal label="Make / Model" value={d.make ? `${d.make}${d.model ? ` ${d.model}` : ""}` : d.model} />
              <KeyVal label="Serial number" value={d.serial_number} />
              <KeyVal label="IMEI" value={d.imei} />
              <KeyVal label="IP address" value={d.ip_address} />
              <KeyVal label="MAC address" value={d.mac_address} />
              <KeyVal label="Operating system" value={d.os ? `${d.os}${d.os_version ? ` ${d.os_version}` : ""}` : d.os_version} />
              <KeyVal label="Owner" value={d.owner_name} />
              <KeyVal label="Owner phone" value={d.owner_phone} />
              <KeyVal label="First seen" value={d.first_seen_at ? new Date(d.first_seen_at).toLocaleString() : null} />
              <KeyVal label="Last seen" value={d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : null} />
              <KeyVal label="Events" value={stats.data?.event_count ?? d.event_count} />
            </dl>
            {stats.data && stats.data.by_type && Object.keys(stats.data.by_type).length > 0 && (
              <div className="mt-5">
                <h3 className="text-xs font-medium text-dim mb-2">Event breakdown</h3>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(stats.data.by_type).map(([t, n]) => (
                    <span key={t} className="rounded-full bg-surface-2 px-2.5 py-1 text-xs">
                      <span className="capitalize">{t.replace(/_/g, " ")}</span> <span className="font-medium text-accent">{n}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-medium text-dim">Telemetry feed</h3>
              {canUpdate && (
                <Button size="sm" variant="secondary" onClick={() => setShowNoteForm((s) => !s)}>
                  <Plus className="mr-1 size-3" /> Add note
                </Button>
              )}
            </div>

            {showNoteForm && (
              <div className="space-y-2 rounded-md border border-border p-3">
                <select
                  value={noteType}
                  onChange={(e) => setNoteType(e.target.value as IoTEventType)}
                  className="w-full rounded-md border border-border-strong bg-surface px-2 py-1.5 text-xs text-foreground"
                >
                  {(["location","connectivity","message","call","app_use","tamper","power","network","custom"] as const).map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <Input value={noteDesc} onChange={(e) => setNoteDesc(e.target.value)} placeholder="Event description…" />
                <div className="flex justify-end">
                  <Button size="sm" onClick={() => void submitEvent()} loading={recordEvent.isPending}>Record</Button>
                </div>
              </div>
            )}

            {events.isLoading ? (
              <div className="space-y-2"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
            ) : events.isError ? (
              <ErrorState error={events.error} onRetry={() => void events.refetch()} />
            ) : (events.data?.items ?? []).length === 0 ? (
              <p className="py-4 text-center text-xs text-dim">No telemetry events yet.</p>
            ) : (
              <div className="divide-y divide-border">
                {(events.data?.items ?? []).map((e) => {
                  const Icon = EVENT_ICONS[e.event_type] ?? Smartphone;
                  return (
                    <div key={e.id} className="py-2.5">
                      <div className="flex items-start gap-2.5">
                        <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", EVENT_TONES[e.event_type] ?? "bg-muted")}>
                          <Icon className="size-3.5" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium capitalize text-foreground">{e.event_type.replace(/_/g, " ")}</p>
                            <span className="shrink-0 text-[11px] text-dim">{new Date(e.event_time).toLocaleString()}</span>
                          </div>
                          {e.description && <p className="mt-0.5 text-xs leading-relaxed text-muted">{e.description}</p>}
                          {e.location_label && <p className="mt-0.5 text-xs text-dim">📍 {e.location_label}</p>}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setConfirmDelete(false)}>
          <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold">Remove device?</h2>
            <p className="mt-1 text-xs text-dim">All telemetry for this device will be permanently deleted.</p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
              <Button variant="danger" onClick={() => void handleDelete()} loading={deleteDevice.isPending}>Delete</Button>
            </div>
          </div>
        </div>
      )}
    </PageContainer>
  );
}