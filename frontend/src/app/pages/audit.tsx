import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import { useAdminUserLookup, useAudit } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { useAuthStore } from "@/stores/auth";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { MonoId, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative, formatTime, shortId } from "@/lib/utils";
import type { AuditEvent } from "@/types/domain";

/**
 * Every `resource_type` the backend can record (derived from the
 * `resource_type=` literals in backend/app). The old hard-coded list here
 * guessed at names — "evidence", "entity", "analytics", "system" matched
 * nothing — so four of its seven options were dead ends and the types the log
 * actually contains (evidence_file, analysis_job, ai_conversation, …) were
 * unreachable.
 */
const KNOWN_RESOURCE_TYPES = [
  "ai_conversation",
  "ai_tool",
  "analysis_job",
  "analytics_run",
  "case",
  "collection",
  "derived_artifact",
  "entity",
  "entity_match",
  "evidence_file",
  "field_device",
  "finding",
  "hypothesis",
  "ingestion_job",
  "iot_device",
  "iot_event",
  "package",
  "report",
  "timeline_event",
  "user",
  "victim",
] as const;

/** `evidence_file` → `Evidence file` for the picker; raw codes stay in the cells. */
function humanizeResourceType(value: string): string {
  const words = value.split("_").filter(Boolean);
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

/** Rows per request. The audit endpoint caps limit at 200; 50 keeps a page
 *  scannable — the old single 200-row request rendered a 9,000px table that
 *  buried everything under it. */
const PAGE_SIZE = 50;

/** Acronyms kept intact when humanizing action codes. */
const ACTION_ACRONYMS: Record<string, string> = { ai: "AI", iot: "IoT", id: "ID", url: "URL", sha: "SHA" };

/**
 * `auth.login_succeeded` → "Login succeeded", `ai_conversation_deleted` →
 * "AI conversation deleted". The raw code stays on screen as the mono line
 * underneath, so nothing an auditor greps for is hidden behind a label.
 */
function humanizeAction(action: string): string {
  const verb = action.includes(".") ? action.slice(action.indexOf(".") + 1) : action;
  const words = verb.replace(/[._]/g, " ").split(/\s+/).filter(Boolean);
  if (words.length === 0) return action;
  const [first, ...rest] = words;
  const head = ACTION_ACRONYMS[first] ?? first.charAt(0).toUpperCase() + first.slice(1);
  return [head, ...rest].join(" ");
}

/**
 * Who acted. Self is labelled from the session; everyone else resolves
 * through per-id lookups *when the viewer may read them* (users.manage) and
 * falls back to a short id — the audit endpoint exposes actor ids only, and
 * fetching usernames unconditionally would 403 for investigators, who hold
 * audit.read but not users.manage.
 */
function ActorCell({
  event,
  viewerId,
  viewerName,
  names,
}: {
  event: AuditEvent;
  viewerId?: string;
  viewerName?: string;
  names: ReadonlyMap<string, string>;
}) {
  if (!event.actor_id) return <span className="text-dim">system</span>;
  if (viewerId && event.actor_id === viewerId) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <ShieldCheck className="size-3 text-accent" aria-hidden />
        You <span className="text-dim">· {viewerName}</span>
      </span>
    );
  }
  const name = names.get(event.actor_id);
  return (
    <span className="inline-flex items-center gap-1.5">
      <ShieldCheck className="size-3 text-dim" aria-hidden />
      {name ?? <MonoId value={shortId(event.actor_id)} title={event.actor_id} />}
    </span>
  );
}

export default function AuditPage() {
  const [resourceType, setResourceType] = useState("all");
  const [offset, setOffset] = useState(0);

  const canSeeDirectory = useCan("users.manage");
  const viewer = useAuthStore((s) => s.user);

  const audit = useAudit({
    limit: PAGE_SIZE,
    offset,
    resource_type: resourceType === "all" ? undefined : resourceType,
  });

  // `?? []` would mint a fresh array each render while loading, churning both
  // memos below that depend on it.
  const items = useMemo(() => audit.data?.items ?? [], [audit.data]);
  const total = audit.data?.total ?? 0;

  // Distinct actors on this page, minus the viewer (labelled "You" from the
  // session) and system rows — exactly the ids worth resolving.
  const actorIds = useMemo(
    () => [
      ...new Set(
        items
          .map((event) => event.actor_id)
          .filter((id): id is string => Boolean(id) && id !== viewer?.id),
      ),
    ],
    [items, viewer?.id],
  );
  const names = useAdminUserLookup(actorIds, canSeeDirectory);

  // Known types plus anything this window actually contains, so a value the
  // backend grows can always be filtered from the rows in front of you.
  const resourceOptions = useMemo(
    () => [...new Set([...KNOWN_RESOURCE_TYPES, ...items.map((e) => e.resource_type)])].sort(),
    [items],
  );

  const from = items.length > 0 ? offset + 1 : 0;
  const to = offset + items.length;
  const hasPrev = offset > 0;
  const hasNext = to < total;

  const changeFilter = (value: string) => {
    setResourceType(value);
    setOffset(0);
  };

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="Immutable record of actions across cases. Used to review who did what, when."
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <Select value={resourceType} onValueChange={changeFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All resources" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All resources</SelectItem>
            {resourceOptions.map((t) => (
              <SelectItem key={t} value={t}>
                {humanizeResourceType(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {total > 0 ? (
          <p className="text-[11px] text-dim" aria-live="polite">
            {audit.isFetching ? "Loading… " : ""}
            Showing {from}–{to} of {total.toLocaleString("en-GB")} events
          </p>
        ) : null}
      </div>

      <div className="mt-4">
        {audit.isLoading ? (
          <Card>
            <CardContent className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-11" />
              ))}
            </CardContent>
          </Card>
        ) : audit.isError ? (
          <Card>
            <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <EmptyState
              title="No audit events"
              description={
                resourceType === "all"
                  ? "Actions recorded here as investigators work."
                  : `No recorded actions against ${humanizeResourceType(resourceType).toLowerCase()} resources.`
              }
            />
          </Card>
        ) : (
          <>
            <Card>
              <Table>
                <THead>
                  <TR>
                    <TH>When</TH>
                    <TH className="hidden md:table-cell">Actor</TH>
                    <TH>Action</TH>
                    <TH className="hidden sm:table-cell">Resource</TH>
                    <TH className="hidden lg:table-cell">Case</TH>
                    <TH className="hidden text-right xl:table-cell">Log id</TH>
                  </TR>
                </THead>
                <TBody>
                  {items.map((event) => (
                    <TR key={event.id}>
                      <TD
                        className="whitespace-nowrap text-xs text-muted"
                        title={event.created_at}
                      >
                        {formatRelative(event.created_at)}{" "}
                        <span className="text-dim">· {formatTime(event.created_at)}</span>
                      </TD>
                      <TD className="hidden whitespace-nowrap text-[11px] text-muted md:table-cell">
                        <ActorCell
                          event={event}
                          viewerId={viewer?.id}
                          viewerName={viewer?.username}
                          names={names}
                        />
                      </TD>
                      <TD className="max-w-[200px]">
                        <span className="block truncate text-xs font-medium text-foreground">
                          {humanizeAction(event.action)}
                        </span>
                        <span className="block truncate font-mono text-[10px] text-dim" title={event.action}>
                          {event.action}
                        </span>
                      </TD>
                      <TD className="hidden sm:table-cell">
                        <Badge>{event.resource_type}</Badge>
                        {event.resource_id ? (
                          <span className="mt-0.5 block max-w-[140px]">
                            <MonoId value={shortId(event.resource_id)} title={event.resource_id} className="text-[10px]" />
                          </span>
                        ) : null}
                      </TD>
                      <TD className="hidden font-mono text-[11px] text-dim lg:table-cell">
                        {event.case_id ? shortId(event.case_id) : "—"}
                      </TD>
                      <TD className="hidden text-right xl:table-cell">
                        <MonoId value={shortId(event.id)} title={event.id} className="text-[10px]" />
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Card>

            {hasPrev || hasNext ? (
              <div className="mt-3 flex items-center justify-between gap-3">
                <Button
                  variant="outline"
                  disabled={!hasPrev || audit.isFetching}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  <ChevronLeft className="size-4" aria-hidden />
                  Newer
                </Button>
                <span className="text-[11px] tabular text-dim">
                  Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
                </span>
                <Button
                  variant="outline"
                  disabled={!hasNext || audit.isFetching}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Older
                  <ChevronRight className="size-4" aria-hidden />
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </PageContainer>
  );
}
