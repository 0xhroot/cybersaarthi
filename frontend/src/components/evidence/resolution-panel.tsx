import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, ClipboardList, Loader2, Search, X } from "lucide-react";

import {
  useArtifacts,
  useCancelIntelJob,
  useIntelJobs,
  useReviewArtifact,
  useSubmitEntityResolution,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { AnalysisJobOut, DerivedArtifactOut } from "@/types/domain";

/**
 * Entity candidate-match panel (phase 3, feature A).
 *
 * Contract: a bounded case-wide scan proposes reviewable `entity_resolution`
 * candidates. The score is a deterministic 0-100 similarity *band*, never a
 * probability. Approving records additive cross-aliases for both entities —
 * it never merges them (merging stays the explicit `entity.merge` action) —
 * so a wrong approval cannot destroy an entity row.
 */

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

function bandTone(band: string): "success" | "info" | "neutral" {
  if (band === "strong") return "success";
  if (band === "ambiguous") return "info";
  return "neutral";
}

interface EntitySide {
  id: string;
  entity_type: string;
  canonical_value: string;
  display_value: string;
}

function sideOf(payload: Record<string, unknown>, key: "entity_a" | "entity_b"): EntitySide | null {
  const value = payload[key];
  if (!value || typeof value !== "object") return null;
  return value as EntitySide;
}

function payloadOf(artifact: DerivedArtifactOut): {
  entity_a?: EntitySide;
  entity_b?: EntitySide;
  method?: string;
  score?: number;
  score_band?: string;
  score_semantics?: string;
  matching_fields?: Array<{ field?: string; detail?: unknown }>;
  conflicting_fields?: Array<{ field?: string; detail?: unknown }>;
} {
  return artifact.payload as Record<string, unknown>;
}

function validationErrorsOf(artifact: DerivedArtifactOut): Array<{ field?: string; code?: string; message?: string }> {
  return (artifact.validation_errors ?? []) as Array<{ field?: string; code?: string; message?: string }>;
}

function CandidateRow({
  artifact,
  caseId,
  busy,
  canReview,
  onApprove,
  onReject,
}: {
  artifact: DerivedArtifactOut;
  caseId: string;
  busy: boolean;
  canReview: boolean;
  onApprove: (artifact: DerivedArtifactOut) => void;
  onReject: (artifact: DerivedArtifactOut) => void;
}) {
  const payload = payloadOf(artifact);
  const entityA = payload.entity_a ?? sideOf(artifact.payload, "entity_a");
  const entityB = payload.entity_b ?? sideOf(artifact.payload, "entity_b");
  const errors = validationErrorsOf(artifact);
  const nameOnly = errors.some((err) => err.code === "no_identifier_evidence");
  const band = payload.score_band ?? "unknown";
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="entity-candidate">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={artifact.status === "approved" ? "success" : artifact.status === "rejected" ? "critical" : "info"}>
          {artifact.status === "approved" ? "Approved" : artifact.status === "rejected" ? "Rejected" : "Needs review"}
        </Badge>
        <Badge tone={bandTone(band)}>{band === "unknown" ? "no band" : `${band} band`}</Badge>
        {nameOnly ? <Badge tone="neutral">name-only evidence</Badge> : null}
        {artifact.origin === "llm" ? <Badge tone="accent">model verdict (unverified)</Badge> : null}
        <span className="ml-auto font-mono text-[10px] text-dim">
          {String(payload.method ?? "unknown")} · {shortId(artifact.id)}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {entityA ? (
          <Link className="text-foreground underline-offset-2 hover:underline" to={`/app/cases/${caseId}/entities/${entityA.id}`}>
            {entityA.display_value}
          </Link>
        ) : null}
        <span className="text-dim">↔</span>
        {entityB ? (
          <Link className="text-foreground underline-offset-2 hover:underline" to={`/app/cases/${caseId}/entities/${entityB.id}`}>
            {entityB.display_value}
          </Link>
        ) : null}
      </div>

      <p className="mt-1 text-[11px] text-dim">
        similarity {typeof payload.score === "number" ? payload.score.toFixed(1) : "—"} ·{" "}
        {payload.score_semantics ?? "band, not a probability"}
      </p>

      {payload.matching_fields?.length ? (
        <p className="mt-1 text-[11px] text-dim">
          matched: {payload.matching_fields.map((field) => field.field).join(", ")}
        </p>
      ) : null}
      {payload.conflicting_fields?.length ? (
        <p className="mt-1 text-[11px] text-high">
          conflicting: {payload.conflicting_fields.map((field) => field.field).join(", ")}
        </p>
      ) : null}

      {errors.length ? (
        <ul className="mt-2 space-y-1 rounded border border-high/25 bg-high/8 p-2">
          {errors.map((err, i) => (
            <li key={i} className="text-[11px] text-high">
              <span className="font-mono">{err.code}</span>
              {err.message ? <span> — {err.message}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {artifact.status === "approved" ? (
        <p className="mt-2 text-[11px] text-dim">
          Recorded as cross-aliases for both entities. The entities themselves were not merged.
        </p>
      ) : null}

      {artifact.status === "pending_review" && canReview ? (
        <div className="mt-2 flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => onApprove(artifact)}>
            <Check className="size-3.5" /> Approve
          </Button>
          <Button size="sm" variant="danger" disabled={busy} onClick={() => onReject(artifact)}>
            <X className="size-3.5" /> Reject
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function ResolutionPanel({ caseId }: { caseId: string }) {
  const canRun = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const jobs = useIntelJobs(caseId, "entity_resolution");
  const artifacts = useArtifacts(caseId, "entity_resolution");
  const submit = useSubmitEntityResolution(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [noteOpen, setNoteOpen] = useState<{ artifact: DerivedArtifactOut; decision: "approved" | "rejected" } | null>(null);
  const [note, setNote] = useState("");

  const activeJob = (jobs.data?.items ?? []).find((j) => j.status === "pending" || j.status === "running");
  const latest = (jobs.data?.items ?? [])[0];
  const summary = (latest?.result_summary ?? {}) as Record<string, unknown>;

  const runScan = async () => {
    try {
      const result = await submit.mutateAsync();
      toast({
        title: "Candidate scan queued",
        description: result.duplicate ? "Reusing the active resolution job." : "Comparing case entities within blocking buckets.",
      });
    } catch (err) {
      toast({ title: "Scan failed", description: (err as Error).message });
    }
  };

  const cancelJob = async (jobId: string) => {
    try {
      await cancel.mutateAsync(jobId);
      toast({ title: "Cancellation requested", description: "The job will end as canceled once the runner observes the flag." });
    } catch (err) {
      toast({ title: "Cancel failed", description: (err as Error).message });
    }
  };

  const submitReview = async (decision: "approved" | "rejected") => {
    if (!noteOpen) return;
    try {
      await review.mutateAsync({ artifactId: noteOpen.artifact.id, review: { decision, note: note || null } });
      toast({
        title: decision === "approved" ? "Candidate approved" : "Candidate rejected",
        description:
          decision === "approved"
            ? "Cross-aliases were recorded for both entities. No entity was merged."
            : "The rejection was recorded in the audit log.",
      });
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">Candidate matches</p>
        {canRun ? (
          <Button size="sm" disabled={submit.isPending || Boolean(activeJob)} onClick={() => void runScan()}>
            {submit.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />}
            {activeJob ? "Scanning…" : "Scan for candidates"}
          </Button>
        ) : null}
      </div>

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          <span className="text-dim">
            {String(summary.entities_scanned ?? "—")} entities scanned · {String(summary.pairs_proposed ?? "—")} candidates ·{" "}
            {formatRelative(latest.updated_at)}
          </span>
          {activeJob && canRun ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)}>
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}

      {jobs.error ? <CardError error={jobs.error} onRetry={() => void jobs.refetch()} /> : null}

      {artifacts.isLoading ? (
        <Skeleton className="h-24" />
      ) : artifacts.error ? (
        <CardError error={artifacts.error} onRetry={() => void artifacts.refetch()} />
      ) : (artifacts.data?.items ?? []).length === 0 ? (
        <EmptyState
          title="No candidate matches"
          description="Run the case-wide scan to compare entities within blocking buckets. Candidates stay unreviewed until a human decides."
        />
      ) : (
        <div className="space-y-2">
          {(artifacts.data?.items ?? []).map((artifact) => (
            <CandidateRow
              key={artifact.id}
              artifact={artifact}
              caseId={caseId}
              busy={review.isPending}
              canReview={canReview}
              onApprove={(a) => {
                void review
                  .mutateAsync({ artifactId: a.id, review: { decision: "approved" } })
                  .then(
                    () => toast({ title: "Candidate approved", description: "Cross-aliases were recorded. No entity was merged." }),
                    (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
                  );
              }}
              onReject={(a) => setNoteOpen({ artifact: a, decision: "rejected" })}
            />
          ))}
        </div>
      )}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">Why is this candidate rejected?</p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-border bg-surface-3 p-2 text-xs text-foreground outline-none focus:border-accent/40"
            placeholder="Rejection reason"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              disabled={review.isPending || !note.trim()}
              onClick={() => void submitReview("rejected")}
            >
              <ClipboardList className="size-3.5" /> Record decision
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setNoteOpen(null);
                setNote("");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CardError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-2">
      <ErrorState error={error} onRetry={onRetry} />
    </div>
  );
}
