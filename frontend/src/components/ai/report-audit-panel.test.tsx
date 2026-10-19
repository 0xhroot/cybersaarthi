import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { AnalysisJobOut, DerivedArtifactOut, ReportAuditOut } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useReportAudits: vi.fn(),
  useReportAuditDetail: vi.fn(),
  useSubmitReportAudit: vi.fn(),
  useIntelJobs: vi.fn(),
  useReviewArtifact: vi.fn(),
  useCancelIntelJob: vi.fn(),
}));

const permissions = vi.hoisted(() => ({ allowed: true, reviewAllowed: true }));

vi.mock("@/hooks/queries", () => queries);
vi.mock("@/lib/permissions", () => ({
  useCan: (perm: string) =>
    permissions.allowed && (perm === "findings.review" ? permissions.reviewAllowed : true),
}));

import { ReportAuditPanel } from "@/components/ai/report-audit-panel";

const CASE = "case-1";
const DRAFT =
  "The seller was contacted on 2026-01-20. The account received ₹5,000 on 2026-01-10.";

function queryResult<T>(data: T | undefined, isLoading = false) {
  return { data, isLoading, isError: false, error: null, isFetching: false, isSuccess: !isLoading };
}

function auditJob(overrides: Partial<AnalysisJobOut> = {}): AnalysisJobOut {
  return {
    id: "job-1",
    case_id: CASE,
    feature: "report_audit",
    status: "succeeded",
    idempotency_key: "report_audit:hash:a1",
    progress: 100,
    total_records: 1,
    processed_records: 1,
    attempts: 1,
    timeout_seconds: 300,
    cancel_requested: false,
    error: null,
    result_summary: {
      draft_source_type: "text",
      draft_chars: DRAFT.length,
      claims_extracted: 3,
      claims_truncated: 0,
      claims_invalid: 0,
      citations_checked: 1,
      citations_invalid: 1,
      assessments_attempted: 1,
      assessments_valid: 0,
      assessments_invalid: 1,
      findings_high: 2,
      findings_medium: 1,
      findings_info: 1,
      records_searched: 2,
      counter_matches: 1,
      artifacts_created: 1,
      artifacts_reused: 0,
      artifacts_flagged: 1,
      units_failed: 0,
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

function auditOut(overrides: Partial<ReportAuditOut> = {}): ReportAuditOut {
  return {
    id: "job-1",
    case_id: CASE,
    status: "succeeded",
    created_at: "2026-03-15T10:00:00Z",
    completed_at: "2026-03-15T10:00:02Z",
    error: null,
    draft_source_type: "text",
    draft_hash: "abc12345",
    draft_chars: DRAFT.length,
    conversation_id: null,
    message_id: null,
    artifact_id: "art-1",
    claims: 3,
    stale: null,
    result_summary: auditJob().result_summary,
    ...overrides,
  };
}

function auditArtifact(
  payloadOverrides: Record<string, unknown> = {},
  overrides: Partial<DerivedArtifactOut> = {},
): DerivedArtifactOut {
  return {
    id: "art-1",
    case_id: CASE,
    kind: "report_claim_review",
    origin: "llm",
    status: "pending_review",
    validation_status: "flagged",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: { scope: "report_draft" },
    payload: {
      report_audit: true,
      draft_source: { type: "text" },
      draft_chars: DRAFT.length,
      draft_hash: "abc12345",
      ...payloadOverrides,
      claims: [
        {
          claim_id: "c_late",
          text: "The seller was contacted on 2026-01-20.",
          char_start: 0,
          char_end: 43,
          category: "timeline",
          extraction_valid: true,
          extraction_problems: [],
          citations: [],
          assessment: null,
          assessment_skipped: "no_valid_citation",
          deterministic: { amounts: [], dates: ["2026-01-20"], unparsed_dates: 0, arithmetic: null },
          counter_evidence: { records_searched: 2, note: "no matching records", matches: [] },
          findings: [],
          severity: "none",
        },
        {
          claim_id: "c_total",
          text: "The total of INR 12,000 and INR 8,000 is INR 18,000.",
          char_start: 44,
          char_end: 97,
          category: "quantity",
          extraction_valid: true,
          extraction_problems: [],
          citations: [],
          assessment: null,
          assessment_skipped: "no_valid_citation",
          deterministic: {
            amounts: [
              { raw: "12,000", currency: "INR", value: "12000" },
              { raw: "8,000", currency: "INR", value: "8000" },
              { raw: "18,000", currency: "INR", value: "18000" },
            ],
            dates: [],
            unparsed_dates: 0,
            arithmetic: { ok: false, stated: "18000", computed: "20000" },
          },
          counter_evidence: { records_searched: 2, note: "no matching records", matches: [] },
          findings: [
            {
              code: "numeric_mismatch",
              severity: "high",
              detail: { stated: "18000", computed: "20000" },
            },
          ],
          severity: "high",
        },
        {
          claim_id: "c_received",
          text: "The account received ₹5,000 on 2026-01-10.",
          char_start: 98,
          char_end: 141,
          category: "factual_statement",
          extraction_valid: true,
          extraction_problems: [],
          citations: [
            { cited_id: "evidence:bad", ok: false, codes: ["citation_record_missing"], checked: true },
          ],
          assessment: {
            assessment: "supported",
            explanation: "the ledger says so",
            quotes_verified: false,
            unverified_quotes: ["the account was drained"],
          },
          assessment_skipped: null,
          deterministic: {
            amounts: [{ raw: "5,000", currency: "INR", value: "5000" }],
            dates: ["2026-01-10"],
            unparsed_dates: 0,
            arithmetic: null,
          },
          counter_evidence: {
            records_searched: 2,
            note: "matches are candidates, not contradictions",
            matches: [{ token: "5,000", record_no: 1, evidence: "statement.txt", excerpt: "…" }],
          },
          findings: [
            { code: "invalid_citation", severity: "high", detail: { cited_id: "evidence:bad" } },
            {
              code: "assessment_unverified",
              severity: "medium",
              detail: { unverified_quotes: ["the account was drained"] },
            },
            { code: "counter_evidence_candidate", severity: "info", detail: { token: "5,000" } },
          ],
          severity: "high",
        },
      ],
      counter_evidence: {
        records_searched: 2,
        note: "matches are candidates for review, not contradictions",
      },
      model: { claims_extracted: 3, claims_truncated: 0 },
      rules_version: "1.0.0",
      analysis_scope: "claim checks only: the draft was never filed or executed",
    },
    content_hash: "art-1-hash",
    parser_version: "deterministic:1",
    prompt_version: "1.0.0",
    model_profile: "local-qwen",
    analysis_job_id: "job-1",
    validation_errors: [{ code: "model_claims_unreviewed", field: "claims", value: null }],
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:02Z",
    ...overrides,
  };
}

function mockAudits(items: ReportAuditOut[]) {
  queries.useReportAudits.mockReturnValue(
    queryResult({ items, total: items.length, limit: 50, offset: 0 }),
  );
}

function mockDetail(artifact: DerivedArtifactOut | null, overrides: Partial<ReportAuditOut> = {}) {
  queries.useReportAuditDetail.mockReturnValue(
    queryResult({ ...auditOut(overrides), artifact }),
  );
}

function mockIntelJobs(items: AnalysisJobOut[]) {
  queries.useIntelJobs.mockReturnValue(
    queryResult({ items, total: items.length, limit: 100, offset: 0 }),
  );
}

function renderPanel(draft: string | null = DRAFT) {
  return render(
    <MemoryRouter>
      <ReportAuditPanel caseId={CASE} draft={draft} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  permissions.allowed = true;
  permissions.reviewAllowed = true;
  mockAudits([]);
  mockDetail(null);
  mockIntelJobs([]);
  queries.useReviewArtifact.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  queries.useCancelIntelJob.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  queries.useSubmitReportAudit.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

describe("ReportAuditPanel", () => {
  it("shows deterministic findings per claim with severity and always labels the output unreviewed", () => {
    mockAudits([auditOut()]);
    mockDetail(auditArtifact());

    renderPanel();

    expect(screen.getByText(/unreviewed model output/)).toBeInTheDocument();
    expect(screen.getByText(/never filed or executed/)).toBeInTheDocument();
    expect(screen.getAllByTestId("report-audit-claim")).toHaveLength(3);
    expect(screen.getByText("numeric_mismatch")).toBeInTheDocument();
    expect(screen.getByText("invalid_citation")).toBeInTheDocument();
    expect(screen.getByText("assessment_unverified")).toBeInTheDocument();
    expect(screen.getByText("counter_evidence_candidate")).toBeInTheDocument();
    // the standing review flag is visible
    expect(screen.getByText(/model_claims_unreviewed/)).toBeInTheDocument();
    expect(screen.getByText(/no finding here is trusted/)).toBeInTheDocument();
  });

  it("shows a rejected forged quote as unverified, never as a trusted assessment", () => {
    mockAudits([auditOut()]);
    mockDetail(auditArtifact());

    renderPanel();

    expect(screen.getByText(/forged\/absent quotes rejected/)).toBeInTheDocument();
    // the forged quote is surfaced both in the finding detail and the
    // assessment line - it is evidence of a problem, never a trusted claim
    expect(screen.getAllByText(/the account was drained/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/all quoted spans verified/)).toBeNull();
  });

  it("submits the passed draft text for audit", async () => {
    const submit = vi.fn().mockResolvedValue({ job: auditJob(), duplicate: false });
    queries.useSubmitReportAudit.mockReturnValue({ mutateAsync: submit, isPending: false });
    mockAudits([]);

    renderPanel();
    fireEvent.click(screen.getByTestId("report-audit-run"));

    expect(submit).toHaveBeenCalledWith({ draft_text: DRAFT });
  });

  it("explains that a draft is required before any audit can run", () => {
    mockAudits([]);

    renderPanel(null);

    expect(screen.getByTestId("report-audit-no-draft")).toBeInTheDocument();
    expect(screen.getByTestId("report-audit-run")).toBeDisabled();
    expect(screen.getByText(/No report audits yet/)).toBeInTheDocument();
  });

  it("offers cancel while an audit is active and refuses a second submit", () => {
    mockIntelJobs([auditJob({ status: "running" })]);
    mockAudits([auditOut({ status: "running" })]);
    mockDetail(null, { status: "running" });

    renderPanel();

    expect(screen.getByRole("button", { name: "Auditing\u2026" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(queries.useCancelIntelJob().mutateAsync).toHaveBeenCalledWith("job-1");
  });

  it("marks an audit stale when the referenced draft changed afterwards", () => {
    mockAudits([auditOut({ stale: true })]);
    mockDetail(null, { stale: true });

    renderPanel();

    expect(screen.getByText(/draft changed since this audit/)).toBeInTheDocument();
  });

  it("reports a failed audit's refusal without hiding the run button", () => {
    mockAudits([auditOut({ status: "failed", error: "REPORT_AUDIT_FAILED" })]);
    mockDetail(null, { status: "failed", error: "REPORT_AUDIT_FAILED" });

    renderPanel();

    expect(screen.getByText(/Audit refused/)).toBeInTheDocument();
    expect(screen.getByText("REPORT_AUDIT_FAILED")).toBeInTheDocument();
    expect(screen.getByTestId("report-audit-run")).toBeEnabled();
  });

  it("labels a partial audit while keeping the deterministic findings visible", () => {
    mockAudits([auditOut({ status: "partial" })]);
    mockDetail(auditArtifact(), { status: "partial" });

    renderPanel();

    expect(screen.getByText(/Partial audit/)).toBeInTheDocument();
    expect(screen.getAllByTestId("report-audit-claim")).toHaveLength(3);
  });

  it("hides run and review controls without permissions", () => {
    permissions.allowed = false;
    mockAudits([auditOut()]);
    mockDetail(auditArtifact());

    renderPanel();

    expect(screen.queryByTestId("report-audit-run")).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
    expect(screen.getAllByTestId("report-audit-claim")).toHaveLength(3);
  });

  it("hides review controls without findings.review", () => {
    permissions.reviewAllowed = false;
    mockAudits([auditOut()]);
    mockDetail(auditArtifact());

    renderPanel();

    expect(screen.getByTestId("report-audit-run")).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("requires a written reason before a rejection is recorded", () => {
    const review = vi.fn().mockResolvedValue(auditArtifact());
    queries.useReviewArtifact.mockReturnValue({ mutateAsync: review, isPending: false });
    mockAudits([auditOut()]);
    mockDetail(auditArtifact());

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    const record = screen.getByRole("button", { name: /Record decision/ });
    expect(record).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("Rejection reason"), {
      target: { value: "the cited record does not support the total" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Record decision/ }));

    expect(review).toHaveBeenCalledWith({
      artifactId: "art-1",
      review: { decision: "rejected", note: "the cited record does not support the total" },
    });
  });
});
