import { Activity, Ban, CircleDot, ShieldCheck, ShieldOff } from "lucide-react";
import type { FieldDeviceStatus, IoTDeviceStatus } from "@/types/domain";
import { cn } from "@/lib/utils";

type Status = FieldDeviceStatus | IoTDeviceStatus;

const styles: Record<string, string> = {
  pending: "border-amber-200 bg-amber-50 text-amber-800",
  approved: "border-emerald-200 bg-emerald-50 text-emerald-800",
  revoked: "border-rose-200 bg-rose-50 text-rose-800",
  registered: "border-slate-200 bg-slate-50 text-slate-700",
  active: "border-emerald-200 bg-emerald-50 text-emerald-800",
  inactive: "border-amber-200 bg-amber-50 text-amber-800",
  seized: "border-blue-200 bg-blue-50 text-blue-800",
  removed: "border-slate-200 bg-slate-50 text-slate-500",
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
