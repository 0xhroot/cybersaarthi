import type {
  HTMLAttributes,
  ReactNode,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      {/* min-w keeps data columns readable on narrow viewports: the wrapper
          scrolls horizontally instead of the auto layout crushing cells. */}
      <table
        className={cn("w-full min-w-[640px] border-collapse text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function THead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("border-b border-border", className)} {...props} />;
}

export function TBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border", className)} {...props} />;
}

export function TR({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn("transition-colors hover:bg-surface-2/60", className)}
      {...props}
    />
  );
}

export function TH({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        // nowrap keeps header labels intact ("CONFIDENCE", not "CONFIDENC E");
        // the table wrapper scrolls horizontally instead of breaking words.
        "whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-dim",
        className,
      )}
      {...props}
    />
  );
}

export function TD({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2.5 align-middle text-foreground", className)} {...props} />;
}

export function Separator({ className }: { className?: string }) {
  return <div role="separator" className={cn("h-px w-full bg-border", className)} />;
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 items-center rounded border border-border-strong bg-surface-2 px-1.5 font-mono text-[10px] text-dim",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

/**
 * Machine identifier (record id, sha-256, stored key…) rendered for humans.
 *
 * These strings are long and unbreakable, so the default browser wrapping
 * rules let a single token push its container past the viewport — that is
 * what made the analytics page 1040px wide on a 390px screen. `break-all`
 * plus an explicit wrapping context keeps them inside their column.
 */
export function MonoId({
  value,
  className,
  title,
}: {
  value: string;
  className?: string;
  title?: string;
}) {
  return (
    <span className={cn("break-all font-mono text-dim", className)} title={title ?? value}>
      {value}
    </span>
  );
}

/**
 * A wrapping list of machine identifiers. Uses flex-wrap rather than a joined
 * string so each id is its own breakable box and the list can never widen its
 * parent. Renders nothing when there is nothing to show.
 */
export function IdList({
  ids,
  label,
  max = 6,
  className,
}: {
  ids?: readonly string[] | null;
  label?: string;
  max?: number;
  className?: string;
}) {
  if (!ids || ids.length === 0) return null;
  const shown = ids.slice(0, max);
  const rest = ids.length - shown.length;
  return (
    <p className={cn("flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px] leading-relaxed", className)}>
      {label ? <span className="text-dim">{label}</span> : null}
      {shown.map((id, i) => (
        <span key={id} className="inline-flex min-w-0">
          <MonoId value={id} className="max-w-full" />
          {i < shown.length - 1 || rest > 0 ? <span className="text-dim">,</span> : null}
        </span>
      ))}
      {rest > 0 ? <span className="tabular text-dim">(+{rest} more)</span> : null}
    </p>
  );
}