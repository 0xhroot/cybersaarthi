import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/** Acronyms kept intact when humanizing machine keys. */
const ACRONYMS: Record<string, string> = {
  ai: "AI",
  iot: "IoT",
  id: "ID",
  url: "URL",
  sha: "SHA",
};

/** `source_locator` → `source locator`, `tzAssumed` → `tz assumed`, `sha256` unchanged. */
export function humanizeKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => ACRONYMS[word.toLowerCase()] ?? word)
    .join(" ");
}

/** Render one payload value as display text. Arrays join, objects stringify. */
export function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.map((item) => formatDetailValue(item)).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * A machine payload as labeled key/value rows instead of a JSON blob.
 *
 * The `JSON.stringify` dumps this replaces put internal hashes, locators and
 * scores on screen as one unparseable line — implementation detail rather
 * than communicated facts. Both tracks are clamped (`grid-cols-1` is
 * minmax(0,1fr); values wrap-anywhere): an implicit `auto` track takes its
 * minimum from the item's min-content, so a nowrap value here would push the
 * track — and the whole card — to the value's full unwrapped width.
 */
export function KeyValueList({
  data,
  className,
  size = "xs",
}: {
  data: Record<string, unknown>;
  className?: string;
  size?: "xs" | "sm";
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <dl
      className={cn(
        "grid grid-cols-1 gap-x-4 gap-y-0.5 sm:grid-cols-2",
        size === "sm" && "text-[11px]",
        className,
      )}
    >
      {entries.map(([key, value]) => (
        <div key={key} className="flex min-w-0 items-baseline justify-between gap-2 text-[10px]">
          <dt className="shrink-0 text-dim">{humanizeKey(key)}</dt>
          <dd className="min-w-0 wrap-anywhere text-right font-mono text-muted">
            {formatDetailValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * `KeyValueList` behind a native `<details>` disclosure — keyboard accessible
 * with no JS, and closed by default so a repeated payload does not dominate
 * a list of events or observations. Renders nothing for an empty payload.
 */
export function PayloadDetail({
  data,
  label,
  className,
  children,
}: {
  data: Record<string, unknown> | null | undefined;
  /** Summary text, or custom summary content via `children`. */
  label?: string;
  className?: string;
  children?: ReactNode;
}) {
  if (!data || Object.keys(data).length === 0) return null;
  return (
    <details className={cn("group", className)}>
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-wider text-dim transition-colors hover:bg-surface-3 hover:text-muted focus-visible:outline-2 focus-visible:outline-accent">
        <ChevronDown className="size-3 transition-transform group-open:rotate-180" aria-hidden />
        {children ?? label ?? "Details"}
      </summary>
      <KeyValueList data={data} className="mt-1" />
    </details>
  );
}
