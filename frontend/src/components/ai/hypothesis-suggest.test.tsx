import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const chatStreamMock = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  api: {
    ai: {
      chatStream: chatStreamMock,
    },
  },
  isMockMode: false,
}));

import { HypothesisSuggest } from "@/components/ai/hypothesis-suggest";
import type { AiHypothesisDraft } from "@/api/contract";

const DRAFT: AiHypothesisDraft = {
  title: "Mule account reuse",
  statement: "Account A was reused across both phishing waves.",
  evidence_ids: ["3a5af37c-e73c-4736-91a1-a8daf6b98b70"],
  unverified_ids: [],
  refutation: "A bank record showing separate owners.",
  missing: "Account opening documents.",
};

const GHOST_ID = "11111111-2222-3333-4444-555555555555";

/** Drive the panel's stream callbacks like the real adapter would. */
function streamThat(done: Record<string, unknown>, opts: { error?: string } = {}) {
  chatStreamMock.mockImplementation(
    async (
      _input: unknown,
      callbacks: {
        onToken?: (t: string) => void;
        onSources?: (s: unknown) => void;
        onError?: (m: string) => void;
        onDone?: (i: unknown) => void;
      },
    ) => {
      callbacks.onToken?.("drafting…");
      if (opts.error) {
        callbacks.onError?.(opts.error);
        return;
      }
      callbacks.onSources?.(done.sources ?? []);
      callbacks.onDone?.(done);
    },
  );
}

describe("HypothesisSuggest", () => {
  beforeEach(() => {
    chatStreamMock.mockReset();
  });

  it("states the honest-semantics contract before anything runs", () => {
    render(<HypothesisSuggest caseId="case-9" canRecord />);
    expect(screen.getByTestId("suggest-run")).toBeInTheDocument();
    expect(screen.getByText(/not conclusions/i)).toBeInTheDocument();
    expect(screen.getByText(/no probability is computed/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing is\s*recorded until you review/i)).toBeInTheDocument();
    expect(screen.queryByTestId("suggest-tray")).not.toBeInTheDocument();
  });

  it("requests hypothesize mode with the think budget on the bound case", async () => {
    streamThat({ grounded: true, sources: [], hypothesis_drafts: [], hypothesis_draft_errors: 0 });
    render(<HypothesisSuggest caseId="case-9" canRecord />);
    fireEvent.click(screen.getByTestId("suggest-run"));
    await waitFor(() => expect(chatStreamMock).toHaveBeenCalledTimes(1));
    expect(chatStreamMock.mock.calls[0][0]).toMatchObject({
      mode: "hypothesize",
      case_id: "case-9",
      profile: "think",
    });
  });

  it("renders drafts and records one only when the reviewer asks", async () => {
    const onRecord = vi.fn();
    streamThat({
      grounded: true,
      sources: [{ type: "case", id: "c1", label: "SHOW-2026-001" }],
      hypothesis_drafts: [DRAFT],
      hypothesis_draft_errors: 0,
    });
    render(<HypothesisSuggest caseId="case-9" canRecord onRecord={onRecord} />);
    fireEvent.click(screen.getByTestId("suggest-run"));

    await waitFor(() => expect(screen.getByTestId("suggest-draft-0")).toBeInTheDocument());
    expect(screen.getByText("Mule account reuse")).toBeInTheDocument();
    expect(screen.getByText(/A bank record showing separate owners\./)).toBeInTheDocument();
    expect(screen.getByTestId("suggest-id-verified")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("suggest-record-0"));
    expect(onRecord).toHaveBeenCalledWith(DRAFT);
  });

  it("hides the record action from users who cannot review", async () => {
    streamThat({ grounded: true, sources: [], hypothesis_drafts: [DRAFT], hypothesis_draft_errors: 0 });
    render(<HypothesisSuggest caseId="case-9" canRecord={false} onRecord={vi.fn()} />);
    fireEvent.click(screen.getByTestId("suggest-run"));
    await waitFor(() => expect(screen.getByTestId("suggest-draft-0")).toBeInTheDocument());
    expect(screen.queryByTestId("suggest-record-0")).not.toBeInTheDocument();
  });

  it("flags evidence ids retrieval could not confirm", async () => {
    streamThat({
      grounded: true,
      sources: [],
      hypothesis_drafts: [{ ...DRAFT, evidence_ids: [GHOST_ID], unverified_ids: [GHOST_ID] }],
      hypothesis_draft_errors: 0,
    });
    render(<HypothesisSuggest caseId="case-9" canRecord />);
    fireEvent.click(screen.getByTestId("suggest-run"));
    await waitFor(() => expect(screen.getByTestId("suggest-draft-0")).toBeInTheDocument());
    expect(screen.getByTestId("suggest-id-unverified")).toBeInTheDocument();
    expect(screen.getByText(/unverified/)).toBeInTheDocument();
  });

  it("labels a partial tray and exposes the raw output", async () => {
    streamThat({
      grounded: true,
      sources: [],
      hypothesis_drafts: [DRAFT],
      hypothesis_draft_errors: 2,
    });
    render(<HypothesisSuggest caseId="case-9" canRecord />);
    fireEvent.click(screen.getByTestId("suggest-run"));
    await waitFor(() => expect(screen.getByTestId("suggest-partial")).toBeInTheDocument());
    expect(screen.getByText(/tray may be partial/i)).toBeInTheDocument();
    expect(screen.getByTestId("suggest-raw")).toBeInTheDocument();
  });

  it("reports a failed run and shows no stale drafts", async () => {
    streamThat({}, { error: "boom" });
    render(<HypothesisSuggest caseId="case-9" canRecord />);
    fireEvent.click(screen.getByTestId("suggest-run"));
    await waitFor(() => expect(screen.getByTestId("suggest-error")).toBeInTheDocument());
    expect(screen.getByText(/Suggestion run failed: boom/)).toBeInTheDocument();
    expect(screen.queryByTestId("suggest-tray")).not.toBeInTheDocument();
  });

  it("warns when a run retrieved nothing and reports an empty result honestly", async () => {
    streamThat({ grounded: false, sources: [], hypothesis_drafts: [], hypothesis_draft_errors: 0 });
    render(<HypothesisSuggest caseId="case-9" canRecord />);
    fireEvent.click(screen.getByTestId("suggest-run"));
    await waitFor(() => expect(screen.getByTestId("suggest-empty")).toBeInTheDocument());
    expect(screen.getByTestId("suggest-ungrounded")).toBeInTheDocument();
    expect(screen.getByText(/no structured suggestions/i)).toBeInTheDocument();
  });
});
