import { request } from "@/api/client/http";
import { authSession } from "@/api/client/session";
import { apiConfig } from "@/config/env";
import type {
  AdminUserListParams,
  AiCitationCheck,
  AiHypothesisDraft,
  AiChatInput,
  AiChatResult,
  AiConversation,
  AiMessage,
  AiReportDraft,
  AiSource,
  AiStatus,
  AiStreamCallbacks,
  AiToolEvent,
  Api,
  ApiAdminUserService,
  ApiAiService,
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
  ApiHealthService,
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
  AnalysisJobList,
  AnalysisJobOut,
  AnalyticsRun,
  AnalyticsRunList,
  AnalyticsSummary,
  ArtifactList,
  AuditList,
  Case,
  CaseList,
  CaseMemberListResponse,
  CentralityEntry,
  Collection,
  CollectionList,
  Community,
  CrossCaseCandidateListResponse,
  CustodyChronologyResponse,
  CustodyEventOut,
  CustodyExplainResponse,
  DerivedArtifactOut,
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
  FlowTraceResponse,
  GraphResponse,
  GraphStats,
  GraphSyncResult,
  Hypothesis,
  HealthResponse,
  ImportAccepted,
  IngestAccepted,
  IngestJobList,
  IntegrityVerificationResponse,
  InvestigationHypothesis,
  InvestigationHypothesisList,
  IoTDevice,
  IoTDeviceList,
  IoTDeviceStats,
  IoTEvent,
  IoTEventList,
  JobSubmitResponse,
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
  SourceRecordList,
  TimelineCommitResponse,
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

  extract(caseId, evidenceFileId) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-intelligence/extract`,
      { method: "POST", body: { evidence_file_id: evidenceFileId } },
    );
  },
  multilingual(caseId, evidenceFileId, translate = false) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-intelligence/multilingual`,
      { method: "POST", body: { evidence_file_id: evidenceFileId, translate } },
    );
  },
  sourceRecords(caseId, evidenceId, params = {}) {
    return request<SourceRecordList>(
      `/cases/${caseId}/evidence/${evidenceId}/records${buildQuery({
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      })}`,
    );
  },
  evidenceJobs(caseId, params = {}) {
    return request<AnalysisJobList>(
      `/cases/${caseId}/evidence-intelligence/jobs${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.feature ? { feature: params.feature } : {}),
        ...(params.status ? { status: params.status } : {}),
      })}`,
    );
  },
  cancelJob(caseId, jobId) {
    return request<AnalysisJobOut>(
      `/cases/${caseId}/evidence-intelligence/jobs/${jobId}/cancel`,
      { method: "POST", body: {} },
    );
  },
  artifacts(caseId, params = {}) {
    return request<ArtifactList>(
      `/cases/${caseId}/evidence-intelligence/artifacts${buildQuery({
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
        ...(params.kind ? { kind: params.kind } : {}),
      })}`,
    );
  },
  reviewArtifact(caseId, artifactId, input) {
    return request<DerivedArtifactOut>(
      `/cases/${caseId}/evidence-intelligence/artifacts/${artifactId}/review`,
      { method: "POST", body: input },
    );
  },
  verifyIntegrity(caseId, evidenceFileId) {
    return request<IntegrityVerificationResponse>(
      `/cases/${caseId}/evidence-integrity/verify`,
      { method: "POST", body: { evidence_file_id: evidenceFileId } },
    );
  },
  custodyAudit(caseId, evidenceFileId) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-integrity/custody-audit`,
      { method: "POST", body: evidenceFileId ? { evidence_file_id: evidenceFileId } : {} },
    );
  },
  custodyChronology(caseId, evidenceId) {
    return request<CustodyChronologyResponse>(
      `/cases/${caseId}/evidence/${evidenceId}/custody`,
    );
  },
  recordCustodyEvent(caseId, evidenceId, input) {
    return request<CustodyEventOut>(
      `/cases/${caseId}/evidence/${evidenceId}/custody-events`,
      { method: "POST", body: input },
    );
  },
  explainFinding(caseId, artifactId) {
    return request<CustodyExplainResponse>(
      `/cases/${caseId}/evidence-intelligence/artifacts/${artifactId}/explain`,
      { method: "POST", body: {} },
    );
  },

  /* ------------------ Case intelligence (phase 3) ------------------ */

  submitEntityResolution(caseId) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-intelligence/entity-resolution`,
      { method: "POST", body: {} },
    );
  },
  submitTimelineReconstruction(caseId) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-intelligence/timeline-reconstruction`,
      { method: "POST", body: {} },
    );
  },
  submitContradictions(caseId) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-intelligence/contradiction-detection`,
      { method: "POST", body: {} },
    );
  },
  commitTimelineProposal(caseId, artifactId) {
    return request<TimelineCommitResponse>(
      `/cases/${caseId}/evidence-intelligence/timeline-proposals/${artifactId}/commit`,
      { method: "POST", body: {} },
    );
  },
  resolveContradiction(caseId, artifactId, input) {
    return request<DerivedArtifactOut>(
      `/cases/${caseId}/evidence-intelligence/contradictions/${artifactId}/resolve`,
      { method: "POST", body: input },
    );
  },

  /* ------------------ Financial flow (phase 4, feature A) ------------------ */

  submitFinancialFlow(caseId) {
    return request<JobSubmitResponse>(
      `/cases/${caseId}/evidence-intelligence/financial-flow`,
      { method: "POST", body: {} },
    );
  },
  traceFinancialFlow(caseId, input) {
    return request<FlowTraceResponse>(
      `/cases/${caseId}/evidence-intelligence/financial-flow/trace`,
      { method: "POST", body: input },
    );
  },

  /* ------------------ Cross-case discovery (phase 4, feature B) ------------------ */

  submitCrossCaseDiscover(input) {
    return request<JobSubmitResponse>(`/cross-case/discover`, {
      method: "POST",
      body: input,
    });
  },
  crossCaseCandidates(anchorCaseId) {
    return request<CrossCaseCandidateListResponse>(
      `/cross-case/candidates${buildQuery({ anchor_case_id: anchorCaseId })}`,
    );
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
    // Cross-origin responses only expose Content-Disposition when the server
    // opts in (expose_headers). When absent, return an empty filename so the
    // caller falls back to its report-metadata-derived name.
    return { blob, filename: match?.[1] ?? "" };
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

const healthService: ApiHealthService = {
  health() {
    return request<HealthResponse>("/health");
  },
};

interface AiStreamEvent {
  type: "token" | "sources" | "tool" | "progress" | "done" | "error";
  text?: string;
  answer?: string;
  conversation_id?: string;
  sources?: AiSource[];
  tool?: string;
  arguments?: Record<string, unknown>;
  ok?: boolean;
  error?: string;
  status?: string | null;
  grounded?: boolean;
  tool_events?: AiToolEvent[];
  duration_ms?: number;
  first_token_ms?: number | null;
  completion_tokens?: number | null;
  code?: string;
  message?: string;
  // `progress` event only.
  phase?: string;
  profile?: string;
  iteration?: number;
  of?: number;
  // `done` event, analysis mode only.
  citation_check?: AiCitationCheck | null;
  // `done` event, hypothesize mode only.
  hypothesis_drafts?: AiHypothesisDraft[];
  hypothesis_draft_errors?: number;
}

const aiService: ApiAiService = {
  status(signal) {
    return request<AiStatus>("/ai/status", { signal });
  },
  chat(input, signal) {
    return request<AiChatResult>("/ai/chat", { method: "POST", body: input, signal });
  },
  async chatStream(input: AiChatInput, callbacks: AiStreamCallbacks, signal?: AbortSignal) {
    const token = authSession.getToken();
    const url = `${apiConfig.apiUrl}/api/v1/ai/chat/stream`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(input),
      signal,
    });
    if (!response.ok || !response.body) {
      let message = `Assistant stream failed (HTTP ${response.status}).`;
      let code: string | undefined;
      try {
        const body = (await response.json()) as { error?: { message?: string; code?: string } };
        if (body.error?.message) message = body.error.message;
        if (body.error?.code) code = body.error.code;
      } catch {
        /* keep default message */
      }
      callbacks.onError?.(message, code);
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data:")) continue;
          let event: AiStreamEvent;
          try {
            event = JSON.parse(line.slice(5).trim()) as AiStreamEvent;
          } catch {
            continue;
          }
          switch (event.type) {
            case "token":
              if (event.text) callbacks.onToken?.(event.text);
              break;
            case "progress":
              callbacks.onProgress?.({
                phase: event.phase ?? "working",
                profile: event.profile,
                iteration: event.iteration,
                of: event.of,
              });
              break;
            case "sources":
              callbacks.onSources?.(event.sources ?? []);
              break;
            case "tool":
              callbacks.onTool?.({
                tool: event.tool ?? "unknown",
                // Pre-execution events for valid tools carry no ok (still
                // running); rejected tools arrive with ok:false + error.
                ok: event.ok ?? true,
                arguments: event.arguments,
                error: event.error,
                status: event.status,
              });
              break;
            case "done":
              callbacks.onDone?.({
                answer: event.answer,
                // Optional today: the backend does not emit it yet, but forward it
                // as soon as the stream starts carrying the thread id.
                conversation_id: event.conversation_id,
                grounded: event.grounded ?? false,
                sources: event.sources ?? [],
                tool_events: event.tool_events ?? [],
                duration_ms: event.duration_ms ?? 0,
                first_token_ms: event.first_token_ms,
                completion_tokens: event.completion_tokens,
                citation_check: event.citation_check,
                hypothesis_drafts: event.hypothesis_drafts,
                hypothesis_draft_errors: event.hypothesis_draft_errors,
              });
              break;
            case "error":
              callbacks.onError?.(event.message ?? "Assistant request failed.", event.code);
              break;
          }
        }
      }
    }
  },
  reportDraft(caseId, signal) {
    return request<AiReportDraft>("/ai/report-draft", {
      method: "POST",
      body: { case_id: caseId },
      signal,
    });
  },
  listConversations(params = {}) {
    return request<{ items: AiConversation[]; total: number }>(
      `/ai/conversations${buildQuery({
        ...(params.case_id ? { case_id: params.case_id } : {}),
        limit: params.limit ?? 50,
      })}`,
    );
  },
  listMessages(conversationId) {
    return request<{ items: AiMessage[] }>(`/ai/conversations/${conversationId}`);
  },
  renameConversation(conversationId, title) {
    // `request` serializes the body to JSON itself, so pass the plain object.
    return request<AiConversation>(`/ai/conversations/${conversationId}`, {
      method: "PATCH",
      body: { title },
    });
  },
  deleteConversation(conversationId) {
    return request<void>(`/ai/conversations/${conversationId}`, { method: "DELETE" });
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
  health: healthService,
  ai: aiService,
};