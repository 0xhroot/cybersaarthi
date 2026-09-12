import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import type { AdminUserListParams, CaseListParams, CaseMemberAddRequest, EntityListParams, FindingListParams, AuditParams, VictimListParams, IoTDeviceListParams, IoTEventListParams, InvestigationHypothesisListParams } from "@/api/contract";
import type { CaseStatus, CollectionCreateRequest, PageParams, VictimCreateRequest, VictimUpdateRequest, IoTDeviceCreateRequest, IoTDeviceUpdateRequest, IoTEventCreateRequest, DeviceRegisterRequest, HypothesisLinkEvidenceRequest, ReportGenerateRequest, InvestigationHypothesisCreateRequest } from "@/types/domain";

const MINUTE = 60_000;

export const queryKeys = {
  cases: (params?: CaseListParams) => ["cases", params] as const,
  case: (id: string) => ["cases", id] as const,
  caseMembers: (id: string) => ["cases", id, "members"] as const,
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
  users: (params?: AdminUserListParams) => ["users", params] as const,
  pendingUsers: () => ["users", "pending"] as const,
  victims: (caseId: string, params?: VictimListParams) => ["victims", caseId, params] as const,
  victim: (caseId: string, id: string) => ["victims", caseId, id] as const,
  iotDevices: (caseId: string, params?: IoTDeviceListParams) => ["iot", caseId, "devices", params] as const,
  iotDevice: (caseId: string, id: string) => ["iot", caseId, "devices", id] as const,
  iotDeviceStats: (caseId: string, id: string) => ["iot", caseId, "devices", id, "stats"] as const,
  iotEvents: (caseId: string, params?: IoTEventListParams) => ["iot", caseId, "events", params] as const,
  collections: (caseId: string) => ["collections", caseId] as const,
  fieldDevices: (caseId: string) => ["field-devices", caseId] as const,
  reports: (caseId: string) => ["reports", caseId] as const,
  health: () => ["health"] as const,
  investigationHypotheses: (caseId: string, params?: InvestigationHypothesisListParams) => ["hypotheses", caseId, params] as const,
  search: (caseId: string, q: string) => ["search", caseId, q] as const,
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

export function useCaseMembers(caseId: string) {
  return useQuery({
    queryKey: queryKeys.caseMembers(caseId),
    queryFn: () => api.cases.listMembers(caseId),
    staleTime: 30 * 1000,
  });
}

export function useAddCaseMember(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CaseMemberAddRequest) => api.cases.addMember(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.caseMembers(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useRemoveCaseMember(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.cases.removeMember(caseId, userId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.caseMembers(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
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
    mutationFn: (input: { file: File; dataSource?: string; collectionId?: string }) =>
      api.evidence.upload(caseId, {
        name: input.file.name,
        type: input.file.type,
        size: input.file.size,
        contents: input.file,
      }, input.dataSource, { collectionId: input.collectionId }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
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
      void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
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

export function useDeleteEvidence(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (evidenceId: string) => api.evidence.delete(caseId, evidenceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
      void qc.invalidateQueries({ queryKey: queryKeys.jobs(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useRetryGraphSync(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.evidence.retryGraphSync(caseId, jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobs(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.graph(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.graphStats(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.entities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.summary(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useReviewResolution(caseId: string) {
  return useQuery({
    queryKey: ["resolution", caseId, "review"] as const,
    queryFn: () => api.entities.reviewResolution(caseId),
    staleTime: MINUTE,
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

export function useAdminUsers(params?: AdminUserListParams) {
  return useQuery({
    queryKey: queryKeys.users(params),
    queryFn: () => api.users.list(params),
    placeholderData: keepPreviousData,
  });
}

export function useAdminPendingUsers() {
  return useQuery({
    queryKey: queryKeys.pendingUsers(),
    queryFn: () => api.users.listPending({ limit: 200 }),
  });
}

export type AdminUserAction =
  | { type: "approve"; userId: string; role: string }
  | { type: "reject"; userId: string }
  | { type: "suspend"; userId: string }
  | { type: "activate"; userId: string }
  | { type: "role"; userId: string; role: string };

export function useAdminUserMutation() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["users"] });
    void qc.invalidateQueries({ queryKey: queryKeys.audit() });
  };
  return useMutation<unknown, unknown, AdminUserAction>({
    mutationFn: (action) => {
      switch (action.type) {
        case "approve":
          return api.users.approve(action.userId, action.role);
        case "reject":
          return api.users.reject(action.userId);
        case "suspend":
          return api.users.suspend(action.userId);
        case "activate":
          return api.users.activate(action.userId);
        case "role":
          return api.users.changeRole(action.userId, action.role);
      }
    },
    onSuccess: invalidate,
    retry: false,
  });
}

/* ------------------------------- Victims ------------------------------ */

export function useVictims(caseId: string, params?: VictimListParams) {
  return useQuery({
    queryKey: queryKeys.victims(caseId, params),
    queryFn: () => api.victims.list(caseId, params),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useVictim(caseId: string, victimId: string | null) {
  return useQuery({
    queryKey: queryKeys.victim(caseId, victimId ?? ""),
    queryFn: () => api.victims.get(caseId, victimId ?? ""),
    enabled: Boolean(victimId),
    staleTime: MINUTE,
  });
}

export function useCreateVictim(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: VictimCreateRequest) => api.victims.create(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.victims(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useUpdateVictim(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ victimId, input }: { victimId: string; input: VictimUpdateRequest }) =>
      api.victims.update(caseId, victimId, input),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.victims(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.victim(caseId, variables.victimId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useDeleteVictim(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (victimId: string) => api.victims.delete(caseId, victimId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.victims(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

/* --------------------------------- IoT -------------------------------- */

export function useIoTDevices(caseId: string, params?: IoTDeviceListParams) {
  return useQuery({
    queryKey: queryKeys.iotDevices(caseId, params),
    queryFn: () => api.iot.devices(caseId, params),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useIoTDevice(caseId: string, deviceId: string | null) {
  return useQuery({
    queryKey: queryKeys.iotDevice(caseId, deviceId ?? ""),
    queryFn: () => api.iot.device(caseId, deviceId ?? ""),
    enabled: Boolean(deviceId),
    staleTime: MINUTE,
  });
}

export function useIoTDeviceStats(caseId: string, deviceId: string | null) {
  return useQuery({
    queryKey: queryKeys.iotDeviceStats(caseId, deviceId ?? ""),
    queryFn: () => api.iot.deviceStats(caseId, deviceId ?? ""),
    enabled: Boolean(deviceId),
    staleTime: MINUTE,
  });
}

export function useIoTEvents(caseId: string, params?: IoTEventListParams) {
  return useQuery({
    queryKey: queryKeys.iotEvents(caseId, params),
    queryFn: () => api.iot.events(caseId, params),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useRegisterIoTDevice(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: IoTDeviceCreateRequest) => api.iot.register(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.iotDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useUpdateIoTDevice(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, input }: { deviceId: string; input: IoTDeviceUpdateRequest }) =>
      api.iot.updateDevice(caseId, deviceId, input),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.iotDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.iotDevice(caseId, variables.deviceId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useDeleteIoTDevice(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => api.iot.deleteDevice(caseId, deviceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.iotDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useRecordIoTEvent(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: IoTEventCreateRequest) => api.iot.recordEvent(caseId, input),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: queryKeys.iotEvents(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.iotDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.iotDevice(caseId, result.device_id) });
      void qc.invalidateQueries({ queryKey: queryKeys.iotDeviceStats(caseId, result.device_id) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

/* ------------------------- Collections & devices ------------------------- */

export function useCollections(caseId: string) {
  return useQuery({
    queryKey: queryKeys.collections(caseId),
    queryFn: () => api.collections.list(caseId),
    staleTime: 30_000,
  });
}

export function useCreateCollection(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CollectionCreateRequest) => api.collections.create(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.collections(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useSealCollection(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (collectionId: string) => api.collections.seal(caseId, collectionId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.collections(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useFieldDevices(caseId: string) {
  return useQuery({
    queryKey: queryKeys.fieldDevices(caseId),
    queryFn: () => api.fieldDevices.list(caseId),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useServerHealth() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: () => api.health.health(),
    staleTime: MINUTE,
    retry: false,
  });
}

export function useRegisterFieldDevice(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DeviceRegisterRequest) => api.fieldDevices.register(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.fieldDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useApproveFieldDevice(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => api.fieldDevices.approve(caseId, deviceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.fieldDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useRevokeFieldDevice(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => api.fieldDevices.revoke(caseId, deviceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.fieldDevices(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

// Resolution review (accept / reject / merge).

export function useAcceptMatch(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (matchId: string) => api.entities.acceptMatch(caseId, matchId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resolution", caseId, "review"] });
      void qc.invalidateQueries({ queryKey: queryKeys.entities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useRejectMatch(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (matchId: string) => api.entities.rejectMatch(caseId, matchId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resolution", caseId, "review"] });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useMergeEntities(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { primaryEntityId: string; mergeEntityId: string }) =>
      api.entities.mergeEntities(caseId, {
        primary_entity_id: input.primaryEntityId,
        merge_entity_id: input.mergeEntityId,
      }),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.entities(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.entity(caseId, variables.primaryEntityId) });
      void qc.invalidateQueries({ queryKey: queryKeys.graph(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

// Evidence restore.

export function useRestoreEvidence(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (evidenceId: string) => api.evidence.restore(caseId, evidenceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

/* -------------------------------- Reports -------------------------------- */

export function useReports(caseId: string) {
  return useQuery({
    queryKey: queryKeys.reports(caseId),
    queryFn: () => api.reports.list(caseId),
    staleTime: 30_000,
  });
}

export function useGenerateReport(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ReportGenerateRequest) => api.reports.generate(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.reports(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

/* ------------------------- Investigation hypotheses ------------------------- */

export function useInvestigationHypotheses(caseId: string) {
  return useQuery({
    queryKey: queryKeys.investigationHypotheses(caseId),
    queryFn: () => api.hypotheses.list(caseId),
    staleTime: 30_000,
  });
}

export function useCreateInvestigationHypothesis(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: InvestigationHypothesisCreateRequest) => api.hypotheses.create(caseId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.investigationHypotheses(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useUpdateInvestigationHypothesisStatus(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ hypothesisId, status }: { hypothesisId: string; status: string }) =>
      api.hypotheses.updateStatus(caseId, hypothesisId, status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.investigationHypotheses(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

export function useLinkEvidenceToHypothesis(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ hypothesisId, input }: { hypothesisId: string; input: HypothesisLinkEvidenceRequest }) =>
      api.hypotheses.linkEvidence(caseId, hypothesisId, input),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.investigationHypotheses(caseId) });
      void variables;
    },
  });
}

export function useDeleteInvestigationHypothesis(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (hypothesisId: string) => api.hypotheses.delete(caseId, hypothesisId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.investigationHypotheses(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}

/* --------------------------------- Search -------------------------------- */

export function useCaseSearch(caseId: string, query: string) {
  return useQuery({
    queryKey: queryKeys.search(caseId, query),
    queryFn: () => api.search.search(caseId, { q: query, limit: 50 }),
    enabled: query.trim().length >= 2,
    staleTime: 30_000,
  });
}

export function useSubmitImportPackage(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { manifest: File; signature: File; files: File[] }) =>
      api.importPackages.submitPackage(caseId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["evidence", caseId] });
      void qc.invalidateQueries({ queryKey: queryKeys.timeline(caseId) });
      void qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}