import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Focus, Maximize, Network, ShieldAlert } from "lucide-react";
import { useGraph, useGraphStats } from "@/hooks/queries";
import { CytoGraph, type Selection } from "@/components/graph/cyto-graph";
import { PageContainer } from "@/components/layout/page";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { EntityTypeBadge } from "@/components/status";
import { RELATIONSHIP_TYPE_META } from "@/components/status";
import { formatPercent, formatRelative } from "@/lib/utils";
import type { EntityType, RelationshipType } from "@/types/domain";

const ENTITY_TYPES = ["person", "phone", "vehicle", "organization", "account", "location", "document", "event"] as const;
const RELATIONSHIP_TYPES = ["called", "owns", "works_for", "associated_with", "located_at", "visited", "transferred_to"] as const;

export default function GraphPage() {
  const { caseId = "" } = useParams();
  const graph = useGraph(caseId);
  const stats = useGraphStats(caseId);
  const [selection, setSelection] = useState<Selection>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | undefined>(undefined);
  const [hiddenEntityTypes, setHiddenEntityTypes] = useState<Set<string>>(new Set());
  const [hiddenRelationshipTypes, setHiddenRelationshipTypes] = useState<Set<string>>(new Set());

  const nodes = graph.data?.nodes ?? [];
  const edges = graph.data?.edges ?? [];
  const signature = `${nodes.length}:${edges.length}:${stats.data?.generated_at ?? ""}`;

  const toggleEntity = (type: string) => {
    setHiddenEntityTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleRelationship = (type: string) => {
    setHiddenRelationshipTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const resetView = () => {
    setFocusNodeId(undefined);
    setSelection(null);
  };

  const selectedNode = selection?.kind === "node" ? selection.entity : undefined;
  const selectedEdge = selection?.kind === "edge" ? selection.edge : undefined;

  const edgeTypeBadge: string | undefined = useMemo(() => {
    if (!selectedEdge) return undefined;
    return [...RELATIONSHIP_TYPES].find((t) => t === selectedEdge.relationship_type);
  }, [selectedEdge]);

  if (graph.isError) {
    return (
      <PageContainer className="py-8">
        <Card><ErrorState error={graph.error} onRetry={() => void graph.refetch()} /></Card>
      </PageContainer>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface px-5 py-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-foreground">Network graph</h2>
          <p className="text-xs text-dim">
            {nodes.length} entities · {edges.length} relationships
            <span className="mx-1.5 text-border-strong">|</span>
            {stats.data ? (
              <span title={`Refreshed ${stats.data.generated_at}`}>
                {stats.data.synced ? "synced to evidence" : "review pending"} · {formatRelative(stats.data.generated_at)}
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={resetView}><Maximize className="size-4" /> Fit</Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-0 lg:flex-row">
        <div className="relative min-h-[420px] min-w-0 flex-1 bg-[radial-gradient(ellipse_at_center,rgba(214,161,78,0.05),transparent_65%)] lg:min-h-0">
          {graph.isLoading ? (
            <div className="grid h-full place-items-center px-6">
              <Skeleton className="h-[420px] w-full" />
            </div>
          ) : nodes.length === 0 ? (
            <div className="grid h-full place-items-center px-6 text-center">
              <div>
                <Network className="mx-auto mb-3 size-8 text-dim" />
                <p className="text-sm text-muted">Nothing to render yet.</p>
                <p className="mt-1 text-xs text-dim">The graph appears after evidence is ingested and synced.</p>
              </div>
            </div>
          ) : (
            <CytoGraph
              nodes={nodes}
              edges={edges}
              signature={signature}
              focusNodeId={focusNodeId}
              hiddenEntityTypes={hiddenEntityTypes}
              hiddenRelationshipTypes={hiddenRelationshipTypes}
              onSelect={setSelection}
            />
          )}

          <div className="pointer-events-none absolute bottom-3 left-3 max-w-[70%] rounded-md border border-border bg-surface/90 px-2.5 py-1.5 text-[11px] leading-relaxed text-dim shadow-lg backdrop-blur">
            Drag to pan · scroll to zoom · click a node or edge to inspect. The layout is cosmetic — positions
            carry no evidential meaning.
          </div>
        </div>

        <aside className="w-full shrink-0 border-t border-border bg-surface-2 lg:w-[300px] lg:border-l lg:border-t-0">
          <div className="space-y-5 p-4">
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wider text-dim">Entity types</p>
              <div className="flex flex-wrap gap-1.5">
                {ENTITY_TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleEntity(t)}
                    className={[
                      "rounded-md border px-2 py-1 text-[11px] capitalize transition-colors",
                      hiddenEntityTypes.has(t)
                        ? "border-border text-dim opacity-50"
                        : "border-border-strong bg-surface-3 text-foreground",
                    ].join(" ")}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wider text-dim">Relationship types</p>
              <div className="flex flex-wrap gap-1.5">
                {RELATIONSHIP_TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleRelationship(t)}
                    className={[
                      "rounded-md border px-2 py-1 text-[11px] capitalize transition-colors",
                      hiddenRelationshipTypes.has(t)
                        ? "border-border text-dim opacity-50"
                        : "border-border-strong bg-surface-3 text-foreground",
                    ].join(" ")}
                  >
                    {RELATIONSHIP_TYPE_META[t]?.label ?? t.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-border bg-surface p-3">
              {selectedNode ? (
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <EntityTypeBadge value={selectedNode.entity_type as EntityType} />
                    <button
                      type="button"
                      onClick={() => setFocusNodeId(selectedNode.id)}
                      className="text-[11px] text-accent hover:text-accent-strong"
                    >
                      <Focus className="mr-1 inline size-3" /> focus
                    </button>
                  </div>
                  <p className="mt-2 text-sm font-medium leading-snug text-foreground">{selectedNode.display_value}</p>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-dim" title={selectedNode.id}>{selectedNode.id}</p>
                  {selectedEdge ? null : (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {selectedNode.aliases.map((a, i) => <Badge key={i}>{a}</Badge>)}
                    </div>
                  )}
                  <p className="mt-2 text-[11px] text-dim">
                    Confidence{" "}
                    <span className="tabular text-foreground/80">
                      {selectedNode.confidence != null ? formatPercent(selectedNode.confidence) : "—"}
                    </span>
                  </p>
                  <Link
                    to={`/app/cases/${caseId}/entities/${selectedNode.id}`}
                    className="mt-3 inline-block text-xs text-accent hover:text-accent-strong"
                  >
                    Open entity record →
                  </Link>
                </div>
              ) : selectedEdge ? (
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-dim">Relationship</p>
                  <p className="mt-1 text-sm font-medium capitalize text-foreground">
                    {RELATIONSHIP_TYPE_META[selectedEdge.relationship_type as RelationshipType]?.label ?? selectedEdge.relationship_type}
                    {edgeTypeBadge ? (
                      <span className="ml-2"><Badge>{edgeTypeBadge}</Badge></span>
                    ) : null}
                  </p>
                  <p className="mt-2 text-[11px] text-dim">
                    Confidence{" "}
                    <span className="tabular text-foreground/80">
                      {selectedEdge.confidence != null ? formatPercent(selectedEdge.confidence) : "—"}
                    </span>
                  </p>
                  <p className="mt-3 flex items-center gap-2 text-[11px] leading-relaxed text-dim">
                    <ShieldAlert className="size-3.5 shrink-0 text-high" />
                    Extracted from source records; verify against the original file before relying on it.
                  </p>
                </div>
              ) : (
                <p className="py-1 text-xs leading-relaxed text-dim">
                  Select a node or edge to inspect its extracted attributes.
                </p>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}