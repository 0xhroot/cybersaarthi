import { useState } from "react";
import { Fingerprint, Gavel, Loader2, PlusCircle, ShieldAlert, Sparkles } from "lucide-react";

import {
  useArtifacts,
  useCustodyAudit,
  useCustodyChronology,
  useExplainFinding,
  useIntelJobs,
  useRecordCustodyEvent,
  useVerifyIntegrity,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/loading";
import { toast } from "@/components/ui/toast";
import { formatDateTime, shortId } from "@/lib/utils";
import type { CustodyEventOut, IntegrityVerificationResponse } from "@/types/domain";

/**
 * Evidence integrity + chain-of-custody panel (feature 9).
 *
 * Contract: verification compares recorded and recomputed digests — a
 * `match` is the only green state, a `mismatch` is red, and unavailable
 * bytes or a missing recorded digest are amber "cannot verify" results, never
 * passes. Custody events are append-only records; findings come from the
 * deterministic rule engine, and the "explain" text is always labelled as
 * unverified AI narration, never as certification.
 */

const EVENT_TONES: Record<string, "info" | "accent" | "neutral"> = {
  collected: "info",
  transferred: "accent",
  received: "info",
  verified: "accent",
};

function verificationTone(status: IntegrityVerificationResponse["status"]): {
  label: string;
  tone: "success" | "critical" | "high";
} {
  if (status === "match") return { label: "Digest matches", tone: "success" };
  if (status === "mismatch") return { label: "Digest MISMATCH", tone: "critical" };
  return { label: "Cannot verify", tone: "high" };
}

function verificationDetail(result: IntegrityVerificationResponse): string {
  if (result.status === "match") return "Recomputed SHA-256 equals the digest recorded at upload.";
  if (result.status === "mismatch") return "The stored bytes no longer hash to the recorded digest — treat the file as altered.";
  if (result.status === "missing_source") return "The stored object is gone: no bytes exist to hash. This is not a pass.";
  if (result.status === "missing_expected") return "No recorded digest exists for this evidence — nothing to compare against.";
  return "The recorded algorithm is not sha256; this service cannot compute it.";
}

function EventRow({ event }: { event: CustodyEventOut }) {
  return (
    <div className="rounded border border-border bg-surface-2 px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={EVENT_TONES[event.event_type] ?? "neutral"}>{event.event_type}</Badge>
        <span className="text-[11px] text-dim" title={formatDateTime(event.occurred_at)}>
          {formatDateTime(event.occurred_at)}
        </span>
        <span className="ml-auto font-mono text-[10px] text-dim">{shortId(event.id)}</span>
      </div>
      <p className="mt-1 text-[11px] text-muted">
        {[
          event.collector ? `collector ${event.collector}` : null,
          event.transferor ? `from ${event.transferor}` : null,
          event.recipient ? `to ${event.recipient}` : null,
          event.location ? `at ${event.location}` : null,
        ]
          .filter(Boolean)
          .join(" · ") || "no parties recorded"}
      </p>
      {event.recorded_sha256 ? (
        <p className="mt-0.5 truncate font-mono text-[10px] text-dim">digest noted {event.recorded_sha256.slice(0, 16)}…</p>
      ) : null}
    </div>
  );
}

export function IntegrityPanel({ caseId, evidenceId }: { caseId: string; evidenceId: string }) {
  const canIngest = useCan("ingestion.run");
  const canRecord = useCan("evidence.upload");
  const chronology = useCustodyChronology(caseId, evidenceId);
  const verify = useVerifyIntegrity(caseId);
  const audit = useCustodyAudit(caseId);
  const record = useRecordCustodyEvent(caseId);
  const explain = useExplainFinding(caseId);
  const custodyJobs = useIntelJobs(caseId, "custody");
  const findings = useArtifacts(caseId, "custody_finding");

  const [verification, setVerification] = useState<IntegrityVerificationResponse | null>(null);
  const [eventOpen, setEventOpen] = useState(false);
  const [eventType, setEventType] = useState("collected");
  const [occurredAt, setOccurredAt] = useState("");
  const [parties, setParties] = useState({ collector: "", transferor: "", recipient: "", location: "", method: "", notes: "" });

  const runVerify = async () => {
    try {
      const result = await verify.mutateAsync(evidenceId);
      setVerification(result);
    } catch (err) {
      toast({ title: "Verification failed", description: (err as Error).message });
    }
  };

  const runAudit = async () => {
    try {
      const result = await audit.mutateAsync(evidenceId);
      toast({ title: "Custody audit queued", description: "Deterministic rules evaluate the recorded events." });
      return result;
    } catch (err) {
      toast({ title: "Audit failed", description: (err as Error).message });
      return null;
    }
  };

  const submitEvent = async () => {
    try {
      await record.mutateAsync({
        evidenceId,
        event: {
          event_type: eventType,
          // <input type="datetime-local"> has no zone; the API requires an
          // explicit one, so convert to a UTC ISO-8601 string here.
          occurred_at: new Date(occurredAt).toISOString(),
          collector: parties.collector || null,
          transferor: parties.transferor || null,
          recipient: parties.recipient || null,
          location: parties.location || null,
          method: parties.method || null,
          notes: parties.notes || null,
        },
      });
      toast({ title: "Custody event recorded", description: "The event was appended to the evidence's custody log." });
      setEventOpen(false);
      setOccurredAt("");
      setParties({ collector: "", transferor: "", recipient: "", location: "", method: "", notes: "" });
    } catch (err) {
      toast({ title: "Event refused", description: (err as Error).message });
    }
  };

  const runExplain = async (artifactId: string) => {
    try {
      const result = await explain.mutateAsync(artifactId);
      toast({ title: "Explanation recorded", description: result.text.slice(0, 140) });
    } catch (err) {
      toast({ title: "Explanation failed", description: (err as Error).message });
    }
  };

  const events = chronology.data?.events ?? [];
  const latestAudit = (custodyJobs.data?.items ?? []).find((j) => j.evidence_file_id === evidenceId);
  const evidenceFindings = findings.data?.items?.filter((f) => f.evidence_file_id === evidenceId) ?? [];
  const pendingFindings = evidenceFindings.filter((f) => f.status === "pending_review");
  const activeAudit = (custodyJobs.data?.items ?? []).find(
    (j) => j.evidence_file_id === evidenceId && (j.status === "pending" || j.status === "running"),
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-dim">Integrity & chain of custody</p>
        {canIngest ? (
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={verify.isPending} onClick={() => void runVerify()}>
              <Fingerprint className="size-3.5" /> Verify
            </Button>
            <Button size="sm" disabled={audit.isPending || Boolean(activeAudit)} onClick={() => void runAudit()}>
              <Gavel className="size-3.5" /> Audit custody
            </Button>
          </div>
        ) : null}
      </div>

      {verify.isPending ? <Skeleton className="h-12" /> : null}
      {verification ? (
        <div
          className={`rounded-lg border p-3 ${
            verification.status === "match"
              ? "border-success/25 bg-success/8"
              : verification.status === "mismatch"
                ? "border-critical/30 bg-critical/8"
                : "border-high/25 bg-high/8"
          }`}
        >
          <div className="flex items-center gap-2">
            {verification.status === "mismatch" ? <ShieldAlert className="size-4 text-critical" /> : null}
            <Badge tone={verificationTone(verification.status).tone}>{verificationTone(verification.status).label}</Badge>
            <span className="text-[11px] text-dim">{verification.algorithm ?? "unknown algorithm"}</span>
          </div>
          <p className="mt-1.5 text-[11px] text-muted">{verificationDetail(verification)}</p>
          <p className="mt-1 truncate font-mono text-[10px] text-dim">
            expected {verification.expected_sha256?.slice(0, 20) ?? "—"} · recomputed {verification.calculated_sha256?.slice(0, 20) ?? "—"}
          </p>
        </div>
      ) : null}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[11px] uppercase tracking-wider text-dim">
            Custody log {chronology.data ? `(${chronology.data.event_count})` : ""}
          </p>
          {canRecord ? (
            <Button size="sm" variant="ghost" onClick={() => setEventOpen((open) => !open)}>
              <PlusCircle className="size-3.5" /> Record event
            </Button>
          ) : null}
        </div>
        {chronology.isLoading ? (
          <Skeleton className="h-16" />
        ) : events.length === 0 ? (
          <p className="rounded border border-border bg-surface-2 px-2.5 py-3 text-[11px] text-dim">
            No custody events recorded yet — absence of events is not evidence of integrity.
          </p>
        ) : (
          <div className="space-y-1.5">
            {events.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </div>
        )}
      </div>

      {eventOpen ? (
        <div className="space-y-2 rounded-lg border border-border bg-surface-2 p-3">
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[11px] text-dim">Event type</span>
              <select
                className="w-full rounded border border-border bg-surface-3 px-2 py-1.5 text-xs text-foreground outline-none"
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
              >
                {["collected", "transferred", "received", "sealed", "unsealed", "verified", "accessed", "exported", "restored", "disposed"].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-dim">Occurred at (with time zone)</span>
              <Input type="datetime-local" value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} className="text-xs" />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {(["collector", "transferor", "recipient", "location"] as const).map((key) => (
              <Input
                key={key}
                placeholder={key}
                value={parties[key]}
                onChange={(e) => setParties((p) => ({ ...p, [key]: e.target.value }))}
                className="text-xs"
              />
            ))}
          </div>
          <div className="flex gap-2">
            <Button size="sm" disabled={record.isPending || !occurredAt} onClick={() => void submitEvent()}>
              {record.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <PlusCircle className="size-3.5" />} Append event
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEventOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {latestAudit ? (
        <p className="text-[11px] text-dim">
          Last audit {latestAudit.status} · findings: {String((latestAudit.result_summary as Record<string, unknown> | null)?.findings_new ?? 0)} new,{" "}
          {String((latestAudit.result_summary as Record<string, unknown> | null)?.findings_existing ?? 0)} existing
        </p>
      ) : null}

      {pendingFindings.map((finding) => {
        const payload = finding.payload as { rule?: string; message?: string; type?: string };
        const explanation = findings.data?.items.find(
          (a) => a.parent_artifact_id === finding.id && (a.payload as { type?: string }).type === "ai_explanation",
        );
        return (
          <div key={finding.id} className="rounded-lg border border-border bg-surface-2 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="high">{payload.rule ?? "custody finding"}</Badge>
              <Badge tone="info">deterministic rule engine</Badge>
              <span className="ml-auto font-mono text-[10px] text-dim">{shortId(finding.id)}</span>
            </div>
            <p className="mt-1.5 text-[11px] text-muted">{payload.message ?? "rule triggered on the custody log"}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {canIngest ? (
                <Button size="sm" variant="secondary" disabled={explain.isPending} onClick={() => void runExplain(finding.id)}>
                  <Sparkles className="size-3.5" /> Explain
                </Button>
              ) : null}
              {explanation ? (
                <Badge tone="high">AI narration — unverified, does not certify custody</Badge>
              ) : null}
            </div>
            {explanation ? (
              <p className="mt-1.5 rounded border border-high/20 bg-high/8 p-2 text-[11px] text-muted">
                {(explanation.payload as { text?: string }).text ?? ""}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
