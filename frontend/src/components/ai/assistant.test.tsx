import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Assistant } from "@/components/ai/assistant";
import { api } from "@/api";
import { AI_SEED_CONVERSATIONS, MOCK_LATENCY, mockApi, resetMockState } from "@/api/mock";
import { CASE_ID_MAIN } from "@/api/mock/data";
import { authSession } from "@/api/client/session";
import { useToastStore } from "@/components/ui/toast";

const CASE_ID = "e3e26b2d-5ad0-4de5-bf2f-c115ceb0119c";
const SEED_PREFIX = "ai-conv-seed";

beforeEach(async () => {
  resetMockState();
  authSession.clear();
  useToastStore.setState({ toasts: [] });
  await mockApi.auth.login({ username: "investigator", password: "investigator-dev-password" });
});

function renderAssistant(path = "/app") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Assistant />
    </MemoryRouter>,
  );
}

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("assistant-fab"));
  expect(await screen.findByTestId("assistant-panel")).toBeInTheDocument();
}

async function ask(user: ReturnType<typeof userEvent.setup>, question: string) {
  await user.type(screen.getByTestId("assistant-input"), question);
  // The composer swaps Send ↔ Stop while a stream is in flight; wait for Send.
  await user.click(await screen.findByTestId("assistant-send"));
}

function createdConversations() {
  return mockApi.ai.listConversations().then(({ items }) =>
    items.filter((c) => !c.id.startsWith(SEED_PREFIX)),
  );
}

describe("floating assistant", () => {
  it("opens from the FAB and shows the empty-state hint", async () => {
    const user = userEvent.setup();
    renderAssistant();

    expect(screen.getByTestId("assistant-fab")).toHaveAttribute("aria-expanded", "false");
    await openPanel(user);

    expect(screen.getByText(/generated on-device by a local model/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Ask CyberSaarthi/i)).toBeInTheDocument();
  });

  it("sends a general question and renders the streamed answer", async () => {
    const user = userEvent.setup();
    renderAssistant();
    await openPanel(user);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "How does evidence ingest work?");
    await user.click(screen.getByTestId("assistant-send"));

    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();
    expect(screen.getByText("knowledge: overview")).toBeInTheDocument();
  });

  it("scopes questions to the case in the route", async () => {
    const user = userEvent.setup();
    renderAssistant(`/cases/${CASE_ID}`);
    await openPanel(user);

    expect(screen.getByPlaceholderText(/Ask about this case/i)).toBeInTheDocument();
    expect(screen.getByText(/Scoped to this case/i)).toBeInTheDocument();

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Summarize this case.");
    await user.click(screen.getByTestId("assistant-send"));

    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();
    // Case-scoped mock answers cite the evidence source chip.
    expect(screen.getByText(/call_detail_record\.csv/)).toBeInTheDocument();
    expect(screen.getByText(/grounded/)).toBeInTheDocument();
  });

  it("never renders the raw tool fence streamed before a tool event", async () => {
    const user = userEvent.setup();
    renderAssistant(`/cases/${CASE_ID}`);
    await openPanel(user);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Summarize this case.");
    await user.click(screen.getByTestId("assistant-send"));

    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();
    // The pre-tool tokens are the model's raw tool fence: per the stream
    // contract they are cleared when the `tool` event arrives and the final
    // message must show only the answer plus the tool chip.
    expect(screen.queryByText(/"tool": "get_case_summary"/)).not.toBeInTheDocument();
    expect(screen.getByText(/get_case_summary/)).toBeInTheDocument();
  });

  it("disables send while the input is empty", async () => {
    const user = userEvent.setup();
    renderAssistant();
    await openPanel(user);

    expect(screen.getByTestId("assistant-send")).toBeDisabled();
    await user.type(screen.getByTestId("assistant-input"), "hi");
    expect(screen.getByTestId("assistant-send")).toBeEnabled();
  });

  it("closes the panel from the header button", async () => {
    const user = userEvent.setup();
    renderAssistant();
    await openPanel(user);

    await user.click(screen.getByLabelText("Close assistant"));
    expect(screen.queryByTestId("assistant-panel")).not.toBeInTheDocument();
  });

  /* ----------------------------- multi-turn ----------------------------- */

  it("reuses the conversation id for follow-up messages", async () => {
    const user = userEvent.setup();
    const streamSpy = vi.spyOn(api.ai, "chatStream");
    renderAssistant();
    await openPanel(user);

    await ask(user, "First question?");
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();

    await ask(user, "Follow-up question?");
    await waitFor(() =>
      expect(screen.getAllByText(/Mock assistant answer/i)).toHaveLength(2),
    );

    expect(streamSpy).toHaveBeenCalledTimes(2);
    expect(streamSpy.mock.calls[0][0].conversation_id).toBeFalsy();
    const secondId = streamSpy.mock.calls[1][0].conversation_id;
    expect(secondId).toBeTruthy();

    // One server thread, four persisted messages — not two separate conversations.
    const created = await createdConversations();
    expect(created).toHaveLength(1);
    expect(created[0].id).toBe(secondId);
    const { items: thread } = await mockApi.ai.listMessages(secondId as string);
    expect(thread).toHaveLength(4);
  });

  it("falls back to the newest conversation when the stream omits the id", async () => {
    const user = userEvent.setup();
    const original = api.ai.chatStream.bind(api.ai);
    const streamSpy = vi.spyOn(api.ai, "chatStream").mockImplementation(async (input, callbacks, signal) => {
      // Simulate the current real backend: `done` carries no conversation_id.
      await original(
        input,
        {
          ...callbacks,
          onDone: (info) => callbacks.onDone?.({ ...info, conversation_id: undefined }),
        },
        signal,
      );
    });
    renderAssistant();
    await openPanel(user);

    await ask(user, "First question?");
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();
    // One-shot listConversations({ limit: 1 }) fallback runs after onDone.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY + 150));
    });

    await ask(user, "Follow-up question?");
    await waitFor(() =>
      expect(screen.getAllByText(/Mock assistant answer/i)).toHaveLength(2),
    );

    expect(streamSpy.mock.calls[1][0].conversation_id).toBeTruthy();
    expect(await createdConversations()).toHaveLength(1);
  });

  it("starts a fresh conversation from the new-chat button", async () => {
    const user = userEvent.setup();
    const streamSpy = vi.spyOn(api.ai, "chatStream");
    renderAssistant();
    await openPanel(user);

    await ask(user, "First question?");
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();

    await user.click(screen.getByTestId("assistant-new"));
    expect(screen.getByText(/generated on-device by a local model/i)).toBeInTheDocument();
    expect(screen.getByTestId("assistant-input")).toHaveValue("");
    expect(screen.queryByText(/Mock assistant answer/i)).not.toBeInTheDocument();

    await ask(user, "Second question?");
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();

    // The cleared thread id must not leak into the next exchange.
    expect(streamSpy.mock.calls[1][0].conversation_id).toBeFalsy();
    expect(await createdConversations()).toHaveLength(2);
  });

  /* ------------------------------- history ------------------------------ */

  it("opens history, loads a stored conversation, and returns to chat", async () => {
    const user = userEvent.setup();
    renderAssistant(`/cases/${CASE_ID_MAIN}`);
    await openPanel(user);

    await user.click(screen.getByTestId("assistant-history"));
    const caseItem = await screen.findByTestId(
      `assistant-history-item-${AI_SEED_CONVERSATIONS.case}`,
    );
    expect(
      screen.getByTestId(`assistant-history-item-${AI_SEED_CONVERSATIONS.general}`),
    ).toBeInTheDocument();
    // Title + relative time + case badge.
    expect(caseItem).toHaveTextContent("Evidence ingest walkthrough");
    expect(caseItem).toHaveTextContent(/ago/);
    expect(caseItem).toHaveTextContent(/case a0000000/);

    await user.click(caseItem);
    expect(
      await screen.findByText(/Which evidence files support the primary lead/i),
    ).toBeInTheDocument();
    // Persisted assistant messages bring their citations back.
    expect(screen.getAllByText(/call_detail_record\.csv/).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("assistant-history-list")).not.toBeInTheDocument();
    expect(screen.getByTestId("assistant-input")).toBeInTheDocument();

    await user.click(screen.getByTestId("assistant-history"));
    expect(await screen.findByTestId("assistant-history-list")).toBeInTheDocument();
    await user.click(screen.getByTestId("assistant-back"));
    expect(screen.queryByTestId("assistant-history-list")).not.toBeInTheDocument();
  });

  it("filters history to the current case context", async () => {
    const user = userEvent.setup();
    renderAssistant("/app");
    await openPanel(user);

    await user.click(screen.getByTestId("assistant-history"));
    expect(
      await screen.findByTestId(`assistant-history-item-${AI_SEED_CONVERSATIONS.general}`),
    ).toBeInTheDocument();
    // Case threads only show while inside that case.
    expect(
      screen.queryByTestId(`assistant-history-item-${AI_SEED_CONVERSATIONS.case}`),
    ).not.toBeInTheDocument();
  });

  it("renames a conversation inline from history", async () => {
    const user = userEvent.setup();
    renderAssistant("/app");
    await openPanel(user);

    await user.click(screen.getByTestId("assistant-history"));
    await screen.findByTestId(`assistant-history-item-${AI_SEED_CONVERSATIONS.general}`);

    await user.click(screen.getByTestId(`assistant-rename-${AI_SEED_CONVERSATIONS.general}`));
    const nameInput = screen.getByLabelText("Conversation name");
    expect(nameInput).toHaveValue("Platform onboarding questions");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed thread");
    await user.click(screen.getByTestId("assistant-rename-save"));

    expect(await screen.findByText("Renamed thread")).toBeInTheDocument();
    const { items } = await mockApi.ai.listConversations();
    expect(items.find((c) => c.id === AI_SEED_CONVERSATIONS.general)?.title).toBe(
      "Renamed thread",
    );
  });

  it("deletes a conversation after inline confirmation", async () => {
    const user = userEvent.setup();
    renderAssistant("/app");
    await openPanel(user);

    await user.click(screen.getByTestId("assistant-history"));
    await screen.findByTestId(`assistant-history-item-${AI_SEED_CONVERSATIONS.general}`);

    await user.click(screen.getByTestId(`assistant-delete-${AI_SEED_CONVERSATIONS.general}`));
    await user.click(screen.getByTestId("assistant-delete-confirm"));
    await waitFor(() =>
      expect(
        screen.queryByTestId(`assistant-history-item-${AI_SEED_CONVERSATIONS.general}`),
      ).not.toBeInTheDocument(),
    );

    const { items } = await mockApi.ai.listConversations();
    expect(items.find((c) => c.id === AI_SEED_CONVERSATIONS.general)).toBeUndefined();
  });

  /* ---------------------------- panel states ---------------------------- */

  it("expands to a full-screen panel and minimizes again", async () => {
    const user = userEvent.setup();
    renderAssistant();
    await openPanel(user);

    expect(screen.getByTestId("assistant-expand")).toHaveAttribute(
      "aria-label",
      "Expand assistant",
    );
    await user.click(screen.getByTestId("assistant-expand"));

    const panel = screen.getByTestId("assistant-panel");
    expect(panel).toHaveClass("inset-4");
    expect(panel).toHaveClass("sm:inset-8");
    expect(panel).not.toHaveClass("bottom-20");
    expect(screen.getByTestId("assistant-expand")).toHaveAttribute(
      "aria-label",
      "Minimize assistant",
    );

    await user.click(screen.getByTestId("assistant-expand"));
    expect(screen.getByTestId("assistant-panel")).toHaveClass("bottom-20");
    expect(screen.getByTestId("assistant-panel")).not.toHaveClass("inset-4");
  });

  it("focuses the input when opened and closes with Escape", async () => {
    const user = userEvent.setup();
    renderAssistant();
    await openPanel(user);

    expect(screen.getByTestId("assistant-input")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("assistant-panel")).not.toBeInTheDocument();
  });

  it("shows the offline banner and re-probes status on retry", async () => {
    const status = await mockApi.ai.status();
    const statusSpy = vi
      .spyOn(api.ai, "status")
      .mockResolvedValueOnce({ ...status, ready: false })
      .mockResolvedValueOnce({ ...status, ready: true });
    const user = userEvent.setup();
    renderAssistant();
    await openPanel(user);

    const banner = await screen.findByTestId("assistant-offline");
    expect(banner).toHaveTextContent(/Local model unavailable/i);
    expect(banner).toHaveTextContent(/answers are disabled until the runtime is ready/i);
    await user.type(screen.getByTestId("assistant-input"), "ping");
    await waitFor(() => expect(screen.getByTestId("assistant-send")).toBeDisabled());

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByTestId("assistant-offline")).not.toBeInTheDocument());
    expect(statusSpy).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("assistant-send")).toBeEnabled();
  });

  it("stops an in-flight generation", async () => {
    const user = userEvent.setup();
    vi.spyOn(api.ai, "chatStream").mockImplementation(
      (_input, _callbacks, signal) =>
        new Promise<void>((resolve) => {
          signal?.addEventListener("abort", () => resolve());
        }),
    );
    renderAssistant();
    await openPanel(user);

    await ask(user, "A question that will hang forever");
    expect(await screen.findByText("Thinking…")).toBeInTheDocument();
    expect(await screen.findByLabelText("Stop generating")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Stop generating"));
    await waitFor(() =>
      expect(screen.queryByLabelText("Stop generating")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("assistant-send")).toBeInTheDocument();
    expect(screen.queryByText("Thinking…")).not.toBeInTheDocument();
  });

  it("regenerates the last answer with the same question", async () => {
    const user = userEvent.setup();
    const streamSpy = vi.spyOn(api.ai, "chatStream");
    renderAssistant();
    await openPanel(user);

    await ask(user, "How does evidence ingest work?");
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();
    expect(streamSpy.mock.calls[0][0].conversation_id).toBeFalsy();

    const regenerate = await screen.findByTestId("assistant-regenerate");
    await user.click(regenerate);
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();

    expect(streamSpy).toHaveBeenCalledTimes(2);
    expect(streamSpy.mock.calls[1][0].question).toBe("How does evidence ingest work?");
    expect(screen.getAllByText(/How does evidence ingest work\?/)).toHaveLength(1);
    // Regeneration stays on the same server thread.
    expect(streamSpy.mock.calls[1][0].conversation_id).toBeTruthy();
  });

  it("shows stream errors inline with a retry action", async () => {
    const user = userEvent.setup();
    const streamSpy = vi
      .spyOn(api.ai, "chatStream")
      .mockImplementation(async (_input, callbacks) => {
        await new Promise((resolve) => setTimeout(resolve, 40));
        callbacks.onError?.("Local runtime exploded.");
      });
    renderAssistant();
    await openPanel(user);

    await ask(user, "Will fail");
    expect(await screen.findByText("Local runtime exploded.")).toBeInTheDocument();
    const retry = await screen.findByTestId("assistant-retry");

    await user.click(retry);
    expect(await screen.findByText("Local runtime exploded.")).toBeInTheDocument();
    expect(streamSpy).toHaveBeenCalledTimes(2);
    expect(streamSpy.mock.calls[1][0].question).toBe("Will fail");
  });

  it("copies an answer and reports clipboard failures", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });
    renderAssistant();
    await openPanel(user);

    await ask(user, "How does evidence ingest work?");
    expect(await screen.findByText(/Mock assistant answer/i)).toBeInTheDocument();

    await user.click(await screen.findByTestId("copy-answer"));
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toMatch(/Mock assistant answer/);
    expect(screen.getByTestId("copy-answer")).toHaveTextContent("Copied");

    writeText.mockRejectedValueOnce(new Error("permission denied"));
    await user.click(screen.getByTestId("copy-answer"));
    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((t) => t.variant === "error")).toBe(true),
    );
  });
});
