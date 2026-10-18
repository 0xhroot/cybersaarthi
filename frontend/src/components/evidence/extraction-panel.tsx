import { useState } from "react";
import { Check, ClipboardList, Loader2, Sparkles, X } from "lucide-react";

import { useArtifacts, useCancelIntelJob, useExtractEvidence, useIntelJobs, useReviewArtifact } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { AnalysisJobOut, DerivedArtifactOut } from "@/types/domain";

/**
 * Evidence extraction copilot panel (feature 1).
 *
 * Contract: the model extracts; deterministic validation checks every claim
 * against the source record before it is stored. Nothing here is
 * auto-approved — artifacts stay `pending_review` until a human decides, a
 * flagged validation error is always shown (never hidden behind a green
 * badge), and canceling a job ends it as canceled, never as succeeded.
 */

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

function artifactStatusMeta(status: string): { label: string; tone: "success" | "info" | "critical" | "neutral" } {
  if (status === "approved") return { label: "Approved", tone: "success" };
  if (status === "rejected") return { label: "Rejected", tone: "critical" };
  if (status === "superseded") return { label: "Superseded", tone: "neutral" };
  if (status === "pending_review") return { label: "Needs review", tone: "info" };
  return { label: status, tone: "neutral" };
}

function fieldsOf(artifact: DerivedArtifactOut): Record<string, string[]> {
  const fields = (artifact.payload as { fields?: Record<string, string[]> }).fields;
  return fields ?? {};
}

function validationErrorsOf(artifact: DerivedArtifactOut): Array<{ field?: string; code?: string; message?: string }> {
  return (artifact.validation_errors ?? []) as Array<{ field?: string; code?: string; message?: string }>;
}

function ArtifactRow({
  artifact,
  onApprove,
  onReject,
  busy,
  canReview,
}: {
  artifact: DerivedArtifactOut;
  onApprove: (artifact: DerivedArtifactOut) => void;
  onReject: (artifact: DerivedArtifactOut) => void;
  busy: boolean;
  canReview: boolean;
}) {
  const meta = artifactStatusMeta(artifact.status);
  const errors = validationErrorsOf(artifact);
  const fields = fieldsOf(artifact);
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <Badge tone={artifact.validation_status === "valid" ? "success" : "high"}>
          {artifact.validation_status === "valid" ? "validated" : `${errors.length} flagged`}
        </Badge>
        {artifact.origin === "llm" ? <Badge tone="accent">model extraction</Badge> : null}
        {artifact.parent_artifact_id ? <Badge tone="neutral">edited</Badge> : null}
        <span className="ml-auto font-mono text-[10px] text-dim">{shortId(artifact.id)}</span>
      </div>
      <div className="mt-2 space-y-1">
        {Object.entries(fields).map(([field, values]) =>
          values.length ? (
            <p key={field} className="text-xs">
              <span className="text-dim">{field}: </span>
              <span className="text-foreground/85">{values.join("; ")}</span>
            </p>
          ) : null,
        )}
      </div>
      {errors.length ? (
        <ul className="mt-2 space-y-1 rounded border border-high/25 bg-high/8 p-2">
          {errors.map((err, i) => (
            <li key={i} className="text-[11px] text-high">
              <span className="font-mono">{err.field}</span>
              {err.code ? <span className="font-mono"> · {err.code}</span> : null}
              {err.message ? <span> — {err.message}</span> : null}
            </li>
          ))}
        </ul>
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

export function ExtractionPanel({ caseId, evidenceId }: { caseId: string; evidenceId: string }) {
  const canIngest = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const jobs = useIntelJobs(caseId, "ingestion");
  const artifacts = useArtifacts(caseId, "extraction");
  const extract = useExtractEvidence(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [noteOpen, setNoteOpen] = useState<{ artifact: DerivedArtifactOut; decision: "approved" | "rejected" } | null>(null);
  const [note, setNote] = useState("");

  const forEvidence = (artifact: DerivedArtifactOut) =>
    artifact.evidence_file_id === evidenceId &&
    // Multilingual analyses are extraction-kind too but belong to their own panel.
    (artifact.payload as { multilingual?: boolean }).multilingual !== true;
  const evidenceArtifacts = (artifacts.data?.items ?? []).filter(forEvidence);
  const evidenceJobs = (jobs.data?.items ?? []).filter((j) => j.evidence_file_id === evidenceId);
  const activeJob = evidenceJobs.find((j) => j.status === "pending" || j.status === "running");

  const runExtract = async () => {
    try {
      const result = await extract.mutateAsync(evidenceId);
      toast({
        title: "Extraction queued",
        description: result.duplicate ? "Reusing the active extraction job." : "The model is extracting fields from the source file.",
      });
    } catch (err) {
      toast({ title: "Extraction failed", description: (err as Error).message });
    }
  };

  const submitReview = async (decision: "approved" | "rejected") => {
    if (!noteOpen) return;
    try {
      await review.mutateAsync({ artifactId: noteOpen.artifact.id, review: { decision, note: note || null } });
      toast({ title: decision === "approved" ? "Extraction approved" : "Extraction rejected", description: "The decision was recorded in the audit log." });
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
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

  const latest = evidenceJobs[0];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">AI extraction copilot</p>
        {canIngest ? (
          <Button size="sm" disabled={extract.isPending || Boolean(activeJob)} onClick={() => void runExtract()}>
            {extract.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
            {activeJob ? "Extracting…" : "Run extraction"}
          </Button>
        ) : null}
      </div>

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          <span className="text-dim">
            {String((latest.result_summary as Record<string, unknown> | null)?.fields_verified ?? "—")} fields validated ·{" "}
            {formatRelative(latest.updated_at)}
          </span>
          {activeJob && canIngest ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)}>
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}

      {artifacts.isLoading ? (
        <Skeleton className="h-24" />
      ) : evidenceArtifacts.length === 0 ? (
        <EmptyState
          title="No extraction yet"
          description="Run the extraction copilot to draft fields from this file. Every field stays unreviewed until a human approves it."
        />
      ) : (
        <div className="space-y-2">
          {evidenceArtifacts.map((artifact) => (
            <ArtifactRow
              key={artifact.id}
              artifact={artifact}
              busy={review.isPending}
              canReview={canReview}
              onApprove={(a) => {
                if (a.validation_status === "valid") {
                  void review.mutateAsync({ artifactId: a.id, review: { decision: "approved" } }).then(
                    () => toast({ title: "Extraction approved", description: "The decision was recorded in the audit log." }),
                    (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
                  );
                } else {
                  setNoteOpen({ artifact: a, decision: "approved" });
                }
              }}
              onReject={(a) => setNoteOpen({ artifact: a, decision: "rejected" })}
            />
          ))}
        </div>
      )}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">
            {noteOpen.decision === "approved"
              ? "Record your approval note (optional)."
              : "Why is this extraction rejected?"}
          </p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-border bg-surface-3 p-2 text-xs text-foreground outline-none focus:border-accent/40"
            placeholder={noteOpen.decision === "approved" ? "Note (optional)" : "Rejection reason"}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" disabled={review.isPending || (noteOpen.decision === "rejected" && !note.trim())} onClick={() => void submitReview(noteOpen.decision)}>
              <ClipboardList className="size-3.5" /> Record decision
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setNoteOpen(null); setNote(""); }}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
