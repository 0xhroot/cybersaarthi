import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import type { AnalysisJobOut, CustodyChronologyResponse, CustodyExplainResponse, DerivedArtifactOut, IntegrityVerificationResponse, JobSubmitResponse } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useIntelJobs: vi.fn(),
  useArtifacts: vi.fn(),
  useExtractEvidence: vi.fn(),
  useReviewArtifact: vi.fn(),
  useCancelIntelJob: vi.fn(),
  useCustodyChronology: vi.fn(),
  useVerifyIntegrity: vi.fn(),
  useCustodyAudit: vi.fn(),
  useRecordCustodyEvent: vi.fn(),
  useExplainFinding: vi.fn(),
}));

vi.mock("@/hooks/queries", () => queries);
vi.mock("@/lib/permissions", () => ({ useCan: () => true }));

import { ExtractionPanel } from "@/components/evidence/extraction-panel";
import { IntegrityPanel } from "@/components/evidence/integrity-panel";

const CASE = "case-1";
const EVIDENCE = "ev-1";

function job(overrides: Partial<AnalysisJobOut> = {}): AnalysisJobOut {
  return {
    id: "job-1",
    case_id: CASE,
    feature: "ingestion",
    status: "succeeded",
    idempotency_key: "k",
    progress: 100,
    total_records: 1,
    processed_records: 1,
    attempts: 1,
    timeout_seconds: 600,
    cancel_requested: false,
    error: null,
    result_summary: { fields_verified: 11 },
    evidence_file_id: EVIDENCE,
    actor_id: null,
    started_at: null,
    completed_at: null,
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
    ...overrides,
  };
}

function artifact(overrides: Partial<DerivedArtifactOut> = {}): DerivedArtifactOut {
  return {
    id: "art-1",
    case_id: CASE,
    kind: "extraction",
    origin: "llm",
    status: "pending_review",
    validation_status: "flagged",
    evidence_file_id: EVIDENCE,
    source_record_id: null,
    source_locator: { unit_index: 0 },
    payload: { fields: { person_names: ["Rajesh Kumar"], statements: ["payment was made promptly"] } },
    content_hash: "h",
    parser_version: "mock:1",
    prompt_version: "1.0.0",
    model_profile: "mock",
    analysis_job_id: "job-1",
    validation_errors: [{ field: "statements", code: "value_not_in_source", message: "not in source" }],
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
    ...overrides,
  };
}

function emptyList<T>(): { items: T[]; total: number; limit: number; offset: number } {
  return { items: [], total: 0, limit: 100, offset: 0 };
}

function mutation<T>(result?: T) {
  return { mutateAsync: vi.fn().mockResolvedValue(result), isPending: false };
}

function stubQueries() {
  queries.useIntelJobs.mockReturnValue({ data: emptyList<AnalysisJobOut>(), isLoading: false });
  queries.useArtifacts.mockReturnValue({ data: emptyList<DerivedArtifactOut>(), isLoading: false });
  queries.useExtractEvidence.mockReturnValue(mutation<JobSubmitResponse>());
  queries.useReviewArtifact.mockReturnValue(mutation<DerivedArtifactOut>());
  queries.useCancelIntelJob.mockReturnValue(mutation<AnalysisJobOut>());
  queries.useCustodyChronology.mockReturnValue({ data: undefined, isLoading: false });
  queries.useVerifyIntegrity.mockReturnValue(mutation<IntegrityVerificationResponse>());
  queries.useCustodyAudit.mockReturnValue(mutation<JobSubmitResponse>());
  queries.useRecordCustodyEvent.mockReturnValue(mutation());
  queries.useExplainFinding.mockReturnValue(mutation<CustodyExplainResponse>());
}

describe("ExtractionPanel", () => {
  it("surfaces flagged validation errors instead of hiding them behind a badge", () => {
    stubQueries();
    queries.useArtifacts.mockReturnValue({
      data: { ...emptyList<DerivedArtifactOut>(), items: [artifact()], total: 1 },
      isLoading: false,
    });
    render(<ExtractionPanel caseId={CASE} evidenceId={EVIDENCE} />);
    expect(screen.getByText("Needs review")).toBeTruthy();
    expect(screen.getByText(/1 flagged/)).toBeTruthy();
    expect(screen.getByText(/value_not_in_source/)).toBeTruthy();
    // The model-provenance label is explicit.
    expect(screen.getByText("model extraction")).toBeTruthy();
  });

  it("hides review controls until the artifact is pending and shows the empty state otherwise", () => {
    stubQueries();
    render(<ExtractionPanel caseId={CASE} evidenceId={EVIDENCE} />);
    expect(screen.getByText("No extraction yet")).toBeTruthy();
    expect(screen.queryByText("Approve")).toBeNull();
  });

  it("shows cancel for a running job", () => {
    stubQueries();
    queries.useIntelJobs.mockReturnValue({
      data: { ...emptyList<AnalysisJobOut>(), items: [job({ status: "running" })], total: 1 },
      isLoading: false,
    });
    render(<ExtractionPanel caseId={CASE} evidenceId={EVIDENCE} />);
    expect(screen.getByText("Extracting…")).toBeTruthy();
    expect(screen.getByText("Cancel")).toBeTruthy();
  });
});

describe("IntegrityPanel", () => {
  function chronology(events: CustodyChronologyResponse["events"]): CustodyChronologyResponse {
    return {
      evidence_id: EVIDENCE,
      original_filename: "a.csv",
      sha256: "ab".repeat(32),
      algorithm: "sha256",
      format: "csv",
      file_size: 10,
      created_at: "2026-01-01T00:00:00Z",
      deleted_at: null,
      events,
      event_count: events.length,
    };
  }

  it("renders a mismatch as a red failure with explicit 'no longer hash' language", async () => {
    stubQueries();
    const result: IntegrityVerificationResponse = {
      evidence_id: EVIDENCE,
      artifact_id: "art-9",
      status: "mismatch",
      algorithm: "sha256",
      expected_sha256: "ab".repeat(32),
      calculated_sha256: "cd".repeat(32),
      object_present: true,
      file_size_bytes: 10,
      duration_ms: 2,
      verified_at: "2026-01-15T10:00:00Z",
    };
    queries.useVerifyIntegrity.mockReturnValue(mutation(result));
    render(<IntegrityPanel caseId={CASE} evidenceId={EVIDENCE} />);
    fireEvent.click(screen.getByText("Verify"));
    expect(await screen.findByText("Digest MISMATCH")).toBeTruthy();
    expect(screen.getByText(/no longer hash/)).toBeTruthy();
  });

  it("renders missing source bytes as cannot-verify, never as a pass", async () => {
    stubQueries();
    const result: IntegrityVerificationResponse = {
      evidence_id: EVIDENCE,
      artifact_id: "art-9",
      status: "missing_source",
      algorithm: "sha256",
      expected_sha256: "ab".repeat(32),
      calculated_sha256: null,
      object_present: false,
      file_size_bytes: null,
      duration_ms: 1,
      verified_at: "2026-01-15T10:00:00Z",
    };
    queries.useVerifyIntegrity.mockReturnValue(mutation(result));
    render(<IntegrityPanel caseId={CASE} evidenceId={EVIDENCE} />);
    fireEvent.click(screen.getByText("Verify"));
    expect(await screen.findByText("Cannot verify")).toBeTruthy();
    expect(screen.getByText(/This is not a pass/)).toBeTruthy();
  });

  it("states that an empty custody log is not evidence of integrity", () => {
    stubQueries();
    queries.useCustodyChronology.mockReturnValue({ data: chronology([]), isLoading: false });
    render(<IntegrityPanel caseId={CASE} evidenceId={EVIDENCE} />);
    expect(screen.getByText(/absence of events is not evidence of integrity/)).toBeTruthy();
  });

  it("labels the AI explanation as unverified and non-certifying", async () => {
    stubQueries();
    const finding = artifact({
      id: "find-1",
      kind: "custody_finding",
      payload: { type: "custody_finding", rule: "custody.unacknowledged_transfer", message: "transfer has no received event" },
      validation_errors: null,
      validation_status: "valid",
      origin: "deterministic",
    });
    const explanation = artifact({
      id: "expl-1",
      kind: "custody_finding",
      origin: "llm",
      status: "recorded",
      validation_status: "flagged",
      parent_artifact_id: "find-1",
      payload: { type: "ai_explanation", text: "Facts-only narration." },
      validation_errors: [{ field: "text", code: "ai_unverified", message: "unverified" }],
    });
    queries.useArtifacts.mockReturnValue({
      data: { ...emptyList<DerivedArtifactOut>(), items: [explanation, finding], total: 2 },
      isLoading: false,
    });
    queries.useCustodyChronology.mockReturnValue({
      data: chronology([
        {
          id: "evt-1",
          case_id: CASE,
          evidence_file_id: EVIDENCE,
          event_type: "transferred",
          occurred_at: "2026-01-10T00:00:00Z",
          recorded_at: "2026-01-10T00:00:00Z",
          actor_user_id: null,
          collector: null,
          transferor: "Insp. Verma",
          recipient: "Lab",
          location: null,
          method: null,
          notes: null,
          recorded_sha256: null,
        },
      ]),
      isLoading: false,
    });
    queries.useExplainFinding.mockReturnValue(
      mutation<CustodyExplainResponse>({
        explanation_artifact: explanation,
        text: "Facts-only narration.",
        rule: "custody.unacknowledged_transfer",
      }),
    );
    render(<IntegrityPanel caseId={CASE} evidenceId={EVIDENCE} />);
    expect(screen.getByText("custody.unacknowledged_transfer")).toBeTruthy();
    expect(screen.getByText("deterministic rule engine")).toBeTruthy();
    fireEvent.click(screen.getByText("Explain"));
    expect(await screen.findByText(/AI narration — unverified, does not certify custody/)).toBeTruthy();
    expect(screen.getByText("Facts-only narration.")).toBeTruthy();
  });
});
