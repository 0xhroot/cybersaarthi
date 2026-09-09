import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { Lightbulb, AlertTriangle } from "lucide-react";
import { useHypotheses } from "@/hooks/queries";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/status";
import { RELATIONSHIP_TYPE_META } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import type { RelationshipType } from "@/types/domain";

function signalName(signal: Record<string, unknown>): string {
  return String(signal.name ?? signal.label ?? signal.description ?? "signal");
}

function signalMessage(signal: Record<string, unknown>): string | null {
  const msg = signal.description ?? signal.message;
  return msg ? String(msg) : null;
}

export default function HypothesesPage() {
  const { caseId = "" } = useParams();
  const hypotheses = useHypotheses(caseId);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Doctorial reasoning"
        title="Hypotheses"
        description="Candidate explanations assembled from weaker or partial signals. These are prompts for investigation, not conclusions."
      />

      <Card className="mt-4 border-high/30 bg-high/5">
        <CardContent className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-high" />
          <p className="text-xs leading-relaxed text-muted">
            Hypotheses propose a plausible link and show the evidence behind it. They are <strong>not findings</strong> —
            nothing here is treated as fact until confirmed against source records and reviewed by an analyst.
          </p>
        </CardContent>
      </Card>

      <div className="mt-5">
        {hypotheses.isLoading ? (
          <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
        ) : hypotheses.isError ? (
          <Card><ErrorState error={hypotheses.error} onRetry={() => void hypotheses.refetch()} /></Card>
        ) : (hypotheses.data ?? []).length === 0 ? (
          <Card><CardContent className="py-10 text-center text-xs text-dim">No hypotheses in this case yet.</CardContent></Card>
        ) : (
          <div className="space-y-4">
            {(hypotheses.data ?? []).map((h) => {
              const path = (h.metadata as Record<string, unknown>)?.path as
                | Record<string, unknown>
                | undefined;
              const entities = path?.entities as Array<{ id: string; display_value: string }> | undefined;
              const relationships = path?.relationships as
                | Array<{ relationship_type: string; source?: string; target?: string }>
                | undefined;
              return (
                <Card key={h.title}>
                  <CardHeader>
                    <CardTitle className="flex flex-wrap items-center gap-2">
                      <Lightbulb className="size-4 text-accent" />
                      <span className="text-sm font-medium text-foreground">{h.title}</span>
                      <SeverityBadge value={h.severity} />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-xs leading-relaxed text-muted">{h.summary}</p>

                    {(h.signals ?? []).length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {(h.signals ?? []).slice(0, 6).map((sig, i) => (
                          <span key={i} className="rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px] text-muted" title={signalMessage(sig) ?? undefined}>
                            {signalName(sig)}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    {relationships?.length ? (
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-dim">
                        {relationships.map((rel, i) => (
                          <span key={i} className="inline-flex items-center gap-1.5">
                            {i > 0 ? <span className="text-dim">→</span> : null}
                            <Badge>{RELATIONSHIP_TYPE_META[rel.relationship_type as RelationshipType]?.label ?? rel.relationship_type}</Badge>
                          </span>
                        ))}
                        <span className="ml-1 text-[10px] text-dim">candidate path</span>
                      </div>
                    ) : null}

                    <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-2.5 text-[10px] text-dim">
                      <span>score <span className="tabular text-foreground/70">{Math.round(h.score * 100)}</span></span>
                      <span>confidence{" "}
                        <span className="tabular text-foreground/70">
                          {h.confidence != null ? Math.round(h.confidence * 100) : "—"}
                        </span>
                      </span>
                      <span className="min-w-0 max-w-full truncate">
                        {entities && entities.length > 0 ? `entities: ${entities.map((e) => e.display_value).join(", ")}` : ""}
                      </span>
                    </div>

                    <p className="flex items-center gap-1.5 text-[11px] text-dim">
                      <AlertTriangle className="size-3 shrink-0 text-high" />
                      Not recorded in the graph — confirm before it informs an action.
                    </p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <p className="mt-6 text-[11px] leading-relaxed text-dim">
        To record a confirmed link, ingest evidence that documents it and re-run{" "}
        <Link to={`/app/cases/${caseId}/analytics`} className="text-accent hover:text-accent-strong">analytics</Link>.
      </p>
    </PageContainer>
  );
}