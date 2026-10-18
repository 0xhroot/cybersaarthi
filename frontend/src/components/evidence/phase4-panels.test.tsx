import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

import type { AnalysisJobOut, CustodyExplainResponse, DerivedArtifactOut, FlowTraceResponse } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useIntelJobs: vi.fn(),
  useArtifacts: vi.fn(),
  useSubmitFinancialFlow: vi.fn(),
  useReviewArtifact: vi.fn(),
  useCancelIntelJob: vi.fn(),
  useTraceFinancialFlow: vi.fn(),
  useCases: vi.fn(),
  useCrossCaseCandidates: vi.fn(),
  useSubmitCrossCase: vi.fn(),
  useExplainFinding: vi.fn(),
}));

const permissions = vi.hoisted(() => ({ allowed: true, reviewAllowed: true }));

vi.mock("@/hooks/queries", () => queries);
vi.mock("@/lib/permissions", () => ({
  useCan: (perm: string) =>
    permissions.allowed && (perm === "findings.review" ? permissions.reviewAllowed : true),
}));

import { CrossCasePanel } from "@/components/evidence/cross-case-panel";
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
  permissions.reviewAllowed = true;
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

/* --------------------------- cross-case panel (feature B) --------------------------- */

const CASE_TWO = "case-2";

function crossCasePayload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    crosscase_rules_version: "crosscase/1.0.0",
    scope: { case_ids: [CASE, CASE_TWO], scope_hash: "scope-abc", cases_in_group: [CASE, CASE_TWO] },
    group: { indicator_kind: "account_ref", value_normalized: "ACCSIH001" },
    classification: "normalized_identifier",
    classification_semantics: {
      normalized_identifier: "a shared identifier after deterministic normalization; stronger than a name-only match",
    },
    score: 78,
    score_semantics:
      "0–100 additive signal band, NOT a probability; only a review decision can become an authoritative link",
    signal_kinds: ["account_ref"],
    additional_shared_kinds: ["email_domain"],
    conflicting_attributes: {
      flagged: true,
      evidence: [{ kind: "city", per_case_values: { [CASE]: ["Pune"], [CASE_TWO]: ["Mumbai"] } }],
    },
    sides: [
      {
        case_id: CASE,
        value_originals: ["ACC-SIH-001"],
        entity_ids: ["ent-1"],
        source_record_ids: ["rec-1", "rec-2"],
        evidence_file_ids: ["ev-1"],
        contributing_kinds: ["account_ref"],
        reviewed_alias: false,
      },
      {
        case_id: CASE_TWO,
        value_originals: ["ACCSIH001"],
        entity_ids: ["ent-2"],
        source_record_ids: ["rec-9"],
        contributing_kinds: ["account_ref"],
        reviewed_alias: true,
      },
    ],
    reviewable: true,
    review_disabled_reason: null,
    limitations: ["a candidate is a discovery signal, not evidence of a shared incident"],
    graph_freshness_note: "Discovery reads only authorized records; it does not depend on the Neo4j projection.",
    ...overrides,
  };
}

function crossCaseArtifact(overrides: Record<string, unknown> = {}, artifactOverrides: Partial<DerivedArtifactOut> = {}) {
  return artifact(crossCasePayload(overrides), {
    id: "art-cc-1",
    kind: "cross_case_link",
    content_hash: "cross-case-case-1",
    parser_version: "crosscase/1.0.0",
    ...artifactOverrides,
  });
}

function scopeCases() {
  return queryResult({
    items: [
      { id: CASE, case_number: "CS-1", title: "Paper Citadel", description: null, status: "open", owner_id: "u-1", created_at: "2026-03-15T10:00:00Z", updated_at: "2026-03-15T10:00:00Z" },
      { id: CASE_TWO, case_number: "CS-2", title: "Skyline Imports", description: null, status: "open", owner_id: "u-1", created_at: "2026-03-15T10:00:00Z", updated_at: "2026-03-15T10:00:00Z" },
    ],
    total: 2,
    limit: 100,
    offset: 0,
  });
}

function crossCaseList(payloadArtifact: DerivedArtifactOut) {
  return queryResult({
    items: [payloadArtifact],
    total: 1,
    anchor_case_id: CASE,
    crosscase_rules_version: "crosscase/1.0.0",
    graph_freshness_note: "Discovery reads only authorized records; it does not depend on the Neo4j projection.",
  });
}

function explainMutation(response?: CustodyExplainResponse) {
  return {
    isPending: false,
    error: null,
    mutate: vi.fn((_id: string, opts?: { onSuccess?: (r: CustodyExplainResponse) => void }) => {
      if (response && opts?.onSuccess) opts.onSuccess(response);
    }),
    reset: vi.fn(),
  };
}

function stubCrossCase(overrides: {
  artifactPayload?: Record<string, unknown>;
  artifact?: DerivedArtifactOut;
  explain?: ReturnType<typeof explainMutation>;
  job?: AnalysisJobOut;
} = {}) {
  const submit = mutation({ job: job({ feature: "cross_case" }), duplicate: false });
  const review = mutation();
  const cancel = mutation();
  const candidate = overrides.artifact ?? crossCaseArtifact(overrides.artifactPayload ?? {});
  queries.useIntelJobs.mockReturnValue(
    queryResult({ items: overrides.job ? [overrides.job] : [], total: overrides.job ? 1 : 0, limit: 100, offset: 0 }),
  );
  queries.useCases.mockReturnValue(scopeCases());
  queries.useCrossCaseCandidates.mockReturnValue(crossCaseList(candidate));
  queries.useSubmitCrossCase.mockReturnValue(submit);
  queries.useReviewArtifact.mockReturnValue(review);
  queries.useCancelIntelJob.mockReturnValue(cancel);
  queries.useExplainFinding.mockReturnValue(overrides.explain ?? explainMutation());
  return { submit, review, cancel, candidate };
}

describe("phase 4 cross-case panel", () => {
  it("empty state explains the discovery contract: candidates, not automatic links", () => {
    stubCrossCase();
    queries.useCrossCaseCandidates.mockReturnValue(
      queryResult({ items: [], total: 0, anchor_case_id: CASE, crosscase_rules_version: "crosscase/1.0.0", graph_freshness_note: "note" }),
    );

    renderPanel(<CrossCasePanel caseId={CASE} />);
    expect(screen.getByText("No cross-case candidates")).toBeTruthy();
    expect(screen.getByTestId("cross-case-scope")).toBeTruthy();
  });

  it("renders the candidate with its score semantics, sides and conflict flags — never a probability", () => {
    stubCrossCase();
    renderPanel(<CrossCasePanel caseId={CASE} />);

    const candidate = screen.getByTestId("cross-case-candidate");
    expect(candidate.textContent).toContain("account_ref");
    expect(candidate.textContent).toContain("ACCSIH001");
    expect(candidate.textContent).toContain("normalized identifier");
    expect(candidate.textContent).toContain("score 78 / 100");
    // The score band ships with its explicit non-probability semantics.
    expect(candidate.textContent).toContain("NOT a probability");

    // Both permitted sides render with original values and record links.
    const sides = screen.getAllByTestId("cross-case-side");
    expect(sides).toHaveLength(2);
    expect(sides[0].textContent).toContain("ACC-SIH-001");
    expect(sides[0].textContent).toContain("rec-1, rec-2");
    expect(sides[0].querySelector("a")?.getAttribute("href")).toBe(`/app/cases/${CASE}/evidence`);
    expect(sides[1].textContent).toContain("reviewed alias");

    // Conflict flags are surfaced, with per-case values.
    const conflict = screen.getByTestId("cross-case-conflict");
    expect(conflict.textContent).toContain("city");
    expect(conflict.textContent).toContain("Pune");
    expect(conflict.textContent).toContain("Mumbai");

    // Graph freshness note states discovery does not depend on the projection.
    const note = screen.getByTestId("cross-case-graph-note");
    expect(note.textContent).toContain("does not depend on the Neo4j projection");
  });

  it("discovery stays disabled below the scope minimum and submits the explicit scope", async () => {
    const { submit } = stubCrossCase();

    renderPanel(<CrossCasePanel caseId={CASE} />);
    const run = screen.getByRole("button", { name: /run cross-case discovery/i });
    expect(run.hasAttribute("disabled")).toBe(true); // anchor alone is not a scope

    fireEvent.click(screen.getByLabelText("Include case CS-2"));
    expect(run.hasAttribute("disabled")).toBe(false);
    await act(async () => {
      fireEvent.click(run);
    });
    await vi.waitFor(() => expect(submit.mutateAsync).toHaveBeenCalledWith([CASE, CASE_TWO]));
  });

  it("approval records a reviewed relationship — the copy never promises a merge", async () => {
    const { review } = stubCrossCase();

    renderPanel(<CrossCasePanel caseId={CASE} />);
    fireEvent.click(screen.getByRole("button", { name: /approve cross-case link/i }));
    await vi.waitFor(() =>
      expect(review.mutateAsync).toHaveBeenCalledWith({
        artifactId: "art-cc-1",
        review: { decision: "approved" },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /reject cross-case link/i }));
    await vi.waitFor(() =>
      expect(review.mutateAsync).toHaveBeenCalledWith({
        artifactId: "art-cc-1",
        review: { decision: "rejected" },
      }),
    );
    // The candidate framing is visible on every card.
    expect(screen.getAllByText(/recorded, never merged/).length).toBeGreaterThan(0);
  });

  it("a reviewed candidate shows its status and loses the review actions", () => {
    stubCrossCase({
      artifact: crossCaseArtifact({}, {
        status: "approved",
        reviewed_at: "2026-03-15T11:00:00Z",
        review_note: "verified against bank records",
      }),
    });

    renderPanel(<CrossCasePanel caseId={CASE} />);
    expect(screen.getByText("reviewed link")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /approve cross-case link/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reject cross-case link/i })).toBeNull();
  });

  it("a name-only candidate is informational: no review actions, the reason is shown", () => {
    stubCrossCase({
      artifactPayload: {
        classification: "similarity_name_only",
        reviewable: false,
        review_disabled_reason: "name-only match: review requires a stronger signal",
      },
    });

    renderPanel(<CrossCasePanel caseId={CASE} />);
    expect(screen.getByText("informational only")).toBeTruthy();
    expect(screen.getByText(/name-only match/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /approve cross-case link/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reject cross-case link/i })).toBeNull();
    // Explaining is still available: narration does not turn it into a link.
    expect(screen.getByRole("button", { name: /explain cross-case candidate/i })).toBeTruthy();
  });

  it("explain renders the structured narration flagged as unverified AI output", async () => {
    const explain = explainMutation({
      explanation_artifact: crossCaseArtifact({ type: "ai_explanation" }, { id: "art-cc-child", origin: "llm" }),
      text: "Both cases carry the shared account_ref ACC-SIH-001; this is a candidate link, not proof of a shared incident.",
      rule: "",
      explanation: {
        summary: "Both cases carry the shared account_ref ACC-SIH-001; this is a candidate link, not proof of a shared incident.",
        matching_signal: "identifier account_ref, classification normalized_identifier",
        cited_identifiers: ["ACC-SIH-001"],
        conflicts: [],
        not_established: ["that the cases are the same incident", "that any transfer occurred between them"],
        verification_steps: ["Confirm the account holder on both sides"],
      },
    });
    stubCrossCase({ explain });

    renderPanel(<CrossCasePanel caseId={CASE} />);
    fireEvent.click(screen.getByRole("button", { name: /explain cross-case candidate/i }));
    await vi.waitFor(() => expect(explain.mutate).toHaveBeenCalledWith("art-cc-1", expect.anything()));

    const block = await screen.findByTestId("cross-case-explanation");
    expect(block.textContent).toContain("AI narration · unverified");
    expect(block.textContent).toContain("ACC-SIH-001");
    expect(block.textContent).toContain("does not establish: that the cases are the same incident");
    expect(block.textContent).toContain("next check: Confirm the account holder on both sides");
  });

  it("job summary shows the bounded scope outcome and an active run can be canceled", () => {
    stubCrossCase({
      job: job({
        feature: "cross_case",
        status: "running",
        result_summary: {
          cases_scanned: 2,
          candidates_found: 1,
          candidates_pending_review: 1,
          cases_inaccessible: 1,
        },
      }),
    });

    renderPanel(<CrossCasePanel caseId={CASE} />);
    const summary = screen.getByTestId("cross-case-summary");
    expect(summary.textContent).toContain("2 cases");
    expect(summary.textContent).toContain("1 candidates");
    expect(summary.textContent).toContain("1 inaccessible (scope enforced)");
    expect(screen.getByRole("button", { name: /cancel discovery/i })).toBeTruthy();
    // One run per anchor: the submit control shows progress and stays disabled.
    const run = screen.getByRole("button", { name: /run cross-case discovery/i });
    expect(run.hasAttribute("disabled")).toBe(true);
  });

  it("without crosscase.read the panel does not render at all", () => {
    permissions.allowed = false;
    stubCrossCase();

    renderPanel(<CrossCasePanel caseId={CASE} />);
    expect(screen.queryByTestId("cross-case-panel")).toBeNull();
    expect(screen.queryByTestId("cross-case-candidate")).toBeNull();
    expect(screen.queryByTestId("cross-case-scope")).toBeNull();
  });

  it("without findings.review the candidate stays readable but not reviewable", () => {
    permissions.reviewAllowed = false;
    stubCrossCase();

    renderPanel(<CrossCasePanel caseId={CASE} />);
    expect(screen.getByTestId("cross-case-candidate")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /approve cross-case link/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reject cross-case link/i })).toBeNull();
    expect(screen.getByRole("button", { name: /explain cross-case candidate/i })).toBeTruthy();
  });
});
