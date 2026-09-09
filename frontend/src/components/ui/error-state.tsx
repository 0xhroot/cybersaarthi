import { ShieldAlert } from "lucide-react";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const status = apiError?.status;

  let title = "Unable to load this view";
  let description =
    apiError?.message ?? "Something unexpected happened. Please try again.";

  if (status === 401) {
    title = "Your session has expired";
    description = "Sign in again to continue reviewing this investigation.";
  } else if (status === 403) {
    title = "No access to this case";
    description = "Your role does not permit viewing this investigation. Contact the case owner.";
  } else if (status === 404) {
    title = "Not found";
    description = "The case or item you are looking for does not exist or has been removed.";
  } else if (status === 429) {
    title = "Rate limit reached";
    description = "Requests are being throttled. Wait a moment and try again.";
  }

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-14 text-center",
        className,
      )}
    >
      <div className="flex size-12 items-center justify-center rounded-full border border-critical/30 bg-critical/10 text-critical">
        <ShieldAlert className="size-5" aria-hidden />
      </div>
      <p className="mt-1 text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-xs leading-relaxed text-dim">{description}</p>
      {apiError?.requestId ? (
        <p className="max-w-sm break-all font-mono text-[10px] text-dim">
          request {apiError.requestId}
        </p>
      ) : null}
      {onRetry ? (
        <Button size="sm" variant="secondary" onClick={onRetry} className="mt-3">
          Try again
        </Button>
      ) : null}
    </div>
  );
}