/**
 * Frontend domain types.
 *
 * These mirror the backend contract in backend/docs/frontend-contract.md and
 * backend/app/schemas. Do not invent fields that the backend does not produce;
 * the mock adapter returns the same shapes so the UI is source-agnostic.
 */

export type Role = "ADMIN" | "INVESTIGATOR" | "ANALYST" | "VIEWER";

/** Account lifecycle stage (mirrors backend AccountStatus). */
export type AccountStatus = "PENDING" | "ACTIVE" | "SUSPENDED" | "REJECTED";

export type EntityType =
  | "person"
  | "phone"
  | "vehicle"
  | "organization"
  | "account"
  | "location"
  | "document"
  | "event";

export type EntityStatus = "active" | "merged" | "review" | "rejected";

export type RelationshipType =
  | "called"
  | "owns"
  | "works_for"
  | "associated_with"
  | "located_at"
  | "visited"
  | "transferred_to";

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type FindingType =
  | "pattern"
  | "anomaly"
  | "hypothesis"
  | "network_insight"
  | "relationship_insight";

export type FindingStatus = "NEW" | "REVIEWED" | "DISMISSED" | "CONFIRMED";

export type PriorityTier = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type ProfileTier = "FOCAL" | "SIGNIFICANT" | "MONITORED" | "PERIPHERAL";

export type CaseStatus = "open" | "in_progress" | "closed" | "archived";

/** Statuses callers may submit when creating/updating a case (F07).
 *
 * ``archived`` is a read-only terminal state: the backend Pydantic schema
 * rejects it on create/update with 422, so the request types must never allow
 * sending it even though reads must tolerate it.
 */
export type WritableCaseStatus = Exclude<CaseStatus, "archived">;

export type JobStatus = "pending" | "running" | "completed" | "failed" | "partial";

export type GraphSyncStatus = "pending" | "synced" | "failed";

/* ------------------------------- Auth ------------------------------- */

export interface UserOut {
  id: string;
  username: string;
  email: string;
  status: AccountStatus;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserOut;
}

export interface MeResponse {
  user: UserOut;
  roles: Role[];
  permissions: string[];
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

/* --------------------------- Admin: users --------------------------- */

export interface RegisteredUserOut {
  user: UserOut;
  roles: Role[];
  created_at: string;
}

export interface AdminUserOut {
  id: string;
  username: string;
  email: string;
  status: AccountStatus;
  is_active: boolean;
  roles: Role[];
  created_at: string;
  updated_at: string;
}

export interface AdminUserList {
  items: AdminUserOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApproveRequest {
  role: Role;
}

export interface RoleChangeRequest {
  role: Role;
}

/* ------------------------------- Cases ------------------------------ */

export interface Case {
  id: string;
  case_number: string;
  title: string;
  description: string | null;
  status: CaseStatus;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CaseCreateRequest {
  title: string;
  description?: string | null;
  case_number?: string | null;
  status?: WritableCaseStatus;
}

export interface CaseUpdateRequest {
  title?: string | null;
  description?: string | null;
  status?: WritableCaseStatus;
}

export interface CaseList {
  items: Case[];
  total: number;
  limit: number;
  offset: number;
}

/* ----------------------------- Case members ------------------------- */

export type CaseMemberRole = "collaborator" | "viewer";

export interface CaseMember {
  user_id: string;
  role: CaseMemberRole;
  created_at: string;
}

export interface CaseMemberListResponse {
  items: CaseMember[];
  case_id: string;
}

export interface CaseMemberAddRequest {
  user_id: string;
  role: CaseMemberRole;
}

/* ----------------------------- Entities ---------------------------- */

export type VictimStatus =
  | "reported"
  | "under_investigation"
  | "evidence_collected"
  | "recovery_initiated"
  | "recovered"
  | "closed";

export type VictimClassification =
  | "individual"
  | "organization"
  | "government"
  | "financial_institution"
  | "unknown";

export interface Victim {
  id: string;
  case_id: string;
  name: string;
  age: number | null;
  date_of_birth: string | null;
  gender: string | null;
  classification: VictimClassification;
  phone: string | null;
  email: string | null;
  address: string | null;
  incident_date: string | null;
  incident_type: string | null;
  fraud_category: string | null;
  description: string | null;
  reported_amount: number | null;
  currency: string | null;
  amount_lost: number | null;
  recovery_amount: number | null;
  digital_accounts: Record<string, unknown>[] | null;
  devices: Record<string, unknown>[] | null;
  wallet_addresses: string[] | null;
  status: VictimStatus;
  statement: string | null;
  investigator_notes: string | null;
  recovery_status: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface VictimCreateRequest {
  name: string;
  age?: number | null;
  date_of_birth?: string | null;
  gender?: string | null;
  classification?: VictimClassification;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  incident_date?: string | null;
  incident_type?: string | null;
  fraud_category?: string | null;
  description?: string | null;
  reported_amount?: number | null;
  currency?: string | null;
  amount_lost?: number | null;
  recovery_amount?: number | null;
  digital_accounts?: Record<string, unknown>[] | null;
  devices?: Record<string, unknown>[] | null;
  wallet_addresses?: string[] | null;
  status?: VictimStatus;
  statement?: string | null;
  investigator_notes?: string | null;
  recovery_status?: string | null;
}

export interface VictimUpdateRequest {
  name?: string | null;
  age?: number | null;
  date_of_birth?: string | null;
  gender?: string | null;
  classification?: VictimClassification | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  incident_date?: string | null;
  incident_type?: string | null;
  fraud_category?: string | null;
  description?: string | null;
  reported_amount?: number | null;
  currency?: string | null;
  amount_lost?: number | null;
  recovery_amount?: number | null;
  digital_accounts?: Record<string, unknown>[] | null;
  devices?: Record<string, unknown>[] | null;
  wallet_addresses?: string[] | null;
  status?: VictimStatus | null;
  statement?: string | null;
  investigator_notes?: string | null;
  recovery_status?: string | null;
}

export interface VictimList {
  items: Victim[];
  total: number;
  limit: number;
  offset: number;
}

/* -------------------------------- IoT -------------------------------- */

export type IoTDeviceType =
  | "mobile"
  | "router"
  | "gps_tracker"
  | "smart_device"
  | "vehicle"
  | "cctv"
  | "computer"
  | "other";

export type IoTDeviceStatus = "registered" | "active" | "inactive" | "seized" | "removed";

export type IoTEventType =
  | "location"
  | "connectivity"
  | "message"
  | "call"
  | "app_use"
  | "tamper"
  | "power"
  | "network"
  | "custom";

export interface IoTDevice {
  id: string;
  case_id: string;
  name: string;
  device_type: IoTDeviceType;
  make: string | null;
  model: string | null;
  serial_number: string;
  imei: string | null;
  ip_address: string | null;
  mac_address: string | null;
  os: string | null;
  os_version: string | null;
  owner_name: string | null;
  owner_phone: string | null;
  status: IoTDeviceStatus;
  description: string | null;
  firmware_version: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  metadata_json: Record<string, unknown> | null;
  event_count: number;
  created_at: string;
  updated_at: string;
}

export interface IoTDeviceCreateRequest {
  name: string;
  device_type?: IoTDeviceType;
  make?: string | null;
  model?: string | null;
  serial_number: string;
  imei?: string | null;
  ip_address?: string | null;
  mac_address?: string | null;
  os?: string | null;
  os_version?: string | null;
  owner_name?: string | null;
  owner_phone?: string | null;
  description?: string | null;
  firmware_version?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface IoTDeviceUpdateRequest {
  name?: string | null;
  device_type?: IoTDeviceType | null;
  make?: string | null;
  model?: string | null;
  serial_number?: string | null;
  imei?: string | null;
  ip_address?: string | null;
  mac_address?: string | null;
  os?: string | null;
  os_version?: string | null;
  owner_name?: string | null;
  owner_phone?: string | null;
  status?: IoTDeviceStatus | null;
  description?: string | null;
  firmware_version?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface IoTDeviceList {
  items: IoTDevice[];
  total: number;
  limit: number;
  offset: number;
}

export interface IoTEvent {
  id: string;
  case_id: string;
  device_id: string;
  event_type: IoTEventType;
  event_time: string;
  source: string | null;
  payload: Record<string, unknown> | null;
  latitude: number | null;
  longitude: number | null;
  location_label: string | null;
  confidence: number | null;
  description: string | null;
  created_at: string;
}

export interface IoTEventCreateRequest {
  device_id: string;
  event_type: IoTEventType;
  event_time: string;
  source?: string | null;
  payload?: Record<string, unknown> | null;
  latitude?: number | null;
  longitude?: number | null;
  location_label?: string | null;
  confidence?: number | null;
  description?: string | null;
}

export interface IoTEventList {
  items: IoTEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface IoTDeviceStats {
  device_id: string;
  event_count: number;
  by_type: Record<string, number>;
  first_event_at: string | null;
  last_event_at: string | null;
}

/* ------------------------------ Entities ---------------------------- */

export interface EntityAlias {
  id: string;
  alias_value: string;
  alias_type: string;
}

export interface Entity {
  id: string;
  case_id: string;
  entity_type: EntityType;
  canonical_value: string;
  display_value: string;
  confidence: number | null;
  status: EntityStatus;
  created_at: string;
}

export interface EntityDetail extends Entity {
  aliases: EntityAlias[];
  context: Record<string, unknown> | null;
}

export interface EntityList {
  items: Entity[];
  total: number;
  limit: number;
  offset: number;
}

export interface Relationship {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: RelationshipType;
  confidence: number | null;
  explanation: string | null;
  created_at: string;
}

export interface RelationshipList {
  items: Relationship[];
  total: number;
}

/* ------------------------------ Graph ------------------------------- */

export interface GraphNode {
  id: string;
  entity_type: string;
  canonical_value: string;
  display_value: string;
  status: string;
  confidence: number | null;
  aliases: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  confidence: number | null;
  context: Record<string, unknown> | null;
}

export interface GraphResponse {
  case_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface EntityEgoGraph extends GraphResponse {
  centre: string;
}

export interface GraphStats {
  case_id: string;
  node_count: number;
  edge_count: number;
  entity_type_counts: Record<string, number>;
  relationship_type_counts: Record<string, number>;
  generated_at: string;
  synced: boolean;
}

/* ----------------------------- Evidence ----------------------------- */

export interface EvidenceListItem {
  id: string;
  original_filename: string;
  sha256: string;
  format: string | null;
  file_size: number;
  status: string;
  record_count: number | null;
  source_field_device_id: string | null;
  created_at: string;
}

export interface EvidenceList {
  items: EvidenceListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EvidenceDetail {
  id: string;
  case_id: string;
  data_source: string | null;
  original_filename: string;
  stored_key: string;
  content_type: string;
  file_size: number;
  sha256: string;
  format: string | null;
  encoding: string | null;
  status: string;
  status_detail: string | null;
  record_count: number | null;
  metadata_json: Record<string, unknown> | null;
  source_field_device_id: string | null;
  created_at: string;
}

export interface SourceRecordOut {
  /** One original parsed source record, verbatim (never model output). */
  id: string;
  evidence_file_id: string;
  record_no: number;
  raw_data: Record<string, unknown>;
}

export interface SourceRecordList {
  items: SourceRecordOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface EvidenceCreateResponse {
  id: string;
  case_id: string;
  original_filename: string;
  stored_key: string;
  content_type: string;
  file_size: number;
  sha256: string;
  format: string | null;
  encoding: string | null;
  status: string;
  status_detail: string | null;
  source_field_device_id: string | null;
  created_at: string;
}

export interface EvidenceProvenanceResponse {
  evidence: EvidenceDetail;
  record_count: number;
  records_by_status: Record<string, number>;
  entity_count: number;
  relationship_count: number;
  finding_count: number;
  related_entity_ids: string[];
  related_relationship_ids: string[];
  finding_ids: string[];
}

export interface IngestionJob {
  id: string;
  case_id: string;
  evidence_file_id: string | null;
  stage: string;
  status: JobStatus;
  progress: number;
  total_records: number;
  processed_records: number;
  graph_sync_status: GraphSyncStatus;
  error: string | null;
  graph_error: string | null;
  summary: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface IngestJobList {
  items: IngestionJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface IngestAccepted {
  job: IngestionJob;
  duplicate: boolean;
}

export interface GraphSyncResult {
  job_id: string;
  graph_sync_status: GraphSyncStatus;
  nodes_synced: number;
  edges_synced: number;
  error: string | null;
}

export type ReviewDecision = "auto_match" | "review";

export interface ReviewCandidate {
  match_id: string;
  candidate_id: string;
  candidate_value: string;
  candidate_type: string;
  target_entity_id: string | null;
  target_value: string | null;
  score: number;
  decision: ReviewDecision;
  signals: Record<string, unknown> | null;
  created_at: string;
}

export interface ReviewList {
  items: ReviewCandidate[];
  total: number;
}

/* ----------------------------- Analytics ---------------------------- */

export interface CentralityEntry {
  entity_id: string;
  metric: string;
  metric_title: string;
  raw: number;
  normalized: number;
  rank: number | null;
  exact: boolean;
}

export interface Community {
  community_id: string;
  member_count: number;
  density: number;
  internal_edges: number;
  external_edges: number;
  dominant_entity_types: string[];
  dominant_relationship_types: string[];
  member_entity_ids: string[];
  score: number | null;
  explanation: string | null;
}

export interface StrengthSignal {
  name: string;
  value: number;
  weight: number;
  description: string;
}

export interface RelationshipStrength {
  relationship_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: string;
  strength: number;
  coverage: number;
  type_diversity: number;
  record_coverage: number;
  file_independence: number;
  resolution_confidence: number;
  evidence_count: number;
  distinct_sources: number;
  independent_files: number;
  signals: StrengthSignal[];
}

export interface NetworkProfileFeature {
  name: string;
  raw: number;
  normalized: number;
  weight: number;
  description: string;
}

export interface NetworkProfile {
  entity_id: string;
  entity_type: string;
  display_value: string;
  overall_score: number;
  tier: ProfileTier;
  features: Record<string, NetworkProfileFeature>;
  signals: Array<Record<string, unknown>>;
  explanation: string | null;
}

export interface Priority {
  entity_id: string;
  entity_type: string;
  display_value: string;
  prominence: number;
  influence: number;
  bridging: number;
  reach: number;
  pattern: number;
  hypothesis: number;
  priority_score: number;
  tier: PriorityTier;
}

export interface HypothesisSignal {
  name?: string;
  value?: number;
  description?: string;
  label?: string;
  message?: string;
  [key: string]: unknown;
}

export interface Hypothesis {
  finding_type: typeof HYPOTHESIS_FINDING_TYPE;
  title: string;
  summary: string;
  severity: Severity;
  score: number;
  confidence: number | null;
  affected_entities: string[];
  affected_relationships: string[];
  evidence_ids: string[];
  signals: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  candidate_relation_type: string | null;
}

export const HYPOTHESIS_FINDING_TYPE = "hypothesis" as const;

export interface Pattern {
  finding_type: FindingType;
  title: string;
  summary: string;
  severity: Severity;
  score: number;
  confidence: number | null;
  affected_entities: string[];
  affected_relationships: string[];
  evidence_ids: string[];
  signals: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
}

export interface AnalyticsSummary {
  case_id: string;
  entity_count: number;
  relationship_count: number;
  community_count: number;
  max_evidence_per_relationship: number;
  average_network_score: number;
  profile_tiers: Record<string, number>;
  priority_tiers: Record<string, number>;
  findings_by_severity: Record<string, number>;
  findings_by_type: Record<string, number>;
  finding_count: number;
  exact_graph: boolean;
  approximation_notice: string | null;
  generated_at: string;
}

export interface Finding {
  id: string;
  case_id: string;
  run_id: string | null;
  finding_type: FindingType;
  title: string;
  summary: string;
  severity: Severity;
  score: number;
  confidence: number | null;
  status: FindingStatus;
  affected_entities: string[];
  affected_relationships: string[];
  evidence_ids: string[];
  explanation: {
    approach: string;
    signals: Array<Record<string, unknown>>;
    paths: Array<Record<string, unknown>>;
    evidence: Array<Record<string, unknown>>;
    limitations: string[];
  };
  details: Record<string, unknown> | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  created_at: string;
}

export interface FindingList {
  items: Finding[];
  total: number;
  limit: number;
  offset: number;
}

export interface FindingStatusOut {
  id: string;
  status: FindingStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
}

export interface FindingStats {
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
}

export interface AnalyticsRun {
  id: string;
  case_id: string;
  status: "pending" | "running" | "completed" | "failed";
  stage: string;
  error: string | null;
  actor_id: string | null;
  summary: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AnalyticsRunList {
  items: AnalyticsRun[];
  total: number;
}

/* ------------------------------- Audit ------------------------------ */

export interface AuditEvent {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  case_id: string | null;
  metadata_: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditList {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

/* ----------------------------- Field collections ----------------------------- */

export type CollectionStatus = "open" | "sealed";

export interface Collection {
  id: string;
  case_id: string;
  name: string;
  description: string | null;
  status: CollectionStatus;
  sealed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CollectionCreateRequest {
  name: string;
  description?: string | null;
}

export interface CollectionUpdateRequest {
  name?: string | null;
  description?: string | null;
}

export interface CollectionList {
  items: Collection[];
  total: number;
  limit: number;
  offset: number;
}

/* ------------------------------ Field devices ------------------------------ */

export type FieldDevicePlatform =
  | "android_mobile"
  | "esp32"
  | "raspberry_pi"
  | "tablet"
  | "laptop"
  | "other";

export type FieldDeviceStatus = "pending" | "approved" | "revoked";

export type FieldDeviceSignatureAlgorithm = "RSA-SHA256" | "Ed25519";

export interface FieldDevice {
  id: string;
  case_id: string;
  platform: string;
  serial: string;
  model: string | null;
  firmware_version: string | null;
  signature_algorithm: string;
  status: string;
  approved_by: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface DeviceRegisterRequest {
  platform: string;
  serial: string;
  model?: string | null;
  firmware_version?: string | null;
  public_key: string;
  signature_algorithm?: string;
}

export interface DeviceVerifyRequest {
  data: string;
  signature: string;
}

export interface DeviceVerifyResponse {
  valid: boolean;
}

export interface DeviceList {
  items: FieldDevice[];
  total: number;
  limit: number;
  offset: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/* -------------------------------- Reports -------------------------------- */

export type ReportStatus = "generating" | "ready" | "failed";

export type ReportFormat = "json" | "csv" | "pdf";

export interface Report {
  id: string;
  case_id: string;
  report_type: string;
  format: string;
  title: string;
  status: ReportStatus;
  byte_size: number | null;
  failure_reason: string | null;
  created_at: string;
}

export interface ReportGenerateRequest {
  report_type: string;
  format?: string;
  title?: string | null;
}

export interface ReportList {
  items: Report[];
  total: number;
  limit: number;
  offset: number;
}

/* ------------------------- Investigation hypotheses ------------------------- */

export type InvestigationHypothesisStatus =
  | "proposed"
  | "under_review"
  | "supported"
  | "contradicted"
  | "dismissed"
  | "concluded";

export interface InvestigationHypothesis {
  id: string;
  case_id: string;
  kind: string;
  status: InvestigationHypothesisStatus;
  title: string;
  statement: string;
  confidence: number | null;
  supporting_evidence: string[] | null;
  contradicting_evidence: string[] | null;
  related_entities: string[] | null;
  related_relationships: string[] | null;
  evidence_weight: number;
  notes: string | null;
  submitted_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvestigationHypothesisCreateRequest {
  kind?: string;
  title: string;
  statement: string;
  confidence?: number | null;
  notes?: string | null;
}

export interface InvestigationHypothesisList {
  items: InvestigationHypothesis[];
  total: number;
  limit: number;
  offset: number;
}

export interface HypothesisLinkEvidenceRequest {
  evidence_id: string;
  support?: boolean;
}

/* -------------------------------- Timeline -------------------------------- */

export type TimelineEventKind =
  | "case_created"
  | "case_status_changed"
  | "case_archived"
  | "evidence_uploaded"
  | "evidence_ingested"
  | "evidence_restored"
  | "collection_created"
  | "collection_sealed"
  | "device_registered"
  | "device_approved"
  | "device_revoked"
  | "hypothesis_created"
  | "hypothesis_status_changed"
  | "finding_created"
  | "finding_status_changed"
  | "entity_merged"
  | "match_accepted"
  | "match_rejected"
  | "analytics_run"
  | "report_generated";

export interface TimelineEvent {
  id: string;
  case_id: string;
  occurred_at: string;
  kind: string;
  title: string;
  description: string | null;
  entity_id: string | null;
  evidence_file_id: string | null;
  collection_id: string | null;
  device_id: string | null;
  actor_user_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface TimelineEventList {
  items: TimelineEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface TimelineEventCreateRequest {
  occurred_at: string;
  kind: string;
  title: string;
  description?: string | null;
  entity_id?: string | null;
  evidence_file_id?: string | null;
  collection_id?: string | null;
  device_id?: string | null;
  payload?: Record<string, unknown> | null;
}

/**
 * Commit of one approved reconstruction proposal. `duplicate: true` means the
 * event was already committed earlier — the same event id comes back, never a
 * second row (the commit is idempotent).
 */
export interface TimelineCommitResponse {
  event: TimelineEvent;
  duplicate: boolean;
}

/* -------------------------------- Search -------------------------------- */

export interface SearchResult {
  kind: string;
  id: string;
  title: string;
  subtitle: string | null;
  url: string;
}

export interface SearchResponse {
  items: SearchResult[];
  total: number;
  limit: number;
  offset: number;
}

/* ----------------------------- Import packages ----------------------------- */

export interface ImportAccepted {
  case_id: string;
  device_serial: string;
  imported_evidence_count: number;
  evidence_ids: string[];
  collection_name: string | null;
}

/* ------------------------------ Resolution API ------------------------------ */

export type EntityMergeRequest = {
  primary_entity_id: string;
  merge_entity_id: string;
};

export interface ReviewDecisionResponse {
  match_id: string;
  status: string;
}

export interface EvidenceRestoreResponse {
  id: string;
  case_id: string;
  original_filename: string;
  restored: boolean;
  content_restored: boolean;
}

/* --------------------- Evidence intelligence (phase 2) --------------------- */

/** Background analysis job (features: ingestion, custody, …). */
export type AnalysisJobStatus = "pending" | "running" | "succeeded" | "partial" | "failed" | "canceled";

export interface AnalysisJobOut {
  id: string;
  case_id: string;
  feature: string;
  status: AnalysisJobStatus;
  idempotency_key: string;
  progress: number;
  total_records: number;
  processed_records: number;
  attempts: number;
  timeout_seconds: number;
  cancel_requested: boolean;
  error: string | null;
  result_summary: Record<string, unknown> | null;
  evidence_file_id: string | null;
  actor_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisJobList {
  items: AnalysisJobOut[];
  total: number;
  limit: number;
  offset: number;
}

/** 202 body of every job-submitting endpoint (extraction, custody audit). */
export interface JobSubmitResponse {
  job: AnalysisJobOut;
  duplicate: boolean;
}

/**
 * One AI report-audit run (phase 6): the job state plus the linkage to its
 * `report_claim_review` findings artifact. `stale` compares the audited
 * draft hash against the current content of the referenced message at read
 * time (`null` for supplied-text audits or missing messages). Findings are
 * unreviewed model-derived output — never auto-trusted.
 */
export interface ReportAuditOut {
  id: string;
  case_id: string;
  status: AnalysisJobStatus;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  draft_source_type: string | null;
  draft_hash: string | null;
  draft_chars: number | null;
  conversation_id: string | null;
  message_id: string | null;
  artifact_id: string | null;
  claims: number | null;
  stale: boolean | null;
  result_summary: Record<string, unknown> | null;
}

export interface ReportAuditDetailOut extends ReportAuditOut {
  artifact: DerivedArtifactOut | null;
}

export interface ReportAuditList {
  items: ReportAuditOut[];
  total: number;
  limit: number;
  offset: number;
}

/** Exactly one source: a report-message reference XOR investigator text. */
export interface ReportAuditSubmitInput {
  conversation_id?: string;
  message_id?: string;
  draft_text?: string;
}

/**
 * One derived artifact: extraction output, deterministic integrity fact or
 * custody finding (plus AI explanations, which are always `validation_status
 * "flagged"`). Nothing here is auto-approved — review is human-only.
 */
export interface DerivedArtifactOut {
  id: string;
  case_id: string;
  kind: string;
  origin: string;
  status: string;
  validation_status: string;
  evidence_file_id: string | null;
  source_record_id: string | null;
  source_locator: Record<string, unknown> | null;
  payload: Record<string, unknown>;
  content_hash: string;
  parser_version: string;
  prompt_version: string | null;
  model_profile: string | null;
  analysis_job_id: string | null;
  validation_errors: Record<string, unknown>[] | null;
  review_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  parent_artifact_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArtifactList {
  items: DerivedArtifactOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface ArtifactReviewRequest {
  decision: "approved" | "rejected";
  note?: string | null;
  /** Approved extraction edits: `{"fields": {...}}`, re-validated server-side. */
  payload?: { fields?: Record<string, string[]> } | null;
}

/**
 * Reviewer resolution states appended to one contradiction candidate as a new
 * child artifact. `confirmed` / `false_positive` are NOT here — they stay the
 * one-shot approve/reject artifact review. A note is required for every state.
 */
export type ContradictionResolutionState = "explained" | "requires_evidence" | "deferred";

export interface ContradictionResolveRequest {
  state: ContradictionResolutionState;
  note: string;
}

/* ------------------ Financial flow (phase 4, feature A) ------------------ */

/** One traversed edge of a bounded structure trace — never a confirmed transfer. */
export interface FlowTraceHop {
  source: string;
  target: string;
  edge_kind: string;
  derivation: string;
  confidence: string;
  relationship_type: string | null;
  supporting_source_record_ids: string[];
}

/**
 * One maximal path from the traced node. `end_state: "dead_end"` marks a trail
 * that stops in the ingested evidence (`incomplete`); `"depth_limit"` marks a
 * path cut by the configured bound, where more evidence may exist beyond it.
 */
export interface FlowTracePath {
  nodes: string[];
  hops: FlowTraceHop[];
  depth: number;
  end_state: string;
  incomplete: boolean;
}

export interface FlowTraceRequest {
  target: string;
  target_kind?: "account" | "transaction";
  edge_kind?: "association" | "transfer";
  max_depth?: number | null;
  max_paths?: number | null;
}

/** Deterministic trace result: scope, bounds and limitations travel with it. */
export interface FlowTraceResponse {
  case_id: string;
  flow_rules_version: string;
  target: string;
  target_kind: string;
  edge_kind: string;
  status: "ok" | "not_found" | "insufficient_data";
  reason: string | null;
  start_node: string | null;
  matched_facts: number;
  target_degree: number;
  paths: FlowTracePath[];
  paths_bounded: boolean;
  records_bounded: boolean;
  bounds: { max_depth: number; max_paths: number; max_records: number; records_scanned: number };
  network: { nodes_total: number; edges_total: number; confirmed_transfer_edges: number };
  limitations: string[];
}

/** Deterministic hash verification result. `missing_*` are results, not errors. */
export interface IntegrityVerificationResponse {
  evidence_id: string;
  artifact_id: string;
  status: "match" | "mismatch" | "missing_expected" | "missing_source" | "unsupported_algorithm";
  algorithm: string | null;
  expected_sha256: string | null;
  calculated_sha256: string | null;
  object_present: boolean;
  file_size_bytes: number | null;
  duration_ms: number;
  verified_at: string;
}

/** One append-only custody event as stored (recorded_at = documentation time). */
export interface CustodyEventOut {
  id: string;
  case_id: string;
  evidence_file_id: string | null;
  event_type: string;
  occurred_at: string;
  recorded_at: string;
  actor_user_id: string | null;
  collector: string | null;
  transferor: string | null;
  recipient: string | null;
  location: string | null;
  method: string | null;
  notes: string | null;
  recorded_sha256: string | null;
}

export interface CustodyEventCreateRequest {
  event_type: string;
  occurred_at: string;
  collector?: string | null;
  transferor?: string | null;
  recipient?: string | null;
  location?: string | null;
  method?: string | null;
  notes?: string | null;
  recorded_sha256?: string | null;
}

export interface CustodyChronologyResponse {
  evidence_id: string;
  original_filename: string;
  sha256: string;
  algorithm: string;
  format: string | null;
  file_size: number;
  created_at: string;
  deleted_at: string | null;
  events: CustodyEventOut[];
  event_count: number;
}

/** Facts-only AI narration of one finding; the model certifies nothing. */
export interface CustodyExplainResponse {
  explanation_artifact: DerivedArtifactOut;
  text: string;
  rule: string;
  /** Structured narration for financial / cross-case findings (phase 4). */
  explanation?: CrossCaseExplanation | FinancialExplanation | null;
}

/** Structured, citation-validated narration of a cross-case candidate. */
export interface CrossCaseExplanation {
  summary: string;
  matching_signal: string;
  cited_identifiers: string[];
  conflicts: string[];
  not_established: string[];
  verification_steps: string[];
}

/** Structured, citation-validated narration of a financial finding. */
export interface FinancialExplanation {
  summary: string;
  why_patterns_fired: string[];
  cited_transaction_ids: string[];
  alternative_explanations: string[];
  missing_information: string[];
  verification_steps: string[];
}

/* ------------------------ Cross-case discovery (phase 4 B) ----------------- */

/** One bounded discovery scope: the anchor case plus the explicitly chosen cases. */
export interface CrossCaseDiscoverInput {
  anchor_case_id: string;
  case_ids: string[];
}

/** One case's side of a cross-case candidate (only the caller's visible sides). */
export interface CrossCaseSide {
  case_id: string;
  value_originals: string[];
  originals_capped?: boolean;
  entity_ids?: string[];
  source_record_ids?: string[];
  evidence_file_ids?: string[];
  supporting_ids_capped?: boolean;
  reviewed_alias?: boolean;
  contributing_kinds?: string[];
}

/** Deterministic candidate payload: classification, score band and limitations. */
export interface CrossCaseCandidatePayload {
  crosscase_rules_version?: string;
  scope?: { case_ids?: string[]; scope_hash?: string; cases_in_group?: string[] };
  group?: { indicator_kind?: string; value_normalized?: string };
  classification?: string;
  classification_semantics?: Record<string, string>;
  /** 0–100 additive score band, explicitly NOT a probability. */
  score?: number;
  score_semantics?: string;
  signal_kinds?: string[];
  additional_shared_kinds?: string[];
  conflicting_attributes?: { flagged?: boolean; evidence?: Array<Record<string, unknown>> };
  sides?: CrossCaseSide[];
  reviewable?: boolean;
  review_disabled_reason?: string | null;
  limitations?: string[];
  graph_freshness_note?: string;
}

/** Read-path response: candidates touching an inaccessible case are omitted. */
export interface CrossCaseCandidateListResponse {
  items: DerivedArtifactOut[];
  total: number;
  anchor_case_id: string;
  crosscase_rules_version: string;
  graph_freshness_note: string;
}

/* ---------------------------- Pagination ---------------------------- */

export interface PageParams {
  limit?: number;
  offset?: number;
}