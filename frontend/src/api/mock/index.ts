import type {
  Api,
  AdminUserListParams,
  AiChatInput,
  AiChatResult,
  AiConversation,
  AiMessage,
  AiReportDraft,
  AiSource,
  AiStatus,
  AiStreamCallbacks,
  AuditParams,
  CaseListParams,
  CollectionListParams,
  DeviceListParams,
  EntityListParams,
  FindingListParams,
  InvestigationHypothesisListParams,
  LoginInput,
  PageParams,
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
import { ApiError, type ApiErrorCode } from "@/types/api";
import type {
  AdminUserOut,
  AnalysisJobList,
  AnalysisJobOut,
  AnalyticsRun,
  ArtifactList,
  ArtifactReviewRequest,
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
  ContradictionResolveRequest,
  CrossCaseCandidateListResponse,
  CrossCaseCandidatePayload,
  CrossCaseDiscoverInput,
  CustodyChronologyResponse,
  CustodyEventCreateRequest,
  CustodyEventOut,
  CustodyExplainResponse,
  DerivedArtifactOut,
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
  FlowTraceHop,
  FlowTracePath,
  FlowTraceRequest,
  FlowTraceResponse,
  GraphStats,
  GraphResponse,
  GraphSyncResult,
  HealthResponse,
  ImportAccepted,
  IngestAccepted,
  IngestionJob,
  IngestJobList,
  IntegrityVerificationResponse,
  InvestigationHypothesis,
  InvestigationHypothesisList,
  JobSubmitResponse,
  NetworkProfile,
  RelationshipStrength,
  Report,
  ReportAuditDetailOut,
  ReportAuditList,
  ReportAuditOut,
  ReportAuditSubmitInput,
  ReportList,
  ReviewDecisionResponse,
  ReviewList,
  SearchResponse,
  SourceRecordList,
  SourceRecordOut,
  TimelineCommitResponse,
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
    MOCK_CASES.filter((c) => c.owner_id).map((c) => [
      c.id,
      [{ user_id: c.owner_id!, role: "collaborator" as const, created_at: c.created_at }],
    ]),
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

/* Phase 2: evidence-intelligence jobs, derived artifacts, custody events. */
const intelJobsState: AnalysisJobOut[] = [];
const artifactsState: DerivedArtifactOut[] = [];
const custodyEventsState: CustodyEventOut[] = [];
const extractionSourceTexts = new Map<string, string>();
let intelSeq = 7000;

const CUSTODY_EVENT_TYPES = [
  "collected",
  "transferred",
  "received",
  "sealed",
  "unsealed",
  "verified",
  "accessed",
  "exported",
  "restored",
  "disposed",
];
const CUSTODY_REQUIRED_FIELDS: Record<string, string[]> = {
  collected: ["collector"],
  transferred: ["transferor", "recipient"],
  received: ["recipient"],
};

function nextIntelId(): string {
  intelSeq += 1;
  return uid(intelSeq);
}

function isoNow(): string {
  return new Date().toISOString();
}

/** Deterministic mock hash (stands in for the backend sha256 draft hash). */
function draftHash(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

/** Map a report-audit job (+ its findings artifact) to the API read model. */
function mockReportAuditOut(job: AnalysisJobOut): ReportAuditOut {
  const summary = job.result_summary ?? {};
  const artifact = artifactsState.find((a) => a.analysis_job_id === job.id) ?? null;
  const claims = artifact?.payload?.claims;
  const str = (key: string) =>
    typeof summary[key] === "string" ? (summary[key] as string) : null;
  return {
    id: job.id,
    case_id: job.case_id,
    status: job.status,
    created_at: job.created_at,
    completed_at: job.completed_at,
    error: job.error,
    draft_source_type: str("draft_source_type"),
    draft_hash: str("draft_hash"),
    draft_chars: typeof summary.draft_chars === "number" ? summary.draft_chars : null,
    conversation_id: str("conversation_id"),
    message_id: str("message_id"),
    artifact_id: artifact?.id ?? null,
    claims: Array.isArray(claims) ? claims.length : null,
    stale: null,
    result_summary: summary,
  };
}

/**
 * Deterministic custody seed: evidence[0] has a transfer with no receipt (the
 * audit finds `custody.unacknowledged_transfer`); evidence[1] has a complete
 * collected → transferred → received chain (the audit finds nothing).
 */
function seedCustodyState(): void {
  const [first, second] = MAIN_EVIDENCE;
  if (!first || !second) return;
  // iso(daysAgo, hoursAgo): smaller n is *older*, so n=1,2,3 reads chronologically.
  const day = (n: number) => iso(9 - n, 8 + n);
  custodyEventsState.push(
    {
      id: nextIntelId(),
      case_id: CASE_ID_MAIN,
      evidence_file_id: first.id,
      event_type: "collected",
      occurred_at: day(1),
      recorded_at: day(1),
      actor_user_id: null,
      collector: "Insp. Verma",
      transferor: null,
      recipient: null,
      location: "Kalyan depot",
      method: "sealed envelope",
      notes: null,
      recorded_sha256: first.sha256,
    },
    {
      id: nextIntelId(),
      case_id: CASE_ID_MAIN,
      evidence_file_id: first.id,
      event_type: "transferred",
      occurred_at: day(2),
      recorded_at: day(2),
      actor_user_id: null,
      collector: null,
      transferor: "Insp. Verma",
      recipient: "Forensics Lab",
      location: "Kalyan depot",
      method: "hand carry",
      notes: "moved for analysis",
      recorded_sha256: null,
    },
    {
      id: nextIntelId(),
      case_id: CASE_ID_MAIN,
      evidence_file_id: second.id,
      event_type: "collected",
      occurred_at: day(1),
      recorded_at: day(1),
      actor_user_id: null,
      collector: "Insp. Verma",
      transferor: null,
      recipient: null,
      location: "Kalyan depot",
      method: null,
      notes: null,
      recorded_sha256: second.sha256,
    },
    {
      id: nextIntelId(),
      case_id: CASE_ID_MAIN,
      evidence_file_id: second.id,
      event_type: "transferred",
      occurred_at: day(2),
      recorded_at: day(2),
      actor_user_id: null,
      collector: null,
      transferor: "Insp. Verma",
      recipient: "Forensics Lab",
      location: null,
      method: "hand carry",
      notes: null,
      recorded_sha256: null,
    },
    {
      id: nextIntelId(),
      case_id: CASE_ID_MAIN,
      evidence_file_id: second.id,
      event_type: "received",
      occurred_at: day(3),
      recorded_at: day(3),
      actor_user_id: null,
      collector: null,
      transferor: null,
      recipient: "Forensics Lab",
      location: "Forensics Lab",
      method: null,
      notes: "chain acknowledged",
      recorded_sha256: second.sha256,
    },
  );
}
seedCustodyState();

/** Resolve evidence within a case, mirroring the backend's 404/409 split. */
function mockEvidenceFor(caseId: string, evidenceId: string): EvidenceListItem {
  const recycled = recycleState.find((e) => e.id === evidenceId && e.case_id === caseId);
  if (recycled) {
    throw new ApiError({
      status: 409,
      code: "EVIDENCE_UNAVAILABLE",
      message: "evidence is deleted; restore it first",
    });
  }
  const item = evidenceState.find((e) => e.id === evidenceId);
  if (!item || (caseId !== CASE_ID_MAIN && caseId !== CASE_ID_SECONDARY)) {
    throw notFound(`evidence ${evidenceId} not found in this case`);
  }
  return item;
}

function mockExtractionArtifact(
  caseId: string,
  item: EvidenceListItem,
  jobId: string,
): DerivedArtifactOut {
  return {
    id: nextIntelId(),
    case_id: caseId,
    kind: "extraction",
    origin: "llm",
    status: "pending_review",
    validation_status: "flagged",
    evidence_file_id: item.id,
    source_record_id: null,
    source_locator: { unit_index: 0, page: 1 },
    payload: {
      fields: {
        person_names: ["Rajesh Kumar"],
        organization_names: ["Gokul Traders"],
        phone_numbers: ["+919820011223"],
        email_addresses: [],
        account_references: [],
        transaction_amounts: ["45,000.00 INR"],
        transaction_dates: ["2026-01-15"],
        urls: [],
        domains: [],
        device_identifiers: [],
        statements: ["payment was made promptly"],
        events: ["payment recorded"],
      },
    },
    content_hash: `extraction-${jobId}-${item.id}`,
    parser_version: "mock:1",
    prompt_version: "1.0.0",
    model_profile: "mock",
    analysis_job_id: jobId,
    validation_errors: [
      {
        field: "statements",
        index: 0,
        code: "value_not_in_source",
        message: "value is not present in the source record",
      },
    ],
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/** Original complaint snapshot shared by the mock records + artifacts. */
export const MOCK_COMPLAINT_SOURCE =
  "मैंने राहुल शर्मा को ५,००० रुपये नहीं दिए। खाता संख्या ACC-7781 से भुगतान हुआ।";

function mockMultilingualArtifacts(
  caseId: string,
  item: EvidenceListItem,
  jobId: string,
  translate: boolean,
): [DerivedArtifactOut, DerivedArtifactOut | null] {
  const now = isoNow();
  const extraction: DerivedArtifactOut = {
    id: nextIntelId(),
    case_id: caseId,
    kind: "extraction",
    origin: "llm",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: item.id,
    source_record_id: null,
    source_locator: { record_no: 1, field: "text" },
    payload: {
      multilingual: true,
      language: "hindi",
      script_profile: {
        devanagari_letters: 62,
        latin_letters: 8,
        devanagari_digits: 5,
        ascii_digits: 4,
        other_letters: 0,
        total_letters: 70,
        devanagari_ratio: 0.8857,
        latin_ratio: 0.1143,
        other_ratio: 0,
        candidate: "devanagari",
      },
      language_consistent: true,
      fields: {
        person_names: ["राहुल शर्मा"],
        organization_names: [],
        account_references: ["ACC-7781"],
        phone_numbers: [],
        email_addresses: [],
        amounts: ["५,०००"],
        dates: [],
        referenced_identifiers: ["ACC-7781"],
        event_statements: ["भुगतान हुआ"],
        negations: ["नहीं दिए"],
      },
      ambiguity_flags: [
        {
          flag: "devanagari_digits",
          detail: "amount/date written in Devanagari digits; verify the exact figure",
        },
      ],
      record_no: 1,
      rules_version: "1.0.0",
    },
    content_hash: `multilingual-${jobId}-${item.id}`,
    parser_version: "mock:1",
    prompt_version: "1.0.0",
    model_profile: "mock",
    analysis_job_id: jobId,
    validation_errors: [],
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: now,
    updated_at: now,
  };
  if (!translate) return [extraction, null];
  const translation: DerivedArtifactOut = {
    id: nextIntelId(),
    case_id: caseId,
    kind: "translation",
    origin: "llm",
    status: "pending_review",
    validation_status: "flagged",
    evidence_file_id: item.id,
    source_record_id: null,
    source_locator: { record_no: 1, field: "text" },
    payload: {
      source_language: "hindi",
      translated_text:
        "I did not give Rahul Sharma any rupees. The payment was made from account ACC-7781.",
      material_check: {
        material_total: 2,
        material_preserved: 1,
        material_missing: ["5,000"],
        preserved: false,
      },
      negation_preserved: true,
      record_no: 1,
      rules_version: "1.0.0",
    },
    content_hash: `translation-${jobId}-${item.id}`,
    parser_version: "mock:1",
    prompt_version: "1.0.0",
    model_profile: "mock",
    analysis_job_id: jobId,
    validation_errors: [{ code: "material_value_missing", value: "5,000" }],
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: now,
    updated_at: now,
  };
  return [extraction, translation];
}

/* ------------------------------ AI threads ------------------------------- */

/** Ids of the deterministic conversations seeded into the mock history. */
export const AI_SEED_CONVERSATIONS = {
  general: "ai-conv-seed-general",
  case: "ai-conv-seed-case",
} as const;

const aiConversationsState: AiConversation[] = [];
const aiMessagesByConversation: Record<string, AiMessage[]> = {};
let aiConversationSeq = 1;

interface AiThreadSeed {
  conversation: AiConversation;
  messages: AiMessage[];
}

/** Seed timestamps are relative to "now" so history reads as plausible recency. */
function buildAiSeeds(): AiThreadSeed[] {
  const hoursAgo = (hours: number) => new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
  const caseStamp = hoursAgo(2);
  const generalStamp = hoursAgo(26);
  return [
    {
      conversation: {
        id: AI_SEED_CONVERSATIONS.case,
        case_id: CASE_ID_MAIN,
        title: "Evidence ingest walkthrough",
        mode: "case",
        status: "active",
        prompt_version: "1.0.0",
        created_at: caseStamp,
        updated_at: caseStamp,
        last_message_at: caseStamp,
      },
      messages: [
        {
          id: "ai-seed-case-msg-1",
          role: "user",
          content: "Which evidence files support the primary lead?",
          sources: [],
          tool_events: [],
          grounded: false,
          prompt_version: "1.0.0",
          created_at: caseStamp,
        },
        {
          id: "ai-seed-case-msg-2",
          role: "assistant",
          content:
            "The uploaded call-detail record ties the primary lead to two phone numbers.\n\n| File | Rows |\n| --- | --- |\n| call_detail_record.csv | 4821 |",
          sources: [{ type: "evidence", id: "ev-seed-cdr", label: "call_detail_record.csv" }],
          tool_events: [],
          grounded: true,
          prompt_version: "1.0.0",
          created_at: caseStamp,
        },
      ],
    },
    {
      conversation: {
        id: AI_SEED_CONVERSATIONS.general,
        case_id: null,
        title: "Platform onboarding questions",
        mode: "general",
        status: "active",
        prompt_version: "1.0.0",
        created_at: generalStamp,
        updated_at: generalStamp,
        last_message_at: generalStamp,
      },
      messages: [
        {
          id: "ai-seed-general-msg-1",
          role: "user",
          content: "How do I invite an analyst to the platform?",
          sources: [],
          tool_events: [],
          grounded: false,
          prompt_version: "1.0.0",
          created_at: generalStamp,
        },
        {
          id: "ai-seed-general-msg-2",
          role: "assistant",
          content:
            "Administrators invite analysts from **Admin → Users**; new accounts stay pending until approved.",
          sources: [{ type: "knowledge", id: "docs/access.md#invites", label: "access control" }],
          tool_events: [],
          grounded: false,
          prompt_version: "1.0.0",
          created_at: generalStamp,
        },
      ],
    },
  ];
}

function seedAiState(): void {
  aiConversationsState.length = 0;
  for (const key of Object.keys(aiMessagesByConversation)) delete aiMessagesByConversation[key];
  for (const seed of buildAiSeeds()) {
    aiConversationsState.push({ ...seed.conversation });
    aiMessagesByConversation[seed.conversation.id] = seed.messages.map((m) => ({ ...m }));
  }
}
seedAiState();

function titleFromQuestion(question: string): string {
  const cleaned = question.trim().replace(/\s+/g, " ");
  if (!cleaned) return "New conversation";
  return cleaned.length > 56 ? `${cleaned.slice(0, 55).trimEnd()}…` : cleaned;
}

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
    description:
      "Victim transferred funds to a fraudulent investment platform promoted over WhatsApp.",
    reported_amount: 1850000,
    currency: "INR",
    amount_lost: 1850000,
    recovery_amount: 0,
    digital_accounts: [{ platform: "geojit", handle: "rajiv.mehta" }],
    devices: [],
    wallet_addresses: null,
    status: "evidence_collected",
    statement:
      "I was contacted on WhatsApp by 'Sharma Ji' offering guaranteed 30% monthly returns.",
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
    throw new ApiError({
      status: 403,
      code: "FORBIDDEN",
      message: `permission '${permission}' required`,
    });
  }
  return user;
}

const ROLE_PERMISSIONS: Record<string, string[]> = {
  ADMIN: [
    "case.read",
    "case.create",
    "case.update",
    "case.archive",
    "evidence.read",
    "evidence.upload",
    "evidence.delete",
    "evidence.restore",
    "ingestion.run",
    "analytics.run",
    "findings.read",
    "findings.review",
    "findings.confirm",
    "findings.dismiss",
    "entity.merge",
    "users.manage",
    "audit.read",
    "crosscase.read",
  ],
  INVESTIGATOR: [
    "case.read",
    "case.create",
    "case.update",
    "case.archive",
    "evidence.read",
    "evidence.upload",
    "evidence.delete",
    "evidence.restore",
    "ingestion.run",
    "analytics.run",
    "findings.read",
    "findings.review",
    "findings.confirm",
    "findings.dismiss",
    "entity.merge",
    "audit.read",
    "crosscase.read",
  ],
  ANALYST: ["case.read", "evidence.read", "analytics.run", "findings.read", "findings.review"],
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
      throw new ApiError({
        status: 403,
        code: "FORBIDDEN",
        message: "You do not have access to this case",
      });
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
    throw new ApiError({
      status: 403,
      code: "FORBIDDEN",
      message: "Only the case owner or an admin can manage members",
    });
  }
}

/** Non-throwing access check used by cross-case scope rechecks (fail closed). */
function canAccessCase(caseId: string): boolean {
  const caze = casesState.find((c) => c.id === caseId);
  if (!caze) return false;
  const { record, roles } = currentUser();
  if (!record) return false;
  if (roles.includes("ADMIN")) return true;
  if (caze.owner_id === record.id) return true;
  return (membersState[caseId] ?? []).some((m) => m.user_id === record.id);
}

function pushAudit(
  action: string,
  resourceType: string,
  caseId: string | null,
  meta: Record<string, unknown> | null,
): void {
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
  intelJobsState.length = 0;
  artifactsState.length = 0;
  custodyEventsState.length = 0;
  extractionSourceTexts.clear();
  for (const key of Object.keys(resolutionAliasState)) delete resolutionAliasState[key];
  seedCustodyState();
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
  seedAiState();
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
        throw new ApiError({
          status: 401,
          code: "UNAUTHORIZED",
          message: "invalid username or password",
        });
      }
      if (user.status === "PENDING") {
        throw new ApiError({
          status: 403,
          code: "ACCOUNT_PENDING",
          message: "account is pending administrator approval",
        });
      }
      if (user.status === "SUSPENDED") {
        throw new ApiError({
          status: 403,
          code: "ACCOUNT_SUSPENDED",
          message: "account is suspended",
        });
      }
      if (user.status === "REJECTED") {
        throw new ApiError({
          status: 403,
          code: "ACCOUNT_REJECTED",
          message: "account was rejected",
        });
      }
      currentUserId = user.id;
      currentRoles = user.roles;
      authSession.setPermissions(resolvedPermissions(user.roles));
      pushAudit("auth.login_succeeded", "user", null, { expires_in_minutes: 30 });
      return {
        access_token: `mock-token-${user.id}`,
        token_type: "bearer",
        expires_in: 1800,
        user: {
          id: user.id,
          username: user.username,
          email: user.email,
          status: user.status,
          is_active: active(user),
        },
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
        user: {
          id: record.id,
          username: record.username,
          email: record.email,
          status: record.status,
          is_active: active(record),
        },
        roles: roleList,
        permissions,
      };
    },

    async register(input: RegisterInput): Promise<RegisteredUserOut> {
      await delay(MOCK_LATENCY);
      if (
        MOCK_USERS.some((u) => u.username === input.username) ||
        registeredState.some((u) => u.username === input.username)
      ) {
        throw new ApiError({
          status: 409,
          code: "CONFLICT",
          message: `username '${input.username}' is taken`,
        });
      }
      if (MOCK_USERS.some((u) => u.email === input.email)) {
        throw new ApiError({
          status: 409,
          code: "CONFLICT",
          message: `email '${input.email}' is registered`,
        });
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
        user: {
          id: record.id,
          username: record.username,
          email: record.email,
          status: "PENDING",
          is_active: false,
        },
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
      return {
        items: page.map((u) => adminUserOut(u, userStamp(u.id))),
        total: sorted.length,
        limit,
        offset,
      };
    },

    async listPending(params: AdminUserListParams = {}) {
      await delay(MOCK_LATENCY / 2);
      requirePermission("users.manage");
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const pending = [...registeredState]
        .filter((u) => u.status === "PENDING")
        .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
      return {
        items: pending
          .slice(offset, offset + limit)
          .map((u) => adminUserOut(u, u.created_at ?? "")),
        total: pending.length,
        limit,
        offset,
      };
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
        throw new ApiError({
          status: 409,
          code: "CONFLICT",
          message: "account is already rejected",
        });
      }
      if (user.status === "ACTIVE" && user.roles.includes("ADMIN")) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "cannot reject an active administrator",
        });
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
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "cannot suspend an active administrator",
        });
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

    async create(input: {
      title: string;
      description?: string | null;
      case_number?: string | null;
      status?: Case["status"];
    }) {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.create");
      const caze: Case = {
        id: uid(Math.floor(900000 + Math.random() * 10000)),
        case_number:
          input.case_number ?? `CS-${Math.random().toString(16).slice(2, 10).toUpperCase()}`,
        title: input.title,
        description: input.description ?? null,
        status: input.status ?? "open",
        owner_id: user.id,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      casesState.unshift(caze);
      pushAudit("case.created", "case", caze.id, {
        title: caze.title,
        case_number: caze.case_number,
      });
      return caze;
    },

    async update(caseId: string, input: CaseUpdateRequest) {
      await delay(MOCK_LATENCY);
      const user = requirePermission("case.update");
      const caze = assertCaseAccess(caseId);
      if ((input.status as string) === "archived") {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "use the archive endpoint",
        });
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
        throw new ApiError({
          status: 409,
          code: "CONFLICT",
          message: "user is already a member of this case",
        });
      }
      const known =
        MOCK_USERS.some((u) => u.id === input.user_id) ||
        registeredState.some((u) => u.id === input.user_id);
      if (!known) throw notFound(`user ${input.user_id} not found`);
      rows.push({ user_id: input.user_id, role: input.role, created_at: new Date().toISOString() });
      pushAudit("case.member_added", "case", caseId, {
        member_id: input.user_id,
        role: input.role,
        member_count: rows.length,
      });
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
      const detail =
        MAIN_ENTITY_DETAILS[entity.display_value] ?? MAIN_ENTITY_DETAILS[entity.canonical_value];
      return {
        ...entity,
        aliases: [...(detail?.aliases ?? []), ...(resolutionAliasState[entity.id] ?? [])],
        context: detail?.context ?? null,
      };
    },

    async relationships(caseId: string, limit = 500) {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const items =
        caseId === CASE_ID_MAIN
          ? MAIN_RELATIONSHIPS
          : caseId === CASE_ID_SECONDARY
            ? SECONDARY_CASE_DATA.relationships
            : [];
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
      const known = [
        "a1000000-0000-4000-8000-000000000001",
        "a1000000-0000-4000-8000-000000000004",
      ];
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
      const known = [
        "a1000000-0000-4000-8000-000000000001",
        "a1000000-0000-4000-8000-000000000004",
      ];
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
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "cannot merge an entity into itself",
        });
      }
      pushAudit("entity.merged", "entity", caseId, {
        primary_id: input.primary_entity_id,
        merge_id: input.merge_entity_id,
      });
      // Mirror the backend: the duplicate leaves the active set, so any open
      // candidate pair involving it becomes stale and can no longer be approved.
      duplicate.status = "merged";
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
      const detail =
        MAIN_ENTITY_DETAILS[primary.display_value] ?? MAIN_ENTITY_DETAILS[primary.canonical_value];
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
      const items =
        caseId === CASE_ID_MAIN
          ? evidenceState
          : caseId === CASE_ID_SECONDARY
            ? SECONDARY_CASE_DATA.evidence
            : [];
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
        EVIDENCE_DETAILS[Object.keys(EVIDENCE_DETAILS)[Math.max(0, seedIndex)] ?? "demo_cdr"];
      return {
        id: item.id,
        case_id: caseId,
        data_source: detail?.data_source ?? "csv",
        original_filename: item.original_filename,
        stored_key:
          detail?.stored_key ?? `cases/${caseId}/evidence/${item.id}/${item.original_filename}`,
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

    async upload(
      caseId: string,
      file: UploadFile,
      _dataSource = "csv",
      _options?: { collectionId?: string },
    ) {
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
          ? [
              "Rajesh Kumar",
              "Sunita Sharma",
              "Arjun Mehta",
              "Kavita Rao",
              "+91-98765-43210",
              "+91-91234-56789",
              "+91-90000-11111",
              "+91-98111-22233",
              "TechSecure Pvt Ltd",
            ]
          : index === 1
            ? [
                "Rajesh Kumar",
                "Arjun Mehta",
                "Mumbai",
                "Pune",
                "Delhi",
                "Noida",
                "MH12AB1234",
                "MH12AB2345",
              ]
            : index === 2
              ? ["Rajesh Kumar", "Arjun Mehta", "1100220011", "5500667788", "2244660088"]
              : index === 3
                ? ["Rajesh Kumar", "Sunita Sharma", "Mehul Desai", "3300445566", "9900112233"]
                : [
                    "Rajesh Kumar",
                    "Arjun Mehta",
                    "Varun Joshi",
                    "MH12AB1234",
                    "DL01EF9012",
                    "UP32GH3456",
                  ];
      const findingIds = MAIN_FINDINGS.filter((f) => f.evidence_ids.includes(evidenceId)).map(
        (f) => f.id,
      );
      const detail = await this.get(caseId, evidenceId).catch(() => null);
      return {
        evidence: (detail ?? {}) as EvidenceDetail,
        record_count: item.record_count ?? 0,
        records_by_status: { [item.status]: item.record_count ?? 0 },
        entity_count: relatedEntityIds.length,
        relationship_count: Math.max(1, Math.floor(relatedEntityIds.length / 2)),
        finding_count: findingIds.length,
        related_entity_ids: relatedEntityIds.map(
          (k) => KEY_ENTITY_IDS[k] ?? relatedEntityId(k, caseId),
        ),
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
        summary: {
          records: item.record_count ?? 40,
          created_records: item.record_count ?? 40,
          entities: 14,
          relationships: 18,
        },
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
      const items =
        caseId === CASE_ID_MAIN
          ? jobsState
          : caseId === CASE_ID_SECONDARY
            ? SECONDARY_CASE_DATA.jobsList
            : [];
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
        caseId === CASE_ID_MAIN
          ? jobsState
          : caseId === CASE_ID_SECONDARY
            ? SECONDARY_CASE_DATA.jobsList
            : [];
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

    /* ------------------ Evidence intelligence (phase 2) ------------------ */

    async extract(caseId: string, evidenceFileId: string): Promise<JobSubmitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const item = mockEvidenceFor(caseId, evidenceFileId);
      const active = intelJobsState.find(
        (j) =>
          j.case_id === caseId &&
          j.feature === "ingestion" &&
          j.evidence_file_id === evidenceFileId &&
          (j.status === "pending" || j.status === "running"),
      );
      if (active) {
        throw new ApiError({
          status: 409,
          code: "EXTRACTION_ACTIVE",
          message: "an extraction is already active for this evidence",
        });
      }
      const attempts = intelJobsState.filter(
        (j) =>
          j.case_id === caseId &&
          j.feature === "ingestion" &&
          j.evidence_file_id === evidenceFileId,
      ).length;
      const job: AnalysisJobOut = {
        id: nextIntelId(),
        case_id: caseId,
        feature: "ingestion",
        status: "succeeded",
        idempotency_key: `extraction:${evidenceFileId}:attempt:${attempts + 1}`,
        progress: 100,
        total_records: 1,
        processed_records: 1,
        attempts: attempts + 1,
        timeout_seconds: 600,
        cancel_requested: false,
        error: null,
        result_summary: {
          units_total: 1,
          artifacts_created: 1,
          artifacts_reused: 0,
          fields_total: 12,
          fields_verified: 11,
          error_code: null,
        },
        evidence_file_id: evidenceFileId,
        actor_id: currentUser().record?.id ?? null,
        started_at: isoNow(),
        completed_at: isoNow(),
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      intelJobsState.unshift(job);
      // Deterministic mock "extraction": verbatim claims from a source snapshot
      // that contains every value, plus one paraphrase honestly flagged by the
      // deterministic validator as `value_not_in_source`.
      const source = `Invoice from ${item.original_filename} for record 1. Amount 45,000.00 INR on 2026-01-15.`;
      const artifact = mockExtractionArtifact(caseId, item, job.id);
      extractionSourceTexts.set(artifact.id, source);
      artifactsState.unshift(artifact);
      pushAudit("extraction.submitted", "analysis_job", caseId, {
        evidence_file_id: evidenceFileId,
      });
      pushAudit("extraction.completed", "analysis_job", caseId, {
        status: "succeeded",
        artifacts_created: 1,
      });
      return { job, duplicate: false };
    },

    async multilingual(
      caseId: string,
      evidenceFileId: string,
      translate = false,
    ): Promise<JobSubmitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const item = mockEvidenceFor(caseId, evidenceFileId);
      const active = intelJobsState.find(
        (j) =>
          j.case_id === caseId &&
          j.feature === "multilingual" &&
          j.evidence_file_id === evidenceFileId &&
          (j.status === "pending" || j.status === "running"),
      );
      if (active) {
        throw new ApiError({
          status: 409,
          code: "MULTILINGUAL_ACTIVE",
          message: "a multilingual run is already active for this evidence",
        });
      }
      const attempts = intelJobsState.filter(
        (j) =>
          j.case_id === caseId &&
          j.feature === "multilingual" &&
          j.evidence_file_id === evidenceFileId,
      ).length;
      const job: AnalysisJobOut = {
        id: nextIntelId(),
        case_id: caseId,
        feature: "multilingual",
        status: "succeeded",
        idempotency_key: `multilingual:${evidenceFileId}:attempt:${attempts + 1}`,
        progress: 100,
        total_records: 1,
        processed_records: 1,
        attempts: attempts + 1,
        timeout_seconds: 300,
        cancel_requested: false,
        error: null,
        result_summary: {
          units_total: 1,
          units_skipped_empty: 0,
          units_failed: 0,
          artifacts_created: 1,
          artifacts_reused: 0,
          artifacts_flagged: translate ? 1 : 0,
          artifacts_invalid: 0,
          translations_created: translate ? 1 : 0,
          language_ambiguous: 0,
          values_total: 4,
          values_verified: 4,
          values_withheld_injected: 0,
        },
        evidence_file_id: evidenceFileId,
        actor_id: currentUser().record?.id ?? null,
        started_at: isoNow(),
        completed_at: isoNow(),
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      intelJobsState.unshift(job);
      // Deterministic mock analysis: script profile + verified fields from the
      // original snapshot; a lossy translation (when requested) is honestly
      // flagged with the material value it dropped.
      const [extraction, translation] = mockMultilingualArtifacts(caseId, item, job.id, translate);
      extractionSourceTexts.set(extraction.id, MOCK_COMPLAINT_SOURCE);
      artifactsState.unshift(extraction);
      if (translation) {
        artifactsState.unshift(translation);
      }
      pushAudit("multilingual.submitted", "analysis_job", caseId, {
        evidence_file_id: evidenceFileId,
      });
      pushAudit("multilingual.completed", "analysis_job", caseId, {
        status: "succeeded",
        artifacts_created: 1,
        translations_created: translate ? 1 : 0,
      });
      return { job, duplicate: false };
    },

    async triage(caseId: string, evidenceFileId: string): Promise<JobSubmitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      mockEvidenceFor(caseId, evidenceFileId);
      const active = intelJobsState.find(
        (j) =>
          j.case_id === caseId &&
          j.feature === "triage" &&
          j.evidence_file_id === evidenceFileId &&
          (j.status === "pending" || j.status === "running"),
      );
      if (active) {
        throw new ApiError({
          status: 409,
          code: "TRIAGE_ACTIVE",
          message: "a triage run is already active for this evidence",
        });
      }
      const attempts = intelJobsState.filter(
        (j) =>
          j.case_id === caseId && j.feature === "triage" && j.evidence_file_id === evidenceFileId,
      ).length;
      const job: AnalysisJobOut = {
        id: nextIntelId(),
        case_id: caseId,
        feature: "triage",
        status: "succeeded",
        idempotency_key: `triage:${evidenceFileId}:attempt:${attempts + 1}`,
        progress: 100,
        total_records: 1,
        processed_records: 1,
        attempts: attempts + 1,
        timeout_seconds: 300,
        cancel_requested: false,
        error: null,
        result_summary: {
          records_total: 1,
          records_scanned: 1,
          urls_analyzed: 2,
          observations_total: 2,
          manifest_entries_verified: 0,
          artifacts_created: 1,
          artifacts_reused: 0,
          artifacts_flagged: 0,
          explanation_failed: 0,
          units_failed: 0,
        },
        evidence_file_id: evidenceFileId,
        actor_id: currentUser().record?.id ?? null,
        started_at: isoNow(),
        completed_at: isoNow(),
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      intelJobsState.unshift(job);
      const artifactId = nextIntelId();
      const triageArtifact: DerivedArtifactOut = {
        id: artifactId,
        case_id: caseId,
        kind: "triage_observation",
        origin: "llm",
        status: "pending_review",
        validation_status: "valid",
        evidence_file_id: evidenceFileId,
        source_record_id: null,
        source_locator: { scope: "evidence_file", records_scanned: 1 },
        payload: {
          triage: true,
          evidence_file_id: evidenceFileId,
          format_profile: {
            records_scanned: 1,
            urls_found: 2,
            manifest_entries: 0,
            log_lines: 0,
            email_header_records: 0,
            history_rows: 0,
            observations_truncated: false,
          },
          fields: {
            urls: [
              {
                url: "http://paypal.com@evil.test/login",
                host: "evil.test",
                userinfo: true,
                ip_host: false,
                punycode: false,
                nonstandard_port: false,
                port: null,
                record_no: 1,
              },
              {
                url: "https://cdn.example.org:8080/asset.js",
                host: "cdn.example.org",
                userinfo: false,
                ip_host: false,
                punycode: false,
                nonstandard_port: true,
                port: 8080,
                record_no: 1,
              },
            ],
            email_headers: [],
            auth_results: [],
            manifest: null,
            history: null,
            logs: null,
          },
          observations: [
            {
              rule: "triage.url.userinfo",
              severity: "high",
              locator: { record_no: 1 },
              detail: { url: "http://paypal.com@evil.test/login", host: "evil.test" },
            },
            {
              rule: "triage.url.nonstandard_port",
              severity: "low",
              locator: { record_no: 1 },
              detail: {
                url: "https://cdn.example.org:8080/asset.js",
                host: "cdn.example.org",
                port: 8080,
              },
            },
          ],
          missing_information: [],
          explanation: {
            summary:
              "One URL hides its real host behind userinfo; one uses a non-standard port. Both are structural observations only.",
            explanations: [
              "The userinfo URL shows paypal.com before the @, but the parsed host is evil.test.",
            ],
            not_established: ["No malicious intent or payload is established by structure alone."],
            verification_steps: [
              "Compare the recorded hosts against known indicators.",
              "Confirm who operates the non-standard port.",
            ],
          },
          explanation_failed: false,
          explanation_error: null,
          analysis_scope:
            "structural observations only: no file was executed, opened or resolved, and no URL was fetched",
          rules_version: "1.0.0",
        },
        content_hash: `triage-${artifactId}`,
        parser_version: "mock:1",
        prompt_version: "1.0.0",
        model_profile: "mock",
        analysis_job_id: job.id,
        validation_errors: [],
        review_note: null,
        reviewed_by: null,
        reviewed_at: null,
        parent_artifact_id: null,
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      artifactsState.unshift(triageArtifact);
      pushAudit("triage.submitted", "analysis_job", caseId, { evidence_file_id: evidenceFileId });
      pushAudit("triage.completed", "analysis_job", caseId, {
        status: "succeeded",
        observations_total: 2,
        artifacts_created: 1,
      });
      return { job, duplicate: false };
    },

    async reportAudit(caseId: string, input: ReportAuditSubmitInput): Promise<JobSubmitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("case.read");
      assertCaseAccess(caseId);
      const hasRef = Boolean(input.conversation_id) !== Boolean(input.message_id);
      const bothRef = Boolean(input.conversation_id) && Boolean(input.message_id);
      const hasText = typeof input.draft_text === "string";
      if ((hasRef && !hasText) || (bothRef && hasText) || (!bothRef && !hasText)) {
        throw new ApiError({
          status: 422,
          code: "DRAFT_SOURCE_INVALID",
          message: "provide exactly one draft source",
        });
      }
      const draft = hasText ? (input.draft_text as string).trim() : "mock message-sourced draft";
      if (!draft) {
        throw new ApiError({ status: 422, code: "DRAFT_SOURCE_INVALID", message: "draft is empty" });
      }
      const active = intelJobsState.find(
        (j) =>
          j.case_id === caseId &&
          j.feature === "report_audit" &&
          (j.status === "pending" || j.status === "running"),
      );
      if (active) {
        throw new ApiError({
          status: 409,
          code: "REPORT_AUDIT_ACTIVE",
          message: "an audit is already active for this case",
        });
      }
      const attempts = intelJobsState.filter(
        (j) => j.case_id === caseId && j.feature === "report_audit",
      ).length;
      const jobId = nextIntelId();
      const job: AnalysisJobOut = {
        id: jobId,
        case_id: caseId,
        feature: "report_audit",
        status: "succeeded",
        idempotency_key: `report_audit:${draftHash(draft)}:a${attempts + 1}`,
        progress: 100,
        total_records: 1,
        processed_records: 1,
        attempts: attempts + 1,
        timeout_seconds: 300,
        cancel_requested: false,
        error: null,
        result_summary: {
          draft_source_type: hasText ? "text" : "message",
          draft_hash: draftHash(draft),
          draft_chars: draft.length,
          claims_extracted: 0,
          claims_truncated: 0,
          claims_invalid: 0,
          citations_checked: 0,
          citations_invalid: 0,
          assessments_attempted: 0,
          assessments_valid: 0,
          assessments_invalid: 0,
          findings_high: 0,
          findings_medium: 0,
          findings_info: 0,
          records_searched: 0,
          counter_matches: 0,
          artifacts_created: 1,
          artifacts_reused: 0,
          artifacts_flagged: 1,
          units_failed: 0,
        },
        evidence_file_id: null,
        actor_id: currentUser().record?.id ?? null,
        started_at: isoNow(),
        completed_at: isoNow(),
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      intelJobsState.unshift(job);
      const artifactId = nextIntelId();
      const auditArtifact: DerivedArtifactOut = {
        id: artifactId,
        case_id: caseId,
        kind: "report_claim_review",
        origin: "llm",
        status: "pending_review",
        validation_status: "flagged",
        evidence_file_id: null,
        source_record_id: null,
        source_locator: { scope: "report_draft" },
        payload: {
          report_audit: true,
          draft_source: {
            type: hasText ? "text" : "message",
            conversation_id: input.conversation_id ?? null,
            message_id: input.message_id ?? null,
            chars: draft.length,
          },
          draft_chars: draft.length,
          draft_hash: draftHash(draft),
          claims: [],
          counter_evidence: { records_searched: 0, note: "mock run scans no records" },
          model: { claims_extracted: 0, claims_truncated: 0 },
          rules_version: "1.0.0",
          analysis_scope:
            "claim extraction and support assessment only: no draft text was executed or filed",
        },
        content_hash: `report-audit-${artifactId}`,
        parser_version: "mock:1",
        prompt_version: "1.0.0",
        model_profile: "mock",
        analysis_job_id: job.id,
        validation_errors: [
          { code: "model_claims_unreviewed", field: "claims", value: null },
        ],
        review_note: null,
        reviewed_by: null,
        reviewed_at: null,
        parent_artifact_id: null,
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      artifactsState.unshift(auditArtifact);
      pushAudit("report_audit.submitted", "analysis_job", caseId, {
        duplicate: false,
        draft_source_type: hasText ? "text" : "message",
      });
      pushAudit("report_audit.completed", "analysis_job", caseId, {
        status: "succeeded",
        claims_extracted: 0,
        artifacts_created: 1,
      });
      return { job, duplicate: false };
    },

    async reportAudits(caseId: string, params: PageParams = {}): Promise<ReportAuditList> {
      await delay(MOCK_LATENCY);
      requirePermission("case.read");
      assertCaseAccess(caseId);
      const jobs = intelJobsState.filter(
        (j) => j.case_id === caseId && j.feature === "report_audit",
      );
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const items = jobs.slice(offset, offset + limit).map((job) => mockReportAuditOut(job));
      return { items, total: jobs.length, limit, offset };
    },

    async reportAuditDetail(caseId: string, auditId: string): Promise<ReportAuditDetailOut> {
      await delay(MOCK_LATENCY);
      requirePermission("case.read");
      assertCaseAccess(caseId);
      const job = intelJobsState.find(
        (j) => j.id === auditId && j.case_id === caseId && j.feature === "report_audit",
      );
      if (!job) {
        throw new ApiError({ status: 404, code: "JOB_NOT_FOUND", message: "audit not found" });
      }
      const artifact =
        artifactsState.find((a) => a.analysis_job_id === job.id) ?? null;
      return { ...mockReportAuditOut(job), artifact };
    },

    async sourceRecords(
      caseId: string,
      evidenceId: string,
      params: PageParams = {},
    ): Promise<SourceRecordList> {
      await delay(MOCK_LATENCY);
      requirePermission("evidence.read");
      assertCaseAccess(caseId);
      const item = mockEvidenceFor(caseId, evidenceId);
      const limit = params.limit ?? 50;
      const offset = params.offset ?? 0;
      const record: SourceRecordOut = {
        id: `srec-${item.id}-1`,
        evidence_file_id: item.id,
        record_no: 1,
        raw_data: { text: MOCK_COMPLAINT_SOURCE },
      };
      return { items: offset === 0 ? [record] : [], total: 1, limit, offset };
    },

    async evidenceJobs(
      caseId: string,
      params: PageParams & { feature?: string; status?: string } = {},
    ): Promise<AnalysisJobList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = intelJobsState.filter((j) => j.case_id === caseId);
      if (params.feature) items = items.filter((j) => j.feature === params.feature);
      if (params.status) items = items.filter((j) => j.status === params.status);
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async cancelJob(caseId: string, jobId: string): Promise<AnalysisJobOut> {
      await delay(MOCK_LATENCY);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const job = intelJobsState.find((j) => j.id === jobId && j.case_id === caseId);
      const analysisRun =
        job?.feature === "entity_resolution" ||
        job?.feature === "timeline" ||
        job?.feature === "contradiction" ||
        job?.feature === "financial_flow";
      if (
        !job ||
        (job.feature !== "ingestion" &&
          job.feature !== "custody" &&
          job.feature !== "multilingual" &&
          job.feature !== "triage" &&
          !analysisRun)
      ) {
        throw notFound(`job ${jobId} not found`);
      }
      if (job.status !== "pending" && job.status !== "running") {
        throw new ApiError({
          status: 409,
          code: "JOB_TERMINAL",
          message: "job already reached a terminal state",
        });
      }
      job.cancel_requested = true;
      job.status = "canceled";
      job.completed_at = isoNow();
      job.updated_at = isoNow();
      if (analysisRun) {
        // Route flag + terminal transition (the mock runner observes it instantly).
        const prefix = ANALYSIS_FEATURES[job.feature as AnalysisFeature].audit;
        pushAudit(`${prefix}.cancel_requested`, "analysis_job", caseId, {
          job_id: job.id,
          feature: job.feature,
        });
        pushAudit(`${prefix}.canceled`, "analysis_job", caseId, {
          job_id: job.id,
          feature: job.feature,
        });
      } else {
        pushAudit("job.canceled", "analysis_job", caseId, { job_id: job.id, feature: job.feature });
      }
      return job;
    },

    async artifacts(
      caseId: string,
      params: PageParams & { kind?: string } = {},
    ): Promise<ArtifactList> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      let items = artifactsState.filter((a) => a.case_id === caseId);
      if (params.kind) items = items.filter((a) => a.kind === params.kind);
      const limit = params.limit ?? 100;
      const offset = params.offset ?? 0;
      const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { items: sorted.slice(offset, offset + limit), total: items.length, limit, offset };
    },

    async reviewArtifact(
      caseId: string,
      artifactId: string,
      input: ArtifactReviewRequest,
    ): Promise<DerivedArtifactOut> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("findings.review");
      assertCaseAccess(caseId);
      const artifact = artifactsState.find((a) => a.id === artifactId && a.case_id === caseId);
      if (!artifact) throw notFound("artifact not found");
      if (input.note && input.note.length > 2000) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "note must be 2000 characters or fewer",
        });
      }
      if (input.payload?.fields) {
        // Edited payloads mirror the server: extraction only, approval only,
        // one-shot from pending_review, original never rewritten.
        if (artifact.status !== "pending_review") {
          throw new ApiError({
            status: 409,
            code: "ARTIFACT_NOT_REVIEWABLE",
            message: "artifact already left pending_review",
          });
        }
        if (artifact.kind !== "extraction") {
          throw new ApiError({
            status: 422,
            code: "ARTIFACT_KIND_UNSUPPORTED",
            message: "payload edits apply only to extraction artifacts",
          });
        }
        if (input.decision !== "approved") {
          throw new ApiError({
            status: 422,
            code: "INVALID_PAYLOAD",
            message: "an edited payload can only accompany approval",
          });
        }
        // Mirror the server rule: every edited value must appear in the
        // artifact's own source snapshot, or the edit is refused (422).
        const source = (extractionSourceTexts.get(artifact.id) ?? "").toLowerCase();
        for (const [field, values] of Object.entries(input.payload.fields)) {
          if (!field || field.length > 128) {
            throw new ApiError({
              status: 422,
              code: "INVALID_PAYLOAD",
              message: "extraction field names must be 1-128 characters",
            });
          }
          for (const value of values) {
            if (!source.includes(value.toLowerCase())) {
              throw new ApiError({
                status: 422,
                code: "INVALID_PAYLOAD",
                message: `edited value for '${field}' is not present in the source record`,
              });
            }
          }
        }
        const originalHash = artifact.content_hash;
        artifact.status = "superseded";
        const child: DerivedArtifactOut = {
          ...artifact,
          id: nextIntelId(),
          status: "approved",
          payload: { ...artifact.payload, fields: input.payload.fields },
          content_hash: `edited-${artifact.id}`,
          validation_errors: null,
          review_note: input.note ?? null,
          reviewed_by: currentUser().record?.id ?? null,
          reviewed_at: isoNow(),
          parent_artifact_id: artifact.id,
          created_at: isoNow(),
          updated_at: isoNow(),
        };
        extractionSourceTexts.set(child.id, extractionSourceTexts.get(artifact.id) ?? "");
        artifactsState.unshift(child);
        pushAudit("derived_artifact.approved", "derived_artifact", caseId, {
          artifact_id: child.id,
          kind: child.kind,
          content_hash: child.content_hash,
          edited: true,
          original_artifact_id: artifact.id,
          edited_artifact_id: child.id,
          original_content_hash: originalHash,
          edited_content_hash: child.content_hash,
        });
        return child;
      }
      if (artifact.status !== "pending_review") {
        throw new ApiError({
          status: 409,
          code: "ARTIFACT_NOT_REVIEWABLE",
          message: "artifact already left pending_review",
        });
      }
      // Approving an entity candidate records additive cross-aliases only —
      // the entities stay separate rows (merging needs entity.merge).
      const resolutionMeta: Record<string, unknown> =
        input.decision === "approved" && artifact.kind === "entity_resolution"
          ? mockResolutionApprove(artifact)
          : {};
      // Approving a cross-case candidate records a reviewed-relationship
      // artifact — never a merge and never a graph write.
      const crossCaseMeta: Record<string, unknown> =
        input.decision === "approved" && artifact.kind === "cross_case_link"
          ? mockCrossCaseApprove(artifact)
          : {};
      artifact.status = input.decision === "approved" ? "approved" : "rejected";
      artifact.review_note = input.note ?? null;
      artifact.reviewed_by = currentUser().record?.id ?? null;
      artifact.reviewed_at = isoNow();
      artifact.updated_at = isoNow();
      pushAudit(`derived_artifact.${input.decision}`, "derived_artifact", caseId, {
        artifact_id: artifact.id,
        kind: artifact.kind,
        content_hash: artifact.content_hash,
        ...resolutionMeta,
        ...crossCaseMeta,
      });
      return artifact;
    },

    async verifyIntegrity(
      caseId: string,
      evidenceFileId: string,
    ): Promise<IntegrityVerificationResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const item = mockEvidenceFor(caseId, evidenceFileId);
      // The mock's storage is self-consistent: re-hashing the "bytes" always
      // reproduces the recorded digest, so the honest result here is `match`.
      const artifact: DerivedArtifactOut = {
        id: nextIntelId(),
        case_id: caseId,
        kind: "integrity_verification",
        origin: "deterministic",
        status: "recorded",
        validation_status: "valid",
        evidence_file_id: evidenceFileId,
        source_record_id: null,
        source_locator: null,
        payload: {
          type: "hash_verification",
          status: "match",
          algorithm: "sha256",
          expected_sha256: item.sha256,
          calculated_sha256: item.sha256,
          object_present: true,
        },
        content_hash: `verify-${evidenceFileId}`,
        parser_version: "deterministic:1",
        prompt_version: null,
        model_profile: null,
        analysis_job_id: null,
        validation_errors: null,
        review_note: null,
        reviewed_by: null,
        reviewed_at: null,
        parent_artifact_id: null,
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      artifactsState.unshift(artifact);
      pushAudit("integrity.verified", "evidence_file", caseId, {
        evidence_file_id: evidenceFileId,
        status: "match",
      });
      return {
        evidence_id: evidenceFileId,
        artifact_id: artifact.id,
        status: "match",
        algorithm: "sha256",
        expected_sha256: item.sha256,
        calculated_sha256: item.sha256,
        object_present: true,
        file_size_bytes: item.file_size,
        duration_ms: 3,
        verified_at: isoNow(),
      };
    },

    async custodyAudit(caseId: string, evidenceFileId?: string | null): Promise<JobSubmitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("ingestion.run");
      assertCaseAccess(caseId);
      const active = intelJobsState.find(
        (j) =>
          j.case_id === caseId &&
          j.feature === "custody" &&
          (j.status === "pending" || j.status === "running"),
      );
      if (active) {
        throw new ApiError({
          status: 409,
          code: "CUSTODY_AUDIT_ACTIVE",
          message: "a custody audit is already active for this case",
        });
      }
      // Deterministic rule engine (mirror of the backend's unacknowledged-transfer
      // rule): a transfer with no later receipt produces one finding, deduped by
      // (evidence, event, rule).
      let findingsNew = 0;
      let findingsExisting = 0;
      const targets = custodyEventsState.filter(
        (e) => e.case_id === caseId && (!evidenceFileId || e.evidence_file_id === evidenceFileId),
      );
      const byEvidence = new Map<string, CustodyEventOut[]>();
      for (const event of targets) {
        const key = event.evidence_file_id ?? "";
        byEvidence.set(key, [...(byEvidence.get(key) ?? []), event]);
      }
      let evidenceChecked = 0;
      for (const [eid, events] of byEvidence) {
        if (!eid) continue;
        evidenceChecked += 1;
        const receipts = events.filter((e) => e.event_type === "received");
        for (const transfer of events.filter((e) => e.event_type === "transferred")) {
          const acknowledged = receipts.some((r) => r.occurred_at >= transfer.occurred_at);
          if (acknowledged) continue;
          const duplicate = artifactsState.find(
            (a) =>
              a.case_id === caseId &&
              a.kind === "custody_finding" &&
              (a.payload as { rule?: string; event_id?: string }).rule ===
                "custody.unacknowledged_transfer" &&
              (a.payload as { event_id?: string }).event_id === transfer.id,
          );
          if (duplicate) {
            findingsExisting += 1;
            continue;
          }
          artifactsState.unshift({
            id: nextIntelId(),
            case_id: caseId,
            kind: "custody_finding",
            origin: "deterministic",
            status: "pending_review",
            validation_status: "valid",
            evidence_file_id: eid,
            source_record_id: null,
            source_locator: { custody_event_id: transfer.id },
            payload: {
              type: "custody_finding",
              rule: "custody.unacknowledged_transfer",
              severity: "warning",
              message: `transfer ${transfer.id} has no received event after it`,
              evidence_id: eid,
              event_id: transfer.id,
              transferor: transfer.transferor,
              recipient: transfer.recipient,
              occurred_at: transfer.occurred_at,
            },
            content_hash: `finding-${transfer.id}`,
            parser_version: "deterministic:1",
            prompt_version: null,
            model_profile: null,
            analysis_job_id: null,
            validation_errors: null,
            review_note: null,
            reviewed_by: null,
            reviewed_at: null,
            parent_artifact_id: null,
            created_at: isoNow(),
            updated_at: isoNow(),
          });
          findingsNew += 1;
        }
      }
      const job: AnalysisJobOut = {
        id: nextIntelId(),
        case_id: caseId,
        feature: "custody",
        status: "succeeded",
        idempotency_key: `custody:${evidenceFileId ?? "case"}:${isoNow()}`,
        progress: 100,
        total_records: evidenceChecked,
        processed_records: evidenceChecked,
        attempts: 1,
        timeout_seconds: 600,
        cancel_requested: false,
        error: null,
        result_summary: {
          evidence_checked: evidenceChecked,
          custody_events: targets.length,
          findings_new: findingsNew,
          findings_existing: findingsExisting,
          hash_match: evidenceChecked,
          hash_mismatch: 0,
          hash_unavailable: 0,
          orphaned_events: 0,
          error_code: null,
        },
        evidence_file_id: evidenceFileId ?? null,
        actor_id: currentUser().record?.id ?? null,
        started_at: isoNow(),
        completed_at: isoNow(),
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      intelJobsState.unshift(job);
      pushAudit("custody.audit_completed", "analysis_job", caseId, {
        status: "succeeded",
        findings_new: findingsNew,
        findings_existing: findingsExisting,
      });
      return { job, duplicate: false };
    },

    async custodyChronology(
      caseId: string,
      evidenceId: string,
    ): Promise<CustodyChronologyResponse> {
      await delay(MOCK_LATENCY);
      assertCaseAccess(caseId);
      const item = mockEvidenceFor(caseId, evidenceId);
      const events = custodyEventsState
        .filter((e) => e.evidence_file_id === evidenceId)
        .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
      const recycled = recycleState.find((e) => e.id === evidenceId);
      return {
        evidence_id: evidenceId,
        original_filename: item.original_filename,
        sha256: item.sha256,
        algorithm: "sha256",
        format: item.format,
        file_size: item.file_size,
        created_at: item.created_at,
        deleted_at: recycled ? isoNow() : null,
        events,
        event_count: events.length,
      };
    },

    async recordCustodyEvent(
      caseId: string,
      evidenceId: string,
      input: CustodyEventCreateRequest,
    ): Promise<CustodyEventOut> {
      await delay(MOCK_LATENCY);
      requirePermission("evidence.upload");
      assertCaseAccess(caseId);
      const item = mockEvidenceFor(caseId, evidenceId);
      if (!CUSTODY_EVENT_TYPES.includes(input.event_type)) {
        throw new ApiError({
          status: 422,
          code: "INVALID_PAYLOAD",
          message: `unknown custody event type '${input.event_type}'`,
        });
      }
      if (
        !/[zZ]|[+-]\d\d:?\d\d$/.test(input.occurred_at) ||
        Number.isNaN(Date.parse(input.occurred_at))
      ) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "occurred_at must be an ISO-8601 timestamp with an explicit time zone",
        });
      }
      if (Date.parse(input.occurred_at) > Date.now() + 300_000) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "occurred_at cannot be more than 300 seconds in the future",
        });
      }
      const required = CUSTODY_REQUIRED_FIELDS[input.event_type] ?? [];
      const missing = required.filter(
        (f) => !String(input[f as keyof CustodyEventCreateRequest] ?? "").trim(),
      );
      if (missing.length) {
        throw new ApiError({
          status: 422,
          code: "CUSTODY_FIELD_REQUIRED",
          message: `'${input.event_type}' custody event requires: ${missing.join(", ")}`,
        });
      }
      if (input.recorded_sha256 && !/^[0-9a-f]{64}$/i.test(input.recorded_sha256)) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "recorded_sha256 must be a 64-character sha256 hex digest",
        });
      }
      void item;
      const event: CustodyEventOut = {
        id: nextIntelId(),
        case_id: caseId,
        evidence_file_id: evidenceId,
        event_type: input.event_type,
        occurred_at: input.occurred_at,
        recorded_at: isoNow(),
        actor_user_id: currentUser().record?.id ?? null,
        collector: input.collector ?? null,
        transferor: input.transferor ?? null,
        recipient: input.recipient ?? null,
        location: input.location ?? null,
        method: input.method ?? null,
        notes: input.notes ?? null,
        recorded_sha256: input.recorded_sha256 ?? null,
      };
      custodyEventsState.push(event);
      pushAudit("custody.event_recorded", "evidence_file", caseId, {
        evidence_file_id: evidenceId,
        event_type: input.event_type,
      });
      return event;
    },

    async explainFinding(caseId: string, artifactId: string): Promise<CustodyExplainResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("evidence.read");
      assertCaseAccess(caseId);
      const finding = artifactsState.find((a) => a.id === artifactId && a.case_id === caseId);
      if (!finding) throw notFound("artifact not found");
      // Phase 4 dispatch: same kind-based routing as the real explain route.
      if (finding.kind === "financial_finding") return mockExplainFinancial(finding);
      if (finding.kind === "cross_case_link") return mockExplainCrossCase(finding);
      const payload = finding.payload as { type?: string; rule?: string };
      if (finding.kind !== "custody_finding" || payload.type !== "custody_finding") {
        throw new ApiError({
          status: 422,
          code: "ARTIFACT_KIND_UNSUPPORTED",
          message:
            "only custody findings can be explained; hash verifications are deterministic facts",
        });
      }
      const rule = payload.rule ?? "custody.finding";
      const explanation: DerivedArtifactOut = {
        id: nextIntelId(),
        case_id: caseId,
        kind: "custody_finding",
        origin: "llm",
        status: "recorded",
        validation_status: "flagged",
        evidence_file_id: finding.evidence_file_id,
        source_record_id: null,
        source_locator: finding.source_locator,
        payload: {
          type: "ai_explanation",
          for_artifact_id: finding.id,
          rule,
          text: `Rule ${rule} was recorded from the custody events listed on the finding; the model verified no files and cannot certify the chain of custody.`,
        },
        content_hash: `explain-${finding.id}`,
        parser_version: "deterministic:1",
        prompt_version: "1.0.0",
        model_profile: "explain",
        analysis_job_id: null,
        validation_errors: [
          {
            field: "text",
            code: "ai_unverified",
            message: "AI-generated narration; unreviewed and unverified",
          },
        ],
        review_note: null,
        reviewed_by: null,
        reviewed_at: null,
        parent_artifact_id: finding.id,
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      artifactsState.unshift(explanation);
      pushAudit("custody.explanation_generated", "derived_artifact", caseId, {
        for_artifact_id: finding.id,
      });
      return {
        explanation_artifact: explanation,
        text: explanation.payload.text as string,
        rule,
      };
    },

    /* ------------------ Case intelligence (phase 3) ------------------ */

    async submitEntityResolution(caseId: string): Promise<JobSubmitResponse> {
      return submitAnalysisFeature(caseId, "entity_resolution");
    },

    async submitTimelineReconstruction(caseId: string): Promise<JobSubmitResponse> {
      return submitAnalysisFeature(caseId, "timeline");
    },

    async submitContradictions(caseId: string): Promise<JobSubmitResponse> {
      return submitAnalysisFeature(caseId, "contradiction");
    },

    async submitFinancialFlow(caseId: string): Promise<JobSubmitResponse> {
      return submitAnalysisFeature(caseId, "financial_flow");
    },

    async traceFinancialFlow(caseId: string, input: FlowTraceRequest): Promise<FlowTraceResponse> {
      await delay(MOCK_LATENCY);
      requirePermission("evidence.read");
      assertCaseAccess(caseId);
      return traceMockFlow(caseId, input);
    },

    /* ------------------ Cross-case discovery (phase 4, feature B) ------------------ */

    async submitCrossCaseDiscover(input: CrossCaseDiscoverInput): Promise<JobSubmitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("crosscase.read");
      const anchor = input.anchor_case_id;
      assertCaseAccess(anchor);
      const ids = input.case_ids;
      if (ids.length < 2 || ids.length > 25 || !ids.includes(anchor)) {
        throw new ApiError({
          status: 422,
          code: "INVALID_PAYLOAD",
          message: "scope must be 2–25 cases and include the anchor case",
        });
      }
      // Fail closed with no disclosure: never name which scope case is missing.
      if (ids.some((id) => !canAccessCase(id))) {
        throw new ApiError({
          status: 404,
          code: "CROSS_CASE_SCOPE_DENIED",
          message: "cross-case scope is not fully authorized for this caller",
        });
      }
      const active = intelJobsState.find(
        (j) =>
          j.case_id === anchor &&
          j.feature === "cross_case" &&
          (j.status === "pending" || j.status === "running"),
      );
      if (active) {
        throw new ApiError({
          status: 409,
          code: "CROSS_CASE_ACTIVE",
          message: "a cross-case run is already active for this case",
        });
      }
      const attempts =
        intelJobsState.filter((j) => j.case_id === anchor && j.feature === "cross_case").length + 1;
      const job: AnalysisJobOut = {
        id: nextIntelId(),
        case_id: anchor,
        feature: "cross_case",
        status: "succeeded",
        idempotency_key: `cross_case:${anchor}:a${attempts}`,
        progress: 100,
        total_records: ids.length,
        processed_records: ids.length,
        attempts,
        timeout_seconds: 300,
        cancel_requested: false,
        error: null,
        result_summary: {},
        evidence_file_id: null,
        actor_id: currentUser().record?.id ?? null,
        started_at: isoNow(),
        completed_at: isoNow(),
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      const candidate = mockCrossCaseCandidate(anchor, ids, job.id);
      const reuse = artifactsState.some(
        (a) => a.case_id === anchor && a.content_hash === candidate.content_hash,
      );
      if (!reuse) artifactsState.unshift(candidate);
      job.result_summary = {
        cases_scanned: ids.length,
        scope_case_ids: ids,
        scope_hash: `scope-${ids.length}`,
        records_scanned: 0,
        records_bounded: false,
        candidates_found: 1,
        candidates_created: reuse ? 0 : 1,
        candidates_reused: reuse ? 1 : 0,
        candidates_pending_review: 1,
        cases_inaccessible: 0,
      };
      intelJobsState.unshift(job);
      pushAudit("cross_case.search_submitted", "analysis_job", anchor, {
        feature: "cross_case",
        attempt: attempts,
      });
      pushAudit("cross_case.analysis_completed", "analysis_job", anchor, {
        ...(job.result_summary as Record<string, unknown>),
      });
      return { job, duplicate: false };
    },

    async crossCaseCandidates(anchorCaseId: string): Promise<CrossCaseCandidateListResponse> {
      await delay(MOCK_LATENCY);
      requirePermission("crosscase.read");
      assertCaseAccess(anchorCaseId);
      const all = artifactsState.filter(
        (a) => a.case_id === anchorCaseId && a.kind === "cross_case_link",
      );
      // Read-time recheck: a candidate touching an inaccessible case is omitted
      // entirely — not redacted, not counted.
      const visible = all.filter((artifact) => {
        const payload = artifact.payload as CrossCaseCandidatePayload;
        return (payload.sides ?? []).every((side) => canAccessCase(side.case_id));
      });
      return {
        items: visible,
        total: visible.length,
        anchor_case_id: anchorCaseId,
        crosscase_rules_version: MOCK_CROSSCASE_RULES_VERSION,
        graph_freshness_note: MOCK_CROSSCASE_GRAPH_NOTE,
      };
    },

    async commitTimelineProposal(
      caseId: string,
      artifactId: string,
    ): Promise<TimelineCommitResponse> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("case.update");
      assertCaseAccess(caseId);
      const artifact = artifactsState.find((a) => a.id === artifactId && a.case_id === caseId);
      if (!artifact) throw notFound("proposal not found");
      if (artifact.kind !== "timeline_proposal") {
        throw new ApiError({
          status: 422,
          code: "ARTIFACT_KIND_UNSUPPORTED",
          message: "artifact is not a timeline proposal",
        });
      }
      const payload = artifact.payload as {
        title?: string;
        description?: string | null;
        occurred_at?: string | null;
        original_timestamp?: string;
        kind?: string;
        proposal_key?: string;
        time_semantics?: string;
        tz_assumed?: boolean;
        missing_timestamp?: boolean;
      };
      if (artifact.status !== "approved") {
        throw new ApiError({
          status: 409,
          code: "PROPOSAL_NOT_APPROVED",
          message: "proposal must be approved before it can be committed",
        });
      }
      if (payload.missing_timestamp || !payload.occurred_at) {
        throw new ApiError({
          status: 422,
          code: "TIMELINE_TIMESTAMP_MISSING",
          message: "no timestamp was established for this proposal; it cannot be committed",
        });
      }
      // Idempotency: one event per proposal key — a retry returns the same row.
      const key = payload.proposal_key ?? `artifact-${artifact.id}`;
      const existing = timelineState.find(
        (event) =>
          event.case_id === caseId &&
          (event.payload as { proposal_key?: unknown } | null)?.proposal_key === key,
      );
      if (existing) {
        pushAudit("reconstruction.proposal_committed", "timeline_event", caseId, {
          proposal_artifact_id: artifact.id,
          duplicate: true,
        });
        return { event: existing, duplicate: true };
      }
      const event: TimelineEvent = {
        id: nextIntelId(),
        case_id: caseId,
        occurred_at: payload.occurred_at,
        kind: payload.kind ?? "case_event",
        title: payload.title ?? "Reconstructed event",
        description: payload.description ?? null,
        entity_id: null,
        evidence_file_id: null,
        collection_id: null,
        device_id: null,
        actor_user_id: currentUser().record?.id ?? null,
        payload: {
          origin: "timeline_reconstruction",
          proposal_artifact_id: artifact.id,
          proposal_key: key,
          original_timestamp: payload.original_timestamp ?? null,
          time_semantics: payload.time_semantics ?? null,
          tz_assumed: payload.tz_assumed ?? false,
        },
        created_at: isoNow(),
      };
      timelineState.push(event);
      pushAudit("reconstruction.proposal_committed", "timeline_event", caseId, {
        proposal_artifact_id: artifact.id,
        duplicate: false,
        occurred_at: event.occurred_at,
      });
      return { event, duplicate: false };
    },

    async resolveContradiction(
      caseId: string,
      artifactId: string,
      input: ContradictionResolveRequest,
    ): Promise<DerivedArtifactOut> {
      await delay(MOCK_LATENCY * 2);
      requirePermission("findings.review");
      assertCaseAccess(caseId);
      const allowed = ["explained", "requires_evidence", "deferred"];
      if (!allowed.includes(input.state)) {
        throw new ApiError({
          status: 422,
          code: "CONTRADICTION_STATE_INVALID",
          message: `unknown contradiction state '${input.state}' (expected one of: ${allowed.join(", ")})`,
        });
      }
      if (!input.note?.trim()) {
        throw new ApiError({
          status: 422,
          code: "REVIEW_NOTE_REQUIRED",
          message: "a resolution note is required for every state",
        });
      }
      const parent = artifactsState.find((a) => a.id === artifactId && a.case_id === caseId);
      if (!parent) throw notFound("artifact not found");
      if (
        parent.kind !== "contradiction" ||
        (parent.payload as { type?: string }).type !== "contradiction"
      ) {
        throw new ApiError({
          status: 422,
          code: "ARTIFACT_KIND_UNSUPPORTED",
          message: "artifact is not a contradiction candidate",
        });
      }
      if (parent.status !== "pending_review") {
        throw new ApiError({
          status: 409,
          code: "ARTIFACT_NOT_REVIEWABLE",
          message: `candidate is ${parent.status}; only unresolved candidates accept resolution states`,
        });
      }
      // Appended child artifact: the candidate payload stays byte-for-byte intact.
      const child: DerivedArtifactOut = {
        id: nextIntelId(),
        case_id: caseId,
        kind: "contradiction",
        origin: "deterministic",
        status: "recorded",
        validation_status: "valid",
        evidence_file_id: parent.evidence_file_id,
        source_record_id: parent.source_record_id,
        source_locator: parent.source_locator,
        payload: {
          type: "contradiction_review",
          state: input.state,
          note: input.note.trim().slice(0, 2000),
          for_artifact_id: parent.id,
        },
        content_hash: `review-${parent.id}-${input.state}`,
        parser_version: "contradiction_review:1.0.0",
        prompt_version: null,
        model_profile: null,
        analysis_job_id: null,
        validation_errors: null,
        review_note: input.note.trim().slice(0, 2000),
        reviewed_by: currentUser().record?.id ?? null,
        reviewed_at: isoNow(),
        parent_artifact_id: parent.id,
        created_at: isoNow(),
        updated_at: isoNow(),
      };
      artifactsState.unshift(child);
      pushAudit(`contradiction.${input.state}`, "derived_artifact", caseId, {
        state: input.state,
        child_artifact_id: child.id,
        child_content_hash: child.content_hash,
      });
      return child;
    },
  },

  graph: {
    async get(caseId: string): Promise<GraphResponse> {
      await delay(MOCK_LATENCY * 2);
      assertCaseAccess(caseId);
      if (caseId === CASE_ID_MAIN)
        return { case_id: caseId, nodes: MAIN_GRAPH_NODES, edges: MAIN_GRAPH_EDGES };
      if (caseId === CASE_ID_SECONDARY) {
        return {
          case_id: caseId,
          nodes: SECONDARY_CASE_DATA.graphNodes,
          edges: SECONDARY_CASE_DATA.graphEdges,
        };
      }
      if (caseId === CASE_ID_CLOSED)
        return { case_id: caseId, nodes: CLOSED_CASE_GRAPH.nodes, edges: CLOSED_CASE_GRAPH.edges };
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
      if (caseId === CASE_ID_SECONDARY)
        return [
          {
            community_id: "C1",
            member_count: 6,
            density: 0.35,
            internal_edges: 5,
            external_edges: 2,
            dominant_entity_types: ["person", "organization"],
            dominant_relationship_types: ["works_for"],
            member_entity_ids: [],
            score: 0.6,
            explanation: "Single import operation.",
          },
        ];
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
                {
                  entity_id: SECONDARY_CASE_DATA.entities[0].id,
                  entity_type: "person",
                  display_value: "Dinesh Sawant",
                  overall_score: 0.62,
                  tier: "MONITORED" as const,
                  features: {},
                  signals: [],
                  explanation: "Central to manifest network.",
                },
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
      pushAudit("analytics.run_completed", "analytics_run", caseId, {
        status: "completed",
        stage: "complete",
      });
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
      let items =
        caseId === CASE_ID_MAIN
          ? findingsState
          : caseId === CASE_ID_SECONDARY
            ? SECONDARY_CASE_DATA.findings
            : [];
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
      const items =
        caseId === CASE_ID_MAIN
          ? findingsState
          : caseId === CASE_ID_SECONDARY
            ? SECONDARY_CASE_DATA.findings
            : [];
      void runId;
      return findingsStatsFor(items);
    },

    async updateStatus(
      caseId: string,
      findingId: string,
      input: { status: string; reason?: string | null },
    ): Promise<FindingStatusOut> {
      await delay(MOCK_LATENCY);
      const user = requirePermission(permissionForStatus(input.status));
      assertCaseAccess(caseId);
      const finding = findingsState.find((f) => f.id === findingId);
      if (!finding) throw notFound("finding not found");
      const previous = finding.status;
      const isClosed = finding.status === "DISMISSED" || finding.status === "CONFIRMED";
      const isAdmin = user.roles.includes("ADMIN");
      if (isClosed && previous !== input.status && !isAdmin) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: "closed findings are immutable except by ADMIN",
        });
      }
      const changed = previous !== input.status;
      finding.status = input.status as Finding["status"];
      finding.reviewed_by = user.id;
      finding.reviewed_at = new Date().toISOString();
      finding.review_comment = input.reason ?? null;
      if (changed) {
        pushAudit("finding.status_changed", "finding", caseId, {
          from: previous,
          to: input.status,
          reason: input.reason,
        });
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
      if (params.resource_type)
        items = items.filter((e) => e.resource_type === params.resource_type);
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
        items = items.filter(
          (d) => d.name.toLowerCase().includes(q) || d.serial_number.toLowerCase().includes(q),
        );
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
      if (
        iotDeviceState.some((d) => d.case_id === caseId && d.serial_number === input.serial_number)
      ) {
        throw new ApiError({
          status: 409,
          code: "CONFLICT",
          message: "a device with this serial number is already registered",
        });
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
      pushAudit("iot.device_registered", "iot_device", device.id, {
        case_id: caseId,
        name: device.name,
      });
      return device;
    },
    async updateDevice(
      caseId: string,
      deviceId: string,
      input: IoTDeviceUpdateRequest,
    ): Promise<IoTDevice> {
      await delay(MOCK_LATENCY);
      const idx = iotDeviceState.findIndex((x) => x.id === deviceId && x.case_id === caseId);
      if (idx === -1) throw notFound("iot device not found");
      const d = iotDeviceState[idx];
      for (const [k, val] of Object.entries(input)) {
        if (val !== undefined) (d as unknown as Record<string, unknown>)[k] = val;
      }
      d.updated_at = iso(Date.now());
      pushAudit("iot.device_updated", "iot_device", d.id, {
        case_id: caseId,
        fields: Object.keys(input),
      });
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
      pushAudit("iot.event_recorded", "iot_event", event.id, {
        case_id: caseId,
        device_id: event.device_id,
        event_type: event.event_type,
      });
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
      pushAudit("timeline.event_recorded", "timeline_event", caseId, {
        kind: event.kind,
        title: event.title,
      });
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

    async update(
      caseId: string,
      collectionId: string,
      input: CollectionUpdateRequest,
    ): Promise<Collection> {
      await delay(MOCK_LATENCY);
      requirePermission("case.update");
      assertCaseAccess(caseId);
      const c = collectionsState.find((x) => x.id === collectionId && x.case_id === caseId);
      if (!c) throw notFound("collection not found");
      if (c.status === "sealed") {
        throw new ApiError({
          status: 409,
          code: "CONFLICT",
          message: "sealed collections cannot be modified",
        });
      }
      if (input.name !== undefined && input.name !== null) c.name = input.name;
      if (input.description !== undefined && input.description !== null)
        c.description = input.description;
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
      pushAudit("device.registered", "field_device", caseId, {
        serial: device.serial,
        platform: device.platform,
      });
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

    async verifyKey(
      caseId: string,
      deviceId: string,
      input: DeviceVerifyRequest,
    ): Promise<DeviceVerifyResponse> {
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

  ai: {
    async status(): Promise<AiStatus> {
      await delay(MOCK_LATENCY);
      return {
        enabled: true,
        ready: true,
        managed: false,
        model_configured: "Qwen3-8B-Q4_K_M.gguf",
        model_valid: true,
        context_length: 4096,
        max_output_tokens: 512,
        gpu_layers: -1,
        started: true,
        load_seconds: 12.4,
        restarts: 1,
        requests_total: 3,
        errors_total: 0,
        generations_active: 0,
        last_error: null,
        prompt_version: "1.0.0",
        tools: ["get_case_summary", "list_evidence", "search_cases", "search_knowledge"],
        feature_flags: {
          case: true,
          evidence: true,
          graph: true,
          copilot: true,
          report_draft: true,
          knowledge: true,
        },
      };
    },
    async chat(input: AiChatInput): Promise<AiChatResult> {
      await delay(MOCK_LATENCY);
      const sources: AiSource[] = input.case_id
        ? [
            {
              type: "case",
              id: input.case_id,
              label: "SHOW-2026-005",
              url: `/cases/${input.case_id}`,
            },
            { type: "evidence", id: "ev-mock-1", label: "call_detail_record.csv" },
          ]
        : [{ type: "knowledge", id: "README.md#overview", label: "overview" }];
      const answer = input.case_id
        ? "This case has 2 entities and 1 evidence file [evidence:ev-mock-1]. The primary lead is the uploaded call-detail record. (Mock assistant answer.)"
        : "CyberSaarthi stores evidence, entities and findings per case. (Mock assistant answer.)";

      // Multi-turn: reuse the requested thread when it exists, otherwise open a new
      // one. Every exchange (user + assistant) is persisted for the history view.
      const now = new Date().toISOString();
      let conversation =
        input.conversation_id != null
          ? aiConversationsState.find((c) => c.id === input.conversation_id)
          : undefined;
      if (!conversation) {
        conversation = {
          id: `conv-mock-${aiConversationSeq++}`,
          case_id: input.case_id ?? null,
          title: titleFromQuestion(input.question),
          mode: input.mode ?? "general",
          status: "active",
          prompt_version: "1.0.0",
          created_at: now,
          updated_at: now,
          last_message_at: now,
        };
        aiConversationsState.push(conversation);
      } else {
        conversation.updated_at = now;
        conversation.last_message_at = now;
      }
      const thread = (aiMessagesByConversation[conversation.id] ??= []);
      const base = thread.length;
      thread.push(
        {
          id: `msg-${conversation.id}-${base}-u`,
          role: "user",
          content: input.question,
          sources: [],
          tool_events: [],
          grounded: false,
          prompt_version: "1.0.0",
          created_at: now,
        },
        {
          id: `msg-${conversation.id}-${base + 1}-a`,
          role: "assistant",
          content: answer,
          sources,
          tool_events: [],
          grounded: true,
          prompt_version: "1.0.0",
          created_at: now,
        },
      );

      return {
        answer,
        conversation_id: conversation.id,
        message_id: `msg-${conversation.id}-${base + 1}-a`,
        sources,
        tool_events: [],
        grounded: true,
        prompt_version: "1.0.0",
        duration_ms: 420,
        first_token_ms: 90,
        prompt_tokens: 320,
        completion_tokens: 48,
      };
    },
    async chatStream(input: AiChatInput, callbacks: AiStreamCallbacks): Promise<void> {
      const result = await this.chat(input);
      // Mirror the real backend's tool loop: when the turn is case-scoped the
      // model first streams a raw tool fence, then a `tool` event arrives and
      // only afterwards the real answer tokens (clients must drop the fence).
      if (input.case_id) {
        callbacks.onToken?.('{"tool": "get_case_summary", "arguments": {"case_id": "');
        callbacks.onToken?.(`${input.case_id}"}} `);
        callbacks.onTool?.({
          tool: "get_case_summary",
          ok: true,
          arguments: { case_id: input.case_id },
        });
      }
      const words = result.answer.split(" ");
      for (const word of words) {
        callbacks.onToken?.(`${word} `);
      }
      callbacks.onSources?.(result.sources);
      callbacks.onDone?.({
        answer: result.answer,
        // Forward the thread id when the transport knows it (the real SSE backend
        // does not send it yet; consumers fall back to listConversations).
        conversation_id: result.conversation_id,
        grounded: result.grounded,
        sources: result.sources,
        tool_events: result.tool_events,
        duration_ms: result.duration_ms,
        first_token_ms: result.first_token_ms,
        completion_tokens: result.completion_tokens,
      });
    },
    async reportDraft(caseId: string): Promise<AiReportDraft> {
      await delay(MOCK_LATENCY);
      return {
        draft: `# Investigation draft — ${caseId}\n\nSummary: (mock draft for human review.)`,
        sources: [{ type: "case", id: caseId, label: "case", url: `/cases/${caseId}` }],
        grounded: true,
        prompt_version: "1.0.0",
        duration_ms: 900,
      };
    },
    async listConversations(
      params: { case_id?: string; limit?: number } = {},
    ): Promise<{ items: AiConversation[]; total: number }> {
      await delay(MOCK_LATENCY);
      const filtered = aiConversationsState
        .filter((c) => (params.case_id ? c.case_id === params.case_id : true))
        // Newest activity first so `{ limit: 1 }` returns the just-used thread.
        .sort((a, b) =>
          (b.last_message_at ?? b.updated_at).localeCompare(a.last_message_at ?? a.updated_at),
        );
      const items = filtered.slice(0, params.limit ?? 50).map((c) => ({ ...c }));
      return { items, total: filtered.length };
    },
    async listMessages(conversationId: string): Promise<{ items: AiMessage[] }> {
      await delay(MOCK_LATENCY);
      const thread = aiMessagesByConversation[conversationId];
      if (!thread) {
        throw new ApiError({ status: 404, code: "NOT_FOUND", message: "conversation not found" });
      }
      return { items: thread.map((m) => ({ ...m })) };
    },
    async renameConversation(conversationId: string, title: string): Promise<AiConversation> {
      await delay(MOCK_LATENCY);
      const conversation = aiConversationsState.find((c) => c.id === conversationId);
      if (!conversation) {
        throw new ApiError({ status: 404, code: "NOT_FOUND", message: "conversation not found" });
      }
      const next = title.trim();
      if (next) {
        conversation.title = next;
        conversation.updated_at = new Date().toISOString();
      }
      return { ...conversation };
    },
    async deleteConversation(conversationId: string): Promise<void> {
      await delay(MOCK_LATENCY);
      const index = aiConversationsState.findIndex((c) => c.id === conversationId);
      if (index === -1) {
        throw new ApiError({ status: 404, code: "NOT_FOUND", message: "conversation not found" });
      }
      aiConversationsState.splice(index, 1);
      delete aiMessagesByConversation[conversationId];
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
      const known = [
        "case_summary",
        "intelligence",
        "evidence_manifest",
        "network_analysis",
        "timeline",
      ];
      const report: Report = {
        id: uid(2600 + reportsState.length),
        case_id: caseId,
        report_type: input.report_type,
        format: input.format ?? "json",
        title:
          input.title ??
          `${input.report_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())} - Case`,
        status: known.includes(input.report_type) ? "ready" : "failed",
        byte_size: known.includes(input.report_type) ? 24680 : null,
        failure_reason: known.includes(input.report_type)
          ? null
          : `unknown report type '${input.report_type}'`,
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
      const blob = new Blob(
        [
          JSON.stringify(
            { report_type: r.report_type, case_id: caseId, generated_at: r.created_at },
            null,
            2,
          ),
        ],
        {
          type: "application/json",
        },
      );
      return { blob, filename: `${r.report_type}-report.json` };
    },
  },

  hypotheses: {
    async list(
      caseId: string,
      params: InvestigationHypothesisListParams = {},
    ): Promise<InvestigationHypothesisList> {
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
      pushAudit("hypothesis.created", "hypothesis", caseId, {
        title: created.title,
        kind: created.kind,
      });
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

    async updateStatus(
      caseId: string,
      hypothesisId: string,
      status: string,
    ): Promise<InvestigationHypothesis> {
      await delay(MOCK_LATENCY);
      const user = requirePermission("findings.review");
      assertCaseAccess(caseId);
      const h = hypothesesState.find((x) => x.id === hypothesisId && x.case_id === caseId);
      if (!h) throw notFound("hypothesis not found");
      const valid = [
        "proposed",
        "under_review",
        "supported",
        "contradicted",
        "dismissed",
        "concluded",
      ];
      if (!valid.includes(status)) {
        throw new ApiError({
          status: 422,
          code: "VALIDATION_ERROR",
          message: `invalid hypothesis status '${status}'`,
        });
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

    async linkEvidence(
      caseId: string,
      hypothesisId: string,
      input,
    ): Promise<InvestigationHypothesis> {
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
            results.push({
              kind: "entity",
              id: e.id,
              title: e.display_value,
              subtitle: e.entity_type,
              url: `/app/cases/${caseId}/entities/${e.id}`,
            });
          }
        }
        for (const item of evidenceState) {
          if (item.original_filename.toLowerCase().includes(q)) {
            results.push({
              kind: "evidence",
              id: item.id,
              title: item.original_filename,
              subtitle: item.format ?? null,
              url: `/app/cases/${caseId}/evidence`,
            });
          }
        }
        for (const f of MAIN_FINDINGS) {
          if (f.title.toLowerCase().includes(q)) {
            results.push({
              kind: "finding",
              id: f.id,
              title: f.title,
              subtitle: f.finding_type,
              url: `/app/cases/${caseId}/findings/${f.id}`,
            });
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

/* ------------------ Case intelligence (phase 3) ------------------ */

type AnalysisFeature =
  "entity_resolution" | "timeline" | "contradiction" | "financial_flow" | "cross_case";

/** Mirrors the backend submit route: refusal code, audit prefix, success action. */
const ANALYSIS_FEATURES: Record<
  AnalysisFeature,
  { audit: string; activeCode: ApiErrorCode; successAction: string }
> = {
  entity_resolution: {
    audit: "resolution",
    activeCode: "RESOLUTION_ACTIVE",
    successAction: "resolution.analysis_completed",
  },
  timeline: {
    audit: "reconstruction",
    activeCode: "RECONSTRUCTION_ACTIVE",
    successAction: "reconstruction.completed",
  },
  contradiction: {
    audit: "contradiction",
    activeCode: "CONTRADICTION_ACTIVE",
    successAction: "contradiction.completed",
  },
  financial_flow: {
    audit: "flow",
    activeCode: "FLOW_ACTIVE",
    successAction: "flow.analysis_completed",
  },
  cross_case: {
    audit: "cross_case",
    activeCode: "CROSS_CASE_ACTIVE",
    successAction: "cross_case.analysis_completed",
  },
};

const RESOLUTION_MESSAGES: Record<string, string> = {
  no_identifier_evidence:
    "no shared identifier or alias; name or context similarity alone never proves identity",
  conflicting_identifiers:
    "the two entities carry disjoint identifier signals alongside the matching evidence",
  ai_unverified: "an LLM verdict is included; it is unverified and cannot certify identity",
};

/** Simplified deterministic similarity for mock candidates: 0-100 ratio. */
function nameSimilarity(a: string, b: string): number {
  if (!a.length || !b.length) return 0;
  const rows = Array.from({ length: a.length + 1 }, (_, i) => i);
  for (let j = 1; j <= b.length; j += 1) {
    let prev = rows[0];
    rows[0] = j;
    for (let i = 1; i <= a.length; i += 1) {
      const current = rows[i];
      rows[i] = Math.min(rows[i] + 1, rows[i - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = current;
    }
  }
  return Math.round((1 - rows[a.length] / Math.max(a.length, b.length)) * 10000) / 100;
}

/** Person blocking-key mirror: surname-prefix-3 + first initial (lowercased). */
function personBucket(canonical: string): string | null {
  const tokens = canonical.toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length < 2) return null;
  const [first, ...rest] = tokens;
  const last = rest[rest.length - 1];
  if (last.length < 3) return null;
  return `${last.slice(0, 3)}_${first[0]}`;
}

function scoreBand(score: number): "strong" | "ambiguous" | "weak" {
  if (score >= 92) return "strong";
  if (score >= 78) return "ambiguous";
  return "weak";
}

/** Indexed same-bucket person pairs (never an all-pairs scan). */
function mockResolutionPairs(caseId: string): Array<{ a: Entity; b: Entity; score: number }> {
  const people = entitiesFor(caseId).filter(
    (e) => e.entity_type === "person" && e.status === "active",
  );
  const buckets = new Map<string, Entity[]>();
  for (const person of people) {
    const key = personBucket(person.canonical_value);
    if (!key) continue;
    buckets.set(key, [...(buckets.get(key) ?? []), person]);
  }
  const pairs: Array<{ a: Entity; b: Entity; score: number }> = [];
  for (const group of buckets.values()) {
    for (let i = 0; i < group.length; i += 1) {
      for (let j = i + 1; j < group.length; j += 1) {
        const score = nameSimilarity(
          group[i].canonical_value.toLowerCase(),
          group[j].canonical_value.toLowerCase(),
        );
        if (score >= 78) pairs.push({ a: group[i], b: group[j], score });
      }
    }
  }
  return pairs;
}

function mockEntitySide(entity: Entity): Record<string, unknown> {
  return {
    id: entity.id,
    entity_type: entity.entity_type,
    canonical_value: entity.canonical_value,
    display_value: entity.display_value,
  };
}

function mockResolutionArtifact(
  caseId: string,
  jobId: string,
  pair: { a: Entity; b: Entity; score: number },
): DerivedArtifactOut {
  const codes = ["no_identifier_evidence"];
  return {
    id: nextIntelId(),
    case_id: caseId,
    kind: "entity_resolution",
    origin: "deterministic",
    status: "pending_review",
    validation_status: "flagged",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: { entity_a: pair.a.id, entity_b: pair.b.id },
    payload: {
      type: "entity_candidate",
      entity_a: mockEntitySide(pair.a),
      entity_b: mockEntitySide(pair.b),
      method: "name_similarity",
      score: pair.score,
      score_band: scoreBand(pair.score),
      score_semantics: "0-100 similarity band (not a probability)",
      name_similarity: pair.score,
      matching_fields: [{ field: "name_variant", detail: { similarity: pair.score } }],
      conflicting_fields: [],
      shared_identifiers: [],
      shared_source_record_ids: [],
      source_record_ids: [],
    },
    content_hash: `resolution-${pair.a.id}-${pair.b.id}`,
    parser_version: "entity_match:1.0.0",
    prompt_version: null,
    model_profile: null,
    analysis_job_id: jobId,
    validation_errors: codes.map((code) => ({
      field: "pair",
      code,
      message: RESOLUTION_MESSAGES[code],
    })),
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/**
 * Deterministic reconstruction snapshot: one date-only field, one zone-less
 * datetime (documented UTC assumption, flagged) and one unparseable strong
 * field (flagged `missing_timestamp`, never an invented instant). The mock has
 * no source records, so locators cite record 1 of the ingested file.
 */
const MOCK_RECONSTRUCTION_DRAFTS = [
  {
    field: "txn_date",
    original: "2026-03-15",
    title: "Transaction recorded on 2026-03-15",
    occurred_at: "2026-03-15T00:00:00+00:00",
    tz: null,
    tz_assumed: false,
    time_granularity: "date",
    time_semantics: "record_occurs_on",
    missing_timestamp: false,
    errors: [],
  },
  {
    field: "incident_at",
    original: "15/03/2026 14:30",
    title: "Incident recorded at 14:30",
    occurred_at: "2026-03-15T14:30:00+00:00",
    tz: null,
    tz_assumed: true,
    time_granularity: "datetime",
    time_semantics: "record_occurs_on",
    missing_timestamp: false,
    errors: [
      {
        field: "timestamp",
        code: "ambiguous_timezone",
        message:
          "the source timestamp has no time zone; it was interpreted as UTC for ordering and flagged",
      },
    ],
  },
  {
    field: "reported_at",
    original: "TBD",
    title: "Reported at TBD",
    occurred_at: null,
    tz: null,
    tz_assumed: false,
    time_granularity: null,
    time_semantics: "statement_refers_to_event",
    missing_timestamp: true,
    errors: [
      {
        field: "timestamp",
        code: "missing_timestamp",
        message:
          "no timestamp could be established from the source; this proposal cannot be committed until a reviewer supplies the time elsewhere",
      },
    ],
  },
] as const;

/** Stable proposal identity across retries (mirrors the backend key inputs). */
function mockProposalKey(draft: (typeof MOCK_RECONSTRUCTION_DRAFTS)[number]): string {
  return `proposal-${draft.field}-${draft.original}`;
}

function mockReconstructionArtifact(
  caseId: string,
  jobId: string,
  draft: (typeof MOCK_RECONSTRUCTION_DRAFTS)[number],
): DerivedArtifactOut {
  const flagged = draft.errors.length > 0;
  return {
    id: nextIntelId(),
    case_id: caseId,
    kind: "timeline_proposal",
    origin: "deterministic",
    status: "pending_review",
    validation_status: flagged ? "flagged" : "valid",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: { record_no: 1, field: draft.field },
    payload: {
      type: "timeline_proposal",
      kind: "case_event",
      title: draft.title,
      description: `Reconstructed from record 1 field ${draft.field}`,
      occurred_at: draft.occurred_at,
      original_timestamp: draft.original,
      tz: draft.tz,
      tz_assumed: draft.tz_assumed,
      time_granularity: draft.time_granularity,
      time_semantics: draft.time_semantics,
      missing_timestamp: draft.missing_timestamp,
      proposal_key: mockProposalKey(draft),
      evidence_file_id: null,
      source_record_id: null,
      source_locator: { record_no: 1, field: draft.field },
      flags: [],
    },
    content_hash: `reconstruction-${mockProposalKey(draft)}`,
    parser_version: "timeline_recon:1.0.0",
    prompt_version: null,
    model_profile: null,
    analysis_job_id: jobId,
    validation_errors: draft.errors.map((error) => ({ ...error })),
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/** Deterministic amount conflict on one shared transaction anchor. */
function mockContradictionArtifact(caseId: string, jobId: string): DerivedArtifactOut {
  const side = (recordNo: number, value: string): Record<string, unknown> => ({
    source_record_id: null,
    evidence_file_id: null,
    record_no: recordNo,
    field: "txn_amount",
    class: "amount",
    value,
    original: value,
    locator: { record_no: recordNo, field: "txn_amount" },
  });
  return {
    id: nextIntelId(),
    case_id: caseId,
    kind: "contradiction",
    origin: "deterministic",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: { record_no: 1, field: "txn_id" },
    payload: {
      type: "contradiction",
      category: "amount",
      rule: "contradiction.amount_disagreement",
      rule_version: "1.0.0",
      priority: "high",
      anchor: { value: "txn9001", scope: "transaction", fields: "txn_id" },
      first: side(1, "1500"),
      second: side(2, "2500"),
      conflicting_values: [
        {
          field: "txn_amount",
          first: "1500",
          second: "2500",
          first_original: "1500",
          second_original: "2500",
        },
      ],
      alternatives: [
        "currency_or_unit: the two records may use different units or minor units",
        "partial_payment: one record may capture a partial settlement",
        "data_entry_error: one of the two values may be a transcription mistake",
      ],
      explanation:
        "Both records reference txn9001 via 'txn_id', but 'txn_amount' differs: '1500' vs '2500'.",
    },
    content_hash: "contradiction-txn9001-txn_amount",
    parser_version: "1.0.0",
    prompt_version: null,
    model_profile: null,
    analysis_job_id: jobId,
    validation_errors: null,
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/** Resolution approvals add reviewed cross-aliases here — entities never merge. */
const resolutionAliasState: Record<
  string,
  Array<{ id: string; alias_value: string; alias_type: string }>
> = {};

function mockResolutionApprove(artifact: DerivedArtifactOut): {
  aliases_added: number;
  entity_a_id: string;
  entity_b_id: string;
} {
  const locator = artifact.source_locator as { entity_a?: string; entity_b?: string };
  const entityA = entitiesFor(artifact.case_id).find((e) => e.id === locator.entity_a);
  const entityB = entitiesFor(artifact.case_id).find((e) => e.id === locator.entity_b);
  if (!entityA || !entityB || entityA.status !== "active" || entityB.status !== "active") {
    throw new ApiError({
      status: 409,
      code: "CANDIDATE_ENTITY_UNAVAILABLE",
      message: "candidate entities are no longer available (missing or merged)",
    });
  }
  const added =
    recordResolutionAlias(entityA.id, entityB.canonical_value) +
    recordResolutionAlias(entityB.id, entityA.canonical_value);
  return { aliases_added: added, entity_a_id: entityA.id, entity_b_id: entityB.id };
}

function recordResolutionAlias(entityId: string, aliasValue: string): number {
  const existing = resolutionAliasState[entityId] ?? [];
  if (existing.some((a) => a.alias_value === aliasValue)) return 0;
  resolutionAliasState[entityId] = [
    ...existing,
    { id: nextIntelId(), alias_value: aliasValue, alias_type: "resolution" },
  ];
  return 1;
}

/**
 * Approving a cross-case candidate records a *reviewed relationship* artifact
 * (deterministic, parented by audit metadata) — mirroring the backend's B5
 * branch. No entity is merged and no graph is ever written.
 */
function mockCrossCaseApprove(artifact: DerivedArtifactOut): Record<string, unknown> {
  const payload = artifact.payload as CrossCaseCandidatePayload;
  const cases = [...new Set((payload.sides ?? []).map((side) => side.case_id))].sort();
  const child: DerivedArtifactOut = {
    ...artifact,
    id: nextIntelId(),
    status: "recorded",
    validation_status: "valid",
    payload: {
      type: "reviewed_cross_case_link",
      decision: "approved",
      indicator_kind: payload.group?.indicator_kind ?? "unknown",
      value_normalized: payload.group?.value_normalized ?? "",
      classification: payload.classification ?? "unknown",
      cases,
      for_artifact_id: artifact.id,
      reviewer_id: currentUser().record?.id ?? null,
    },
    content_hash: `reviewed-cross-case-${artifact.id}`,
    validation_errors: null,
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
  artifactsState.unshift(child);
  return { reviewed_child_artifact_id: child.id, reviewed_cases: cases };
}

/** Is this proposal already committed to the authoritative timeline? */
function committedProposalKeys(): Set<string> {
  const keys = new Set<string>();
  for (const event of timelineState) {
    const key = (event.payload as { proposal_key?: unknown } | null)?.proposal_key;
    if (typeof key === "string") keys.add(key);
  }
  return keys;
}

/**
 * One bounded case-wide run: one active job per feature (concurrent submit ->
 * typed 409), attempt-numbered idempotency keys, deterministic artifacts with
 * content-hash reuse on re-runs, completion audits mirroring the backend.
 */
/* ------------------ Financial flow (phase 4, feature A) ------------------ */

type MockFlowNode = { id: string; kind: string; label: string; origin: string };
type MockFlowEdge = {
  source: string;
  target: string;
  edge_kind: string;
  confidence: string;
  derivation: string;
  relationship_type: string | null;
  schema_confidence: number | null;
  supporting_source_record_ids: string[];
};
type MockFlowAdjacency = Record<string, Record<string, MockFlowEdge>>;

const MOCK_FLOW_RECORDS_SCANNED = 6;
const MOCK_FLOW_TRACE_MAX_DEPTH = 4;
const MOCK_FLOW_TRACE_MAX_PATHS = 50;
const MOCK_FLOW_MAX_RECORDS = 1000;
const MOCK_FLOW_RULES_VERSION = "flow-rules/1.0.0";
const MOCK_FLOW_PATTERNS_VERSION = "flow-patterns/1.0.0";

const mockFlowEdge = (source: string, target: string, ids: string[]): MockFlowEdge => ({
  source,
  target,
  edge_kind: "association",
  confidence: "suspected",
  derivation: "account_star",
  relationship_type: null,
  schema_confidence: null,
  supporting_source_record_ids: ids,
});

/**
 * Deterministic structure the mock computes over: the same shape the backend
 * derives from the fixtures (10 nodes, 7 association edges, zero transfers) so
 * the panel always shows the honest picture — association only, never a
 * confirmed transfer, and an empty trail rather than an invented one.
 */
const MOCK_FLOW_NODES: MockFlowNode[] = [
  { id: "account:ACCSIH001", kind: "account", label: "ACC-SIH-001", origin: "record" },
  {
    id: "merchant:phonepe merchant",
    kind: "merchant",
    label: "PhonePe Merchant",
    origin: "record",
  },
  { id: "party:ananya sirohi", kind: "party", label: "Ananya Sirohi", origin: "record" },
  { id: "account:ACCSIH002", kind: "account", label: "ACC-SIH-002", origin: "record" },
  { id: "merchant:paytm merchant", kind: "merchant", label: "Paytm Merchant", origin: "record" },
  { id: "party:rohan mehta", kind: "party", label: "Rohan Mehta", origin: "record" },
  {
    id: "beneficiary:ananya sirohi",
    kind: "beneficiary",
    label: "Ananya Sirohi",
    origin: "record",
  },
  { id: "account:3300445566", kind: "account", label: "3300445566", origin: "record" },
  { id: "bank:securemart", kind: "bank", label: "SecureMart", origin: "record" },
  { id: "party:sunita sharma", kind: "party", label: "Sunita Sharma", origin: "record" },
];

const MOCK_FLOW_EDGES: MockFlowEdge[] = [
  mockFlowEdge("account:ACCSIH001", "merchant:phonepe merchant", ["mock-rec-1"]),
  mockFlowEdge("account:ACCSIH001", "party:ananya sirohi", ["mock-rec-1"]),
  mockFlowEdge("account:ACCSIH002", "merchant:paytm merchant", ["mock-rec-2"]),
  mockFlowEdge("account:ACCSIH002", "party:rohan mehta", ["mock-rec-2"]),
  mockFlowEdge("account:ACCSIH001", "beneficiary:ananya sirohi", ["mock-rec-3", "mock-rec-4"]),
  mockFlowEdge("account:3300445566", "bank:securemart", ["mock-rec-5"]),
  mockFlowEdge("account:3300445566", "party:sunita sharma", ["mock-rec-5"]),
];

const MOCK_FLOW_ADJACENCY: MockFlowAdjacency = {};
for (const edge of MOCK_FLOW_EDGES) {
  (MOCK_FLOW_ADJACENCY[edge.source] ??= {})[edge.target] = edge;
  (MOCK_FLOW_ADJACENCY[edge.target] ??= {})[edge.source] = edge;
}

const mockFlowFact = (over: Record<string, unknown>): Record<string, unknown> => ({
  fact_class: "transaction",
  source_record_id: "mock-rec-1",
  evidence_file_id: "mock-ev-1",
  record_no: 1,
  source_locator: { record_no: 1, evidence_file_id: "mock-ev-1" },
  txn_ref_original: null,
  txn_ref_normalized: null,
  amount: null,
  amount_original: null,
  amount_precision: null,
  currency: null,
  currency_source: null,
  receiver: null,
  receiver_phone: null,
  account_original: null,
  account_normalized: null,
  bank: null,
  merchant: null,
  party: null,
  status: "unknown",
  occurred_at: null,
  occurred_at_original: null,
  occurred_at_granularity: null,
  missing: [],
  limitations: [],
  ...over,
});

/**
 * Five deterministic facts mirroring the documented ingest shape: amounts are
 * strings, no payer exists anywhere, nothing carries a timestamp, and one
 * record documents an account holder with no movement at all.
 */
const MOCK_FLOW_FACTS: Record<string, unknown>[] = [
  mockFlowFact({
    source_record_id: "mock-rec-1",
    record_no: 1,
    source_locator: { record_no: 1, evidence_file_id: "mock-ev-1" },
    txn_ref_original: "TXN-SIH-001",
    txn_ref_normalized: "TXN-SIH-001",
    amount: "4500.00",
    amount_original: "4500.00",
    amount_precision: "string_source",
    account_original: "ACC-SIH-001",
    account_normalized: "ACCSIH001",
    merchant: "PhonePe Merchant",
    party: "Ananya Sirohi",
    missing: ["currency", "timestamp", "counterparty", "source_direction"],
    limitations: ["currency_unknown", "missing_timestamp", "one_sided"],
  }),
  mockFlowFact({
    source_record_id: "mock-rec-2",
    record_no: 2,
    source_locator: { record_no: 2, evidence_file_id: "mock-ev-1" },
    txn_ref_original: "TXN-SIH-002",
    txn_ref_normalized: "TXN-SIH-002",
    amount: "12000.00",
    amount_original: "12000.00",
    amount_precision: "string_source",
    account_original: "ACC-SIH-002",
    account_normalized: "ACCSIH002",
    merchant: "Paytm Merchant",
    party: "Rohan Mehta",
    missing: ["currency", "timestamp", "counterparty", "source_direction"],
    limitations: ["currency_unknown", "missing_timestamp", "one_sided"],
  }),
  mockFlowFact({
    source_record_id: "mock-rec-3",
    record_no: 3,
    source_locator: { record_no: 3, evidence_file_id: "mock-ev-1" },
    txn_ref_original: "TXN-SIH-001",
    txn_ref_normalized: "TXN-SIH-001",
    amount: "4500.00",
    amount_original: "4500.00",
    amount_precision: "string_source",
    account_original: "ACC-SIH-001",
    account_normalized: "ACCSIH001",
    receiver: "Ananya Sirohi",
    missing: ["currency", "timestamp", "source_direction"],
    limitations: ["currency_unknown", "missing_timestamp", "one_sided"],
  }),
  mockFlowFact({
    source_record_id: "mock-rec-4",
    record_no: 4,
    source_locator: { record_no: 4, evidence_file_id: "mock-ev-1" },
    amount: "4500.00",
    amount_original: "4500.00",
    amount_precision: "string_source",
    account_original: "ACC-SIH-001",
    account_normalized: "ACCSIH001",
    receiver: "Ananya Sirohi",
    receiver_phone: "+91 98200 00001",
    missing: ["currency", "timestamp", "txn_ref", "source_direction"],
    limitations: ["currency_unknown", "missing_timestamp", "one_sided"],
  }),
  mockFlowFact({
    fact_class: "account_reference",
    source_record_id: "mock-rec-5",
    record_no: 5,
    source_locator: { record_no: 5, evidence_file_id: "mock-ev-1" },
    account_original: "3300445566",
    account_normalized: "3300445566",
    bank: "SecureMart",
    party: "Sunita Sharma",
    missing: ["amount", "currency", "timestamp", "txn_ref"],
    limitations: [],
  }),
];

const MOCK_FLOW_LIMITATIONS = [
  "no transactions table exists; every fact is a deterministic extraction from source_records.raw_data and coverage equals ingestion coverage",
  "no payer/sender key occurs in any record, so direction-dependent metrics (inflow/outflow/net) are reported not_computable_no_direction",
  "relationships contains no transfer edge type, so confirmed_transfer_edges is 0 and every structure edge is an association or a recorded relationship",
  "record-level amounts carry no currency attribution; totals are bucketed under currency=null flagged currency_unknown and never labelled with a default currency",
  "no ingested record carries a transaction timestamp, so time-windowed pattern rules are returned not_evaluable(missing_timestamp)",
  "pattern candidates are descriptive observations for human review; a pattern is never evidence of intent",
];

const MOCK_FLOW_CALCULATION_DEFINITIONS: Record<string, string> = {
  fact: "one deterministic extraction from one source record's raw_data; fact_class=transaction when an amount or transaction reference is present, otherwise account_reference",
  amount:
    "parsed with Decimal from the original value (JSON strings parse exactly); originals are preserved verbatim alongside; non-numeric values are rejected and counted, never coerced",
  total_records:
    "sum of exact Decimal amounts over every record carrying an amount, duplicates included",
  total_distinct:
    "one contribution per distinct transaction group (grouped by the documented dedupe key: transaction reference, else amount+account), so a transfer recorded twice counts once; groups whose records disagree on the amount are excluded and listed in conflicting_groups. Records without a transaction reference cannot be told apart from genuinely repeated transfers, so both totals are always reported together and neither is the unique truth. When every group disagrees it is null, because a zero there would be a fabricated figure",
  currency_bucketing:
    "amounts are summed only within one currency value; records without a currency fall into a null bucket flagged currency_unknown",
  net_flow: "not computed: direction is absent from the ingest",
  structure_edge:
    "association edges are documented co-occurrence within one record (star from the account when present); relationship edges are schema-asserted (e.g. owns). No edge is a confirmed transfer",
  pattern:
    "deterministic rule over the extracted facts; status is firing (with exact evidence), not_fired (evaluated, no evidence) or not_evaluable (a documented input is missing)",
};

/** Four rules that fire over the fixed fixtures, rebuilt fresh per payload. */
const mockFlowBaseFiring = (): Record<string, unknown>[] => [
  {
    rule: "duplicate_amount",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "firing",
    evidence: { amount: "4500.00", record_count: 3, distinct_dedupe_keys: 2 },
    supporting_source_record_ids: ["mock-rec-1", "mock-rec-3", "mock-rec-4"],
    limitations: ["currency_unknown"],
    review_status: "pending_review",
    pattern_not_intent: true,
  },
  {
    rule: "amount_threshold",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "firing",
    evidence: {
      threshold: "5000",
      threshold_semantics: "investigation default constant, not a regulatory or universal limit",
      matched_count: 1,
      amounts: ["12000.00"],
    },
    supporting_source_record_ids: ["mock-rec-2"],
    limitations: ["currency_unknown"],
    review_status: "pending_review",
    pattern_not_intent: true,
  },
  {
    rule: "missing_currency",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "firing",
    evidence: { matched_count: 4 },
    supporting_source_record_ids: ["mock-rec-1", "mock-rec-2", "mock-rec-3", "mock-rec-4"],
    limitations: ["currency_unknown"],
    review_status: "pending_review",
    pattern_not_intent: true,
  },
  {
    rule: "missing_timestamp",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "firing",
    evidence: { matched_count: 4 },
    supporting_source_record_ids: ["mock-rec-1", "mock-rec-2", "mock-rec-3", "mock-rec-4"],
    limitations: ["missing_timestamp"],
    review_status: "pending_review",
    pattern_not_intent: true,
  },
];

/** Rules the ingest cannot support — each states the specific missing input. */
const mockFlowNotEvaluable = (): Record<string, unknown>[] => [
  {
    rule: "rapid_succession",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "not_evaluable",
    reason: "missing_timestamp",
    explanation:
      "requires several movements from one source inside a rolling time window; no ingested record carries a transaction timestamp",
  },
  {
    rule: "repeated_pair",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "not_evaluable",
    reason: "missing_direction",
    explanation: "requires an ordered account pair (payer -> payee); no record states a direction",
  },
  {
    rule: "circular_path",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "not_evaluable",
    reason: "no_transfer_edges",
    explanation: "requires a cycle of confirmed transfers; no transfer edge exists to traverse",
  },
  {
    rule: "amount_splitting",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "not_evaluable",
    reason: "missing_direction",
    explanation:
      "requires one source splitting identical amounts to several destinations inside a window; neither direction nor timestamps exist",
  },
  {
    rule: "concentration",
    version: MOCK_FLOW_PATTERNS_VERSION,
    status: "not_evaluable",
    reason: "missing_direction",
    explanation:
      "requires counting distinct counterparties sending to or receiving from one account; direction is absent",
  },
];

/** Victim loss totals, flagged `float_source` exactly like the backend. */
function mockFlowVictims(caseId: string): Record<string, unknown>[] {
  const exact = (value: number | null): string | null => {
    if (value === null || value === undefined) return null;
    return Number.isInteger(value) ? `${value}.0` : String(value);
  };
  return victimState
    .filter((victim) => victim.case_id === caseId)
    .map((victim) => {
      const missing: string[] = [];
      const limitations = ["float_source"];
      if (victim.reported_amount === null || victim.reported_amount === undefined)
        missing.push("reported_amount");
      if (victim.amount_lost === null || victim.amount_lost === undefined)
        missing.push("amount_lost");
      if (victim.recovery_amount === null || victim.recovery_amount === undefined)
        missing.push("recovery_amount");
      if (!victim.currency) {
        missing.push("currency");
        limitations.push("currency_unknown");
      }
      if (!victim.incident_date) missing.push("incident_date");
      return {
        victim_id: victim.id,
        case_id: victim.case_id,
        reported_amount: exact(victim.reported_amount ?? null),
        amount_lost: exact(victim.amount_lost ?? null),
        recovery_amount: exact(victim.recovery_amount ?? null),
        currency: victim.currency ? victim.currency.trim().toUpperCase() : null,
        incident_date: victim.incident_date ?? null,
        precision: "float_source",
        missing,
        limitations,
      };
    });
}

/** The deterministic payload the mock records — same shape as the backend. */
function mockFlowPayload(caseId: string): Record<string, unknown> {
  const victimFinancials = mockFlowVictims(caseId);
  const transactionAmounts = new Set(
    MOCK_FLOW_FACTS.filter((fact) => fact.amount !== null).map((fact) => String(fact.amount)),
  );
  const unmatchedVictims = victimFinancials.filter((victim) => {
    const reported = (victim.reported_amount ?? victim.amount_lost) as string | null;
    return reported !== null && !transactionAmounts.has(reported);
  });
  const firing = mockFlowBaseFiring();
  for (const victim of unmatchedVictims) {
    firing.push({
      rule: "victim_loss_unmatched",
      version: MOCK_FLOW_PATTERNS_VERSION,
      status: "firing",
      evidence: {
        victim_id: victim.victim_id,
        amount: victim.reported_amount ?? victim.amount_lost,
        currency: victim.currency,
        incident_date: victim.incident_date,
        match_rule:
          "exact Decimal equality against a transaction fact amount; no victim-to-record foreign key exists, so this is the only deterministic link available",
        transaction_amounts_in_case: [...transactionAmounts].sort(),
      },
      supporting_source_record_ids: [],
      supporting_victim_ids: [victim.victim_id],
      limitations: ["no_transaction_level_match", "float_source"],
      review_status: "pending_review",
      pattern_not_intent: true,
    });
  }
  const limitations = [...MOCK_FLOW_LIMITATIONS];
  if (victimFinancials.length > 0) {
    limitations.push(
      "some amounts originate in double precision columns and carry precision=float_source; exact-Decimal guarantees apply only to string/int-sourced amounts",
    );
  }
  return {
    flow_rules_version: MOCK_FLOW_RULES_VERSION,
    pattern_rules_version: MOCK_FLOW_PATTERNS_VERSION,
    case_id: caseId,
    scope: {
      records_scanned: MOCK_FLOW_RECORDS_SCANNED,
      records_bounded: false,
      victim_rows_scanned: victimFinancials.length,
      owns_edges_scanned: 0,
      flow_max_records: MOCK_FLOW_MAX_RECORDS,
    },
    facts: MOCK_FLOW_FACTS,
    facts_bounded: false,
    facts_total: MOCK_FLOW_FACTS.length,
    victim_financials: victimFinancials,
    aggregates: {
      counts: {
        facts_total: MOCK_FLOW_FACTS.length,
        fact_class_transaction: 4,
        fact_class_account_reference: 1,
        transaction_with_amount: 4,
        transaction_without_amount: 0,
        with_currency: 0,
        without_currency: 4,
        with_timestamp: 0,
        without_timestamp: 4,
        with_txn_ref: 3,
        without_txn_ref: 1,
      },
      currency_buckets: [
        {
          currency: null,
          currency_unknown: true,
          count: 4,
          distinct_groups: 3,
          conflicting_groups: [],
          distinct_amounts: 2,
          min: "4500.00",
          max: "12000.00",
          total_records: "25500.00",
          total_distinct: "21000.00",
          total_distinct_conflicts_excluded: 0,
          dedupe_key_definition:
            "normalized transaction reference when present, else (exact amount, normalized account)",
          dedupe_caveat:
            "records without a transaction reference cannot be told apart from genuinely repeated transfers; both totals are reported and neither is presented as the unique truth",
          supporting_source_record_ids: ["mock-rec-1", "mock-rec-2", "mock-rec-3", "mock-rec-4"],
          supporting_ids_capped: false,
        },
      ],
      by_status: [
        {
          status: "unknown",
          count: 4,
          total_records: "25500.00",
          supporting_source_record_ids: ["mock-rec-1", "mock-rec-2", "mock-rec-3", "mock-rec-4"],
          supporting_ids_capped: false,
        },
      ],
      by_account: [
        {
          account_normalized: "ACCSIH001",
          count: 3,
          total_records: "13500.00",
          supporting_source_record_ids: ["mock-rec-1", "mock-rec-3", "mock-rec-4"],
          supporting_ids_capped: false,
        },
        {
          account_normalized: "ACCSIH002",
          count: 1,
          total_records: "12000.00",
          supporting_source_record_ids: ["mock-rec-2"],
          supporting_ids_capped: false,
        },
      ],
      by_bank: [],
      by_merchant: [
        {
          merchant: "Paytm Merchant",
          count: 1,
          total_records: "12000.00",
          supporting_source_record_ids: ["mock-rec-2"],
          supporting_ids_capped: false,
        },
        {
          merchant: "PhonePe Merchant",
          count: 1,
          total_records: "4500.00",
          supporting_source_record_ids: ["mock-rec-1"],
          supporting_ids_capped: false,
        },
      ],
      not_computable: {
        inflow: "not_computable_no_direction",
        outflow: "not_computable_no_direction",
        net: "not_computable_no_direction",
        reason:
          "no payer-side key exists in any ingested record and relationships contains no transfer edge type, so no movement has a direction; these are reported as absent, never as zero",
      },
    },
    structure_network: {
      nodes: MOCK_FLOW_NODES,
      edges: MOCK_FLOW_EDGES,
      nodes_total: MOCK_FLOW_NODES.length,
      edges_total: MOCK_FLOW_EDGES.length,
      edges_bounded: false,
      max_edges: 500,
      confirmed_transfer_edges: 0,
      transfer_edge_note:
        "no ingested record states a two-sided money movement and relationships has no transfer edge type, so no edge is a confirmed transfer; association edges are candidates for review",
      account_node_linkage:
        "fact-derived and entity-derived account nodes share one documented normalization; a mismatch yields two nodes rather than an assumed merge",
    },
    patterns: {
      firing,
      not_fired: unmatchedVictims.length === 0 ? ["victim_loss_unmatched"] : [],
      not_evaluable: mockFlowNotEvaluable(),
      rule_count: 10,
      rules_version: MOCK_FLOW_PATTERNS_VERSION,
    },
    extraction_warnings: {
      records_without_financial_fields: 1,
      amount_invalid: 0,
      amounts_parsed: 4,
    },
    limitations,
    calculation_definitions: MOCK_FLOW_CALCULATION_DEFINITIONS,
  };
}

function mockFinancialFindingArtifact(caseId: string, jobId: string): DerivedArtifactOut {
  return {
    id: nextIntelId(),
    case_id: caseId,
    kind: "financial_finding",
    origin: "deterministic",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: null,
    payload: mockFlowPayload(caseId),
    // Content-derived: a rerun reuses the artifact instead of duplicating it.
    content_hash: `financial-finding-${caseId}`,
    parser_version: MOCK_FLOW_RULES_VERSION,
    prompt_version: null,
    model_profile: null,
    analysis_job_id: jobId,
    validation_errors: null,
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/* -------------------- Cross-case discovery (phase 4, feature B) -------------------- */

const MOCK_CROSSCASE_RULES_VERSION = "crosscase/1.0.0";
const MOCK_CROSSCASE_GRAPH_NOTE =
  "Discovery reads only the cases' authorized records; it does not depend on the Neo4j projection.";

/** One deterministic mock candidate: a shared account reference across two cases. */
function mockCrossCaseCandidate(
  anchorCaseId: string,
  caseIds: string[],
  jobId: string,
): DerivedArtifactOut {
  const sides = caseIds.slice(0, 2).map((caseId) => ({
    case_id: caseId,
    value_originals: ["ACC-SIH-001"],
    originals_capped: false,
    entity_ids: [`ent-${caseId}`],
    source_record_ids: [`rec-${caseId}-1`],
    evidence_file_ids: [],
    supporting_ids_capped: false,
    reviewed_alias: false,
    contributing_kinds: ["account_ref"],
  }));
  return {
    id: nextIntelId(),
    case_id: anchorCaseId,
    kind: "cross_case_link",
    origin: "deterministic",
    status: "pending_review",
    validation_status: "valid",
    evidence_file_id: null,
    source_record_id: null,
    source_locator: null,
    payload: {
      crosscase_rules_version: MOCK_CROSSCASE_RULES_VERSION,
      scope: {
        case_ids: caseIds,
        scope_hash: `scope-${caseIds.length}`,
        cases_in_group: caseIds.slice(0, 2),
      },
      group: { indicator_kind: "account_ref", value_normalized: "ACCSIH001" },
      classification: "normalized_identifier",
      classification_semantics: {
        normalized_identifier:
          "a shared identifier after deterministic normalization; stronger than a name-only match",
      },
      score: 78,
      score_semantics:
        "0–100 additive signal band, NOT a probability; only a review decision can become an authoritative link",
      signal_kinds: ["account_ref"],
      additional_shared_kinds: [],
      conflicting_attributes: { flagged: false, evidence: [] },
      sides,
      reviewable: true,
      review_disabled_reason: null,
      limitations: [
        "a candidate is a discovery signal, not evidence of a shared incident",
        "approval records a reviewed relationship; it never merges entities or writes to the graph",
      ],
      graph_freshness_note: MOCK_CROSSCASE_GRAPH_NOTE,
    },
    // Content-derived: a rerun reuses the artifact instead of duplicating it.
    content_hash: `cross-case-${anchorCaseId}-${caseIds.slice(0, 2).join("-")}`,
    parser_version: MOCK_CROSSCASE_RULES_VERSION,
    prompt_version: null,
    model_profile: null,
    analysis_job_id: jobId,
    validation_errors: null,
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: null,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/** AI-narration child: flagged `ai_unverified`, parented, never approval-queued. */
function structuredExplanationChild(
  parent: DerivedArtifactOut,
  kind: DerivedArtifactOut["kind"],
  explanation: unknown,
): DerivedArtifactOut {
  return {
    id: nextIntelId(),
    case_id: parent.case_id,
    kind,
    origin: "llm",
    status: "recorded",
    validation_status: "flagged",
    evidence_file_id: parent.evidence_file_id,
    source_record_id: null,
    source_locator: parent.source_locator,
    payload: { type: "ai_explanation", for_artifact_id: parent.id, explanation },
    content_hash: `explain-${parent.id}-${Math.random().toString(36).slice(2, 8)}`,
    parser_version: "deterministic:1",
    prompt_version: "1.0.0",
    model_profile: "explain",
    analysis_job_id: null,
    validation_errors: [
      {
        field: "explanation",
        code: "ai_unverified",
        message: "AI-generated narration; unreviewed and unverified",
      },
    ],
    review_note: null,
    reviewed_by: null,
    reviewed_at: null,
    parent_artifact_id: parent.id,
    created_at: isoNow(),
    updated_at: isoNow(),
  };
}

/** Facts-only narration of a financial finding: cites a real fact, quotes no invented number. */
function mockExplainFinancial(parent: DerivedArtifactOut): CustodyExplainResponse {
  const payload = parent.payload as {
    facts?: Array<{ record_no?: number; amount?: string | null }>;
  };
  const first = payload.facts?.[0] ?? {};
  const cited = first.record_no != null ? [String(first.record_no)] : [];
  const explanation = {
    summary: first.amount
      ? `Amount-bearing records were extracted; the first carries ${first.amount} with currency unrecorded.`
      : "Amount-bearing records were extracted from the case records.",
    why_patterns_fired: [
      "Each pattern fires only on the extracted facts recorded on this finding.",
    ],
    cited_transaction_ids: cited,
    alternative_explanations: ["A legitimate business transfer with the same recorded shape."],
    missing_information: ["currency", "payer side", "timestamps"],
    verification_steps: ["Confirm the account holder", "Locate the payer-side record if it exists"],
  };
  const child = structuredExplanationChild(parent, "financial_finding", explanation);
  artifactsState.unshift(child);
  pushAudit("flow.explanation_generated", "derived_artifact", parent.case_id, {
    for_artifact_id: parent.id,
  });
  return { explanation_artifact: child, text: explanation.summary, rule: "", explanation };
}

/** Facts-only narration of a cross-case candidate: scope-rechecked, never proof. */
function mockExplainCrossCase(parent: DerivedArtifactOut): CustodyExplainResponse {
  requirePermission("crosscase.read");
  const payload = parent.payload as {
    group?: { indicator_kind?: string };
    classification?: string;
    sides?: Array<{ case_id: string; value_originals?: string[] }>;
  };
  // Fail closed: a candidate touching an inaccessible case is shown as not-found.
  if (!(payload.sides ?? []).every((side) => canAccessCase(side.case_id)))
    throw notFound("artifact not found");
  const shared = payload.sides?.[0]?.value_originals?.[0] ?? "";
  const explanation = {
    summary: shared
      ? `Both cases carry the shared ${payload.group?.indicator_kind ?? "identifier"} ${shared}; this is a candidate link, not proof of a shared incident.`
      : "The cases share an identifier; this is a candidate link, not proof.",
    matching_signal: `identifier ${payload.group?.indicator_kind ?? "unknown"}, classification ${payload.classification ?? "unknown"}`,
    cited_identifiers: shared ? [shared] : [],
    conflicts: [] as string[],
    not_established: [
      "that the cases are the same incident",
      "that any transfer occurred between them",
    ],
    verification_steps: [
      "Confirm the account holder on both sides",
      "Check whether the shared value is a coincidence",
    ],
  };
  const child = structuredExplanationChild(parent, "cross_case_link", explanation);
  artifactsState.unshift(child);
  pushAudit("cross_case.explanation_generated", "derived_artifact", parent.case_id, {
    for_artifact_id: parent.id,
  });
  return { explanation_artifact: child, text: explanation.summary, rule: "", explanation };
}

/**
 * Bounded structure trace over `MOCK_FLOW_NETWORK` — the same rules as the
 * backend: sorted neighbours, simple paths only, dead ends marked incomplete,
 * bounds clamped and echoed, and `transfer` answered as absent instead of
 * approximated with associations.
 */
function traceMockFlow(caseId: string, input: FlowTraceRequest): FlowTraceResponse {
  const target = input.target;
  const edgeKind = input.edge_kind ?? "association";
  const targetKind = input.target_kind ?? "account";
  const maxDepth = Math.min(
    Math.max(input.max_depth ?? MOCK_FLOW_TRACE_MAX_DEPTH, 1),
    MOCK_FLOW_TRACE_MAX_DEPTH,
  );
  const maxPaths = Math.min(
    Math.max(input.max_paths ?? MOCK_FLOW_TRACE_MAX_PATHS, 1),
    MOCK_FLOW_TRACE_MAX_PATHS,
  );
  const limitations = [
    "every hop is an association (documented co-occurrence) or a recorded relationship, never a confirmed transfer, so a trace answers what else is documented about an account \u2014 not where money went",
    "no ingested record carries a transaction timestamp, so a trace has no time dimension",
    "a path ending dead_end means the trail stops there in the ingested evidence; no destination beyond it is ever guessed",
  ];
  const response: FlowTraceResponse = {
    case_id: caseId,
    flow_rules_version: MOCK_FLOW_RULES_VERSION,
    target,
    target_kind: targetKind,
    edge_kind: edgeKind,
    status: "ok",
    reason: null,
    start_node: null,
    matched_facts: 0,
    target_degree: 0,
    paths: [],
    paths_bounded: false,
    records_bounded: false,
    bounds: {
      max_depth: maxDepth,
      max_paths: maxPaths,
      max_records: MOCK_FLOW_MAX_RECORDS,
      records_scanned: MOCK_FLOW_RECORDS_SCANNED,
    },
    network: {
      nodes_total: MOCK_FLOW_NODES.length,
      edges_total: MOCK_FLOW_EDGES.length,
      confirmed_transfer_edges: 0,
    },
    limitations,
  };

  if (edgeKind === "transfer") {
    return {
      ...response,
      status: "insufficient_data",
      reason: "no_transfer_edges_in_ingest",
      limitations: [
        ...limitations,
        "a transfer trace was requested but no ingested record states a two-sided money movement and relationships contains no transfer edge type, so there is no transfer path to return; the trail is reported as absent rather than approximated with associations",
      ],
    };
  }

  const nodeIds = new Set(MOCK_FLOW_NODES.map((node) => node.id));
  let start: string | null = null;
  if (targetKind === "transaction") {
    const normalized = target.trim().toUpperCase();
    const matched = MOCK_FLOW_FACTS.filter((fact) => fact.txn_ref_normalized === normalized);
    response.matched_facts = matched.length;
    if (matched.length === 0) {
      response.status = "not_found";
      response.reason = "no_source_record_in_this_case_carries_that_transaction_reference";
    } else {
      const accountFact = matched.find(
        (fact) =>
          typeof fact.account_normalized === "string" &&
          nodeIds.has(`account:${String(fact.account_normalized)}`),
      );
      start = accountFact ? `account:${String(accountFact.account_normalized)}` : null;
      if (!start) response.reason = "transaction_found_but_no_account_is_documented_for_it";
    }
  } else {
    const candidate = `account:${target.replace(/[^A-Za-z0-9]/g, "").toUpperCase()}`;
    if (nodeIds.has(candidate)) {
      start = candidate;
    } else {
      response.status = "not_found";
      response.reason = "no_account_matching_that_reference_is_documented_in_this_case";
    }
  }

  if (response.status === "ok" && start) {
    response.start_node = start;
    const paths: FlowTracePath[] = [];
    let truncated = false;
    const dfs = (
      node: string,
      nodesPath: string[],
      hops: FlowTraceHop[],
      visited: Set<string>,
    ): void => {
      if (paths.length >= maxPaths) {
        truncated = true;
        return;
      }
      const open = Object.keys(MOCK_FLOW_ADJACENCY[node] ?? {})
        .filter((neighbor) => !visited.has(neighbor))
        .sort();
      const atDepthLimit = hops.length >= maxDepth;
      if (open.length === 0 || atDepthLimit) {
        if (nodesPath.length > 1) {
          if (paths.length >= maxPaths) {
            truncated = true;
            return;
          }
          const endState = atDepthLimit && open.length > 0 ? "depth_limit" : "dead_end";
          paths.push({
            nodes: [...nodesPath],
            hops: [...hops],
            depth: hops.length,
            end_state: endState,
            incomplete: endState === "dead_end",
          });
        } else if (atDepthLimit && open.length > 0) {
          truncated = true;
        }
        return;
      }
      for (const neighbor of open) {
        if (paths.length >= maxPaths) {
          truncated = true;
          return;
        }
        const edge = MOCK_FLOW_ADJACENCY[node][neighbor];
        dfs(
          neighbor,
          [...nodesPath, neighbor],
          [
            ...hops,
            {
              source: node,
              target: neighbor,
              edge_kind: edge.edge_kind,
              derivation: edge.derivation,
              confidence: edge.confidence,
              relationship_type: edge.relationship_type,
              supporting_source_record_ids: [...edge.supporting_source_record_ids],
            },
          ],
          new Set([...visited, neighbor]),
        );
      }
    };
    dfs(start, [start], [], new Set([start]));
    response.target_degree = Object.keys(MOCK_FLOW_ADJACENCY[start] ?? {}).length;
    response.paths = paths;
    response.paths_bounded = truncated;
  }

  return response;
}

async function submitAnalysisFeature(
  caseId: string,
  feature: AnalysisFeature,
): Promise<JobSubmitResponse> {
  await delay(MOCK_LATENCY * 2);
  requirePermission("ingestion.run");
  assertCaseAccess(caseId);
  const meta = ANALYSIS_FEATURES[feature];
  const active = intelJobsState.find(
    (j) =>
      j.case_id === caseId &&
      j.feature === feature &&
      (j.status === "pending" || j.status === "running"),
  );
  if (active) {
    throw new ApiError({
      status: 409,
      code: meta.activeCode,
      message: `a ${feature} run is already active for this case`,
    });
  }
  const attempts =
    intelJobsState.filter((j) => j.case_id === caseId && j.feature === feature).length + 1;
  const job: AnalysisJobOut = {
    id: nextIntelId(),
    case_id: caseId,
    feature,
    status: "succeeded",
    idempotency_key: `${feature}:${caseId}:a${attempts}`,
    progress: 100,
    total_records: 1,
    processed_records: 1,
    attempts,
    timeout_seconds: 300,
    cancel_requested: false,
    error: null,
    result_summary: {},
    evidence_file_id: null,
    actor_id: currentUser().record?.id ?? null,
    started_at: isoNow(),
    completed_at: isoNow(),
    created_at: isoNow(),
    updated_at: isoNow(),
  };

  const record = (artifact: DerivedArtifactOut): boolean => {
    const reuse = artifactsState.some(
      (a) => a.case_id === caseId && a.content_hash === artifact.content_hash,
    );
    if (!reuse) artifactsState.unshift(artifact);
    return !reuse;
  };

  const summary: Record<string, unknown> = {};
  if (feature === "entity_resolution") {
    const entities = entitiesFor(caseId);
    const pairs = mockResolutionPairs(caseId);
    Object.assign(summary, {
      entities_scanned: entities.length,
      entities_bounded: false,
      pairs_generated: pairs.length,
      pairs_proposed: 0,
      pairs_llm: 0,
      pairs_llm_invalid: 0,
      pairs_llm_failed: 0,
      pairs_llm_skipped: 0,
      artifacts_created: 0,
      artifacts_reused: 0,
    });
    for (const pair of pairs) {
      summary["pairs_proposed"] = Number(summary["pairs_proposed"]) + 1;
      // The mock has no local model: ambiguous pairs are honestly skipped.
      if (scoreBand(pair.score) === "ambiguous") {
        summary["pairs_llm_skipped"] = Number(summary["pairs_llm_skipped"]) + 1;
      }
      const created = record(mockResolutionArtifact(caseId, job.id, pair));
      summary[created ? "artifacts_created" : "artifacts_reused"] =
        Number(summary[created ? "artifacts_created" : "artifacts_reused"]) + 1;
    }
  } else if (feature === "timeline") {
    const committed = committedProposalKeys();
    Object.assign(summary, {
      records_scanned: 0,
      records_bounded: false,
      artifacts_scanned: artifactsState.filter(
        (a) => a.case_id === caseId && a.kind === "timeline_proposal",
      ).length,
      artifacts_bounded: false,
      drafts_generated: 0,
      proposals_recorded: 0,
      proposals_reused: 0,
      proposals_committed_skipped: 0,
      duplicates: 0,
      conflicts: 0,
      overlaps: 0,
      missing_timestamps: 0,
      ambiguous_timezones: 0,
    });
    for (const draft of MOCK_RECONSTRUCTION_DRAFTS) {
      if (committed.has(mockProposalKey(draft))) {
        summary["proposals_committed_skipped"] = Number(summary["proposals_committed_skipped"]) + 1;
        continue;
      }
      summary["drafts_generated"] = Number(summary["drafts_generated"]) + 1;
      if (draft.missing_timestamp)
        summary["missing_timestamps"] = Number(summary["missing_timestamps"]) + 1;
      if (draft.tz_assumed)
        summary["ambiguous_timezones"] = Number(summary["ambiguous_timezones"]) + 1;
      const created = record(mockReconstructionArtifact(caseId, job.id, draft));
      summary[created ? "proposals_recorded" : "proposals_reused"] =
        Number(summary[created ? "proposals_recorded" : "proposals_reused"]) + 1;
    }
  } else if (feature === "financial_flow") {
    const payload = mockFlowPayload(caseId);
    const patterns = payload.patterns as {
      firing: unknown[];
      not_fired: string[];
      not_evaluable: unknown[];
    };
    const aggregates = payload.aggregates as { currency_buckets: unknown[] };
    const network = payload.structure_network as { nodes_total: number; edges_total: number };
    const scope = payload.scope as { records_scanned: number; victim_rows_scanned: number };
    Object.assign(summary, {
      records_scanned: scope.records_scanned,
      records_bounded: false,
      victim_rows_scanned: scope.victim_rows_scanned,
      facts_extracted: payload.facts_total,
      facts_transaction: 4,
      facts_account_reference: 1,
      currency_buckets: aggregates.currency_buckets.length,
      network_nodes: network.nodes_total,
      network_edges: network.edges_total,
      patterns_firing: patterns.firing.length,
      patterns_not_evaluable: patterns.not_evaluable.length,
      patterns_not_fired: patterns.not_fired.length,
      artifacts_created: 0,
      artifacts_reused: 0,
    });
    const created = record(mockFinancialFindingArtifact(caseId, job.id));
    summary[created ? "artifacts_created" : "artifacts_reused"] = 1;
  } else {
    Object.assign(summary, {
      records_scanned: 0,
      records_bounded: false,
      records_with_claims: 2,
      anchor_groups: 1,
      pair_evals: 1,
      conflicts: 1,
      artifacts_created: 0,
      artifacts_reused: 0,
      semantic_pairs: 0,
      semantic_llm: 0,
      semantic_invalid: 0,
      semantic_skipped: 0,
    });
    const created = record(mockContradictionArtifact(caseId, job.id));
    summary[created ? "artifacts_created" : "artifacts_reused"] = 1;
  }

  job.result_summary = summary;
  intelJobsState.unshift(job);
  pushAudit(`${meta.audit}.submitted`, "analysis_job", caseId, { feature, attempt: attempts });
  pushAudit(meta.successAction, "analysis_job", caseId, { ...summary });
  return { job, duplicate: false };
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
