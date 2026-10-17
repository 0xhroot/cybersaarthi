import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

import type { AnalysisJobOut, ContradictionResolutionState, DerivedArtifactOut } from "@/types/domain";

const queries = vi.hoisted(() => ({
  useIntelJobs: vi.fn(),
  useArtifacts: vi.fn(),
  useSubmitEntityResolution: vi.fn(),
  useSubmitTimelineReconstruction: vi.fn(),
  useSubmitContradictions: vi.fn(),
  useReviewArtifact: vi.fn(),
  useCancelIntelJob: vi.fn(),
  useCommitTimelineProposal: vi.fn(),
  useResolveContradiction: vi.fn(),
}));

vi.mock("@/hooks/queries", () => queries);
vi.mock("@/lib/permissions", () => ({ useCan: () => true }));

import { ResolutionPanel } from "@/components/evidence/resolution-panel";
import { ReconstructionPanel } from "@/components/evidence/reconstruction-panel";
import { ContradictionPanel } from "@/components/evidence/contradiction-panel";

const CASE = "case-1";

function job(overrides: Partial<AnalysisJobOut> = {}): AnalysisJobOut {
  return {
    id: "job-1",
    case_id: CASE,
    feature: "entity_resolution",
    status: "succeeded",
    idempotency_key: `entity_resolution:${CASE}:a1`,
    progress: 100,
    total_records: 1,
    processed_records: 1,
    attempts: 1,
    timeout_seconds: 300,
    cancel_requested: false,
    error: null,
    result_summary: null,
    evidence_file_id: null,
    actor_id: "user-1",
    started_at: "2026-03-15T10:00:00Z",
    completed_at: "2026-03-15T10:00:02Z",
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:02Z",
    ...overrides,
  };
}

function artifact(overrides: Partial<DerivedArtifactOut>): DerivedArtifactOut {
  return {
    id: "art-1",
    case_id: CASE,
    kind: "entity_resolution",
    origin: "deterministic",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: null,
    payload: {},
    content_hash: "hash-1",
    parser_version: "1.0.0",
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

function queryResult<T extends { items: unknown[] }>(data: T, overrides: Record<string, unknown> = {}) {
  return { data, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...overrides };
}

function mutation<T>(result?: T) {
  return { mutateAsync: vi.fn().mockResolvedValue(result ?? {}), isPending: false, reset: vi.fn() };
}

function renderPanel(panel: ReactElement) {
  return render(
    <MemoryRouter initialEntries={[`/app/cases/${CASE}`]}>{panel}</MemoryRouter>,
  );
}

const candidatePayload = {
  type: "entity_candidate",
  entity_a: {
    id: "ent-1",
    entity_type: "person",
    canonical_value: "rajesh kumar",
    display_value: "Rajesh Kumar",
  },
  entity_b: {
    id: "ent-2",
    entity_type: "person",
    canonical_value: "rajesh kumarr",
    display_value: "Rajesh Kumarr",
  },
  method: "name_similarity",
  score: 91.67,
  score_band: "ambiguous",
  score_semantics: "0-100 similarity band (not a probability)",
  name_similarity: 91.67,
  matching_fields: [{ field: "name_variant", detail: { similarity: 91.67 } }],
  conflicting_fields: [],
};

describe("phase 3 panels", () => {
  it("resolution panel: empty state explains what a run would do", () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useSubmitEntityResolution.mockReturnValue(mutation({ job: job(), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ResolutionPanel caseId={CASE} />);
    expect(screen.getByText("No candidate matches")).toBeTruthy();
  });

  it("resolution panel: shows the pair, band, name-only flag and score semantics", () => {
    queries.useIntelJobs.mockReturnValue(
      queryResult({ items: [job({ result_summary: { entities_scanned: 39, pairs_proposed: 1 } })], total: 1, limit: 100, offset: 0 }),
    );
    queries.useArtifacts.mockReturnValue(
      queryResult({
        items: [
          artifact({
            validation_status: "flagged",
            payload: candidatePayload,
            validation_errors: [
              { field: "pair", code: "no_identifier_evidence", message: "no shared identifier or alias" },
            ],
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    );
    queries.useSubmitEntityResolution.mockReturnValue(mutation({ job: job(), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ResolutionPanel caseId={CASE} />);
    expect(screen.getByText("Rajesh Kumar")).toBeTruthy();
    expect(screen.getByText("Rajesh Kumarr")).toBeTruthy();
    expect(screen.getByText("ambiguous band")).toBeTruthy();
    expect(screen.getByText("name-only evidence")).toBeTruthy();
    expect(screen.getByText(/not a probability/)).toBeTruthy();
    expect(screen.getByText(/no_identifier_evidence/)).toBeTruthy();
    // Both entities stay navigable: approving later never merges them.
    expect((screen.getByText("Rajesh Kumar").closest("a") as HTMLAnchorElement).getAttribute("href")).toBe(
      `/app/cases/${CASE}/entities/ent-1`,
    );
    // The scan summary reports honest counts.
    expect(screen.getByText(/39 entities scanned/)).toBeTruthy();
  });

  it("resolution panel: approve is one click; reject demands a typed reason", async () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(
      queryResult({ items: [artifact({ payload: candidatePayload })], total: 1, limit: 100, offset: 0 }),
    );
    queries.useSubmitEntityResolution.mockReturnValue(mutation({ job: job(), duplicate: false }));
    const review = mutation();
    queries.useReviewArtifact.mockReturnValue(review);
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ResolutionPanel caseId={CASE} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await vi.waitFor(() => expect(review.mutateAsync).toHaveBeenCalledWith({
      artifactId: "art-1",
      review: { decision: "approved" },
    }));

    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(screen.getByText(/Why is this candidate rejected/)).toBeTruthy();
    const record = screen.getByRole("button", { name: /record decision/i });
    expect((record as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("Rejection reason"), { target: { value: "different people" } });
    expect((record as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(record);
    await vi.waitFor(() => expect(review.mutateAsync).toHaveBeenCalledWith({
      artifactId: "art-1",
      review: { decision: "rejected", note: "different people" },
    }));
  });

  it("resolution panel: a failed candidate query shows retry, not an empty panel", () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    const refetch = vi.fn();
    queries.useArtifacts.mockReturnValue(
      queryResult({ items: [], total: 0, limit: 100, offset: 0 }, { data: undefined, isError: true, error: new Error("boom"), refetch }),
    );
    queries.useSubmitEntityResolution.mockReturnValue(mutation({ job: job(), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ResolutionPanel caseId={CASE} />);
    expect(screen.getByText("Unable to load this view")).toBeTruthy();
    expect(screen.queryByText("No candidate matches")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it("reconstruction panel: originals, assumptions and flags stay visible on every proposal", () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(
      queryResult({
        items: [
          artifact({
            kind: "timeline_proposal",
            payload: {
              type: "timeline_proposal",
              kind: "case_event",
              title: "Transaction recorded on 2026-03-15",
              occurred_at: "2026-03-15T00:00:00+00:00",
              original_timestamp: "2026-03-15",
              tz: null,
              tz_assumed: false,
              time_granularity: "date",
              time_semantics: "record_occurs_on",
              missing_timestamp: false,
              proposal_key: "k1",
            },
            source_locator: { record_no: 1, field: "txn_date" },
          }),
          artifact({
            id: "art-2",
            kind: "timeline_proposal",
            payload: {
              type: "timeline_proposal",
              kind: "case_event",
              title: "Incident recorded at 14:30",
              occurred_at: "2026-03-15T14:30:00+00:00",
              original_timestamp: "15/03/2026 14:30",
              tz: null,
              tz_assumed: true,
              time_granularity: "datetime",
              time_semantics: "record_occurs_on",
              missing_timestamp: false,
              proposal_key: "k2",
            },
          }),
          artifact({
            id: "art-3",
            kind: "timeline_proposal",
            validation_status: "flagged",
            payload: {
              type: "timeline_proposal",
              kind: "case_event",
              title: "Reported at TBD",
              occurred_at: null,
              original_timestamp: "TBD",
              tz: null,
              tz_assumed: false,
              time_granularity: null,
              time_semantics: "statement_refers_to_event",
              missing_timestamp: true,
              proposal_key: "k3",
            },
            validation_errors: [{ field: "timestamp", code: "missing_timestamp", message: "no timestamp could be established" }],
          }),
        ],
        total: 3,
        limit: 100,
        offset: 0,
      }),
    );
    queries.useSubmitTimelineReconstruction.mockReturnValue(mutation({ job: job({ feature: "timeline" }), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    queries.useCommitTimelineProposal.mockReturnValue(mutation({ event: {}, duplicate: false }));
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ReconstructionPanel caseId={CASE} />);
    expect(screen.getByText("2026-03-15")).toBeTruthy(); // original preserved
    expect(screen.getByText("15/03/2026 14:30")).toBeTruthy();
    expect(screen.getByText("UTC assumed (no zone in source)")).toBeTruthy();
    expect(screen.getByText("missing_timestamp")).toBeTruthy();
    expect(screen.getByText(/record 1/)).toBeTruthy(); // locator for source navigation
  });

  it("reconstruction panel: commit needs an approved proposal and never fires for a missing timestamp", async () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    const dateProposal = (id: string, missing: boolean) =>
      artifact({
        id,
        kind: "timeline_proposal",
        status: "approved",
        payload: {
          type: "timeline_proposal",
          kind: "case_event",
          title: missing ? "Reported at TBD" : "Transaction recorded",
          occurred_at: missing ? null : "2026-03-15T00:00:00+00:00",
          original_timestamp: missing ? "TBD" : "2026-03-15",
          tz_assumed: false,
          time_granularity: missing ? null : "date",
          missing_timestamp: missing,
          proposal_key: missing ? "k3" : "k1",
        },
      });
    queries.useArtifacts.mockReturnValue(
      queryResult({ items: [dateProposal("art-1", false), dateProposal("art-2", true)], total: 2, limit: 100, offset: 0 }),
    );
    queries.useSubmitTimelineReconstruction.mockReturnValue(mutation({ job: job({ feature: "timeline" }), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    const commit = mutation({ event: { id: "evt-1" }, duplicate: false });
    queries.useCommitTimelineProposal.mockReturnValue(commit);
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ReconstructionPanel caseId={CASE} />);
    // The missing-timestamp proposal renders its commit disabled: it can never
    // invent an instant, even when approved.
    const buttons = screen.getAllByRole("button", { name: /commit to timeline/i });
    expect(buttons.length).toBe(2);
    expect((buttons[1] as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(buttons[0]);
    await vi.waitFor(() => expect(commit.mutateAsync).toHaveBeenCalledWith("art-1"));
    // After a successful commit the row marks itself committed and locks.
    expect(await screen.findByRole("button", { name: /committed/i })).toBeTruthy();
    const after = screen.getAllByRole("button", { name: /committed/i });
    expect((after[after.length - 1] as HTMLButtonElement).disabled).toBe(true);
  });

  it("contradiction panel: side-by-side values, alternatives and priorities are always visible", () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(
      queryResult({
        items: [
          artifact({
            kind: "contradiction",
            payload: {
              type: "contradiction",
              category: "amount",
              rule: "contradiction.amount_disagreement",
              rule_version: "1.0.0",
              priority: "high",
              anchor: { value: "txn9001", scope: "transaction", fields: "txn_id" },
              first: { source_record_id: null, record_no: 1, field: "txn_amount", value: "1500", original: "1500", locator: { record_no: 1, field: "txn_amount" } },
              second: { source_record_id: null, record_no: 2, field: "txn_amount", value: "2500", original: "2500", locator: { record_no: 2, field: "txn_amount" } },
              conflicting_values: [{ field: "txn_amount", first: "1500", second: "2500" }],
              alternatives: ["currency_or_unit: records may use different units", "partial_payment: partial settlement"],
            },
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    );
    queries.useSubmitContradictions.mockReturnValue(mutation({ job: job({ feature: "contradiction" }), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    queries.useResolveContradiction.mockReturnValue(mutation());
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ContradictionPanel caseId={CASE} />);
    expect(screen.getByText("Unresolved")).toBeTruthy();
    expect(screen.getByText("amount")).toBeTruthy();
    expect(screen.getByText("high priority")).toBeTruthy();
    expect(screen.getByText(/txn9001/)).toBeTruthy();
    expect(screen.getByText("1500")).toBeTruthy();
    expect(screen.getByText("2500")).toBeTruthy();
    expect(screen.getByText(/partial_payment/)).toBeTruthy();
  });

  it("contradiction panel: confirm is direct; false positive and resolution states demand a note", async () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(
      queryResult({
        items: [
          artifact({
            kind: "contradiction",
            payload: {
              type: "contradiction",
              category: "amount",
              priority: "high",
              anchor: { value: "txn9001", scope: "transaction", fields: "txn_id" },
              first: { record_no: 1, field: "txn_amount", value: "1500", original: "1500" },
              second: { record_no: 2, field: "txn_amount", value: "2500", original: "2500" },
              alternatives: ["partial_payment"],
            },
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    );
    queries.useSubmitContradictions.mockReturnValue(mutation({ job: job({ feature: "contradiction" }), duplicate: false }));
    const review = mutation();
    queries.useReviewArtifact.mockReturnValue(review);
    const resolve = mutation({ id: "child-1" });
    queries.useResolveContradiction.mockReturnValue(resolve);
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ContradictionPanel caseId={CASE} />);

    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await vi.waitFor(() => expect(review.mutateAsync).toHaveBeenCalledWith({
      artifactId: "art-1",
      review: { decision: "approved" },
    }));

    fireEvent.click(screen.getByRole("button", { name: /false positive/i }));
    const record = screen.getByRole("button", { name: /^record$/i });
    expect((record as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("Note"), { target: { value: "both values are consistent" } });
    fireEvent.click(record);
    await vi.waitFor(() => expect(review.mutateAsync).toHaveBeenCalledWith({
      artifactId: "art-1",
      review: { decision: "rejected", note: "both values are consistent" },
    }));

    fireEvent.click(screen.getByRole("button", { name: /explained/i }));
    fireEvent.change(screen.getByPlaceholderText("Note"), { target: { value: "partial settlement recorded later" } });
    fireEvent.click(screen.getByRole("button", { name: /^record$/i }));
    await vi.waitFor(() =>
      expect(resolve.mutateAsync).toHaveBeenCalledWith({
        artifactId: "art-1",
        resolution: { state: "explained" as ContradictionResolutionState, note: "partial settlement recorded later" },
      }),
    );
  });

  it("contradiction panel: appended resolution children render next to the candidate", () => {
    queries.useIntelJobs.mockReturnValue(queryResult({ items: [], total: 0, limit: 100, offset: 0 }));
    queries.useArtifacts.mockReturnValue(
      queryResult({
        items: [
          artifact({
            kind: "contradiction",
            payload: {
              type: "contradiction",
              category: "amount",
              priority: "high",
              anchor: { value: "txn9001", scope: "transaction", fields: "txn_id" },
              first: { record_no: 1, field: "txn_amount", value: "1500", original: "1500" },
              second: { record_no: 2, field: "txn_amount", value: "2500", original: "2500" },
              alternatives: ["partial_payment"],
            },
          }),
          artifact({
            id: "child-1",
            kind: "contradiction",
            status: "recorded",
            parent_artifact_id: "art-1",
            payload: {
              type: "contradiction_review",
              state: "explained",
              note: "partial settlement",
              for_artifact_id: "art-1",
            },
          }),
        ],
        total: 2,
        limit: 100,
        offset: 0,
      }),
    );
    queries.useSubmitContradictions.mockReturnValue(mutation({ job: job({ feature: "contradiction" }), duplicate: false }));
    queries.useReviewArtifact.mockReturnValue(mutation());
    queries.useResolveContradiction.mockReturnValue(mutation());
    queries.useCancelIntelJob.mockReturnValue(mutation());

    renderPanel(<ContradictionPanel caseId={CASE} />);
    // The candidate stays visible and unresolved; the child adds reviewer state
    // without replacing anything.
    expect(screen.getByText("Unresolved")).toBeTruthy();
    // "Explained" appears twice: the child's state badge and the still-open
    // resolve action for the unresolved candidate.
    expect(screen.getAllByText("Explained").length).toBe(2);
    expect(screen.getByText(/partial settlement/)).toBeTruthy();
    // The child is not itself listed as a second candidate.
    expect(screen.getAllByTestId("contradiction-candidate").length).toBe(1);
  });
});
