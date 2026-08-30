import type {
  Api,
  ApiTimelineEvent,
  AuditParams,
  CaseListParams,
  EntityListParams,
  FindingListParams,
  LoginInput,
  RegisterInput,
  RegisteredUserOut,
  UploadFile,
} from "@/api/contract";
import { authSession } from "@/api/client/session";
import { ApiError } from "@/types/api";
import type {
  AnalyticsRun,
  AuditEvent,
  Case,
  CaseUpdateRequest,
  CentralityEntry,
  Entity,
  EntityDetail,
  EntityEgoGraph,
  EvidenceCreateResponse,
  EvidenceDetail,
  EvidenceList,
  EvidenceProvenanceResponse,
  Finding,
  FindingList,
  FindingStats,
  FindingStatusOut,
  GraphStats,
  GraphResponse,
  IngestAccepted,
  IngestionJob,
  IngestJobList,
  NetworkProfile,
  RelationshipStrength,
} from "@/types/domain";
import {
  CASE_ID_MAIN,
  CASE_ID_SECONDARY,
  CASE_ID_CLOSED,
  EVIDENCE_DETAILS,
  KEY_ENTITY_IDS,
  MAIN_AUDIT,
  MAIN_CENTRALITY,
  MAIN_COMMUNITIES,
  MAIN_ENTITIES,
  MAIN_ENTITY_DETAILS,
  MAIN_EVIDENCE,
  MAIN_FINDINGS,
  MAIN_GRAPH_EDGES,
  MAIN_GRAPH_NODES,
  MAIN_HYPOTHESES,
  MAIN_JOBS,
  MAIN_NETWORK_PROFILES,
  MAIN_PATTERNS,
  MAIN_PRIORITIES,
  MAIN_RELATIONSHIPS,
  MAIN_RELATIONSHIP_STRENGTH,
  MAIN_RUNS,
  MOCK_CASES,
  SECONDARY_CASE_DATA,
  CLOSED_CASE_GRAPH,
  CLOSED_CASE_ENTITIES,
  TERTIARY_CASE_ENTITIES,
  USER_ADMIN_ID,
  USER_ANALYST_ID,
  USER_INVESTIGATOR_ID,
  USER_VIEWER_ID,
  findingsStatsFor,
  graphStatsFor,
  summaryForCase,
  uid,
  iso,
} from "./data";
import { delay } from "@/lib/utils";

export const MOCK_LATENCY = 170;

interface MockUserRecord {
  id: string;
  username: string;
  email: string;
  password: string;
  is_active: boolean;
  roles: Array<"ADMIN" | "INVESTIGATOR" | "ANALYST" | "VIEWER">;
}

const MOCK_USERS: MockUserRecord[] = [
  {
    id: USER_ADMIN_ID,
    username: "admin",
    email: "admin@cybersaarthi.local",
    password: "admin-dev-password",
    is_active: true,
    roles: ["ADMIN"],
  },
  {
    id: USER_INVESTIGATOR_ID,
    username: "investigator",
    email: "investigator@cybersaarthi.local",
    password: "investigator-dev-password",
    is_active: true,
    roles: ["INVESTIGATOR"],
  },
  {
    id: USER_ANALYST_ID,
    username: "analyst",
    email: "analyst@cybersaarthi.local",
    password: "analyst-demo-password",
    is_active: true,
    roles: ["ANALYST"],
  },
  {
    id: USER_VIEWER_ID,
    username: "viewer",
    email: "viewer@cybersaarthi.local",
    password: "viewer-demo-password",
    is_active: true,
    roles: ["VIEWER"],
  },
];

/* In-memory mutable state (deterministic initial data; mutations persist for the session). */
const casesState: Case[] = [...MOCK_CASES];
const evidenceState: EvidenceList["items"] = [...MAIN_EVIDENCE];
const findingsState: Finding[] = [...MAIN_FINDINGS];
const jobsState = [...MAIN_JOBS];
const auditState: AuditEvent[] = [...MAIN_AUDIT];
const registeredState: Array<MockUserRecord & { created_at: string }> = [];

let currentUserId: string | null = null;
let currentRoles: MockUserRecord["roles"] = [];

function currentUser(): { record?: MockUserRecord; roles: MockUserRecord["roles"] } {
  const id = currentUserId ?? authSession.getUser()?.id;
  return {
    record: MOCK_USERS.find((u) => u.id === id) ?? registeredState.find((u) => u.id === id),
    roles: currentRoles,
  };
}

function requireAuth(): MockUserRecord {
  const { record } = currentUser();
  if (!record) throw unauthorized();
  return record;
}

function requirePermission(permission: string): MockUserRecord {
  const user = requireAuth();
  const permissions = resolvedPermissions(user.roles);
  if (!permissions.includes(permission)) {
    throw new ApiError({ status: 403, code: "FORBIDDEN", message: `permission '${permission}' required` });
  }
  return user;
}

const ROLE_PERMISSIONS: Record<string, string[]> = {
  ADMIN: [
    "case.read", "case.create", "case.update", "case.archive", "evidence.read",
    "evidence.upload", "ingestion.run", "analytics.run", "findings.read",
    "findings.review", "findings.confirm", "findings.dismiss", "users.manage", "audit.read",
  ],
  INVESTIGATOR: [
    "case.read", "case.create", "case.update", "case.archive", "evidence.read",
    "evidence.upload", "ingestion.run", "analytics.run", "findings.read",
    "findings.review", "findings.confirm", "findings.dismiss", "audit.read",
  ],
  ANALYST: [
    "case.read", "evidence.read", "analytics.run", "findings.read", "findings.review",
  ],
  VIEWER: ["case.read", "evidence.read", "findings.read"],
};

export function resolvedPermissions(roles: MockUserRecord["roles"]): string[] {
  const set = new Set<string>();
  for (const role of roles) for (const perm of ROLE_PERMISSIONS[role] ?? []) set.add(perm);
  return [...set];
}

function unauthorized(): ApiError {
  return new ApiError({ status: 401, code: "UNAUTHORIZED", message: "Not authenticated" });
}

function notFound(message: string): ApiError {
  return new ApiError({ status: 404, code: "NOT_FOUND", message });
}

/** Access rule matching the backend: owner or admin. */
function assertCaseAccess(caseId: string): Case {
  const caze = casesState.find((c) => c.id === caseId);
  if (!caze) throw notFound("case not found");
  const { record, roles } = currentUser();
  if (!record) throw unauthorized();
  const isAdmin = roles.includes("ADMIN");
  if (!isAdmin && caze.owner_id !== record.id) {
    throw new ApiError({ status: 403, code: "FORBIDDEN", message: "You do not have access to this case" });
  }
  return caze;
}

function pushAudit(action: string, resourceType: string, caseId: string | null, meta: Record<string, unknown> | null): void {
  const { record } = currentUser();
  auditState.unshift({
    id: uid(4200 + auditState.length),
    actor_id: record?.id ?? null,
    action,
    resource_type: resourceType,
    resource_id: uid(4200 + auditState.length),
    case_id: caseId,
    metadata_: meta,
    created_at: new Date().toISOString(),
  });
}

/* ------------------------------------------------------------------ */

export const mockApi: Api = {
  src: "mock",

  auth: {
    async login(input: LoginInput) {
      await delay(MOCK_LATENCY);
      const username = input.username.trim();
      const user =
        MOCK_USERS.find((u) => u.username === username || u.email === username) ??
        registeredState.find((u) => u.username === username || u.email === username);
      if (!user || user.password !== input.password) {
        throw new ApiError({ status: 401, code: "UNAUTHORIZED", message: "invalid username or password" });
      }
      if (!user.is_active) {
        throw new ApiError({ status: 403, code: "FORBIDDEN", message: "account is deactivated" });
      }
      currentUserId = user.id;
      currentRoles = user.roles;
      authSession.setPermissions(resolvedPermissions(user.roles));
      pushAudit("auth.login_succeeded", "user", null, { expires_in_minutes: 30 });
      return {
        access_token: `mock-token-${user.id}`,
        token_type: "bearer",
        expires_in: 1800,
        user: { id: user.id, username: user.username, email: user.email, is_active: user.is_active },
      };
    },

    async me() {
      await delay(MOCK_LATENCY / 2);
      const { record, roles } = currentUser();
      if (!record) throw unauthorized();
      const roleList = record.roles.length ? record.roles : roles;
      const permissions = resolvedPermissions(roleList);
      authSession.setPermissions(permissions);
      return {
        user: { id: record.id, username: record.username, email: record.email, is_active: record.is_active },
        roles: roleList,
        permissions,
      };
    },

    async register(input: RegisterInput): Promise<RegisteredUserOut> {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      if (MOCK_USERS.some((u) => u.username === input.username) || registeredState.some((u) => u.username === input.username)) {
        throw new ApiError({ status: 409, code: "CONFLICT", message: `username '${input.username}' is taken` });
      }
      if (MOCK_USERS.some((u) => u.email === input.email)) {
        throw new ApiError({ status: 409, code: "CONFLICT", message: `email '${input.email}' is registered` });
      }
      const record: MockUserRecord & { created_at: string } = {
        id: uid(4300 + registeredState.length),
        username: input.username,
        email: input.email.toLowerCase(),
        password: input.password,
        is_active: true,
        roles: [input.role as MockUserRecord["roles"][number]],
        created_at: iso(0),
      };
      registeredState.push(record);
      pushAudit("auth.user_created", "user", null, { username: input.username, role: input.role });
      return {
        user: { id: record.id, username: record.username, email: record.email, is_active: true },
        roles: record.roles,
        created_at: record.created_at,
      };
    },
  },

  cases: {
    async list(params: CaseListParams = {}) {
      await delay(MOCK_LATENCY);
      const user = requireAuth();
      const isAdmin = user.roles.includes("ADMIN");
      let items = casesState.filter((c) => isAdmin || c.owner_id === user.id);
      if (params.search) {
        const q = params.search.toLowerCase();
        items = items.filter(
          (c) => c.title.toLowerCase().includes(q) || c.case_number.toLowerCase().includes(q),
        );
      }
      if (params.status) items = items.filter((c) => c.status === params.status);
      const start = params.offset ?? 0;
      const end = start + (params.limit ?? 100);
      return { items: items.slice(start, end), total: items.length };
    },

    async get(caseId: string) {
      await delay(MOCK_LATENCY / 2);
      return assertCaseAccess(caseId);
    },

    async create(input: { title: string; description?: string | null; case_number?: string | null; status?: Case["status"] }) {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.create");
      const caze: Case = {
        id: uid(Math.floor(900000 + Math.random() * 10000)),
        case_number: input.case_number ?? `CS-${Math.random().toString(16).slice(2, 10).toUpperCase()}`,
        title: input.title,
        description: input.description ?? null,
        status: input.status ?? "open",
        owner_id: user.id,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      casesState.unshift(caze);
      pushAudit("case.created", "case", caze.id, { title: caze.title, case_number: caze.case_number });
      return caze;
    },

    async update(caseId: string, input: CaseUpdateRequest) {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.update");
      const caze = assertCaseAccess(caseId);
      if ((input.status as string) === "archived") {
        throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "use the archive endpoint" });
      }
      const changes: Record<string, unknown> = {};
      if (input.title !== undefined && input.title !== null && input.title !== caze.title) {
        changes.title = input.title;
        caze.title = input.title;
      }
      if (input.description !== undefined && input.description !== caze.description) {
        changes.description = input.description;
        caze.description = input.description;
      }
      if (input.status && input.status !== caze.status) {
        changes.status = input.status;
        caze.status = input.status;
      }
      caze.updated_at = new Date().toISOString();
      if (Object.keys(changes).length > 0) {
        pushAudit("case.updated", "case", caze.id, { changes });
      }
      void user;
      return caze;
    },

    async archive(caseId: string) {
      await delay(MOCK_LATENCY);
      requirePermission("case.archive");
      const caze = assertCaseAccess(caseId);
      const from = caze.status;
      caze.status = "archived";
      caze.updated_at = new Date().toISOString();
      pushAudit("case.archived", "case", caze.id, { from_status: from });
      return caze;
    },
  },

  entities: {
    async list(caseId: string, params: EntityListParams = {}) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const source = entitiesFor(caseId);
      let items = source;
      if (params.entity_type) items = items.filter((e) => e.entity_type === params.entity_type);
      if (params.status) items = items.filter((e) => e.status === params.status);
      if (params.query) {
        const q = params.query.toLowerCase();
        items = items.filter(
          (e) =>
            e.display_value.toLowerCase().includes(q) ||
            e.canonical_value.toLowerCase().includes(q) ||
            e.entity_type.toLowerCase().includes(q),
        );
      }
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      const itemsById = [...items].sort((a, b) => a.display_value.localeCompare(b.display_value));
      return { items: itemsById.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async get(caseId: string, entityId: string): Promise<EntityDetail> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const entity = entitiesFor(caseId).find((e) => e.id === entityId);
      if (!entity) throw notFound("entity not found");
      const detail = MAIN_ENTITY_DETAILS[entity.display_value] ?? MAIN_ENTITY_DETAILS[entity.canonical_value];
      return {
        ...entity,
        aliases: detail?.aliases ?? [],
        context: detail?.context ?? null,
      };
    },

    async relationships(caseId: string, limit = 500) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const items =
        caseId === CASE_ID_MAIN ? MAIN_RELATIONSHIPS : caseId === CASE_ID_SECONDARY ? SECONDARY_CASE_DATA.relationships : [];
      return { items: items.slice(0, limit), total: items.length };
    },
  },

  evidence: {
    async list(caseId: string, params = {}) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const items = caseId === CASE_ID_MAIN ? evidenceState : caseId === CASE_ID_SECONDARY ? SECONDARY_CASE_DATA.evidence : [];
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { items: sorted.slice(offset, offset + limit), total: sorted.length, limit, offset };
    },

    async get(caseId: string, evidenceId: string): Promise<EvidenceDetail> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const item = evidenceState.find((e) => e.id === evidenceId);
      if (!item) throw notFound("evidence not found");
      const seedIndex = MAIN_EVIDENCE.findIndex((e) => e.id === evidenceId);
      const detail =
        EVIDENCE_DETAILS[
          Object.keys(EVIDENCE_DETAILS)[Math.max(0, seedIndex)] ?? "demo_cdr"
        ];
      return {
        id: item.id,
        case_id: caseId,
        data_source: detail?.data_source ?? "csv",
        original_filename: item.original_filename,
        stored_key: detail?.stored_key ?? `cases/${caseId}/evidence/${item.id}/${item.original_filename}`,
        content_type: detail?.content_type ?? "text/plain",
        file_size: item.file_size,
        sha256: item.sha256,
        format: item.format,
        encoding: detail?.encoding ?? "utf-8",
        status: item.status,
        status_detail: detail?.status_detail ?? null,
        record_count: item.record_count,
        metadata_json: detail?.metadata_json ?? null,
        created_at: item.created_at,
      };
    },

    async upload(caseId: string, file: UploadFile, _dataSource = "csv") {
      void _dataSource;
      await delay(MOCK_LATENCY * 2);
      requirePermission("evidence.upload");
      assertCaseAccess(caseId);
      let hash = 0x811c9dc5;
      const seed = `${file.name}:${file.size}`;
      for (let i = 0; i < seed.length; i++) {
        hash ^= seed.charCodeAt(i);
        hash = (hash * 0x01000193) >>> 0;
      }
      const id = uid(5500 + evidenceState.length);
      const created = new Date().toISOString();
      const item: EvidenceCreateResponse = {
        id,
        case_id: caseId,
        original_filename: file.name,
        stored_key: `cases/${caseId}/evidence/${id}/${file.name}`,
        content_type: file.type || "application/octet-stream",
        file_size: file.size,
        sha256: `${hash.toString(16).padStart(8, "0")}${hash.toString(16).padStart(8, "0")}${hash.toString(16).padStart(8, "0")}${hash.toString(16).padStart(8, "0")}`,
        format: file.name.endsWith(".csv") ? "csv" : file.name.endsWith(".json") ? "json" : "txt",
        encoding: "utf-8",
        status: "pending",
        status_detail: null,
        created_at: created,
      };
      evidenceState.push({
        id,
        original_filename: file.name,
        sha256: item.sha256,
        format: item.format,
        file_size: file.size,
        status: "pending",
        record_count: null,
        created_at: created,
      });
      pushAudit("evidence.uploaded", "evidence_file", caseId, { filename: file.name, format: item.format });
      return item;
    },

    async provenance(caseId: string, evidenceId: string): Promise<EvidenceProvenanceResponse> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const item = evidenceState.find((e) => e.id === evidenceId);
      if (!item) throw notFound("evidence not found");
      const index = MAIN_EVIDENCE.findIndex((e) => e.id === evidenceId);
      const relatedEntityIds =
        index === 0
          ? ["Rajesh Kumar", "Sunita Sharma", "Arjun Mehta", "Kavita Rao", "+91-98765-43210", "+91-91234-56789", "+91-90000-11111", "+91-98111-22233", "TechSecure Pvt Ltd"]
          : index === 1
            ? ["Rajesh Kumar", "Arjun Mehta", "Mumbai", "Pune", "Delhi", "Noida", "MH12AB1234", "MH12AB2345"]
            : index === 2
              ? ["Rajesh Kumar", "Arjun Mehta", "1100220011", "5500667788", "2244660088"]
              : index === 3
                ? ["Rajesh Kumar", "Sunita Sharma", "Mehul Desai", "3300445566", "9900112233"]
                : ["Rajesh Kumar", "Arjun Mehta", "Varun Joshi", "MH12AB1234", "DL01EF9012", "UP32GH3456"];
      const findingIds = MAIN_FINDINGS.filter((f) => f.evidence_ids.includes(evidenceId)).map((f) => f.id);
      const detail = await this.get(caseId, evidenceId).catch(() => null);
      return {
        evidence: (detail ?? {}) as EvidenceDetail,
        record_count: item.record_count ?? 0,
        records_by_status: { [item.status]: item.record_count ?? 0 },
        entity_count: relatedEntityIds.length,
        relationship_count: Math.max(1, Math.floor(relatedEntityIds.length / 2)),
        finding_count: findingIds.length,
        related_entity_ids: relatedEntityIds.map((k) => KEY_ENTITY_IDS[k] ?? relatedEntityId(k, caseId)),
        related_relationship_ids: [],
        finding_ids: findingIds,
      };
    },

    async ingest(caseId: string, evidenceFileId: string): Promise<IngestAccepted> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const item = evidenceState.find((e) => e.id === evidenceFileId);
      if (!item) throw notFound("evidence not found");
      const job: IngestionJob = {
        id: uid(5600 + jobsState.length),
        case_id: caseId,
        evidence_file_id: evidenceFileId,
        stage: "complete",
        status: "completed",
        progress: 100,
        total_records: item.record_count ?? 40,
        processed_records: item.record_count ?? 40,
        graph_sync_status: "synced" as const,
        error: null,
        graph_error: null,
        summary: { records: item.record_count ?? 40, created_records: item.record_count ?? 40, entities: 14, relationships: 18 },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      jobsState.unshift(job);
      item.status = "ingested";
      pushAudit("ingestion.job_ran", "ingestion_job", caseId, { status: "completed" });
      return { job, duplicate: false };
    },

    async jobs(caseId: string, params = {}): Promise<IngestJobList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const items = caseId === CASE_ID_MAIN ? jobsState : caseId === CASE_ID_SECONDARY ? SECONDARY_CASE_DATA.jobsList : [];
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },
  },

  graph: {
    async get(caseId: string): Promise<GraphResponse> {
      await delay(MOCK_LATENCY * 2);
      assertCaseAccess(caseId);
      if (caseId === CASE_ID_MAIN) return { case_id: caseId, nodes: MAIN_GRAPH_NODES, edges: MAIN_GRAPH_EDGES };
      if (caseId === CASE_ID_SECONDARY) {
        return { case_id: caseId, nodes: SECONDARY_CASE_DATA.graphNodes, edges: SECONDARY_CASE_DATA.graphEdges };
      }
      if (caseId === CASE_ID_CLOSED) return { case_id: caseId, nodes: CLOSED_CASE_GRAPH.nodes, edges: CLOSED_CASE_GRAPH.edges };
      return { case_id: caseId, nodes: [], edges: [] };
    },

    async stats(caseId: string): Promise<GraphStats> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const graph = await (async () => (this as Api["graph"]).get(caseId))();
      return graphStatsFor(caseId, graph.nodes, graph.edges);
    },

    async ego(caseId: string, entityId: string): Promise<EntityEgoGraph> {
      await delay(MOCK_LATENCY * 2);
      assertCaseAccess(caseId);
      const graph = await (async () => (this as Api["graph"]).get(caseId))();
      const node = graph.nodes.find((n) => n.id === entityId);
      if (!node) throw notFound("entity not in graph");
      const neighbourIds = new Set<string>([entityId]);
      const edges = graph.edges.filter((e) => e.source === entityId || e.target === entityId);
      for (const edge of edges) {
        neighbourIds.add(edge.source);
        neighbourIds.add(edge.target);
      }
      return {
        case_id: caseId,
        nodes: graph.nodes.filter((n) => neighbourIds.has(n.id)),
        edges,
        centre: entityId,
      };
    },
  },

  analytics: {
    async summary(caseId: string) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const data = summaryForCase(caseId);
      return {
        case_id: caseId,
        entity_count: data.entity_count,
        relationship_count: data.relationship_count,
        community_count: data.community_count,
        max_evidence_per_relationship: caseId === CASE_ID_MAIN ? 6 : 1,
        average_network_score: data.average_network_score,
        profile_tiers: data.profile_tiers,
        priority_tiers: data.priority_tiers,
        findings_by_severity: data.findings_by_severity,
        findings_by_type: data.findings_by_type,
        finding_count: data.finding_count,
        exact_graph: data.exact_graph,
        approximation_notice: null,
        generated_at: iso(0),
      };
    },

    async centrality(caseId: string, metric = "degree", limit = 50): Promise<CentralityEntry[]> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      if (caseId !== CASE_ID_MAIN) return [];
      const entries = MAIN_CENTRALITY.filter((e) => e.metric === metric).slice(0, limit);
      return entries;
    },

    async communities(caseId: string) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      if (caseId === CASE_ID_MAIN) return MAIN_COMMUNITIES;
      if (caseId === CASE_ID_SECONDARY) return [{ community_id: "C1", member_count: 6, density: 0.35, internal_edges: 5, external_edges: 2, dominant_entity_types: ["person", "organization"], dominant_relationship_types: ["works_for"], member_entity_ids: [], score: 0.6, explanation: "Single import operation." }];
      return [];
    },

    async networkDna(caseId: string, limit = 50): Promise<NetworkProfile[]> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const profiles =
        caseId === CASE_ID_MAIN
          ? MAIN_NETWORK_PROFILES
          : caseId === CASE_ID_SECONDARY
            ? [
                { entity_id: SECONDARY_CASE_DATA.entities[0].id, entity_type: "person", display_value: "Dinesh Sawant", overall_score: 0.62, tier: "MONITORED" as const, features: {}, signals: [], explanation: "Central to manifest network." },
              ]
            : [];
      return profiles.slice(0, limit);
    },

    async priorities(caseId: string, limit = 50) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const rows = caseId === CASE_ID_MAIN ? MAIN_PRIORITIES : [];
      void limit;
      return rows;
    },

    async strength(caseId: string, limit = 100): Promise<RelationshipStrength[]> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const rows = caseId === CASE_ID_MAIN ? MAIN_RELATIONSHIP_STRENGTH : [];
      return rows.slice(0, limit);
    },

    async patterns(caseId: string, limit = 50) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      return caseId === CASE_ID_MAIN ? MAIN_PATTERNS.slice(0, limit) : [];
    },

    async hypotheses(caseId: string, limit = 25) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      return caseId === CASE_ID_MAIN ? MAIN_HYPOTHESES.slice(0, limit) : [];
    },

    async run(caseId: string): Promise<AnalyticsRun> {
      await delay(MOCK_LATENCY * 3);
      requirePermission("analytics.run");
      assertCaseAccess(caseId);
      const run: AnalyticsRun = {
        id: uid(5700 + MAIN_RUNS.length),
        case_id: caseId,
        status: "completed",
        stage: "complete",
        error: null,
        actor_id: currentUserId,
        summary: summaryForCase(caseId) as unknown as Record<string, unknown>,
        started_at: new Date(Date.now() - 60000).toISOString(),
        completed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      };
      pushAudit("analytics.run_completed", "analytics_run", caseId, { status: "completed", stage: "complete" });
      return run;
    },

    async runs(caseId: string, params = {}) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const items = caseId === CASE_ID_MAIN ? MAIN_RUNS : [];
      const limit = params.limit ?? 20;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length };
    },
  },

  findings: {
    async list(caseId: string, params: FindingListParams = {}): Promise<FindingList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = caseId === CASE_ID_MAIN ? findingsState : caseId === CASE_ID_SECONDARY ? SECONDARY_CASE_DATA.findings : [];
      if (params.finding_type) items = items.filter((f) => f.finding_type === params.finding_type);
      if (params.status) items = items.filter((f) => f.status === params.status);
      if (params.severity) items = items.filter((f) => f.severity === params.severity);
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { items: sorted.slice(offset, offset + limit), total: sorted.length, limit, offset };
    },

    async get(caseId: string, findingId: string): Promise<Finding> {
      await delay(MOCK_LATENCY / 2);
      assertCaseAccess(caseId);
      const finding = findingsState.find((f) => f.id === findingId);
      if (!finding) throw notFound("finding not found");
      return finding;
    },

    async stats(caseId: string, runId?: string): Promise<FindingStats> {
      await delay(MOCK_LATENCY / 2);
      assertCaseAccess(caseId);
      const items = caseId === CASE_ID_MAIN ? findingsState : caseId === CASE_ID_SECONDARY ? SECONDARY_CASE_DATA.findings : [];
      void runId;
      return findingsStatsFor(items);
    },

    async updateStatus(caseId: string, findingId: string, input: { status: string; reason?: string | null }): Promise<FindingStatusOut> {
      await delay(MOCK_LATENCY);
      const user = requirePermission(permissionForStatus(input.status));
      assertCaseAccess(caseId);
      const finding = findingsState.find((f) => f.id === findingId);
      if (!finding) throw notFound("finding not found");
      const previous = finding.status;
      const isClosed = finding.status === "DISMISSED" || finding.status === "CONFIRMED";
      const isAdmin = user.roles.includes("ADMIN");
      if (isClosed && previous !== input.status && !isAdmin) {
        throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "closed findings are immutable except by ADMIN" });
      }
      const changed = previous !== input.status;
      finding.status = input.status as Finding["status"];
      finding.reviewed_by = user.id;
      finding.reviewed_at = new Date().toISOString();
      finding.review_comment = input.reason ?? null;
      if (changed) {
        pushAudit("finding.status_changed", "finding", caseId, { from: previous, to: input.status, reason: input.reason });
      }
      return {
        id: finding.id,
        status: finding.status,
        reviewed_by: user.id,
        reviewed_at: finding.reviewed_at,
        review_comment: finding.review_comment,
      };
    },
  },

  audit: {
    async list(params: AuditParams = {}) {
      await delay(MOCK_LATENCY);
      requirePermission("audit.read");
      let items = [...auditState].sort((a, b) => b.created_at.localeCompare(a.created_at));
      if (params.case_id) items = items.filter((e) => e.case_id === params.case_id);
      if (params.actor_id) items = items.filter((e) => e.actor_id === params.actor_id);
      if (params.action) items = items.filter((e) => e.action === params.action);
      if (params.resource_type) items = items.filter((e) => e.resource_type === params.resource_type);
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },
  },

  timeline: {
    async events(caseId: string, limit = 100): Promise<ApiTimelineEvent[]> {
      await delay(MOCK_LATENCY);
      const { record } = currentUser();
      if (!record) throw unauthorized();
      const permissions = resolvedPermissions(record.roles);
      if (!permissions.includes("audit.read")) return [];
      const items = [...auditState]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .filter((e) => e.case_id === caseId)
        .slice(0, limit);
      return items.map((e) => ({
        id: e.id,
        action: e.action,
        case_id: e.case_id,
        actor_id: e.actor_id,
        metadata_: e.metadata_,
        created_at: e.created_at,
      }));
    },
  },
};

function permissionForStatus(status: string): string {
  const map: Record<string, string> = {
    REVIEWED: "findings.review",
    DISMISSED: "findings.dismiss",
    CONFIRMED: "findings.confirm",
  };
  return map[status] ?? "findings.review";
}

function entitiesFor(caseId: string): Entity[] {
  if (caseId === CASE_ID_MAIN) return MAIN_ENTITIES;
  if (caseId === CASE_ID_SECONDARY) return SECONDARY_CASE_DATA.entities;
  if (caseId === CASE_ID_CLOSED) return CLOSED_CASE_ENTITIES;
  return TERTIARY_CASE_ENTITIES;
}

function relatedEntityId(key: string, caseId: string): string {
  return `d0000000-0000-4000-8000-${caseId.slice(-4)}${key.length}`;
}