/**
 * The service contract every adapter (mock | real) must satisfy.
 *
 * The UI never imports mock or real modules directly — it uses the facade in
 * `src/api/index.ts`, which picks an implementation for `VITE_USE_MOCK_API`.
 *
 * Shapes match backend/app/schemas; see backend/docs/frontend-contract.md.
 */

import type {
  AnalyticsRun,
  AnalyticsRunList,
  AnalyticsSummary,
  AuditEvent,
  AuditList,
  Case,
  CaseCreateRequest,
  CaseUpdateRequest,
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
import type { PageParams } from "@/types/domain";
export type { PageParams };

export interface LoginInput {
  username: string;
  password: string;
}

export interface RegisterInput {
  username: string;
  email: string;
  password: string;
  role: string;
}

export interface RegisteredUserOut {
  user: { id: string; username: string; email: string; is_active: boolean };
  roles: string[];
  created_at: string;
}

export interface CaseListParams extends PageParams {
  search?: string;
  status?: string;
}

export interface FindingListParams extends PageParams {
  finding_type?: string;
  status?: string;
  severity?: string;
  run_id?: string;
}

export interface EntityListParams extends PageParams {
  entity_type?: string;
  status?: string;
  query?: string;
}

export interface AuditParams extends PageParams {
  case_id?: string;
  actor_id?: string;
  action?: string;
  resource_type?: string;
}

export interface UploadFile {
  name: string;
  type: string;
  size: number;
  contents: Blob;
}

export interface ApiAuthService {
  login(input: LoginInput): Promise<TokenResponse>;
  me(): Promise<MeResponse>;
  register(input: RegisterInput): Promise<RegisteredUserOut>;
}

export interface ApiCaseService {
  list(params?: CaseListParams): Promise<{ items: Case[]; total: number }>;
  get(id: string): Promise<Case>;
  create(input: CaseCreateRequest): Promise<Case>;
  update(id: string, input: CaseUpdateRequest): Promise<Case>;
  archive(id: string): Promise<Case>;
}

export interface ApiEntityService {
  list(caseId: string, params?: EntityListParams): Promise<EntityList>;
  get(caseId: string, entityId: string): Promise<EntityDetail>;
  relationships(caseId: string, limit?: number): Promise<RelationshipList>;
}

export interface ApiEvidenceService {
  list(caseId: string, params?: PageParams): Promise<EvidenceList>;
  get(caseId: string, evidenceId: string): Promise<EvidenceDetail>;
  upload(
    caseId: string,
    file: UploadFile,
    dataSource?: string,
  ): Promise<EvidenceCreateResponse>;
  provenance(caseId: string, evidenceId: string): Promise<EvidenceProvenanceResponse>;
  ingest(caseId: string, evidenceFileId: string): Promise<IngestAccepted>;
  jobs(caseId: string, params?: PageParams): Promise<IngestJobList>;
}

export interface ApiGraphService {
  get(caseId: string): Promise<GraphResponse>;
  stats(caseId: string): Promise<GraphStats>;
  ego(caseId: string, entityId: string): Promise<EntityEgoGraph>;
}

export interface ApiAnalyticsService {
  summary(caseId: string): Promise<AnalyticsSummary>;
  centrality(caseId: string, metric?: string, limit?: number): Promise<CentralityEntry[]>;
  communities(caseId: string): Promise<Community[]>;
  networkDna(caseId: string, limit?: number): Promise<NetworkProfile[]>;
  priorities(caseId: string, limit?: number): Promise<Priority[]>;
  strength(caseId: string, limit?: number): Promise<RelationshipStrength[]>;
  patterns(caseId: string, limit?: number): Promise<Pattern[]>;
  hypotheses(caseId: string, limit?: number): Promise<Hypothesis[]>;
  run(caseId: string): Promise<AnalyticsRun>;
  runs(caseId: string, params?: PageParams): Promise<AnalyticsRunList>;
}

export interface ApiFindingService {
  list(caseId: string, params?: FindingListParams): Promise<FindingList>;
  get(caseId: string, findingId: string): Promise<Finding>;
  stats(caseId: string, runId?: string): Promise<FindingStats>;
  updateStatus(
    caseId: string,
    findingId: string,
    input: { status: string; reason?: string | null },
  ): Promise<FindingStatusOut>;
}

export interface ApiAuditService {
  list(params?: AuditParams): Promise<AuditList>;
}

export type ApiTimelineEvent = Pick<AuditEvent, "id" | "action" | "case_id"> & {
  metadata_: Record<string, unknown> | null;
  created_at: string;
  actor_id: string | null;
};

export interface ApiTimelineService {
  events(caseId: string, limit?: number): Promise<ApiTimelineEvent[]>;
}

export interface Api {
  readonly src: "mock" | "real";
  auth: ApiAuthService;
  cases: ApiCaseService;
  entities: ApiEntityService;
  evidence: ApiEvidenceService;
  graph: ApiGraphService;
  analytics: ApiAnalyticsService;
  findings: ApiFindingService;
  audit: ApiAuditService;
  timeline: ApiTimelineService;
}