import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "accent" | "success" | "info" | "critical" | "high" | "medium" | "low";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-3 text-muted border-border",
  accent: "bg-accent-soft text-accent-strong border-accent/25",
  success: "bg-success/12 text-success border-success/25",
  info: "bg-info/12 text-info border-info/25",
  critical: "bg-critical/12 text-critical border-critical/25",
  high: "bg-high/12 text-high border-high/25",
  medium: "bg-medium/12 text-medium border-medium/25",
  low: "bg-low/15 text-low border-low/25",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, tone = "neutral", ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4",
        TONES[tone],
        className,
      )}
      {...props}
    />
  ),
);
Badge.displayName = "Badge";

export function Dot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-1.5 rounded-full bg-current", className)}
    />
  );
}