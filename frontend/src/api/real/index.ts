import { request } from "@/api/client/http";
import { authSession } from "@/api/client/session";
import type {
  ApiAnalyticsService,
  ApiAuditService,
  ApiAuthService,
  ApiCaseService,
  ApiEntityService,
  ApiEvidenceService,
  ApiFindingService,
  ApiGraphService,
  Api,
  ApiTimelineService,
  CaseListParams,
  RegisterInput,
  RegisteredUserOut,
} from "@/api/contract";
import type {
  AnalyticsRun,
  AnalyticsRunList,
  AnalyticsSummary,
  AuditList,
  Case,
  CentralityEntry,
  Community,
  EntityDetail,
  EntityEgoGraph,
  EntityList,
  EvidenceCreateResponse,
  EvidenceDetail,
  EvidenceList,
  EvidenceProvenanceResponse,
  Finding,
  FindingList,
  FindingStats,
  FindingStatusOut,
  GraphResponse,
  GraphStats,
  Hypothesis,
  IngestAccepted,
  IngestJobList,
  MeResponse,
  NetworkProfile,
  Pattern,
  Priority,
  RelationshipList,
  RelationshipStrength,
  TokenResponse,
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
    return request<RegisteredUserOut>("/auth/register", { method: "POST", body: input });
  },
};

const caseService: ApiCaseService = {
  async list(params: CaseListParams = {}) {
    const response = await request<{ items: Case[]; total: number }>(
      `/cases${buildQuery({ limit: params.limit ?? 100, offset: params.offset ?? 0 })}`,
    );
    let items = response.items;
    if (params.search) {
      const q = params.search.toLowerCase();
      items = items.filter(
        (c) =>
          c.title.toLowerCase().includes(q) || c.case_number.toLowerCase().includes(q),
      );
    }
    if (params.status) {
      items = items.filter((c) => c.status === params.status);
    }
    return { items, total: items.length };
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
  async upload(caseId, file, dataSource = "csv") {
    const formData = new FormData();
    formData.append("file", new File([file.contents], file.name, { type: file.type }));
    formData.append("data_source", dataSource);
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
   * Case timeline is derived from the append-only audit log. VIEWER/ANALYST
   * cannot read audit (the API 403s), so for those roles we surface an empty
   * timeline rather than failing the whole case view.
   */
  async events(caseId, limit = 100) {
    const permissions = authSession.permissions ?? [];
    if (!permissions.includes("audit.read")) {
      return [];
    }
    const audit = await auditService.list({ case_id: caseId, limit });
    return audit.items.map((event) => ({
      id: event.id,
      action: event.action,
      case_id: event.case_id,
      actor_id: event.actor_id,
      metadata_: event.metadata_,
      created_at: event.created_at,
    }));
  },
};

export const realApi: Api = {
  src: "real",
  auth: authService,
  cases: caseService,
  entities: entityService,
  evidence: evidenceService,
  graph: graphService,
  analytics: analyticsService,
  findings: findingService,
  audit: auditService,
  timeline: timelineService,
};