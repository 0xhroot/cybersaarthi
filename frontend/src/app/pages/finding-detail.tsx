import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, Eye, X, ShieldAlert } from "lucide-react";
import { useEntities, useFinding, useUpdateFindingStatus } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FindingStatusBadge, FindingTypeBadge, SeverityBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { useDocumentTitle } from "@/hooks/ui";
import { formatDateTime } from "@/lib/utils";
import type { FindingStatus } from "@/types/domain";

export default function FindingDetailPage() {
  const { caseId = "", findingId = "" } = useParams();
  useDocumentTitle("Finding");
  const finding = useFinding(caseId, findingId);
  const entities = useEntities(caseId, { limit: 200 });
  const updateStatus = useUpdateFindingStatus(caseId);

  const [reason, setReason] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const canReview = useCan("findings.review");
  const canConfirm = useCan("findings.confirm");
  const canDismiss = useCan("findings.dismiss");

  const record = finding.data;
  const entityById = new Map((entities.data?.items ?? []).map((e) => [e.id, e]));

  const applyStatus = (status: FindingStatus) => {
    setConfirmOpen(false);
    void updateStatus.mutate(
      { findingId, status, reason: reason.trim() || undefined },
      {
        onSuccess: () => setReason(""),
      },
    );
  };

  if (finding.isError) {
    return (
      <PageContainer className="py-8">
        <Card><ErrorState error={finding.error} onRetry={() => void finding.refetch()} /></Card>
      </PageContainer>
    );
  }

  const signals = record?.explanation.signals ?? [];
  const paths = record?.explanation.paths ?? [];
  const evidence = record?.explanation.evidence ?? [];

  return (
    <PageContainer>
      <Link to={`/app/cases/${caseId}/findings`} className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Back to findings
      </Link>

      {finding.isLoading || !record ? (
        <div className="mt-4 space-y-3"><Skeleton className="h-8 w-1/2" /><Skeleton className="h-40" /></div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <h1 className="mr-1 text-xl font-semibold tracking-tight text-foreground">{record.title}</h1>
            <FindingStatusBadge value={record.status} />
            <FindingTypeBadge value={record.finding_type} />
            <SeverityBadge value={record.severity} />
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">{record.summary}</p>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-dim">
            <span>score <span className="tabular text-foreground/70">{Math.round(record.score * 100)}</span></span>
            <span>confidence <span className="tabular text-foreground/70">{record.confidence != null ? Math.round(record.confidence * 100) : "—"}</span></span>
            <span>detected {formatDateTime(record.created_at)}</span>
            {record.reviewed_at ? <span>reviewed {formatDateTime(record.reviewed_at)}</span> : null}
            {record.review_comment ? <span className="max-w-[300px] truncate" title={record.review_comment}>comment: {record.review_comment}</span> : null}
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <div className="space-y-5">
              <Card>
                <CardHeader><CardTitle>Approach</CardTitle></CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted">{record.explanation.approach}</p>
                </CardContent>
              </Card>

              {signals.length > 0 ? (
                <Card>
                  <CardHeader><CardTitle>Signals</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {signals.map((sig, i) => (
                      <div key={i} className="flex items-start gap-3 rounded-md border border-border bg-surface-2 px-3 py-2">
                        <span className="grid size-5 shrink-0 place-items-center rounded bg-surface-3 text-[10px] text-dim">{i + 1}</span>
                        <div>
                          <p className="text-sm text-foreground">{String(sig.name ?? sig.label ?? "signal")}</p>
                          <p className="text-[11px] leading-relaxed text-dim">{String(sig.description ?? sig.message ?? sig.value ?? "")}</p>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ) : null}

              {paths.length > 0 ? (
                <Card>
                  <CardHeader><CardTitle>Supporting paths</CardTitle></CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {paths.map((path, i) => {
                        const nodes = (path.entities as Array<{ id: string; display_value: string }> | undefined) ?? [];
                        const rels = (path.relationships as Array<Record<string, unknown>> | undefined) ?? [];
                        return (
                          <div key={i} className="rounded-md border border-border bg-surface-2 p-3">
                            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                              {nodes.map((node, j) => (
                                <span key={node.id} className="inline-flex items-center gap-1.5">
                                  {j > 0 ? (
                                    <span className="text-[10px] uppercase text-dim">{String(rels[j - 1]?.relationship_type ?? rels[j - 1]?.type ?? "→")}</span>
                                  ) : null}
                                  <Link to={`/app/cases/${caseId}/entities/${node.id}`} className="rounded border border-border bg-surface-3 px-1.5 py-0.5 text-[11px] text-foreground hover:border-accent/40">
                                    {node.display_value}
                                  </Link>
                                </span>
                              ))}
                            </div>
                            {path.explanation ? <p className="mt-2 text-[11px] text-dim">{String(path.explanation)}</p> : null}
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              ) : null}

              <Card>
                <CardHeader><CardTitle>Limitations</CardTitle></CardHeader>
                <CardContent>
                  {record.explanation.limitations.length === 0 ? (
                    <p className="text-xs text-dim">No limitations recorded for this finding.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {record.explanation.limitations.map((limit, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-muted">
                          <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-high" />
                          {limit}
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-5">
              <Card>
                <CardHeader><CardTitle>Affected entities</CardTitle></CardHeader>
                <CardContent className="space-y-1.5">
                  {record.affected_entities.length === 0 ? (
                    <p className="text-xs text-dim">None recorded.</p>
                  ) : (
                    record.affected_entities.map((id) => {
                      const entity = entityById.get(id);
                      return (
                        <Link key={id} to={`/app/cases/${caseId}/entities/${id}`} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-surface-3">
                          <span className="truncate text-foreground">{entity?.display_value ?? id.slice(0, 8)}</span>
                          <Badge>{entity?.entity_type ?? "?"}</Badge>
                        </Link>
                      );
                    })
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Source records</CardTitle></CardHeader>
                <CardContent className="space-y-1.5">
                  {evidence.length === 0 ? (
                    <p className="text-xs text-dim">No direct source records attached.</p>
                  ) : (
                    evidence.map((ev, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="size-1.5 shrink-0 rounded-full bg-accent" />
                        <span className="truncate text-muted">{String(ev.label ?? ev.kind ?? ev.id ?? `record ${i + 1}`)}</span>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-border">
                <CardHeader><CardTitle>Review decision</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  {(canReview || canConfirm || canDismiss) && record.status === "NEW" ? (
                    <>
                      <div className="flex flex-wrap gap-2">
                        {canReview ? (
                          <Button variant="outline" size="sm" onClick={() => void applyStatus("REVIEWED")}>
                            <Eye className="size-3.5" /> Mark reviewed
                          </Button>
                        ) : null}
                        {canConfirm ? (
                          <Button size="sm" onClick={() => { setReason(""); applyStatus("CONFIRMED"); }}>
                            <Check className="size-3.5" /> Confirm
                          </Button>
                        ) : null}
                        {canDismiss ? (
                          <Button variant="ghost" size="sm" onClick={() => setConfirmOpen(true)}>
                            <X className="size-3.5" /> Dismiss
                          </Button>
                        ) : null}
                      </div>
                      {canDismiss && confirmOpen ? (
                        <div className="space-y-2 rounded-md border border-border bg-surface-2 p-3">
                          <Label>Dismissal reason</Label>
                          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this not actionable?" />
                          <Button size="sm" variant="danger" onClick={() => applyStatus("DISMISSED")}>Dismiss finding</Button>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-xs leading-relaxed text-dim">
                      {record.status !== "NEW"
                        ? <>This finding was set to <strong className="text-foreground">{record.status.toLowerCase()}</strong>{record.reviewed_at ? ` · ${formatDateTime(record.reviewed_at)}` : ""}.</>
                        : "No review actions yet."}
                    </p>
                  )}
                  {!canReview && !canConfirm && !canDismiss && record.status === "NEW" ? (
                    <p className="text-xs text-dim">You don't have permission to review this case's findings.</p>
                  ) : null}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}
    </PageContainer>
  );
}