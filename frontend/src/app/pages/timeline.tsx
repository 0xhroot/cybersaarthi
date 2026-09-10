import { useParams } from "react-router-dom";
import { useTimeline } from "@/hooks/queries";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative, formatTime } from "@/lib/utils";

const KIND_LABELS: Record<string, string> = {
  case_created: "Case opened",
  case_status_changed: "Case status",
  case_archived: "Case archived",
  evidence_uploaded: "Evidence uploaded",
  evidence_ingested: "Evidence ingested",
  evidence_restored: "Evidence restored",
  collection_created: "Collection",
  collection_sealed: "Collection sealed",
  device_registered: "Device",
  device_approved: "Device approved",
  device_revoked: "Device revoked",
  hypothesis_created: "Hypothesis",
  hypothesis_status_changed: "Hypothesis status",
  finding_created: "Finding",
  finding_status_changed: "Finding status",
  entity_merged: "Entity merged",
  match_accepted: "Resolution",
  match_rejected: "Resolution",
  analytics_run: "Analytics",
  report_generated: "Report",
};

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}

export default function TimelinePage() {
  const { caseId = "" } = useParams();
  const timeline = useTimeline(caseId);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Case timeline"
        title="Timeline"
        description="Every transition recorded on this case in order — evidence uploaded or restored, collections sealed, devices approved, hypotheses tracked, reports generated."
      />

      <div className="mt-5">
        {timeline.isLoading ? (
          <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : timeline.isError ? (
          <Card><ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} /></Card>
        ) : (timeline.data?.items ?? []).length === 0 ? (
          <Card><CardContent className="py-10 text-center text-xs text-dim">No activity recorded on this case yet.</CardContent></Card>
        ) : (
          <div className="relative">
            <span aria-hidden className="absolute bottom-2 left-[7px] top-2 w-px bg-border-strong" />
            <div className="space-y-1">
              {(timeline.data?.items ?? []).map((event) => (
                <div key={event.id} className="relative flex gap-3 pl-6">
                  <span aria-hidden className="absolute left-0 top-[13px] size-[15px] rounded-full border-[3px] border-background bg-accent shadow-[0_0_0_1px_var(--color-accent)]" />
                  <div className="min-w-0 flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="info">{kindLabel(event.kind)}</Badge>
                      <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{event.title}</span>
                      <span className="ml-auto whitespace-nowrap text-[10px] tabular text-dim" title={event.occurred_at}>
                        {formatRelative(event.occurred_at)} · {formatTime(event.occurred_at)}
                      </span>
                    </div>
                    {event.description ? (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-dim">{event.description}</p>
                    ) : null}
                    {event.payload ? (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-dim">
                        {JSON.stringify(event.payload)}
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