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

/* --------------------------- Local AI assistant --------------------------- */

export interface AiStatus {
  enabled: boolean;
  ready: boolean;
  managed: boolean;
  model_configured: string;
  model_valid: boolean;
  context_length: number;
  max_output_tokens: number;
  gpu_layers: number;
  started: boolean;
  load_seconds: number | null;
  restarts: number;
  requests_total: number;
  errors_total: number;
  generations_active: number;
  last_error: string | null;
  prompt_version: string | null;
  tools: string[];
  feature_flags: Record<string, boolean>;
}

export interface AiSource {
  type: string;
  id: string;
  label?: string;
  url?: string | null;
}

export interface AiToolEvent {
  tool: string;
  ok: boolean;
  arguments?: Record<string, unknown>;
  error?: string | null;
  /**
   * Structured outcome (case_not_found_or_not_accessible / case_found_but_empty
   * / case_found_with_data / case_ambiguous / lookup_error) so clients can tell
   * an authorized miss from an empty case from a hard lookup failure.
   */
  status?: string | null;
  duration_ms?: number | null;
}

export interface AiChatInput {
  question: string;
  mode?:
    | "general"
    | "case"
    | "evidence"
    | "graph"
    | "copilot"
    | "report"
    | "knowledge"
    | "analysis";
  case_id?: string | null;
  conversation_id?: string | null;
  /**
   * Latency/quality trade-off. `think` spends the larger budget and asks for a
   * structured rationale/uncertainty/citations answer. Omitted = server default.
   */
  profile?: "quick" | "standard" | "deep" | "think";
}

/**
 * Server-side machine check of the ids and metric numbers an analysis answer
 * cited, compared against what was actually retrieved for the case. Null when
 * the mode does not run a claim check — a missing check is not a pass.
 */
export interface AiCitationCheck {
  cited_ids: number;
  verified_ids: number;
  unverified_ids: string[];
  metric_claims_checked: number;
  metric_claims_mismatched: string[];
}

export interface AiChatResult {
  answer: string;
  conversation_id: string;
  message_id?: string | null;
  sources: AiSource[];
  tool_events: AiToolEvent[];
  grounded: boolean;
  prompt_version: string;
  duration_ms: number;
  first_token_ms?: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  citation_check?: AiCitationCheck | null;
}

export interface AiStreamCallbacks {
  onToken?: (text: string) => void;
  onSources?: (sources: AiSource[]) => void;
  onTool?: (event: AiToolEvent) => void;
  /**
   * Live status while generation runs (`progress` SSE event). Lets the UI show
   * "retrieving…" / "synthesizing…" instead of a bare spinner. Optional so
   * existing consumers are unaffected.
   */
  onProgress?: (info: {
    phase: "retrieving" | "synthesizing" | string;
    profile?: string;
    iteration?: number;
    of?: number;
  }) => void;
  onDone?: (info: {
    answer?: string;
    /**
     * Thread id for follow-ups. The real backend's SSE `done` event does not send
     * this yet, so consumers must treat it as optional and fall back to the newest
     * conversation (see the assistant widget) when it is missing.
     */
    conversation_id?: string;
    grounded: boolean;
    sources: AiSource[];
    tool_events: AiToolEvent[];
    duration_ms: number;
    first_token_ms?: number | null;
    completion_tokens?: number | null;
    /** Analysis mode only: server-side id/number claim validation. */
    citation_check?: AiCitationCheck | null;
  }) => void;
  onError?: (message: string, code?: string) => void;
}

export interface AiConversation {
  id: string;
  case_id: string | null;
  title: string;
  mode: string;
  status: string;
  prompt_version: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface AiMessage {
  id: string;
  role: string;
  content: string;
  sources?: AiSource[] | null;
  tool_events?: AiToolEvent[] | null;
  grounded: boolean;
  prompt_version: string | null;
  created_at: string;
}

export interface AiReportDraft {
  draft: string;
  sources: AiSource[];
  grounded: boolean;
  prompt_version: string;
  duration_ms: number;
}

export interface ApiAiService {
  status(signal?: AbortSignal): Promise<AiStatus>;
  chat(input: AiChatInput, signal?: AbortSignal): Promise<AiChatResult>;
  /** POST /ai/chat/stream over SSE; resolves when the stream completes. */
  chatStream(input: AiChatInput, callbacks: AiStreamCallbacks, signal?: AbortSignal): Promise<void>;
  reportDraft(caseId: string, signal?: AbortSignal): Promise<AiReportDraft>;
  listConversations(params?: { case_id?: string; limit?: number }): Promise<{ items: AiConversation[]; total: number }>;
  listMessages(conversationId: string): Promise<{ items: AiMessage[] }>;
  /** PATCH /ai/conversations/{id} with `{ title }` — renames a stored thread. */
  renameConversation(conversationId: string, title: string): Promise<AiConversation>;
  deleteConversation(conversationId: string): Promise<void>;
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
  ai: ApiAiService;
}