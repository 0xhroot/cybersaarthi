import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  /** Optional trailing count (e.g. findings by review status). */
  count?: number;
}

/**
 * A URL-synced section tab strip with roving tabindex: the selected tab is
 * `tabIndex=0`, arrow keys (and Home/End) move between tabs, and the
 * selection underline is the accent bar. Extracted from the analytics
 * page so review-style filters (findings status) share one interaction.
 */
export function TabBar({
  items,
  active,
  onChange,
  ariaLabel,
  idPrefix,
  panelId,
  className,
}: {
  items: readonly TabItem[];
  active: string;
  onChange: (id: string) => void;
  ariaLabel: string;
  /** DOM id prefix for each tab button (`{idPrefix}-tab-{id}`). */
  idPrefix: string;
  /** Optional `aria-controls` target (a tabpanel id). */
  panelId?: string;
  className?: string;
}) {
  const focusTab = (id: string) =>
    document.getElementById(`${idPrefix}-tab-${id}`)?.focus();

  const move = (delta: number, to?: "first" | "last") => {
    const index = items.findIndex((item) => item.id === active);
    if (index < 0 || items.length === 0) return;
    const next =
      to === "first"
        ? items[0]
        : to === "last"
          ? items[items.length - 1]
          : items[(index + delta + items.length) % items.length];
    onChange(next.id);
    focusTab(next.id);
  };

  return (
    <div className={cn("border-b border-border", className)}>
      <nav
        aria-label={ariaLabel}
        className="subtle-scrollbar -mb-px flex gap-1 overflow-x-auto"
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            move(1);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            move(-1);
          } else if (event.key === "Home") {
            event.preventDefault();
            move(0, "first");
          } else if (event.key === "End") {
            event.preventDefault();
            move(0, "last");
          }
        }}
      >
        {items.map((item) => {
          const Icon = item.icon;
          const selected = item.id === active;
          return (
            <button
              key={item.id}
              id={`${idPrefix}-tab-${item.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(item.id)}
              className={cn(
                "relative flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-[12px] font-medium transition-colors",
                selected ? "text-accent-strong" : "text-muted hover:text-foreground",
              )}
            >
              {Icon ? <Icon className="size-3.5" aria-hidden /> : null}
              {item.label}
              {item.count != null ? (
                <span
                  className={cn(
                    "tabular rounded-md px-1.5 py-0.5 text-[10px]",
                    selected ? "bg-accent/12 text-accent-strong" : "bg-surface-3 text-dim",
                  )}
                >
                  {item.count}
                </span>
              ) : null}
              {selected ? (
                <span aria-hidden className="absolute inset-x-2 -bottom-px h-0.5 bg-accent" />
              ) : null}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
