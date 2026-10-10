import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Case } from "@/types/domain";

const useCaseHook = vi.hoisted(() => vi.fn());
const archiveHook = vi.hoisted(() => vi.fn());
const updateHook = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/queries", () => ({
  useCase: (cid: string) => useCaseHook(cid),
  useArchiveCase: () => archiveHook(),
  useUpdateCase: () => updateHook(),
}));

vi.mock("@/lib/permissions", () => ({
  useCan: () => true,
}));

import CaseLayout from "@/app/pages/case-layout";

const mutation = () => ({ isPending: false, mutateAsync: vi.fn() });

const CASE: Case = {
  id: "case-1",
  case_number: "SHOW-2026-005",
  title: "Ponzi investment racket",
  description: "Synthetic demo case.",
  status: "in_progress",
  owner_id: "u1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

const TAB_LABELS = [
  "Overview",
  "Entities",
  "Evidence",
  "Victims",
  "Devices",
  "IoT",
  "Graph",
  "Analytics",
  "Hypotheses",
  "Findings",
  "Reports",
  "Timeline",
];

const renderCase = (entry = "/app/cases/case-1") =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/app/cases/:caseId" element={<CaseLayout />}>
          <Route index element={<div>overview-body</div>} />
          {TAB_LABELS.slice(1).map((label) => (
            <Route key={label} path={label.toLowerCase()} element={<div>{label.toLowerCase()}-body</div>} />
          ))}
        </Route>
      </Routes>
    </MemoryRouter>,
  );

describe("case workspace navigation", () => {
  beforeEach(() => {
    archiveHook.mockReturnValue(mutation());
    updateHook.mockReturnValue(mutation());
  });

  it("renders all twelve case tabs in one accessible strip", () => {
    useCaseHook.mockReturnValue({ data: CASE, isLoading: false, isError: false, error: null, refetch: vi.fn() });
    renderCase();
    const nav = screen.getByRole("navigation", { name: "Case workspace" });
    for (const label of TAB_LABELS) {
      expect(nav).toHaveTextContent(label);
    }
    expect(nav.querySelectorAll("a")).toHaveLength(12);
  });

  it("keeps the strip horizontally scrollable without page overflow", () => {
    useCaseHook.mockReturnValue({ data: CASE, isLoading: false, isError: false, error: null, refetch: vi.fn() });
    renderCase();
    const nav = screen.getByRole("navigation", { name: "Case workspace" });
    // overflow-x-auto + a subtle (not hidden) scrollbar keep every tab reachable
    expect(nav.className).toContain("overflow-x-auto");
    expect(nav.className).toContain("subtle-scrollbar");
    expect(nav.className).not.toContain("no-scrollbar");
    // compact padding is what lets all twelve tabs fit on one line at 1280px+
    const first = nav.querySelector("a");
    expect(first?.className).toContain("px-1.5");
    expect(first?.className).toContain("shrink-0");
  });

  it("highlights the active tab and switches content on click", () => {
    useCaseHook.mockReturnValue({ data: CASE, isLoading: false, isError: false, error: null, refetch: vi.fn() });
    renderCase("/app/cases/case-1/entities");
    const nav = screen.getByRole("navigation", { name: "Case workspace" });
    const entities = [...nav.querySelectorAll("a")].find((a) => a.textContent === "Entities")!;
    const reports = [...nav.querySelectorAll("a")].find((a) => a.textContent === "Reports")!;
    expect(entities.getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("entities-body")).toBeInTheDocument();

    fireEvent.click(reports);
    expect(reports.getAttribute("aria-current")).toBe("page");
    expect(entities.getAttribute("aria-current")).toBeNull();
    expect(screen.getByText("reports-body")).toBeInTheDocument();
  });

  it("keeps Reports and Timeline reachable in the strip", () => {
    useCaseHook.mockReturnValue({ data: CASE, isLoading: false, isError: false, error: null, refetch: vi.fn() });
    renderCase("/app/cases/case-1/timeline");
    const nav = screen.getByRole("navigation", { name: "Case workspace" });
    const timeline = [...nav.querySelectorAll("a")].find((a) => a.textContent === "Timeline")!;
    expect(timeline.getAttribute("aria-current")).toBe("page");
    expect([...nav.querySelectorAll("a")].some((a) => a.textContent === "Reports")).toBe(true);
    expect(screen.getByText("timeline-body")).toBeInTheDocument();
  });

  it("shows the case header context above the tabs", () => {
    useCaseHook.mockReturnValue({ data: CASE, isLoading: false, isError: false, error: null, refetch: vi.fn() });
    renderCase();
    expect(screen.getByText("SHOW-2026-005")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ponzi investment racket" })).toBeInTheDocument();
  });
});
