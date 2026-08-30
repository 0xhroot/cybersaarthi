import { Badge, type BadgeProps } from "@/components/ui/badge";
import type {
  CaseStatus,
  EntityStatus,
  EntityType,
  FindingStatus,
  FindingType,
  GraphSyncStatus,
  JobStatus,
  PriorityTier,
  ProfileTier,
  RelationshipType,
  Severity,
} from "@/types/domain";

export const SEVERITY_META: Record<Severity, { label: string; tone: BadgeProps["tone"] }> = {
  CRITICAL: { label: "Critical", tone: "critical" },
  HIGH: { label: "High", tone: "high" },
  MEDIUM: { label: "Medium", tone: "medium" },
  LOW: { label: "Low", tone: "low" },
};

export function SeverityBadge({ value }: { value: Severity }) {
  const meta = SEVERITY_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export const FINDING_STATUS_META: Record<FindingStatus, { label: string; tone: BadgeProps["tone"] }> = {
  NEW: { label: "New", tone: "info" },
  REVIEWED: { label: "Reviewed", tone: "accent" },
  DISMISSED: { label: "Dismissed", tone: "neutral" },
  CONFIRMED: { label: "Confirmed", tone: "success" },
};

export function FindingStatusBadge({ value }: { value: FindingStatus }) {
  const meta = FINDING_STATUS_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export const CASE_STATUS_META: Record<CaseStatus, { label: string; tone: BadgeProps["tone"] }> = {
  open: { label: "Open", tone: "info" },
  in_progress: { label: "In progress", tone: "accent" },
  closed: { label: "Closed", tone: "neutral" },
  archived: { label: "Archived", tone: "neutral" },
};

export function CaseStatusBadge({ value }: { value: CaseStatus }) {
  const meta = CASE_STATUS_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export const ENTITY_TYPE_META: Record<EntityType, { label: string; tone: BadgeProps["tone"] }> = {
  person: { label: "Person", tone: "accent" },
  phone: { label: "Phone", tone: "info" },
  vehicle: { label: "Vehicle", tone: "high" },
  organization: { label: "Organization", tone: "success" },
  account: { label: "Account", tone: "medium" },
  location: { label: "Location", tone: "low" },
  document: { label: "Document", tone: "neutral" },
  event: { label: "Event", tone: "neutral" },
};

export function EntityTypeBadge({ value }: { value: EntityType }) {
  const meta = ENTITY_TYPE_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function EntityTypeLabel({ value }: { value: EntityType }) {
  return ENTITY_TYPE_META[value].label;
}

export const PROFILE_TIER_META: Record<ProfileTier, { label: string; tone: BadgeProps["tone"] }> = {
  FOCAL: { label: "Focal", tone: "critical" },
  SIGNIFICANT: { label: "Significant", tone: "high" },
  MONITORED: { label: "Monitored", tone: "medium" },
  PERIPHERAL: { label: "Peripheral", tone: "neutral" },
};

export function ProfileTierBadge({ value }: { value: ProfileTier }) {
  const meta = PROFILE_TIER_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export const PRIORITY_META: Record<PriorityTier, { label: string; tone: BadgeProps["tone"] }> = {
  CRITICAL: { label: "Critical", tone: "critical" },
  HIGH: { label: "High", tone: "high" },
  MEDIUM: { label: "Medium", tone: "medium" },
  LOW: { label: "Low", tone: "low" },
};

export function PriorityBadge({ value }: { value: PriorityTier }) {
  const meta = PRIORITY_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export const JOB_STATUS_META: Record<JobStatus, { label: string; tone: BadgeProps["tone"] }> = {
  pending: { label: "Pending", tone: "low" },
  running: { label: "Running", tone: "accent" },
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "critical" },
  partial: { label: "Partial", tone: "high" },
};

export function JobStatusBadge({ value }: { value: JobStatus }) {
  const meta = JOB_STATUS_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function GraphSyncBadge({ value }: { value: GraphSyncStatus }) {
  const tone: BadgeProps["tone"] =
    value === "synced" ? "success" : value === "failed" ? "critical" : "accent";
  return <Badge tone={tone}>{value}</Badge>;
}

export const ENTITY_STATUS_META: Record<EntityStatus, { label: string; tone: BadgeProps["tone"] }> = {
  active: { label: "Active", tone: "success" },
  merged: { label: "Merged", tone: "info" },
  review: { label: "Review", tone: "accent" },
  rejected: { label: "Rejected", tone: "neutral" },
};

export function EntityStatusBadge({ value }: { value: EntityStatus }) {
  const meta = ENTITY_STATUS_META[value];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export const FINDING_TYPE_META: Record<FindingType, { label: string }> = {
  hypothesis: { label: "Hypothesis" },
  pattern: { label: "Pattern" },
  anomaly: { label: "Anomaly" },
  network_insight: { label: "Network insight" },
  relationship_insight: { label: "Relationship insight" },
};

export function FindingTypeBadge({ value }: { value: FindingType }) {
  const meta = FINDING_TYPE_META[value];
  return <Badge>{meta.label}</Badge>;
}

export const RELATIONSHIP_TYPE_META: Record<RelationshipType, { label: string }> = {
  called: { label: "Called" },
  owns: { label: "Owns" },
  works_for: { label: "Works for" },
  associated_with: { label: "Associated with" },
  located_at: { label: "Located at" },
  visited: { label: "Visited" },
  transferred_to: { label: "Transferred to" },
};