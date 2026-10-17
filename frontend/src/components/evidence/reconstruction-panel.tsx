import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, ClipboardList, Clock, Loader2, Upload, X } from "lucide-react";

import {
  useArtifacts,
  useCancelIntelJob,
  useCommitTimelineProposal,
  useIntelJobs,
  useReviewArtifact,
  useSubmitTimelineReconstruction,
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
 * Timeline reconstruction panel (phase 3, feature B).
 *
 * Contract: deterministic proposals only — each one cites the source record
 * field it came from and preserves the original text and time zone next to
 * the parsed instant. A zone-less timestamp is shown with its documented UTC
 * assumption; an unparseable field becomes a flagged `missing_timestamp`
 * proposal that can never be committed. Committing requires an explicit
 * reviewer approval plus `case.update`, goes through the authoritative
 * timeline service, and is idempotent (re-committing returns the same event).
 */

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

function validationErrorsOf(artifact: DerivedArtifactOut): Array<{ field?: string; code?: string; message?: string }> {
  return (artifact.validation_errors ?? []) as Array<{ field?: string; code?: string; message?: string }>;
}

interface ProposalPayload {
  title?: string;
  occurred_at?: string | null;
  original_timestamp?: string;
  tz?: string | null;
  tz_assumed?: boolean;
  time_granularity?: string | null;
  time_semantics?: string;
  missing_timestamp?: boolean;
  source_locator?: { record_no?: number; field?: string };
}

function payloadOf(artifact: DerivedArtifactOut): ProposalPayload {
  return artifact.payload as ProposalPayload;
}

function ProposalRow({
  artifact,
  busy,
  canReview,
  canCommit,
  committed,
  onApprove,
  onReject,
  onCommit,
}: {
  artifact: DerivedArtifactOut;
  busy: boolean;
  canReview: boolean;
  canCommit: boolean;
  committed: boolean;
  onApprove: (artifact: DerivedArtifactOut) => void;
  onReject: (artifact: DerivedArtifactOut) => void;
  onCommit: (artifact: DerivedArtifactOut) => void;
}) {
  const payload = payloadOf(artifact);
  const errors = validationErrorsOf(artifact);
  const locator = artifact.source_locator as { record_no?: number; field?: string } | null;
  const blocked = Boolean(payload.missing_timestamp) || !payload.occurred_at;
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="reconstruction-proposal">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={artifact.status === "approved" ? "success" : artifact.status === "rejected" ? "critical" : "info"}>
          {artifact.status === "approved" ? "Approved" : artifact.status === "rejected" ? "Rejected" : "Proposal"}
        </Badge>
        {committed ? <Badge tone="accent">committed</Badge> : null}
        {payload.time_granularity ? <Badge tone="neutral">{payload.time_granularity}</Badge> : null}
        {payload.tz_assumed ? <Badge tone="info">UTC assumed (no zone in source)</Badge> : null}
        {payload.tz ? <Badge tone="neutral">zone {payload.tz}</Badge> : null}
        <span className="ml-auto font-mono text-[10px] text-dim">{shortId(artifact.id)}</span>
      </div>

      <p className="mt-2 text-sm text-foreground">{payload.title ?? "Reconstructed event"}</p>
      <div className="mt-1 space-y-0.5 text-xs">
        <p>
          <span className="text-dim">source text: </span>
          <span className="font-mono text-foreground/85">{payload.original_timestamp ?? "—"}</span>
        </p>
        <p>
          <span className="text-dim">parsed instant: </span>
          <span className="font-mono text-foreground/85">{payload.occurred_at ?? "not established"}</span>
        </p>
        {payload.time_semantics ? (
          <p>
            <span className="text-dim">semantics: </span>
            <span className="text-foreground/85">{payload.time_semantics.replace(/_/g, " ")}</span>
          </p>
        ) : null}
        {locator?.field ? (
          <p>
            <span className="text-dim">from: </span>
            <span className="font-mono text-foreground/85">{locator.field}</span>
            {typeof locator.record_no === "number" ? <span className="text-dim"> · record {locator.record_no}</span> : null}
            {artifact.evidence_file_id ? (
              <Link className="ml-2 text-accent underline-offset-2 hover:underline" to={`/app/cases/${artifact.case_id}/evidence`}>
                open evidence
              </Link>
            ) : null}
          </p>
        ) : null}
      </div>

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

      {artifact.status === "approved" && blocked ? (
        <p className="mt-2 text-[11px] text-dim">
          Approved, but no timestamp was established — it cannot be committed until a reviewer records the time elsewhere.
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-2">
        {artifact.status === "pending_review" && canReview ? (
          <>
            <Button size="sm" disabled={busy} onClick={() => onApprove(artifact)}>
              <Check className="size-3.5" /> Approve
            </Button>
            <Button size="sm" variant="danger" disabled={busy} onClick={() => onReject(artifact)}>
              <X className="size-3.5" /> Reject
            </Button>
          </>
        ) : null}
        {artifact.status === "approved" && canCommit ? (
          <Button size="sm" variant="secondary" disabled={busy || blocked || committed} onClick={() => onCommit(artifact)}>
            <Upload className="size-3.5" /> {committed ? "Committed" : "Commit to timeline"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function ReconstructionPanel({ caseId }: { caseId: string }) {
  const canRun = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const canCommit = useCan("case.update");
  const jobs = useIntelJobs(caseId, "timeline");
  const artifacts = useArtifacts(caseId, "timeline_proposal");
  const submit = useSubmitTimelineReconstruction(caseId);
  const review = useReviewArtifact(caseId);
  const commit = useCommitTimelineProposal(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [noteOpen, setNoteOpen] = useState<DerivedArtifactOut | null>(null);
  const [note, setNote] = useState("");
  const [committedIds, setCommittedIds] = useState<Set<string>>(new Set());

  const activeJob = (jobs.data?.items ?? []).find((j) => j.status === "pending" || j.status === "running");
  const latest = (jobs.data?.items ?? [])[0];
  const summary = (latest?.result_summary ?? {}) as Record<string, unknown>;

  const runReconstruction = async () => {
    try {
      const result = await submit.mutateAsync();
      toast({
        title: "Reconstruction queued",
        description: result.duplicate ? "Reusing the active reconstruction job." : "Parsing deterministic timestamps from case records.",
      });
    } catch (err) {
      toast({ title: "Reconstruction failed", description: (err as Error).message });
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
      await review.mutateAsync({ artifactId: noteOpen.id, review: { decision, note: note || null } });
      toast({ title: decision === "approved" ? "Proposal approved" : "Proposal rejected", description: "The decision was recorded in the audit log." });
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
    }
  };

  const commitProposal = async (artifact: DerivedArtifactOut) => {
    try {
      const result = await commit.mutateAsync(artifact.id);
      setCommittedIds((prev) => new Set(prev).add(artifact.id));
      toast({
        title: result.duplicate ? "Already committed" : "Event committed",
        description: result.duplicate
          ? "This proposal was committed earlier — the existing event was returned instead of a duplicate."
          : "The event was added to the case timeline.",
      });
    } catch (err) {
      toast({ title: "Commit failed", description: (err as Error).message });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">Reconstruction proposals</p>
        {canRun ? (
          <Button size="sm" disabled={submit.isPending || Boolean(activeJob)} onClick={() => void runReconstruction()}>
            {submit.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Clock className="size-3.5" />}
            {activeJob ? "Reconstructing…" : "Reconstruct timeline"}
          </Button>
        ) : null}
      </div>

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          <span className="text-dim">
            {String(summary.drafts_generated ?? "—")} drafts · {String(summary.proposals_recorded ?? "—")} recorded ·{" "}
            {String(summary.missing_timestamps ?? 0)} missing · {formatRelative(latest.updated_at)}
          </span>
          {activeJob && canRun ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)}>
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}

      {jobs.error ? <PanelError error={jobs.error} onRetry={() => void jobs.refetch()} /> : null}

      {artifacts.isLoading ? (
        <Skeleton className="h-24" />
      ) : artifacts.error ? (
        <PanelError error={artifacts.error} onRetry={() => void artifacts.refetch()} />
      ) : (artifacts.data?.items ?? []).length === 0 ? (
        <EmptyState
          title="No reconstruction proposals"
          description="Run the deterministic reconstruction to draft events from case records. Proposals stay visually distinct until approved and committed."
        />
      ) : (
        <div className="space-y-2">
          {(artifacts.data?.items ?? []).map((artifact) => (
            <ProposalRow
              key={artifact.id}
              artifact={artifact}
              busy={review.isPending || commit.isPending}
              canReview={canReview}
              canCommit={canCommit}
              committed={committedIds.has(artifact.id)}
              onApprove={(a) => {
                void review
                  .mutateAsync({ artifactId: a.id, review: { decision: "approved" } })
                  .then(
                    () => toast({ title: "Proposal approved", description: "Commit it to the timeline when ready." }),
                    (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
                  );
              }}
              onReject={(a) => setNoteOpen(a)}
              onCommit={(a) => void commitProposal(a)}
            />
          ))}
        </div>
      )}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">Why is this proposal rejected?</p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-border bg-surface-3 p-2 text-xs text-foreground outline-none focus:border-accent/40"
            placeholder="Rejection reason"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" disabled={review.isPending || !note.trim()} onClick={() => void submitReview("rejected")}>
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

function PanelError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-2">
      <ErrorState error={error} onRetry={onRetry} />
    </div>
  );
}
