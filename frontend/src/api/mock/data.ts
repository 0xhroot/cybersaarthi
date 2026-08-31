/**
 * Deterministic demo dataset for mock mode.
 *
 * Models the CyberSaarthi demo domain (TechSecure cell, call/vehicle/banking
 * records) and produces the exact shapes the backend contract defines. All ids
 * and values are stable across reloads — nothing is randomized.
 */

import type {
  AnalyticsRun,
  AuditEvent,
  Case,
  CentralityEntry,
  Community,
  Entity,
  EntityDetail,
  EvidenceListItem,
  Finding,
  FindingStats,
  GraphEdge,
  GraphNode,
  GraphStats,
  Hypothesis,
  IngestionJob,
  NetworkProfile,
  Pattern,
  Priority,
  Relationship,
  RelationshipStrength,
} from "@/types/domain";

export type IdGenerator = (seed: number) => string;

/** Deterministic UUIDs derived from a numeric seed. */
export const uid = (seed: number): string => {
  const body = `${seed}`.padStart(12, "0");
  return `00000000-0000-4000-8000-${body}`;
};

export const CASE_ID_MAIN = "a0000000-0000-4000-8000-000000000001";
export const CASE_ID_SECONDARY = "a0000000-0000-4000-8000-000000000002";
export const CASE_ID_TERTIARY = "a0000000-0000-4000-8000-000000000003";
export const CASE_ID_CLOSED = "a0000000-0000-4000-8000-000000000004";

export const USER_ADMIN_ID = "b0000000-0000-4000-8000-000000000001";
export const USER_INVESTIGATOR_ID = "b0000000-0000-4000-8000-000000000002";
export const USER_ANALYST_ID = "b0000000-0000-4000-8000-000000000003";
export const USER_VIEWER_ID = "b0000000-0000-4000-8000-000000000004";

/* ------------------------------------------------------------------ */
/* Timestamps fixed relative to a static anchor so relative times read  */
/* plausibly and never shift between reloads.                          */
/* ------------------------------------------------------------------ */
const NOW = new Date("2026-08-30T12:00:00Z");
export function iso(daysAgo: number, hoursAgo = 0, minutes = 0): string {
  const d = new Date(NOW);
  d.setUTCDate(d.getUTCDate() - daysAgo);
  d.setUTCHours(d.getUTCHours() - hoursAgo);
  d.setUTCMinutes(d.getUTCMinutes() - minutes);
  return d.toISOString();
}

interface EntitySeed {
  key: string;
  type: Entity["entity_type"];
  value: string;
  display?: string;
  confidence?: number | null;
  status?: Entity["status"];
  aliases?: Array<{ alias_value: string; alias_type: string }>;
}

const H = (key: string): EntitySeed => ({ key, type: "person", value: key });
const P = (key: string): EntitySeed => ({ key, type: "phone", value: key });
const V = (key: string): EntitySeed => ({ key, type: "vehicle", value: key });
const O = (key: string): EntitySeed => ({ key, type: "organization", value: key });
const L = (key: string): EntitySeed => ({ key, type: "location", value: key });
const A = (key: string): EntitySeed => ({ key, type: "account", value: key });
const EV = (key: string): EntitySeed => ({ key, type: "event", value: key });

const MAIN_ENTITY_SEEDS: EntitySeed[] = [
  H("Rajesh Kumar"),
  H("Sunita Sharma"),
  H("Arjun Mehta"),
  H("Kavita Rao"),
  H("Mehul Desai"),
  H("Priya Nair"),
  H("Varun Joshi"),
  H("Anjali Kale"),
  P("+91-98765-43210"),
  P("+91-91234-56789"),
  P("+91-90000-11111"),
  P("+91-98111-22233"),
  P("+91-94000-33344"),
  P("+91-90909-88877"),
  V("MH12AB1234"),
  V("MH12AB2345"),
  V("KA01CD5678"),
  V("DL01EF9012"),
  V("UP32GH3456"),
  V("MH14JK7890"),
  O("TechSecure Pvt Ltd"),
  O("SecureMart Ltd"),
  O("Kavita Enterprises"),
  O("Horizon Freight Services"),
  O("Nova Logistics"),
  L("Mumbai"),
  L("Pune"),
  L("Bengaluru"),
  L("Delhi"),
  L("Noida"),
  L("Chennai"),
  A("1100220011"),
  A("3300445566"),
  A("5500667788"),
  A("7700990011"),
  A("9900112233"),
  A("2244660088"),
  { key: "Call detail records - June 2026", type: "document", value: "CDR_2026_06", display: "Call detail records · Jun 2026" },
  { key: "Bank statements - Q2 2026", type: "document", value: "STMT_Q2_2026", display: "Bank statements · Q2 2026" },
  EV("Meeting at Horizon depot"),
];

export const KEY_ENTITY_IDS: Record<string, string> = {};
MAIN_ENTITY_SEEDS.forEach((seed, index) => {
  KEY_ENTITY_IDS[seed.key] = uid(100 + index);
});

export interface MockEntry {
  key: string;
  type: string;
  display: string;
  confidence: number | null;
  status: Entity["status"];
  aliases: Array<{ id: string; alias_value: string; alias_type: string }>;
  context: Record<string, unknown> | null;
  created_at: string;
}

const NAMED_CONTEXT: Record<string, Record<string, unknown>> = {
  "Rajesh Kumar": {
    designation: "Director, TechSecure",
    remittance_share: 0.41,
    flagged_entities: 2,
  },
  "TechSecure Pvt Ltd": {
    sector: "Information technology",
    hadronic: false,
  },
  "Horizon Freight Services": { sector: "Freight & logistics" },
};

export const MAIN_ENTITIES: Entity[] = MAIN_ENTITY_SEEDS.map((seed, index) => {
  const createdAt = iso(14 + (index % 4));
  return {
    id: KEY_ENTITY_IDS[seed.key],
    case_id: CASE_ID_MAIN,
    entity_type: seed.type,
    canonical_value: seed.value,
    display_value: seed.display ?? seed.value,
    confidence: seed.confidence ?? (seed.type === "person" ? 0.94 : 0.98),
    status: (seed.status ?? "active") as Entity["status"],
    created_at: createdAt,
  } satisfies Entity;
});

export const MAIN_ENTITY_DETAILS: Record<string, Partial<EntityDetail>> = Object.fromEntries(
  MAIN_ENTITY_SEEDS.map((seed) => [
    seed.key,
    {
      aliases: (seed.aliases ?? []).map((a, i) => ({
        id: uid(9000 + i),
        alias_value: a.alias_value,
        alias_type: a.alias_type,
      })),
      context: NAMED_CONTEXT[seed.key] ?? null,
    },
  ]),
);

/* True observed aliases only — derived variants are values, not aliases. */
MAIN_ENTITY_DETAILS["Arjun Mehta"] = {
  aliases: [
    { id: uid(9001), alias_value: "Arjun Mehra", alias_type: "name" },
    { id: uid(9002), alias_value: "a.mehta@techsecure.co.in", alias_type: "email" },
  ],
  context: { designation: "Senior Engineer, TechSecure" },
};
MAIN_ENTITY_DETAILS["Rajesh Kumar"] = {
  aliases: [
    { id: uid(9003), alias_value: "rajesh.k@techsecure.co.in", alias_type: "email" },
  ],
  context: {
    designation: "Director, TechSecure",
    flagged_entities: 2,
    remittance_share: 0.41,
  },
};

interface RelSeed {
  source: string;
  target: string;
  type: Relationship["relationship_type"];
  confidence?: number | null;
  explanation?: string;
  evidenceHits?: number;
}

const REL_SEEDS: RelSeed[] = [
  { source: "Rajesh Kumar", target: "+91-98765-43210", type: "owns" },
  { source: "Rajesh Kumar", target: "TechSecure Pvt Ltd", type: "works_for" },
  { source: "Rajesh Kumar", target: "1100220011", type: "owns" },
  { source: "Rajesh Kumar", target: "Mumbai", type: "located_at" },
  { source: "Rajesh Kumar", target: "MH12AB1234", type: "owns" },
  { source: "Rajesh Kumar", target: "Sunita Sharma", type: "called", evidenceHits: 6 },
  { source: "Rajesh Kumar", target: "Arjun Mehta", type: "called", evidenceHits: 14 },
  { source: "Rajesh Kumar", target: "Mehul Desai", type: "associated_with" },
  { source: "Rajesh Kumar", target: "2244660088", type: "transferred_to", evidenceHits: 5 },
  { source: "Rajesh Kumar", target: "Pune", type: "visited", evidenceHits: 2 },
  { source: "Rajesh Kumar", target: "Call detail records - June 2026", type: "associated_with" },
  { source: "Sunita Sharma", target: "+91-91234-56789", type: "owns" },
  { source: "Sunita Sharma", target: "SecureMart Ltd", type: "works_for" },
  { source: "Sunita Sharma", target: "3300445566", type: "owns" },
  { source: "Sunita Sharma", target: "Bengaluru", type: "located_at" },
  { source: "Sunita Sharma", target: "KA01CD5678", type: "owns" },
  { source: "Sunita Sharma", target: "Kavita Rao", type: "called", evidenceHits: 4 },
  { source: "Arjun Mehta", target: "+91-90000-11111", type: "owns" },
  { source: "Arjun Mehta", target: "TechSecure Pvt Ltd", type: "works_for" },
  { source: "Arjun Mehta", target: "5500667788", type: "owns" },
  { source: "Arjun Mehta", target: "Delhi", type: "located_at" },
  { source: "Arjun Mehta", target: "DL01EF9012", type: "owns" },
  { source: "Arjun Mehta", target: "UP32GH3456", type: "owns" },
  { source: "Arjun Mehta", target: "Noida", type: "visited", evidenceHits: 3 },
  { source: "Arjun Mehta", target: "Kavita Rao", type: "called", evidenceHits: 3 },
  { source: "Kavita Rao", target: "+91-98111-22233", type: "owns" },
  { source: "Kavita Rao", target: "Kavita Enterprises", type: "works_for" },
  { source: "Kavita Rao", target: "7700990011", type: "owns" },
  { source: "Kavita Rao", target: "Mumbai", type: "located_at" },
  { source: "Kavita Rao", target: "MH14JK7890", type: "owns" },
  { source: "Mehul Desai", target: "+91-94000-33344", type: "owns" },
  { source: "Mehul Desai", target: "Horizon Freight Services", type: "works_for" },
  { source: "Mehul Desai", target: "9900112233", type: "owns" },
  { source: "Mehul Desai", target: "Chennai", type: "located_at" },
  { source: "Mehul Desai", target: "Priya Nair", type: "called", evidenceHits: 2 },
  { source: "Priya Nair", target: "+91-90909-88877", type: "owns" },
  { source: "Priya Nair", target: "Nova Logistics", type: "works_for" },
  { source: "Priya Nair", target: "Mumbai", type: "located_at" },
  { source: "Varun Joshi", target: "MH12AB2345", type: "owns" },
  { source: "Varun Joshi", target: "Delhi", type: "located_at" },
  { source: "Anjali Kale", target: "2244660088", type: "owns", evidenceHits: 4 },
  { source: "TechSecure Pvt Ltd", target: "Mumbai", type: "located_at" },
  { source: "SecureMart Ltd", target: "Bengaluru", type: "located_at" },
  { source: "Kavita Enterprises", target: "Mumbai", type: "located_at" },
  { source: "Horizon Freight Services", target: "Chennai", type: "located_at" },
  { source: "Horizon Freight Services", target: "Delhi", type: "located_at" },
  { source: "Nova Logistics", target: "Mumbai", type: "located_at" },
  { source: "Sunita Sharma", target: "Priya Nair", type: "associated_with" },
  { source: "Kavita Rao", target: "Sunita Sharma", type: "called", evidenceHits: 2 },
  { source: "Arjun Mehta", target: "MH12AB2345", type: "associated_with", evidenceHits: 3 },
  { source: "Mehul Desai", target: "Arjun Mehta", type: "transferred_to", evidenceHits: 4 },
  { source: "Meeting at Horizon depot", target: "Rajesh Kumar", type: "associated_with" },
  { source: "Call detail records - June 2026", target: "Arjun Mehta", type: "associated_with" },
];

export const MAIN_RELATIONSHIPS: Relationship[] = REL_SEEDS.map((rel, index) => ({
  id: uid(300 + index),
  source_entity_id: KEY_ENTITY_IDS[rel.source],
  target_entity_id: KEY_ENTITY_IDS[rel.target],
  relationship_type: rel.type,
  confidence: rel.confidence ?? (rel.evidenceHits && rel.evidenceHits >= 5 ? 0.95 : 0.87),
  explanation:
    rel.explanation ??
    (rel.evidenceHits
      ? `Observed in ${rel.evidenceHits} source records across ${rel.evidenceHits >= 5 ? "2" : "1"} evidence file(s).`
      : "Extracted from ingested source records."),
  created_at: iso(12 - (index % 10)),
}));

/* ---------------------------------------------------------------- */
/* Graph                                                              */
/* ---------------------------------------------------------------- */
export const MAIN_GRAPH_NODES: GraphNode[] = MAIN_ENTITIES.map((entity, index) => ({
  id: entity.id,
  entity_type: entity.entity_type,
  canonical_value: entity.canonical_value,
  display_value: entity.display_value,
  status: entity.status,
  confidence: entity.confidence,
  aliases:
    entity.entity_type === "person" ? [`alias-${index}`, `alt-${index}`] : [],
}));

export const MAIN_GRAPH_EDGES: GraphEdge[] = MAIN_RELATIONSHIPS.map((rel) => ({
  id: rel.id,
  source: rel.source_entity_id,
  target: rel.target_entity_id,
  relationship_type: rel.relationship_type,
  confidence: rel.confidence,
  context: null,
}));

export function graphStatsFor(caseId: string, nodes: GraphNode[], edges: GraphEdge[]): GraphStats {
  const entityTypeCounts: Record<string, number> = {};
  const relationshipTypeCounts: Record<string, number> = {};
  for (const node of nodes) {
    entityTypeCounts[node.entity_type] = (entityTypeCounts[node.entity_type] ?? 0) + 1;
  }
  for (const edge of edges) {
    relationshipTypeCounts[edge.relationship_type] =
      (relationshipTypeCounts[edge.relationship_type] ?? 0) + 1;
  }
  return {
    case_id: caseId,
    node_count: nodes.length,
    edge_count: edges.length,
    entity_type_counts: entityTypeCounts,
    relationship_type_counts: relationshipTypeCounts,
    generated_at: iso(0),
    synced: true,
  };
}

/* ---------------------------------------------------------------- */
/* Evidence                                                            */
/* ---------------------------------------------------------------- */
interface EvidenceSeed {
  key: string;
  filename: string;
  format: string;
  dataSource: string;
  size: number;
  records: number;
}

const EVIDENCE_SEEDS: EvidenceSeed[] = [
  {
    key: "demo_cdr",
    filename: "demo_cdr_june.csv",
    format: "csv",
    dataSource: "call detail records",
    size: 486_000,
    records: 218,
  },
  {
    key: "demo_surveillance",
    filename: "demo_surveillance.txt",
    format: "txt",
    dataSource: "surveillance log",
    size: 31_200,
    records: 74,
  },
  {
    key: "demo_statements",
    filename: "demo_statements.txt",
    format: "txt",
    dataSource: "bank statements",
    size: 14_880,
    records: 41,
  },
  {
    key: "bank_accounts",
    filename: "bank_accounts_q2.json",
    format: "json",
    dataSource: "banking",
    size: 9_600,
    records: 13,
  },
  {
    key: "vehicle_registry",
    filename: "vehicle_registry.csv",
    format: "csv",
    dataSource: "vehicle registry",
    size: 4_120,
    records: 9,
  },
];

function sha256For(key: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < key.length; i++) {
    hash ^= key.charCodeAt(i);
    hash = (hash * 0x01000193) >>> 0;
  }
  return `${hash.toString(16).padStart(8, "0")}${hash
    .toString(16)
    .padStart(8, "0")}${hash.toString(16).padStart(8, "0")}${hash
    .toString(16)
    .padStart(8, "0")}`;
}

export const MAIN_EVIDENCE: EvidenceListItem[] = EVIDENCE_SEEDS.map((seed, index) => {
  const created = iso(10 - index, 0, index * 22);
  return {
    id: uid(500 + index),
    original_filename: seed.filename,
    sha256: sha256For(seed.key),
    format: seed.format,
    file_size: seed.size,
    status: index === 0 ? "stored" : "parsed",
    record_count: seed.records,
    created_at: created,
  } satisfies EvidenceListItem;
});

export const EVIDENCE_DETAILS: Record<
  string,
  {
    stored_key: string;
    content_type: string;
    encoding: string | null;
    status_detail: string | null;
    data_source: string;
    metadata_json: Record<string, unknown> | null;
  }
> = Object.fromEntries(
  EVIDENCE_SEEDS.map((seed, index) => [
    seed.key,
    {
      stored_key: `cases/${CASE_ID_MAIN}/evidence/${uid(500 + index)}/${seed.filename}`,
      content_type: seed.format === "csv" ? "text/csv" : seed.format === "json" ? "application/json" : "text/plain",
      encoding: "utf-8",
      status_detail: index === 0 ? null : "Parsed successfully",
      data_source: seed.dataSource,
      metadata_json: { source: seed.dataSource, integrity: "verified" },
    },
  ]),
);

export const MAIN_JOBS: IngestionJob[] = EVIDENCE_SEEDS.map((seed, index) => ({
  id: uid(1500 + index),
  case_id: CASE_ID_MAIN,
  evidence_file_id: uid(500 + index),
  stage: index === 0 ? "queued" : "complete",
  status: index === 0 ? "pending" : "completed",
  progress: index === 0 ? 0 : 100,
  total_records: seed.records,
  processed_records: index === 0 ? 0 : seed.records,
  graph_sync_status: index === 0 ? "pending" : "synced",
  error: null,
  graph_error: null,
  summary:
    index === 0
      ? null
      : {
          records: seed.records,
          created_records: seed.records,
          entities: index === 0 ? 0 : 9 + index,
          relationships: index === 0 ? 0 : 12 + index,
        },
  created_at: iso(9 - index),
  updated_at: iso(9 - index, 0, 8),
}));

/* ---------------------------------------------------------------- */
/* Analytics primitives                                               */
/* ---------------------------------------------------------------- */

const PROFILE_TIERS: NetworkProfile["tier"][] = [
  "FOCAL",
  "SIGNIFICANT",
  "MONITORED",
  "PERIPHERAL",
];

interface ProfileSeed {
  key: string;
  overall: number;
  tier: NetworkProfile["tier"];
  features: Array<{ name: string; raw: number; normalized: number; weight: number; description: string }>;
  explanation: string;
}

const PROFILE_SEEDS: ProfileSeed[] = [
  {
    key: "Rajesh Kumar",
    overall: 0.91,
    tier: "FOCAL",
    features: [
      { name: "prominence", raw: 0.93, normalized: 0.93, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.88, normalized: 0.88, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.90, normalized: 0.90, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.85, normalized: 0.85, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Focal hub: highest degree and community-bridging load in the case.",
  },
  {
    key: "Arjun Mehta",
    overall: 0.82,
    tier: "SIGNIFICANT",
    features: [
      { name: "prominence", raw: 0.80, normalized: 0.80, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.71, normalized: 0.71, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.84, normalized: 0.84, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.88, normalized: 0.88, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "High call volume toward the focal entity and shared identifiers.",
  },
  {
    key: "Sunita Sharma",
    overall: 0.74,
    tier: "SIGNIFICANT",
    features: [
      { name: "prominence", raw: 0.62, normalized: 0.62, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.69, normalized: 0.69, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.78, normalized: 0.78, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.72, normalized: 0.72, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Links the SecureMart community to the focal cell.",
  },
  {
    key: "Kavita Rao",
    overall: 0.61,
    tier: "MONITORED",
    features: [
      { name: "prominence", raw: 0.51, normalized: 0.51, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.44, normalized: 0.44, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.52, normalized: 0.52, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.62, normalized: 0.62, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Repeated contact with both communities; owns a registered business.",
  },
  {
    key: "Mehul Desai",
    overall: 0.68,
    tier: "MONITORED",
    features: [
      { name: "prominence", raw: 0.47, normalized: 0.47, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.58, normalized: 0.58, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.66, normalized: 0.66, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.71, normalized: 0.71, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Handles logistics assets; banking transfers intersect the focal network.",
  },
  {
    key: "Priya Nair",
    overall: 0.43,
    tier: "PERIPHERAL",
    features: [
      { name: "prominence", raw: 0.28, normalized: 0.28, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.22, normalized: 0.22, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.31, normalized: 0.31, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.47, normalized: 0.47, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Peripheral node with limited, repeated contact toward the focal cell.",
  },
  {
    key: "Varun Joshi",
    overall: 0.21,
    tier: "PERIPHERAL",
    features: [
      { name: "prominence", raw: 0.12, normalized: 0.12, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.10, normalized: 0.10, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.14, normalized: 0.14, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.33, normalized: 0.33, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Shares a vehicle identifier with the focal network.",
  },
  {
    key: "Anjali Kale",
    overall: 0.38,
    tier: "PERIPHERAL",
    features: [
      { name: "prominence", raw: 0.18, normalized: 0.18, weight: 0.30, description: "Share of connections by degree" },
      { name: "influence", raw: 0.16, normalized: 0.16, weight: 0.30, description: "Betweenness centrality (bridging load)" },
      { name: "bridging", raw: 0.24, normalized: 0.24, weight: 0.20, description: "Degree to which the entity spans communities" },
      { name: "reach", raw: 0.41, normalized: 0.41, weight: 0.20, description: "Proportion reachable within two hops" },
    ],
    explanation: "Recipient of repeated banking transfers from the focal entity.",
  },
];

export const MAIN_NETWORK_PROFILES: NetworkProfile[] = PROFILE_SEEDS.map((seed) => ({
  entity_id: KEY_ENTITY_IDS[seed.key],
  entity_type: "person",
  display_value: seed.key,
  overall_score: seed.overall,
  tier: seed.tier,
  features: Object.fromEntries(
    seed.features.map((f) => [f.name, { name: f.name, raw: f.raw, normalized: f.normalized, weight: f.weight, description: f.description }]),
  ),
  signals: seed.features.map((f) => ({
    name: f.name,
    value: f.normalized,
    weight: f.weight,
    description: f.description,
  })),
  explanation: seed.explanation,
}));

/** FOCAL/SIGNIFICANT/MONITORED/PERIPHERAL — used by the closed case too. */
export const TIERS = PROFILE_TIERS;

export const MAIN_CENTRALITY: CentralityEntry[] = (() => {
  const degree = new Map<string, number>();
  for (const rel of MAIN_RELATIONSHIPS) {
    degree.set(rel.source_entity_id, (degree.get(rel.source_entity_id) ?? 0) + 1);
  }
  const max = Math.max(0, ...degree.values());
  const ranked = [...degree.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([id, raw], index) => ({
      entity_id: id,
      metric: "degree",
      metric_title: "Degree",
      raw,
      normalized: max === 0 ? 0 : raw / max,
      rank: index + 1,
      exact: true,
    }));
  return ranked;
})();

const communities: Array<{
  id: string;
  name: string;
  members: string[];
  density: number;
  internal: number;
  external: number;
  score: number;
}> = [
  {
    id: "C1",
    name: "TechSecure cell",
    members: [
      "Rajesh Kumar",
      "Arjun Mehta",
      "Mehul Desai",
      "TechSecure Pvt Ltd",
      "Horizon Freight Services",
      "Mumbai",
      "Delhi",
      "Chennai",
      "1100220011",
      "5500667788",
      "2244660088",
      "+91-98765-43210",
      "+91-90000-11111",
      "MH12AB1234",
      "DL01EF9012",
    ],
    density: 0.34,
    internal: 24,
    external: 9,
    score: 0.86,
  },
  {
    id: "C2",
    name: "SecureMart community",
    members: [
      "Sunita Sharma",
      "Kavita Rao",
      "Priya Nair",
      "SecureMart Ltd",
      "Kavita Enterprises",
      "Nova Logistics",
      "Bengaluru",
      "Mumbai",
      "3300445566",
      "7700990011",
      "+91-91234-56789",
      "+91-98111-22233",
    ],
    density: 0.29,
    internal: 16,
    external: 11,
    score: 0.74,
  },
  {
    id: "C3",
    name: "Peripheral identifiers",
    members: ["Varun Joshi", "Anjali Kale", "MH12AB2345", "9900112233", "+91-94000-33344"],
    density: 0.2,
    internal: 4,
    external: 6,
    score: 0.52,
  },
];

export const MAIN_COMMUNITIES: Community[] = communities.map((c) => ({
  community_id: c.id,
  member_count: c.members.length,
  density: c.density,
  internal_edges: c.internal,
  external_edges: c.external,
  dominant_entity_types: ["person"],
  dominant_relationship_types: c.id === "C1" ? ["called", "works_for", "transferred_to"] : ["called"],
  member_entity_ids: c.members.map((m) => KEY_ENTITY_IDS[m]),
  score: c.score,
  explanation:
    c.id === "C1"
      ? "High-density cell centred on the focal entity with banking and call-record overlap."
      : c.id === "C2"
        ? "Retail/business community bridged to the focal cell by Kavita Rao."
        : "Sparse identifiers connected to the core by shared vehicles and transfers.",
}));

const priorityAllocation: Record<
  string,
  { score: number; tier: Priority["tier"]; pattern: number; hypothesis: number }
> = {
  "Rajesh Kumar": { score: 0.93, tier: "CRITICAL", pattern: 0.45, hypothesis: 0.2 },
  "Arjun Mehta": { score: 0.81, tier: "HIGH", pattern: 0.3, hypothesis: 0.18 },
  "Sunita Sharma": { score: 0.66, tier: "HIGH", pattern: 0.24, hypothesis: 0.14 },
  "Mehul Desai": { score: 0.6, tier: "MEDIUM", pattern: 0.22, hypothesis: 0.1 },
  "Kavita Rao": { score: 0.55, tier: "MEDIUM", pattern: 0.18, hypothesis: 0.1 },
  "Anjali Kale": { score: 0.42, tier: "MEDIUM", pattern: 0.16, hypothesis: 0.06 },
  "Priya Nair": { score: 0.31, tier: "LOW", pattern: 0.1, hypothesis: 0.08 },
  "Varun Joshi": { score: 0.19, tier: "LOW", pattern: 0.08, hypothesis: 0.02 },
};

export const MAIN_PRIORITIES: Priority[] = (() => {
  const rows: Priority[] = [];
  for (const [key, alloc] of Object.entries(priorityAllocation)) {
    const profile = MAIN_NETWORK_PROFILES.find((p) => p.display_value === key);
    const centrality = MAIN_CENTRALITY.find((c) => KEY_ENTITY_IDS[key] === c.entity_id);
    rows.push({
      entity_id: KEY_ENTITY_IDS[key],
      entity_type: "person",
      display_value: key,
      prominence: profile?.features.prominence?.normalized ?? 0,
      influence: profile?.features.influence?.normalized ?? 0,
      bridging: profile?.features.bridging?.normalized ?? 0,
      reach: profile?.features.reach?.normalized ?? 0,
      pattern: alloc.pattern,
      hypothesis: alloc.hypothesis,
      priority_score: alloc.score,
      tier: alloc.tier,
      ...(centrality ? {} : {}),
    });
  }
  return rows.sort((a, b) => b.priority_score - a.priority_score);
})();

export const MAIN_RELATIONSHIP_STRENGTH: RelationshipStrength[] = MAIN_RELATIONSHIPS.filter(
  (rel) => rel.confidence !== null,
)
  .map((rel, index) => ({
    relationship_id: rel.id,
    source_entity_id: rel.source_entity_id,
    target_entity_id: rel.target_entity_id,
    relationship_type: rel.relationship_type,
    strength: 0.4 + ((index * 17) % 55) / 100,
    coverage: 0.35 + ((index * 11) % 55) / 100,
    type_diversity: 0.5,
    record_coverage: 0.5 + ((index * 7) % 40) / 100,
    file_independence: 0.6,
    resolution_confidence: rel.confidence ?? 0.8,
    evidence_count: 1 + (index % 5),
    distinct_sources: 1 + (index % 3),
    independent_files: 1 + (index % 2),
    signals: [
      { name: "record_coverage", value: 0.6, weight: 0.4, description: "Share of records that reference this relationship" },
      { name: "file_independence", value: 0.7, weight: 0.3, description: "Number of independent evidence files" },
    ],
  }))
  .sort((a, b) => b.strength - a.strength);

/* ---------------------------------------------------------------- */
/* Patterns / hypotheses / findings                                   */
/* ---------------------------------------------------------------- */

const evidenceIdFor = (key: string): string => uid(500 + EVIDENCE_SEEDS.findIndex((e) => e.key === key));

const SIGNAL = (name: string, value: number, description: string) => ({
  name,
  value,
  weight: 0.5,
  description,
});

export const MAIN_PATTERNS: Pattern[] = [
  {
    finding_type: "pattern",
    title: "Shared identifier: Arjun Mehta",
    summary:
      "Arjun Mehta appears in source records represented by more than one phone descriptor, a pattern frequently associated with controlled identifiers.",
    severity: "HIGH",
    score: 0.84,
    confidence: null,
    affected_entities: [KEY_ENTITY_IDS["Arjun Mehta"], KEY_ENTITY_IDS["+91-90000-11111"]],
    affected_relationships: [uid(308)],
    evidence_ids: [evidenceIdFor("demo_cdr"), evidenceIdFor("demo_surveillance")],
    signals: [
      SIGNAL("identifier_overlap", 0.84, "Multiple descriptors resolve to the same entity"),
      SIGNAL("record_frequency", 0.71, "High-frequency usage across evidence files"),
    ],
    metadata: { approach: "identifier_overlap" },
  },
  {
    finding_type: "pattern",
    title: "Bridge entity: Rajesh Kumar",
    summary:
      "Rajesh Kumar connects two otherwise distinct communities (TechSecure cell and SecureMart community) and therefore absorbs a large share of cross-community traffic.",
    severity: "CRITICAL",
    score: 0.91,
    confidence: null,
    affected_entities: [KEY_ENTITY_IDS["Rajesh Kumar"], KEY_ENTITY_IDS["Sunita Sharma"]],
    affected_relationships: [uid(300), uid(303), uid(305)],
    evidence_ids: [
      evidenceIdFor("demo_cdr"),
      evidenceIdFor("demo_statements"),
      evidenceIdFor("bank_accounts"),
    ],
    signals: [
      SIGNAL("bridge_score", 0.9, "Removal would split the component"),
      SIGNAL("betweenness", 0.88, "Disproportionate share of shortest paths"),
    ],
    metadata: { approach: "bridging" },
  },
  {
    finding_type: "pattern",
    title: "Relationship concentration: Rajesh Kumar",
    summary:
      "A single entity accounts for most of the call and transfer volume in the case, exceeding what the surrounding network would predict.",
    severity: "HIGH",
    score: 0.79,
    confidence: null,
    affected_entities: [KEY_ENTITY_IDS["Rajesh Kumar"]],
    affected_relationships: [uid(300), uid(305), uid(306), uid(309)],
    evidence_ids: [evidenceIdFor("demo_cdr"), evidenceIdFor("bank_accounts")],
    signals: [
      SIGNAL("degree_share", 0.82, "Share of total case degree"),
      SIGNAL("volume_concentration", 0.76, "Disproportionate interaction counts"),
    ],
    metadata: { approach: "concentration" },
  },
  {
    finding_type: "pattern",
    title: "Location + identifier linkage: Arjun Mehta",
    summary:
      "Banking and vehicle records place Arjun Mehta's identifier both in Delhi and Noida while transferring funds across accounts.",
    severity: "MEDIUM",
    score: 0.66,
    confidence: null,
    affected_entities: [KEY_ENTITY_IDS["Arjun Mehta"], KEY_ENTITY_IDS["Noida"], KEY_ENTITY_IDS["Delhi"]],
    affected_relationships: [uid(320), uid(322)],
    evidence_ids: [evidenceIdFor("demo_statements"), evidenceIdFor("bank_accounts")],
    signals: [
      SIGNAL("location_spread", 0.68, "Identifiers observed across multiple locations"),
      SIGNAL("transfer_linkage", 0.62, "Fund movement tied to location identifiers"),
    ],
    metadata: { approach: "location_identifier" },
  },
  {
    finding_type: "pattern",
    title: "Closed connection loop",
    summary:
      "Rajesh Kumar, Sunita Sharma and Kavita Rao form a closed interaction triangle with no evidence of an independent business explanation.",
    severity: "MEDIUM",
    score: 0.62,
    confidence: null,
    affected_entities: [
      KEY_ENTITY_IDS["Rajesh Kumar"],
      KEY_ENTITY_IDS["Sunita Sharma"],
      KEY_ENTITY_IDS["Kavita Rao"],
    ],
    affected_relationships: [uid(305), uid(349), uid(351)],
    evidence_ids: [evidenceIdFor("demo_cdr")],
    signals: [
      SIGNAL("three_cycle", 1, "Closed 3-node cycle present"),
      SIGNAL("unattributed_contact", 0.6, "Contacts lack a stated business purpose"),
    ],
    metadata: { approach: "cycle" },
  },
];

export const MAIN_HYPOTHESES: Hypothesis[] = [
  {
    finding_type: "hypothesis",
    title: "Possible connection: Rajesh Kumar ↔ Priya Nair",
    summary:
      "Priya Nair's identifier interacts with the Nova Logistics and SecureMart communities, which the focal cell is linked to through Sunita Sharma. A direct relationship is not observed in the ingested records.",
    severity: "LOW",
    score: 0.58,
    confidence: 0.58,
    affected_entities: [KEY_ENTITY_IDS["Rajesh Kumar"], KEY_ENTITY_IDS["Priya Nair"]],
    affected_relationships: [],
    evidence_ids: [evidenceIdFor("demo_cdr"), evidenceIdFor("demo_surveillance")],
    signals: [
      SIGNAL("two_hop", 0.66, "2-hop path between the identifiers"),
      SIGNAL("shared_org", 0.5, "Shared organization/location ties"),
    ],
    metadata: {
      path: [KEY_ENTITY_IDS["Rajesh Kumar"], KEY_ENTITY_IDS["Sunita Sharma"], KEY_ENTITY_IDS["Priya Nair"]],
    },
    candidate_relation_type: "associated_with",
  },
  {
    finding_type: "hypothesis",
    title: "Possible connection: Arjun Mehta ↔ Priya Nair",
    summary:
      "Both identifiers are linked to the same logistics corridor (Delhi–Mumbai) but no direct call or transfer is recorded between them.",
    severity: "LOW",
    score: 0.42,
    confidence: 0.42,
    affected_entities: [KEY_ENTITY_IDS["Arjun Mehta"], KEY_ENTITY_IDS["Priya Nair"]],
    affected_relationships: [],
    evidence_ids: [evidenceIdFor("demo_cdr")],
    signals: [SIGNAL("location_overlap", 0.55, "Identifiers co-occur in the same location cluster")],
    metadata: { path: [KEY_ENTITY_IDS["Arjun Mehta"], KEY_ENTITY_IDS["Delhi"], KEY_ENTITY_IDS["Priya Nair"]] },
    candidate_relation_type: "associated_with",
  },
  {
    finding_type: "hypothesis",
    title: "Possible connection: Mehul Desai ↔ Horizon Freight cell",
    summary:
      "Transfers involving account 9900112233 originate in the focal network but stop short of a recorded relationship between Mehul Desai and the freight operation's central contacts.",
    severity: "MEDIUM",
    score: 0.61,
    confidence: 0.61,
    affected_entities: [KEY_ENTITY_IDS["Mehul Desai"], KEY_ENTITY_IDS["Arjun Mehta"]],
    affected_relationships: [uid(354)],
    evidence_ids: [evidenceIdFor("bank_accounts"), evidenceIdFor("demo_statements")],
    signals: [
      SIGNAL("transfer_chain", 0.7, "Funds flow in a chain through related accounts"),
      SIGNAL("shared_bank", 0.52, "Accounts hosted at the same institution"),
    ],
    metadata: {
      path: [KEY_ENTITY_IDS["Mehul Desai"], KEY_ENTITY_IDS["Arjun Mehta"]],
    },
    candidate_relation_type: "a71",
  },
];

export const MAIN_FINDINGS: Finding[] = MAIN_PATTERNS.map((pattern, index): Finding => ({
  id: uid(700 + index),
  case_id: CASE_ID_MAIN,
  run_id: uid(2000),
  finding_type: pattern.finding_type,
  title: pattern.title,
  summary: pattern.summary,
  severity: pattern.severity,
  score: pattern.score,
  confidence: pattern.confidence,
  status: index === 0 ? "NEW" : index === 1 ? "REVIEWED" : index === 2 ? "NEW" : index === 3 ? "DISMISSED" : "REVIEWED",
  affected_entities: pattern.affected_entities,
  affected_relationships: pattern.affected_relationships,
  evidence_ids: pattern.evidence_ids,
  explanation: {
    approach: "Deterministic structural analysis over the projected knowledge graph (pattern detection on PostgreSQL-derived adjacency).",
    signals: pattern.signals.map((s) => ({
      name: s.name,
      value: s.value,
      description: s.description,
    })),
    paths: [
      {
        hops: 2,
        node_ids: pattern.affected_entities.slice(0, 3),
        relationship_ids: pattern.affected_relationships.slice(0, 2),
        relationship_types: ["called", "associated_with"],
      },
    ],
    evidence: pattern.evidence_ids.map((id, i) => ({
      kind: "source_record",
      id,
      label: EVIDENCE_SEEDS[i % EVIDENCE_SEEDS.length]?.filename ?? id,
    })),
    limitations: [
      "Structural signals establish correlation, not intent or wrongdoing.",
      "No assessment of content is performed; humans confirm or dismiss.",
    ],
  },
  details: null,
  reviewed_by:
    index === 1 || index === 4 ? USER_INVESTIGATOR_ID : index === 3 ? USER_ANALYST_ID : null,
  reviewed_at: index === 1 || index === 4 ? iso(2, 3) : index === 3 ? iso(1, 6) : null,
  review_comment:
    index === 1
      ? "Cross-checked against call records; consistent with observed frequency."
      : index === 3
        ? "Insufficient independent sources to support this pattern."
        : null,
  created_at: iso(2, 0, index * 9),
})).concat(
  MAIN_HYPOTHESES.map((hyp, index) => ({
    id: uid(800 + index),
    case_id: CASE_ID_MAIN,
    run_id: uid(2000),
    finding_type: "hypothesis" as const,
    title: hyp.title,
    summary: hyp.summary,
    severity: hyp.severity,
    score: hyp.score,
    confidence: hyp.confidence,
    status: index === 0 ? "NEW" : index === 1 ? "NEW" : "CONFIRMED",
    affected_entities: hyp.affected_entities,
    affected_relationships: hyp.affected_relationships,
    evidence_ids: hyp.evidence_ids,
    explanation: {
      approach:
        "Candidate missing-link analysis over the projected knowledge graph (multi-hop traversal, never written to the graph).",
      signals: hyp.signals.map((s) => ({
        name: s.name,
        value: s.value,
        description: s.description,
      })),
      paths: [{ hops: 2, node_ids: (hyp.metadata.path as string[]) ?? [], relationship_ids: [], relationship_types: [] }],
      evidence: hyp.evidence_ids.map((id, i) => ({
        kind: "source_record",
        id,
        label: EVIDENCE_SEEDS[i % EVIDENCE_SEEDS.length]?.filename ?? id,
      })),
      limitations: [
        "This is a structural hypothesis and does not establish a relationship, intent or wrongdoing.",
        "A direct edge is NOT present in the ingested records; it requires human validation.",
      ],
    },
    details: null,
    reviewed_by: index === 2 ? USER_INVESTIGATOR_ID : null,
    reviewed_at: index === 2 ? iso(1, 2) : null,
    review_comment: index === 2 ? "Transfer chain corroborated across three statements." : null,
    created_at: iso(2, 0, index * 7 + 30),
  })),
);

export function findingsStatsFor(findings: Finding[]): FindingStats {
  const by_type: Record<string, number> = {};
  const by_severity: Record<string, number> = {};
  const by_status: Record<string, number> = {};
  for (const f of findings) {
    by_type[f.finding_type] = (by_type[f.finding_type] ?? 0) + 1;
    by_severity[f.severity] = (by_severity[f.severity] ?? 0) + 1;
    by_status[f.status] = (by_status[f.status] ?? 0) + 1;
  }
  return { by_type, by_severity, by_status };
}

/* ---------------------------------------------------------------- */
/* Runs, cases, audit                                                 */
/* ---------------------------------------------------------------- */

export const MAIN_RUNS: AnalyticsRun[] = [
  {
    id: uid(2000),
    case_id: CASE_ID_MAIN,
    status: "completed",
    stage: "complete",
    error: null,
    actor_id: USER_INVESTIGATOR_ID,
    summary: {
      entity_count: MAIN_ENTITIES.length,
      relationship_count: MAIN_RELATIONSHIPS.length,
      community_count: MAIN_COMMUNITIES.length,
      finding_count: MAIN_FINDINGS.length,
    },
    started_at: iso(2, 1),
    completed_at: iso(2, 0, 55),
    created_at: iso(2, 1),
  },
  {
    id: uid(2001),
    case_id: CASE_ID_MAIN,
    status: "completed",
    stage: "complete",
    error: null,
    actor_id: USER_ANALYST_ID,
    summary: {
      entity_count: MAIN_ENTITIES.length - 2,
      relationship_count: MAIN_RELATIONSHIPS.length - 1,
      community_count: 2,
      finding_count: 6,
    },
    started_at: iso(6, 2),
    completed_at: iso(6, 1, 40),
    created_at: iso(6, 2),
  },
];

const SECONDARY_ENTITIES: Entity[] = [
  { id: uid(6001), case_id: CASE_ID_SECONDARY, entity_type: "person", canonical_value: "Dinesh Sawant", display_value: "Dinesh Sawant", confidence: 0.91, status: "active", created_at: iso(8) },
  { id: uid(6002), case_id: CASE_ID_SECONDARY, entity_type: "person", canonical_value: "Farida Sheikh", display_value: "Farida Sheikh", confidence: 0.9, status: "active", created_at: iso(8) },
  { id: uid(6003), case_id: CASE_ID_SECONDARY, entity_type: "organization", canonical_value: "Skyline Imports", display_value: "Skyline Imports", confidence: 0.98, status: "active", created_at: iso(8) },
  { id: uid(6004), case_id: CASE_ID_SECONDARY, entity_type: "phone", canonical_value: "+91-98989-76767", display_value: "+91-98989-76767", confidence: 0.95, status: "active", created_at: iso(8) },
  { id: uid(6005), case_id: CASE_ID_SECONDARY, entity_type: "account", canonical_value: "8182736450", display_value: "8182736450", confidence: 0.94, status: "active", created_at: iso(8) },
  { id: uid(6006), case_id: CASE_ID_SECONDARY, entity_type: "location", canonical_value: "Kolkata", display_value: "Kolkata", confidence: 1, status: "active", created_at: iso(8) },
];

const SECONDARY_RELATIONSHIPS: Relationship[] = [
  { id: uid(6101), source_entity_id: uid(6001), target_entity_id: uid(6003), relationship_type: "works_for", confidence: 0.96, explanation: "Designated as importer of record in shipment manifests.", created_at: iso(8) },
  { id: uid(6102), source_entity_id: uid(6001), target_entity_id: uid(6004), relationship_type: "owns", confidence: 0.99, explanation: "Phone identifier registered to subject.", created_at: iso(8) },
  { id: uid(6103), source_entity_id: uid(6002), target_entity_id: uid(6003), relationship_type: "works_for", confidence: 0.93, explanation: "Listed in payroll export.", created_at: iso(8) },
  { id: uid(6104), source_entity_id: uid(6001), target_entity_id: uid(6006), relationship_type: "located_at", confidence: 1, explanation: "Residence declared in intake form.", created_at: iso(8) },
  { id: uid(6105), source_entity_id: uid(6001), target_entity_id: uid(6005), relationship_type: "owns", confidence: 0.9, explanation: "Account holder matched by name + PAN.", created_at: iso(8) },
];

const SECONDARY_FINDINGS: Finding[] = [
  {
    id: uid(6201),
    case_id: CASE_ID_SECONDARY,
    run_id: uid(6200),
    finding_type: "network_insight",
    title: "Bridge entity: Dinesh Sawant",
    summary: "Dinesh Sawant is the only confirmed bridge between the import operation and phone/account identifiers.",
    severity: "MEDIUM",
    score: 0.57,
    confidence: null,
    status: "NEW",
    affected_entities: [uid(6001), uid(6003)],
    affected_relationships: [uid(6101)],
    evidence_ids: [uid(6510)],
    explanation: {
      approach: "Structural bridge detection.",
      signals: [{ name: "bridge_score", value: 0.63, description: "Removal splits components" }],
      paths: [],
      evidence: [{ kind: "source_record", id: uid(6510), label: "shipment_manifest_2026.csv" }],
      limitations: ["Single independent source in this case."],
    },
    details: null,
    reviewed_by: null,
    reviewed_at: null,
    review_comment: null,
    created_at: iso(3),
  },
];

const SECONDARY_EVIDENCE: EvidenceListItem[] = [
  { id: uid(6510), original_filename: "shipment_manifest_2026.csv", sha256: sha256For("manifest"), format: "csv", file_size: 221_500, status: "parsed", record_count: 96, created_at: iso(8) },
  { id: uid(6511), original_filename: "intake_forms.json", sha256: sha256For("intake"), format: "json", file_size: 12_800, status: "parsed", record_count: 14, created_at: iso(7) },
];

const SECONDARY_JOBS: IngestionJob[] = [
  { id: uid(6520), case_id: CASE_ID_SECONDARY, evidence_file_id: uid(6510), stage: "complete", status: "completed", progress: 100, total_records: 96, processed_records: 96, graph_sync_status: "synced", error: null, graph_error: null, summary: { records: 96, entities: 11, relationships: 14 }, created_at: iso(7, 12), updated_at: iso(7, 11) },
];

const TERTIARY_ENTITIES: Entity[] = [
  { id: uid(7001), case_id: CASE_ID_TERTIARY, entity_type: "person", canonical_value: "Nikhil Patil", display_value: "Nikhil Patil", confidence: 0.9, status: "active", created_at: iso(5) },
  { id: uid(7002), case_id: CASE_ID_TERTIARY, entity_type: "account", canonical_value: "3034415220", display_value: "3034415220", confidence: 0.95, status: "review", created_at: iso(5) },
  { id: uid(7003), case_id: CASE_ID_TERTIARY, entity_type: "organization", canonical_value: "Meena Traders", display_value: "Meena Traders", confidence: 0.9, status: "active", created_at: iso(5) },
  { id: uid(7004), case_id: CASE_ID_TERTIARY, entity_type: "location", canonical_value: "Ahmedabad", display_value: "Ahmedabad", confidence: 1, status: "active", created_at: iso(5) },
];

export const CLOSED_CASE_ENTITIES: Entity[] = [
  { id: uid(8001), case_id: CASE_ID_CLOSED, entity_type: "person", canonical_value: "Rohit Malhotra", display_value: "Rohit Malhotra", confidence: 0.92, status: "active", created_at: iso(60) },
  { id: uid(8002), case_id: CASE_ID_CLOSED, entity_type: "phone", canonical_value: "+91-90901-12233", display_value: "+91-90901-12233", confidence: 0.97, status: "active", created_at: iso(60) },
  { id: uid(8003), case_id: CASE_ID_CLOSED, entity_type: "organization", canonical_value: "Triton Media", display_value: "Triton Media", confidence: 0.95, status: "active", created_at: iso(60) },
];

const CLOSED_CASE_GRAPH_NODES: GraphNode[] = CLOSED_CASE_ENTITIES.map((e) => ({
  id: e.id,
  entity_type: e.entity_type,
  canonical_value: e.canonical_value,
  display_value: e.display_value,
  status: e.status,
  confidence: e.confidence,
  aliases: [],
}));

const CLOSED_CASE_GRAPH_EDGES: GraphEdge[] = [
  { id: uid(8101), source: uid(8001), target: uid(8002), relationship_type: "owns", confidence: 0.99, context: null },
  { id: uid(8102), source: uid(8001), target: uid(8003), relationship_type: "works_for", confidence: 0.97, context: null },
];

export const SECONDARY_CASE_DATA = {
  entities: SECONDARY_ENTITIES,
  relationships: SECONDARY_RELATIONSHIPS,
  findings: SECONDARY_FINDINGS,
  evidence: SECONDARY_EVIDENCE,
  jobs: SECONDARY_JOBS,
  graphNodes: SECONDARY_ENTITIES.map((e) => ({
    id: e.id,
    entity_type: e.entity_type,
    canonical_value: e.canonical_value,
    display_value: e.display_value,
    status: e.status,
    confidence: e.confidence,
    aliases: [] as string[],
  })),
  graphEdges: SECONDARY_RELATIONSHIPS.map((r) => ({
    id: r.id,
    source: r.source_entity_id,
    target: r.target_entity_id,
    relationship_type: r.relationship_type,
    confidence: r.confidence,
    context: null,
  })),
  jobsList: SECONDARY_JOBS,
};

export const TERTIARY_CASE_ENTITIES = TERTIARY_ENTITIES;
export const CLOSED_CASE_GRAPH = {
  nodes: CLOSED_CASE_GRAPH_NODES,
  edges: CLOSED_CASE_GRAPH_EDGES,
};

export const MOCK_CASES: Case[] = [
  {
    id: CASE_ID_MAIN,
    case_number: "DEMO-2026-001",
    title: "Operation Paper Citadel",
    description:
      "Surveillance and banking review against the TechSecure identifier cell. Objective: confirm whether identifiers, call volume and fund movement share a single operator before any attribution is made.",
    status: "in_progress",
    owner_id: USER_INVESTIGATOR_ID,
    created_at: iso(12),
    updated_at: iso(0, 3),
  },
  {
    id: CASE_ID_SECONDARY,
    case_number: "CS-78B22A01",
    title: "Manifest review — Skyline Imports",
    description: "Import manifest anomalies: shipment values diverge from recorded customs declarations.",
    status: "open",
    owner_id: USER_INVESTIGATOR_ID,
    created_at: iso(8),
    updated_at: iso(2),
  },
  {
    id: CASE_ID_TERTIARY,
    case_number: "CS-11BF9032",
    title: "Accounts anomaly — Meena Traders",
    description: "Rapid movement of balances between newly opened accounts.",
    status: "open",
    owner_id: USER_ADMIN_ID,
    created_at: iso(5),
    updated_at: iso(1),
  },
  {
    id: CASE_ID_CLOSED,
    case_number: "CS-24911C07",
    title: "Closed replication run",
    description: "Control case used to validate deterministic analytics output.",
    status: "closed",
    owner_id: USER_INVESTIGATOR_ID,
    created_at: iso(60),
    updated_at: iso(40),
  },
];

/* ---------------------------------------------------------------- */
/* Audit                                                               */
/* ---------------------------------------------------------------- */

interface AuditSeed {
  id: number;
  action: string;
  resourceType: string;
  caseKey?: string;
  meta: Record<string, unknown> | null;
  daysAgo: number;
  hoursAgo?: number;
  actor: string;
}

const AUDIT_SEEDS: AuditSeed[] = [
  { id: 1, action: "case.created", resourceType: "case", caseKey: CASE_ID_MAIN, meta: { title: "Operation Paper Citadel", case_number: "DEMO-2026-001" }, daysAgo: 12, actor: "investigator" },
  { id: 2, action: "evidence.uploaded", resourceType: "evidence_file", caseKey: CASE_ID_MAIN, meta: { filename: "demo_cdr_june.csv", format: "csv" }, daysAgo: 10, actor: "investigator" },
  { id: 3, action: "ingestion.job_ran", resourceType: "ingestion_job", caseKey: CASE_ID_MAIN, meta: { status: "completed" }, daysAgo: 10, hoursAgo: 1, actor: "investigator" },
  { id: 4, action: "evidence.uploaded", resourceType: "evidence_file", caseKey: CASE_ID_MAIN, meta: { filename: "demo_surveillance.txt", format: "txt" }, daysAgo: 9, actor: "investigator" },
  { id: 5, action: "ingestion.job_ran", resourceType: "ingestion_job", caseKey: CASE_ID_MAIN, meta: { status: "completed" }, daysAgo: 9, hoursAgo: 1, actor: "investigator" },
  { id: 6, action: "evidence.uploaded", resourceType: "evidence_file", caseKey: CASE_ID_MAIN, meta: { filename: "bank_accounts_q2.json", format: "json" }, daysAgo: 8, actor: "investigator" },
  { id: 7, action: "ingestion.job_ran", resourceType: "ingestion_job", caseKey: CASE_ID_MAIN, meta: { status: "completed" }, daysAgo: 8, hoursAgo: 2, actor: "investigator" },
  { id: 8, action: "analytics.run_completed", resourceType: "analytics_run", caseKey: CASE_ID_MAIN, meta: { status: "completed", stage: "complete" }, daysAgo: 6, hoursAgo: 2, actor: "analyst" },
  { id: 9, action: "finding.status_changed", resourceType: "finding", caseKey: CASE_ID_MAIN, meta: { from: "NEW", to: "REVIEWED", reason: "Cross-checked against call records" }, daysAgo: 2, hoursAgo: 3, actor: "investigator" },
  { id: 10, action: "finding.status_changed", resourceType: "finding", caseKey: CASE_ID_MAIN, meta: { from: "NEW", to: "DISMISSED", reason: "Insufficient independent sources" }, daysAgo: 1, hoursAgo: 6, actor: "analyst" },
  { id: 11, action: "auth.login_succeeded", resourceType: "user", meta: { expires_in_minutes: 30 }, daysAgo: 0, hoursAgo: 3, actor: "investigator" },
  { id: 12, action: "case.updated", resourceType: "case", caseKey: CASE_ID_MAIN, meta: { changes: { status: "in_progress" } }, daysAgo: 0, hoursAgo: 3, actor: "investigator" },
  { id: 13, action: "case.created", resourceType: "case", caseKey: CASE_ID_SECONDARY, meta: { title: "Manifest review — Skyline Imports" }, daysAgo: 8, actor: "investigator" },
  { id: 14, action: "case.created", resourceType: "case", caseKey: CASE_ID_TERTIARY, meta: { title: "Accounts anomaly — Meena Traders" }, daysAgo: 5, actor: "admin" },
  { id: 15, action: "auth.user_created", resourceType: "user", meta: { username: "analyst", role: "ANALYST" }, daysAgo: 14, actor: "admin" },
];

const ACTOR_ID: Record<string, string> = {
  admin: USER_ADMIN_ID,
  investigator: USER_INVESTIGATOR_ID,
  analyst: USER_ANALYST_ID,
  viewer: USER_VIEWER_ID,
};

export const MAIN_AUDIT: AuditEvent[] = AUDIT_SEEDS.map((seed) => ({
  id: uid(900 + seed.id),
  actor_id: ACTOR_ID[seed.actor],
  action: seed.action,
  resource_type: seed.resourceType,
  resource_id: uid(900 + seed.id),
  case_id: seed.caseKey ?? null,
  metadata_: seed.meta,
  created_at: iso(seed.daysAgo, seed.hoursAgo ?? 0, seed.id * 4),
}));

/* ---------------------------------------------------------------- */
/* Derived summary                                                     */
/* ---------------------------------------------------------------- */

export function summaryForCase(caseId: string): {
  entity_count: number;
  relationship_count: number;
  community_count: number;
  finding_count: number;
  average_network_score: number;
  profile_tiers: Record<string, number>;
  priority_tiers: Record<string, number>;
  findings_by_severity: Record<string, number>;
  findings_by_type: Record<string, number>;
  exact_graph: boolean;
} {
  if (caseId === CASE_ID_MAIN) {
    const profileTiers: Record<string, number> = {};
    const priorityTiers: Record<string, number> = {};
    for (const p of MAIN_NETWORK_PROFILES) profileTiers[p.tier] = (profileTiers[p.tier] ?? 0) + 1;
    for (const p of MAIN_PRIORITIES) priorityTiers[p.tier] = (priorityTiers[p.tier] ?? 0) + 1;
    const stats = findingsStatsFor(MAIN_FINDINGS);
    return {
      entity_count: MAIN_ENTITIES.length,
      relationship_count: MAIN_RELATIONSHIPS.length,
      community_count: MAIN_COMMUNITIES.length,
      finding_count: MAIN_FINDINGS.length,
      average_network_score: 0.6,
      profile_tiers: profileTiers,
      priority_tiers: priorityTiers,
      findings_by_severity: stats.by_severity,
      findings_by_type: stats.by_type,
      exact_graph: true,
    };
  }
  if (caseId === CASE_ID_SECONDARY) {
    const stats = findingsStatsFor(SECONDARY_FINDINGS);
    return {
      entity_count: SECONDARY_ENTITIES.length,
      relationship_count: SECONDARY_RELATIONSHIPS.length,
      community_count: 1,
      finding_count: SECONDARY_FINDINGS.length,
      average_network_score: 0.31,
      profile_tiers: { MONITORED: 2, PERIPHERAL: 4 },
      priority_tiers: { MEDIUM: 1, LOW: 5 },
      findings_by_severity: stats.by_severity,
      findings_by_type: stats.by_type,
      exact_graph: true,
    };
  }
  if (caseId === CASE_ID_CLOSED) {
    return {
      entity_count: CLOSED_CASE_ENTITIES.length,
      relationship_count: CLOSED_CASE_GRAPH_EDGES.length,
      community_count: 1,
      finding_count: 0,
      average_network_score: 0,
      profile_tiers: {},
      priority_tiers: {},
      findings_by_severity: {},
      findings_by_type: {},
      exact_graph: true,
    };
  }
  return {
    entity_count: TERTIARY_ENTITIES.length,
    relationship_count: 0,
    community_count: 0,
    finding_count: 0,
    average_network_score: 0,
    profile_tiers: {},
    priority_tiers: {},
    findings_by_severity: {},
    findings_by_type: {},
    exact_graph: true,
  };
}

export const MOCK_SHA_GRACE = true;