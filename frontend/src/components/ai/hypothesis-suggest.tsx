import { useCallback, useRef, useState } from "react";
import { AlertTriangle, Loader2, Sparkles, Square } from "lucide-react";

import { api } from "@/api";
import type { AiHypothesisDraft, AiSource } from "@/api/contract";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * AI hypothesis suggestion tray for the Hypotheses page.
 *
 * Honest-semantics contract (pinned by tests):
 * - Suggestions are *drafts for human review only*. The backend never stores
 *   them, never confirms them, and computes no numeric confidence — the UI
 *   must not display one either. A draft becomes a stored hypothesis only
 *   when the investigator clicks Record, edits it in the normal form, and
 *   submits through the existing hypothesis API (status starts at
 *   "proposed" and can never become a finding from here).
 * - Every cited record id is verified server-side against the retrieved,
 *   authorized data; unverifiable ids are listed per draft as "unverified"
 *   instead of being silently trusted.
 * - Blocks the server could not parse are reported as an error count — a
 *   partial tray is always labelled partial, with the raw model output
 *   available for inspection.
 */

const SUGGEST_QUESTION =
  "Propose up to three falsifiable candidate hypotheses from the records in this case. " +
  "For each, cite the supporting record ids, name the check that would refute it, and " +
  "list the records missing to test it.";

const PHASE_LABEL: Record<string, string> = {
  retrieving: "Retrieving authorized records…",
  synthesizing: "Drafting candidates…",
};

export interface HypothesisSuggestProps {
  caseId: string;
  /** Only reviewers may record; suggestions are still viewable by all. */
  canRecord: boolean;
  /** Called when the investigator chooses to record a draft (pre-fills the
   * editable create form — nothing is written until they submit it). */
  onRecord?: (draft: AiHypothesisDraft) => void;
}

export function HypothesisSuggest({ caseId, canRecord, onRecord }: HypothesisSuggestProps) {
  const [drafts, setDrafts] = useState<AiHypothesisDraft[]>([]);
  const [draftErrors, setDraftErrors] = useState(0);
  const [raw, setRaw] = useState("");
  const [sources, setSources] = useState<AiSource[]>([]);
  const [grounded, setGrounded] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setPhase(null);
  }, []);

  const suggest = useCallback(async () => {
    if (busy) return;
    // Reset first: a previous tray must never masquerade as this run's output.
    setBusy(true);
    setError(null);
    setDrafts([]);
    setDraftErrors(0);
    setRaw("");
    setSources([]);
    setGrounded(null);
    setPhase(PHASE_LABEL.retrieving);

    const controller = new AbortController();
    abortRef.current = controller;
    let streamed = "";

    try {
      await api.ai.chatStream(
        // `think` budget: drafting falsifiable candidates with citations needs
        // the larger generation allowance; grounding/tool rules stay identical.
        { question: SUGGEST_QUESTION, mode: "hypothesize", case_id: caseId, profile: "think" },
        {
          onProgress: (info) => setPhase(PHASE_LABEL[info.phase] ?? `${info.phase}…`),
          onToken: (text) => {
            streamed += text;
            setPhase(null);
          },
          onSources: (next) => setSources(next),
          onError: (message) => {
            setError(message);
            setDrafts([]);
            setDraftErrors(0);
            setRaw("");
            setSources([]);
            setGrounded(null);
          },
          onDone: (info) => {
            setRaw(streamed || info.answer || "");
            setDrafts(info.hypothesis_drafts ?? []);
            setDraftErrors(info.hypothesis_draft_errors ?? 0);
            setSources(info.sources);
            setGrounded(info.grounded);
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "The suggestion request failed.");
      setDrafts([]);
      setDraftErrors(0);
      setRaw("");
      setSources([]);
      setGrounded(null);
    } finally {
      abortRef.current = null;
      setBusy(false);
      setPhase(null);
    }
  }, [busy, caseId]);

  const hasRun = raw !== "" || drafts.length > 0 || draftErrors > 0 || error !== null;

  return (
    <div className="mt-6" data-testid="hypothesis-suggest">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-foreground">AI-drafted candidates</h2>
          <p className="text-[11px] text-dim">
            Unverified prompts for investigation — not conclusions. No probability is computed, and nothing is
            recorded until you review a draft and submit it yourself.
          </p>
        </div>
        {busy ? (
          <Button type="button" variant="secondary" size="sm" onClick={stop} aria-label="Stop suggestions" data-testid="suggest-stop">
            <Square className="size-3" aria-hidden="true" /> Stop
          </Button>
        ) : (
          <Button type="button" variant="secondary" size="sm" onClick={() => void suggest()} data-testid="suggest-run">
            <Sparkles className="size-3" aria-hidden="true" /> Suggest hypotheses
          </Button>
        )}
      </div>

      {error ? (
        <p
          className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical"
          role="alert"
          data-testid="suggest-error"
        >
          Suggestion run failed: {error}
        </p>
      ) : null}

      {busy && !hasRun ? (
        <p className="inline-flex items-center gap-1.5 text-xs text-dim" data-testid="suggest-progress">
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          {phase ?? "Working…"}
        </p>
      ) : null}

      {grounded === false && !error ? (
        <p
          className="rounded-md border border-medium/30 bg-medium/10 px-3 py-2 text-xs text-medium"
          role="alert"
          data-testid="suggest-ungrounded"
        >
          No authorized sources were retrieved for this run — every draft from it is unverified.
        </p>
      ) : null}

      {!error && hasRun && !busy && drafts.length === 0 && draftErrors === 0 ? (
        <p className="text-xs text-dim" data-testid="suggest-empty">
          The model returned no structured suggestions this run — see the raw output below.
        </p>
      ) : null}

      {draftErrors > 0 ? (
        <p
          className="rounded-md border border-medium/30 bg-medium/10 px-3 py-2 text-xs text-medium"
          role="alert"
          data-testid="suggest-partial"
        >
          {draftErrors} suggestion block{draftErrors === 1 ? "" : "s"} could not be accepted (invalid or over the
          limit) — this tray may be partial. The raw model output below shows everything that was generated.
        </p>
      ) : null}

      {drafts.length > 0 ? (
        <ul className="mt-3 space-y-2" data-testid="suggest-tray">
          {drafts.map((draft, index) => {
            const unverified = new Set(draft.unverified_ids);
            return (
              <li key={`${draft.title}-${index}`} className="rounded-lg border border-border bg-surface-2 p-3" data-testid={`suggest-draft-${index}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="min-w-0 text-sm font-medium text-foreground">{draft.title}</p>
                  {canRecord && onRecord ? (
                    <Button type="button" size="sm" onClick={() => onRecord(draft)} data-testid={`suggest-record-${index}`}>
                      Record…
                    </Button>
                  ) : null}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted">{draft.statement}</p>
                {draft.evidence_ids.length > 0 ? (
                  <div className="mt-2 flex flex-wrap items-center gap-1">
                    <span className="text-[10px] text-dim">cited records:</span>
                    {draft.evidence_ids.map((id) => (
                      <span
                        key={id}
                        title={unverified.has(id) ? `${id} — not found in retrieved data` : `${id} — present in retrieved data`}
                        className={cn(
                          "rounded border px-1.5 py-0.5 font-mono text-[10px]",
                          unverified.has(id)
                            ? "border-medium/40 bg-medium/10 text-medium"
                            : "border-border bg-surface-3 text-muted",
                        )}
                        data-testid={unverified.has(id) ? "suggest-id-unverified" : "suggest-id-verified"}
                      >
                        {id.slice(0, 8)}…
                        {unverified.has(id) ? " ⚠ unverified" : " · retrieved"}
                      </span>
                    ))}
                  </div>
                ) : null}
                {draft.refutation ? (
                  <p className="mt-2 text-[11px] text-dim">
                    <span className="font-medium text-muted">Refutation test:</span> {draft.refutation}
                  </p>
                ) : null}
                {draft.missing ? (
                  <p className="mt-1 text-[11px] text-dim">
                    <span className="font-medium text-muted">Missing to test:</span> {draft.missing}
                  </p>
                ) : null}
                <p className="mt-2 flex items-center gap-1.5 border-t border-border pt-2 text-[10px] text-dim">
                  <AlertTriangle className="size-3 shrink-0 text-high" aria-hidden="true" />
                  Unverified draft — recording it stores a "proposed" hypothesis with your name on it, nothing more.
                </p>
              </li>
            );
          })}
        </ul>
      ) : null}

      {raw ? (
        <details className="mt-3 rounded-md border border-border bg-surface-3 px-3 py-2 text-[11px] text-muted" data-testid="suggest-raw">
          <summary className="cursor-pointer text-dim">Model output (raw)</summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[10px] leading-relaxed">
            {raw}
          </pre>
        </details>
      ) : null}

      {sources.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1" data-testid="suggest-sources">
          {sources.map((source) => (
            <li
              key={`${source.type}:${source.id}`}
              className="rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] text-dim"
              title={source.id}
            >
              {source.type}: {source.label || source.id}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
