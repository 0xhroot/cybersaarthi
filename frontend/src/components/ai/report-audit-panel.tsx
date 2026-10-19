import { useState } from "react";
import { ClipboardList, FileSearch, Loader2, ShieldAlert } from "lucide-react";

import {
  useCancelIntelJob,
  useIntelJobs,
  useReportAudits,
  useReportAuditDetail,
  useReviewArtifact,
  useSubmitReportAudit,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { DerivedArtifactOut, ReportAuditOut } from "@/types/domain";

/**
 * AI report auditor panel (feature 10, phase 6).
 *
 * Contract: the auditor never edits or files the draft — it queues a bounded
 * audit whose findings are a reviewable `report_claim_review` artifact.
 * Deterministic code owns span reproduction, citation validation, amounts,
 * dates, arithmetic and chronology; the model only extracts claims and
 * assesses support, and every quoted span it produces is re-verified against
 * the real source records — forged quotes are rejected and flagged, never
 * trusted. The artifact is always `flagged` and `pending_review`: approval
 * and rejection are human decisions recorded in the audit log.
 */

interface AuditClaim {
  claim_id?: string | null;
  claim_index?: number;
  text?: string;
  char_start?: number;
  char_end?: number;
  category?: string | null;
  extraction_valid?: boolean;
  extraction_problems?: string[];
  citations?: Array<{ cited_id?: string; ok?: boolean; codes?: string[]; checked?: boolean }>;
  assessment?: {
    assessment?: string;
    explanation?: string;
    quotes_verified?: boolean;
    unverified_quotes?: string[];
  } | null;
  assessment_skipped?: string | null;
  deterministic?: {
    amounts?: Array<{ raw?: string; currency?: string | null; value?: string }>;
    dates?: string[];
    unparsed_dates?: number;
    arithmetic?: {
      ok?: boolean;
      stated?: string;
      computed?: string;
      components?: string[];
    } | null;
  };
  counter_evidence?: {
    records_searched?: number;
    note?: string;
    matches?: Array<{ token?: string; record_no?: number; evidence?: string; excerpt?: string }>;
  };
  findings?: Array<{ code?: string; severity?: string; detail?: Record<string, unknown> }>;
  severity?: string;
}

interface AuditPayload {
  report_audit?: boolean;
  draft_source?: { type?: string; conversation_id?: string | null; message_id?: string | null };
  draft_chars?: number;
  draft_hash?: string;
  claims?: AuditClaim[];
  counter_evidence?: { records_searched?: number; note?: string };
  model?: { claims_extracted?: number; claims_truncated?: number };
  rules_version?: string;
  analysis_scope?: string;
}

const SEVERITY_TONE: Record<string, "high" | "medium" | "low" | "info"> = {
  high: "high",
  medium: "medium",
  low: "low",
  info: "info",
};

function jobTone(status: string): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

function artifactStatusMeta(status: string): {
  label: string;
  tone: "success" | "info" | "critical" | "neutral";
} {
  if (status === "approved") return { label: "Approved", tone: "success" };
  if (status === "rejected") return { label: "Rejected", tone: "critical" };
  if (status === "superseded") return { label: "Superseded", tone: "neutral" };
  if (status === "pending_review") return { label: "Needs review", tone: "info" };
  return { label: status, tone: "neutral" };
}

function claimLabel(claim: AuditClaim): string {
  return claim.claim_id || `claim ${String(claim.claim_index ?? 0) + 1}`;
}

export function ReportAuditPanel({
  caseId,
  draft,
}: {
  caseId: string;
  draft: string | null;
}) {
  const canSubmit = useCan("case.read");
  const canReview = useCan("findings.review");
  const audits = useReportAudits(caseId);
  const intelJobs = useIntelJobs(caseId, "report_audit");
  const submit = useSubmitReportAudit(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [selected, setSelected] = useState<string | null>(null);
  const [noteOpen, setNoteOpen] = useState<{
    artifact: DerivedArtifactOut;
    decision: "approved" | "rejected";
  } | null>(null);
  const [note, setNote] = useState("");

  const items = audits.data?.items ?? [];
  const latest = items[0];
  const activeJob = (intelJobs.data?.items ?? []).find(
    (j) => j.status === "pending" || j.status === "running",
  );
  const detail = useReportAuditDetail(caseId, selected ?? latest?.id ?? null);

  const runAudit = async () => {
    if (!draft) return;
    try {
      const result = await submit.mutateAsync({ draft_text: draft });
      toast({
        title: "Audit queued",
        description: result.duplicate
          ? "Reusing the active audit for this draft."
          : "Claims extraction and support assessment run against the real case records.",
      });
    } catch (err) {
      toast({ title: "Audit failed", description: (err as Error).message });
    }
  };

  const cancelJob = async (jobId: string) => {
    try {
      await cancel.mutateAsync(jobId);
      toast({
        title: "Cancellation requested",
        description: "The job will end as canceled once the runner observes the flag.",
      });
    } catch (err) {
      toast({ title: "Cancel failed", description: (err as Error).message });
    }
  };

  const submitReview = async (decision: "approved" | "rejected") => {
    if (!noteOpen) return;
    try {
      await review.mutateAsync({
        artifactId: noteOpen.artifact.id,
        review: { decision, note: note || null },
      });
      toast({
        title: decision === "approved" ? "Approved" : "Rejected",
        description: "The decision was recorded in the audit log.",
      });
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
    }
  };

  const summary = (latest?.result_summary ?? null) as Record<string, unknown> | null;
  const detailArtifact = detail.data?.artifact ?? null;

  return (
    <div className="space-y-3" data-testid="report-audit-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wider text-dim">AI report auditor</p>
        {canSubmit ? (
          <Button
            size="sm"
            disabled={submit.isPending || Boolean(activeJob) || !draft}
            onClick={() => void runAudit()}
            data-testid="report-audit-run"
          >
            {submit.isPending || activeJob ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <FileSearch className="size-3.5" />
            )}
            {activeJob ? "Auditing…" : "Audit draft"}
          </Button>
        ) : null}
      </div>
      {!draft ? (
        <p className="text-[11px] text-dim" data-testid="report-audit-no-draft">
          Generate a report draft first — the auditor checks a draft against the case records and
          never edits or files it.
        </p>
      ) : null}

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="report-audit-latest">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          {latest.stale ? (
            <Badge tone="medium">draft changed since this audit</Badge>
          ) : null}
          <span className="text-dim">
            {String(summary?.claims_extracted ?? 0)} claims ·{" "}
            {String(summary?.findings_high ?? 0)} high / {String(summary?.findings_medium ?? 0)}{" "}
            medium / {String(summary?.findings_info ?? 0)} info findings ·{" "}
            {String(summary?.records_searched ?? 0)} records searched ·{" "}
            {formatRelative(latest.created_at)}
          </span>
          {activeJob && canSubmit ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)}>
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}
      {latest?.status === "failed" && latest.error ? (
        <div className="rounded border border-high/25 bg-high/8 p-2 text-[11px] text-high">
          Audit refused: <span className="font-mono">{latest.error}</span>
        </div>
      ) : null}
      {latest?.status === "partial" ? (
        <div className="rounded border border-medium/25 bg-medium/8 p-2 text-[11px] text-medium">
          Partial audit — some model calls failed; recorded findings below are unchanged and still
          need review.
        </div>
      ) : null}

      {items.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {items.slice(0, 8).map((item: ReportAuditOut) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSelected(item.id)}
              className="rounded border border-border bg-surface-3 px-2 py-1 font-mono text-[10px] text-dim transition hover:text-foreground"
              data-testid="report-audit-history-item"
            >
              {shortId(item.id)} · {item.status}
              {item.stale ? " · stale" : ""}
            </button>
          ))}
        </div>
      ) : null}

      {detail.isLoading ? (
        <Skeleton className="h-24" />
      ) : detailArtifact ? (
        <AuditCard
          artifact={detailArtifact}
          canReview={canReview}
          busy={review.isPending}
          onApprove={(artifact) => setNoteOpen({ artifact, decision: "approved" })}
          onReject={(artifact) => setNoteOpen({ artifact, decision: "rejected" })}
        />
      ) : latest ? null : (
        <EmptyState
          title="No report audits yet"
          description="Audit a generated draft: every span, citation, number and date is validated deterministically, and the model's claim support is verified against the real records — or flagged."
        />
      )}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">
            {noteOpen.decision === "approved"
              ? "Record your approval note (optional)."
              : "Why is this rejected?"}
          </p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-border bg-surface-3 p-2 text-xs text-foreground outline-none focus:border-accent/40"
            placeholder={noteOpen.decision === "approved" ? "Note (optional)" : "Rejection reason"}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            data-testid="report-audit-review-note"
          />
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              disabled={review.isPending || (noteOpen.decision === "rejected" && !note.trim())}
              onClick={() => void submitReview(noteOpen.decision)}
              data-testid="report-audit-record-decision"
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

function AuditCard({
  artifact,
  canReview,
  busy,
  onApprove,
  onReject,
}: {
  artifact: DerivedArtifactOut;
  canReview: boolean;
  busy: boolean;
  onApprove: (artifact: DerivedArtifactOut) => void;
  onReject: (artifact: DerivedArtifactOut) => void;
}) {
  const payload = (artifact.payload ?? {}) as AuditPayload;
  const claims = payload.claims ?? [];
  const meta = artifactStatusMeta(artifact.status);
  const issues = (artifact.validation_errors ?? []) as Array<{ code?: string }>;
  const totalMatches = claims.reduce(
    (sum, claim) => sum + (claim.counter_evidence?.matches?.length ?? 0),
    0,
  );

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="report-audit-card">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <Badge tone="high">
          <ShieldAlert className="size-3" aria-hidden="true" /> unreviewed model output
        </Badge>
        <Badge tone="neutral">rules {payload.rules_version ?? "—"}</Badge>
        <span className="ml-auto font-mono text-[10px] text-dim">{shortId(artifact.id)}</span>
      </div>

      {payload.analysis_scope ? (
        <p className="mt-2 text-[11px] text-dim">{payload.analysis_scope}</p>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-1.5">
        <Badge tone="neutral">
          draft: {payload.draft_source?.type ?? "text"} · {String(payload.draft_chars ?? 0)} chars
        </Badge>
        <Badge tone="neutral">
          {String(payload.model?.claims_extracted ?? claims.length)} extracted
          {payload.model?.claims_truncated
            ? ` · ${String(payload.model.claims_truncated)} truncated by the claim cap`
            : ""}
        </Badge>
        <Badge tone="neutral">
          {String(payload.counter_evidence?.records_searched ?? 0)} records ·{" "}
          {String(totalMatches)} counter-evidence matches
        </Badge>
      </div>

      {issues.length ? (
        <div className="mt-2 rounded border border-medium/25 bg-medium/8 p-2 text-[11px] text-medium">
          Flagged for review:{" "}
          <span className="font-mono">{issues.map((issue) => issue.code).join(", ")}</span> — no
          finding here is trusted until a human reviews it.
        </div>
      ) : null}

      <div className="mt-3 space-y-1" data-testid="report-audit-claims">
        <p className="text-[11px] uppercase tracking-wider text-dim">
          Claim checks — deterministic validation first, model assessment second
        </p>
        {claims.length === 0 ? (
          <p className="text-xs text-dim">
            The model extracted no claims from this draft — nothing to review.
          </p>
        ) : (
          claims.map((claim, i) => (
            <div
              key={claim.claim_id ?? String(i)}
              className="rounded border border-border bg-surface-3 p-2"
              data-testid="report-audit-claim"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={SEVERITY_TONE[String(claim.severity)] ?? "neutral"}>
                  {claim.severity ?? "none"}
                </Badge>
                <span className="font-mono text-[11px] text-foreground/90">
                  {claimLabel(claim)}
                </span>
                <span className="text-[11px] text-dim">
                  {claim.category ?? "uncategorized"} · chars {String(claim.char_start ?? "—")}–
                  {String(claim.char_end ?? "—")}
                </span>
              </div>
              <p className="mt-1 break-words text-[11px] text-foreground/80">
                {claim.text ?? claim.extraction_problems?.join(", ") ?? "unusable claim"}
              </p>

              {claim.findings?.length ? (
                <div className="mt-1 space-y-0.5" data-testid="report-audit-claim-findings">
                  {claim.findings.map((finding, fi) => (
                    <div key={fi} className="flex flex-wrap items-center gap-1.5 text-[11px]">
                      <Badge tone={SEVERITY_TONE[String(finding.severity)] ?? "neutral"}>
                        {finding.severity ?? "info"}
                      </Badge>
                      <span className="font-mono text-foreground/90">{finding.code}</span>
                      {finding.detail ? (
                        <span className="break-all font-mono text-[10px] text-dim">
                          {JSON.stringify(finding.detail)}
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}

              {claim.assessment ? (
                <p className="mt-1 text-[11px] text-dim">
                  model assessment:{" "}
                  <span className="font-mono text-foreground/90">
                    {claim.assessment.assessment ?? "unknown"}
                  </span>{" "}
                  {claim.assessment.quotes_verified
                    ? "— all quoted spans verified verbatim in the sources"
                    : claim.assessment.unverified_quotes?.length
                      ? "— forged/absent quotes rejected:"
                      : "— no quote supplied for a judgement"}
                  {claim.assessment.unverified_quotes?.length
                    ? ` ${claim.assessment.unverified_quotes.join(" | ")}`
                    : ""}
                </p>
              ) : claim.assessment_skipped ? (
                <p className="mt-1 text-[11px] text-dim">
                  model assessment skipped: {claim.assessment_skipped}
                </p>
              ) : null}
            </div>
          ))
        )}
      </div>

      {canReview && artifact.status === "pending_review" ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => onApprove(artifact)}>
            Approve
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onReject(artifact)}>
            Reject
          </Button>
        </div>
      ) : null}
    </div>
  );
}
