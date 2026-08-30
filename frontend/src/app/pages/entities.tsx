import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Search, Users } from "lucide-react";
import { useEntities } from "@/hooks/queries";
import { useDebounce } from "@/hooks/ui";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { EntityTypeBadge, EntityStatusBadge } from "@/components/status";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatPercent } from "@/lib/utils";
import type { EntityType } from "@/types/domain";

const ENTITY_TYPES: EntityType[] = [
  "person",
  "phone",
  "vehicle",
  "organization",
  "account",
  "location",
  "document",
  "event",
];

export default function EntitiesPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const debounced = useDebounce(query, 300);
  const entityType = params.get("type") ?? "";

  const entities = useEntities(caseId, {
    entity_type: entityType || undefined,
    query: debounced || undefined,
    limit: 200,
  });

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced);
    else next.delete("q");
    if (entityType) next.set("type", entityType);
    else next.delete("type");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, entityType]);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Knowledge graph"
        title="Entities"
        description="Who and what participates in this network — people, telephones, vehicles, accounts and more."
        actions={<div className="flex items-center gap-2 text-xs text-dim">
          <Users className="size-4" />
          {entities.data?.total ?? "…"} entities
        </div>}
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search entities…" className="pl-9" />
        </div>
        <Select
          value={entityType}
          onValueChange={(value) => {
            setParams((p) => {
              const next = new URLSearchParams(p);
              if (value && value !== "all") next.set("type", value);
              else next.delete("type");
              return next;
            });
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {ENTITY_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-4">
        {entities.isLoading ? (
          <Card>
            <CardContent className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-11" />
              ))}
            </CardContent>
          </Card>
        ) : entities.isError ? (
          <Card>
            <ErrorState error={entities.error} onRetry={() => void entities.refetch()} />
          </Card>
        ) : (entities.data?.items ?? []).length === 0 ? (
          <Card>
            <EmptyState title="No entities found" description="Adjust the filters, or ingest evidence to grow the graph." />
          </Card>
        ) : (
          <Card>
            <Table>
              <THead>
                <TR>
                  <TH>Type</TH>
                  <TH>Display value</TH>
                  <TH className="hidden md:table-cell">Canonical value</TH>
                  <TH className="hidden sm:table-cell">Status</TH>
                  <TH className="text-right">Confidence</TH>
                </TR>
              </THead>
              <TBody>
                {(entities.data?.items ?? []).map((e) => (
                  <TR
                    key={e.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/app/cases/${caseId}/entities/${e.id}`)}
                  >
                    <TD className="w-28">
                      <EntityTypeBadge value={e.entity_type} />
                    </TD>
                    <TD className="max-w-[220px] truncate font-medium text-foreground">{e.display_value}</TD>
                    <TD className="hidden max-w-[200px] truncate font-mono text-xs text-muted md:table-cell">
                      {e.canonical_value}
                    </TD>
                    <TD className="hidden sm:table-cell">
                      <EntityStatusBadge value={e.status} />
                    </TD>
                    <TD className="tabular w-24 text-right text-xs text-dim">
                      {e.confidence != null ? formatPercent(e.confidence, 0) : "—"}
                    </TD>
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