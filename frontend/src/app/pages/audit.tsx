import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useAudit } from "@/hooks/queries";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative, formatTime, shortId } from "@/lib/utils";

const RESOURCE_TYPES = ["case", "evidence", "finding", "entity", "analytics", "user", "system"];

export default function AuditPage() {
  const [resourceType, setResourceType] = useState("all");
  const audit = useAudit({ limit: 200, resource_type: resourceType === "all" ? undefined : resourceType });

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="Immutable record of actions across cases. Used to review who did what, when."
      />

      <div className="mt-4">
        <Select
          value={resourceType}
          onValueChange={(value) => setResourceType(value)}
        >
          <SelectTrigger className="w-[200px]"><SelectValue placeholder="All resources" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All resources</SelectItem>
            {RESOURCE_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-4">
        {audit.isLoading ? (
          <Card><CardContent className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
          </CardContent></Card>
        ) : audit.isError ? (
          <Card><ErrorState error={audit.error} onRetry={() => void audit.refetch()} /></Card>
        ) : (audit.data?.items ?? []).length === 0 ? (
          <Card><EmptyState title="No audit events" description="Actions recorded here as investigators work." /></Card>
        ) : (
          <Card>
            <Table>
              <THead>
                <TR>
                  <TH>When</TH>
                  <TH className="hidden md:table-cell">Actor</TH>
                  <TH>Action</TH>
                  <TH className="hidden sm:table-cell">Resource</TH>
                  <TH className="hidden lg:table-cell">Case</TH>
                  <TH className="text-right">Record</TH>
                </TR>
              </THead>
              <TBody>
                {(audit.data?.items ?? []).map((event) => (
                  <TR key={event.id}>
                    <TD className="whitespace-nowrap text-xs text-muted" title={event.created_at}>
                      {formatRelative(event.created_at)} <span className="text-dim">· {formatTime(event.created_at)}</span>
                    </TD>
                    <TD className="hidden font-mono text-[11px] text-muted md:table-cell">
                      {event.actor_id ? (
                        <span className="inline-flex items-center gap-1.5">
                          <ShieldCheck className="size-3 text-dim" />
                          {shortId(event.actor_id)}
                        </span>
                      ) : <span className="text-dim">system</span>}
                    </TD>
                    <TD className="max-w-[220px] truncate text-xs text-foreground">{event.action}</TD>
                    <TD className="hidden sm:table-cell"><Badge>{event.resource_type}</Badge></TD>
                    <TD className="hidden font-mono text-[11px] text-dim lg:table-cell">
                      {event.case_id ? shortId(event.case_id) : "—"}
                    </TD>
                    <TD className="text-right font-mono text-[10px] text-dim">{shortId(event.id)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>
        )}
      </div>
    </PageContainer>
  );
}