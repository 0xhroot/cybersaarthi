import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function InvestigationHeader({
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
    <header className={cn("investigation-header", className)}>
      <div className="investigation-header__copy">
        <div className="investigation-header__eyebrow">
          <span className="investigation-header__marker" aria-hidden="true" />
          <span>{eyebrow ?? "Case workspace"}</span>
        </div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="investigation-header__actions">{actions}</div> : null}
    </header>
  );
}
