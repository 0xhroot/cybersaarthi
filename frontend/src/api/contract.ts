/**
 * The service contract every adapter (mock | real) must satisfy.
 *
 * The UI never imports mock or real modules directly — it uses the facade in
 * `src/api/index.ts`, which picks an implementation for `VITE_USE_MOCK_API`.
 *
 * Shapes match backend/app/schemas; see backend/docs/frontend-contract.md.
 */

import type {
  AdminUserList,
  AdminUserOut,
  AnalyticsRun,
  AnalyticsRunList,
  AnalyticsSummary,
  AuditList,
  Case,
  CaseCreateRequest,
  CaseList,
  CaseMemberAddRequest,
  CaseMemberListResponse,
  CaseUpdateRequest,
  CentralityEntry,
  Collection,
  CollectionCreateRequest,
  CollectionList,
  CollectionUpdateRequest,
  Community,
  DeviceList,
  DeviceRegisterRequest,
  DeviceVerifyRequest,
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
  HealthResponse,
  Hypothesis,
  HypothesisLinkEvidenceRequest,
  ImportAccepted,
  IngestAccepted,
  IngestJobList,
  InvestigationHypothesis,
  InvestigationHypothesisCreateRequest,
  InvestigationHypothesisList,
  IoTDevice,
  IoTDeviceCreateRequest,
  IoTDeviceList,
  IoTDeviceStats,
  IoTDeviceUpdateRequest,
  IoTEvent,
  IoTEventCreateRequest,
  IoTEventList,
  MeResponse,
  NetworkProfile,
  Pattern,
  Priority,
  RelationshipList,
  RelationshipStrength,
  Report,
  ReportGenerateRequest,
  ReportList,
  ReviewDecisionResponse,
  ReviewList,
  SearchResponse,
  TimelineEvent,
  TimelineEventCreateRequest,
  TimelineEventList,
  TokenResponse,
  UserOut,
  Victim,
  VictimCreateRequest,
  VictimList,
  VictimUpdateRequest,
} from "@/types/domain";
import type { PageParams } from "@/types/domain";
export type { PageParams, CaseMemberAddRequest };

export interface LoginInput {
  username: string;
  password: string;
}

export interface RegisterInput {
  username: string;
  email: string;
  password: string;
}

export interface RegisteredUserOut {
  user: UserOut;
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
  logout(): Promise<void>;
}

export interface AdminUserListParams extends PageParams {
  status?: string;
  search?: string;
}

export interface ApiAdminUserService {
  list(params?: AdminUserListParams): Promise<AdminUserList>;
  listPending(params?: PageParams): Promise<AdminUserList>;
  get(userId: string): Promise<AdminUserOut>;
  approve(userId: string, role: string): Promise<AdminUserOut>;
  reject(userId: string): Promise<AdminUserOut>;
  suspend(userId: string): Promise<AdminUserOut>;
  activate(userId: string): Promise<AdminUserOut>;
  changeRole(userId: string, role: string): Promise<AdminUserOut>;
}

export interface ApiCaseService {
  list(params?: CaseListParams): Promise<CaseList>;
  get(id: string): Promise<Case>;
  create(input: CaseCreateRequest): Promise<Case>;
  update(id: string, input: CaseUpdateRequest): Promise<Case>;
  archive(id: string): Promise<Case>;
  listMembers(caseId: string): Promise<CaseMemberListResponse>;
  addMember(caseId: string, input: CaseMemberAddRequest): Promise<CaseMemberListResponse>;
  removeMember(caseId: string, userId: string): Promise<CaseMemberListResponse>;
}

export interface ApiEntityService {
  list(caseId: string, params?: EntityListParams): Promise<EntityList>;
  get(caseId: string, entityId: string): Promise<EntityDetail>;
  relationships(caseId: string, limit?: number): Promise<RelationshipList>;
  reviewResolution(caseId: string): Promise<ReviewList>;
  acceptMatch(caseId: string, matchId: string): Promise<ReviewDecisionResponse>;
  rejectMatch(caseId: string, matchId: string): Promise<ReviewDecisionResponse>;
  mergeEntities(caseId: string, input: EntityMergeRequest): Promise<EntityDetail>;
}

export interface ApiEvidenceService {
  list(caseId: string, params?: PageParams): Promise<EvidenceList>;
  get(caseId: string, evidenceId: string): Promise<EvidenceDetail>;
  upload(
    caseId: string,
    file: UploadFile,
    dataSource?: string,
    options?: { collectionId?: string },
  ): Promise<EvidenceCreateResponse>;
  provenance(caseId: string, evidenceId: string): Promise<EvidenceProvenanceResponse>;
  ingest(caseId: string, evidenceFileId: string): Promise<IngestAccepted>;
  jobs(caseId: string, params?: PageParams): Promise<IngestJobList>;
  delete(caseId: string, evidenceId: string): Promise<void>;
  restore(caseId: string, evidenceId: string): Promise<EvidenceRestoreResponse>;
  retryGraphSync(caseId: string, jobId: string): Promise<GraphSyncResult>;
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

export interface VictimListParams extends PageParams {
  status?: string;
  search?: string;
}

export interface ApiVictimService {
  list(caseId: string, params?: VictimListParams): Promise<VictimList>;
  get(caseId: string, victimId: string): Promise<Victim>;
  create(caseId: string, input: VictimCreateRequest): Promise<Victim>;
  update(caseId: string, victimId: string, input: VictimUpdateRequest): Promise<Victim>;
  delete(caseId: string, victimId: string): Promise<void>;
}

export interface IoTDeviceListParams extends PageParams {
  status?: string;
  device_type?: string;
  search?: string;
}

export interface IoTEventListParams extends PageParams {
  device_id?: string;
  event_type?: string;
}

export interface ApiIoTService {
  devices(caseId: string, params?: IoTDeviceListParams): Promise<IoTDeviceList>;
  device(caseId: string, deviceId: string): Promise<IoTDevice>;
  register(caseId: string, input: IoTDeviceCreateRequest): Promise<IoTDevice>;
  updateDevice(caseId: string, deviceId: string, input: IoTDeviceUpdateRequest): Promise<IoTDevice>;
  deleteDevice(caseId: string, deviceId: string): Promise<void>;
  deviceStats(caseId: string, deviceId: string): Promise<IoTDeviceStats>;
  events(caseId: string, params?: IoTEventListParams): Promise<IoTEventList>;
  recordEvent(caseId: string, input: IoTEventCreateRequest): Promise<IoTEvent>;
}

/* ---------------------------- Collections ---------------------------- */

export interface CollectionListParams extends PageParams {
  status?: string;
}

export interface ApiCollectionService {
  list(caseId: string, params?: CollectionListParams): Promise<CollectionList>;
  get(caseId: string, collectionId: string): Promise<Collection>;
  create(caseId: string, input: CollectionCreateRequest): Promise<Collection>;
  update(caseId: string, collectionId: string, input: CollectionUpdateRequest): Promise<Collection>;
  seal(caseId: string, collectionId: string): Promise<Collection>;
  delete(caseId: string, collectionId: string): Promise<void>;
}

/* ------------------------------ Field devices ------------------------------ */

export interface DeviceListParams extends PageParams {
  status?: string;
}

export interface ApiFieldDeviceService {
  list(caseId: string, params?: DeviceListParams): Promise<DeviceList>;
  register(caseId: string, input: DeviceRegisterRequest): Promise<FieldDevice>;
  approve(caseId: string, deviceId: string): Promise<FieldDevice>;
  revoke(caseId: string, deviceId: string): Promise<FieldDevice>;
  verifyKey(caseId: string, deviceId: string, input: DeviceVerifyRequest): Promise<DeviceVerifyResponse>;
}

/* --------------------------------- Reports -------------------------------- */

export interface ReportListParams extends PageParams {
  report_type?: string;
}

export interface ApiReportService {
  list(caseId: string, params?: ReportListParams): Promise<ReportList>;
  get(caseId: string, reportId: string): Promise<Report>;
  generate(caseId: string, input: ReportGenerateRequest): Promise<Report>;
  download(caseId: string, reportId: string): Promise<{ blob: Blob; filename: string }>;
}

/* ------------------------- Investigation hypotheses ------------------------- */

export interface InvestigationHypothesisListParams extends PageParams {
  kind?: string;
  status?: string;
}

export interface ApiHypothesisService {
  list(caseId: string, params?: InvestigationHypothesisListParams): Promise<InvestigationHypothesisList>;
  get(caseId: string, hypothesisId: string): Promise<InvestigationHypothesis>;
  create(caseId: string, input: InvestigationHypothesisCreateRequest): Promise<InvestigationHypothesis>;
  updateStatus(caseId: string, hypothesisId: string, status: string): Promise<InvestigationHypothesis>;
  linkEvidence(
    caseId: string,
    hypothesisId: string,
    input: HypothesisLinkEvidenceRequest,
  ): Promise<InvestigationHypothesis>;
  delete(caseId: string, hypothesisId: string): Promise<void>;
}

/* ---------------------------------- Search -------------------------------- */

export interface SearchParams extends PageParams {
  q: string;
}

export interface ApiSearchService {
  search(caseId: string, params: SearchParams): Promise<SearchResponse>;
}

/* ------------------------------ Import packages ------------------------------ */

export interface ApiImportService {
  submitPackage(
    caseId: string,
    payload: { manifest: File; signature: File; files: File[] },
  ): Promise<ImportAccepted>;
}

export interface ApiTimelineService {
  events(caseId: string, params?: { limit?: number; kind?: string }): Promise<TimelineEventList>;
  create(caseId: string, input: TimelineEventCreateRequest): Promise<TimelineEvent>;
}

export interface ApiHealthService {
  /** Unauthenticated server health; used to fingerprint the backend during QR pairing. */
  health(): Promise<HealthResponse>;
}

export interface Api {
  readonly src: "mock" | "real";
  auth: ApiAuthService;
  users: ApiAdminUserService;
  cases: ApiCaseService;
  entities: ApiEntityService;
  evidence: ApiEvidenceService;
  graph: ApiGraphService;
  analytics: ApiAnalyticsService;
  findings: ApiFindingService;
  audit: ApiAuditService;
  victims: ApiVictimService;
  iot: ApiIoTService;
  timeline: ApiTimelineService;
  collections: ApiCollectionService;
  fieldDevices: ApiFieldDeviceService;
  reports: ApiReportService;
  hypotheses: ApiHypothesisService;
  search: ApiSearchService;
  importPackages: ApiImportService;
  health: ApiHealthService;
}