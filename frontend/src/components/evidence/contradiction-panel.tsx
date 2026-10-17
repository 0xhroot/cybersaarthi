import { useState } from "react";
import { Check, ClipboardList, Loader2, Scale, X } from "lucide-react";

import {
  useArtifacts,
  useCancelIntelJob,
  useIntelJobs,
  useResolveContradiction,
  useReviewArtifact,
  useSubmitContradictions,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { AnalysisJobOut, ContradictionResolutionState, DerivedArtifactOut } from "@/types/domain";

/**
 * Contradiction panel (phase 3, feature C).
 *
 * Contract: candidates are anchored comparisons — two records only ever
 * contradict each other inside a shared identifier anchor, and every candidate
 * carries deterministic alternative explanations so the UI never presents the
 * engine's conclusion as established fact. Review states: Unresolved until a
 * human decides; Confirmed / False positive via the one-shot artifact review;
 * Explained / Requires additional evidence / Deferred appended as new child
 * artifacts. Nothing ever rewrites the candidate or the evidence.
 */

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

function priorityTone(priority: string): "high" | "info" | "neutral" {
  if (priority === "high") return "high";
  if (priority === "medium") return "info";
  return "neutral";
}

const STATE_LABELS: Record<ContradictionResolutionState, string> = {
  explained: "Explained",
  requires_evidence: "Requires additional evidence",
  deferred: "Deferred",
};

const RESOLVE_ACTIONS: Array<{ state: ContradictionResolutionState; label: string }> = [
  { state: "explained", label: "Explained" },
  { state: "requires_evidence", label: "Requires additional evidence" },
  { state: "deferred", label: "Deferred" },
];

interface ClaimSide {
  record_no?: number;
  field?: string;
  value?: string;
  original?: string;
  locator?: { record_no?: number; field?: string };
}

interface ContradictionPayload {
  category?: string;
  priority?: string;
  rule?: string;
  anchor?: { value?: string; scope?: string; fields?: string };
  first?: ClaimSide;
  second?: ClaimSide;
  conflicting_values?: Array<{ field?: string; first?: string; second?: string }>;
  alternatives?: string[];
  explanation?: string;
  type?: string;
}

interface ContradictionReviewPayload {
  type?: string;
  state?: ContradictionResolutionState;
  note?: string;
  for_artifact_id?: string;
}

function payloadOf(artifact: DerivedArtifactOut): ContradictionPayload {
  return artifact.payload as ContradictionPayload;
}

function statusLabel(status: string): { label: string; tone: "success" | "critical" | "info" } {
  if (status === "approved") return { label: "Confirmed", tone: "success" };
  if (status === "rejected") return { label: "False positive", tone: "critical" };
  return { label: "Unresolved", tone: "info" };
}

function ClaimColumn({ side, heading }: { side: ClaimSide; heading: string }) {
  return (
    <div className="rounded border border-border bg-surface-3 p-2">
      <p className="text-[10px] uppercase tracking-wider text-dim">
        {heading}
        {typeof side.record_no === "number" ? ` · record ${side.record_no}` : ""}
        {side.field ? ` · ${side.field}` : ""}
      </p>
      <p className="mt-1 font-mono text-sm text-foreground">{side.original ?? side.value ?? "—"}</p>
      {side.original && side.value && side.original !== side.value ? (
        <p className="mt-0.5 font-mono text-[10px] text-dim">compared as {side.value}</p>
      ) : null}
    </div>
  );
}

function CandidateRow({
  artifact,
  resolutions,
  busy,
  canReview,
  canResolve,
  onConfirm,
  onFalsePositive,
  onResolve,
}: {
  artifact: DerivedArtifactOut;
  resolutions: DerivedArtifactOut[];
  busy: boolean;
  canReview: boolean;
  canResolve: boolean;
  onConfirm: (artifact: DerivedArtifactOut) => void;
  onFalsePositive: (artifact: DerivedArtifactOut) => void;
  onResolve: (artifact: DerivedArtifactOut, state: ContradictionResolutionState) => void;
}) {
  const payload = payloadOf(artifact);
  const meta = statusLabel(artifact.status);
  const anchor = payload.anchor;
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="contradiction-candidate">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <Badge tone="neutral">{payload.category ?? "unclassified"}</Badge>
        <Badge tone={priorityTone(payload.priority ?? "low")}>{payload.priority ?? "low"} priority</Badge>
        {artifact.origin === "llm" ? <Badge tone="accent">model verdict (unverified)</Badge> : null}
        <span className="ml-auto font-mono text-[10px] text-dim">
          {anchor?.scope ?? "unscoped"} {anchor?.value ? `· ${anchor.value}` : ""} · {shortId(artifact.id)}
        </span>
      </div>

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <ClaimColumn side={payload.first ?? {}} heading="First record" />
        <ClaimColumn side={payload.second ?? {}} heading="Second record" />
      </div>

      {payload.alternatives?.length ? (
        <div className="mt-2 rounded border border-border bg-surface-3 p-2">
          <p className="text-[10px] uppercase tracking-wider text-dim">Alternative explanations to rule out</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {payload.alternatives.map((alternative, i) => (
              <li key={i} className="text-[11px] text-foreground/85">
                {alternative}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {payload.explanation ? (
        <p className="mt-2 text-[11px] text-foreground/85">
          <span className="text-dim">note: </span>
          {payload.explanation}
        </p>
      ) : null}

      {resolutions.length ? (
        <div className="mt-2 space-y-1">
          {resolutions.map((child) => {
            const childPayload = child.payload as ContradictionReviewPayload;
            return (
              <p key={child.id} className="text-[11px] text-dim">
                <Badge tone="neutral">{childPayload.state ? STATE_LABELS[childPayload.state] : "Recorded"}</Badge>{" "}
                {childPayload.note ? <span>— {childPayload.note}</span> : null}{" "}
                <span className="font-mono">{formatRelative(child.created_at)}</span>
              </p>
            );
          })}
        </div>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-2">
        {artifact.status === "pending_review" && canReview ? (
          <>
            <Button size="sm" disabled={busy} onClick={() => onConfirm(artifact)}>
              <Check className="size-3.5" /> Confirm
            </Button>
            <Button size="sm" variant="danger" disabled={busy} onClick={() => onFalsePositive(artifact)}>
              <X className="size-3.5" /> False positive
            </Button>
          </>
        ) : null}
        {artifact.status === "pending_review" && canResolve
          ? RESOLVE_ACTIONS.map((action) => (
              <Button key={action.state} size="sm" variant="secondary" disabled={busy} onClick={() => onResolve(artifact, action.state)}>
                <ClipboardList className="size-3.5" /> {action.label}
              </Button>
            ))
          : null}
      </div>
    </div>
  );
}

export function ContradictionPanel({ caseId }: { caseId: string }) {
  const canRun = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const jobs = useIntelJobs(caseId, "contradiction");
  const artifacts = useArtifacts(caseId, "contradiction");
  const submit = useSubmitContradictions(caseId);
  const review = useReviewArtifact(caseId);
  const resolve = useResolveContradiction(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [noteOpen, setNoteOpen] = useState<{
    artifact: DerivedArtifactOut;
    action: { kind: "review"; decision: "rejected" } | { kind: "resolve"; state: ContradictionResolutionState };
  } | null>(null);
  const [note, setNote] = useState("");

  const activeJob = (jobs.data?.items ?? []).find((j) => j.status === "pending" || j.status === "running");
  const latest = (jobs.data?.items ?? [])[0];
  const summary = (latest?.result_summary ?? {}) as Record<string, unknown>;

  const items = artifacts.data?.items ?? [];
  const candidates = items.filter((artifact) => payloadOf(artifact).type === "contradiction");
  const resolutionsOf = (artifact: DerivedArtifactOut) =>
    items.filter((child) => {
      const childPayload = child.payload as ContradictionReviewPayload;
      return childPayload.type === "contradiction_review" && childPayload.for_artifact_id === artifact.id;
    });

  const runDetection = async () => {
    try {
      const result = await submit.mutateAsync();
      toast({
        title: "Contradiction scan queued",
        description: result.duplicate ? "Reusing the active detection job." : "Comparing anchored claims within shared identifiers.",
      });
    } catch (err) {
      toast({ title: "Contradiction scan failed", description: (err as Error).message });
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

  const confirmCandidate = async (artifact: DerivedArtifactOut) => {
    try {
      await review.mutateAsync({ artifactId: artifact.id, review: { decision: "approved" } });
      toast({ title: "Contradiction confirmed", description: "Recorded as confirmed — the evidence itself stays untouched." });
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
    }
  };

  const submitNote = async () => {
    if (!noteOpen) return;
    try {
      if (noteOpen.action.kind === "review") {
        await review.mutateAsync({ artifactId: noteOpen.artifact.id, review: { decision: "rejected", note } });
        toast({ title: "Marked false positive", description: "The candidate stays recorded with your reason in the audit trail." });
      } else {
        await resolve.mutateAsync({
          artifactId: noteOpen.artifact.id,
          resolution: { state: noteOpen.action.state, note },
        });
        toast({
          title: "Resolution recorded",
          description: "Your state was appended as a new artifact — the candidate was not rewritten.",
        });
      }
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Recording failed", description: (err as Error).message });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">Contradictions</p>
        {canRun ? (
          <Button size="sm" disabled={submit.isPending || Boolean(activeJob)} onClick={() => void runDetection()}>
            {submit.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Scale className="size-3.5" />}
            {activeJob ? "Scanning…" : "Detect contradictions"}
          </Button>
        ) : null}
      </div>

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          <span className="text-dim">
            {String(summary.conflicts ?? "—")} conflicts · {String(summary.artifacts_created ?? "—")} recorded ·{" "}
            {formatRelative(latest.updated_at)}
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
      ) : candidates.length === 0 ? (
        <EmptyState
          title="No contradictions recorded"
          description="Run the anchored detection to compare claims that share an identifier. Every candidate ships with alternative explanations and stays reviewable."
        />
      ) : (
        <div className="space-y-2">
          {candidates.map((artifact) => (
            <CandidateRow
              key={artifact.id}
              artifact={artifact}
              resolutions={resolutionsOf(artifact)}
              busy={review.isPending || resolve.isPending}
              canReview={canReview}
              canResolve={canReview}
              onConfirm={(a) => void confirmCandidate(a)}
              onFalsePositive={(a) => setNoteOpen({ artifact: a, action: { kind: "review", decision: "rejected" } })}
              onResolve={(a, state) => setNoteOpen({ artifact: a, action: { kind: "resolve", state } })}
            />
          ))}
        </div>
      )}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">
            {noteOpen.action.kind === "review"
              ? "Why is this candidate a false positive?"
              : `Record your note for “${STATE_LABELS[noteOpen.action.state]}” (required).`}
          </p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-border bg-surface-3 p-2 text-xs text-foreground outline-none focus:border-accent/40"
            placeholder="Note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" disabled={(review.isPending || resolve.isPending) || !note.trim()} onClick={() => void submitNote()}>
              <ClipboardList className="size-3.5" /> Record
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
