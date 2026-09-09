import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-3", className)}
      aria-hidden
    />
  );
}

export function Progress({
  value,
  className,
  tone = "accent",
}: {
  value: number;
  className?: string;
  tone?: "accent" | "success" | "high" | "medium" | "critical" | "info";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const bar = {
    accent: "bg-accent",
    success: "bg-success",
    high: "bg-high",
    medium: "bg-medium",
    critical: "bg-critical",
    info: "bg-info",
  }[tone];
  return (
    <div
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-surface-3", className)}
    >
      <div
        className={cn("h-full rounded-full transition-all duration-500", bar)}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export function SpinnerBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted">
      <span className="size-5 animate-spin rounded-full border-2 border-accent/40 border-t-accent" aria-hidden />
      <span className="text-sm">{label}</span>
    </div>
  );
}