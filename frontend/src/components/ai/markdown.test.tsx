import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Markdown } from "@/components/ai/markdown";

function renderMarkdown(text: string) {
  return render(<Markdown>{text}</Markdown>);
}

describe("assistant markdown", () => {
  it("renders headings, emphasis, and inline code", () => {
    renderMarkdown("# Incident summary\n\nSome **bold** and *italic* wrapped in `code`.");

    expect(screen.getByRole("heading", { name: "Incident summary" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    const inlineCode = screen.getByText("code");
    expect(inlineCode.tagName).toBe("CODE");
  });

  it("renders GFM tables with headers and cells", () => {
    renderMarkdown("| File | Rows |\n| --- | --- |\n| call_detail_record.csv | 4821 |");

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "File" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Rows" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "call_detail_record.csv" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "4821" })).toBeInTheDocument();
  });

  it("renders fenced code blocks with a copy button", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });

    renderMarkdown("```python\nprint('hi')\n```");

    expect(screen.getByText("python")).toBeInTheDocument(); // language label
    expect(screen.getByText("print('hi')").tagName).toBe("CODE");

    await user.click(screen.getByTestId("copy-code"));
    expect(writeText).toHaveBeenCalledWith("print('hi')");
  });

  it("renders ordered and unordered lists plus blockquotes", () => {
    const { container } = renderMarkdown("1. one\n2. two\n\n- alpha\n- beta\n\n> quoted");

    expect(screen.getAllByRole("list")).toHaveLength(2);
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(container.querySelector("blockquote")).not.toBeNull();
    expect(screen.getByText("quoted")).toBeInTheDocument();
  });

  it("only turns http(s) and relative URLs into links", () => {
    const { container } = renderMarkdown(
      "[ok](https://example.com/a) [rel](/cases/x) [bad](javascript:alert(1))",
    );

    const anchors = Array.from(container.querySelectorAll("a"));
    expect(anchors).toHaveLength(2);
    expect(anchors[0]).toHaveAttribute("href", "https://example.com/a");
    expect(anchors[1]).toHaveAttribute("href", "/cases/x");

    // Unsafe protocol degrades to plain text, never a clickable javascript: URL.
    const bad = screen.getByText("bad");
    expect(bad.tagName).toBe("SPAN");
    expect(bad.closest("a")).toBeNull();
  });
});
