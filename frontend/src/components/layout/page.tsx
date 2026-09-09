import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Kbd } from "@/components/ui/table";

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  className,
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        {eyebrow ? (
          <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.18em] text-accent/80">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description ? <p className="mt-1 text-xs leading-relaxed text-dim">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function PageContainer({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mx-auto w-full max-w-7xl px-4 py-6 sm:px-6", className)} {...props} />;
}

export function PageBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-6 space-y-5", className)} {...props} />;
}

export function CommandHint() {
  return (
    <span className="flex items-center gap-1 text-[11px] text-dim">
      Press <Kbd>Ctrl</Kbd> <Kbd>K</Kbd>
    </span>
  );
}