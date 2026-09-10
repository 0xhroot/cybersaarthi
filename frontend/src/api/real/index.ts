import { request } from "@/api/client/http";
import { authSession } from "@/api/client/session";
import { apiConfig } from "@/config/env";
import type {
  AdminUserListParams,
  Api,
  ApiAdminUserService,
  ApiAnalyticsService,
  ApiAuditService,
  ApiAuthService,
  ApiCaseService,
  ApiCollectionService,
  ApiEntityService,
  ApiEvidenceService,
  ApiFieldDeviceService,
  ApiFindingService,
  ApiGraphService,
  ApiHypothesisService,
  ApiImportService,
  ApiIoTService,
  ApiReportService,
  ApiSearchService,
  ApiTimelineService,
  ApiVictimService,
  CaseListParams,
  CollectionListParams,
  DeviceListParams,
  InvestigationHypothesisListParams,
  RegisterInput,
  RegisteredUserOut,
  ReportListParams,
  SearchParams,
} from "@/api/contract";
import type {
  AdminUserList,
  AdminUserOut,
  AnalyticsRun,
  AnalyticsRunList,
  AnalyticsSummary,
  AuditList,
  Case,
  CaseList,
  CaseMemberListResponse,
  CentralityEntry,
  Collection,
  CollectionList,
  Community,
  DeviceList,
  DeviceVerifyResponse,
  EntityDetail,
  EntityEgoGraph,
  EntityList,
  EntityMergeRequest,
  EvidenceCreateResponse,
  EvidenceDetail,
  EvidenceList,
  EvidenceProvenanceResponse,
  EvidenceRestoreResponse,
  FieldDevice,
  Finding,
  FindingList,
  FindingStats,
  FindingStatusOut,
  GraphResponse,
  GraphStats,
  GraphSyncResult,
  Hypothesis,
  ImportAccepted,
  IngestAccepted,
  IngestJobList,
  InvestigationHypothesis,
  InvestigationHypothesisList,
  IoTDevice,
  IoTDeviceList,
  IoTDeviceStats,
  IoTEvent,
  IoTEventList,
  MeResponse,
  NetworkProfile,
  Pattern,
  Priority,
  RelationshipList,
  RelationshipStrength,
  Report,
  ReportList,
  ReviewDecisionResponse,
  ReviewList,
  SearchResponse,
  TimelineEvent,
  TimelineEventList,
  TokenResponse,
  Victim,
  VictimList,
} from "@/types/domain";

export function buildQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

const authService: ApiAuthService = {
  async login(input) {
    return request<TokenResponse>("/auth/login", {
      method: "POST",
      body: { username: input.username, password: input.password },
      headers: { Authorization: "" }, // login is public
    });
  },
  async me() {
    return request<MeResponse>("/auth/me");
  },
  async register(input: RegisterInput) {
    return request<RegisteredUserOut>("/auth/register", {
      method: "POST",
      body: { username: input.username, email: input.email, password: input.password },
    });
  },
  async logout() {
    await request<void>("/auth/logout", {
      method: "POST",
      headers: { Authorization: authSession.getToken() ? `Bearer ${authSession.getToken()}` : "" },
    });
  },
};

const userService: ApiAdminUserService = {
  list(params: AdminUserListParams = {}) {
    return request<AdminUserList>(
      `/admin/users${buildQuery({
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
        ...(params.status ? { status: params.status } : {}),
        ...(params.search ? { search: params.search } : {}),
      })}`,
    );
  },
  listPending(params: AdminUserListParams = {}) {
    return request<AdminUserList>(
      `/admin/users/pending${buildQuery({
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      })}`,
    );
  },
  get(userId) {
    return request<AdminUserOut>(`/admin/users/${userId}`);
  },
  approve(userId, role) {
    return request<AdminUserOut>(`/admin/users/${userId}/approve`, {
      method: "POST",
      body: { role },
    });
  },
  reject(userId) {
    return request<AdminUserOut>(`/admin/users/${userId}/reject`, {
      method: "POST",
      body: {},
    });
  },
  suspend(userId) {
    return request<AdminUserOut>(`/admin/users/${userId}/suspend`, {
      method: "POST",
      body: {},
    });
  },
  activate(userId) {
    return request<AdminUserOut>(`/admin/users/${userId}/activate`, {
      method: "POST",
      body: {},
    });
  },
  changeRole(userId, role) {
    return request<AdminUserOut>(`/admin/users/${userId}/role`, {
      method: "PATCH",
      body: { role },
    });
  },
};

const caseService: ApiCaseService = {
  async list(params: CaseListParams = {}) {
    // Search and status filters are applied server-side (SQL), so `total`
    // always reflects the filtered universe and pagination stays correct.
    return request<CaseList>(
      `/cases${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.search ? { search: params.search } : {}),
        ...(params.status ? { status: params.status } : {}),
      })}`,
    );
  },
  get(id) {
    return request<Case>(`/cases/${id}`);
  },
  create(input) {
    return request<Case>("/cases", { method: "POST", body: input });
  },
  update(id, input) {
    return request<Case>(`/cases/${id}`, { method: "PATCH", body: input });
  },
  archive(id) {
    return request<Case>(`/cases/${id}/archive`, { method: "POST", body: {} });
  },
  listMembers(caseId) {
    return request<CaseMemberListResponse>(`/cases/${caseId}/members`);
  },
  addMember(caseId, input) {
    return request<CaseMemberListResponse>(`/cases/${caseId}/members`, {
      method: "POST",
      body: input,
    });
  },
  removeMember(caseId, userId) {
    return request<CaseMemberListResponse>(`/cases/${caseId}/members/${userId}`, {
      method: "DELETE",
    });
  },
};

const entityService: ApiEntityService = {
  list(caseId, params = {}) {
    return request<EntityList>(`/cases/${caseId}/entities${buildQuery(params)}`);
  },
  get(caseId, entityId) {
    return request<EntityDetail>(`/cases/${caseId}/entities/${entityId}`);
  },
  relationships(caseId, limit = 500) {
    return request<RelationshipList>(
      `/cases/${caseId}/relationships${buildQuery({ limit })}`,
    );
  },
  reviewResolution(caseId) {
    return request<ReviewList>(`/cases/${caseId}/resolution/review`);
  },
  acceptMatch(caseId, matchId) {
    return request<ReviewDecisionResponse>(
      `/cases/${caseId}/resolution/matches/${matchId}/accept`,
      { method: "POST", body: {} },
    );
  },
  rejectMatch(caseId, matchId) {
    return request<ReviewDecisionResponse>(
      `/cases/${caseId}/resolution/matches/${matchId}/reject`,
      { method: "POST", body: {} },
    );
  },
  mergeEntities(caseId, input: EntityMergeRequest) {
    return request<EntityDetail>(`/cases/${caseId}/entities/merge`, {
      method: "POST",
      body: input,
    });
  },
};

const evidenceService: ApiEvidenceService = {
  list(caseId, params = {}) {
    return request<EvidenceList>(
      `/cases/${caseId}/evidence${buildQuery({ limit: params.limit ?? 50, offset: params.offset ?? 0 })}`,
    );
  },
  get(caseId, evidenceId) {
    return request<EvidenceDetail>(`/cases/${caseId}/evidence/${evidenceId}`);
  },
  async upload(caseId, file, dataSource = "csv", options) {
    const formData = new FormData();
    formData.append("file", new File([file.contents], file.name, { type: file.type }));
    formData.append("data_source", dataSource);
    if (options?.collectionId) {
      formData.append("collection_id", options.collectionId);
    }
    return request<EvidenceCreateResponse>(`/cases/${caseId}/evidence`, {
      method: "POST",
      formData,
    });
  },
  provenance(caseId, evidenceId) {
    return request<EvidenceProvenanceResponse>(
      `/cases/${caseId}/evidence/${evidenceId}/provenance`,
    );
  },
  ingest(caseId, evidenceFileId) {
    return request<IngestAccepted>(`/cases/${caseId}/ingest`, {
      method: "POST",
      body: { evidence_file_id: evidenceFileId },
    });
  },
  jobs(caseId, params = {}) {
    return request<IngestJobList>(
      `/cases/${caseId}/ingest-jobs${buildQuery({ limit: params.limit ?? 50, offset: params.offset ?? 0 })}`,
    );
  },
  delete(caseId, evidenceId) {
    return request<void>(`/cases/${caseId}/evidence/${evidenceId}`, {
      method: "DELETE",
    });
  },
  restore(caseId, evidenceId) {
    return request<EvidenceRestoreResponse>(
      `/cases/${caseId}/evidence/${evidenceId}/restore`,
      { method: "POST", body: {} },
    );
  },
  retryGraphSync(caseId, jobId) {
    return request<GraphSyncResult>(`/cases/${caseId}/ingest/${jobId}/retry-graph-sync`, {
      method: "POST",
      body: {},
    });
  },
};

const graphService: ApiGraphService = {
  get(caseId) {
    return request<GraphResponse>(`/cases/${caseId}/graph`);
  },
  stats(caseId) {
    return request<GraphStats>(`/cases/${caseId}/graph/stats`);
  },
  ego(caseId, entityId) {
    return request<EntityEgoGraph>(`/cases/${caseId}/graph/entity/${entityId}`);
  },
};

const analyticsService: ApiAnalyticsService = {
  summary(caseId) {
    return request<AnalyticsSummary>(`/cases/${caseId}/analytics/summary`);
  },
  centrality(caseId, metric = "degree", limit = 50) {
    return request<CentralityEntry[]>(
      `/cases/${caseId}/analytics/centrality${buildQuery({ metric, limit })}`,
    );
  },
  communities(caseId) {
    return request<Community[]>(`/cases/${caseId}/analytics/communities`);
  },
  networkDna(caseId, limit = 50) {
    return request<NetworkProfile[]>(
      `/cases/${caseId}/analytics/network-dna${buildQuery({ limit })}`,
    );
  },
  priorities(caseId, limit = 50) {
    return request<Priority[]>(
      `/cases/${caseId}/analytics/priorities${buildQuery({ limit })}`,
    );
  },
  strength(caseId, limit = 100) {
    return request<RelationshipStrength[]>(
      `/cases/${caseId}/analytics/strength${buildQuery({ limit })}`,
    );
  },
  patterns(caseId, limit = 50) {
    return request<Pattern[]>(
      `/cases/${caseId}/analytics/patterns${buildQuery({ limit })}`,
    );
  },
  hypotheses(caseId, limit = 25) {
    return request<Hypothesis[]>(
      `/cases/${caseId}/analytics/hypotheses${buildQuery({ limit })}`,
    );
  },
  run(caseId) {
    return request<AnalyticsRun>(`/cases/${caseId}/analytics/run`, {
      method: "POST",
      body: {},
    });
  },
  runs(caseId, params = {}) {
    return request<AnalyticsRunList>(
      `/cases/${caseId}/analytics/runs${buildQuery({ limit: params.limit ?? 20, offset: params.offset ?? 0 })}`,
    );
  },
};

const findingService: ApiFindingService = {
  list(caseId, params = {}) {
    return request<FindingList>(
      `/cases/${caseId}/findings${buildQuery({ ...params, limit: params.limit ?? 50, offset: params.offset ?? 0 })}`,
    );
  },
  get(caseId, findingId) {
    return request<Finding>(`/cases/${caseId}/findings/${findingId}`);
  },
  stats(caseId, runId) {
    return request<FindingStats>(
      `/cases/${caseId}/findings/stats${buildQuery({ run_id: runId })}`,
    );
  },
  updateStatus(caseId, findingId, input) {
    return request<FindingStatusOut>(
      `/cases/${caseId}/findings/${findingId}/status`,
      { method: "PATCH", body: input },
    );
  },
};

const auditService: ApiAuditService = {
  list(params = {}) {
    return request<AuditList>(
      `/audit-logs${buildQuery({ ...params, limit: params.limit ?? 50, offset: params.offset ?? 0 })}`,
    );
  },
};

const timelineService: ApiTimelineService = {
  /**
   * Case timeline is the first-class TimelineEvent feed (one row per recorded
   * transition: evidence uploaded, collections sealed, devices approved,
   * hypotheses upset, reports generated). Every reader of the case can list it
   * (PERM_CASE_READ), so unlike the old audit-derived feed there is no role
   * fallback to an empty list.
   */
  events(caseId, params = {}) {
    return request<TimelineEventList>(
      `/cases/${caseId}/timeline${buildQuery({
        limit: params.limit ?? 200,
        ...(params.kind ? { kind: params.kind } : {}),
      })}`,
    );
  },
  create(caseId, input) {
    return request<TimelineEvent>(`/cases/${caseId}/timeline`, {
      method: "POST",
      body: input,
    });
  },
};

const collectionService: ApiCollectionService = {
  list(caseId, params: CollectionListParams = {}) {
    return request<CollectionList>(
      `/cases/${caseId}/collections${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.status ? { status: params.status } : {}),
      })}`,
    );
  },
  get(caseId, collectionId) {
    return request<Collection>(`/cases/${caseId}/collections/${collectionId}`);
  },
  create(caseId, input) {
    return request<Collection>(`/cases/${caseId}/collections`, {
      method: "POST",
      body: input,
    });
  },
  update(caseId, collectionId, input) {
    return request<Collection>(`/cases/${caseId}/collections/${collectionId}`, {
      method: "PATCH",
      body: input,
    });
  },
  seal(caseId, collectionId) {
    return request<Collection>(`/cases/${caseId}/collections/${collectionId}/seal`, {
      method: "POST",
      body: {},
    });
  },
  delete(caseId, collectionId) {
    return request<void>(`/cases/${caseId}/collections/${collectionId}`, {
      method: "DELETE",
    });
  },
};

const fieldDeviceService: ApiFieldDeviceService = {
  list(caseId, params: DeviceListParams = {}) {
    return request<DeviceList>(
      `/cases/${caseId}/devices${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.status ? { status: params.status } : {}),
      })}`,
    );
  },
  register(caseId, input) {
    return request<FieldDevice>(`/cases/${caseId}/devices`, {
      method: "POST",
      body: input,
    });
  },
  approve(caseId, deviceId) {
    return request<FieldDevice>(`/cases/${caseId}/devices/${deviceId}/approve`, {
      method: "POST",
      body: {},
    });
  },
  revoke(caseId, deviceId) {
    return request<FieldDevice>(`/cases/${caseId}/devices/${deviceId}/revoke`, {
      method: "POST",
      body: {},
    });
  },
  verifyKey(caseId, deviceId, input) {
    return request<DeviceVerifyResponse>(`/cases/${caseId}/devices/${deviceId}/verify-key`, {
      method: "POST",
      body: input,
    });
  },
};

const reportService: ApiReportService = {
  list(caseId, params: ReportListParams = {}) {
    return request<ReportList>(
      `/cases/${caseId}/reports${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.report_type ? { report_type: params.report_type } : {}),
      })}`,
    );
  },
  get(caseId, reportId) {
    return request<Report>(`/cases/${caseId}/reports/${reportId}`);
  },
  generate(caseId, input) {
    return request<Report>(`/cases/${caseId}/reports`, {
      method: "POST",
      body: input,
    });
  },
  async download(caseId, reportId) {
    const token = authSession.getToken();
    const url = `/cases/${caseId}/reports/${reportId}/download`;
    const response = await fetch(`${apiConfig.apiUrl}/api/v1${url}`, {
      headers: { Authorization: token ? `Bearer ${token}` : "" },
    });
    if (!response.ok) {
      throw new Error(`Download failed (HTTP ${response.status}).`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") ?? "";
    const match = /filename="?([^";]+)"?/.exec(disposition);
    const fallback = match?.[1] ?? `report-${reportId}.json`;
    return { blob, filename: fallback };
  },
};

const hypothesisService: ApiHypothesisService = {
  list(caseId, params: InvestigationHypothesisListParams = {}) {
    return request<InvestigationHypothesisList>(
      `/cases/${caseId}/hypotheses${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.kind ? { kind: params.kind } : {}),
        ...(params.status ? { status: params.status } : {}),
      })}`,
    );
  },
  get(caseId, hypothesisId) {
    return request<InvestigationHypothesis>(`/cases/${caseId}/hypotheses/${hypothesisId}`);
  },
  create(caseId, input) {
    return request<InvestigationHypothesis>(`/cases/${caseId}/hypotheses`, {
      method: "POST",
      body: input,
    });
  },
  updateStatus(caseId, hypothesisId, status) {
    return request<InvestigationHypothesis>(
      `/cases/${caseId}/hypotheses/${hypothesisId}/status`,
      { method: "PATCH", body: { status } },
    );
  },
  linkEvidence(caseId, hypothesisId, input) {
    return request<InvestigationHypothesis>(
      `/cases/${caseId}/hypotheses/${hypothesisId}/evidence`,
      { method: "POST", body: input },
    );
  },
  delete(caseId, hypothesisId) {
    return request<void>(`/cases/${caseId}/hypotheses/${hypothesisId}`, {
      method: "DELETE",
    });
  },
};

const searchService: ApiSearchService = {
  search(caseId, params: SearchParams) {
    return request<SearchResponse>(
      `/cases/${caseId}/search${buildQuery({
        q: params.q,
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      })}`,
    );
  },
};

const importService: ApiImportService = {
  submitPackage(caseId, payload) {
    const formData = new FormData();
    formData.append("manifest", new File([payload.manifest], payload.manifest.name, { type: payload.manifest.type }));
    formData.append("manifest_signature", new File([payload.signature], payload.signature.name, { type: payload.signature.type }));
    for (const file of payload.files) {
      formData.append("files", new File([file], file.name, { type: file.type }));
    }
    return request<ImportAccepted>(`/cases/${caseId}/import/packages`, {
      method: "POST",
      formData,
    });
  },
};

const victimService: ApiVictimService = {
  list(caseId, params = {}) {
    return request<VictimList>(
      `/cases/${caseId}/victims${buildQuery({
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
        ...(params.status ? { status: params.status } : {}),
        ...(params.search ? { search: params.search } : {}),
      })}`,
    );
  },
  get(caseId, victimId) {
    return request<Victim>(`/cases/${caseId}/victims/${victimId}`);
  },
  create(caseId, input) {
    return request<Victim>(`/cases/${caseId}/victims`, {
      method: "POST",
      body: input,
    });
  },
  update(caseId, victimId, input) {
    return request<Victim>(`/cases/${caseId}/victims/${victimId}`, {
      method: "PATCH",
      body: input,
    });
  },
  delete(caseId, victimId) {
    return request<void>(`/cases/${caseId}/victims/${victimId}`, {
      method: "DELETE",
    });
  },
};

const iotService: ApiIoTService = {
  devices(caseId, params = {}) {
    return request<IoTDeviceList>(
      `/cases/${caseId}/iot/devices${buildQuery({
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
        ...(params.status ? { status: params.status } : {}),
        ...(params.device_type ? { device_type: params.device_type } : {}),
        ...(params.search ? { search: params.search } : {}),
      })}`,
    );
  },
  device(caseId, deviceId) {
    return request<IoTDevice>(`/cases/${caseId}/iot/devices/${deviceId}`);
  },
  register(caseId, input) {
    return request<IoTDevice>(`/cases/${caseId}/iot/devices`, {
      method: "POST",
      body: input,
    });
  },
  updateDevice(caseId, deviceId, input) {
    return request<IoTDevice>(`/cases/${caseId}/iot/devices/${deviceId}`, {
      method: "PATCH",
      body: input,
    });
  },
  deleteDevice(caseId, deviceId) {
    return request<void>(`/cases/${caseId}/iot/devices/${deviceId}`, {
      method: "DELETE",
    });
  },
  deviceStats(caseId, deviceId) {
    return request<IoTDeviceStats>(`/cases/${caseId}/iot/devices/${deviceId}/stats`);
  },
  events(caseId, params = {}) {
    return request<IoTEventList>(
      `/cases/${caseId}/iot/events${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.device_id ? { device_id: params.device_id } : {}),
        ...(params.event_type ? { event_type: params.event_type } : {}),
      })}`,
    );
  },
  recordEvent(caseId, input) {
    return request<IoTEvent>(`/cases/${caseId}/iot/events`, {
      method: "POST",
      body: input,
    });
  },
};

export const realApi: Api = {
  src: "real",
  auth: authService,
  users: userService,
  cases: caseService,
  entities: entityService,
  evidence: evidenceService,
  graph: graphService,
  analytics: analyticsService,
  findings: findingService,
  audit: auditService,
  victims: victimService,
  iot: iotService,
  timeline: timelineService,
  collections: collectionService,
  fieldDevices: fieldDeviceService,
  reports: reportService,
  hypotheses: hypothesisService,
  search: searchService,
  importPackages: importService,
};