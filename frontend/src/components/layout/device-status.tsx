import { Activity, Ban, CircleDot, ShieldCheck, ShieldOff } from "lucide-react";
import type { FieldDeviceStatus, IoTDeviceStatus } from "@/types/domain";
import { cn } from "@/lib/utils";

type Status = FieldDeviceStatus | IoTDeviceStatus;

/** Token-toned with the same recipe as ui/badge (bg-tone/12 · text-tone ·
 *  border-tone/25) — the old amber-50/emerald-800 pairs were light-theme
 *  leftovers that rendered as near-white chips in dark mode. */
const styles: Record<string, string> = {
  pending: "border-high/25 bg-high/12 text-high",
  approved: "border-success/25 bg-success/12 text-success",
  revoked: "border-critical/25 bg-critical/12 text-critical",
  registered: "border-border bg-surface-3 text-muted",
  active: "border-success/25 bg-success/12 text-success",
  inactive: "border-high/25 bg-high/12 text-high",
  seized: "border-info/25 bg-info/12 text-info",
  removed: "border-border bg-surface-3 text-dim",
};

const icons: Record<string, typeof Activity> = {
  pending: CircleDot,
  approved: ShieldCheck,
  revoked: ShieldOff,
  registered: CircleDot,
  active: Activity,
  inactive: CircleDot,
  seized: ShieldCheck,
  removed: Ban,
};

export function DeviceStatusBadge({ status }: { status: Status }) {
  const Icon = icons[status] ?? CircleDot;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold capitalize tracking-wide", styles[status] ?? styles.registered)}>
      <Icon className="size-3" aria-hidden="true" />
      {status.replace(/_/g, " ")}
    </span>
  );
}
