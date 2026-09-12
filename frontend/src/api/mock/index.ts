import type {
  Api,
  AdminUserListParams,
  AuditParams,
  CaseListParams,
  CollectionListParams,
  DeviceListParams,
  EntityListParams,
  FindingListParams,
  InvestigationHypothesisListParams,
  LoginInput,
  RegisterInput,
  RegisteredUserOut,
  ReportListParams,
  SearchParams,
  UploadFile,
  VictimListParams,
  IoTDeviceListParams,
  IoTEventListParams,
} from "@/api/contract";
import { authSession } from "@/api/client/session";
import { ApiError } from "@/types/api";
import type {
  AdminUserOut,
  AnalyticsRun,
  AuditEvent,
  Case,
  CaseMember,
  CaseMemberAddRequest,
  CaseMemberListResponse,
  CaseUpdateRequest,
  CentralityEntry,
  Collection,
  CollectionList,
  CollectionUpdateRequest,
  DeviceList,
  DeviceVerifyRequest,
  DeviceVerifyResponse,
  Entity,
  EntityDetail,
  EntityEgoGraph,
  EntityMergeRequest,
  EvidenceCreateResponse,
  EvidenceDetail,
  EvidenceList,
  EvidenceListItem,
  EvidenceProvenanceResponse,
  EvidenceRestoreResponse,
  FieldDevice,
  Finding,
  FindingList,
  FindingStats,
  FindingStatusOut,
  GraphStats,
  GraphResponse,
  GraphSyncResult,
  HealthResponse,
  ImportAccepted,
  IngestAccepted,
  IngestionJob,
  IngestJobList,
  InvestigationHypothesis,
  InvestigationHypothesisList,
  NetworkProfile,
  RelationshipStrength,
  Report,
  ReportList,
  ReviewDecisionResponse,
  ReviewList,
  SearchResponse,
  TimelineEvent,
  TimelineEventList,
  Victim,
  VictimCreateRequest,
  VictimList,
  VictimUpdateRequest,
  IoTDevice,
  IoTDeviceCreateRequest,
  IoTDeviceList,
  IoTDeviceStats,
  IoTDeviceUpdateRequest,
  IoTEvent,
  IoTEventCreateRequest,
  IoTEventList,
} from "@/types/domain";
import {
  CASE_ID_MAIN,
  CASE_ID_SECONDARY,
  CASE_ID_CLOSED,
  EVIDENCE_DETAILS,
  KEY_ENTITY_IDS,
  MAIN_AUDIT,
  MAIN_CENTRALITY,
  MAIN_COLLECTIONS,
  MAIN_COMMUNITIES,
  MAIN_DEVICES,
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
  MAIN_REGISTERED_HYPOTHESES,
  MAIN_RELATIONSHIPS,
  MAIN_RELATIONSHIP_STRENGTH,
  MAIN_REPORTS,
  MAIN_RUNS,
  MAIN_TIMELINE_EVENTS,
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
  status: "PENDING" | "ACTIVE" | "SUSPENDED" | "REJECTED";
  roles: Array<"ADMIN" | "INVESTIGATOR" | "ANALYST" | "VIEWER">;
}

function active(record: MockUserRecord): boolean {
  return record.status === "ACTIVE";
}

const MOCK_USERS: MockUserRecord[] = [
  {
    id: USER_ADMIN_ID,
    username: "admin",
    email: "admin@cybersaarthi.local",
    password: "admin-dev-password",
    status: "ACTIVE",
    roles: ["ADMIN"],
  },
  {
    id: USER_INVESTIGATOR_ID,
    username: "investigator",
    email: "investigator@cybersaarthi.local",
    password: "investigator-dev-password",
    status: "ACTIVE",
    roles: ["INVESTIGATOR"],
  },
  {
    id: USER_ANALYST_ID,
    username: "analyst",
    email: "analyst@cybersaarthi.local",
    password: "analyst-demo-password",
    status: "ACTIVE",
    roles: ["ANALYST"],
  },
  {
    id: USER_VIEWER_ID,
    username: "viewer",
    email: "viewer@cybersaarthi.local",
    password: "viewer-demo-password",
    status: "ACTIVE",
    roles: ["VIEWER"],
  },
];

const iotDeviceState: IoTDevice[] = [
  {
    id: uid(6020),
    case_id: CASE_ID_MAIN,
    name: "Rahul's old phone",
    device_type: "mobile",
    make: "Samsung",
    model: "Galaxy M13",
    serial_number: "IMEI-3572140890123",
    imei: "357214089012345",
    ip_address: null,
    mac_address: "A4:6B:3F:22:11:90",
    os: "Android",
    os_version: "13",
    owner_name: "Rahul Verma",
    owner_phone: "+91-98711-22334",
    status: "seized",
    description: "Primary device recovered during raid; SIM card removed.",
    firmware_version: null,
    first_seen_at: iso(10, 2),
    last_seen_at: iso(3, 1),
    metadata_json: { acquisition: "Court order 2026-114", location: "Mumbai" },
    event_count: 0,
    created_at: iso(9),
    updated_at: iso(3),
  },
  {
    id: uid(6021),
    case_id: CASE_ID_MAIN,
    name: "Office router",
    device_type: "router",
    make: "TP-Link",
    model: "Archer AX55",
    serial_number: "SN-8021-ARX-55",
    imei: null,
    ip_address: "103.84.116.22",
    mac_address: "7C:39:53:AA:BB:CC",
    os: null,
    os_version: null,
    owner_name: "Skyline Imports",
    owner_phone: null,
    status: "active",
    description: "Registrar at the shell office; DHCP logs under review.",
    firmware_version: "1.2.4",
    first_seen_at: iso(12, 4),
    last_seen_at: iso(0, 1),
    metadata_json: null,
    event_count: 0,
    created_at: iso(12),
    updated_at: iso(0),
  },
];

let iotEventState: IoTEvent[] = [
  {
    id: uid(7020),
    case_id: CASE_ID_MAIN,
    device_id: uid(6020),
    event_type: "location",
    event_time: iso(9, 3),
    source: "cell-tower-318",
    payload: { tower: "MUM-318", accuracy: 42 },
    latitude: 19.076,
    longitude: 72.8777,
    location_label: "Mumbai, Maharashtra",
    confidence: 0.93,
    description: "Device pinged Mumbai Gateway Cell Tower.",
    created_at: iso(9, 3),
  },
  {
    id: uid(7021),
    case_id: CASE_ID_MAIN,
    device_id: uid(6020),
    event_type: "call",
    event_time: iso(8, 5),
    source: "cdr",
    payload: { direction: "outbound", duration_sec: 312, number: "+919833221100" },
    latitude: null,
    longitude: null,
    location_label: null,
    confidence: null,
    description: "Long outbound call to suspected handler line.",
    created_at: iso(8, 5),
  },
  {
    id: uid(7022),
    case_id: CASE_ID_MAIN,
    device_id: uid(6021),
    event_type: "connectivity",
    event_time: iso(5, 2),
    source: "isp",
    payload: { clients: 4, bandwidth_mbps: 12.4 },
    latitude: null,
    longitude: null,
    location_label: "Skyline Imports office",
    confidence: 0.8,
    description: "Four clients connected during investigative hours.",
    created_at: iso(5, 2),
  },
];

/* In-memory mutable state (deterministic initial data; mutations persist for the session). */
const casesState: Case[] = [...MOCK_CASES];
const evidenceState: EvidenceList["items"] = [...MAIN_EVIDENCE];
const findingsState: Finding[] = [...MAIN_FINDINGS];
const jobsState = [...MAIN_JOBS];
const membersState: Record<string, CaseMember[]> = seedMembers();

function seedMembers(): Record<string, CaseMember[]> {
  return Object.fromEntries(
    MOCK_CASES
      .filter((c) => c.owner_id)
      .map((c) => [c.id, [{ user_id: c.owner_id!, role: "collaborator" as const, created_at: c.created_at }]]),
  );
}
const auditState: AuditEvent[] = [...MAIN_AUDIT];
const registeredState: Array<MockUserRecord & { created_at: string }> = [];

const collectionsState: Collection[] = [...MAIN_COLLECTIONS];
const devicesState: FieldDevice[] = [...MAIN_DEVICES];
const reportsState: Report[] = [...MAIN_REPORTS];
const hypothesesState: InvestigationHypothesis[] = [...MAIN_REGISTERED_HYPOTHESES];
const timelineState: TimelineEvent[] = [...MAIN_TIMELINE_EVENTS];
const recycleState: Array<EvidenceListItem & { case_id: string }> = [];

const victimState: Victim[] = [
  {
    id: uid(5010),
    case_id: CASE_ID_MAIN,
    name: "Rajiv Mehta",
    age: 52,
    date_of_birth: null,
    gender: "male",
    classification: "individual",
    phone: "+91-98220-12345",
    email: "rajiv.mehta@gmail.com",
    address: "Mumbai, Maharashtra",
    incident_date: iso(45, 10),
    incident_type: "Investment fraud",
    fraud_category: "Ponzi scheme",
    description: "Victim transferred funds to a fraudulent investment platform promoted over WhatsApp.",
    reported_amount: 1850000,
    currency: "INR",
    amount_lost: 1850000,
    recovery_amount: 0,
    digital_accounts: [{ platform: "geojit", handle: "rajiv.mehta" }],
    devices: [],
    wallet_addresses: null,
    status: "evidence_collected",
    statement: "I was contacted on WhatsApp by 'Sharma Ji' offering guaranteed 30% monthly returns.",
    investigator_notes: "Transfers traced to HDFC account of shell firm. Call records corroborate.",
    recovery_status: null,
    created_by: null,
    created_at: iso(45),
    updated_at: iso(45),
  },
  {
    id: uid(5011),
    case_id: CASE_ID_MAIN,
    name: "Sunita Devi",
    age: 47,
    date_of_birth: null,
    gender: "female",
    classification: "individual",
    phone: "+91-98110-98765",
    email: null,
    address: "New Delhi, Delhi",
    incident_date: iso(28, 3),
    incident_type: "UPI fraud",
    fraud_category: "Phishing",
    description: "Clicked a malicious UPI request link; funds debited from bank account.",
    reported_amount: 42000,
    currency: "INR",
    amount_lost: 42000,
    recovery_amount: 0,
    digital_accounts: [{ platform: "phonepe", handle: "sunitadevi47" }],
    devices: [],
    wallet_addresses: null,
    status: "under_investigation",
    statement: "Received SMS with a payment-request link pretending to be from the bank.",
    investigator_notes: "Trace request submitted to NPCI. Waiting for beneficiary details.",
    recovery_status: "trace_requested",
    created_by: null,
    created_at: iso(28),
    updated_at: iso(20),
  },
  {
    id: uid(5012),
    case_id: CASE_ID_SECONDARY,
    name: "Farida Sheikh",
    age: 39,
    date_of_birth: null,
    gender: "female",
    classification: "individual",
    phone: "+91-98300-55667",
    email: "farida.sheikh@outlook.com",
    address: "Kolkata, West Bengal",
    incident_date: iso(8, 6),
    incident_type: "Manifest fraud",
    fraud_category: "Import scam",
    description: "Paid advance for goods that were never shipped by Skyline Imports.",
    reported_amount: 320000,
    currency: "INR",
    amount_lost: 320000,
    recovery_amount: 80000,
    digital_accounts: null,
    devices: [],
    wallet_addresses: null,
    status: "recovery_initiated",
    statement: null,
    investigator_notes: "Partial chargeback received on credit card.",
    recovery_status: "partial_recovery",
    created_by: null,
    created_at: iso(8),
    updated_at: iso(5),
  },
];

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
    "evidence.upload", "evidence.delete", "evidence.restore", "ingestion.run", "analytics.run", "findings.read",
    "findings.review", "findings.confirm", "findings.dismiss", "entity.merge", "users.manage", "audit.read",
  ],
  INVESTIGATOR: [
    "case.read", "case.create", "case.update", "case.archive", "evidence.read",
    "evidence.upload", "evidence.delete", "evidence.restore", "ingestion.run", "analytics.run", "findings.read",
    "findings.review", "findings.confirm", "findings.dismiss", "entity.merge", "audit.read",
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

/** Access rule matching the backend: owner, member, or admin (member-aware). */
function assertCaseAccess(caseId: string): Case {
  const caze = casesState.find((c) => c.id === caseId);
  if (!caze) throw notFound("case not found");
  const { record, roles } = currentUser();
  if (!record) throw unauthorized();
  const isAdmin = roles.includes("ADMIN");
  if (!isAdmin && caze.owner_id !== record.id) {
    const isMember = (membersState[caseId] ?? []).some((m) => m.user_id === record.id);
    if (!isMember) {
      throw new ApiError({ status: 403, code: "FORBIDDEN", message: "You do not have access to this case" });
    }
  }
  return caze;
}

/** Backend mirror: only the case owner or an admin may manage membership. */
function requireOwnerOrAdmin(caseId: string): void {
  const caze = assertCaseAccess(caseId);
  const { roles, record } = currentUser();
  const isAdmin = roles.includes("ADMIN");
  if (!isAdmin && caze.owner_id !== record?.id) {
    throw new ApiError({ status: 403, code: "FORBIDDEN", message: "Only the case owner or an admin can manage members" });
  }
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

/**
 * Restore the in-memory state to its deterministic seed data (and drop any
 * active session) so tests can run independently without cross-test leakage.
 */
export function resetMockState(): void {
  casesState.length = 0;
  casesState.push(...MOCK_CASES);
  evidenceState.length = 0;
  evidenceState.push(...MAIN_EVIDENCE);
  findingsState.length = 0;
  findingsState.push(...MAIN_FINDINGS);
  jobsState.length = 0;
  jobsState.push(...MAIN_JOBS);
  for (const k of Object.keys(membersState)) delete membersState[k];
  Object.assign(membersState, seedMembers());
  auditState.length = 0;
  auditState.push(...MAIN_AUDIT);
  registeredState.length = 0;
  collectionsState.length = 0;
  collectionsState.push(...MAIN_COLLECTIONS);
  devicesState.length = 0;
  devicesState.push(...MAIN_DEVICES);
  reportsState.length = 0;
  reportsState.push(...MAIN_REPORTS);
  hypothesesState.length = 0;
  hypothesesState.push(...MAIN_REGISTERED_HYPOTHESES);
  timelineState.length = 0;
  timelineState.push(...MAIN_TIMELINE_EVENTS);
  recycleState.length = 0;
  currentUserId = null;
  currentRoles = [];
  authSession.clear();
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
      if (user.status === "PENDING") {
        throw new ApiError({ status: 403, code: "ACCOUNT_PENDING", message: "account is pending administrator approval" });
      }
      if (user.status === "SUSPENDED") {
        throw new ApiError({ status: 403, code: "ACCOUNT_SUSPENDED", message: "account is suspended" });
      }
      if (user.status === "REJECTED") {
        throw new ApiError({ status: 403, code: "ACCOUNT_REJECTED", message: "account was rejected" });
      }
      currentUserId = user.id;
      currentRoles = user.roles;
      authSession.setPermissions(resolvedPermissions(user.roles));
      pushAudit("auth.login_succeeded", "user", null, { expires_in_minutes: 30 });
      return {
        access_token: `mock-token-${user.id}`,
        token_type: "bearer",
        expires_in: 1800,
        user: { id: user.id, username: user.username, email: user.email, status: user.status, is_active: active(user) },
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
        user: { id: record.id, username: record.username, email: record.email, status: record.status, is_active: active(record) },
        roles: roleList,
        permissions,
      };
    },

    async register(input: RegisterInput): Promise<RegisteredUserOut> {
      await delay(MOCK_LATENCY);
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
        status: "PENDING",
        roles: [],
        created_at: iso(0),
      };
      registeredState.push(record);
      pushAudit("auth.registration_requested", "user", null, { username: input.username });
      return {
        user: { id: record.id, username: record.username, email: record.email, status: "PENDING", is_active: false },
        roles: [],
        created_at: record.created_at,
      };
    },

    async logout() {
      await delay(MOCK_LATENCY / 2);
      if (!currentUser().record) throw unauthorized();
      pushAudit("auth.logged_out", "user", null, {});
      currentUserId = null;
      currentRoles = [];
      authSession.setPermissions([]);
    },
  },

  users: {
    async list(params: AdminUserListParams = {}) {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      let items = [...MOCK_USERS, ...registeredState];
      if (params.status) items = items.filter((u) => u.status === params.status);
      if (params.search) {
        const q = params.search.toLowerCase();
        items = items.filter(
          (u) => u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
        );
      }
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const sorted = [...items].sort((a, b) => a.username.localeCompare(b.username));
      const page = sorted.slice(offset, offset + limit);
      return { items: page.map((u) => adminUserOut(u, userStamp(u.id))), total: sorted.length, limit, offset };
    },

    async listPending(params: AdminUserListParams = {}) {
      await delay(MOCK_LATENCY / 2);
      requirePermission("users.manage");
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const pending = [...registeredState]
        .filter((u) => u.status === "PENDING")
        .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
      return { items: pending.slice(offset, offset + limit).map((u) => adminUserOut(u, u.created_at ?? "")), total: pending.length, limit, offset };
    },

    async get(userId: string): Promise<AdminUserOut> {
      await delay(MOCK_LATENCY / 2);
      requirePermission("users.manage");
      return adminUserOut(findUser(userId), userStamp(userId));
    },

    async approve(userId: string, role: string): Promise<AdminUserOut> {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      const user = findUser(userId);
      const current = user.status;
      if (current === "ACTIVE") {
        throw new ApiError({ status: 409, code: "CONFLICT", message: "account is already active" });
      }
      user.status = "ACTIVE";
      user.roles = [role as MockUserRecord["roles"][number]];
      pushAudit("user.approved", "user", null, { user_id: userId, role });
      return adminUserOut(user, userStamp(userId));
    },

    async reject(userId: string): Promise<AdminUserOut> {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      const user = findUser(userId);
      if (user.status === "REJECTED") {
        throw new ApiError({ status: 409, code: "CONFLICT", message: "account is already rejected" });
      }
      if (user.status === "ACTIVE" && user.roles.includes("ADMIN")) {
        throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "cannot reject an active administrator" });
      }
      user.status = "REJECTED";
      pushAudit("user.rejected", "user", null, { user_id: userId });
      return adminUserOut(user, userStamp(userId));
    },

    async suspend(userId: string): Promise<AdminUserOut> {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      const user = findUser(userId);
      if (user.roles.includes("ADMIN") && user.status === "ACTIVE") {
        throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "cannot suspend an active administrator" });
      }
      user.status = "SUSPENDED";
      pushAudit("user.suspended", "user", null, { user_id: userId });
      return adminUserOut(user, userStamp(userId));
    },

    async activate(userId: string): Promise<AdminUserOut> {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      const user = findUser(userId);
      user.status = "ACTIVE";
      pushAudit("user.activated", "user", null, { user_id: userId });
      return adminUserOut(user, userStamp(userId));
    },

    async changeRole(userId: string, role: string): Promise<AdminUserOut> {
      await delay(MOCK_LATENCY);
      requirePermission("users.manage");
      const user = findUser(userId);
      user.roles = [role as MockUserRecord["roles"][number]];
      pushAudit("user.role_changed", "user", null, { user_id: userId, role });
      return adminUserOut(user, userStamp(userId));
    },
  },

  cases: {
    async list(params: CaseListParams = {}) {
      await delay(MOCK_LATENCY);
      const user = requireAuth();
      const isAdmin = user.roles.includes("ADMIN");
      let items = casesState.filter(
        (c) =>
          isAdmin ||
          c.owner_id === user.id ||
          (membersState[c.id] ?? []).some((m) => m.user_id === user.id),
      );
      if (params.search) {
        const q = params.search.toLowerCase();
        items = items.filter(
          (c) => c.title.toLowerCase().includes(q) || c.case_number.toLowerCase().includes(q),
        );
      }
      if (params.status) items = items.filter((c) => c.status === params.status);
      const start = params.offset ?? 0;
      const limit = params.limit ?? 100;
      const end = start + limit;
      return { items: items.slice(start, end), total: items.length, limit, offset: start };
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

    async listMembers(caseId: string): Promise<CaseMemberListResponse> {
      await delay(MOCK_LATENCY / 2);
      requirePermission("case.read");
      assertCaseAccess(caseId);
      return { items: [...(membersState[caseId] ?? [])], case_id: caseId };
    },

    async addMember(caseId: string, input: CaseMemberAddRequest): Promise<CaseMemberListResponse> {
      await delay(MOCK_LATENCY);
      requirePermission("case.update");
      requireOwnerOrAdmin(caseId);
      const rows = (membersState[caseId] ??= []);
      if (rows.some((m) => m.user_id === input.user_id)) {
        throw new ApiError({ status: 409, code: "CONFLICT", message: "user is already a member of this case" });
      }
      const known = MOCK_USERS.some((u) => u.id === input.user_id) || registeredState.some((u) => u.id === input.user_id);
      if (!known) throw notFound(`user ${input.user_id} not found`);
      rows.push({ user_id: input.user_id, role: input.role, created_at: new Date().toISOString() });
      pushAudit("case.member_added", "case", caseId, { member_id: input.user_id, role: input.role, member_count: rows.length });
      return { items: [...rows], case_id: caseId };
    },

    async removeMember(caseId: string, userId: string): Promise<CaseMemberListResponse> {
      await delay(MOCK_LATENCY);
      requirePermission("case.update");
      requireOwnerOrAdmin(caseId);
      const rows = membersState[caseId] ?? [];
      const idx = rows.findIndex((m) => m.user_id === userId);
      if (idx === -1) throw notFound("member not found");
      const [removed] = rows.splice(idx, 1);
      pushAudit("case.member_removed", "case", caseId, { member_id: userId, role: removed.role });
      return { items: [...rows], case_id: caseId };
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

    async reviewResolution(caseId: string): Promise<ReviewList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      if (caseId === CASE_ID_MAIN) {
        const items = [
          {
            match_id: "a1000000-0000-4000-8000-000000000001",
            candidate_id: "a2000000-0000-4000-8000-000000000002",
            candidate_value: "Rajesh Kumar",
            candidate_type: "person",
            target_entity_id: "a3000000-0000-4000-8000-000000000003",
            target_value: "Rajesh Kumar",
            score: 0.97,
            decision: "auto_match" as const,
            signals: { name_overlap: 1.0, phone_overlap: 1.0 },
            created_at: new Date(Date.now() - 86_400_000).toISOString(),
          },
          {
            match_id: "a1000000-0000-4000-8000-000000000004",
            candidate_id: "a2000000-0000-4000-8000-000000000005",
            candidate_value: "Arjun Mehta",
            candidate_type: "person",
            target_entity_id: null,
            target_value: null,
            score: 0.62,
            decision: "review" as const,
            signals: { name_partial: 1.0 },
            created_at: new Date(Date.now() - 43_200_000).toISOString(),
          },
        ];
        return { items, total: items.length };
      }
      return { items: [], total: 0 };
    },

    async acceptMatch(caseId: string, matchId: string): Promise<ReviewDecisionResponse> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("findings.review");
      assertCaseAccess(caseId);
      if (caseId !== CASE_ID_MAIN) throw notFound("match not found");
      const known = ["a1000000-0000-4000-8000-000000000001", "a1000000-0000-4000-8000-000000000004"];
      if (!known.includes(matchId)) throw notFound("match not found");
      pushAudit("match.accepted", "entity_match", caseId, { score: 0.9 });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: new Date().toISOString(),
        kind: "match_accepted",
        title: `Resolution accepted for match ${matchId.slice(0, 8)}`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: new Date().toISOString(),
      });
      return { match_id: matchId, status: "accepted" };
    },

    async rejectMatch(caseId: string, matchId: string): Promise<ReviewDecisionResponse> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("findings.review");
      assertCaseAccess(caseId);
      if (caseId !== CASE_ID_MAIN) throw notFound("match not found");
      const known = ["a1000000-0000-4000-8000-000000000001", "a1000000-0000-4000-8000-000000000004"];
      if (!known.includes(matchId)) throw notFound("match not found");
      pushAudit("match.rejected", "entity_match", caseId, { score: 0.62 });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: new Date().toISOString(),
        kind: "match_rejected",
        title: `Resolution rejected for match ${matchId.slice(0, 8)}`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: new Date().toISOString(),
      });
      return { match_id: matchId, status: "rejected" };
    },

    async mergeEntities(caseId: string, input: EntityMergeRequest): Promise<EntityDetail> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("entity.merge");
      assertCaseAccess(caseId);
      const entities = entitiesFor(caseId);
      const primary = entities.find((e) => e.id === input.primary_entity_id);
      if (!primary) throw notFound("primary entity not found");
      const duplicate = entities.find((e) => e.id === input.merge_entity_id);
      if (!duplicate) throw notFound("merge entity not found");
      if (input.primary_entity_id === input.merge_entity_id) {
        throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "cannot merge an entity into itself" });
      }
      pushAudit("entity.merged", "entity", caseId, {
        primary_id: input.primary_entity_id,
        merge_id: input.merge_entity_id,
      });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: new Date().toISOString(),
        kind: "entity_merged",
        title: `Entity '${primary.display_value}' merged with '${duplicate.display_value}'`,
        description: null,
        entity_id: primary.id,
        evidence_file_id: null,
        collection_id: null,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: new Date().toISOString(),
      });
      const detail = MAIN_ENTITY_DETAILS[primary.display_value] ?? MAIN_ENTITY_DETAILS[primary.canonical_value];
      return {
        ...primary,
        status: "active",
        aliases: detail?.aliases ?? [],
        context: detail?.context ?? null,
      };
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
        source_field_device_id: item.source_field_device_id ?? null,
        created_at: item.created_at,
      };
    },

    async upload(caseId: string, file: UploadFile, _dataSource = "csv", _options?: { collectionId?: string }) {
      void _dataSource;
      await delay(MOCK_LATENCY * 2);
      requirePermission("evidence.upload");
      assertCaseAccess(caseId);
      const collectionName = _options?.collectionId
        ? collectionsState.find((c) => c.id === _options.collectionId && c.case_id === caseId)?.name
        : undefined;
      if (_options?.collectionId && !collectionName) {
        throw new ApiError({ status: 404, code: "NOT_FOUND", message: "collection not found" });
      }
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
        status: "stored",
        status_detail: null,
        source_field_device_id: null,
        created_at: created,
      };
      evidenceState.push({
        id,
        original_filename: file.name,
        sha256: item.sha256,
        format: item.format,
        file_size: file.size,
        status: "stored",
        record_count: null,
        source_field_device_id: null,
        created_at: created,
      });
      pushAudit("evidence.uploaded", "evidence_file", caseId, {
        filename: file.name,
        format: item.format,
        ...(collectionName ? { collection: collectionName } : {}),
      });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: created,
        kind: "evidence_uploaded",
        title: `Evidence '${file.name}' uploaded`,
        description: null,
        entity_id: null,
        evidence_file_id: id,
        collection_id: _options?.collectionId ?? null,
        device_id: null,
        actor_user_id: currentUser().record?.id ?? null,
        payload: { format: item.format },
        created_at: created,
      });
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
      // Mirrors the backend lifecycle: a completed ingestion leaves the
      // evidence file in the "parsed" state (stored -> processing -> parsed).
      item.status = "parsed";
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

    async delete(caseId: string, evidenceId: string): Promise<void> {
      await delay(MOCK_LATENCY);
      requirePermission("evidence.delete");
      assertCaseAccess(caseId);
      const idx = evidenceState.findIndex((e) => e.id === evidenceId);
      if (idx === -1) throw notFound("evidence not found");
      const [item] = evidenceState.splice(idx, 1);
      // Backend mirror: deletion moves the record to the recycle bin so a
      // restore can bring both the metadata and the content back.
      recycleState.push({ ...item, case_id: caseId });
      pushAudit("evidence.deleted", "evidence_file", caseId, { filename: item.original_filename });
    },

    async restore(caseId: string, evidenceId: string): Promise<EvidenceRestoreResponse> {
      await delay(MOCK_LATENCY);
      requirePermission("evidence.restore");
      assertCaseAccess(caseId);
      const idx = recycleState.findIndex((e) => e.id === evidenceId);
      if (idx === -1) throw notFound("evidence not in the recycle bin");
      const [item] = recycleState.splice(idx, 1);
      if (item.case_id !== caseId) throw notFound("evidence not in the recycle bin");
      evidenceState.push({ ...item });
      pushAudit("evidence.restored", "evidence_file", caseId, {
        filename: item.original_filename,
        content_restored: true,
      });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: new Date().toISOString(),
        kind: "evidence_restored",
        title: `Evidence '${item.original_filename}' restored`,
        description: null,
        entity_id: null,
        evidence_file_id: item.id,
        collection_id: null,
        device_id: null,
        actor_user_id: currentUser().record?.id ?? null,
        payload: { content_restored: true },
        created_at: new Date().toISOString(),
      });
      return {
        id: item.id,
        case_id: caseId,
        original_filename: item.original_filename,
        restored: true,
        content_restored: true,
      };
    },

    async retryGraphSync(caseId: string, jobId: string): Promise<GraphSyncResult> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const candidates =
        caseId === CASE_ID_MAIN ? jobsState : caseId === CASE_ID_SECONDARY ? SECONDARY_CASE_DATA.jobsList : [];
      const job = candidates.find((j) => j.id === jobId);
      // IDOR guard: the job must belong to *this* case.
      if (!job || job.case_id !== caseId) throw notFound(`job ${jobId} not found`);
      job.graph_sync_status = "synced";
      job.graph_error = null;
      job.updated_at = new Date().toISOString();
      pushAudit("ingestion.graph_sync_retried", "ingestion_job", caseId, {
        nodes_synced: 14,
        edges_synced: 18,
      });
      return {
        job_id: job.id,
        graph_sync_status: "synced",
        nodes_synced: 14,
        edges_synced: 18,
        error: null,
      };
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

  victims: {
    async list(caseId: string, params: VictimListParams = {}): Promise<VictimList> {
      await delay(MOCK_LATENCY);
      let items = [...victimState].filter((v) => v.case_id === caseId);
      if (params.status) items = items.filter((v) => v.status === params.status);
      if (params.search) {
        const q = params.search.toLowerCase();
        items = items.filter((v) => v.name.toLowerCase().includes(q));
      }
      items.sort((a, b) => b.created_at.localeCompare(a.created_at));
      const total = items.length;
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total, limit, offset };
    },
    async get(caseId: string, victimId: string): Promise<Victim> {
      await delay(MOCK_LATENCY);
      const v = victimState.find((x) => x.id === victimId && x.case_id === caseId);
      if (!v) throw notFound("victim not found");
      return v;
    },
    async create(caseId: string, input: VictimCreateRequest): Promise<Victim> {
      await delay(MOCK_LATENCY);
      const now = iso(Date.now());
      const victim: Victim = {
        id: uid(5000 + victimState.length),
        case_id: caseId,
        name: input.name,
        age: input.age ?? null,
        date_of_birth: input.date_of_birth ?? null,
        gender: input.gender ?? null,
        classification: input.classification ?? "individual",
        phone: input.phone ?? null,
        email: input.email ?? null,
        address: input.address ?? null,
        incident_date: input.incident_date ?? null,
        incident_type: input.incident_type ?? null,
        fraud_category: input.fraud_category ?? null,
        description: input.description ?? null,
        reported_amount: input.reported_amount ?? null,
        currency: input.currency ?? null,
        amount_lost: input.amount_lost ?? null,
        recovery_amount: input.recovery_amount ?? null,
        digital_accounts: input.digital_accounts ?? null,
        devices: input.devices ?? null,
        wallet_addresses: input.wallet_addresses ?? null,
        status: input.status ?? "reported",
        statement: input.statement ?? null,
        investigator_notes: input.investigator_notes ?? null,
        recovery_status: input.recovery_status ?? null,
        created_by: currentUserId,
        created_at: now,
        updated_at: now,
      };
      victimState.push(victim);
      pushAudit("victim.created", "victim", victim.id, { case_id: caseId, name: victim.name });
      return victim;
    },
    async update(caseId: string, victimId: string, input: VictimUpdateRequest): Promise<Victim> {
      await delay(MOCK_LATENCY);
      const idx = victimState.findIndex((x) => x.id === victimId && x.case_id === caseId);
      if (idx === -1) throw notFound("victim not found");
      const v = victimState[idx];
      for (const [k, val] of Object.entries(input)) {
        if (val !== undefined) (v as unknown as Record<string, unknown>)[k] = val;
      }
      v.updated_at = iso(Date.now());
      pushAudit("victim.updated", "victim", v.id, { case_id: caseId, fields: Object.keys(input) });
      return v;
    },
    async delete(caseId: string, victimId: string): Promise<void> {
      await delay(MOCK_LATENCY);
      const idx = victimState.findIndex((x) => x.id === victimId && x.case_id === caseId);
      if (idx === -1) throw notFound("victim not found");
      const v = victimState[idx];
      victimState.splice(idx, 1);
      pushAudit("victim.deleted", "victim", v.id, { case_id: caseId, name: v.name });
    },
  },

  iot: {
    async devices(caseId: string, params: IoTDeviceListParams = {}): Promise<IoTDeviceList> {
      await delay(MOCK_LATENCY);
      let items = [...iotDeviceState].filter((d) => d.case_id === caseId);
      if (params.status) items = items.filter((d) => d.status === params.status);
      if (params.device_type) items = items.filter((d) => d.device_type === params.device_type);
      if (params.search) {
        const q = params.search.toLowerCase();
        items = items.filter((d) => d.name.toLowerCase().includes(q) || d.serial_number.toLowerCase().includes(q));
      }
      items.sort((a, b) => b.created_at.localeCompare(a.created_at));
      const total = items.length;
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total, limit, offset };
    },
    async device(caseId: string, deviceId: string): Promise<IoTDevice> {
      await delay(MOCK_LATENCY);
      const d = iotDeviceState.find((x) => x.id === deviceId && x.case_id === caseId);
      if (!d) throw notFound("iot device not found");
      return d;
    },
    async register(caseId: string, input: IoTDeviceCreateRequest): Promise<IoTDevice> {
      await delay(MOCK_LATENCY);
      const now = iso(Date.now());
      if (iotDeviceState.some((d) => d.case_id === caseId && d.serial_number === input.serial_number)) {
        throw new ApiError({ status: 409, code: "CONFLICT", message: "a device with this serial number is already registered" });
      }
      const device: IoTDevice = {
        id: uid(6000 + iotDeviceState.length),
        case_id: caseId,
        name: input.name,
        device_type: input.device_type ?? "mobile",
        make: input.make ?? null,
        model: input.model ?? null,
        serial_number: input.serial_number,
        imei: input.imei ?? null,
        ip_address: input.ip_address ?? null,
        mac_address: input.mac_address ?? null,
        os: input.os ?? null,
        os_version: input.os_version ?? null,
        owner_name: input.owner_name ?? null,
        owner_phone: input.owner_phone ?? null,
        status: "registered",
        description: input.description ?? null,
        firmware_version: input.firmware_version ?? null,
        first_seen_at: input.first_seen_at ?? null,
        last_seen_at: input.last_seen_at ?? null,
        metadata_json: input.metadata_json ?? null,
        event_count: 0,
        created_at: now,
        updated_at: now,
      };
      iotDeviceState.push(device);
      pushAudit("iot.device_registered", "iot_device", device.id, { case_id: caseId, name: device.name });
      return device;
    },
    async updateDevice(caseId: string, deviceId: string, input: IoTDeviceUpdateRequest): Promise<IoTDevice> {
      await delay(MOCK_LATENCY);
      const idx = iotDeviceState.findIndex((x) => x.id === deviceId && x.case_id === caseId);
      if (idx === -1) throw notFound("iot device not found");
      const d = iotDeviceState[idx];
      for (const [k, val] of Object.entries(input)) {
        if (val !== undefined) (d as unknown as Record<string, unknown>)[k] = val;
      }
      d.updated_at = iso(Date.now());
      pushAudit("iot.device_updated", "iot_device", d.id, { case_id: caseId, fields: Object.keys(input) });
      return d;
    },
    async deleteDevice(caseId: string, deviceId: string): Promise<void> {
      await delay(MOCK_LATENCY);
      const idx = iotDeviceState.findIndex((x) => x.id === deviceId && x.case_id === caseId);
      if (idx === -1) throw notFound("iot device not found");
      const d = iotDeviceState[idx];
      iotDeviceState.splice(idx, 1);
      iotEventState = iotEventState.filter((e) => e.device_id !== deviceId);
      pushAudit("iot.device_removed", "iot_device", d.id, { case_id: caseId, name: d.name });
    },
    async deviceStats(caseId: string, deviceId: string): Promise<IoTDeviceStats> {
      await delay(MOCK_LATENCY);
      const events = iotEventState.filter((e) => e.case_id === caseId && e.device_id === deviceId);
      const by_type: Record<string, number> = {};
      for (const e of events) by_type[e.event_type] = (by_type[e.event_type] ?? 0) + 1;
      const times = events.map((e) => e.event_time).sort();
      return {
        device_id: deviceId,
        event_count: events.length,
        by_type,
        first_event_at: times[0] ?? null,
        last_event_at: times[times.length - 1] ?? null,
      };
    },
    async events(caseId: string, params: IoTEventListParams = {}): Promise<IoTEventList> {
      await delay(MOCK_LATENCY);
      let items = iotEventState.filter((e) => e.case_id === caseId);
      if (params.device_id) items = items.filter((e) => e.device_id === params.device_id);
      if (params.event_type) items = items.filter((e) => e.event_type === params.event_type);
      items.sort((a, b) => b.event_time.localeCompare(a.event_time));
      const total = items.length;
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total, limit, offset };
    },
    async recordEvent(caseId: string, input: IoTEventCreateRequest): Promise<IoTEvent> {
      await delay(MOCK_LATENCY);
      const device = iotDeviceState.find((d) => d.id === input.device_id && d.case_id === caseId);
      if (!device) throw notFound("iot device not found");
      const now = iso(Date.now());
      const event: IoTEvent = {
        id: uid(7000 + iotEventState.length),
        case_id: caseId,
        device_id: input.device_id,
        event_type: input.event_type,
        event_time: input.event_time,
        source: input.source ?? null,
        payload: input.payload ?? null,
        latitude: input.latitude ?? null,
        longitude: input.longitude ?? null,
        location_label: input.location_label ?? null,
        confidence: input.confidence ?? null,
        description: input.description ?? null,
        created_at: now,
      };
      iotEventState.push(event);
      if (!device.last_seen_at || event.event_time > device.last_seen_at) {
        device.last_seen_at = event.event_time;
      }
      device.event_count += 1;
      pushAudit("iot.event_recorded", "iot_event", event.id, { case_id: caseId, device_id: event.device_id, event_type: event.event_type });
      return event;
    },
  },

  timeline: {
    async events(caseId: string, params = {}): Promise<TimelineEventList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = [...timelineState].filter((e) => e.case_id === caseId);
      if (params.kind) items = items.filter((e) => e.kind === params.kind);
      items.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
      const limit = params.limit ?? 200;
      return { items: items.slice(0, limit), total: items.length, limit, offset: 0 };
    },

    async create(caseId: string, input) {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.update");
      assertCaseAccess(caseId);
      const created = new Date().toISOString();
      const event: TimelineEvent = {
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: input.occurred_at,
        kind: input.kind,
        title: input.title,
        description: input.description ?? null,
        entity_id: input.entity_id ?? null,
        evidence_file_id: input.evidence_file_id ?? null,
        collection_id: input.collection_id ?? null,
        device_id: input.device_id ?? null,
        actor_user_id: user?.id ?? null,
        payload: input.payload ?? null,
        created_at: created,
      };
      timelineState.unshift(event);
      pushAudit("timeline.event_recorded", "timeline_event", caseId, { kind: event.kind, title: event.title });
      return event;
    },
  },

  collections: {
    async list(caseId: string, params: CollectionListParams = {}): Promise<CollectionList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = collectionsState.filter((c) => c.case_id === caseId);
      if (params.status) items = items.filter((c) => c.status === params.status);
      items.sort((a, b) => b.created_at.localeCompare(a.created_at));
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async get(caseId: string, collectionId: string): Promise<Collection> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const c = collectionsState.find((x) => x.id === collectionId && x.case_id === caseId);
      if (!c) throw notFound("collection not found");
      return c;
    },

    async create(caseId: string, input): Promise<Collection> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.update");
      assertCaseAccess(caseId);
      const now = new Date().toISOString();
      const created: Collection = {
        id: uid(2400 + collectionsState.length),
        case_id: caseId,
        name: input.name,
        description: input.description ?? null,
        status: "open",
        sealed_at: null,
        created_at: now,
        updated_at: now,
      };
      collectionsState.push(created);
      pushAudit("collection.created", "collection", caseId, { name: created.name });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: now,
        kind: "collection_created",
        title: `Collection '${created.name}' created`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: created.id,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: now,
      });
      return created;
    },

    async update(caseId: string, collectionId: string, input: CollectionUpdateRequest): Promise<Collection> {
      await delay(MOCK_LATENCY);
      requirePermission("case.update");
      assertCaseAccess(caseId);
      const c = collectionsState.find((x) => x.id === collectionId && x.case_id === caseId);
      if (!c) throw notFound("collection not found");
      if (c.status === "sealed") {
        throw new ApiError({ status: 409, code: "CONFLICT", message: "sealed collections cannot be modified" });
      }
      if (input.name !== undefined && input.name !== null) c.name = input.name;
      if (input.description !== undefined && input.description !== null) c.description = input.description;
      c.updated_at = new Date().toISOString();
      return c;
    },

    async seal(caseId: string, collectionId: string): Promise<Collection> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.update");
      assertCaseAccess(caseId);
      const c = collectionsState.find((x) => x.id === collectionId && x.case_id === caseId);
      if (!c) throw notFound("collection not found");
      if (c.status === "sealed") return c;
      c.status = "sealed";
      c.sealed_at = new Date().toISOString();
      c.updated_at = c.sealed_at;
      pushAudit("collection.sealed", "collection", caseId, { name: c.name });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: c.sealed_at,
        kind: "collection_sealed",
        title: `Collection '${c.name}' sealed`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: c.id,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: c.sealed_at,
      });
      return c;
    },

    async delete(caseId: string, collectionId: string): Promise<void> {
      await delay(MOCK_LATENCY);
      requirePermission("case.update");
      assertCaseAccess(caseId);
      const idx = collectionsState.findIndex((x) => x.id === collectionId && x.case_id === caseId);
      if (idx === -1) throw notFound("collection not found");
      const [c] = collectionsState.splice(idx, 1);
      pushAudit("collection.deleted", "collection", caseId, { name: c.name });
    },
  },

  fieldDevices: {
    async list(caseId: string, params: DeviceListParams = {}): Promise<DeviceList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = devicesState.filter((d) => d.case_id === caseId);
      if (params.status) items = items.filter((d) => d.status === params.status);
      items.sort((a, b) => b.created_at.localeCompare(a.created_at));
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async register(caseId: string, input): Promise<FieldDevice> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.update");
      assertCaseAccess(caseId);
      const now = new Date().toISOString();
      const device: FieldDevice = {
        id: uid(2500 + devicesState.length),
        case_id: caseId,
        platform: input.platform,
        serial: input.serial,
        model: input.model ?? null,
        firmware_version: input.firmware_version ?? null,
        signature_algorithm: input.signature_algorithm ?? "RSA-SHA256",
        status: "pending",
        approved_by: null,
        last_seen_at: null,
        created_at: now,
      };
      devicesState.push(device);
      pushAudit("device.registered", "field_device", caseId, { serial: device.serial, platform: device.platform });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: now,
        kind: "device_registered",
        title: `Device '${device.serial}' registered`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: device.id,
        actor_user_id: user.id,
        payload: { platform: device.platform },
        created_at: now,
      });
      return device;
    },

    async approve(caseId: string, deviceId: string): Promise<FieldDevice> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("users.manage");
      assertCaseAccess(caseId);
      const d = devicesState.find((x) => x.id === deviceId && x.case_id === caseId);
      if (!d) throw notFound("device not found");
      d.status = "approved";
      d.approved_by = user.id;
      d.last_seen_at = new Date().toISOString();
      pushAudit("device.approved", "field_device", caseId, { serial: d.serial });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: new Date().toISOString(),
        kind: "device_approved",
        title: `Device '${d.serial}' approved`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: d.id,
        actor_user_id: user.id,
        payload: null,
        created_at: new Date().toISOString(),
      });
      return d;
    },

    async revoke(caseId: string, deviceId: string): Promise<FieldDevice> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("users.manage");
      assertCaseAccess(caseId);
      const d = devicesState.find((x) => x.id === deviceId && x.case_id === caseId);
      if (!d) throw notFound("device not found");
      d.status = "revoked";
      d.approved_by = null;
      pushAudit("device.revoked", "field_device", caseId, { serial: d.serial });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: new Date().toISOString(),
        kind: "device_revoked",
        title: `Device '${d.serial}' revoked`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: d.id,
        actor_user_id: user.id,
        payload: null,
        created_at: new Date().toISOString(),
      });
      return d;
    },

    async verifyKey(caseId: string, deviceId: string, input: DeviceVerifyRequest): Promise<DeviceVerifyResponse> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const d = devicesState.find((x) => x.id === deviceId && x.case_id === caseId);
      if (!d) throw notFound("device not found");
      // Deterministic demo answer: approved RSA-SHA256 devices verify when a
      // non-empty signature is presented (parity with the real adapter, which
      // forwards { data, signature } to the backend).
      const hasProof = Boolean(input?.data && input?.signature);
      const valid = d.status === "approved" && d.signature_algorithm === "RSA-SHA256" && hasProof;
      return { valid };
    },
  },

  health: {
    async health(): Promise<HealthResponse> {
      await delay(MOCK_LATENCY);
      return { status: "ok", service: "cybersaarthi", version: "0.1.0" };
    },
  },

  reports: {
    async list(caseId: string, params: ReportListParams = {}): Promise<ReportList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = reportsState.filter((r) => r.case_id === caseId);
      if (params.report_type) items = items.filter((r) => r.report_type === params.report_type);
      items.sort((a, b) => b.created_at.localeCompare(a.created_at));
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async get(caseId: string, reportId: string): Promise<Report> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const r = reportsState.find((x) => x.id === reportId && x.case_id === caseId);
      if (!r) throw notFound("report not found");
      return r;
    },

    async generate(caseId: string, input): Promise<Report> {
      await delay(MOCK_LATENCY * 2);
      assertCaseAccess(caseId);
      const now = new Date().toISOString();
      const known = ["case_summary", "intelligence", "evidence_manifest", "network_analysis"];
      const report: Report = {
        id: uid(2600 + reportsState.length),
        case_id: caseId,
        report_type: input.report_type,
        format: input.format ?? "json",
        title: input.title ?? `${input.report_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())} - Case`,
        status: known.includes(input.report_type) ? "ready" : "failed",
        byte_size: known.includes(input.report_type) ? 24680 : null,
        failure_reason: known.includes(input.report_type) ? null : `unknown report type '${input.report_type}'`,
        created_at: now,
      };
      reportsState.unshift(report);
      pushAudit("report.generated", "report", caseId, {
        report_type: report.report_type,
        format: report.format,
        status: report.status,
      });
      return report;
    },

    async download(caseId: string, reportId: string): Promise<{ blob: Blob; filename: string }> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const r = reportsState.find((x) => x.id === reportId && x.case_id === caseId);
      if (!r) throw notFound("report not found");
      if (r.status !== "ready") {
        throw new ApiError({ status: 409, code: "CONFLICT", message: "report not ready" });
      }
      const blob = new Blob([JSON.stringify({ report_type: r.report_type, case_id: caseId, generated_at: r.created_at }, null, 2)], {
        type: "application/json",
      });
      return { blob, filename: `${r.report_type}-report.json` };
    },
  },

  hypotheses: {
    async list(caseId: string, params: InvestigationHypothesisListParams = {}): Promise<InvestigationHypothesisList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = hypothesesState.filter((h) => h.case_id === caseId);
      if (params.kind) items = items.filter((h) => h.kind === params.kind);
      if (params.status) items = items.filter((h) => h.status === params.status);
      items.sort((a, b) => b.created_at.localeCompare(a.created_at));
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async get(caseId: string, hypothesisId: string): Promise<InvestigationHypothesis> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const h = hypothesesState.find((x) => x.id === hypothesisId && x.case_id === caseId);
      if (!h) throw notFound("hypothesis not found");
      return h;
    },

    async create(caseId: string, input): Promise<InvestigationHypothesis> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("findings.review");
      assertCaseAccess(caseId);
      const now = new Date().toISOString();
      const created: InvestigationHypothesis = {
        id: uid(2700 + hypothesesState.length),
        case_id: caseId,
        kind: input.kind ?? "hypothesis",
        status: "proposed",
        title: input.title,
        statement: input.statement,
        confidence: input.confidence ?? null,
        supporting_evidence: null,
        contradicting_evidence: null,
        related_entities: null,
        related_relationships: null,
        evidence_weight: 0,
        notes: input.notes ?? null,
        submitted_by: user.id,
        created_at: now,
        updated_at: now,
      };
      hypothesesState.unshift(created);
      pushAudit("hypothesis.created", "hypothesis", caseId, { title: created.title, kind: created.kind });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: now,
        kind: "hypothesis_created",
        title: `Hypothesis: ${created.title}`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: now,
      });
      return created;
    },

    async updateStatus(caseId: string, hypothesisId: string, status: string): Promise<InvestigationHypothesis> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("findings.review");
      assertCaseAccess(caseId);
      const h = hypothesesState.find((x) => x.id === hypothesisId && x.case_id === caseId);
      if (!h) throw notFound("hypothesis not found");
      const valid = ["proposed", "under_review", "supported", "contradicted", "dismissed", "concluded"];
      if (!valid.includes(status)) {
        throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: `invalid hypothesis status '${status}'` });
      }
      const oldStatus = h.status;
      h.status = status as InvestigationHypothesis["status"];
      h.updated_at = new Date().toISOString();
      pushAudit("hypothesis.status_changed", "hypothesis", caseId, { old: oldStatus, new: status });
      timelineState.unshift({
        id: uid(3900 + timelineState.length),
        case_id: caseId,
        occurred_at: h.updated_at,
        kind: "hypothesis_status_changed",
        title: `Hypothesis '${h.title}' status: ${oldStatus} -> ${status}`,
        description: null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: null,
        actor_user_id: user.id,
        payload: null,
        created_at: h.updated_at,
      });
      return h;
    },

    async linkEvidence(caseId: string, hypothesisId: string, input): Promise<InvestigationHypothesis> {
      await delay(MOCK_LATENCY);
      requirePermission("findings.review");
      assertCaseAccess(caseId);
      const h = hypothesesState.find((x) => x.id === hypothesisId && x.case_id === caseId);
      if (!h) throw notFound("hypothesis not found");
      const target = input.support ? "supporting_evidence" : "contradicting_evidence";
      const list = h[target] ?? [];
      if (!list.includes(input.evidence_id)) {
        h[target] = [...list, input.evidence_id];
        h.evidence_weight += input.support ? 1 : -1;
      }
      h.updated_at = new Date().toISOString();
      return h;
    },

    async delete(caseId: string, hypothesisId: string): Promise<void> {
      await delay(MOCK_LATENCY);
      requirePermission("findings.dismiss");
      assertCaseAccess(caseId);
      const idx = hypothesesState.findIndex((x) => x.id === hypothesisId && x.case_id === caseId);
      if (idx === -1) throw notFound("hypothesis not found");
      hypothesesState.splice(idx, 1);
    },
  },

  search: {
    async search(caseId: string, params: SearchParams): Promise<SearchResponse> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const q = params.q.toLowerCase();
      const results: SearchResponse["items"] = [];
      if (caseId === CASE_ID_MAIN) {
        for (const e of MAIN_ENTITIES) {
          if (e.display_value.toLowerCase().includes(q)) {
            results.push({ kind: "entity", id: e.id, title: e.display_value, subtitle: e.entity_type, url: `/app/cases/${caseId}/entities/${e.id}` });
          }
        }
        for (const item of evidenceState) {
          if (item.original_filename.toLowerCase().includes(q)) {
            results.push({ kind: "evidence", id: item.id, title: item.original_filename, subtitle: item.format ?? null, url: `/app/cases/${caseId}/evidence` });
          }
        }
        for (const f of MAIN_FINDINGS) {
          if (f.title.toLowerCase().includes(q)) {
            results.push({ kind: "finding", id: f.id, title: f.title, subtitle: f.finding_type, url: `/app/cases/${caseId}/findings/${f.id}` });
          }
        }
      }
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      return { items: results.slice(offset, offset + limit), total: results.length, limit, offset };
    },
  },

  importPackages: {
    async submitPackage(caseId: string, payload): Promise<ImportAccepted> {
      await delay(MOCK_LATENCY * 3);
      const user = requirePermission("evidence.upload");
      assertCaseAccess(caseId);
      const device = devicesState.find((d) => d.status === "approved" && d.case_id === caseId);
      const now = new Date().toISOString();
      const fileCount = Math.max(1, payload.files.length);
      const ids = Array.from({ length: fileCount }, (_, i) => uid(5700 + evidenceState.length + i));
      const filenames = payload.files.map((f: File) => f.name) as string[];
      ids.forEach((id, i) => {
        const filename = filenames[i] ?? `collection_evidence_${id.slice(-6)}.bin`;
        evidenceState.push({
          id,
          original_filename: filename,
          sha256: `${id.replace(/-/g, "").slice(0, 56)}0000`,
          format: "txt",
          file_size: 128,
          status: "stored",
          record_count: null,
          source_field_device_id: device?.id ?? null,
          created_at: now,
        });
        timelineState.unshift({
          id: uid(3900 + timelineState.length),
          case_id: caseId,
          occurred_at: now,
          kind: "evidence_uploaded",
          title: `Field evidence '${filename}' imported from device '${device?.serial ?? "unknown"}'`,
          description: "Package collection · per-file SHA-256 verified",
          entity_id: null,
          evidence_file_id: id,
          collection_id: null,
          device_id: device?.id ?? null,
          actor_user_id: user.id,
          payload: null,
          created_at: now,
        });
      });
      pushAudit("import.package_accepted", "import_package", caseId, {
        device_serial: device?.serial ?? null,
        evidence_count: ids.length,
      });
      return {
        case_id: caseId,
        device_serial: device?.serial ?? "andromeda-0001",
        imported_evidence_count: ids.length,
        evidence_ids: ids,
        collection_name: "Field collection (imported)",
      };
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

function userStamp(userId: string): string {
  const record = [...MOCK_USERS, ...registeredState].find((u) => u.id === userId);
  const stamp = record === undefined ? undefined : (record as { created_at?: string }).created_at;
  return stamp ? stamp : iso(0);
}

function findUser(userId: string): MockUserRecord & { created_at?: string } {
  const record = [...MOCK_USERS, ...registeredState].find((u) => u.id === userId);
  if (!record) throw notFound("user not found");
  return record;
}

function adminUserOut(
  user: MockUserRecord & { created_at?: string },
  created: string,
): AdminUserOut {
  return {
    id: user.id,
    username: user.username,
    email: user.email,
    status: user.status,
    is_active: active(user),
    roles: user.roles,
    created_at: created,
    updated_at: created,
  };
}