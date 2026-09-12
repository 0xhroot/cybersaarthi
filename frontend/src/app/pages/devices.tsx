import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { QrCode, Scan, ShieldCheck, ShieldOff, Smartphone } from "lucide-react";
import QRCode from "qrcode";
import {
  useApproveFieldDevice,
  useFieldDevices,
  useRevokeFieldDevice,
  useServerHealth,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { toast } from "@/components/ui/toast";
import { cn, formatRelative } from "@/lib/utils";
import { buildPairingUri, computeServerFingerprint, normalizeApiBase, randomHex } from "@/lib/pairing";
import type { FieldDeviceStatus } from "@/types/domain";

const STATUS_COLORS: Record<FieldDeviceStatus, string> = {
  pending: "bg-amber-500/15 text-amber-500",
  approved: "bg-emerald-500/15 text-emerald-500",
  revoked: "bg-rose-500/15 text-rose-500",
};

function DeviceStatusBadge({ status }: { status: FieldDeviceStatus }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_COLORS[status] ?? "")}>
      {status}
    </span>
  );
}

export default function FieldDevicesPage() {
  const { caseId = "" } = useParams();
  const devices = useFieldDevices(caseId);
  const approve = useApproveFieldDevice(caseId);
  const revoke = useRevokeFieldDevice(caseId);
  const [showPair, setShowPair] = useState(false);
  const canManage = useCan("users.manage");

  async function approveDevice(deviceId: string) {
    try {
      await approve.mutateAsync(deviceId);
      toast({ title: "Device approved", variant: "success" });
    } catch (err) {
      toast({ title: "Could not approve device", description: (err as Error).message, variant: "error" });
    }
  }

  async function revokeDevice(deviceId: string) {
    try {
      await revoke.mutateAsync(deviceId);
      toast({ title: "Device revoked", variant: "success" });
    } catch (err) {
      toast({ title: "Could not revoke device", description: (err as Error).message, variant: "error" });
    }
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Field coordination"
        title="Field devices"
        description="Android agents enrolled for this case submit signed evidence packages over the LAN. Approve a device to accept its data."
        actions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-dim">{devices.data?.total ?? "…"} enrolled</span>
            <Button size="sm" onClick={() => setShowPair(true)}>
              <QrCode className="mr-1.5 size-3.5" /> Pair new device
            </Button>
          </div>
        }
      />

      <Card className="mt-4">
        <CardContent className="p-0">
          {devices.isLoading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </div>
          ) : devices.isError ? (
            <ErrorState error={devices.error} onRetry={() => void devices.refetch()} />
          ) : devices.data?.items.length === 0 ? (
            <EmptyState
              icon={<Smartphone className="size-10" />}
              title="No field devices enrolled"
              description="Open the Android Field Agent on a phone, scan a pairing code and register its key with this case."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Device</TH>
                    <TH>Status</TH>
                    <TH>Key algorithm</TH>
                    <TH>Last seen</TH>
                    <TH>Enrolled</TH>
                    <TH>Actions</TH>
                  </TR>
                </THead>
                <TBody>
                  {devices.data?.items.map((d) => (
                    <TR key={d.id}>
                      <TD>
                        <p className="font-medium text-foreground">{d.platform}</p>
                        <p className="font-mono text-xs text-dim">{d.serial}</p>
                      </TD>
                      <TD><DeviceStatusBadge status={d.status as FieldDeviceStatus} /></TD>
                      <TD className="font-mono text-xs">{d.signature_algorithm}</TD>
                      <TD className="text-xs text-dim">
                        {d.last_seen_at ? (
                          <span className="inline-flex items-center gap-1">
                            <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
                            {formatRelative(d.last_seen_at)}
                          </span>
                        ) : (
                          "never"
                        )}
                      </TD>
                      <TD className="text-xs text-dim">{formatRelative(d.created_at)}</TD>
                      <TD>
                        <div className="flex items-center gap-2">
                          {canManage && d.status === "pending" && (
                            <Button size="sm" variant="secondary" onClick={() => void approveDevice(d.id)}>
                              <ShieldCheck className="mr-1.5 size-3.5" /> Approve
                            </Button>
                          )}
                          {canManage && d.status === "approved" && (
                            <Button size="sm" variant="ghost" onClick={() => void revokeDevice(d.id)}>
                              <ShieldOff className="mr-1.5 size-3.5" /> Revoke
                            </Button>
                          )}
                        </div>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {showPair && <PairDeviceDialog onClose={() => setShowPair(false)} />}
    </PageContainer>
  );
}

function PairDeviceDialog({ onClose }: { onClose: () => void }) {
  const health = useServerHealth();
  const [rawBase, setRawBase] = useState(
    () => `http://${globalThis.location?.hostname || "localhost"}:8000`,
  );
  const [apiBase, setApiBase] = useState("");
  const [qrImage, setQrImage] = useState<string | null>(null);
  const [pairingUri, setPairingUri] = useState("");

  async function generate() {
    if (!health.data || health.data.status !== "ok") {
      toast({
        title: "Backend health unavailable",
        description: "Pairing encodes the live server fingerprint; confirm the web app can reach the backend.",
        variant: "error",
      });
      return;
    }
    const base = normalizeApiBase(rawBase);
    if (!base) return;
    const fingerprint = computeServerFingerprint(health.data.service, health.data.version);
    const expiresAtEpochMillis = Date.now() + 10 * 60 * 1000;
    const uri = buildPairingUri({ baseUrl: base, fingerprint, nonce: randomHex(16), expiresAtEpochMillis });
    const svg = await QRCode.toString(uri, { type: "svg", margin: 1, width: 320, errorCorrectionLevel: "M" });
    setApiBase(base);
    setPairingUri(uri);
    setQrImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`);
  }

  useEffect(() => {
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function copyUri() {
    try {
      await navigator.clipboard.writeText(pairingUri);
      toast({ title: "Pairing code copied", variant: "success" });
    } catch {
      toast({ title: "Could not copy", variant: "error" });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Pair an Android field device</h2>
            <p className="mt-1 text-xs text-dim">
              In the Field Agent open <span className="font-medium text-foreground">Connect → Scan QR</span> and
              point the camera at this code. It carries the backend URL, a one-time nonce and the server identity
              fingerprint.
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-dim hover:text-foreground">×</button>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium text-dim">Backend URL the phone should reach</label>
          <div className="flex gap-2">
            <Input
              value={rawBase}
              onChange={(e) => setRawBase(e.target.value)}
              placeholder="http://192.168.0.127:8000"
              className="font-mono"
              onKeyDown={(e) => {
                if (e.key === "Enter") void generate();
              }}
            />
            <Button type="button" variant="secondary" onClick={() => void generate()}>
              <Scan className="mr-1.5 size-3.5" /> Regenerate
            </Button>
          </div>
          <p className="mt-1.5 text-[11px] text-dim">
            The phone must be on the same LAN/Wi-Fi as the investigation server. Use the machine&apos;s LAN IP, not
            localhost, so the scanning phone can connect back.
          </p>
        </div>

        <div className="mt-5 flex items-center justify-center gap-6">
          {qrImage ? (
            <div className="rounded-xl border border-border bg-white p-3">
              <img src={qrImage} alt="Pairing QR code" width={320} height={320} />
            </div>
          ) : (
            <div className="flex h-52 w-52 items-center justify-center rounded-xl border border-border bg-muted/30">
              <Skeleton className="h-24 w-24" />
            </div>
          )}
          {health.isError ? (
            <p className="max-w-[180px] text-xs text-rose-500">
              Could not read the server health; fingerprint unavailable.
            </p>
          ) : null}
        </div>

        {apiBase && (
          <div className="mt-4 space-y-1 truncate rounded-md border border-border bg-muted/20 px-3 py-2 font-mono text-[11px] text-dim">
            <p>base: {apiBase}</p>
            {health.data ? (
              <p>
                fingerprint: {computeServerFingerprint(health.data.service, health.data.version)}
              </p>
            ) : null}
            <p>valid for: 10 minutes</p>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Close</Button>
          {pairingUri && (
            <Button type="button" onClick={() => void copyUri()} disabled={!pairingUri}>
              Copy pairing code
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}