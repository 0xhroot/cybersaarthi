import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import type { CaseListParams, EntityListParams, FindingListParams, AuditParams } from "@/api/contract";
import type { CaseStatus, PageParams } from "@/types/domain";

const MINUTE = 60_000;

export const queryKeys = {
  cases: (params?: CaseListParams) => ["cases", params] as const,
  case: (id: string) => ["cases", id] as const,
  entities: (caseId: string, params?: EntityListParams) => ["entities", caseId, params] as const,
  entity: (caseId: string, id: string) => ["entities", caseId, id] as const,
  relationships: (caseId: string) => ["relationships", caseId] as const,
  evidence: (caseId: string, params?: PageParams) => ["evidence", caseId, params] as const,
  evidenceDetail: (caseId: string, id: string) => ["evidence", caseId, id] as const,
  provenance: (caseId: string, id: string) => ["evidence", caseId, id, "provenance"] as const,
  jobs: (caseId: string) => ["jobs", caseId] as const,
  graph: (caseId: string) => ["graph", caseId] as const,
  graphStats: (caseId: string) => ["graph", caseId, "stats"] as const,
  ego: (caseId: string, id: string) => ["graph", caseId, "ego", id] as const,
  summary: (caseId: string) => ["analytics", caseId, "summary"] as const,
  centrality: (caseId: string, metric: string) => ["analytics", caseId, "centrality", metric] as const,
  communities: (caseId: string) => ["analytics", caseId, "communities"] as const,
  networkDna: (caseId: string) => ["analytics", caseId, "network-dna"] as const,
  priorities: (caseId: string) => ["analytics", caseId, "priorities"] as const,
  strength: (caseId: string) => ["analytics", caseId, "strength"] as const,
  patterns: (caseId: string) => ["analytics", caseId, "patterns"] as const,
  hypotheses: (caseId: string) => ["analytics", caseId, "hypotheses"] as const,
  runs: (caseId: string) => ["analytics", caseId, "runs"] as const,
  findings: (caseId: string, params?: FindingListParams) => ["findings", caseId, params] as const,
  finding: (caseId: string, id: string) => ["findings", caseId, id] as const,
  findingStats: (caseId: string) => ["findings", caseId, "stats"] as const,
  audit: (params?: AuditParams) => ["audit", params] as const,
  timeline: (caseId: string) => ["timeline", caseId] as const,
};

export function useCases(params?: CaseListParams) {
  return useQuery({
    queryKey: queryKeys.cases(params),
    queryFn: () => api.cases.list(params),
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  });
}

export function useCase(caseId: string) {
  return useQuery({
    queryKey: queryKeys.case(caseId),
    queryFn: () => api.cases.get(caseId),
    staleTime: MINUTE,
  });
}

export function useEntities(caseId: string, params?: EntityListParams) {
  return useQuery({
    queryKey: queryKeys.entities(caseId, params),
    queryFn: () => api.entities.list(caseId, params),
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  });
}

export function useEntity(caseId: string, entityId: string) {
  return useQuery({
    queryKey: queryKeys.entity(caseId, entityId),
    queryFn: () => api.entities.get(caseId, entityId),
    enabled: Boolean(entityId),
    staleTime: MINUTE,
  });
}

export function useRelationships(caseId: string) {
  return useQuery({
    queryKey: queryKeys.relationships(caseId),
    queryFn: () => api.entities.relationships(caseId),
    staleTime: 5 * MINUTE,
  });
}

export function useEvidence(caseId: string, params?: PageParams) {
  return useQuery({
    queryKey: queryKeys.evidence(caseId, params),
    queryFn: () => api.evidence.list(caseId, params),
    staleTime: 30 * 1000,
  });
}

export function useEvidenceDetail(caseId: string, evidenceId: string | null) {
  return useQuery({
    queryKey: queryKeys.evidenceDetail(caseId, evidenceId ?? ""),
    queryFn: () => api.evidence.get(caseId, evidenceId ?? ""),
    enabled: Boolean(evidenceId),
    staleTime: MINUTE,
  });
}

export function useProvenance(caseId: string, evidenceId: string | null) {
  return useQuery({
    queryKey: queryKeys.provenance(caseId, evidenceId ?? ""),
    queryFn: () => api.evidence.provenance(caseId, evidenceId ?? ""),
    enabled: Boolean(evidenceId),
    staleTime: MINUTE,
  });
}

export function useIngestJobs(caseId: string) {
  return useQuery({
    queryKey: queryKeys.jobs(caseId),
    queryFn: () => api.evidence.jobs(caseId),
    staleTime: 30 * 1000,
  });
}

export function useGraph(caseId: string) {
  return useQuery({
    queryKey: queryKeys.graph(caseId),
    queryFn: () => api.graph.get(caseId),
    staleTime: 5 * MINUTE,
  });
}

export function useGraphStats(caseId: string) {
  return useQuery({
    queryKey: queryKeys.graphStats(caseId),
    queryFn: () => api.graph.stats(caseId),
    staleTime: MINUTE,
  });
}

export function useEntityEgo(caseId: string, entityId: string | null) {
  return useQuery({
    queryKey: queryKeys.ego(caseId, entityId ?? ""),
    queryFn: () => api.graph.ego(caseId, entityId ?? ""),
    enabled: Boolean(entityId),
    staleTime: MINUTE,
  });
}

export function useAnalyticsSummary(caseId: string) {
  return useQuery({
    queryKey: queryKeys.summary(caseId),
    queryFn: () => api.analytics.summary(caseId),
    staleTime: MINUTE,
  });
}

export function useCentrality(caseId: string, metric = "degree") {
  return useQuery({
    queryKey: queryKeys.centrality(caseId, metric),
    queryFn: () => api.analytics.centrality(caseId, metric),
    staleTime: MINUTE,
  });
}

export function useCommunities(caseId: string) {
  return useQuery({
    queryKey: queryKeys.communities(caseId),
    queryFn: () => api.analytics.communities(caseId),
    staleTime: MINUTE,
  });
}

export function useNetworkDna(caseId: string) {
  return useQuery({
    queryKey: queryKeys.networkDna(caseId),
    queryFn: () => api.analytics.networkDna(caseId),
    staleTime: MINUTE,
  });
}

export function usePriorities(caseId: string) {
  return useQuery({
    queryKey: queryKeys.priorities(caseId),
    queryFn: () => api.analytics.priorities(caseId),
    staleTime: MINUTE,
  });
}

export function useStrength(caseId: string) {
  return useQuery({
    queryKey: queryKeys.strength(caseId),
    queryFn: () => api.analytics.strength(caseId),
    staleTime: 5 * MINUTE,
  });
}

export function usePatterns(caseId: string) {
  return useQuery({
    queryKey: queryKeys.patterns(caseId),
    queryFn: () => api.analytics.patterns(caseId),
    staleTime: MINUTE,
  });
}

export function useHypotheses(caseId: string) {
  return useQuery({
    queryKey: queryKeys.hypotheses(caseId),
    queryFn: () => api.analytics.hypotheses(caseId),
    staleTime: MINUTE,
  });
}

export function useAnalyticsRuns(caseId: string) {
  return useQuery({
    queryKey: queryKeys.runs(caseId),
    queryFn: () => api.analytics.runs(caseId),
    staleTime: MINUTE,
  });
}

export function useFindings(caseId: string, params?: FindingListParams) {
  return useQuery({
    queryKey: queryKeys.findings(caseId, params),
    queryFn: () => api.findings.list(caseId, params),
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  });
}

export function useFinding(caseId: string, findingId: string) {
  return useQuery({
    queryKey: queryKeys.finding(caseId, findingId),
    queryFn: () => api.findings.get(caseId, findingId),
    enabled: Boolean(findingId),
    staleTime: 30 * 1000,
  });
}

export function useFindingStats(caseId: string) {
  return useQuery({
    queryKey: queryKeys.findingStats(caseId),
    queryFn: () => api.findings.stats(caseId),
    staleTime: 30 * 1000,
  });
}

export function useAudit(params?: AuditParams) {
  const enabled = true;
  return useQuery({
    queryKey: queryKeys.audit(params),
    queryFn: () => api.audit.list(params),
    staleTime: 30 * 1000,
    enabled,
    retry: (failureCount, error) =>
      (error as { status?: number }).status === 403 ? false : failureCount < 2,
  });
}

export function useTimeline(caseId: string) {
  return useQuery({
    queryKey: queryKeys.timeline(caseId),
    queryFn: () => api.timeline.events(caseId),
    staleTime: MINUTE,
  });
}

/* ------------------------------ Mutations ------------------------------ */

export function useCreateCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; description?: string | null; status?: Exclude<CaseStatus, "archived"> }) =>
      api.cases.create(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cases"] });
    },
  });
}

export function useUpdateCase(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      title?: string | null;
      description?: string | null;
      status?: Exclude<CaseStatus, "archived">;
    }) => api.cases.update(caseId, input),
    onSuccess: (updated) => {
      void qc.setQueryData(queryKeys.case(caseId), updated);
      void qc.invalidateQueries({ queryKey: ["cases"] });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
    },
  });
}

export function useArchiveCase(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.cases.archive(caseId),
    onSuccess: (updated) => {
      void qc.setQueryData(queryKeys.case(caseId), updated);
      void qc.invalidateQueries({ queryKey: ["cases"] });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
    },
  });
}

export function useUploadEvidence(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { file: File; dataSource?: string }) =>
      api.evidence.upload(caseId, {
        name: input.file.name,
        type: input.file.type,
        size: input.file.size,
        contents: input.file,
      }, input.dataSource),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.evidence(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.jobs(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useIngestEvidence(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (evidenceFileId: string) => api.evidence.ingest(caseId, evidenceFileId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.evidence(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.jobs(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.entities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.graph(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.graphStats(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.summary(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
      // F04: the case's analytics panes derive from the same pipeline, so a
      // successful ingest/run must refresh every analytics-backed panel too.
      void qc.invalidateQueries({ queryKey: ["analytics", caseId, "centrality"] });
      void qc.invalidateQueries({ queryKey: queryKeys.communities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.networkDna(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.priorities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.strength(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.patterns(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.hypotheses(caseId) });
    },
  });
}

export function useRunAnalytics(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.analytics.run(caseId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.runs(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.findings(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.findingStats(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.summary(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
      // F04: refresh every analytics-derived key so no dashboard panel shows
      // stale data (up to the previous 60 s cache window) after a run.
      void qc.invalidateQueries({ queryKey: ["analytics", caseId, "centrality"] });
      void qc.invalidateQueries({ queryKey: queryKeys.communities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.networkDna(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.priorities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.strength(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.patterns(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.hypotheses(caseId) });
    },
  });
}

export function useUpdateFindingStatus(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { findingId: string; status: string; reason?: string | null }) =>
      api.findings.updateStatus(caseId, input.findingId, {
        status: input.status,
        reason: input.reason,
      }),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.findings(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.finding(caseId, variables.findingId) });
      void qc.invalidateQueries({ queryKey: queryKeys.findingStats(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useInvalidateCaseData() {
  const qc = useQueryClient();
  return (caseId: string) => {
    void qc.invalidateQueries({ queryKey: ["entities", caseId] });
    void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
    void qc.invalidateQueries({ queryKey: ["graph", caseId] });
    void qc.invalidateQueries({ queryKey: ["analytics", caseId] });
    void qc.invalidateQueries({ queryKey: ["findings", caseId] });
    void qc.invalidateQueries({ queryKey: ["timeline", caseId] });
    void qc.invalidateQueries({ queryKey: ["cases"] });
  };
}