import { useCallback, useRef, useState } from "react";
import { Brain, FileText, Loader2, Square } from "lucide-react";

import { api } from "@/api";
import type { AiCitationCheck, AiSource, AiToolEvent } from "@/api/contract";
import { Markdown } from "@/components/ai/markdown";
import { ReportAuditPanel } from "@/components/ai/report-audit-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * AI analysis panel for the Analytics page.
 *
 * Contract: the deterministic engine computes; this panel only renders the
 * model's *interpretation* of those results. Every answer arrives with the
 * server-side `citation_check` (ids and metric numbers verified against the
 * retrieved case data), so mismatches surface as warnings instead of quietly
 * passing. A failed stream or a failed report draft is always shown as a
 * failure — never as an analysis that succeeded.
 */

/** Preset questions — prompts only; answers always come from the model/data. */
const ANALYSIS_ACTIONS = [
  {
    id: "interpret",
    label: "Interpret metrics",
    question:
      "Interpret the computed analytics for this case: what do the metrics, communities and network DNA indicate?",
  },
  {
    id: "anomalies",
    label: "Anomalies",
    question:
      "Which anomalies in the metrics or graph are evidence-grounded, and which evidence supports each?",
  },
  {
    id: "correlation",
    label: "Timeline & entities",
    question:
      "Correlate the timeline with the top-ranked entities and communities; which sequences stand out?",
  },
  {
    id: "contradictions",
    label: "Contradictions & gaps",
    question:
      "Identify contradictions and missing data across evidence, entities and analytics; what is absent?",
  },
  {
    id: "alternatives",
    label: "Alternative explanations",
    question:
      "Give alternative explanations for the observed network structure, with evidence for and against each.",
  },
  {
    id: "next",
    label: "Next steps",
    question:
      "List concrete follow-up questions and verification steps, each tied to a specific record.",
  },
] as const;

const PHASE_LABEL: Record<string, string> = {
  retrieving: "Retrieving authorized records…",
  synthesizing: "Synthesizing analysis…",
};

export interface AnalysisPanelProps {
  caseId: string;
}

export function AnalysisPanel({ caseId }: AnalysisPanelProps) {
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<AiSource[]>([]);
  const [toolEvents, setToolEvents] = useState<AiToolEvent[]>([]);
  const [grounded, setGrounded] = useState<boolean | null>(null);
  const [citationCheck, setCitationCheck] = useState<AiCitationCheck | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setPhase(null);
  }, []);

  const runAction = useCallback(
    async (question: string) => {
      if (busy) return;
      // Reset everything first: a previous answer must never masquerade as
      // the result of this run if this run fails.
      setBusy(true);
      setError(null);
      setAnswer("");
      setSources([]);
      setToolEvents([]);
      setGrounded(null);
      setCitationCheck(null);
      setDraft(null);
      setPhase(PHASE_LABEL.retrieving);

      const controller = new AbortController();
      abortRef.current = controller;
      let streamed = "";

      try {
        await api.ai.chatStream(
          // `think` budget: the five-section analysis contract needs the larger
          // generation allowance; grounding/tool rules stay identical.
          { question, mode: "analysis", case_id: caseId, profile: "think" },
          {
            onProgress: (info) => setPhase(PHASE_LABEL[info.phase] ?? `${info.phase}…`),
            onToken: (text) => {
              streamed += text;
              setAnswer(streamed);
              setPhase(null);
            },
            onSources: (next) => setSources(next),
            onTool: (event) => setToolEvents((prev) => [...prev, event]),
            onError: (message) => {
              setError(message);
              setAnswer("");
              setSources([]);
              setCitationCheck(null);
              setGrounded(null);
            },
            onDone: (info) => {
              setAnswer(
                streamed ||
                  info.answer ||
                  "The model returned no analysis text — treat this run as failed.",
              );
              setSources(info.sources);
              setToolEvents(info.tool_events.length ? info.tool_events : []);
              setGrounded(info.grounded);
              setCitationCheck(info.citation_check ?? null);
            },
          },
          controller.signal,
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "The analysis request failed.");
        setAnswer("");
        setSources([]);
        setCitationCheck(null);
        setGrounded(null);
      } finally {
        abortRef.current = null;
        setBusy(false);
        setPhase(null);
      }
    },
    [busy, caseId],
  );

  const runReportDraft = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setAnswer("");
    setSources([]);
    setToolEvents([]);
    setGrounded(null);
    setCitationCheck(null);
    setDraft(null);
    try {
      const result = await api.ai.reportDraft(caseId);
      setDraft(result.draft);
      setSources(result.sources);
      setGrounded(result.grounded);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Report draft failed — no draft was produced.",
      );
      setDraft(null);
    } finally {
      setBusy(false);
    }
  }, [busy, caseId]);

  const unverified = citationCheck?.unverified_ids ?? [];
  const mismatches = citationCheck?.metric_claims_mismatched ?? [];
  const checkPassed =
    citationCheck != null &&
    unverified.length === 0 &&
    mismatches.length === 0;

  return (
    <div className="mt-5 space-y-3" data-testid="analysis-panel">
      <div className="rounded-lg border border-border bg-surface-2 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Brain className="size-4 text-accent" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-foreground">AI analysis</h2>
            <span className="text-[11px] text-dim">
              interprets the deterministic results above — it never recomputes them
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {ANALYSIS_ACTIONS.map((action) => (
              <button
                key={action.id}
                type="button"
                disabled={busy}
                data-testid={`analysis-action-${action.id}`}
                onClick={() => void runAction(action.question)}
                className={cn(
                  "rounded-md border border-border bg-surface-3 px-2 py-1 text-[11px] text-muted transition",
                  "hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  busy && "cursor-not-allowed opacity-50",
                )}
              >
                {action.label}
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              data-testid="analysis-report-draft"
              onClick={() => void runReportDraft()}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border border-border bg-surface-3 px-2 py-1 text-[11px] text-muted transition",
                "hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                busy && "cursor-not-allowed opacity-50",
              )}
            >
              <FileText className="size-3" aria-hidden="true" /> Report draft
            </button>
            {busy ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={stop}
                aria-label="Stop analysis"
                data-testid="analysis-stop"
              >
                <Square className="size-3" aria-hidden="true" /> Stop
              </Button>
            ) : null}
          </div>
        </div>

        {error ? (
          <p
            className="mt-3 rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical"
            role="alert"
            data-testid="analysis-error"
          >
            Analysis failed: {error}
          </p>
        ) : null}

        {busy && !answer && !error ? (
          <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-dim" data-testid="analysis-progress">
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            {phase ?? "Working…"}
          </p>
        ) : null}

        {grounded === false && (answer || draft) ? (
          <p
            className="mt-3 rounded-md border border-medium/30 bg-medium/10 px-3 py-2 text-xs text-medium"
            role="alert"
            data-testid="analysis-ungrounded"
          >
            No authorized sources were retrieved for this response — treat it as
            unverified.
          </p>
        ) : null}

        {draft ? (
          <div className="mt-3 space-y-2" data-testid="analysis-draft">
            <p className="text-[11px] uppercase tracking-wider text-dim">
              Report draft — proposal for human review, not a submitted report
            </p>
            <Markdown>{draft}</Markdown>
            <ReportAuditPanel caseId={caseId} draft={draft} />
          </div>
        ) : null}

        {answer ? (
          <div className="mt-3 space-y-2" data-testid="analysis-answer">
            <Markdown>{answer}</Markdown>
          </div>
        ) : null}

        {citationCheck ? (
          <div
            className="mt-3 space-y-1 rounded-md border border-border bg-surface-3 px-3 py-2 text-[11px]"
            data-testid="analysis-citation-check"
          >
            <p className={cn(checkPassed ? "text-success" : "text-medium")}>
              {checkPassed
                ? `Claim check passed: ${citationCheck.verified_ids}/${citationCheck.cited_ids} cited ids verified, ${citationCheck.metric_claims_checked} metric claim${citationCheck.metric_claims_checked === 1 ? "" : "s"} match the data.`
                : `Claim check found issues: ${citationCheck.verified_ids}/${citationCheck.cited_ids} cited ids verified.`}
            </p>
            {unverified.length > 0 ? (
              <ul className="list-inside list-disc text-critical">
                {unverified.map((id) => (
                  <li key={id}>
                    unverified citation: <code>{id}</code>
                  </li>
                ))}
              </ul>
            ) : null}
            {mismatches.length > 0 ? (
              <ul className="list-inside list-disc text-critical">
                {mismatches.map((entry) => (
                  <li key={entry}>metric mismatch: {entry}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : answer ? (
          <p className="mt-3 text-[11px] text-dim" data-testid="analysis-citation-unavailable">
            Server claim check not available for this response.
          </p>
        ) : null}

        {sources.length > 0 ? (
          <ul className="mt-3 flex flex-wrap gap-1" data-testid="analysis-sources">
            {sources.map((source) => (
              <li
                key={`${source.type}:${source.id}`}
                className="rounded border border-border bg-surface-3 px-1.5 py-0.5 text-[10px] text-muted"
                title={source.id}
              >
                {source.type}: {source.label || source.id}
              </li>
            ))}
          </ul>
        ) : null}

        {toolEvents.length > 0 ? (
          <ul className="mt-2 space-y-0.5 text-[10px] text-dim" data-testid="analysis-tools">
            {toolEvents.map((event, index) => (
              <li key={`${event.tool}-${index}`}>
                tool: {event.tool} ·{" "}
                {event.ok
                  ? (event.status ?? "ok")
                  : (event.status ?? event.error ?? "failed")}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
