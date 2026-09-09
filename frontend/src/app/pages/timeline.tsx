import { useParams } from "react-router-dom";
import { useTimeline } from "@/hooks/queries";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative, formatTime } from "@/lib/utils";
import type { ApiTimelineEvent } from "@/api/contract";

function actorFor(event: ApiTimelineEvent): string {
  if (event.metadata_ && typeof event.metadata_ === "object") {
    const actor = (event.metadata_ as Record<string, unknown>).actor_username;
    if (typeof actor === "string") return actor;
  }
  if (event.actor_id) return event.actor_id.slice(0, 8);
  return "system";
}

export default function TimelinePage() {
  const { caseId = "" } = useParams();
  const timeline = useTimeline(caseId);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Case audit trail"
        title="Timeline"
        description="Everything that changed this case, in order — evidence uploaded, findings reviewed, analytics run."
      />

      <div className="mt-5">
        {timeline.isLoading ? (
          <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : timeline.isError ? (
          <Card><ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} /></Card>
        ) : (timeline.data ?? []).length === 0 ? (
          <Card><CardContent className="py-10 text-center text-xs text-dim">No activity recorded on this case yet.</CardContent></Card>
        ) : (
          <div className="relative">
            <span aria-hidden className="absolute bottom-2 left-[7px] top-2 w-px bg-border-strong" />
            <div className="space-y-1">
              {(timeline.data ?? []).map((event) => (
                <div key={event.id} className="relative flex gap-3 pl-6">
                  <span aria-hidden className="absolute left-0 top-[13px] size-[15px] rounded-full border-[3px] border-background bg-accent shadow-[0_0_0_1px_var(--color-accent)]" />
                  <div className="min-w-0 flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-foreground">{event.action}</span>
                      <Badge>{actorFor(event)}</Badge>
                      <span className="ml-auto text-[10px] tabular text-dim" title={event.created_at}>
                        {formatRelative(event.created_at)} · {formatTime(event.created_at)}
                      </span>
                    </div>
                    {event.metadata_ ? (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-dim">
                        {JSON.stringify(event.metadata_)}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </PageContainer>
  );
}