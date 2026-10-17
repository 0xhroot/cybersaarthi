import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

import type { AnalysisJobOut, DerivedArtifactOut, FlowTraceResponse } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useIntelJobs: vi.fn(),
  useArtifacts: vi.fn(),
  useSubmitFinancialFlow: vi.fn(),
  useReviewArtifact: vi.fn(),
  useCancelIntelJob: vi.fn(),
  useTraceFinancialFlow: vi.fn(),
}));

const permissions = vi.hoisted(() => ({ allowed: true }));

vi.mock("@/hooks/queries", () => queries);
vi.mock("@/lib/permissions", () => ({ useCan: () => permissions.allowed }));

import { FinancialFlowPanel } from "@/components/evidence/financial-flow-panel";
import { TooltipProvider } from "@/components/ui/tooltip";

const CASE = "case-1";

function job(overrides: Partial<AnalysisJobOut> = {}): AnalysisJobOut {
  return {
    id: "job-1",
    case_id: CASE,
    feature: "financial_flow",
    status: "succeeded",
    idempotency_key: `financial_flow:${CASE}:a1`,
    progress: 100,
    total_records: 6,
    processed_records: 6,
    attempts: 1,
    timeout_seconds: 300,
    cancel_requested: false,
    error: null,
    result_summary: {
      records_scanned: 6,
      facts_extracted: 5,
      currency_buckets: 1,
      network_nodes: 10,
      network_edges: 7,
      patterns_firing: 4,
      patterns_not_evaluable: 5,
      patterns_not_fired: 1,
    },
    evidence_file_id: null,
    actor_id: "user-1",
    started_at: "2026-03-15T10:00:00Z",
    completed_at: "2026-03-15T10:00:02Z",
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:02Z",
    ...overrides,
  };
}

function artifact(payload: Record<string, unknown>, overrides: Partial<DerivedArtifactOut> = {}): DerivedArtifactOut {
  return {
    id: "art-1",
    case_id: CASE,
    kind: "financial_finding",
    origin: "deterministic",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: null,
    payload,
    content_hash: "financial-finding-case-1",
    parser_version: "flow-rules/1.0.0",
    prompt_version: null,
    model_profile: null,
    analysis_job_id: "job-1",
    validation_errors: null,
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:02Z",
    ...overrides,
  };
}

/**
 * Payload numbers mirror the documented ingest shape (exact string amounts,
 * no currency, no timestamps, no payer) so the panel assertions read like the
 * backend contract.
 */
const flowPayload = {
  flow_rules_version: "flow-rules/1.0.0",
  pattern_rules_version: "flow-patterns/1.0.0",
  scope: { records_scanned: 6, records_bounded: false, victim_rows_scanned: 0, flow_max_records: 1000 },
  facts: [
    {
      fact_class: "transaction",
      record_no: 1,
      evidence_file_id: "ev-1",
      source_locator: { record_no: 1, evidence_file_id: "ev-1" },
      txn_ref_original: "TXN-SIH-001",
      amount: "4500.00",
      amount_original: "4500.00",
      amount_precision: "string_source",
      currency: null,
      occurred_at: null,
      account_original: "ACC-SIH-001",
      receiver: "Ananya Sirohi",
      status: "unknown",
      missing: ["currency", "timestamp", "source_direction"],
      limitations: ["currency_unknown", "missing_timestamp", "one_sided"],
    },
  ],
  facts_bounded: false,
  facts_total: 5,
  victim_financials: [],
  aggregates: {
    counts: { facts_total: 5, without_currency: 4, without_timestamp: 4 },
    currency_buckets: [
      {
        currency: null,
        currency_unknown: true,
        count: 4,
        distinct_groups: 3,
        conflicting_groups: [],
        distinct_amounts: 2,
        min: "4500.00",
        max: "12000.00",
        total_records: "25500.00",
        total_distinct: "21000.00",
        total_distinct_conflicts_excluded: 0,
        dedupe_caveat: "both totals are reported together and neither is presented as the unique truth",
        supporting_source_record_ids: ["rec-1", "rec-2", "rec-3", "rec-4"],
      },
    ],
    by_account: [
      {
        account_normalized: "ACCSIH001",
        count: 3,
        total_records: "13500.00",
        supporting_source_record_ids: ["rec-1", "rec-3", "rec-4"],
      },
    ],
    by_bank: [],
    by_merchant: [],
    not_computable: {
      inflow: "not_computable_no_direction",
      outflow: "not_computable_no_direction",
      net: "not_computable_no_direction",
      reason: "no payer-side key exists in any ingested record; these are reported as absent, never as zero",
    },
  },
  structure_network: {
    nodes: [{ id: "account:ACCSIH001", kind: "account", label: "ACC-SIH-001", origin: "record" }],
    edges: [
      {
        source: "account:ACCSIH001",
        target: "merchant:phonepe merchant",
        edge_kind: "association",
        confidence: "suspected",
        derivation: "account_star",
        relationship_type: null,
        supporting_source_record_ids: ["rec-1"],
      },
    ],
    nodes_total: 10,
    edges_total: 7,
    confirmed_transfer_edges: 0,
    transfer_edge_note: "no edge is a confirmed transfer; association edges are candidates for review",
  },
  patterns: {
    firing: [
      {
        rule: "duplicate_amount",
        version: "flow-patterns/1.0.0",
        status: "firing",
        evidence: { amount: "4500.00", record_count: 3 },
        supporting_source_record_ids: ["rec-1", "rec-3", "rec-4"],
        limitations: ["currency_unknown"],
        review_status: "pending_review",
        pattern_not_intent: true,
      },
    ],
    not_fired: ["victim_loss_unmatched"],
    not_evaluable: [
      {
        rule: "circular_path",
        version: "flow-patterns/1.0.0",
        status: "not_evaluable",
        reason: "no_transfer_edges",
        explanation: "requires a cycle of confirmed transfers; no transfer edge exists to traverse",
      },
    ],
  },
  limitations: [
    "no transactions table exists; every fact is a deterministic extraction from source_records.raw_data",
    "no payer/sender key occurs in any record, so direction-dependent metrics are reported not_computable_no_direction",
    "record-level amounts carry no currency attribution; totals are bucketed under currency=null flagged currency_unknown",
  ],
  calculation_definitions: {
    total_records: "sum of exact Decimal amounts over every record carrying an amount, duplicates included",
    total_distinct: "one contribution per distinct transaction group; neither total is the unique truth",
    net_flow: "not computed: direction is absent from the ingest",
  },
};

function queryResult<T extends { items: unknown[] }>(data: T, overrides: Record<string, unknown> = {}) {
  return { data, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...overrides };
}

function mutation<T>(result?: T) {
  return { mutateAsync: vi.fn().mockResolvedValue(result ?? {}), isPending: false, reset: vi.fn() };
}

function renderPanel(panel: ReactElement) {
  return render(
    <MemoryRouter initialEntries={[`/app/cases/${CASE}`]}>
      <TooltipProvider>{panel}</TooltipProvider>
    </MemoryRouter>,
  );
}

function stubAll(overrides: { artifactPayload?: Record<string, unknown> } = {}) {
  const submit = mutation({ job: job(), duplicate: false });
  const review = mutation();
  const cancel = mutation();
  const trace = mutation(associationTrace());
  queries.useIntelJobs.mockReturnValue(queryResult({ items: [job()], total: 1, limit: 100, offset: 0 }));
  queries.useArtifacts.mockReturnValue(
    queryResult({
      items:
        overrides.artifactPayload === undefined
          ? [artifact(flowPayload)]
          : [artifact(overrides.artifactPayload)],
      total: 1,
      limit: 100,
      offset: 0,
    }),
  );
  queries.useSubmitFinancialFlow.mockReturnValue(submit);
  queries.useReviewArtifact.mockReturnValue(review);
  queries.useCancelIntelJob.mockReturnValue(cancel);
  queries.useTraceFinancialFlow.mockReturnValue(trace);
  return { submit, review, cancel, trace };
}

function associationTrace(): FlowTraceResponse {
  return {
    case_id: CASE,
    flow_rules_version: "flow-rules/1.0.0",
    target: "ACC-SIH-001",
    target_kind: "account",
    edge_kind: "association",
    status: "ok",
    reason: null,
    start_node: "account:ACCSIH001",
    matched_facts: 0,
    target_degree: 1,
    paths: [
      {
        nodes: ["account:ACCSIH001", "merchant:phonepe merchant"],
        hops: [
          {
            source: "account:ACCSIH001",
            target: "merchant:phonepe merchant",
            edge_kind: "association",
            derivation: "account_star",
            confidence: "suspected",
            relationship_type: null,
            supporting_source_record_ids: ["rec-1"],
          },
        ],
        depth: 1,
        end_state: "dead_end",
        incomplete: true,
      },
    ],
    paths_bounded: false,
    records_bounded: false,
    bounds: { max_depth: 4, max_paths: 50, max_records: 1000, records_scanned: 6 },
    network: { nodes_total: 10, edges_total: 7, confirmed_transfer_edges: 0 },
    limitations: [
      "every hop is an association, never a confirmed transfer, so a trace answers what else is documented about an account — not where money went",
    ],
  };
}

afterEach(() => {
  permissions.allowed = true;
  vi.clearAllMocks();
});

describe("phase 4 financial flow panel", () => {
  it("empty state explains what the deterministic run would produce", () => {
    stubAll();
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    expect(screen.getByText("No financial finding recorded")).toBeTruthy();
    expect(screen.getByTestId("flow-trace-form")).toBeTruthy();
  });

  it("shows both totals, the unknown currency and the direction refusal — never a fabricated zero", () => {
    stubAll();
    renderPanel(<FinancialFlowPanel caseId={CASE} />);

    const bucket = screen.getByTestId("flow-bucket");
    expect(bucket.textContent).toContain("25500.00"); // total_records (duplicates included)
    expect(bucket.textContent).toContain("21000.00"); // total_distinct (grouped)
    expect(bucket.textContent).toContain("currency unknown");
    expect(bucket.textContent).toContain("both totals are reported together");

    const notComputable = screen.getByTestId("flow-not-computable");
    expect(notComputable.textContent).toContain("not computed — direction is absent from the ingest");
    expect(notComputable.textContent).toContain("never as zero");
    // The word "0" only ever appears as a refusal counter, never as a total.
    expect(screen.queryByText(/^0$/)).toBeNull();
  });

  it("renders facts, association-only structure and pattern rules with their reasons", () => {
    stubAll();
    renderPanel(<FinancialFlowPanel caseId={CASE} />);

    // One fact row: exact amount, original preserved, currency and time absent,
    // payer explicitly marked absent rather than invented.
    const facts = screen.getAllByTestId("flow-fact");
    expect(facts).toHaveLength(1);
    expect(facts[0].textContent).toContain("TXN-SIH-001");
    expect(facts[0].textContent).toContain("4500.00");
    expect(facts[0].textContent).toContain("currency unknown");
    expect(facts[0].textContent).toContain("no time");
    expect(facts[0].textContent).toContain("payer absent → Ananya Sirohi");
    // Source locator stays navigable to the evidence.
    expect(facts[0].querySelector("a")?.getAttribute("href")).toBe(`/app/cases/${CASE}/evidence`);

    // Structure: association edge typed, zero confirmed transfers on screen.
    const edges = screen.getAllByTestId("flow-edge");
    expect(edges).toHaveLength(1);
    expect(edges[0].textContent).toContain("association");
    expect(edges[0].textContent).toContain("suspected");
    expect(screen.getAllByText(/0 confirmed transfer edges/).length).toBeGreaterThan(0);

    // Patterns: the firing rule carries exact evidence; the unevaluable rule
    // states its specific missing input instead of silently disappearing.
    const firing = screen.getAllByTestId("flow-pattern");
    expect(firing).toHaveLength(1);
    expect(firing[0].textContent).toContain("duplicate_amount");
    expect(firing[0].textContent).toContain("4500.00");
    expect(firing[0].textContent).toContain("pattern ≠ intent");
    expect(screen.getByText(/evaluated, no evidence: victim_loss_unmatched/)).toBeTruthy();
    const notEvaluable = screen.getByTestId("flow-pattern-not-evaluable");
    expect(notEvaluable.textContent).toContain("circular_path");
    expect(notEvaluable.textContent).toContain("cannot evaluate: no_transfer_edges");

    // Limitations block is always visible with the direction definition.
    const limitations = screen.getByTestId("flow-limitations");
    expect(limitations.textContent).toContain("no payer/sender key");
    expect(limitations.textContent).toContain("not computed: direction is absent from the ingest");
  });

  it("submit runs the analysis; confirm is one click; dismiss records an optional note", async () => {
    const { submit, review } = stubAll();

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    fireEvent.click(screen.getByRole("button", { name: /run financial analysis/i }));
    await vi.waitFor(() => expect(submit.mutateAsync).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: /confirm finding/i }));
    await vi.waitFor(() =>
      expect(review.mutateAsync).toHaveBeenCalledWith({
        artifactId: "art-1",
        review: { decision: "approved" },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(screen.getByText(/Why is this finding being dismissed/)).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Note"), { target: { value: "amounts verified against the bank" } });
    fireEvent.click(screen.getByRole("button", { name: /record decision/i }));
    await vi.waitFor(() =>
      expect(review.mutateAsync).toHaveBeenCalledWith({
        artifactId: "art-1",
        review: { decision: "rejected", note: "amounts verified against the bank" },
      }),
    );
  });

  it("trace: association paths render typed hops and the incomplete-trail warning", async () => {
    const { trace } = stubAll();

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    fireEvent.change(screen.getByLabelText("Trace target"), { target: { value: "ACC-SIH-001" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /run structure trace/i }));
    });
    expect(trace.mutateAsync).toHaveBeenCalledTimes(1);
    expect(trace.mutateAsync).toHaveBeenCalledWith({
      target: "ACC-SIH-001",
      target_kind: "account",
      edge_kind: "association",
    });

    const result = await screen.findByTestId("flow-trace-result");
    expect(result.textContent).toContain("ok");
    expect(result.textContent).toContain("0 confirmed transfer edges");
    expect(screen.getByTestId("flow-trace-path")).toBeTruthy();
    const hop = screen.getByTestId("flow-trace-hop");
    expect(hop.textContent).toContain("account:ACCSIH001 → merchant:phonepe merchant");
    expect(hop.textContent).toContain("association (suspected) · account_star");
    expect(screen.getByText(/incomplete — trail stops here in the evidence/)).toBeTruthy();
    expect(screen.getByText(/never a confirmed transfer/)).toBeTruthy();
  });

  it("trace: a transfer request is answered as absent data, never approximated", async () => {
    const { trace } = stubAll();
    trace.mutateAsync.mockResolvedValue({
      ...associationTrace(),
      edge_kind: "transfer",
      status: "insufficient_data",
      reason: "no_transfer_edges_in_ingest",
      paths: [],
      limitations: ["no transfer path to return; the trail is reported as absent rather than approximated"],
    });

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    fireEvent.change(screen.getByLabelText("Trace target"), { target: { value: "ACC-SIH-001" } });
    fireEvent.change(screen.getByLabelText("Edge kind"), { target: { value: "transfer" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /run structure trace/i }));
    });

    const result = await screen.findByTestId("flow-trace-result");
    expect(result.textContent).toContain("insufficient data");
    expect(result.textContent).toContain("no transfer edges in ingest");
    expect(result.textContent).toContain("0 confirmed transfer edges");
    expect(screen.queryByTestId("flow-trace-path")).toBeNull();
    expect(trace.mutateAsync).toHaveBeenCalledWith({
      target: "ACC-SIH-001",
      target_kind: "account",
      edge_kind: "transfer",
    });
  });

  it("trace refuses an empty target instead of querying for nothing", () => {
    const { trace } = stubAll();

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    fireEvent.click(screen.getByRole("button", { name: /run structure trace/i }));
    expect(trace.mutateAsync).not.toHaveBeenCalled();
    expect(screen.queryByTestId("flow-trace-result")).toBeNull();
  });

  it("without run or evidence.read permission the controls are hidden, the read-only view stays", () => {
    permissions.allowed = false;
    stubAll();

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    expect(screen.queryByRole("button", { name: /run financial analysis/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /confirm finding/i })).toBeNull();
    expect(screen.queryByTestId("flow-trace-form")).toBeNull();
    // The deterministic finding itself remains readable.
    expect(screen.getByTestId("flow-bucket")).toBeTruthy();
    expect(screen.getByTestId("financial-flow-panel")).toBeTruthy();
  });

  it("a failed artifact query shows retry instead of a silent empty panel", () => {
    stubAll();
    const refetch = vi.fn();
    queries.useArtifacts.mockReturnValue(
      queryResult(
        { items: [], total: 0, limit: 100, offset: 0 },
        { data: undefined, isError: true, error: new Error("boom"), refetch },
      ),
    );

    renderPanel(<FinancialFlowPanel caseId={CASE} />);
    expect(screen.getByText("Unable to load this view")).toBeTruthy();
    expect(screen.queryByText("No financial finding recorded")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
