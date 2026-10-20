import { useMemo } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { Flag } from "lucide-react";
import { useFindingStats, useFindings } from "@/hooks/queries";
import { PageContainer } from "@/components/layout/page";
import { InvestigationHeader } from "@/components/layout/investigation-header";
import { Card, CardContent } from "@/components/ui/card";
import { FindingStatusBadge, FindingTypeBadge, SeverityBadge } from "@/components/status";
import { FINDING_TYPE_META, SEVERITY_META } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TabBar } from "@/components/ui/tab-bar";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative } from "@/lib/utils";
import type { FindingStatus, FindingType, Severity } from "@/types/domain";

/** Rows per request; the findings endpoint accepts up to 200. The backend
 *  orders by score descending, so each page is a ranked slice of the queue. */
const PAGE_SIZE = 50;

/** Review states, grouped as tabs — the queue's primary workflow axis. */
const STATUS_TABS: Array<FindingStatus | "all"> = ["all", "NEW", "REVIEWED", "CONFIRMED", "DISMISSED"];

function statusLabel(status: FindingStatus | "all"): string {
  return status === "all" ? "All" : status.charAt(0) + status.slice(1).toLowerCase();
}

export default function FindingsPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") as FindingStatus | null) ?? "all";
  const severity = (params.get("severity") as Severity | null) ?? "all";
  const type = (params.get("type") as FindingType | null) ?? "all";
  const rawOffset = Number(params.get("offset") ?? "0");
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const findings = useFindings(caseId, {
    status: status === "all" ? undefined : status,
    severity: severity === "all" ? undefined : severity,
    finding_type: type === "all" ? undefined : type,
    limit: PAGE_SIZE,
    offset: offset > 0 ? offset : undefined,
  });
  const stats = useFindingStats(caseId);

  const updateParam = (key: string, value: string) => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value && value !== "all") next.set(key, value);
      else next.delete(key);
      // A different filter invalidates whatever page we were on.
      next.delete("offset");
      return next;
    });
  };

  const setPageOffset = (value: number) => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value > 0) next.set("offset", String(value));
      else next.delete("offset");
      return next;
    });
  };

  const byStatus = stats.data?.by_status;
  const statusTabs = useMemo(() => {
    const total = byStatus ? Object.values(byStatus).reduce((sum, n) => sum + n, 0) : undefined;
    return STATUS_TABS.map((s) => ({
      id: s,
      label: statusLabel(s),
      // Counts come from the stats endpoint; omit them (rather than showing
      // zeros) until it resolves.
      count: byStatus ? (s === "all" ? total : (byStatus[s] ?? 0)) : undefined,
    }));
  }, [byStatus]);

  const st = stats.data;
  const totalConfirmed = st?.by_status.CONFIRMED ?? 0;
  const totalDismissed = st?.by_status.DISMISSED ?? 0;

  const items = findings.data?.items ?? [];
  const total = findings.data?.total ?? 0;
  const from = items.length > 0 ? offset + 1 : 0;
  const to = offset + items.length;
  const hasPrev = offset > 0;
  const hasNext = to < total;

  return (
    <PageContainer>
      <InvestigationHeader
        eyebrow="Review queue"
        title="Findings"
        description="Patterns, anomalies and network insights. Each one carries the approach and the source records behind it."
        actions={
          <div className="flex items-center gap-1.5 text-xs text-dim">
            {totalConfirmed > 0 ? <span className="rounded-md bg-success/12 px-2 py-1 text-success">{totalConfirmed} confirmed</span> : null}
            {totalDismissed > 0 ? <span className="rounded-md bg-surface-3 px-2 py-1">{totalDismissed} dismissed</span> : null}
          </div>
        }
      />

      <TabBar
        items={statusTabs}
        active={status}
        onChange={(id) => updateParam("status", id)}
        ariaLabel="Findings by review status"
        idPrefix="findings"
        className="mt-4"
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Select value={severity} onValueChange={(value) => updateParam("severity", value)}>
          <SelectTrigger className="w-[150px]"><SelectValue placeholder="All severities" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All severities</SelectItem>
            {(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const).map((s) => (
              <SelectItem key={s} value={s}>{SEVERITY_META[s].label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={type} onValueChange={(value) => updateParam("type", value)}>
          <SelectTrigger className="w-[190px]"><SelectValue placeholder="All types" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {(["pattern", "anomaly", "hypothesis", "network_insight", "relationship_insight"] as FindingType[]).map((t) => (
              <SelectItem key={t} value={t}>{FINDING_TYPE_META[t].label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {total > 0 && items.length > 0 ? (
          <p className="ml-auto text-[11px] text-dim" aria-live="polite">
            {findings.isFetching ? "Loading… " : ""}
            Showing {from}–{to} of {total}
          </p>
        ) : null}
      </div>

      <div className="mt-4">
        {findings.isLoading ? (
          <Card><CardContent className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
          </CardContent></Card>
        ) : findings.isError ? (
          <Card><ErrorState error={findings.error} onRetry={() => void findings.refetch()} /></Card>
        ) : items.length === 0 && offset > 0 ? (
          // The queue shrank (or the filter changed underneath us) after this
          // page was requested — say so and offer the way back rather than
          // claiming nothing matches.
          <Card>
            <EmptyState
              title="No findings on this page"
              description="This page sits past the end of the queue — the list has changed since it was opened."
              action={{ label: "Back to newest", onClick: () => setPageOffset(0) }}
            />
          </Card>
        ) : items.length === 0 ? (
          <Card><EmptyState title="No findings match" description="Re-run analytics or widen the filters to see the review queue." /></Card>
        ) : (
          <>
            <Card>
              <Table>
                <THead>
                  <TR>
                    <TH className="w-32">Status</TH>
                    <TH>Finding</TH>
                    <TH className="hidden sm:table-cell">Type</TH>
                    <TH className="w-28">Severity</TH>
                    <TH className="hidden lg:table-cell">Detected</TH>
                    {/* Score orders this queue (the backend sorts by it);
                        confidence is a different 0–100 number — how much of
                        the supporting evidence verified — so both are shown,
                        labelled, instead of score alone with confidence
                        whispered in a tooltip. */}
                    <TH
                      className="w-24 text-right"
                      title="Score: the rule's strength (0–100); this queue is ordered by it. Confidence: how much of the supporting evidence verified."
                    >
                      Score
                    </TH>
                  </TR>
                </THead>
                <TBody>
                  {items.map((f) => (
                    <TR key={f.id} className="cursor-pointer" onClick={() => navigate(`/app/cases/${caseId}/findings/${f.id}`)}>
                      <TD>
                        <FindingStatusBadge value={f.status} />
                      </TD>
                      <TD className="max-w-[340px]">
                        <p className="truncate font-medium text-foreground">{f.title}</p>
                        <p className="line-clamp-1 text-[11px] text-dim">{f.summary}</p>
                      </TD>
                      <TD className="hidden sm:table-cell"><FindingTypeBadge value={f.finding_type} /></TD>
                      <TD><SeverityBadge value={f.severity} /></TD>
                      <TD className="hidden text-xs text-dim lg:table-cell" title={f.created_at}>{formatRelative(f.created_at)}</TD>
                      <TD className="text-right">
                        <span className="tabular text-xs text-foreground/80">{Math.round(f.score * 100)}</span>
                        {f.confidence != null ? (
                          <span className="block tabular text-[10px] text-dim">
                            conf {Math.round(f.confidence * 100)}%
                          </span>
                        ) : null}
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
                  disabled={!hasPrev || findings.isFetching}
                  onClick={() => setPageOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Newer
                </Button>
                <span className="text-[11px] tabular text-dim">
                  Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
                </span>
                <Button
                  variant="outline"
                  disabled={!hasNext || findings.isFetching}
                  onClick={() => setPageOffset(offset + PAGE_SIZE)}
                >
                  Older
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>

      <div className="mt-4 flex items-center gap-2 text-[11px] text-dim">
        <Flag className="size-3.5 text-accent" />
        {st ? (
          Object.entries(st.by_severity).map(([sev, count]) => (
            <span key={sev} className="rounded-md bg-surface-3 px-2 py-0.5">
              <span className="text-foreground/70">{sev}</span> <span className="tabular text-muted">{count}</span>
            </span>
          ))
        ) : null}
      </div>
    </PageContainer>
  );
}
