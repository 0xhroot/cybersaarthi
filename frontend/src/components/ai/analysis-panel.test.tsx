import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const chatStreamMock = vi.hoisted(() => vi.fn());
const reportDraftMock = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  api: {
    ai: {
      chatStream: chatStreamMock,
      reportDraft: reportDraftMock,
    },
  },
  isMockMode: false,
}));

import { AnalysisPanel } from "@/components/ai/analysis-panel";
import type { AiCitationCheck } from "@/api/contract";

const PASSING_CHECK: AiCitationCheck = {
  cited_ids: 2,
  verified_ids: 2,
  unverified_ids: [],
  metric_claims_checked: 1,
  metric_claims_mismatched: [],
};

/** Drive the panel's stream callbacks like the real adapter would. */
function streamThat(
  done: Record<string, unknown>,
  opts: { tokens?: string[]; error?: string } = {},
) {
  chatStreamMock.mockImplementation(
    async (
      _input: unknown,
      callbacks: {
        onProgress?: (i: unknown) => void;
        onToken?: (t: string) => void;
        onSources?: (s: unknown) => void;
        onError?: (m: string) => void;
        onDone?: (i: unknown) => void;
      },
    ) => {
      callbacks.onProgress?.({ phase: "retrieving" });
      for (const token of opts.tokens ?? [""]) callbacks.onToken?.(token);
      if (opts.error) {
        callbacks.onError?.(opts.error);
        return;
      }
      callbacks.onSources?.(done.sources ?? []);
      callbacks.onDone?.(done);
    },
  );
}

describe("AnalysisPanel", () => {
  beforeEach(() => {
    chatStreamMock.mockReset();
    reportDraftMock.mockReset();
  });

  it("offers the analysis actions and a report draft", () => {
    render(<AnalysisPanel caseId="case-9" />);
    expect(screen.getByTestId("analysis-action-interpret")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-action-anomalies")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-action-contradictions")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-report-draft")).toBeInTheDocument();
    // Nothing is claimed before anything ran.
    expect(screen.queryByTestId("analysis-answer")).not.toBeInTheDocument();
    expect(screen.queryByTestId("analysis-citation-check")).not.toBeInTheDocument();
  });

  it("requests analysis mode with the think budget on the bound case", async () => {
    streamThat({
      answer: "Interpretation text.",
      grounded: true,
      sources: [{ type: "metric", id: "m1", label: "degree" }],
      tool_events: [],
      citation_check: PASSING_CHECK,
    });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-action-interpret"));

    await waitFor(() => expect(screen.getByTestId("analysis-answer")).toBeInTheDocument());
    expect(chatStreamMock).toHaveBeenCalledTimes(1);
    const input = chatStreamMock.mock.calls[0][0];
    expect(input).toMatchObject({
      mode: "analysis",
      case_id: "case-9",
      profile: "think",
    });
    expect(screen.getByTestId("analysis-citation-check")).toHaveTextContent(
      "Claim check passed: 2/2",
    );
    expect(screen.getByTestId("analysis-sources")).toHaveTextContent("degree");
  });

  it("surfaces unverified citations and metric mismatches as warnings", async () => {
    const ghost = "11111111-2222-3333-4444-555555555555";
    streamThat({
      answer: "Analysis.",
      grounded: true,
      sources: [],
      tool_events: [],
      citation_check: {
        cited_ids: 2,
        verified_ids: 1,
        unverified_ids: [ghost],
        metric_claims_checked: 2,
        metric_claims_mismatched: [
          `metric:degree@${ghost} = 99.0: data says 4.0000`,
        ],
      },
    });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-action-interpret"));

    await waitFor(() => expect(screen.getByTestId("analysis-citation-check")).toBeInTheDocument());
    const strip = screen.getByTestId("analysis-citation-check");
    expect(strip).toHaveTextContent("Claim check found issues: 1/2 cited ids verified");
    expect(strip).toHaveTextContent(ghost);
    expect(strip).toHaveTextContent("metric mismatch");
    expect(strip).toHaveTextContent("data says 4.0000");
  });

  it("never shows a passing check when the server sent none", async () => {
    streamThat({
      answer: "Analysis.",
      grounded: true,
      sources: [],
      tool_events: [],
      citation_check: null,
    });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-action-interpret"));

    await waitFor(() => expect(screen.getByTestId("analysis-answer")).toBeInTheDocument());
    expect(screen.queryByTestId("analysis-citation-check")).not.toBeInTheDocument();
    expect(screen.getByTestId("analysis-citation-unavailable")).toBeInTheDocument();
  });

  it("warns when the response carried no authorized sources", async () => {
    streamThat({
      answer: "Analysis.",
      grounded: false,
      sources: [],
      tool_events: [],
      citation_check: PASSING_CHECK,
    });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-action-interpret"));

    await waitFor(() => expect(screen.getByTestId("analysis-ungrounded")).toBeInTheDocument());
    expect(screen.getByTestId("analysis-ungrounded")).toHaveTextContent("unverified");
  });

  it("reports a failed stream as a failure, never as an analysis", async () => {
    streamThat({}, { error: "inference failed; try again" });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-action-interpret"));

    await waitFor(() => expect(screen.getByTestId("analysis-error")).toBeInTheDocument());
    expect(screen.getByTestId("analysis-error")).toHaveTextContent(
      "Analysis failed: inference failed; try again",
    );
    expect(screen.queryByTestId("analysis-answer")).not.toBeInTheDocument();
    expect(screen.queryByTestId("analysis-citation-check")).not.toBeInTheDocument();
  });

  it("drops the previous answer when a new run starts", async () => {
    streamThat({
      answer: "First analysis.",
      grounded: true,
      sources: [],
      tool_events: [],
      citation_check: PASSING_CHECK,
    });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-action-interpret"));
    await waitFor(() => expect(screen.getByTestId("analysis-answer")).toHaveTextContent("First analysis."));

    // Second run fails → the first answer must not survive as this run's result.
    streamThat({}, { error: "boom" });
    fireEvent.click(screen.getByTestId("analysis-action-anomalies"));
    await waitFor(() => expect(screen.getByTestId("analysis-error")).toBeInTheDocument());
    expect(screen.queryByTestId("analysis-answer")).not.toBeInTheDocument();
  });

  it("renders the report draft as a review proposal", async () => {
    reportDraftMock.mockResolvedValue({
      draft: "# Draft section\nFacts for review.",
      sources: [{ type: "case", id: "case-9", label: "case" }],
      grounded: true,
      prompt_version: "1.0.0",
      duration_ms: 12,
    });
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-report-draft"));

    await waitFor(() => expect(screen.getByTestId("analysis-draft")).toBeInTheDocument());
    expect(screen.getByTestId("analysis-draft")).toHaveTextContent(
      "proposal for human review",
    );
    expect(screen.getByTestId("analysis-draft")).toHaveTextContent("Facts for review.");
    expect(reportDraftMock).toHaveBeenCalledWith("case-9");
  });

  it("shows a failed report draft as a failure", async () => {
    reportDraftMock.mockRejectedValue(new Error("runtime unavailable"));
    render(<AnalysisPanel caseId="case-9" />);
    fireEvent.click(screen.getByTestId("analysis-report-draft"));

    await waitFor(() => expect(screen.getByTestId("analysis-error")).toBeInTheDocument());
    expect(screen.getByTestId("analysis-error")).toHaveTextContent("runtime unavailable");
    expect(screen.queryByTestId("analysis-draft")).not.toBeInTheDocument();
  });
});
