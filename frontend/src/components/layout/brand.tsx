import { cn } from "@/lib/utils";

export function Brand({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-center gap-3", className)}>
      <span className="relative grid size-9 shrink-0 place-items-center border border-accent/25 bg-accent-soft text-accent shadow-sm">
        <MarkIcon className="size-5" />
      </span>
      {!compact ? (
        <span className="min-w-0">
          <span className="block truncate text-sm font-bold tracking-tight text-foreground">
            Cyber<span className="text-accent">Saarthi</span>
          </span>
          <span className="block truncate text-[9px] font-medium uppercase tracking-[0.13em] text-dim">
            Investigation Platform
          </span>
        </span>
      ) : null}
    </div>
  );
}

export function MarkIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={className}
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 2.5 19.5 6.75v10.5L12 21.5l-7.5-4.25V6.75L12 2.5Z" />
      <circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none" />
      <path d="M12 7.5v1.9M12 14.6v1.9M7.5 12h1.9M14.6 12h1.9" />
    </svg>
  );
}
