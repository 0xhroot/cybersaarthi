import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { AnalysisJobOut, DerivedArtifactOut, SourceRecordOut } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useIntelJobs: vi.fn(),
  useArtifacts: vi.fn(),
  useMultilingual: vi.fn(),
  useTriage: vi.fn(),
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
import { TriagePanel } from "@/components/evidence/triage-panel";

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
      translated_text:
        "I did not give Rahul Sharma any rupees. Payment was made from account ACC-7781.",
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
  queries.useIntelJobs.mockReturnValue(
    queryResult({ items, total: items.length, limit: 100, offset: 0 }),
  );
}

function mockArtifacts(extractions: DerivedArtifactOut[], translations: DerivedArtifactOut[]) {
  queries.useArtifacts.mockImplementation((_caseId: string, kind?: string) =>
    kind === "translation"
      ? queryResult({ items: translations, total: translations.length, limit: 100, offset: 0 })
      : queryResult({ items: extractions, total: extractions.length, limit: 100, offset: 0 }),
  );
}

function triageArtifact(
  payloadOverrides: Record<string, unknown> = {},
  overrides: Partial<DerivedArtifactOut> = {},
): DerivedArtifactOut {
  return artifact(
    {
      triage: true,
      format_profile: {
        records_scanned: 1,
        urls_found: 2,
        manifest_entries: 0,
        log_lines: 0,
        email_header_records: 0,
        history_rows: 0,
        observations_truncated: false,
      },
      fields: {
        urls: [
          {
            url: "http://paypal.com@evil.test/login",
            host: "evil.test",
            userinfo: true,
            ip_host: false,
            punycode: false,
            nonstandard_port: false,
            port: null,
            record_no: 1,
          },
          {
            url: "https://cdn.example.org:8080/asset.js",
            host: "cdn.example.org",
            userinfo: false,
            ip_host: false,
            punycode: false,
            nonstandard_port: true,
            port: 8080,
            record_no: 1,
          },
        ],
        email_headers: [],
        auth_results: [],
        manifest: null,
        history: null,
        logs: null,
      },
      observations: [
        {
          rule: "triage.url.userinfo",
          severity: "high",
          locator: { record_no: 1 },
          detail: { url: "http://paypal.com@evil.test/login", host: "evil.test" },
        },
        {
          rule: "triage.url.nonstandard_port",
          severity: "low",
          locator: { record_no: 1 },
          detail: { url: "https://cdn.example.org:8080/asset.js", port: 8080 },
        },
      ],
      missing_information: [],
      explanation: {
        summary: "One URL hides its real host behind userinfo; one uses a non-standard port.",
        explanations: [
          "The userinfo URL shows paypal.com before the @, but the parsed host is evil.test.",
        ],
        not_established: ["No malicious intent or payload is established by structure alone."],
        verification_steps: ["Compare the recorded hosts against known indicators."],
      },
      explanation_failed: false,
      explanation_error: null,
      analysis_scope: "structural observations only: no URL was fetched",
      rules_version: "1.0.0",
      ...payloadOverrides,
    },
    { id: "art-triage", kind: "triage_observation", ...overrides },
  );
}

function triageJob(overrides: Partial<AnalysisJobOut> = {}): AnalysisJobOut {
  return job({
    feature: "triage",
    idempotency_key: `triage:${EV}:a1`,
    result_summary: {
      records_total: 1,
      records_scanned: 1,
      urls_analyzed: 2,
      observations_total: 2,
      manifest_entries_verified: 0,
      artifacts_created: 1,
      artifacts_reused: 0,
      artifacts_flagged: 0,
      explanation_failed: 0,
      units_failed: 0,
    },
    ...overrides,
  });
}

function mockTriageArtifacts(items: DerivedArtifactOut[]) {
  queries.useArtifacts.mockImplementation((_caseId: string, kind?: string) =>
    kind === "triage_observation"
      ? queryResult({ items, total: items.length, limit: 100, offset: 0 })
      : queryResult({ items: [], total: 0, limit: 100, offset: 0 }),
  );
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <MultilingualPanel caseId={CASE} evidenceId={EV} />
    </MemoryRouter>,
  );
}

function renderTriagePanel() {
  return render(
    <MemoryRouter>
      <TriagePanel caseId={CASE} evidenceId={EV} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  permissions.allowed = true;
  permissions.reviewAllowed = true;
  mockJobs([]);
  mockArtifacts([], []);
  queries.useSourceRecords.mockReturnValue(
    queryResult({ items: [], total: 0, limit: 50, offset: 0 }),
  );
  queries.useMultilingual.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ job: job(), duplicate: false }),
    isPending: false,
  });
  queries.useTriage.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ job: triageJob(), duplicate: false }),
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
    expect(
      screen.getByText(/Original record #1 — verbatim source, never modified/),
    ).toBeInTheDocument();
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

    expect(
      screen.getByText(/disagrees with the deterministic script evidence/),
    ).toBeInTheDocument();
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
      job({
        status: "failed",
        error: "LANGUAGE_UNSUPPORTED: complaint uses an unsupported script",
      }),
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
    const regular = artifact({ fields: { person_names: ["Asha Verma"] } }, { id: "art-regular" });
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

describe("TriagePanel", () => {
  it("shows deterministic observations as facts with severity, rule and record locator", () => {
    mockJobs([triageJob()]);
    mockTriageArtifacts([triageArtifact()]);

    renderTriagePanel();

    expect(screen.getByText(/facts, not verdicts/)).toBeInTheDocument();
    expect(screen.getAllByTestId("triage-observation")).toHaveLength(2);
    expect(screen.getByText("triage.url.userinfo")).toBeInTheDocument();
    expect(screen.getByText("triage.url.nonstandard_port")).toBeInTheDocument();
    expect(screen.getAllByText("record #1")).toHaveLength(2);
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("low")).toBeInTheDocument();
    // structural analysis is presented, including the bounded scope statement
    expect(screen.getAllByText(/evil\.test/).length).toBeGreaterThan(0);
    expect(screen.getByText(/no URL was fetched/)).toBeInTheDocument();
  });

  it("shows hash-manifest verdicts recomputed from stored bytes", () => {
    const shaA = "a".repeat(64);
    const shaB = "b".repeat(64);
    const shaF = "f".repeat(64);
    mockJobs([
      triageJob({
        status: "succeeded",
        result_summary: {
          ...triageJob().result_summary,
          observations_total: 2,
          manifest_entries_verified: 3,
        },
      }),
    ]);
    mockTriageArtifacts([
      triageArtifact({
        format_profile: {
          records_scanned: 3,
          urls_found: 0,
          manifest_entries: 3,
          log_lines: 0,
          email_header_records: 0,
          history_rows: 0,
          observations_truncated: false,
        },
        fields: {
          urls: [],
          email_headers: [],
          auth_results: [],
          history: null,
          logs: null,
          manifest: [
            {
              record_no: 1,
              sha256: shaA,
              filename: "target.txt",
              verdict: "match",
              computed_sha256: shaA,
            },
            {
              record_no: 2,
              sha256: shaB,
              filename: "victim.txt",
              verdict: "mismatch",
              computed_sha256: shaF,
            },
            {
              record_no: 3,
              sha256: shaB,
              filename: "absent.txt",
              verdict: "missing",
              computed_sha256: null,
            },
          ],
        },
        observations: [
          {
            rule: "triage.manifest.hash_mismatch",
            severity: "high",
            locator: { record_no: 2 },
            detail: { filename: "victim.txt" },
          },
          {
            rule: "triage.manifest.entry_missing",
            severity: "medium",
            locator: { record_no: 3 },
            detail: { filename: "absent.txt" },
          },
        ],
        explanation: null,
      }),
    ]);

    renderTriagePanel();

    expect(screen.getByText(/recomputed from stored bytes/i)).toBeInTheDocument();
    expect(screen.getByText("match")).toBeInTheDocument();
    expect(screen.getByText("mismatch")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
    expect(screen.getByText("victim.txt")).toBeInTheDocument();
    expect(screen.getByText("triage.manifest.hash_mismatch")).toBeInTheDocument();
  });

  it("keeps the model explanation labelled unreviewed beside the recorded observations", () => {
    mockJobs([triageJob()]);
    mockTriageArtifacts([triageArtifact()]);

    renderTriagePanel();

    const explanation = screen.getByTestId("triage-explanation");
    expect(explanation).toHaveTextContent(/AI interpretation · unreviewed/);
    expect(explanation).toHaveTextContent(/hides its real host behind userinfo/);
    expect(explanation).toHaveTextContent(/No malicious intent or payload is established/);
    expect(explanation).toHaveTextContent(/Suggested verification steps/);
    // the deterministic observations stay visible alongside it
    expect(screen.getAllByTestId("triage-observation")).toHaveLength(2);
  });

  it("reports a model outage as an honest partial: observations survive, explanation failed", () => {
    mockJobs([
      triageJob({
        status: "partial",
        error: "1 unit(s) failed (model)",
        result_summary: {
          ...triageJob().result_summary,
          units_failed: 1,
          explanation_failed: 1,
          artifacts_flagged: 1,
        },
      }),
    ]);
    mockTriageArtifacts([
      triageArtifact(
        {
          explanation: null,
          explanation_failed: true,
          explanation_error: "model call failed: timeout",
        },
        {
          validation_status: "flagged",
          validation_errors: [
            {
              code: "model_call_failed",
              message: "the model call failed; observations were recorded",
            },
          ],
        },
      ),
    ]);

    renderTriagePanel();

    // deterministic observations are still fully shown
    expect(screen.getAllByTestId("triage-observation")).toHaveLength(2);
    expect(screen.getByText("triage.url.userinfo")).toBeInTheDocument();
    // the failure is explicit, never a silent success
    expect(screen.getByText(/Model explanation was not recorded/)).toBeInTheDocument();
    expect(screen.getByText(/model_call_failed/)).toBeInTheDocument();
    expect(screen.getByText(/Partial run/)).toBeInTheDocument();
    expect(screen.queryByTestId("triage-explanation")).toBeNull();
  });

  it("shows a failed run's typed refusal (TRIAGE_UNSUPPORTED_CONTENT)", () => {
    mockJobs([
      triageJob({
        status: "failed",
        error: "TRIAGE_UNSUPPORTED_CONTENT: no forensic structure found",
      }),
    ]);
    mockTriageArtifacts([]);

    renderTriagePanel();

    expect(screen.getByText(/Run refused/)).toBeInTheDocument();
    expect(screen.getByText(/TRIAGE_UNSUPPORTED_CONTENT/)).toBeInTheDocument();
    // no empty success is rendered, and the run button stays available
    expect(screen.getByText(/No triage observations yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run triage/ })).toBeEnabled();
  });

  it("submits a triage run", () => {
    const submit = vi.fn().mockResolvedValue({ job: triageJob(), duplicate: false });
    queries.useTriage.mockReturnValue({ mutateAsync: submit, isPending: false });

    renderTriagePanel();
    fireEvent.click(screen.getByRole("button", { name: /Run triage/ }));

    expect(submit).toHaveBeenCalledWith(EV);
  });

  it("offers cancel while a run is active and refuses a second submit", () => {
    mockJobs([triageJob({ status: "running" })]);

    renderTriagePanel();

    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Triaging\u2026" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(queries.useCancelIntelJob().mutateAsync).toHaveBeenCalledWith("job-1");
  });

  it("hides run and review controls without permissions", () => {
    permissions.allowed = false;
    mockJobs([triageJob()]);
    mockTriageArtifacts([triageArtifact()]);

    renderTriagePanel();

    expect(screen.queryByRole("button", { name: /Run triage/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
    // the data itself stays visible
    expect(screen.getAllByTestId("triage-observation")).toHaveLength(2);
  });

  it("hides review controls without findings.review", () => {
    permissions.reviewAllowed = false;
    mockJobs([triageJob()]);
    mockTriageArtifacts([triageArtifact()]);

    renderTriagePanel();

    expect(screen.getByRole("button", { name: /Run triage/ })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("approves a validated observation artifact with a recorded decision", () => {
    const review = vi.fn().mockResolvedValue(artifact({}));
    queries.useReviewArtifact.mockReturnValue({ mutateAsync: review, isPending: false });
    mockJobs([triageJob()]);
    mockTriageArtifacts([triageArtifact()]);

    renderTriagePanel();
    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));

    expect(review).toHaveBeenCalledWith({
      artifactId: "art-triage",
      review: { decision: "approved" },
    });
  });

  it("requires a written reason before a rejection is recorded", () => {
    const review = vi.fn().mockResolvedValue(artifact({}));
    queries.useReviewArtifact.mockReturnValue({ mutateAsync: review, isPending: false });
    mockJobs([triageJob()]);
    mockTriageArtifacts([triageArtifact()]);

    renderTriagePanel();
    fireEvent.click(screen.getByRole("button", { name: /Reject/ }));

    const record = screen.getByRole("button", { name: /Record decision/ });
    expect(record).toBeDisabled(); // a rejection without a reason is refused
    fireEvent.change(screen.getByPlaceholderText("Rejection reason"), {
      target: { value: "scope is wrong: this file is not the target" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Record decision/ }));

    expect(review).toHaveBeenCalledWith({
      artifactId: "art-triage",
      review: { decision: "rejected", note: "scope is wrong: this file is not the target" },
    });
  });
});
