import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger" | "link";
type Size = "sm" | "default" | "lg" | "icon" | "icon-sm";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-on-accent hover:bg-accent-strong shadow-[0_0_0_1px_rgba(214,161,78,0.35)_inset]",
  secondary:
    "bg-surface-3 text-foreground border border-border hover:border-border-strong hover:bg-surface-3/80",
  ghost: "text-muted hover:text-foreground hover:bg-surface-2",
  outline:
    "border border-border-strong text-foreground hover:border-accent hover:text-accent bg-transparent",
  danger:
    "border border-critical/30 bg-critical/10 text-critical hover:bg-critical/20 hover:text-critical",
  link: "text-accent hover:text-accent-strong underline-offset-4 hover:underline px-0 py-0 h-auto",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  default: "h-9 px-4 text-sm gap-2",
  lg: "h-10 px-6 text-sm gap-2",
  icon: "h-9 w-9",
  "icon-sm": "h-7 w-7",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "default", loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors",
        "focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Spinner className="size-4" /> : null}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent",
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  );
}