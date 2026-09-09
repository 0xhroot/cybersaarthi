import * as ToastPrimitive from "@radix-ui/react-toast";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { create } from "zustand";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "success" | "error" | "info";

export interface ToastData {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
  duration: number;
}

interface ToastState {
  toasts: ToastData[];
  push: (t: Omit<ToastData, "id">) => number;
  dismiss: (id: number) => void;
}

let toastSeq = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = toastSeq++;
    set((s) => ({ toasts: [...s.toasts.slice(-3), { ...t, id }] }));
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function toast(input: {
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}) {
  useToastStore
    .getState()
    .push({ ...input, variant: input.variant ?? "default", duration: input.duration ?? 5000 });
}

const ICONS: Record<ToastVariant, ReactNode> = {
  default: <Info className="size-4 text-info" />,
  success: <CheckCircle2 className="size-4 text-success" />,
  error: <AlertCircle className="size-4 text-critical" />,
  info: <Info className="size-4 text-info" />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <ToastPrimitive.Provider swipeDirection="right" duration={4000}>
      {children}
      {toasts.map((t) => (
        <ToastPrimitive.Root
          key={t.id}
          duration={t.duration}
          onOpenChange={(open) => {
            if (!open) dismiss(t.id);
          }}
          className={cn(
            "pointer-events-auto flex items-start gap-3 rounded-lg border border-border-strong bg-surface-2 p-3 shadow-xl shadow-black/40",
            "data-[state=open]:animate-toast-in data-[state=closed]:animate-toast-out",
          )}
        >
          <span className="mt-0.5">{ICONS[t.variant]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">{t.title}</p>
            {t.description ? <p className="mt-0.5 text-xs leading-relaxed text-muted">{t.description}</p> : null}
          </div>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => dismiss(t.id)}
            className="rounded p-0.5 text-dim transition-colors hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-toast flex w-[min(92vw,380px)] flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}

export function toastFromError(err: unknown, fallback: string) {
  const message = (err as { message?: string })?.message;
  toast({
    title: "Something went wrong",
    description: message && message !== fallback ? message : fallback,
    variant: "error",
  });
}