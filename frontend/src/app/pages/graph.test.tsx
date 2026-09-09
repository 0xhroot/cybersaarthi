import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const graphHook = vi.hoisted(() => vi.fn());
const statsHook = vi.hoisted(() => vi.fn());
const cytoGraph = vi.hoisted(() =>
  vi.fn((props: unknown) => {
    void props;
    return <div data-testid="graph-canvas" />;
  }),
);

vi.mock("@/hooks/queries", () => ({
  useGraph: (cid: string) => graphHook(cid),
  useGraphStats: (cid: string) => statsHook(cid),
}));

vi.mock("@/components/graph/cyto-graph", () => ({
  CytoGraph: (props: Record<string, unknown>) => cytoGraph(props),
}));

import GraphPage from "@/app/pages/graph";

const renderGraph = () =>
  render(
    <MemoryRouter initialEntries={["/app/cases/case-1"]}>
      <GraphPage />
    </MemoryRouter>,
  );

describe("graph page fit interaction", () => {
  it("Fit button triggers a viewport fit (fitSignal) and clears focus", () => {
    graphHook.mockReturnValue({
      data: { nodes: [{ id: "n1", entity_type: "person" }], edges: [] },
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
      error: null,
    });
    statsHook.mockReturnValue({
      data: { synced: true, generated_at: "2026-01-01T00:00:00Z" },
    });

    renderGraph();

    const fitButton = screen.getByRole("button", { name: /fit/i });
    expect(fitButton).toBeTruthy();

    cytoGraph.mockClear();
    fireEvent.click(fitButton);
    const firstCallProps = cytoGraph.mock.calls[0][0] as unknown as {
      fitSignal: number;
      focusNodeId: string | undefined;
    };
    // Fit bumps the signal (the graph component then refits the viewport) and
    // clears any focused node so the whole visible graph is shown.
    expect(firstCallProps.fitSignal).toBeGreaterThan(0);
    expect(firstCallProps.focusNodeId).toBeUndefined();

    cytoGraph.mockClear();
    fireEvent.click(fitButton);
    const secondCallProps = cytoGraph.mock.calls[0][0] as unknown as { fitSignal: number };
    expect(secondCallProps.fitSignal).toBe(firstCallProps.fitSignal + 1);
  });
});