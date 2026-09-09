import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { Flag } from "lucide-react";
import { useFindingStats, useFindings } from "@/hooks/queries";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { FindingStatusBadge, FindingTypeBadge, SeverityBadge } from "@/components/status";
import { FINDING_TYPE_META, SEVERITY_META } from "@/components/status";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative } from "@/lib/utils";
import type { FindingStatus, FindingType, Severity } from "@/types/domain";

const STATUS_FILTERS: Array<FindingStatus | "all"> = ["all", "NEW", "REVIEWED", "CONFIRMED", "DISMISSED"];

export default function FindingsPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") as FindingStatus | null) ?? "all";
  const severity = (params.get("severity") as Severity | null) ?? "all";
  const type = (params.get("type") as FindingType | null) ?? "all";

  const findings = useFindings(caseId, {
    status: status === "all" ? undefined : status,
    severity: severity === "all" ? undefined : severity,
    finding_type: type === "all" ? undefined : type,
    limit: 100,
  });
  const stats = useFindingStats(caseId);

  const updateParam = (key: string, value: string) => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value && value !== "all") next.set(key, value);
      else next.delete(key);
      return next;
    });
  };

  const st = stats.data;
  const totalConfirmed = st?.by_status.CONFIRMED ?? 0;
  const totalDismissed = st?.by_status.DISMISSED ?? 0;

  return (
    <PageContainer>
      <PageHeader
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

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Select value={status} onValueChange={(value) => updateParam("status", value)}>
          <SelectTrigger className="w-[160px]"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((s) => (
              <SelectItem key={s} value={s}>{s === "all" ? "All statuses" : s.toLowerCase()}</SelectItem>
            ))}
          </SelectContent>
        </Select>
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
      </div>

      <div className="mt-4">
        {findings.isLoading ? (
          <Card><CardContent className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
          </CardContent></Card>
        ) : findings.isError ? (
          <Card><ErrorState error={findings.error} onRetry={() => void findings.refetch()} /></Card>
        ) : (findings.data?.items ?? []).length === 0 ? (
          <Card><EmptyState title="No findings match" description="Re-run analytics or widen the filters to see the review queue." /></Card>
        ) : (
          <Card>
            <Table>
              <THead>
                <TR>
                  <TH className="w-32">Status</TH>
                  <TH>Finding</TH>
                  <TH className="hidden sm:table-cell">Type</TH>
                  <TH className="w-28">Severity</TH>
                  <TH className="hidden lg:table-cell">Detected</TH>
                  <TH className="w-20 text-right">Score</TH>
                </TR>
              </THead>
              <TBody>
                {(findings.data?.items ?? []).map((f) => (
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
                    <TD className="tabular text-right text-xs text-foreground/80" title={f.confidence != null ? `confidence ${Math.round(f.confidence * 100)}%` : undefined}>
                      {Math.round(f.score * 100)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>
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