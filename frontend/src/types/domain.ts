/**
 * Frontend domain types.
 *
 * These mirror the backend contract in backend/docs/frontend-contract.md and
 * backend/app/schemas. Do not invent fields that the backend does not produce;
 * the mock adapter returns the same shapes so the UI is source-agnostic.
 */

export type Role = "ADMIN" | "INVESTIGATOR" | "ANALYST" | "VIEWER";

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

export type JobStatus = "pending" | "running" | "completed" | "failed" | "partial";

export type GraphSyncStatus = "pending" | "synced" | "failed";

/* ------------------------------- Auth ------------------------------- */

export interface UserOut {
  id: string;
  username: string;
  email: string;
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
  status?: CaseStatus;
}

export interface CaseUpdateRequest {
  title?: string | null;
  description?: string | null;
  status?: Exclude<CaseStatus, "archived">;
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
  created_at: string;
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

/* ---------------------------- Pagination ---------------------------- */

export interface PageParams {
  limit?: number;
  offset?: number;
}