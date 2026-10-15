import { useCallback, useEffect, useRef, useState, type ButtonHTMLAttributes } from "react";
import {
  ArrowLeft,
  Bot,
  Check,
  Copy,
  History,
  Loader2,
  Maximize2,
  Minimize2,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { useLocation } from "react-router-dom";

import { api } from "@/api";
import type { AiConversation, AiMessage, AiSource, AiToolEvent } from "@/api/contract";
import { Markdown } from "@/components/ai/markdown";
import { Button } from "@/components/ui/button";
import { toastFromError } from "@/components/ui/toast";
import { cn, formatRelative } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: AiSource[];
  toolEvents?: AiToolEvent[];
  grounded?: boolean;
  pending?: boolean;
  error?: string;
}

type PanelView = "chat" | "history";

function caseIdFromPath(pathname: string): string | null {
  const match = /^\/cases\/([0-9a-fA-F-]{36})/.exec(pathname);
  return match ? match[1] : null;
}

function fromServerMessage(message: AiMessage, index: number): ChatMessage {
  return {
    id: message.id || `m-${index}`,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    sources: message.sources ?? undefined,
    toolEvents: message.tool_events ?? undefined,
    grounded: message.grounded || undefined,
  };
}

async function writeToClipboard(text: string): Promise<void> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (!clipboard?.writeText) {
    throw new Error("Clipboard access is unavailable in this browser.");
  }
  await clipboard.writeText(text);
}

function IconButton({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        "rounded p-1 text-dim transition hover:text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        className,
      )}
    />
  );
}

/**
 * Floating assistant: talks only to the authenticated /api/v1/ai/* gateway.
 * Case context is taken from the current route, so answers stay scoped to the
 * case the investigator is already authorized to view.
 *
 * The widget keeps a `conversationId` so follow-up messages continue the same
 * server thread instead of opening a new conversation per message.
 */
export function Assistant() {
  const location = useLocation();
  const caseId = caseIdFromPath(location.pathname);

  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [view, setView] = useState<PanelView>("chat");
  const [ready, setReady] = useState<boolean | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const [history, setHistory] = useState<AiConversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const statusLoadedRef = useRef(false);
  const copiedTimerRef = useRef<number | null>(null);

  const probeStatus = useCallback(async (force = false) => {
    if (!force && statusLoadedRef.current) return;
    statusLoadedRef.current = true;
    try {
      const status = await api.ai.status();
      setReady(status.enabled && status.ready);
    } catch {
      setReady(false);
    }
  }, []);

  useEffect(() => {
    if (open) void probeStatus();
  }, [open, probeStatus]);

  // Esc cancels an inline edit/confirm first, then closes the panel.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (renamingId) {
        setRenamingId(null);
        return;
      }
      if (confirmingDeleteId) {
        setConfirmingDeleteId(null);
        return;
      }
      setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, renamingId, confirmingDeleteId]);

  // Opening the panel (or returning from history) puts focus in the composer.
  useEffect(() => {
    if (open && view === "chat") textareaRef.current?.focus();
  }, [open, view]);

  useEffect(() => {
    const el = scrollRef.current;
    // jsdom and some embedded webviews do not implement scrollTo.
    if (typeof el?.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    } else if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, open, view]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
    };
  }, []);

  const copyAnswer = useCallback(async (message: ChatMessage) => {
    try {
      await writeToClipboard(message.content);
      setCopiedId(message.id);
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = window.setTimeout(() => setCopiedId(null), 1500);
    } catch (error) {
      toastFromError(error, "Could not copy the answer.");
    }
  }, []);

  const send = useCallback(
    async (questionOverride?: string) => {
      const question = (questionOverride ?? input).trim();
      if (!question || busy) return;
      if (questionOverride === undefined) setInput("");
      setBusy(true);
      const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: question };
      const assistantId = `a-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "", pending: true },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      // Capture the thread id at send time so a concurrent "new chat" cannot
      // re-route this exchange into the wrong conversation.
      const activeConversationId = conversationId;
      let answer = "";
      let sawToken = false;
      const toolEvents: AiToolEvent[] = [];

      const patchAssistant = (patch: Partial<ChatMessage>) => {
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)));
      };

      const rememberConversation = (id?: string) => {
        if (id) {
          setConversationId(id);
          return;
        }
        if (activeConversationId) return;
        // Older streams may omit the id in `done`; recover the thread with one
        // cheap request instead of silently dropping the conversation binding.
        void api.ai
          .listConversations({ limit: 1 })
          .then(({ items }) => {
            const newest = items[0];
            if (newest) setConversationId(newest.id);
          })
          .catch(() => {
            /* non-fatal: the next message simply opens a fresh thread */
          });
      };

      try {
        await api.ai.chatStream(
          {
            question,
            mode: caseId ? "case" : "general",
            case_id: caseId,
            conversation_id: activeConversationId,
          },
          {
            onToken: (text) => {
              sawToken = true;
              answer += text;
              patchAssistant({ content: answer });
            },
            onSources: (sources) => patchAssistant({ sources }),
            onTool: (event) => {
              // Tokens streamed before a `tool` event are the raw tool fence
              // the model emitted, not answer text — per the stream contract
              // the client clears the buffer so the fence never renders.
              answer = "";
              toolEvents.push(event);
              patchAssistant({ content: "", toolEvents: [...toolEvents] });
            },
            onError: (message) => {
              patchAssistant({
                pending: false,
                error: message,
                content: answer || "",
              });
            },
            onDone: (info) => {
              patchAssistant({
                pending: false,
                content:
                  answer ||
                  info.answer ||
                  info.sources.map((s) => s.label || s.id).join(", ") ||
                  "Done.",
                sources: info.sources,
                grounded: info.grounded,
                toolEvents:
                  info.tool_events.length
                    ? info.tool_events
                    : (toolEvents.length ? toolEvents : undefined),
              });
              rememberConversation(info.conversation_id);
            },
          },
          controller.signal,
        );
        if (!sawToken) {
          // Defensive: stream ended without tokens or done event.
          patchAssistant({ pending: false });
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        toastFromError(error, "The assistant request failed.");
        patchAssistant({
          pending: false,
          error: "The assistant request failed. Check the local AI runtime and retry.",
        });
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [input, busy, caseId, conversationId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setMessages((prev) => prev.map((m) => (m.pending ? { ...m, pending: false } : m)));
  }, []);

  /** Drop the last assistant reply (or failed attempt) and re-ask its question. */
  const resendLast = useCallback(() => {
    if (busy) return;
    const last = messages[messages.length - 1];
    const question = messages[messages.length - 2];
    if (!last || last.role !== "assistant" || !question || question.role !== "user") return;
    setMessages((prev) => prev.slice(0, Math.max(prev.length - 2, 0)));
    void send(question.content);
  }, [busy, messages, send]);

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setMessages([]);
    setConversationId(null);
    setInput("");
    setRenamingId(null);
    setConfirmingDeleteId(null);
    setView("chat");
    textareaRef.current?.focus();
  }, []);

  const openHistory = useCallback(async () => {
    setView("history");
    setHistoryLoading(true);
    try {
      const { items } = await api.ai.listConversations({ limit: 20 });
      setHistory(items);
    } catch (error) {
      toastFromError(error, "Could not load conversation history.");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadConversation = useCallback(async (conversation: AiConversation) => {
    setLoadingConversationId(conversation.id);
    try {
      const { items } = await api.ai.listMessages(conversation.id);
      setMessages(items.map(fromServerMessage));
      setConversationId(conversation.id);
      setView("chat");
    } catch (error) {
      toastFromError(error, "Could not load that conversation.");
    } finally {
      setLoadingConversationId(null);
    }
  }, []);

  const saveRename = useCallback(
    async (conversationIdToRename: string) => {
      const title = renameValue.trim();
      if (!title) {
        setRenamingId(null);
        return;
      }
      try {
        const updated = await api.ai.renameConversation(conversationIdToRename, title);
        setHistory((prev) => prev.map((c) => (c.id === conversationIdToRename ? { ...c, ...updated } : c)));
      } catch (error) {
        toastFromError(error, "Could not rename the conversation.");
      } finally {
        setRenamingId(null);
      }
    },
    [renameValue],
  );

  const deleteConversation = useCallback(
    async (conversationIdToDelete: string) => {
      try {
        await api.ai.deleteConversation(conversationIdToDelete);
        setHistory((prev) => prev.filter((c) => c.id !== conversationIdToDelete));
        // If the open thread was deleted, the next send starts a fresh one.
        if (conversationId === conversationIdToDelete) setConversationId(null);
      } catch (error) {
        toastFromError(error, "Could not delete the conversation.");
      } finally {
        setConfirmingDeleteId(null);
      }
    },
    [conversationId],
  );

  // Client-side scope filter: general threads everywhere, case threads only
  // while the investigator is inside that case.
  const visibleHistory = history.filter((c) => c.case_id == null || c.case_id === caseId);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close AI assistant" : "Open AI assistant"}
        aria-expanded={open}
        data-testid="assistant-fab"
        className={cn(
          "fixed bottom-5 right-5 z-50 inline-flex size-12 items-center justify-center rounded-full",
          "border border-border bg-surface-3 text-muted shadow-lg transition hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        )}
      >
        {open ? <X className="size-5" /> : <Bot className="size-5" />}
      </button>

      {open && (
        <section
          aria-label="CyberSaarthi assistant"
          data-testid="assistant-panel"
          className={cn(
            "z-50 flex flex-col rounded-lg border border-border bg-surface shadow-xl",
            expanded
              ? "fixed inset-4 sm:inset-8"
              : "fixed bottom-20 right-5 max-h-[70vh] w-[min(26rem,calc(100vw-2.5rem))]",
          )}
        >
          <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <div className="flex min-w-0 items-center gap-2">
              {view === "history" ? (
                <IconButton
                  aria-label="Back to chat"
                  data-testid="assistant-back"
                  onClick={() => setView("chat")}
                >
                  <ArrowLeft className="size-4" aria-hidden="true" />
                </IconButton>
              ) : (
                <Bot className="size-4 shrink-0 text-accent" aria-hidden="true" />
              )}
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-foreground">
                  {view === "history" ? "History" : "Investigation assistant"}
                </h2>
                <p className="text-[11px] text-dim">
                  {view === "history"
                    ? "Stored conversations"
                    : caseId
                      ? "Scoped to this case · local model"
                      : ready
                        ? "Platform help · local model"
                        : "Local model"}
                  {view === "chat" && ready === false && " · offline"}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {view === "chat" && (
                <>
                  <IconButton
                    aria-label="Start new chat"
                    data-testid="assistant-new"
                    onClick={startNewChat}
                  >
                    <Plus className="size-4" aria-hidden="true" />
                  </IconButton>
                  <IconButton
                    aria-label="Conversation history"
                    data-testid="assistant-history"
                    onClick={() => void openHistory()}
                  >
                    <History className="size-4" aria-hidden="true" />
                  </IconButton>
                  <IconButton
                    aria-label={expanded ? "Minimize assistant" : "Expand assistant"}
                    aria-expanded={expanded}
                    data-testid="assistant-expand"
                    onClick={() => setExpanded((v) => !v)}
                  >
                    {expanded ? (
                      <Minimize2 className="size-4" aria-hidden="true" />
                    ) : (
                      <Maximize2 className="size-4" aria-hidden="true" />
                    )}
                  </IconButton>
                </>
              )}
              <IconButton aria-label="Close assistant" onClick={() => setOpen(false)}>
                <X className="size-4" aria-hidden="true" />
              </IconButton>
            </div>
          </header>

          {view === "chat" && ready === false && (
            <div
              role="status"
              data-testid="assistant-offline"
              className="flex items-center justify-between gap-3 border-b border-border bg-critical/10 px-4 py-2"
            >
              <p className="text-xs leading-relaxed text-critical">
                Local model unavailable — answers are disabled until the runtime is ready.
              </p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setReady(null);
                  void probeStatus(true);
                }}
              >
                Retry
              </Button>
            </div>
          )}

          {view === "chat" ? (
            <div
              ref={scrollRef}
              data-testid="assistant-messages"
              aria-live="polite"
              className="flex-1 space-y-3 overflow-y-auto px-4 py-3"
            >
              {messages.length === 0 && (
                <p className="text-xs text-dim">
                  Ask about this case, the platform, or investigative methodology. Answers are
                  generated on-device by a local model and cite authorized records.
                </p>
              )}
              {messages.map((message, index) => {
                const showCopy =
                  message.role === "assistant" && !message.pending && message.content.length > 0;
                const showResend =
                  message.role === "assistant" &&
                  !message.pending &&
                  index === messages.length - 1 &&
                  !busy;
                const hasChips =
                  (message.sources && message.sources.length > 0) || Boolean(message.grounded);
                return (
                  <article
                    key={message.id}
                    className={cn("text-xs", message.role === "user" && "text-right")}
                  >
                    <div
                      className={cn(
                        "inline-block max-w-[92%] rounded-lg px-3 py-2 text-left leading-relaxed",
                        message.role === "user"
                          ? "bg-surface-3 text-foreground"
                          : "border border-border bg-surface-2 text-muted",
                      )}
                    >
                      {message.role === "assistant" && message.pending && !message.content && (
                        <span className="inline-flex items-center gap-1.5 text-dim">
                          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                          Thinking…
                        </span>
                      )}
                      {message.content &&
                        (message.role === "assistant" ? (
                          <Markdown>{message.content}</Markdown>
                        ) : (
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        ))}
                      {message.error && (
                        <p className="mt-1 text-critical" role="alert">
                          {message.error}
                        </p>
                      )}
                      {message.toolEvents && message.toolEvents.length > 0 && (
                        <ul className="mt-2 space-y-1 border-t border-border pt-2 text-[11px] text-dim">
                          {message.toolEvents.map((event, eventIndex) => (
                            <li key={`${event.tool}-${eventIndex}`}>
                              tool: {event.tool} · {event.ok ? "ok" : (event.error ?? "failed")}
                            </li>
                          ))}
                        </ul>
                      )}
                      {(hasChips || showCopy || showResend) && (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
                          {message.sources?.slice(0, 8).map((source) => {
                            const label = `${source.type}: ${source.label || source.id.slice(0, 8)}`;
                            return source.url ? (
                              <a
                                key={`${source.type}-${source.id}`}
                                href={source.url}
                                className="rounded border border-border bg-surface-3 px-1.5 py-0.5 text-[10px] text-muted transition hover:text-foreground"
                              >
                                {label}
                              </a>
                            ) : (
                              <span
                                key={`${source.type}-${source.id}`}
                                className="rounded border border-border px-1.5 py-0.5 text-[10px] text-dim"
                              >
                                {label}
                              </span>
                            );
                          })}
                          {message.grounded && (
                            <span className="rounded border border-accent/40 px-1.5 py-0.5 text-[10px] text-accent">
                              grounded
                            </span>
                          )}
                          {(showCopy || showResend) && (
                            <span className="ml-auto flex items-center gap-2">
                              {showCopy && (
                                <button
                                  type="button"
                                  data-testid="copy-answer"
                                  aria-label={
                                    copiedId === message.id ? "Answer copied" : "Copy answer"
                                  }
                                  onClick={() => void copyAnswer(message)}
                                  className={cn(
                                    "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition",
                                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                                    copiedId === message.id
                                      ? "text-accent"
                                      : "text-dim hover:text-foreground",
                                  )}
                                >
                                  {copiedId === message.id ? (
                                    <>
                                      <Check className="size-3" aria-hidden="true" />
                                      Copied
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="size-3" aria-hidden="true" />
                                      Copy
                                    </>
                                  )}
                                </button>
                              )}
                              {showResend &&
                                (message.error ? (
                                  <button
                                    type="button"
                                    data-testid="assistant-retry"
                                    aria-label="Retry answer"
                                    onClick={resendLast}
                                    className={cn(
                                      "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-accent transition",
                                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                                    )}
                                  >
                                    <RefreshCw className="size-3" aria-hidden="true" />
                                    Retry
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    data-testid="assistant-regenerate"
                                    aria-label="Regenerate answer"
                                    onClick={resendLast}
                                    className={cn(
                                      "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-dim transition hover:text-foreground",
                                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                                    )}
                                  >
                                    <RefreshCw className="size-3" aria-hidden="true" />
                                    Regenerate
                                  </button>
                                ))}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div
              data-testid="assistant-history-list"
              className="flex-1 space-y-2 overflow-y-auto px-3 py-3"
            >
              {historyLoading ? (
                <p className="inline-flex items-center gap-1.5 text-xs text-dim">
                  <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                  Loading conversations…
                </p>
              ) : visibleHistory.length === 0 ? (
                <p className="text-xs text-dim">No conversations yet.</p>
              ) : (
                <ul role="list" className="space-y-2">
                  {visibleHistory.map((conversation) => (
                    <li
                      key={conversation.id}
                      className="rounded-md border border-border bg-surface-2 p-2"
                    >
                      {renamingId === conversation.id ? (
                        <form
                          className="flex items-center gap-1.5"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void saveRename(conversation.id);
                          }}
                        >
                          <label
                            htmlFor={`rename-${conversation.id}`}
                            className="sr-only"
                          >
                            Conversation name
                          </label>
                          <input
                            id={`rename-${conversation.id}`}
                            autoFocus
                            value={renameValue}
                            onChange={(event) => setRenameValue(event.target.value)}
                            className="min-w-0 flex-1 rounded border border-border bg-surface-3 px-2 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                          />
                          <IconButton
                            type="submit"
                            aria-label="Save conversation name"
                            data-testid="assistant-rename-save"
                          >
                            <Check className="size-3.5" aria-hidden="true" />
                          </IconButton>
                          <IconButton
                            aria-label="Cancel rename"
                            onClick={() => setRenamingId(null)}
                          >
                            <X className="size-3.5" aria-hidden="true" />
                          </IconButton>
                        </form>
                      ) : (
                        <div className="flex items-start gap-1">
                          <button
                            type="button"
                            data-testid={`assistant-history-item-${conversation.id}`}
                            disabled={loadingConversationId === conversation.id}
                            onClick={() => void loadConversation(conversation)}
                            className={cn(
                              "min-w-0 flex-1 rounded text-left",
                              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                            )}
                          >
                            <span className="block truncate text-xs font-medium text-foreground">
                              {conversation.title}
                            </span>
                            <span className="mt-1 flex items-center gap-1.5 text-[10px] text-dim">
                              <span>
                                {formatRelative(
                                  conversation.last_message_at ?? conversation.updated_at,
                                )}
                              </span>
                              <span className="rounded border border-border px-1 py-0.5">
                                {conversation.case_id
                                  ? `case ${conversation.case_id.slice(0, 8)}`
                                  : "general"}
                              </span>
                            </span>
                          </button>
                          <IconButton
                            aria-label={`Rename conversation: ${conversation.title}`}
                            data-testid={`assistant-rename-${conversation.id}`}
                            onClick={() => {
                              setRenamingId(conversation.id);
                              setRenameValue(conversation.title);
                            }}
                          >
                            <Pencil className="size-3.5" aria-hidden="true" />
                          </IconButton>
                          {confirmingDeleteId === conversation.id ? (
                            <span className="flex items-center gap-1">
                              <IconButton
                                aria-label={`Confirm delete conversation: ${conversation.title}`}
                                data-testid="assistant-delete-confirm"
                                onClick={() => void deleteConversation(conversation.id)}
                              >
                                <Trash2 className="size-3.5 text-critical" aria-hidden="true" />
                              </IconButton>
                              <IconButton
                                aria-label="Cancel delete"
                                onClick={() => setConfirmingDeleteId(null)}
                              >
                                <X className="size-3.5" aria-hidden="true" />
                              </IconButton>
                            </span>
                          ) : (
                            <IconButton
                              aria-label={`Delete conversation: ${conversation.title}`}
                              data-testid={`assistant-delete-${conversation.id}`}
                              onClick={() => setConfirmingDeleteId(conversation.id)}
                            >
                              <Trash2 className="size-3.5" aria-hidden="true" />
                            </IconButton>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {view === "chat" && (
            <form
              className="flex items-end gap-2 border-t border-border px-3 py-3"
              onSubmit={(event) => {
                event.preventDefault();
                void send();
              }}
            >
              <label htmlFor="assistant-input" className="sr-only">
                Ask the assistant
              </label>
              <textarea
                id="assistant-input"
                ref={textareaRef}
                data-testid="assistant-input"
                rows={2}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send();
                  }
                }}
                placeholder={caseId ? "Ask about this case…" : "Ask CyberSaarthi…"}
                className="min-h-[2.75rem] flex-1 resize-none rounded-md border border-border bg-surface-3 px-3 py-2 text-xs text-foreground placeholder:text-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              />
              {busy ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={stop}
                  aria-label="Stop generating"
                >
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Stop
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="sm"
                  disabled={!input.trim() || ready === false}
                  aria-label="Send message"
                  data-testid="assistant-send"
                >
                  <Send className="size-4" aria-hidden="true" />
                  Send
                </Button>
              )}
            </form>
          )}
        </section>
      )}
    </>
  );
}
