import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTimeline } from "@/hooks/queries";
import { ReconstructionPanel } from "@/components/evidence/reconstruction-panel";
import { PageContainer } from "@/components/layout/page";
import { InvestigationHeader } from "@/components/layout/investigation-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PayloadDetail } from "@/components/ui/key-value";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { formatDate, formatRelative, formatTime, pluralize } from "@/lib/utils";
import type { TimelineEvent } from "@/types/domain";

const KIND_LABELS: Record<string, string> = {
  case_event: "Case",
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

/** Events rendered before the investigator asks for more. */
const PAGE_SIZE = 30;

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}

function TimelineEventRow({ event }: { event: TimelineEvent }) {
  return (
    <li className="relative flex gap-3 pl-6">
      <span
        aria-hidden
        className="absolute left-0 top-[13px] size-[15px] rounded-full border-[3px] border-background bg-accent shadow-[0_0_0_1px_var(--color-accent)]"
      />
      <div className="min-w-0 flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info">{kindLabel(event.kind)}</Badge>
          {(event.payload as { origin?: string } | null)?.origin === "timeline_reconstruction" ? (
            <Badge tone="accent">reconstructed</Badge>
          ) : null}
          <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{event.title}</span>
          <span className="ml-auto whitespace-nowrap text-[10px] tabular text-dim" title={event.occurred_at}>
            {formatRelative(event.occurred_at)} · {formatTime(event.occurred_at)}
          </span>
        </div>
        {event.description ? (
          <p className="mt-1 text-[11px] leading-relaxed text-dim">{event.description}</p>
        ) : null}
        <PayloadDetail data={event.payload} label="Event details" className="mt-1.5" />
      </div>
    </li>
  );
}

export default function TimelinePage() {
  const { caseId = "" } = useParams();
  // Events page by growing the server-side limit (both API adapters accept
  // `limit`; the feed is already newest-first, so a bigger window simply
  // reveals older rows) — the page never renders an unbounded list.
  const [limit, setLimit] = useState(PAGE_SIZE);
  const timeline = useTimeline(caseId, { limit });

  const items = timeline.data?.items ?? [];
  const total = timeline.data?.total ?? items.length;
  const hidden = Math.max(0, total - items.length);

  // Events arrive newest-first (occurred_at desc), so day groups fall out in
  // order without sorting.
  const groups: Array<{ day: string; events: TimelineEvent[] }> = [];
  for (const event of items) {
    const day = formatDate(event.occurred_at);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.events.push(event);
    else groups.push({ day, events: [event] });
  }

  return (
    <PageContainer>
      <InvestigationHeader
        eyebrow="Case timeline"
        title="Timeline"
        description="Every transition recorded on this case in order — evidence uploaded or restored, collections sealed, devices approved, hypotheses tracked, reports generated."
      />

      <div className="mt-5">
        <Card>
          <CardContent>
            <ReconstructionPanel caseId={caseId} />
          </CardContent>
        </Card>
      </div>

      <div className="mt-5">
        {timeline.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : timeline.isError ? (
          <Card>
            <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} />
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-xs text-dim">
              No activity recorded on this case yet.
            </CardContent>
          </Card>
        ) : (
          <>
            <p className="mb-3 text-[11px] text-dim">
              {items.length >= total
                ? `${total} ${pluralize(total, "event")} recorded, newest first.`
                : `Showing the newest ${items.length} of ${total} events, newest first.`}
            </p>
            <div className="relative space-y-5">
              <span aria-hidden className="absolute bottom-2 left-[7px] top-2 w-px bg-border-strong" />
              {groups.map((group) => (
                <section key={group.day} aria-label={`Events on ${group.day}`}>
                  <div className="relative flex items-center gap-2 pb-1 pl-6">
                    <span
                      aria-hidden
                      className="absolute left-[7px] h-full w-px bg-background"
                    />
                    <h2 className="relative text-[11px] font-semibold uppercase tracking-wider text-dim">{group.day}</h2>
                    <span className="text-[10px] text-dim">
                      {group.events.length} {pluralize(group.events.length, "event")}
                    </span>
                  </div>
                  <ol className="space-y-1">
                    {group.events.map((event) => (
                      <TimelineEventRow key={event.id} event={event} />
                    ))}
                  </ol>
                </section>
              ))}
            </div>
            {hidden > 0 ? (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="outline"
                  disabled={timeline.isFetching}
                  onClick={() => setLimit((count) => count + 100)}
                >
                  {timeline.isFetching
                    ? "Loading older events…"
                    : `Show ${hidden} older ${pluralize(hidden, "event")}`}
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </PageContainer>
  );
}
