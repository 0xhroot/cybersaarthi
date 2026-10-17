import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Ban, Coins, Loader2, Search, Wallet } from "lucide-react";

import {
  useArtifacts,
  useCancelIntelJob,
  useIntelJobs,
  useReviewArtifact,
  useSubmitFinancialFlow,
  useTraceFinancialFlow,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/loading";
import { Tip } from "@/components/ui/tooltip";
import { toast } from "@/components/ui/toast";
import { formatRelative, shortId } from "@/lib/utils";
import type { AnalysisJobOut, DerivedArtifactOut, FlowTraceResponse } from "@/types/domain";

/**
 * Financial flow panel (phase 4, feature A).
 *
 * Contract: every number on this panel is a deterministic, citation-complete
 * extraction from the case's own source records — no model ran to produce it.
 * The panel therefore shows the calculation definitions next to each total,
 * keeps `total_records` and `total_distinct` side by side (neither is "the"
 * truth), marks direction-dependent metrics as not computable rather than
 * zero, and renders the structure as association-only: `confirmed_transfer
 * _edges` is always displayed. The trace tool answers what else is
 * *documented* about an account; a `transfer` trace is answered as absent.
 * Firing patterns are review candidates — never evidence of intent — and a
 * human review decision applies to the artifact as a whole.
 */

function jobTone(status: AnalysisJobOut["status"]): "success" | "info" | "critical" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "critical";
  if (status === "running" || status === "pending") return "info";
  return "neutral";
}

/* ----------------------------- payload shapes ----------------------------- */

interface FlowFact {
  fact_class?: string;
  record_no?: number;
  evidence_file_id?: string | null;
  source_locator?: { record_no?: number; evidence_file_id?: string } | null;
  txn_ref_original?: string | null;
  amount?: string | null;
  amount_original?: string | null;
  amount_precision?: string | null;
  currency?: string | null;
  occurred_at?: string | null;
  account_original?: string | null;
  receiver?: string | null;
  merchant?: string | null;
  party?: string | null;
  bank?: string | null;
  status?: string;
  missing?: string[];
  limitations?: string[];
}

interface FlowBucket {
  currency: string | null;
  currency_unknown?: boolean;
  count?: number;
  distinct_groups?: number;
  distinct_amounts?: number;
  conflicting_groups?: Array<{ key?: string; amounts?: string[] }>;
  min?: string | null;
  max?: string | null;
  total_records?: string | null;
  total_distinct?: string | null;
  total_distinct_conflicts_excluded?: number;
  dedupe_key_definition?: string;
  dedupe_caveat?: string;
  supporting_source_record_ids?: string[];
}

interface FlowGrouped {
  account_normalized?: string;
  merchant?: string;
  bank?: string;
  count?: number;
  total_records?: string;
  supporting_source_record_ids?: string[];
}

interface FlowPattern {
  rule?: string;
  version?: string;
  status?: string;
  reason?: string;
  explanation?: string;
  evidence?: Record<string, unknown>;
  supporting_source_record_ids?: string[];
  supporting_victim_ids?: string[];
  limitations?: string[];
  review_status?: string;
  pattern_not_intent?: boolean;
}

interface FlowNetwork {
  nodes?: Array<{ id?: string; kind?: string; label?: string }>;
  edges?: Array<{
    source?: string;
    target?: string;
    edge_kind?: string;
    confidence?: string;
    derivation?: string;
    relationship_type?: string | null;
    supporting_source_record_ids?: string[];
  }>;
  nodes_total?: number;
  edges_total?: number;
  confirmed_transfer_edges?: number;
  transfer_edge_note?: string;
}

interface FlowPayload {
  flow_rules_version?: string;
  pattern_rules_version?: string;
  scope?: Record<string, unknown>;
  facts?: FlowFact[];
  facts_bounded?: boolean;
  facts_total?: number;
  victim_financials?: Array<Record<string, unknown>>;
  aggregates?: {
    counts?: Record<string, number>;
    currency_buckets?: FlowBucket[];
    by_account?: FlowGrouped[];
    by_merchant?: FlowGrouped[];
    not_computable?: Record<string, string>;
  };
  structure_network?: FlowNetwork;
  patterns?: { firing?: FlowPattern[]; not_fired?: string[]; not_evaluable?: FlowPattern[] };
  limitations?: string[];
  calculation_definitions?: Record<string, string>;
}

function payloadOf(artifact: DerivedArtifactOut): FlowPayload {
  return artifact.payload as FlowPayload;
}

/* ------------------------------ small pieces ------------------------------ */

function DefinitionTip({ label, definition }: { label: string; definition: string }) {
  return (
    <Tip label={definition}>
      <button
        type="button"
        aria-label={`Calculation definition for ${label}`}
        className="cursor-help border-b border-dashed border-border text-inherit"
      >
        {label}
      </button>
    </Tip>
  );
}

function EvidenceList({ evidence }: { evidence?: Record<string, unknown> }) {
  if (!evidence || Object.keys(evidence).length === 0) return null;
  return (
    <dl className="mt-1.5 grid gap-x-4 gap-y-1 sm:grid-cols-2">
      {Object.entries(evidence).map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-2 text-[11px]">
          <dt className="shrink-0 text-dim">{key.replace(/_/g, " ")}</dt>
          <dd className="min-w-0 truncate font-mono text-foreground/85" title={String(value)}>
            {Array.isArray(value) ? value.join(", ") : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function IdList({ ids }: { ids?: string[] }) {
  if (!ids?.length) return null;
  return (
    <p className="mt-1.5 font-mono text-[10px] leading-relaxed text-dim">
      supporting records: {ids.slice(0, 6).join(", ")}
      {ids.length > 6 ? ` (+${ids.length - 6} more)` : ""}
    </p>
  );
}

function PatternCard({ pattern }: { pattern: FlowPattern }) {
  const isNotEvaluable = (pattern.status ?? "") === "not_evaluable";
  return (
    <div
      className="rounded-lg border border-border bg-surface-2 p-3"
      data-testid={isNotEvaluable ? "flow-pattern-not-evaluable" : "flow-pattern"}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">{pattern.rule ?? "unknown rule"}</Badge>
        {isNotEvaluable ? <Badge tone="neutral">cannot evaluate: {pattern.reason ?? "unknown input missing"}</Badge> : null}
        {!isNotEvaluable ? <Badge tone="info">firing · review candidate</Badge> : null}
        {pattern.version ? <span className="font-mono text-[10px] text-dim">{pattern.version}</span> : null}
        {!isNotEvaluable ? (
          <span className="ml-auto text-[10px] uppercase tracking-wider text-dim">
            deterministic · pattern ≠ intent
          </span>
        ) : null}
      </div>
      {isNotEvaluable ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/80">{pattern.explanation}</p>
      ) : (
        <>
          <EvidenceList evidence={pattern.evidence} />
          <IdList ids={pattern.supporting_source_record_ids} />
          <IdList ids={pattern.supporting_victim_ids} />
          {pattern.limitations?.length ? (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {pattern.limitations.map((limitation) => (
                <Badge key={limitation} tone="low">
                  {limitation}
                </Badge>
              ))}
            </div>
          ) : null}
          {pattern.review_status ? (
            <p className="mt-1.5 text-[10px] uppercase tracking-wider text-dim">
              review status: {pattern.review_status.replace(/_/g, " ")} — decided by the reviewer of this artifact
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}

function BucketCard({ bucket, definitions }: { bucket: FlowBucket; definitions: Record<string, string> }) {
  const conflicts = bucket.conflicting_groups ?? [];
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="flow-bucket">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={bucket.currency ? "neutral" : "low"}>
          {bucket.currency ? `currency ${bucket.currency}` : "currency unknown"}
        </Badge>
        <span className="text-[11px] text-dim">
          {bucket.count ?? 0} amount-bearing record{(bucket.count ?? 0) === 1 ? "" : "s"} ·{" "}
          {bucket.distinct_groups ?? 0} distinct groups · {bucket.distinct_amounts ?? 0} distinct amounts
        </span>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div className="rounded border border-border bg-surface-3 p-2">
          <p className="text-[10px] uppercase tracking-wider text-dim">
            {definitions.total_records ? (
              <DefinitionTip label="Total · every record" definition={definitions.total_records} />
            ) : (
              "Total · every record"
            )}
          </p>
          <p className="mt-0.5 font-mono text-sm tabular text-foreground">{bucket.total_records ?? "—"}</p>
        </div>
        <div className="rounded border border-border bg-surface-3 p-2">
          <p className="text-[10px] uppercase tracking-wider text-dim">
            {definitions.total_distinct ? (
              <DefinitionTip label="Total · distinct groups" definition={definitions.total_distinct} />
            ) : (
              "Total · distinct groups"
            )}
          </p>
          <p className="mt-0.5 font-mono text-sm tabular text-foreground">
            {bucket.total_distinct ?? "not computable"}
          </p>
        </div>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-dim">
        {bucket.total_distinct === null && bucket.total_distinct !== undefined
          ? "Every group's records disagree on the amount, so no distinct total exists — a zero here would be a fabricated figure."
          : bucket.dedupe_caveat ?? "Both totals are reported together; neither is presented as the unique truth."}
      </p>
      {conflicts.length ? (
        <p className="mt-1 font-mono text-[10px] text-low">
          {conflicts.length} conflicting group{conflicts.length === 1 ? "" : "s"} excluded from the distinct total
          {conflicts.map((conflict) => ` (${(conflict.amounts ?? []).join(" vs ")})`).join("")}
        </p>
      ) : null}
      {bucket.min && bucket.max ? (
        <p className="mt-1 text-[11px] text-dim">
          exact min <span className="font-mono text-foreground/85">{bucket.min}</span> · max{" "}
          <span className="font-mono text-foreground/85">{bucket.max}</span>
        </p>
      ) : null}
      <IdList ids={bucket.supporting_source_record_ids} />
    </div>
  );
}

function FactRow({ fact, caseId }: { fact: FlowFact; caseId: string }) {
  const locatorFile = fact.evidence_file_id ?? fact.source_locator?.evidence_file_id ?? null;
  const counterparty = fact.receiver ?? fact.merchant ?? fact.party ?? null;
  return (
    <tr data-testid="flow-fact">
      <td className="font-mono text-[11px] text-dim">
        {fact.record_no ?? "—"}
        {locatorFile ? (
          <Link
            className="ml-1.5 text-accent underline-offset-2 hover:underline"
            to={`/app/cases/${caseId}/evidence`}
            aria-label={`Open evidence for record ${fact.record_no ?? ""}`}
          >
            open
          </Link>
        ) : null}
      </td>
      <td className="font-mono text-[11px] text-foreground/85">
        {fact.txn_ref_original ?? <span className="text-dim">— no ref</span>}
      </td>
      <td className="text-[11px]">
        <span className="font-mono text-foreground">{fact.amount ?? "—"}</span>
        {fact.amount && fact.amount_original && fact.amount !== fact.amount_original ? (
          <span className="ml-1 font-mono text-[10px] text-dim">(from {fact.amount_original})</span>
        ) : null}
        <span className="ml-1 text-dim">{fact.currency ? fact.currency : "· currency unknown"}</span>
      </td>
      <td className="text-[11px] text-foreground/85">{fact.occurred_at ?? <span className="text-dim">no time</span>}</td>
      <td className="text-[11px]">
        <span className="text-dim">payer absent → </span>
        <span className="font-mono text-foreground/85">{counterparty ?? "—"}</span>
      </td>
      <td className="text-[11px]">
        <span className="font-mono text-foreground/85">{fact.account_original ?? "—"}</span>
        <span className="ml-1 text-dim">{fact.status ?? ""}</span>
      </td>
    </tr>
  );
}

/* -------------------------------- trace UI -------------------------------- */

const TRACE_EMPTY_HINT =
  "Accounts documented in this run appear as quick picks. The trace recomputes from your authorized records on every call.";

function TraceResultView({ result }: { result: FlowTraceResponse }) {
  const statusTone =
    result.status === "ok" ? "info" : result.status === "insufficient_data" ? "low" : "neutral";
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3" data-testid="flow-trace-result">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={statusTone}>{result.status.replace(/_/g, " ")}</Badge>
        <span className="font-mono text-[11px] text-foreground/85">
          {result.target_kind}: {result.target}
        </span>
        <Badge tone="neutral">{result.edge_kind}</Badge>
        {result.start_node ? <span className="font-mono text-[10px] text-dim">start {result.start_node}</span> : null}
        <span className="ml-auto font-mono text-[10px] text-dim">
          depth ≤ {result.bounds.max_depth} · paths ≤ {result.bounds.max_paths} ·{" "}
          {result.bounds.records_scanned} records scanned
        </span>
      </div>

      {result.reason ? <p className="mt-1.5 text-[11px] text-dim">{result.reason.replace(/_/g, " ")}</p> : null}

      <div className="mt-1.5 text-[11px] text-dim">
        network scope: {result.network.nodes_total} nodes · {result.network.edges_total} edges ·{" "}
        <span className={result.network.confirmed_transfer_edges === 0 ? "text-low" : "text-foreground"}>
          {result.network.confirmed_transfer_edges} confirmed transfer edges
        </span>
      </div>

      {result.paths.length === 0 && result.status === "ok" ? (
        <p className="mt-2 text-[11px] text-foreground/80">
          {result.target_degree === 0
            ? "No further documented links for this target — the trail stops here in the ingested evidence."
            : "No path within the configured bounds."}
        </p>
      ) : null}

      {result.paths.map((path, index) => (
        <div key={index} className="mt-2 rounded border border-border bg-surface-3 p-2" data-testid="flow-trace-path">
          <div className="flex flex-wrap items-center gap-1.5">
            {path.nodes.map((node, position) => (
              <span key={node} className="flex items-center gap-1.5">
                {position > 0 ? <ArrowRight className="size-3 text-dim" /> : null}
                <span className="font-mono text-[11px] text-foreground/85">{node}</span>
              </span>
            ))}
            <Badge tone="neutral">depth {path.depth}</Badge>
            {path.end_state === "depth_limit" ? <Badge tone="info">cut at depth limit</Badge> : null}
            {path.incomplete ? (
              <Badge tone="low">incomplete — trail stops here in the evidence</Badge>
            ) : null}
          </div>
          {path.hops.map((hop, hopIndex) => (
            <p key={hopIndex} className="mt-1 font-mono text-[10px] leading-relaxed text-dim" data-testid="flow-trace-hop">
              {hop.source} → {hop.target} · {hop.edge_kind} ({hop.confidence}) · {hop.derivation}
              {hop.supporting_source_record_ids.length
                ? ` · records ${hop.supporting_source_record_ids.join(", ")}`
                : ""}
            </p>
          ))}
        </div>
      ))}

      {result.paths_bounded ? (
        <p className="mt-2 text-[11px] text-low">
          Path limit reached — more documented links may exist beyond the returned set (bounded at{" "}
          {result.bounds.max_paths} paths).
        </p>
      ) : null}

      <ul className="mt-2 list-inside list-disc space-y-0.5">
        {result.limitations.map((limitation) => (
          <li key={limitation} className="text-[11px] leading-relaxed text-dim">
            {limitation}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* -------------------------------- main panel ------------------------------- */

export function FinancialFlowPanel({ caseId }: { caseId: string }) {
  const canRun = useCan("ingestion.run");
  const canReview = useCan("findings.review");
  const canTrace = useCan("evidence.read");
  const jobs = useIntelJobs(caseId, "financial_flow");
  const artifacts = useArtifacts(caseId, "financial_finding");
  const submit = useSubmitFinancialFlow(caseId);
  const review = useReviewArtifact(caseId);
  const cancel = useCancelIntelJob(caseId);
  const trace = useTraceFinancialFlow(caseId);

  const [noteOpen, setNoteOpen] = useState<{ artifact: DerivedArtifactOut; decision: "approved" | "rejected" } | null>(
    null,
  );
  const [note, setNote] = useState("");
  const [target, setTarget] = useState("");
  const [targetKind, setTargetKind] = useState<"account" | "transaction">("account");
  const [edgeKind, setEdgeKind] = useState<"association" | "transfer">("association");
  const [traceResult, setTraceResult] = useState<FlowTraceResponse | null>(null);

  const items = useMemo(() => artifacts.data?.items ?? [], [artifacts.data]);
  const latestJob = (jobs.data?.items ?? [])[0];
  const activeJob = (jobs.data?.items ?? []).find((job) => job.status === "pending" || job.status === "running");
  const summary = (latestJob?.result_summary ?? {}) as Record<string, unknown>;

  const artifact = useMemo(() => {
    const sorted = [...items].sort((left, right) => (left.created_at < right.created_at ? 1 : -1));
    return sorted[0] ?? null;
  }, [items]);
  const payload = artifact ? payloadOf(artifact) : null;
  const definitions = payload?.calculation_definitions ?? {};

  const accountPicks = useMemo(
    () =>
      (payload?.structure_network?.nodes ?? [])
        .filter((node) => node.kind === "account" && node.label)
        .map((node) => String(node.label)),
    [payload],
  );

  const runAnalysis = async () => {
    try {
      const result = await submit.mutateAsync();
      toast({
        title: "Financial analysis queued",
        description: result.duplicate
          ? "Reusing the active financial-flow job."
          : "Extracting exact amounts, aggregates and pattern candidates from the case records.",
      });
    } catch (err) {
      toast({ title: "Financial analysis failed", description: (err as Error).message });
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

  const runTrace = async () => {
    if (!target.trim()) {
      toast({ title: "Target required", description: "Enter an account reference or transaction id to trace." });
      return;
    }
    try {
      const result = await trace.mutateAsync({ target: target.trim(), target_kind: targetKind, edge_kind: edgeKind });
      setTraceResult(result);
    } catch (err) {
      toast({ title: "Trace failed", description: (err as Error).message });
    }
  };

  const submitReview = async () => {
    if (!noteOpen) return;
    try {
      await review.mutateAsync({
        artifactId: noteOpen.artifact.id,
        review: { decision: noteOpen.decision, note: note || null },
      });
      toast({
        title: noteOpen.decision === "approved" ? "Finding confirmed" : "Finding dismissed",
        description: "The decision was recorded in the audit log — the extracted numbers are unchanged.",
      });
      setNoteOpen(null);
      setNote("");
    } catch (err) {
      toast({ title: "Review failed", description: (err as Error).message });
    }
  };

  const reviewStatus = artifact
    ? artifact.status === "approved"
      ? { label: "Confirmed", tone: "success" as const }
      : artifact.status === "rejected"
        ? { label: "Dismissed", tone: "critical" as const }
        : { label: "Pending review", tone: "info" as const }
    : null;

  return (
    <div className="space-y-3" data-testid="financial-flow-panel">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">Financial flow</p>
        {canRun ? (
          <Button
            size="sm"
            disabled={submit.isPending || Boolean(activeJob)}
            onClick={() => void runAnalysis()}
          >
            {submit.isPending || activeJob ? <Loader2 className="size-3.5 animate-spin" /> : <Wallet className="size-3.5" />}
            {activeJob ? "Analyzing…" : "Run financial analysis"}
          </Button>
        ) : null}
      </div>

      {latestJob ? (
        <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="flow-summary">
          <Badge tone={jobTone(latestJob.status)}>{latestJob.status}</Badge>
          <span className="text-dim">
            {String(summary.records_scanned ?? "—")} records · {String(summary.facts_extracted ?? "—")} facts ·{" "}
            {String(summary.currency_buckets ?? "—")} currency bucket
            {String(summary.currency_buckets ?? "0") === "1" ? "" : "s"} · {String(summary.network_nodes ?? "—")} nodes ·{" "}
            {String(summary.network_edges ?? "—")} edges · {String(summary.patterns_firing ?? "—")} firing ·{" "}
            {String(summary.patterns_not_evaluable ?? "—")} not evaluable · {formatRelative(latestJob.updated_at)}
          </span>
          {activeJob && canRun ? (
            <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob.id)} aria-label="Cancel financial analysis">
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
      ) : !artifact || !payload ? (
        <EmptyState
          title="No financial finding recorded"
          description="Run the deterministic analysis to extract exact amounts, per-currency totals, the bounded association network and the declared pattern rules. No model is involved, and every number stays traceable to its source records."
        />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {reviewStatus ? <Badge tone={reviewStatus.tone}>{reviewStatus.label}</Badge> : null}
            <Badge tone="accent">deterministic · no model in this run</Badge>
            <span className="font-mono text-[10px] text-dim">
              {payload.flow_rules_version} · {payload.pattern_rules_version} · {shortId(artifact.id)}
            </span>
            {items.length > 1 ? (
              <span className="text-[10px] text-dim">showing the latest of {items.length} findings</span>
            ) : null}
            {artifact.status === "pending_review" && canReview ? (
              <span className="ml-auto flex gap-2">
                <Button
                  size="sm"
                  disabled={review.isPending}
                  aria-label="Confirm finding"
                  onClick={() => {
                    void review
                      .mutateAsync({ artifactId: artifact.id, review: { decision: "approved" } })
                      .then(
                        () =>
                          toast({
                            title: "Finding confirmed",
                            description:
                              "Recorded as confirmed — the extracted numbers and their source records are unchanged.",
                          }),
                        (err: unknown) => toast({ title: "Review failed", description: (err as Error).message }),
                      );
                  }}
                >
                  Confirm finding
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={review.isPending}
                  onClick={() => setNoteOpen({ artifact, decision: "rejected" })}
                >
                  <Ban className="size-3.5" /> Dismiss
                </Button>
              </span>
            ) : null}
          </div>

          {/* Scope */}
          <div className="rounded border border-border bg-surface-3 p-2 text-[11px] text-dim">
            scope: {String(payload.scope?.records_scanned ?? "—")} source records scanned
            {payload.scope?.records_bounded ? " (bounded scan)" : ""} ·{" "}
            {String(payload.scope?.victim_rows_scanned ?? 0)} victim rows ·{" "}
            {payload.facts_total ?? 0} facts{payload.facts_bounded ? " (bounded)" : ""} · rules{" "}
            {payload.flow_rules_version}
          </div>

          {/* Aggregates */}
          <section>
            <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">Per-currency totals</p>
            <div className="grid gap-2">
              {(payload.aggregates?.currency_buckets ?? []).map((bucket, index) => (
                <BucketCard key={index} bucket={bucket} definitions={definitions} />
              ))}
            </div>
            {payload.aggregates?.not_computable ? (
              <div className="mt-2 rounded border border-dashed border-low/50 bg-low/5 p-2" data-testid="flow-not-computable">
                <p className="text-[11px] font-medium text-low">
                  Inflow / outflow / net: not computed — direction is absent from the ingest
                </p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-dim">
                  {payload.aggregates.not_computable.reason}
                </p>
              </div>
            ) : null}
          </section>

          {/* Accounts */}
          {(payload.aggregates?.by_account ?? []).length ? (
            <section>
              <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">Accounts with amounts</p>
              <div className="rounded border border-border">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-border text-[10px] uppercase tracking-wider text-dim">
                      <th className="px-2 py-1.5 font-medium">Account</th>
                      <th className="px-2 py-1.5 font-medium">Records</th>
                      <th className="px-2 py-1.5 font-medium">Total (records)</th>
                      <th className="px-2 py-1.5 font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {(payload.aggregates?.by_account ?? []).map((group) => (
                      <tr key={group.account_normalized} className="border-b border-border/60 last:border-0">
                        <td className="px-2 py-1.5 font-mono text-[11px] text-foreground">
                          {group.account_normalized ?? "—"}
                        </td>
                        <td className="px-2 py-1.5 text-[11px] text-dim">{group.count ?? 0}</td>
                        <td className="px-2 py-1.5 font-mono text-[11px] tabular text-foreground/85">
                          {group.total_records ?? "—"}
                        </td>
                        <td className="px-2 py-1.5 text-right">
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={!canTrace || trace.isPending}
                            aria-label={`Trace account ${group.account_normalized ?? ""}`}
                            onClick={() => {
                              setTargetKind("account");
                              setEdgeKind("association");
                              setTarget(group.account_normalized ?? "");
                            }}
                          >
                            <Search className="size-3.5" /> Trace
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {/* Facts / transactions */}
          {(payload.facts ?? []).length ? (
            <section>
              <p className="mb-1.5 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-dim">
                <Coins className="size-3" /> Extracted transaction facts
              </p>
              <div className="overflow-x-auto rounded border border-border">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-border text-[10px] uppercase tracking-wider text-dim">
                      <th className="px-2 py-1.5 font-medium">Record</th>
                      <th className="px-2 py-1.5 font-medium">Txn ref</th>
                      <th className="px-2 py-1.5 font-medium">Amount</th>
                      <th className="px-2 py-1.5 font-medium">Time</th>
                      <th className="px-2 py-1.5 font-medium">From → to</th>
                      <th className="px-2 py-1.5 font-medium">Account · status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(payload.facts ?? []).map((fact, index) => (
                      <FactRow key={index} fact={fact} caseId={caseId} />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {/* Patterns */}
          <section>
            <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">
              Pattern rules — candidates for review, never evidence of intent
            </p>
            <div className="grid gap-2">
              {(payload.patterns?.firing ?? []).map((pattern, index) => (
                <PatternCard key={index} pattern={pattern} />
              ))}
            </div>
            {(payload.patterns?.not_fired ?? []).length ? (
              <p className="mt-1.5 text-[11px] text-dim">
                evaluated, no evidence: {(payload.patterns?.not_fired ?? []).join(", ")}
              </p>
            ) : null}
            <div className="mt-2 grid gap-2">
              {(payload.patterns?.not_evaluable ?? []).map((pattern, index) => (
                <PatternCard key={index} pattern={pattern} />
              ))}
            </div>
          </section>

          {/* Structure */}
          <section>
            <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">Association structure</p>
            <div className="rounded border border-border bg-surface-3 p-2 text-[11px] text-dim">
              {payload.structure_network?.nodes_total ?? 0} nodes · {payload.structure_network?.edges_total ?? 0} edges ·{" "}
              <span className="text-low">
                {payload.structure_network?.confirmed_transfer_edges ?? 0} confirmed transfer edges
              </span>
              <p className="mt-1 leading-relaxed">{payload.structure_network?.transfer_edge_note}</p>
            </div>
            <div className="mt-1.5 space-y-1">
              {(payload.structure_network?.edges ?? []).map((edge, index) => (
                <p key={index} className="font-mono text-[10px] leading-relaxed text-dim" data-testid="flow-edge">
                  {edge.source} ↔ {edge.target} · {edge.edge_kind} ({edge.confidence ?? "suspected"}) ·{" "}
                  {edge.derivation ?? "co_occurrence"}
                  {edge.supporting_source_record_ids?.length
                    ? ` · records ${edge.supporting_source_record_ids.join(", ")}`
                    : ""}
                </p>
              ))}
            </div>
          </section>

          {/* Limitations + calculation definitions (always visible) */}
          <section className="rounded border border-border bg-surface-3 p-2" data-testid="flow-limitations">
            <p className="text-[10px] uppercase tracking-wider text-dim">Limitations of this analysis</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {(payload.limitations ?? []).map((limitation) => (
                <li key={limitation} className="text-[11px] leading-relaxed text-foreground/80">
                  {limitation}
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[11px] leading-relaxed text-dim">
              {definitions.net_flow ?? "Direction-dependent totals are not computed."} Export travels through the existing
              artifacts/reports flow — the payload is citation-complete.
            </p>
          </section>
        </div>
      )}

      {/* Trace tool — read-only, works with or without a completed run. */}
      {canTrace ? (
        <section className="rounded-lg border border-border bg-surface-2 p-3" data-testid="flow-trace-form">
          <p className="text-[10px] uppercase tracking-wider text-dim">Bounded structure trace</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
            <div>
              <Label htmlFor="flow-trace-target" className="text-[11px] text-dim">
                Target
              </Label>
              <Input
                id="flow-trace-target"
                value={target}
                placeholder={targetKind === "account" ? "ACC-SIH-001" : "TXN-SIH-001"}
                onChange={(event) => setTarget(event.target.value)}
                aria-label="Trace target"
              />
            </div>
            <div>
              <Label htmlFor="flow-trace-kind" className="text-[11px] text-dim">
                Kind
              </Label>
              <select
                id="flow-trace-kind"
                className="h-9 w-full rounded border border-border bg-surface-3 px-2 text-xs text-foreground outline-none focus:border-accent/40"
                value={targetKind}
                onChange={(event) => setTargetKind(event.target.value as "account" | "transaction")}
              >
                <option value="account">Account</option>
                <option value="transaction">Transaction</option>
              </select>
            </div>
            <div>
              <Label htmlFor="flow-trace-edge" className="text-[11px] text-dim">
                Edge kind
              </Label>
              <select
                id="flow-trace-edge"
                className="h-9 w-full rounded border border-border bg-surface-3 px-2 text-xs text-foreground outline-none focus:border-accent/40"
                value={edgeKind}
                onChange={(event) => setEdgeKind(event.target.value as "association" | "transfer")}
              >
                <option value="association">Association</option>
                <option value="transfer">Transfer</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button size="sm" disabled={trace.isPending} onClick={() => void runTrace()} aria-label="Run structure trace">
                {trace.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />} Trace
              </Button>
            </div>
          </div>

          {accountPicks.length && targetKind === "account" ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-dim">quick picks:</span>
              {accountPicks.map((pick) => (
                <Button key={pick} size="sm" variant="ghost" onClick={() => setTarget(pick)} aria-label={`Use account ${pick}`}>
                  {pick}
                </Button>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-[11px] text-dim">{TRACE_EMPTY_HINT}</p>
          )}

          {trace.error ? <PanelError error={trace.error} onRetry={() => void runTrace()} /> : null}
          {traceResult ? <div className="mt-2"><TraceResultView result={traceResult} /></div> : null}
        </section>
      ) : null}

      {noteOpen ? (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs font-medium text-foreground">
            {noteOpen.decision === "rejected"
              ? "Why is this finding being dismissed? (optional, recorded in the audit trail)"
              : "Confirm this finding as reviewed?"}
          </p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-border bg-surface-3 p-2 text-xs text-foreground outline-none focus:border-accent/40"
            placeholder="Note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" disabled={review.isPending} onClick={() => void submitReview()}>
              Record decision
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
