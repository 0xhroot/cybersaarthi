import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Boxes, GitCompareArrows, Play, Radar, Scale, Users2, GitBranch, Activity, Layers, Wallet } from "lucide-react";
import {
  useAnalyticsRuns,
  useAnalyticsSummary,
  useCentrality,
  useCommunities,
  useNetworkDna,
  usePatterns,
  usePriorities,
  useRunAnalytics,
  useStrength,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer } from "@/components/layout/page";
import { InvestigationHeader } from "@/components/layout/investigation-header";
import { AnalysisPanel } from "@/components/ai/analysis-panel";
import { ContradictionPanel } from "@/components/evidence/contradiction-panel";
import { FinancialFlowPanel } from "@/components/evidence/financial-flow-panel";
import { CrossCasePanel } from "@/components/evidence/cross-case-panel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PriorityBadge, ProfileTierBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { TabBar } from "@/components/ui/tab-bar";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { Progress } from "@/components/ui/loading";
import { EmptyState } from "@/components/ui/empty-state";
import { formatPercent, formatRelative, pluralize } from "@/lib/utils";

// F08: only metrics the backend actually computes (degree|betweenness|closeness|
// pagerank — no eigenvector) are offered; a dead option 400s with 422.
const CENTRALITY_METRICS = ["degree", "betweenness", "pagerank", "closeness"] as const;
type Metric = (typeof CENTRALITY_METRICS)[number];

const RUN_STAGES = [
  { label: "Confirming exact graph", pct: 10 },
  { label: "Community detection", pct: 32 },
  { label: "Centrality + network DNA", pct: 55 },
  { label: "Relationship strength", pct: 74 },
  { label: "Patterns & hypotheses", pct: 92 },
];

/**
 * The analytics page answers three different questions, so it is split into
 * sections rather than one continuous scroll: what the model *interprets*
 * (analysis), what deterministically *conflicts* (contradictions), where the
 * money *goes* (financial), whether the pattern *repeats* (cross-case), and how
 * the graph is *shaped* (structure — the raw measurements the other four lean
 * on). Each id is a valid `?section=` value.
 */
const ANALYTICS_SECTIONS = [
  { id: "analysis", label: "AI analysis", icon: Radar },
  { id: "contradictions", label: "Contradictions", icon: GitCompareArrows },
  { id: "financial", label: "Financial flow", icon: Wallet },
  { id: "crosscase", label: "Cross-case", icon: Boxes },
  { id: "structure", label: "Network structure", icon: Scale },
] as const;

type SectionId = (typeof ANALYTICS_SECTIONS)[number]["id"];

const DEFAULT_SECTION: SectionId = "analysis";

export default function AnalyticsPage() {
  const { caseId = "" } = useParams();
  const runningAllowed = useCan("analytics.run");
  const canCrossCase = useCan("crosscase.read");

  const summary = useAnalyticsSummary(caseId);
  const dna = useNetworkDna(caseId);
  const communities = useCommunities(caseId);
  const priorities = usePriorities(caseId);
  const strength = useStrength(caseId);
  const patterns = usePatterns(caseId);
  const runs = useAnalyticsRuns(caseId);

  const [metric, setMetric] = useState<Metric>("degree");
  const centrality = useCentrality(caseId, metric);

  const run = useRunAnalytics(caseId);
  const [stageIndex, setStageIndex] = useState(-1);

  const [params, setParams] = useSearchParams();
  const requestedSection = params.get("section") as SectionId | null;
  // A stale/absent ?section= falls back to the default instead of rendering
  // an empty panel.
  const activeSection: SectionId =
    requestedSection && ANALYTICS_SECTIONS.some((s) => s.id === requestedSection)
      ? requestedSection
      : DEFAULT_SECTION;
  const setSection = (id: SectionId) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id === DEFAULT_SECTION) next.delete("section");
        else next.set("section", id);
        return next;
      },
      { replace: true },
    );

  const startRun = async () => {
    setStageIndex(0);
    try {
      await run.mutateAsync();
    } catch {
      setStageIndex(-1);
      return;
    }
    const timer = window.setInterval(() => {
      setStageIndex((i) => {
        if (i >= RUN_STAGES.length - 1) {
          window.clearInterval(timer);
          return -1;
        }
        return i + 1;
      });
    }, 450);
    window.setTimeout(() => {
      window.clearInterval(timer);
      setStageIndex(-1);
    }, RUN_STAGES.length * 480 + 400);
  };

  const s = summary.data;

  const stats = [
    { label: "Entities", value: s?.entity_count, icon: Users2 },
    { label: "Relationships", value: s?.relationship_count, icon: GitBranch },
    { label: "Communities", value: s?.community_count, icon: Layers },
    { label: "Avg network score", value: s ? formatPercent(s.average_network_score) : undefined, icon: Scale },
    { label: "Findings", value: s?.finding_count, icon: Activity },
  ];

  return (
    <PageContainer className="max-w-none">
      <InvestigationHeader
        eyebrow="Network intelligence"
        title="Analytics"
        description="Structural measurements of the case network. All values are derived from ingested evidence and clearly attributed."
        actions={
          runningAllowed ? (
            <Button onClick={() => void startRun()} disabled={run.isPending || stageIndex >= 0}>
              <Play className="size-4" /> {stageIndex >= 0 ? "Running…" : "Run analysis"}
            </Button>
          ) : undefined
        }
      />

      {stageIndex >= 0 ? (
        <Card className="mt-4 border-accent/30">
          <CardContent className="space-y-2">
            {RUN_STAGES.map((st, i) => (
              <div key={st.label} className="flex items-center gap-3">
                <span className={`tabular text-[11px] w-8 text-right ${i <= stageIndex ? "text-accent-strong" : "text-dim"}`}>
                  {st.pct}%
                </span>
                <p className={`text-xs ${i <= stageIndex ? "text-foreground" : "text-dim"} ${i === stageIndex ? "font-medium" : ""}`}>
                  {st.label}
                  {i === stageIndex ? "…" : ""}
                </p>
              </div>
            ))}
            <Progress value={RUN_STAGES[Math.min(stageIndex, RUN_STAGES.length - 1)]?.pct ?? 0} className="mt-2 h-1.5" />
            <p className="text-[11px] text-dim">Stages reflect the analyst workflow, not clock time.</p>
          </CardContent>
        </Card>
      ) : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {summary.isLoading
          ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20" />)
          : stats.map(({ label, value, icon: Icon }) => (
              <Card key={label}>
                <CardContent className="flex items-center gap-3">
                  <span className="grid size-8 shrink-0 place-items-center rounded-md bg-surface-3 text-muted">
                    <Icon className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-lg font-semibold tabular text-foreground">
                      {value ?? "—"}
                      {!value && summary.isError ? "!" : ""}
                    </p>
                    <p className="truncate text-[11px] uppercase tracking-wider text-dim">{label}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
      </div>

      {summary.isError ? (
        <Card className="mt-4"><ErrorState error={summary.error} onRetry={() => void summary.refetch()} /></Card>
      ) : null}

      {/* Section tabs. The selected section is mirrored into the URL so a
          deep link (and the browser back button) still work, and only the
          active section stays mounted — the four analysis panels each fetch
          their own data, so a single 22k-px scroll that mounted all of them
          also fired four request bursts nobody was looking at. */}
      <TabBar
        items={ANALYTICS_SECTIONS.filter((section) => section.id !== "crosscase" || canCrossCase)}
        active={activeSection}
        onChange={(id) => setSection(id as SectionId)}
        ariaLabel="Analytics sections"
        idPrefix="analytics"
        panelId={`analytics-panel-${activeSection}`}
        className="mt-5"
      />

      {/* Analysis panels are mutually exclusive; only the selected section
          stays mounted (see ANALYTICS_SECTIONS). */}
      <div
        id={`analytics-panel-${activeSection}`}
        role="tabpanel"
        aria-labelledby={`analytics-tab-${activeSection}`}
        className="mt-4"
      >
        {activeSection === "analysis" ? (
          <AnalysisPanel caseId={caseId} />
        ) : activeSection === "contradictions" ? (
          <Card><CardContent><ContradictionPanel caseId={caseId} /></CardContent></Card>
        ) : activeSection === "financial" ? (
          <Card><CardContent><FinancialFlowPanel caseId={caseId} /></CardContent></Card>
        ) : activeSection === "crosscase" && canCrossCase ? (
          <Card><CardContent><CrossCasePanel caseId={caseId} /></CardContent></Card>
        ) : (
          <NetworkStructureView
            dna={dna}
            communities={communities}
            centrality={centrality}
            priorities={priorities}
            strength={strength}
            patterns={patterns}
            runs={runs}
            metric={metric}
            setMetric={setMetric}
          />
        )}
      </div>
    </PageContainer>
  );
}

/**
 * The "Network structure" section: how the graph is shaped, and what the
 * deterministic measurements say about it. Split out of the main page so the
 * four analysis panels above can mount and unmount independently.
 */
function NetworkStructureView({
  dna,
  communities,
  centrality,
  priorities,
  strength,
  patterns,
  runs,
  metric,
  setMetric,
}: {
  dna: ReturnType<typeof useNetworkDna>;
  communities: ReturnType<typeof useCommunities>;
  centrality: ReturnType<typeof useCentrality>;
  priorities: ReturnType<typeof usePriorities>;
  strength: ReturnType<typeof useStrength>;
  patterns: ReturnType<typeof usePatterns>;
  runs: ReturnType<typeof useAnalyticsRuns>;
  metric: Metric;
  setMetric: (m: Metric) => void;
}) {
  return (
    <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Radar className="size-4 text-accent" /> Network DNA</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {dna.isLoading ? (
              <Skeleton className="h-24" />
            ) : dna.isError ? (
              <ErrorState error={dna.error} onRetry={() => void dna.refetch()} />
            ) : (dna.data ?? []).length === 0 ? (
              <EmptyState title="No profiles yet" description="Run analytics to score entities by network role." />
            ) : (
              (dna.data ?? []).map((p) => (
                <div key={p.entity_id} className="rounded-lg border border-border bg-surface-2 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{p.display_value}</p>
                    <ProfileTierBadge value={p.tier} />
                    <span className="tabular text-[11px] text-dim">{Math.round(p.overall_score * 100)}</span>
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-dim">{p.explanation}</p>
                  <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
                    {Object.values(p.features).slice(0, 6).map((f) => (
                      <div key={f.name} className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="truncate capitalize text-muted">{f.name.replace(/_/g, " ")}</span>
                        <span className="tabular text-foreground/80">{Math.round(f.normalized * 100)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Layers className="size-4 text-accent" /> Communities</CardTitle>
          </CardHeader>
          <CardContent>
            {communities.isLoading ? (
              <Skeleton className="h-24" />
            ) : communities.isError ? (
              <ErrorState error={communities.error} onRetry={() => void communities.refetch()} />
            ) : (communities.data ?? []).length === 0 ? (
              <EmptyState title="No communities" description="Run analytics to detect clusters." />
            ) : (
              <div className="space-y-3">
                {(communities.data ?? []).map((c) => (
                  <div key={c.community_id} className="rounded-lg border border-border bg-surface-2 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm text-foreground">
                        <span className="font-mono text-xs text-dim">{c.community_id.slice(0, 8)}</span> · {c.member_count} members
                      </p>
                      <span className="tabular text-[11px] text-dim">density {c.density.toFixed(2)}</span>
                    </div>
                    <p className="mt-1.5 text-[11px] leading-relaxed text-dim">{c.explanation ?? "Community detected by graph partition."}</p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {c.dominant_entity_types.map((t) => <span key={t} className="rounded border border-border bg-surface-3 px-1.5 py-0.5 text-[10px] capitalize text-muted">{t}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Scale className="size-4 text-accent" /> Centrality</CardTitle>
            <div className="flex flex-wrap gap-1.5">
              {CENTRALITY_METRICS.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMetric(m)}
                  className={[
                    "rounded-md border px-2 py-1 text-[11px] capitalize transition-colors",
                    metric === m ? "border-accent/40 bg-accent-soft text-accent-strong" : "border-border bg-surface-3 text-muted",
                  ].join(" ")}
                >
                  {m}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {centrality.isLoading ? (
              <Skeleton className="h-24" />
            ) : centrality.isError ? (
              <ErrorState error={centrality.error} onRetry={() => void centrality.refetch()} />
            ) : (centrality.data ?? []).length === 0 ? (
              <EmptyState
                title="No entries for this metric"
                description="This run only computed degree centrality. Run analytics on a backend that supports this metric to populate it."
              />
            ) : (
              <div className="space-y-2">
                {(centrality.data ?? []).slice(0, 12).map((c) => (
                  <div key={`${c.metric}-${c.entity_id}`} className="flex items-center gap-3">
                    <span className="tabular w-6 text-[11px] text-dim">{c.rank ?? "·"}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
                      <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.round(c.normalized * 100)}%` }} />
                    </div>
                    <span className="tabular w-12 text-right text-[11px] text-muted">{Math.round(c.normalized * 100)}</span>
                  </div>
                ))}
                <p className="pt-1 text-[11px] text-dim">{centrality.data?.[0]?.exact ? "Exact computation." : "Approximate (scalable) computation."}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-5">
        <PrioritiesCard priorities={priorities} />
        <StrengthCard strength={strength} />
        <PatternsCard patterns={patterns} />
        <RunsCard runs={runs} />
      </div>
    </div>
  );
}

function PrioritiesCard({ priorities }: { priorities: ReturnType<typeof usePriorities> }) {
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="size-4 text-accent" /> Priorities</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        {priorities.isLoading ? (
          <Skeleton className="h-24" />
        ) : (priorities.data ?? []).length === 0 ? (
          <EmptyState title="No priorities yet" description="Run analytics to rank entities." />
        ) : (
          (priorities.data ?? []).map((p) => (
            <div key={p.entity_id} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm text-foreground">{p.display_value}</span>
              <PriorityBadge value={p.tier} />
              <span className="tabular text-[11px] text-dim">{Math.round(p.priority_score * 100)}</span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function StrengthCard({ strength }: { strength: ReturnType<typeof useStrength> }) {
  return (
    <Card>
      <CardHeader><CardTitle>Relationship strength</CardTitle></CardHeader>
      <CardContent>
        {strength.isLoading ? (
          <Skeleton className="h-24" />
        ) : (strength.data ?? []).length === 0 ? (
          <EmptyState title="No relationships scored" description="Strength appears after analytics run." />
        ) : (
          <div className="space-y-2">
            {(strength.data ?? []).slice(0, 8).map((r) => (
              <div key={r.relationship_id} className="rounded-md border border-border bg-surface-2 px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs capitalize text-foreground">{r.relationship_type.replace("_", " ")}</span>
                  <span className="tabular text-[11px] text-dim">{Math.round(r.strength * 100)}</span>
                </div>
                <p className="mt-1 text-[10px] text-dim">
                  {r.evidence_count} {pluralize(r.evidence_count, "record")} · {r.independent_files} {pluralize(r.independent_files, "source file")}
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PatternsCard({ patterns }: { patterns: ReturnType<typeof usePatterns> }) {
  return (
    <Card>
      <CardHeader><CardTitle>Patterns</CardTitle></CardHeader>
      <CardContent>
        {patterns.isLoading ? (
          <Skeleton className="h-24" />
        ) : (patterns.data ?? []).length === 0 ? (
          <EmptyState title="No patterns matched" description="Patterns surface in the findings workspace." />
        ) : (
          <div className="space-y-2">
            {(patterns.data ?? []).map((p) => (
              <div key={p.title} className="rounded-md border border-border bg-surface-2 px-2.5 py-2">
                <p className="text-xs font-medium text-foreground">{p.title}</p>
                <p className="mt-0.5 line-clamp-2 text-[11px] text-dim">{p.summary}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RunsCard({ runs }: { runs: ReturnType<typeof useAnalyticsRuns> }) {
  return (
    <Card>
      <CardHeader><CardTitle>Analysis runs</CardTitle></CardHeader>
      <CardContent>
        {(runs.data?.items ?? []).length === 0 ? (
          <EmptyState title="No runs yet" description="Every analysis execution is recorded here." />
        ) : (
          <div className="space-y-2">
            {(runs.data?.items ?? []).slice(0, 6).map((runItem) => (
              <div key={runItem.id} className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-dim">{runItem.id.slice(0, 8)}</span>
                <span className="text-right text-[11px] capitalize text-muted">{runItem.status}</span>
                <span className="tabular text-[11px] text-dim">{formatRelative(runItem.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}