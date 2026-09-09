import { cn } from "@/lib/utils";

export function Brand({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="relative grid size-8 shrink-0 place-items-center rounded-lg bg-accent/15 ring-1 ring-accent/30">
        <MarkIcon className="size-4 text-accent" />
      </span>
      {!compact ? (
        <span className="text-sm font-semibold tracking-tight text-foreground">
          Cyber<span className="text-accent">Saarthi</span>
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