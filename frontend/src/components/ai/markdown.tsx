import { isValidElement, useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";

import { toastFromError } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

/**
 * Only `http:`/`https:` links (and relative URLs) may become anchors; anything
 * else (`javascript:`, `data:`, …) is rendered as plain text instead.
 */
function isSafeHref(href: string): boolean {
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return /^https?:/i.test(href);
  return true; // relative: `/cases/…`, `#anchor`, `./file`
}

async function writeToClipboard(text: string): Promise<void> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (!clipboard?.writeText) {
    throw new Error("Clipboard access is unavailable in this browser.");
  }
  await clipboard.writeText(text);
}

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const onCopy = () => {
    void (async () => {
      try {
        await writeToClipboard(code);
        setCopied(true);
        if (timerRef.current !== null) window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(() => setCopied(false), 1500);
      } catch (error) {
        toastFromError(error, "Could not copy the code block.");
      }
    })();
  };

  return (
    <div className="my-2 overflow-hidden rounded-md border border-border bg-surface-3">
      <div className="flex items-center justify-between border-b border-border px-2 py-1">
        <span className="text-[10px] uppercase tracking-wide text-dim">{language ?? "code"}</span>
        <button
          type="button"
          data-testid="copy-code"
          aria-label="Copy code block"
          onClick={onCopy}
          className={cn(
            "rounded p-0.5 text-dim transition hover:text-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            copied && "text-accent",
          )}
        >
          {copied ? <Check className="size-3" aria-hidden="true" /> : <Copy className="size-3" aria-hidden="true" />}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-muted">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function blockCodeText(child: ReactNode): string {
  const raw = (child as { props?: { children?: ReactNode } } | null)?.props?.children;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) return raw.join("");
  return raw == null ? "" : String(raw);
}

const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h2 className="mt-3 mb-1.5 text-sm font-semibold text-foreground first:mt-0">{children}</h2>
  ),
  h2: ({ children }) => (
    <h3 className="mt-3 mb-1.5 text-sm font-semibold text-foreground first:mt-0">{children}</h3>
  ),
  h3: ({ children }) => (
    <p className="mt-2 mb-1 text-xs font-semibold text-foreground first:mt-0">{children}</p>
  ),
  h4: ({ children }) => (
    <p className="mt-2 mb-1 text-xs font-semibold text-foreground first:mt-0">{children}</p>
  ),
  p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="my-1.5 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-border pl-3 text-dim italic">{children}</blockquote>
  ),
  hr: () => <hr className="my-3 border-border" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-3">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border px-2 py-1 text-left font-semibold text-foreground">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1 text-muted">{children}</td>,
  a: ({ href, children }) => {
    if (!href || !isSafeHref(href)) return <span className="text-muted">{children}</span>;
    return (
      <a
        href={href}
        className="text-accent underline underline-offset-2 hover:text-accent-strong"
        {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      >
        {children}
      </a>
    );
  },
  // Inline code (block code is intercepted by `pre` below and never rendered here).
  code: ({ children }) => (
    <code className="rounded border border-border bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-accent-strong">
      {children}
    </code>
  ),
  pre: ({ children }) => {
    const child = Array.isArray(children) ? children[0] : children;
    if (isValidElement<{ className?: string; children?: ReactNode }>(child)) {
      const language = /language-([\w+-]+)/.exec(child.props.className ?? "")?.[1];
      return <CodeBlock language={language} code={blockCodeText(child).replace(/\n+$/, "")} />;
    }
    return (
      <pre className="my-2 overflow-x-auto rounded-md border border-border bg-surface-3 px-3 py-2 font-mono text-[11px] text-muted">
        {children}
      </pre>
    );
  },
};

/**
 * Safe Markdown renderer for assistant answers: GFM tables + fenced code blocks,
 * no `dangerouslySetInnerHTML` anywhere (React escapes every text node).
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("text-xs leading-relaxed", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={MARKDOWN_COMPONENTS}
        urlTransform={(url) => (isSafeHref(url) ? url : "")}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
