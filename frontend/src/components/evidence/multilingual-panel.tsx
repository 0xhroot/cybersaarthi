import { useState } from "react";
import { Check, ClipboardList, FileText, Languages, Loader2, Pencil, Sparkles, X } from "lucide-react";

import {
  useArtifacts,
  useCancelIntelJob,
  useIntelJobs,
  useMultilingual,
  useReviewArtifact,
  useSourceRecords,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { AnalysisJobOut, DerivedArtifactOut, SourceRecordOut } from "@/types/domain";

/**
 * Multilingual complaint intelligence panel (feature 7).
 *
 * Contract: the original complaint text is always shown verbatim and clearly
 * separated from the generated translation — the two are never merged. The
 * model's language label is cross-checked against deterministic Unicode script
 * profiling (a disagreement is surfaced as a warning, never silently fixed),
 * ambiguity flags and validation errors are always shown, edited fields are
 * re-validated against the original text, and nothing is auto-approved.
 */

interface MultilingualPayload {
  multilingual?: boolean;
  language?: string;
  script_profile?: Record<string, unknown> & { candidate?: string };
  language_consistent?: boolean;
  fields?: Record<string, string[]>;
  ambiguity_flags?: Array<{ flag?: string; detail?: string }>;
  record_no?: number;
}

interface TranslationPayload {
  source_language?: string;
  translated_text?: string;
  material_check?: {
    material_total?: number;
    material_preserved?: number;
    material_missing?: string[];
    preserved?: boolean;
  };
  negation_preserved?: boolean;
  record_no?: number;
}

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

function issuesOf(artifact: DerivedArtifactOut): Array<{ field?: string; value?: string; code?: string; message?: string }> {
  return (artifact.validation_errors ?? []) as Array<{
    field?: string;
    value?: string;
    code?: string;
    message?: string;
  }>;
}

function RecordBlock({ record }: { record: SourceRecordOut }) {
  const text = typeof record.raw_data?.text === "string" ? (record.raw_data.text as string) : null;
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <div className="flex items-center gap-2">
        <FileText className="size-3.5 text-dim" />
        <p className="text-[11px] uppercase tracking-wider text-dim">
          Original record #{record.record_no} — verbatim source, never modified
        </p>
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground/90">
        {text ?? JSON.stringify(record.raw_data)}
      </p>
    </div>
  );
}

export function MultilingualPanel({ caseId, evidenceId }: { caseId: string; evidenceId: string }) {
  const canIngest = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const jobs = useIntelJobs(caseId, "multilingual");
  const extractions = useArtifacts(caseId, "extraction");
  const translations = useArtifacts(caseId, "translation");
  const records = useSourceRecords(caseId, evidenceId);
  const submit = useMultilingual(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);

  const [translate, setTranslate] = useState(false);
  const [noteOpen, setNoteOpen] = useState<{ artifact: DerivedArtifactOut; decision: "approved" | "rejected" } | null>(null);
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState<{ artifactId: string; values: Record<string, string[]> } | null>(null);

  const forEvidence = (artifact: DerivedArtifactOut) => artifact.evidence_file_id === evidenceId;
  const multilingualExtractions = (extractions.data?.items ?? []).filter(
    (a) => forEvidence(a) && (a.payload as MultilingualPayload).multilingual === true,
  );
  const translationArtifacts = (translations.data?.items ?? []).filter(forEvidence);
  const evidenceJobs = (jobs.data?.items ?? []).filter((j) => j.evidence_file_id === evidenceId);
  const activeJob = evidenceJobs.find((j) => j.status === "pending" || j.status === "running");
  const latest = evidenceJobs[0];

  const runAnalysis = async () => {
    try {
      const result = await submit.mutateAsync({ evidenceFileId: evidenceId, translate });
      toast({
        title: "Multilingual analysis queued",
        description: result.duplicate
          ? "Reusing the active analysis job."
          : "Script profiling runs deterministically; every value is checked against the original text.",
      });
    } catch (err) {
      toast({ title: "Analysis failed", description: (err as Error).message });
    }
  };

  const submitReview = async (decision: "approved" | "rejected") => {
    if (!noteOpen) return;
    try {
      await review.mutateAsync({ artifactId: noteOpen.artifact.id, review: { decision, note: note || null } });
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

  const submitEditedFields = async (artifact: DerivedArtifactOut) => {
    if (!editing || editing.artifactId !== artifact.id) return;
    try {
      await review.mutateAsync({
        artifactId: artifact.id,
        review: { decision: "approved", payload: { fields: editing.values } },
      });
      toast({ title: "Edit recorded", description: "Edited fields were re-validated against the original text." });
      setEditing(null);
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Edit rejected", description: (err as Error).message });
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

  const startEdit = (artifact: DerivedArtifactOut) => {
    const fields = ((artifact.payload as MultilingualPayload).fields ?? {}) as Record<string, string[]>;
    setEditing({ artifactId: artifact.id, values: structuredClone(fields) });
  };

  const latestAnalysis = multilingualExtractions[0];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wider text-dim">Multilingual complaint intelligence</p>
        {canIngest ? (
          <div className="flex items-center gap-3">
            <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-dim">
              <input
                type="checkbox"
                className="size-3 accent-accent"
                checked={translate}
                onChange={(e) => setTranslate(e.target.checked)}
              />
              Also translate to English
            </label>
            <Button size="sm" disabled={submit.isPending || Boolean(activeJob)} onClick={() => void runAnalysis()}>
              {submit.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Languages className="size-3.5" />}
              {activeJob ? "Analyzing…" : "Run analysis"}
            </Button>
          </div>
        ) : null}
      </div>

      {latest ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={jobTone(latest.status)}>{latest.status}</Badge>
          <span className="text-dim">
            {String((latest.result_summary as Record<string, unknown> | null)?.values_verified ?? "—")} values verified ·{" "}
            {String((latest.result_summary as Record<string, unknown> | null)?.translations_created ?? 0)} translations ·{" "}
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

      {records.isLoading ? (
        <Skeleton className="h-24" />
      ) : (records.data?.items ?? []).length === 0 ? (
        <EmptyState
          title="No parsed original text yet"
          description="The original complaint appears here after the file is ingested or analyzed. The source is shown verbatim — translations never replace it."
        />
      ) : (
        <div className="space-y-2">
          {(records.data?.items ?? []).map((record) => (
            <RecordBlock key={record.id} record={record} />
          ))}
        </div>
      )}

      {latestAnalysis ? (
        <AnalysisCard
          artifact={latestAnalysis}
          canReview={canReview}
          busy={review.isPending}
          editing={editing}
          onStartEdit={() => startEdit(latestAnalysis)}
          onCancelEdit={() => setEditing(null)}
          onEditChange={(field, raw) => {
            if (!editing) return;
            const values = raw
              .split(",")
              .map((v) => v.trim())
              .filter((v) => v.length > 0);
            setEditing({ ...editing, values: { ...editing.values, [field]: values } });
          }}
          onSubmitEdit={() => void submitEditedFields(latestAnalysis)}
          onApprove={(a) => {
            if (a.validation_status === "valid" && !editing) {
              void review.mutateAsync({ artifactId: a.id, review: { decision: "approved" } }).then(
                () => toast({ title: "Analysis approved", description: "The decision was recorded in the audit log." }),
                (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
              );
            } else {
              setNoteOpen({ artifact: a, decision: "approved" });
            }
          }}
          onReject={(a) => setNoteOpen({ artifact: a, decision: "rejected" })}
        />
      ) : extractions.isLoading ? (
        <Skeleton className="h-24" />
      ) : (
        <EmptyState
          title="No multilingual analysis yet"
          description="Run the analysis to profile the complaint's script, cross-check the language label and extract source-verified fields."
        />
      )}

      {translationArtifacts.length ? (
        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wider text-dim">Generated translations — not the original</p>
          {translationArtifacts.map((artifact) => {
            const payload = (artifact.payload ?? {}) as TranslationPayload;
            const material = payload.material_check ?? {};
            const issues = issuesOf(artifact);
            const meta = artifactStatusMeta(artifact.status);
            return (
              <div
                key={artifact.id}
                className="rounded-lg border border-accent/30 bg-accent/5 p-3"
                data-testid="translation-card"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={meta.tone}>{meta.label}</Badge>
                  <Badge tone="accent">machine translation · unreviewed</Badge>
                  <Badge tone="neutral">from {payload.source_language ?? "unknown"}</Badge>
                  <span className="ml-auto font-mono text-[10px] text-dim">{shortId(artifact.id)}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap break-words text-xs italic leading-relaxed text-foreground/85">
                  {payload.translated_text ?? "—"}
                </p>
                <div className="mt-2 space-y-1">
                  <p className="text-[11px] text-dim">
                    Material values: {material.material_preserved ?? 0}/{material.material_total ?? 0} preserved
                    {material.preserved === false ? " — translation is lossy, verify against the original" : ""}
                  </p>
                  {payload.negation_preserved === false ? (
                    <p className="text-[11px] text-high">Negation not preserved — meaning may be inverted.</p>
                  ) : null}
                </div>
                {issues.length ? (
                  <ul className="mt-2 space-y-1 rounded border border-high/25 bg-high/8 p-2">
                    {issues.map((issue, i) => (
                      <li key={i} className="text-[11px] text-high">
                        <span className="font-mono">{issue.code}</span>
                        {issue.value ? <span> — {issue.value}</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {artifact.status === "pending_review" && canReview ? (
                  <div className="mt-2 flex gap-2">
                    <Button
                      size="sm"
                      disabled={review.isPending}
                      onClick={() => {
                        if (artifact.validation_status === "valid") {
                          void review.mutateAsync({ artifactId: artifact.id, review: { decision: "approved" } }).then(
                            () => toast({ title: "Translation approved", description: "The decision was recorded in the audit log." }),
                            (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
                          );
                        } else {
                          setNoteOpen({ artifact, decision: "approved" });
                        }
                      }}
                    >
                      <Check className="size-3.5" /> Approve
                    </Button>
                    <Button size="sm" variant="danger" disabled={review.isPending} onClick={() => setNoteOpen({ artifact, decision: "rejected" })}>
                      <X className="size-3.5" /> Reject
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">
            {noteOpen.decision === "approved" ? "Record your approval note (optional)." : "Why is this rejected?"}
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

function AnalysisCard({
  artifact,
  canReview,
  busy,
  editing,
  onStartEdit,
  onCancelEdit,
  onEditChange,
  onSubmitEdit,
  onApprove,
  onReject,
}: {
  artifact: DerivedArtifactOut;
  canReview: boolean;
  busy: boolean;
  editing: { artifactId: string; values: Record<string, string[]> } | null;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onEditChange: (field: string, raw: string) => void;
  onSubmitEdit: () => void;
  onApprove: (artifact: DerivedArtifactOut) => void;
  onReject: (artifact: DerivedArtifactOut) => void;
}) {
  const payload = (artifact.payload ?? {}) as MultilingualPayload;
  const fields = payload.fields ?? {};
  const flags = payload.ambiguity_flags ?? [];
  const issues = issuesOf(artifact);
  const meta = artifactStatusMeta(artifact.status);
  const isEditing = editing?.artifactId === artifact.id;

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="analysis-card">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <Badge tone="accent">{payload.language ?? "unknown"} (model label)</Badge>
        <Badge tone="neutral">script: {payload.script_profile?.candidate ?? "unknown"}</Badge>
        <Badge tone={artifact.validation_status === "valid" ? "success" : "high"}>
          {artifact.validation_status === "valid" ? "validated" : `${issues.length} flagged`}
        </Badge>
        <span className="ml-auto font-mono text-[10px] text-dim">{shortId(artifact.id)}</span>
      </div>

      {payload.language_consistent === false ? (
        <div className="mt-2 rounded border border-high/25 bg-high/8 p-2 text-[11px] text-high">
          Language label disagrees with the deterministic script evidence — both values are preserved for manual review.
        </div>
      ) : null}

      {flags.length ? (
        <ul className="mt-2 space-y-1 rounded border border-border bg-surface-3 p-2">
          {flags.map((flag, i) => (
            <li key={i} className="text-[11px] text-amber-300/90">
              <span className="font-mono">{flag.flag}</span>
              {flag.detail ? <span> — {flag.detail}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-2 space-y-1.5">
        {Object.entries(fields).map(([field, values]) =>
          isEditing ? (
            <label key={field} className="block text-xs">
              <span className="text-dim">{field}</span>
              <input
                className="mt-0.5 w-full rounded border border-border bg-surface-3 p-1.5 font-mono text-xs text-foreground outline-none focus:border-accent/40"
                value={(editing?.values[field] ?? []).join(", ")}
                onChange={(e) => onEditChange(field, e.target.value)}
              />
            </label>
          ) : values.length ? (
            <p key={field} className="text-xs">
              <span className="text-dim">{field}: </span>
              <span className="text-foreground/85">{values.join("; ")}</span>
            </p>
          ) : null,
        )}
      </div>

      {issues.length ? (
        <ul className="mt-2 space-y-1 rounded border border-high/25 bg-high/8 p-2">
          {issues.map((issue, i) => (
            <li key={i} className="text-[11px] text-high">
              <span className="font-mono">{issue.field}</span>
              {issue.code ? <span className="font-mono"> · {issue.code}</span> : null}
              {issue.value ? <span> — {issue.value}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {artifact.status === "pending_review" && canReview ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {isEditing ? (
            <>
              <Button size="sm" disabled={busy} onClick={onSubmitEdit}>
                <Check className="size-3.5" /> Re-validate & approve
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                Cancel edit
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" disabled={busy} onClick={() => onApprove(artifact)}>
                <Check className="size-3.5" /> Approve
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={onStartEdit}>
                <Pencil className="size-3.5" /> Edit fields
              </Button>
              <Button size="sm" variant="danger" disabled={busy} onClick={() => onReject(artifact)}>
                <X className="size-3.5" /> Reject
              </Button>
            </>
          )}
        </div>
      ) : null}
      {isEditing ? (
        <p className="mt-2 text-[11px] text-dim">
          <Sparkles className="mr-1 inline size-3" />
          Edited values are re-validated against the original text before approval; a value not present in the source is refused.
        </p>
      ) : null}
    </div>
  );
}
