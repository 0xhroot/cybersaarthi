import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import type { GraphEdge, GraphNode } from "@/types/domain";

export type Selection =
  | { kind: "node"; entity: GraphNode }
  | { kind: "edge"; edge: GraphEdge }
  | null;

const NODE_COLORS: Record<string, string> = {
  person: "#d6a14e",
  phone: "#6ea8d8",
  vehicle: "#e08a5a",
  organization: "#8ec98a",
  account: "#d7888a",
  location: "#9f86d6",
  document: "#86c5c9",
  event: "#c98ac4",
};

const FALLBACK_COLOR = "#8a93a5";

function truncateLabel(value: string): string {
  return value.length > 24 ? `${value.slice(0, 22)}…` : value;
}

export interface CytoGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  signature: string;
  focusNodeId?: string;
  hiddenEntityTypes?: Set<string>;
  hiddenRelationshipTypes?: Set<string>;
  onSelect: (selection: Selection) => void;
}

export function CytoGraph({
  nodes,
  edges,
  signature,
  focusNodeId,
  hiddenEntityTypes,
  hiddenRelationshipTypes,
  onSelect,
}: CytoGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!containerRef.current) return;

    const elements: ElementDefinition[] = [
      ...nodes.map((n) => ({
        group: "nodes" as const,
        data: {
          id: n.id,
          display_value: truncateLabel(n.display_value),
          entity_type: n.entity_type,
          confidence: n.confidence,
          aliases: n.aliases,
          canonical_value: n.canonical_value,
        },
      })),
      ...edges.map((e) => ({
        group: "edges" as const,
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          relationship_type: e.relationship_type,
          confidence: e.confidence,
        },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      wheelSensitivity: 0.6,
      minZoom: 0.15,
      maxZoom: 3,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (el) => NODE_COLORS[el.data("entity_type") as string] ?? FALLBACK_COLOR,
            "border-width": 1,
            "border-color": "rgba(255,255,255,0.18)",
            label: "data(display_value)",
            color: "#d7dbe3",
            "font-size": 10,
            "font-family": "Inter Variable, Inter, system-ui, sans-serif",
            "text-valign": "bottom",
            "text-margin-y": 6,
            "text-wrap": "none",
            "overlay-opacity": 0,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.2,
            "line-color": "#3a4254",
            "target-arrow-color": "#3a4254",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.8,
            "overlay-opacity": 0,
          },
        },
        {
          selector: "edge:selected",
          style: {
            "line-color": "#d6a14e",
            "target-arrow-color": "#d6a14e",
            width: 2,
          },
        },
        {
          selector: "node.focused",
          style: {
            "border-width": 3,
            "border-color": "#d6a14e",
            "background-color": (el) => NODE_COLORS[el.data("entity_type") as string] ?? FALLBACK_COLOR,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        padding: 40,
        nodeRepulsion: 8000,
        idealEdgeLength: 70,
        edgeElasticity: 120,
        randomize: true,
      },
    });

    cyRef.current = cy;

    cy.on("tap", "node", (event) => {
      const data = event.target.data();
      const node = nodes.find((n) => n.id === data.id);
      if (node) onSelectRef.current({ kind: "node", entity: node });
    });
    cy.on("tap", "edge", (event) => {
      const data = event.target.data();
      const edge = edges.find((e) => e.id === data.id);
      if (edge) onSelectRef.current({ kind: "edge", edge });
    });
    cy.on("tap", (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [signature, nodes, edges]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const applyFilters = () => {
      cy.nodes().forEach((node) => {
        const type = node.data("entity_type") as string;
        const hidden = hiddenEntityTypes?.has(type) ?? false;
        node.style("display", hidden ? "none" : "element");
      });
      cy.edges().forEach((edge) => {
        const type = edge.data("relationship_type") as string;
        const hidden = hiddenRelationshipTypes?.has(type) ?? false;
        edge.style("display", hidden ? "none" : "element");
      });
    };

    applyFilters();

    if (focusNodeId) {
      cy.getElementById(focusNodeId).style("display", "element");
      cy.elements().removeClass("focused");
      cy.getElementById(focusNodeId).addClass("focused");
      const target = cy.getElementById(focusNodeId);
      if (target.length) {
        cy.animate({
          fit: { eles: target, padding: 120 },
          duration: 350,
        });
      }
    }
  }, [focusNodeId, hiddenEntityTypes, hiddenRelationshipTypes, signature]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      role="img"
      aria-label="Case network graph"
      style={{ minHeight: 0 }}
    />
  );
}