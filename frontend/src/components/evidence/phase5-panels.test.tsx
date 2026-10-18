import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { AnalysisJobOut, DerivedArtifactOut, SourceRecordOut } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useIntelJobs: vi.fn(),
  useArtifacts: vi.fn(),
  useMultilingual: vi.fn(),
  useExtractEvidence: vi.fn(),
  useReviewArtifact: vi.fn(),
  useCancelIntelJob: vi.fn(),
  useSourceRecords: vi.fn(),
}));

const permissions = vi.hoisted(() => ({ allowed: true, reviewAllowed: true }));

vi.mock("@/hooks/queries", () => queries);
vi.mock("@/lib/permissions", () => ({
  useCan: (perm: string) =>
    permissions.allowed && (perm === "findings.review" ? permissions.reviewAllowed : true),
}));

import { ExtractionPanel } from "@/components/evidence/extraction-panel";
import { MultilingualPanel } from "@/components/evidence/multilingual-panel";

const CASE = "case-1";
const EV = "ev-1";
const HINDI = "मैंने राहुल शर्मा को ५,००० रुपये नहीं दिए। खाता संख्या ACC-7781 से भुगतान हुआ।";

function queryResult<T>(data: T | undefined, isLoading = false) {
  return { data, isLoading, isError: false, error: null, isFetching: false, isSuccess: !isLoading };
}

function job(overrides: Partial<AnalysisJobOut> = {}): AnalysisJobOut {
  return {
    id: "job-1",
    case_id: CASE,
    feature: "multilingual",
    status: "succeeded",
    idempotency_key: `multilingual:${EV}:a1`,
    progress: 100,
    total_records: 1,
    processed_records: 1,
    attempts: 1,
    timeout_seconds: 300,
    cancel_requested: false,
    error: null,
    result_summary: {
      units_total: 1,
      artifacts_created: 1,
      translations_created: 1,
      language_ambiguous: 0,
      values_total: 4,
      values_verified: 4,
    },
    evidence_file_id: EV,
    actor_id: "user-1",
    started_at: "2026-03-15T10:00:00Z",
    completed_at: "2026-03-15T10:00:02Z",
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:02Z",
    ...overrides,
  };
}

function artifact(
  payload: Record<string, unknown>,
  overrides: Partial<DerivedArtifactOut> = {},
): DerivedArtifactOut {
  return {
    id: "art-1",
    case_id: CASE,
    kind: "extraction",
    origin: "llm",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: EV,
    source_record_id: null,
    source_locator: { record_no: 1, field: "text" },
    payload,
    content_hash: "art-1-hash",
    parser_version: "deterministic:1",
    prompt_version: "1.0.0",
    model_profile: "local-qwen",
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

function analysisArtifact(
  payloadOverrides: Record<string, unknown> = {},
  overrides: Partial<DerivedArtifactOut> = {},
): DerivedArtifactOut {
  return artifact(
    {
      multilingual: true,
      language: "hindi",
      script_profile: { candidate: "devanagari", devanagari_ratio: 0.88, latin_ratio: 0.11 },
      language_consistent: true,
      fields: { person_names: ["राहुल शर्मा"], amounts: ["५,०००"], negations: ["नहीं दिए"] },
      ambiguity_flags: [{ flag: "devanagari_digits", detail: "verify the exact figure" }],
      record_no: 1,
      ...payloadOverrides,
    },
    { id: "art-analysis", ...overrides },
  );
}

function translationArtifact(
  payloadOverrides: Record<string, unknown> = {},
  overrides: Partial<DerivedArtifactOut> = {},
): DerivedArtifactOut {
  return artifact(
    {
      source_language: "hindi",
      translated_text: "I did not give Rahul Sharma any rupees. Payment was made from account ACC-7781.",
      material_check: {
        material_total: 2,
        material_preserved: 1,
        material_missing: ["5,000"],
        preserved: false,
      },
      negation_preserved: false,
      record_no: 1,
      ...payloadOverrides,
    },
    {
      id: "art-translation",
      kind: "translation",
      validation_status: "flagged",
      validation_errors: [{ code: "material_value_missing", value: "5,000" }],
      ...overrides,
    },
  );
}

function record(): SourceRecordOut {
  return { id: "srec-1", evidence_file_id: EV, record_no: 1, raw_data: { text: HINDI } };
}

function mockJobs(items: AnalysisJobOut[]) {
  queries.useIntelJobs.mockReturnValue(queryResult({ items, total: items.length, limit: 100, offset: 0 }));
}

function mockArtifacts(extractions: DerivedArtifactOut[], translations: DerivedArtifactOut[]) {
  queries.useArtifacts.mockImplementation((_caseId: string, kind?: string) =>
    kind === "translation"
      ? queryResult({ items: translations, total: translations.length, limit: 100, offset: 0 })
      : queryResult({ items: extractions, total: extractions.length, limit: 100, offset: 0 }),
  );
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <MultilingualPanel caseId={CASE} evidenceId={EV} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  permissions.allowed = true;
  permissions.reviewAllowed = true;
  mockJobs([]);
  mockArtifacts([], []);
  queries.useSourceRecords.mockReturnValue(queryResult({ items: [], total: 0, limit: 50, offset: 0 }));
  queries.useMultilingual.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ job: job(), duplicate: false }),
    isPending: false,
  });
  queries.useExtractEvidence.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ job: job(), duplicate: false }),
    isPending: false,
  });
  queries.useReviewArtifact.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(artifact({})),
    isPending: false,
  });
  queries.useCancelIntelJob.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(job()),
    isPending: false,
  });
});

describe("MultilingualPanel", () => {
  it("shows the verbatim original beside the model label, script profile and flags", () => {
    queries.useSourceRecords.mockReturnValue(
      queryResult({ items: [record()], total: 1, limit: 50, offset: 0 }),
    );
    mockJobs([job()]);
    mockArtifacts([analysisArtifact()], [translationArtifact()]);

    renderPanel();

    // Original viewer: verbatim source, explicitly labeled as unmodified.
    expect(screen.getByText(/Original record #1 — verbatim source, never modified/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(HINDI.slice(0, 18)))).toBeInTheDocument();
    // Model output is clearly labeled and never presented as the original.
    expect(screen.getByText(/hindi \(model label\)/)).toBeInTheDocument();
    expect(screen.getByText(/script: devanagari/)).toBeInTheDocument();
    // Deterministic ambiguity flags with detail are visible.
    expect(screen.getByText(/devanagari_digits/)).toBeInTheDocument();
    expect(screen.getByText(/verify the exact figure/)).toBeInTheDocument();
    // Extracted source-verified fields are rendered.
    expect(screen.getByText(/person_names/)).toBeInTheDocument();
    // The value appears in both the original text and the extracted fields.
    expect(screen.getAllByText(/राहुल शर्मा/).length).toBeGreaterThanOrEqual(2);
  });

  it("keeps the generated translation visually separate and flags its losses", () => {
    queries.useSourceRecords.mockReturnValue(
      queryResult({ items: [record()], total: 1, limit: 50, offset: 0 }),
    );
    mockArtifacts([analysisArtifact()], [translationArtifact()]);

    renderPanel();

    // Both original and translation are on screen at once, never merged.
    expect(screen.getByText(new RegExp(HINDI.slice(0, 18)))).toBeInTheDocument();
    const card = screen.getByTestId("translation-card");
    expect(card).toHaveTextContent(/machine translation · unreviewed/);
    expect(card).toHaveTextContent(/from hindi/);
    expect(card).toHaveTextContent(/Material values: 1\/2 preserved/);
    expect(card).toHaveTextContent(/translation is lossy/);
    expect(card).toHaveTextContent(/Negation not preserved/);
    expect(card).toHaveTextContent(/material_value_missing/);
  });

  it("surfaces a language/script disagreement as a review warning", () => {
    mockArtifacts([analysisArtifact({ language: "english", language_consistent: false })], []);

    renderPanel();

    expect(screen.getByText(/disagrees with the deterministic script evidence/)).toBeInTheDocument();
    // The model's claim is preserved, not overwritten.
    expect(screen.getByText(/english \(model label\)/)).toBeInTheDocument();
  });

  it("always shows flagged validation errors (withheld injected values)", () => {
    mockArtifacts(
      [
        analysisArtifact(
          { fields: { person_names: ["Asha Verma"] } },
          {
            validation_status: "flagged",
            validation_errors: [
              {
                field: "person_names",
                value: "John Doe",
                code: "value_in_injected_context",
              },
            ],
          },
        ),
      ],
      [],
    );

    renderPanel();

    expect(screen.getByText(/1 flagged/)).toBeInTheDocument();
    expect(screen.getByText(/value_in_injected_context/)).toBeInTheDocument();
    expect(screen.getByText(/John Doe/)).toBeInTheDocument();
    // The source-anchored value is still visible for the reviewer.
    expect(screen.getByText(/Asha Verma/)).toBeInTheDocument();
  });

  it("submits an analysis with the translate opt-in", async () => {
    const submit = vi.fn().mockResolvedValue({ job: job(), duplicate: false });
    queries.useMultilingual.mockReturnValue({ mutateAsync: submit, isPending: false });

    renderPanel();

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));

    expect(submit).toHaveBeenCalledWith({ evidenceFileId: EV, translate: true });
  });

  it("offers cancel while a run is active and refuses a second submit", () => {
    mockJobs([job({ status: "running" })]);

    renderPanel();

    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyzing…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(queries.useCancelIntelJob().mutateAsync).toHaveBeenCalledWith("job-1");
  });

  it("shows a failed run's typed refusal without hiding the run button", () => {
    mockJobs([
      job({ status: "failed", error: "LANGUAGE_UNSUPPORTED: complaint uses an unsupported script" }),
    ]);

    renderPanel();

    expect(screen.getByText(/Run refused/)).toBeInTheDocument();
    expect(screen.getByText(/LANGUAGE_UNSUPPORTED/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run analysis/ })).toBeEnabled();
  });

  it("hides review controls without findings.review permission", () => {
    permissions.reviewAllowed = false;
    mockArtifacts([analysisArtifact()], []);

    renderPanel();

    expect(screen.getByText(/person_names/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit fields" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("approves a validated analysis with a recorded decision", async () => {
    const review = vi.fn().mockResolvedValue(artifact({}));
    queries.useReviewArtifact.mockReturnValue({ mutateAsync: review, isPending: false });
    mockArtifacts([analysisArtifact()], []);

    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));

    expect(review).toHaveBeenCalledWith({
      artifactId: "art-analysis",
      review: { decision: "approved" },
    });
  });

  it("re-validates edited fields against the original before approving", async () => {
    const review = vi.fn().mockResolvedValue(artifact({}));
    queries.useReviewArtifact.mockReturnValue({ mutateAsync: review, isPending: false });
    mockArtifacts([analysisArtifact()], []);

    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /Edit fields/ }));
    const input = screen.getByDisplayValue("राहुल शर्मा");
    fireEvent.change(input, { target: { value: "राहुल शर्मा, नया नाम" } });
    fireEvent.click(screen.getByRole("button", { name: /Re-validate & approve/ }));

    expect(review).toHaveBeenCalledWith({
      artifactId: "art-analysis",
      review: {
        decision: "approved",
        payload: {
          fields: {
            person_names: ["राहुल शर्मा", "नया नाम"],
            amounts: ["५,०००"],
            negations: ["नहीं दिए"],
          },
        },
      },
    });
  });

  it("explains that original text appears after ingest/analysis when no records exist", () => {
    renderPanel();

    expect(screen.getByText(/No parsed original text yet/)).toBeInTheDocument();
    expect(screen.getByText(/No multilingual analysis yet/)).toBeInTheDocument();
  });
});

describe("ExtractionPanel artifact scoping", () => {
  it("skips multilingual analysis artifacts (rendered by their own panel)", () => {
    mockJobs([]);
    const regular = artifact(
      { fields: { person_names: ["Asha Verma"] } },
      { id: "art-regular" },
    );
    mockArtifacts([analysisArtifact(), regular], []);

    render(
      <MemoryRouter>
        <ExtractionPanel caseId={CASE} evidenceId={EV} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Asha Verma/)).toBeInTheDocument();
    expect(screen.queryByText(/राहुल शर्मा/)).toBeNull();
    expect(screen.queryByText(/devanagari_digits/)).toBeNull();
  });
});
