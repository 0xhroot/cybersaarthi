import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Network, Search } from "lucide-react";

import {
  useCancelIntelJob,
  useCases,
  useCrossCaseCandidates,
  useExplainFinding,
  useIntelJobs,
  useReviewArtifact,
  useSubmitCrossCase,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type {
  AnalysisJobOut,
  Case,
  CrossCaseCandidatePayload,
  CrossCaseSide,
  CustodyExplainResponse,
  DerivedArtifactOut,
} from "@/types/domain";

/**
 * Cross-case intelligence panel (phase 4, feature B).
 *
 * Contract: every candidate on this panel is a *discovery signal* produced by
 * deterministic, permission-scoped extraction over the explicit scope — never
 * proof of a shared incident, never a canonical relationship. The score is an
 * additive 0–100 band and is always rendered together with its "NOT a
 * probability" semantics; a `similarity_name_only` candidate is informational
 * and cannot be approved. Approval records a reviewed relationship as an
 * artifact + audit entry (it never merges entities and never writes to the
 * graph). AI narration is on-demand, flagged `ai_unverified`, and its
 * citations were validated against the candidate's own provenance before it
 * could be stored. Candidates touching a case the caller cannot read are
 * omitted server-side — this panel renders only what it is given, and it never
 * shows names, ids, counts or badges for inaccessible cases.
 */

const SCOPE_MIN = 2;
const SCOPE_MAX = 25;

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

function payloadOf(artifact: DerivedArtifactOut): CrossCaseCandidatePayload {
  return artifact.payload as CrossCaseCandidatePayload;
}

function caseLabel(cases: Case[] | undefined, caseId: string): string {
  const match = cases?.find((c) => c.id === caseId);
  return match ? `${match.case_number} · ${match.title}` : shortId(caseId);
}

/* -------------------------------- side card -------------------------------- */

function SideRow({ side, cases }: { side: CrossCaseSide; cases?: Case[] }) {
  const records = side.source_record_ids ?? [];
  const files = side.evidence_file_ids ?? [];
  return (
    <div className="rounded border border-border bg-surface-3 p-2" data-testid="cross-case-side">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          className="font-mono text-[11px] text-accent underline-offset-2 hover:underline"
          to={`/app/cases/${side.case_id}/evidence`}
          aria-label={`Open evidence for case ${side.case_id}`}
        >
          {caseLabel(cases, side.case_id)}
        </Link>
        {side.reviewed_alias ? <Badge tone="info">reviewed alias</Badge> : null}
      </div>
      <p className="mt-1 font-mono text-[11px] text-foreground/85">
        {(side.value_originals ?? []).join(", ") || "—"}
      </p>
      <p className="mt-0.5 text-[10px] text-dim">
        contributing kinds: {(side.contributing_kinds ?? []).join(", ") || "—"}
      </p>
      {records.length || files.length ? (
        <p className="mt-0.5 font-mono text-[10px] leading-relaxed text-dim">
          records: {records.slice(0, 4).join(", ") || "—"}
          {records.length > 4 ? ` (+${records.length - 4} more)` : ""}
          {files.length ? ` · files: ${files.slice(0, 2).join(", ")}` : ""}
          {side.supporting_ids_capped ? " (capped)" : ""}
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------ candidate card ------------------------------ */

function CandidateCard({
  artifact,
  cases,
  canReview,
  explaining,
  explainError,
  onExplain,
  explanation,
  onReview,
}: {
  artifact: DerivedArtifactOut;
  cases?: Case[];
  canReview: boolean;
  explaining: boolean;
  explainError: unknown;
  onExplain: () => void;
  explanation: CustodyExplainResponse | null;
  onReview: (artifact: DerivedArtifactOut, decision: "approved" | "rejected") => void;
}) {
  const payload = payloadOf(artifact);
  const reviewable = payload.reviewable !== false;
  const conflicts = payload.conflicting_attributes;
  const isPending = artifact.status === "pending_review";

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="cross-case-candidate">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">{payload.group?.indicator_kind ?? "unknown indicator"}</Badge>
        <span className="font-mono text-[11px] text-foreground">{payload.group?.value_normalized ?? "—"}</span>
        <Badge tone="info">{(payload.classification ?? "unknown").replace(/_/g, " ")}</Badge>
        {artifact.status !== "pending_review" ? (
          <Badge tone={artifact.status === "approved" ? "success" : artifact.status === "rejected" ? "critical" : "neutral"}>
            {artifact.status === "approved" ? "reviewed link" : artifact.status}
          </Badge>
        ) : null}
        {!reviewable ? <Badge tone="neutral">informational only</Badge> : null}
        <span className="ml-auto font-mono text-[10px] text-dim">
          score {payload.score ?? "—"} / 100 · {payload.crosscase_rules_version}
        </span>
      </div>

      {/* Score semantics: the band is never presented as a probability. */}
      <p className="mt-1 text-[10px] leading-relaxed text-dim">{payload.score_semantics}</p>
      {payload.classification_semantics?.[payload.classification ?? ""] ? (
        <p className="mt-0.5 text-[11px] leading-relaxed text-foreground/80">
          {payload.classification_semantics[payload.classification ?? ""]}
        </p>
      ) : null}

      {/* Sides: only cases this caller may read ever reach this panel. */}
      <div className="mt-2 grid gap-2">
        {(payload.sides ?? []).map((side) => (
          <SideRow key={side.case_id} side={side} cases={cases} />
        ))}
      </div>

      {conflicts?.flagged ? (
        <div className="mt-2 rounded border border-low/40 bg-low/5 p-2" data-testid="cross-case-conflict">
          <p className="text-[11px] font-medium text-low">Conflicting attributes across the cases</p>
          {(conflicts.evidence ?? []).map((conflict, index) => (
            <p key={index} className="mt-0.5 font-mono text-[10px] text-dim">
              {String(conflict.kind ?? "attribute")}:{" "}
              {Object.entries((conflict.per_case_values as Record<string, string[]>) ?? {})
                .map(([caseId, values]) => `${shortId(caseId)} → ${values.join(", ")}`)
                .join(" · ")}
            </p>
          ))}
        </div>
      ) : null}

      {payload.additional_shared_kinds?.length ? (
        <p className="mt-1.5 text-[11px] text-dim">
          also shared: {payload.additional_shared_kinds.join(", ")}
        </p>
      ) : null}

      {!reviewable && payload.review_disabled_reason ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-low">{payload.review_disabled_reason}</p>
      ) : null}

      {artifact.reviewed_at ? (
        <p className="mt-1.5 text-[10px] uppercase tracking-wider text-dim">
          {artifact.status} · {formatRelative(artifact.reviewed_at)}
          {artifact.review_note ? ` — ${artifact.review_note}` : ""}
        </p>
      ) : null}

      {/* Actions: review is a decision on this artifact, never a merge. */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {isPending && canReview && reviewable ? (
          <>
            <Button
              size="sm"
              disabled={explaining}
              aria-label="Approve cross-case link"
              onClick={() => onReview(artifact, "approved")}
            >
              Approve link
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={explaining}
              aria-label="Reject cross-case link"
              onClick={() => onReview(artifact, "rejected")}
            >
              Reject
            </Button>
          </>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          disabled={explaining}
          aria-label="Explain cross-case candidate"
          onClick={onExplain}
        >
          {explaining ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />} Explain
        </Button>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-dim">
          candidate · reviewed relationships are recorded, never merged
        </span>
      </div>

      {explainError ? (
        <div className="mt-2 rounded border border-border bg-surface-3 p-2">
          <ErrorState error={explainError} onRetry={onExplain} />
        </div>
      ) : null}

      {explanation ? <ExplanationBlock response={explanation} /> : null}
    </div>
  );
}

/* ------------------------------ explanation block ---------------------------- */

function ExplanationBlock({ response }: { response: CustodyExplainResponse }) {
  const explanation = response.explanation;
  return (
    <div className="mt-2 rounded border border-accent/30 bg-accent/5 p-2" data-testid="cross-case-explanation">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">AI narration · unverified</Badge>
        <span className="text-[10px] uppercase tracking-wider text-dim">
          citations validated against this candidate's provenance
        </span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/85">
        {explanation && "summary" in explanation
          ? explanation.summary
          : response.text}
      </p>
      {explanation && "matching_signal" in explanation ? (
        <p className="mt-1 text-[11px] leading-relaxed text-dim">
          signal: {explanation.matching_signal}
        </p>
      ) : null}
      {explanation && "cited_identifiers" in explanation && explanation.cited_identifiers.length ? (
        <p className="mt-1 font-mono text-[10px] text-dim">
          cited: {explanation.cited_identifiers.join(", ")}
        </p>
      ) : null}
      {explanation && "not_established" in explanation ? (
        <ul className="mt-1.5 list-inside list-disc space-y-0.5">
          {explanation.not_established.map((item) => (
            <li key={item} className="text-[11px] leading-relaxed text-dim">
              does not establish: {item}
            </li>
          ))}
        </ul>
      ) : null}
      {explanation && "verification_steps" in explanation ? (
        <ul className="mt-1.5 list-inside list-disc space-y-0.5">
          {explanation.verification_steps.map((item) => (
            <li key={item} className="text-[11px] leading-relaxed text-dim">
              next check: {item}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* -------------------------------- main panel -------------------------------- */

export function CrossCasePanel({ caseId }: { caseId: string }) {
  const canCrossCase = useCan("crosscase.read");
  const canReview = useCan("findings.review");
  const cases = useCases({ limit: 100 });
  const jobs = useIntelJobs(caseId, "cross_case");
  const candidates = useCrossCaseCandidates(caseId);
  const submit = useSubmitCrossCase(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);
  const explain = useExplainFinding(caseId);

  const [selected, setSelected] = useState<string[]>([caseId]);
  const [explanations, setExplanations] = useState<Record<string, CustodyExplainResponse>>({});

  const caseItems = useMemo(() => cases.data?.items ?? [], [cases.data]);
  const latestJob = (jobs.data?.items ?? [])[0];
  const activeJob = (jobs.data?.items ?? []).find(
    (job) => job.status === "pending" || job.status === "running",
  );
  const summary = (latestJob?.result_summary ?? {}) as Record<string, unknown>;
  const items = useMemo(() => candidates.data?.items ?? [], [candidates.data]);

  const toggleCase = (id: string) => {
    setSelected((current) => {
      if (id === caseId) return current; // the anchor case is always in scope
      return current.includes(id)
        ? current.filter((c) => c !== id)
        : current.length >= SCOPE_MAX
          ? current
          : [...current, id];
    });
  };

  const runDiscovery = async () => {
    if (selected.length < SCOPE_MIN) {
      toast({ title: "Scope too small", description: `Pick at least ${SCOPE_MIN} permitted cases including this one.` });
      return;
    }
    try {
      const result = await submit.mutateAsync([...new Set([caseId, ...selected])]);
      toast({
        title: "Cross-case discovery queued",
        description: result.duplicate
          ? "Reusing the active discovery job."
          : `Scanning ${selected.length} authorized cases for shared identifiers. Discovery never reads the whole graph.`,
      });
    } catch (err) {
      toast({ title: "Cross-case discovery failed", description: (err as Error).message });
    }
  };

  const cancelJob = async (jobId: string) => {
    try {
      await cancel.mutateAsync(jobId);
      toast({ title: "Cancellation requested", description: "The job ends as canceled once the runner observes the flag." });
    } catch (err) {
      toast({ title: "Cancel failed", description: (err as Error).message });
    }
  };

  const runReview = async (artifact: DerivedArtifactOut, decision: "approved" | "rejected") => {
    try {
      await review.mutateAsync({ artifactId: artifact.id, review: { decision } });
      toast({
        title: decision === "approved" ? "Relationship reviewed" : "Candidate rejected",
        description:
          decision === "approved"
            ? "Recorded as a reviewed cross-case relationship — no entities were merged and the graph was not written."
            : "The candidate was dismissed and recorded in the audit log.",
      });
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
    }
  };

  const runExplain = (artifact: DerivedArtifactOut) => {
    explain.mutate(artifact.id, {
      onSuccess: (response) => setExplanations((current) => ({ ...current, [artifact.id]: response })),
    });
  };

  if (!canCrossCase) return null;

  return (
    <div className="space-y-3" data-testid="cross-case-panel">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">Cross-case intelligence</p>
        <Button
          size="sm"
          disabled={submit.isPending || Boolean(activeJob) || selected.length < SCOPE_MIN}
          onClick={() => void runDiscovery()}
          aria-label="Run cross-case discovery"
        >
          {submit.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Network className="size-3.5" />}
          {activeJob ? "Discovering…" : "Run discovery"}
        </Button>
      </div>

      {/* Scope: explicit and bounded — never "every case I can see". */}
      <section className="rounded border border-border bg-surface-3 p-2" data-testid="cross-case-scope">
        <p className="text-[10px] uppercase tracking-wider text-dim">
          Discovery scope — explicit and bounded ({selected.length} of {SCOPE_MAX}, at least {SCOPE_MIN})
        </p>
        {cases.isLoading ? (
          <Skeleton className="mt-2 h-16" />
        ) : (
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
            {caseItems.map((caze) => {
              const isAnchor = caze.id === caseId;
              const checked = isAnchor || selected.includes(caze.id);
              return (
                <label key={caze.id} className="flex items-center gap-1.5 text-[11px] text-foreground/85">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={isAnchor || (!checked && selected.length >= SCOPE_MAX)}
                    onChange={() => toggleCase(caze.id)}
                    aria-label={`Include case ${caze.case_number}`}
                  />
                  <span className={isAnchor ? "font-medium" : undefined}>
                    {caze.case_number}
                    {isAnchor ? " (this case)" : ""}
                  </span>
                </label>
              );
            })}
          </div>
        )}
        <p className="mt-1.5 text-[10px] leading-relaxed text-dim">
          Only cases you may read are listed; discovery reads their authorized records directly and does not query or
          depend on the Neo4j projection. A scope that is no longer fully authorized fails closed.
        </p>
      </section>

      {latestJob ? (
        <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="cross-case-summary">
          <Badge tone={jobTone(latestJob.status)}>{latestJob.status}</Badge>
          <span className="text-dim">
            {String(summary.cases_scanned ?? "—")} cases · {String(summary.candidates_found ?? "—")} candidates ·{" "}
            {String(summary.candidates_pending_review ?? "—")} pending review ·{" "}
            {String(summary.cases_inaccessible ?? 0)} inaccessible (scope enforced) ·{" "}
            {formatRelative(latestJob.updated_at)}
          </span>
          {activeJob ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)} aria-label="Cancel discovery">
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}

      {jobs.error ? (
        <div className="rounded-lg border border-border bg-surface-2 p-2">
          <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />
        </div>
      ) : null}

      {candidates.isLoading ? (
        <Skeleton className="h-24" />
      ) : candidates.error ? (
        <div className="rounded-lg border border-border bg-surface-2 p-2">
          <ErrorState error={candidates.error} onRetry={() => void candidates.refetch()} />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No cross-case candidates"
          description="Run a bounded discovery over an explicit scope of cases you may read. Deterministic extraction groups shared identifiers across those cases; every candidate stays a review candidate until a human approves it — nothing is linked automatically, and no graph is written."
        />
      ) : (
        <div className="space-y-2">
          {items.map((artifact) => (
            <CandidateCard
              key={artifact.id}
              artifact={artifact}
              cases={caseItems}
              canReview={canReview}
              explaining={explain.isPending}
              explainError={explain.error}
              onExplain={() => runExplain(artifact)}
              explanation={explanations[artifact.id] ?? null}
              onReview={(art, decision) => void runReview(art, decision)}
            />
          ))}
        </div>
      )}

      {candidates.data?.graph_freshness_note || candidates.data?.crosscase_rules_version ? (
        <p className="text-[10px] leading-relaxed text-dim" data-testid="cross-case-graph-note">
          {candidates.data?.graph_freshness_note} · rules {candidates.data?.crosscase_rules_version}
        </p>
      ) : null}
    </div>
  );
}
