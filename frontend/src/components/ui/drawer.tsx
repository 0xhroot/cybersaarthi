import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

/** Right-hand investigation drawer. Rendered in a portal with Radix dialog semantics. */
export const Drawer = DialogPrimitive.Root;
export const DrawerTrigger = DialogPrimitive.Trigger;

export const DrawerPortal = DialogPrimitive.Portal;

export const DrawerOverlay = forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-drawer bg-black/55 backdrop-blur-[1px]",
      "data-[state=open]:animate-overlay-in data-[state=closed]:animate-overlay-out",
      className,
    )}
    {...props}
  />
));
DrawerOverlay.displayName = "DrawerOverlay";

export function DrawerContent({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>) {
  return (
    <DrawerPortal>
      <DrawerOverlay />
      <DialogPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-drawer flex w-[min(92vw,420px)] flex-col",
          "border-l border-border-strong bg-surface shadow-2xl shadow-black/50",
          "data-[state=open]:animate-drawer-in data-[state=closed]:animate-drawer-out",
          className,
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DrawerPortal>
  );
}

export function DrawerHeader({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>) {
  return (
    <div className={cn("flex items-start justify-between gap-3 border-b border-border px-4 py-3", className)} {...props} />
  );
}

export const DrawerTitle = DialogPrimitive.Title;
export const DrawerClose = DialogPrimitive.Close;

export function DrawerCloseIcon() {
  return (
    <DialogPrimitive.Close
      aria-label="Close panel"
      className="rounded-md p-1 text-dim transition-colors hover:bg-surface-3 hover:text-foreground focus-visible:outline-none"
    >
      <X className="size-4" />
    </DialogPrimitive.Close>
  );
}