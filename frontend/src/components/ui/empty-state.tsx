import { Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-14 text-center",
        className,
      )}
    >
      <div className="flex size-12 items-center justify-center rounded-full border border-border bg-surface-2 text-dim">
        {icon ?? <Inbox className="size-5" />}
      </div>
      <p className="mt-1 text-sm font-medium text-foreground">{title}</p>
      {description ? <p className="max-w-sm text-xs leading-relaxed text-dim">{description}</p> : null}
      {action ? (
        <Button size="sm" variant="secondary" onClick={action.onClick} className="mt-3">
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}