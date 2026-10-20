import { useState } from "react";
import { Check, ClipboardList, Fingerprint, Loader2, X } from "lucide-react";

import {
  useArtifacts,
  useCancelIntelJob,
  useIntelJobs,
  useReviewArtifact,
  useTriage,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { KeyValueList } from "@/components/ui/key-value";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { AnalysisJobOut, DerivedArtifactOut } from "@/types/domain";

/**
 * Digital forensics triage panel (feature 8).
 *
 * Contract: observations are deterministic structural facts (rule id,
 * severity, record locator) and are presented as observations — never as
 * verdicts. The model's explanation is labelled unreviewed, shown only
 * alongside the recorded observations it describes, and a failed explanation
 * never hides the deterministic results. Nothing is auto-approved; approval
 * and rejection are human decisions recorded in the audit log.
 */

interface TriageObservation {
  rule?: string;
  severity?: string;
  locator?: { record_no?: number; field?: string };
  detail?: Record<string, unknown>;
}

interface TriageManifestRow {
  record_no?: number;
  sha256?: string;
  filename?: string | null;
  verdict?: string;
  computed_sha256?: string | null;
}

interface TriagePayload {
  triage?: boolean;
  format_profile?: Record<string, number | boolean>;
  observations?: TriageObservation[];
  missing_information?: string[];
  fields?: {
    urls?: Array<Record<string, unknown>>;
    email_headers?: Array<{ record_no?: number; headers?: Record<string, string[]> }>;
    auth_results?: Array<Record<string, unknown>>;
    manifest?: TriageManifestRow[] | null;
    history?: { visits_total?: number; domains?: number } | null;
    logs?: { severity_counts?: Record<string, number>; auth_failure_lines?: number } | null;
  } | null;
  explanation?: {
    summary?: string;
    explanations?: string[];
    not_established?: string[];
    verification_steps?: string[];
  } | null;
  explanation_failed?: boolean;
  explanation_error?: string | null;
  analysis_scope?: string;
  rules_version?: string;
}

const SEVERITY_ORDER = ["high", "medium", "low", "info"];
const SEVERITY_TONE: Record<string, "high" | "medium" | "low" | "info"> = {
  high: "high",
  medium: "medium",
  low: "low",
  info: "info",
};

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
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

function issuesOf(
  artifact: DerivedArtifactOut,
): Array<{ field?: string; value?: string; code?: string; message?: string }> {
  return (artifact.validation_errors ?? []) as Array<{
    field?: string;
    value?: string;
    code?: string;
    message?: string;
  }>;
}

export function TriagePanel({ caseId, evidenceId }: { caseId: string; evidenceId: string }) {
  const canIngest = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const jobs = useIntelJobs(caseId, "triage");
  const triageArtifacts = useArtifacts(caseId, "triage_observation");
  const submit = useTriage(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [noteOpen, setNoteOpen] = useState<{
    artifact: DerivedArtifactOut;
    decision: "approved" | "rejected";
  } | null>(null);
  const [note, setNote] = useState("");

  const evidenceJobs = (jobs.data?.items ?? []).filter((j) => j.evidence_file_id === evidenceId);
  const activeJob = evidenceJobs.find((j) => j.status === "pending" || j.status === "running");
  const latest = evidenceJobs[0];
  const artifacts = (triageArtifacts.data?.items ?? []).filter(
    (a) => a.evidence_file_id === evidenceId,
  );
  const latestArtifact = artifacts[0];

  const runTriage = async () => {
    try {
      const result = await submit.mutateAsync(evidenceId);
      toast({
        title: "Triage queued",
        description: result.duplicate
          ? "Reusing the active triage job."
          : "Deterministic parsing runs first; the model only explains the recorded observations.",
      });
    } catch (err) {
      toast({ title: "Triage failed", description: (err as Error).message });
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

  const approveDirect = (artifact: DerivedArtifactOut) => {
    void review.mutateAsync({ artifactId: artifact.id, review: { decision: "approved" } }).then(
      () =>
        toast({
          title: "Triage observations approved",
          description: "The decision was recorded in the audit log.",
        }),
      (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
    );
  };

  const summary = (latest?.result_summary ?? null) as Record<string, unknown> | null;

  return (
    <div className="space-y-3" data-testid="triage-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wider text-dim">Digital forensics triage</p>
        {canIngest ? (
          <Button
            size="sm"
            disabled={submit.isPending || Boolean(activeJob)}
            onClick={() => void runTriage()}
          >
            {submit.isPending || activeJob ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Fingerprint className="size-3.5" />
            )}
            {activeJob ? "Triaging…" : "Run triage"}
          </Button>
        ) : null}
      </div>

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          <span className="text-dim">
            {String(summary?.observations_total ?? 0)} observations ·{" "}
            {String(summary?.manifest_entries_verified ?? 0)} manifest hashes verified ·{" "}
            {formatRelative(latest.updated_at)}
          </span>
          {activeJob && canIngest ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)}>
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}
      {latest?.status === "failed" && latest.error ? (
        <div className="rounded border border-high/25 bg-high/8 p-2 text-[11px] text-high">
          Run refused: <span className="font-mono">{latest.error}</span>
        </div>
      ) : null}
      {latest?.status === "partial" && latest.error ? (
        <div className="rounded border border-medium/25 bg-medium/8 p-2 text-[11px] text-medium">
          Partial run: <span className="font-mono">{latest.error}</span> — recorded observations
          below are unchanged.
        </div>
      ) : null}

      {latestArtifact ? (
        <TriageCard
          artifact={latestArtifact}
          canReview={canReview}
          busy={review.isPending}
          onApprove={(artifact) => {
            if (artifact.validation_status === "valid") {
              approveDirect(artifact);
            } else {
              setNoteOpen({ artifact, decision: "approved" });
            }
          }}
          onReject={(artifact) => setNoteOpen({ artifact, decision: "rejected" })}
        />
      ) : triageArtifacts.isLoading || jobs.isLoading ? (
        <Skeleton className="h-24" />
      ) : (
        <EmptyState
          title="No triage observations yet"
          description="Run the triage to parse headers, URLs, history, hash manifests and logs into deterministic, record-located observations for review."
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
          />
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              disabled={review.isPending || (noteOpen.decision === "rejected" && !note.trim())}
              onClick={() => void submitReview(noteOpen.decision)}
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

function TriageCard({
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
  const payload = (artifact.payload ?? {}) as TriagePayload;
  const profile = payload.format_profile ?? {};
  const observations = [...(payload.observations ?? [])].sort(
    (a, b) =>
      SEVERITY_ORDER.indexOf(String(a.severity)) - SEVERITY_ORDER.indexOf(String(b.severity)),
  );
  const fields = payload.fields ?? {};
  const urls = fields.urls ?? [];
  const manifest = fields.manifest ?? [];
  const missing = payload.missing_information ?? [];
  const explanation = payload.explanation;
  const issues = issuesOf(artifact);
  const meta = artifactStatusMeta(artifact.status);

  const profileEntries: Array<[string, unknown]> = [
    ["records scanned", profile.records_scanned],
    ["urls", profile.urls_found],
    ["manifest entries", profile.manifest_entries],
    ["log lines", profile.log_lines],
    ["e-mail headers", profile.email_header_records],
    ["history rows", profile.history_rows],
  ];
  const chips = profileEntries.filter(([, value]) => typeof value === "number" && value > 0);

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="triage-card">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <Badge tone={artifact.validation_status === "valid" ? "success" : "high"}>
          {artifact.validation_status === "valid" ? "validated" : `${issues.length} flagged`}
        </Badge>
        <Badge tone="neutral">rules {payload.rules_version ?? "—"}</Badge>
        <span className="ml-auto font-mono text-[10px] text-dim">{shortId(artifact.id)}</span>
      </div>

      {payload.analysis_scope ? (
        <p className="mt-2 text-[11px] text-dim">{payload.analysis_scope}</p>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-1.5">
        {chips.map(([label, value]) => (
          <Badge key={label} tone="neutral">
            {label}: {String(value)}
          </Badge>
        ))}
        {profile.observations_truncated ? (
          <Badge tone="medium">observation cap reached — bounded run</Badge>
        ) : null}
      </div>

      <div className="mt-3 space-y-1" data-testid="triage-observations">
        <p className="text-[11px] uppercase tracking-wider text-dim">
          Deterministic observations — facts, not verdicts
        </p>
        {observations.length === 0 ? (
          <p className="text-xs text-dim">No structural rules fired for this evidence.</p>
        ) : (
          observations.map((obs, i) => (
            <div
              key={i}
              className="flex flex-wrap items-start gap-2 rounded border border-border bg-surface-3 p-2"
              data-testid="triage-observation"
            >
              <Badge tone={SEVERITY_TONE[String(obs.severity)] ?? "neutral"}>
                {obs.severity ?? "unknown"}
              </Badge>
              <span className="font-mono text-[11px] text-foreground/90">
                {obs.rule ?? "unknown_rule"}
              </span>
              <span className="text-[11px] text-dim">record #{obs.locator?.record_no ?? "—"}</span>
              {obs.detail ? <KeyValueList data={obs.detail} className="w-full" /> : null}
            </div>
          ))
        )}
      </div>

      {urls.length ? (
        <div className="mt-3 space-y-1">
          <p className="text-[11px] uppercase tracking-wider text-dim">
            Structurally analyzed URLs
          </p>
          {urls.slice(0, 20).map((url, i) => {
            const flags = [
              url.userinfo ? "userinfo" : null,
              url.ip_host ? "raw-ip host" : null,
              url.punycode ? "punycode" : null,
              url.nonstandard_port ? `port ${String(url.port)}` : null,
            ].filter(Boolean);
            return (
              <p
                key={i}
                className="break-all font-mono text-[10px] leading-relaxed text-foreground/80"
              >
                {String(url.url ?? "—")}
                {flags.length ? <span className="text-dim"> — {flags.join(", ")}</span> : null}
              </p>
            );
          })}
        </div>
      ) : null}

      {manifest.length ? (
        <div className="mt-3 space-y-1">
          <p className="text-[11px] uppercase tracking-wider text-dim">
            Hash manifest — recomputed from stored bytes
          </p>
          {manifest.map((row, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 text-[11px]">
              <Badge
                tone={
                  row.verdict === "match"
                    ? "success"
                    : row.verdict === "mismatch"
                      ? "high"
                      : "medium"
                }
              >
                {row.verdict ?? "unknown"}
              </Badge>
              <span className="font-mono text-foreground/85">
                {row.filename ?? "(no filename)"}
              </span>
              <span className="font-mono text-[10px] text-dim">
                expected {String(row.sha256 ?? "").slice(0, 16)}… · computed{" "}
                {row.computed_sha256 ? `${row.computed_sha256.slice(0, 16)}…` : "—"}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {fields.logs ? (
        <p className="mt-3 text-[11px] text-dim">
          Log severities:{" "}
          {Object.entries(fields.logs.severity_counts ?? {})
            .map(([k, v]) => `${k} ${v}`)
            .join(", ") || "—"}
          {typeof fields.logs.auth_failure_lines === "number"
            ? ` · ${fields.logs.auth_failure_lines} auth-failure lines`
            : ""}
        </p>
      ) : null}
      {fields.history ? (
        <p className="mt-1 text-[11px] text-dim">
          Browser history: {String(fields.history.visits_total ?? 0)} visits across{" "}
          {String(fields.history.domains ?? 0)} domains
        </p>
      ) : null}

      {missing.length ? (
        <div className="mt-3">
          <p className="text-[11px] uppercase tracking-wider text-dim">Missing information</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-[11px] text-dim">
            {missing.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {payload.explanation_failed ? (
        <div className="mt-3 rounded border border-medium/25 bg-medium/8 p-2 text-[11px] text-medium">
          Model explanation was not recorded ({payload.explanation_error ?? "unknown failure"}). The
          deterministic observations above are unaffected.
        </div>
      ) : explanation ? (
        <div
          className="mt-3 rounded border border-accent/30 bg-accent/5 p-3"
          data-testid="triage-explanation"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="accent">AI interpretation · unreviewed</Badge>
            <span className="text-[10px] text-dim">
              explains the recorded observations above — adds no indicators
            </span>
          </div>
          <p className="mt-2 text-xs text-foreground/90">{explanation.summary ?? "—"}</p>
          {explanation.explanations?.length ? (
            <ul className="mt-2 list-inside list-disc space-y-0.5 text-[11px] text-foreground/80">
              {explanation.explanations.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : null}
          {explanation.not_established?.length ? (
            <p className="mt-2 text-[11px] text-dim">
              Not established: {explanation.not_established.join(" · ")}
            </p>
          ) : null}
          {explanation.verification_steps?.length ? (
            <div className="mt-2">
              <p className="text-[11px] uppercase tracking-wider text-dim">
                Suggested verification steps
              </p>
              <ol className="mt-1 list-inside list-decimal space-y-0.5 text-[11px] text-foreground/80">
                {explanation.verification_steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : null}

      {issues.length ? (
        <ul className="mt-3 space-y-1 rounded border border-high/25 bg-high/8 p-2">
          {issues.map((issue, i) => (
            <li key={i} className="text-[11px] text-high">
              <span className="font-mono">{issue.code ?? issue.field}</span>
              {issue.message ? <span> — {issue.message}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {artifact.status === "pending_review" && canReview ? (
        <div className="mt-3 flex flex-wrap gap-2">
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
