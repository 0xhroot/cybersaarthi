import * as SwitchPrimitive from "@radix-ui/react-switch";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Switch = forwardRef<
  React.ComponentRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      "inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border bg-surface-3 transition-colors",
      "data-[state=checked]:border-accent/50 data-[state=checked]:bg-accent/25",
      "focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb
      className={cn(
        "pointer-events-none block size-4 translate-x-0.5 rounded-full bg-muted shadow transition-transform",
        "data-[state=checked]:translate-x-[18px] data-[state=checked]:bg-accent-strong",
      )}
    />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";