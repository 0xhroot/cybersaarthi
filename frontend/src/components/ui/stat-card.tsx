import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  accent?: string;
  subtitle?: string;
  className?: string;
}

export function StatCard({ label, value, icon, accent, subtitle, className }: StatCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface px-4 py-3.5 transition-colors hover:border-border-strong",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-dim">
            {label}
          </p>
          <p className="mt-1 tabular text-2xl font-semibold tracking-tight text-foreground">
            {value}
          </p>
          {subtitle ? (
            <p className="mt-0.5 truncate text-[10px] text-dim">{subtitle}</p>
          ) : null}
        </div>
        {icon ? (
          <span
            className="grid size-9 shrink-0 place-items-center rounded-lg border bg-surface-2 text-sm"
            style={{ color: accent, borderColor: "var(--color-border)" }}
          >
            {icon}
          </span>
        ) : null}
      </div>
    </div>
  );
}
