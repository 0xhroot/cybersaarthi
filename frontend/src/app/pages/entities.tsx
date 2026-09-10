import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Search, Users, Merge, Check, X } from "lucide-react";
import { useEntities, useReviewResolution, useAcceptMatch, useRejectMatch, useMergeEntities } from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { useDebounce } from "@/hooks/ui";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { EntityTypeBadge, EntityStatusBadge } from "@/components/status";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { toast } from "@/components/ui/toast";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

  const review = useReviewResolution(caseId);

  const canMerge = useCan("entity.merge");
  const canReview = useCan("findings.review");

  const acceptMatch = useAcceptMatch(caseId);
  const rejectMatch = useRejectMatch(caseId);
  const mergeEntities = useMergeEntities(caseId);

  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergePrimary, setMergePrimary] = useState("");
  const [mergeDuplicate, setMergeDuplicate] = useState("");

  const mergeOptions = (entities.data?.items ?? []).filter((e) => e.status === "active");

  const submitAccept = async (matchId: string) => {
    try {
      await acceptMatch.mutateAsync(matchId);
      toast({ title: "Match accepted", description: "The candidate was linked to the primary entity." });
    } catch (err) {
      toast({ title: "Action failed", description: (err as Error).message });
    }
  };

  const submitReject = async (matchId: string) => {
    try {
      await rejectMatch.mutateAsync(matchId);
      toast({ title: "Match rejected", description: "The candidate was dismissed." });
    } catch (err) {
      toast({ title: "Action failed", description: (err as Error).message });
    }
  };

  const submitMerge = async () => {
    if (!mergePrimary || !mergeDuplicate) {
      toast({ title: "Choose both entities", description: "Select the surviving and duplicate entities to merge." });
      return;
    }
    try {
      await mergeEntities.mutateAsync({ primaryEntityId: mergePrimary, mergeEntityId: mergeDuplicate });
      toast({ title: "Entities merged", description: "The duplicate folded into the primary and the graph was updated." });
      setMergeOpen(false);
      setMergePrimary("");
      setMergeDuplicate("");
    } catch (err) {
      toast({ title: "Merge failed", description: (err as Error).message });
    }
  };

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
        actions={<div className="flex items-center gap-2">
          {canMerge ? (
            <Button variant="secondary" size="sm" onClick={() => setMergeOpen(true)}>
              <Merge className="size-4" /> Merge entities
            </Button>
          ) : null}
          <div className="flex items-center gap-2 text-xs text-dim">
            <Users className="size-4" />
            {entities.data?.total ?? "…"} entities
          </div>
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

      {review.data && review.data.items.length > 0 ? (
        <div className="mt-5">
          <Card>
            <CardContent className="space-y-1">
              <p className="mb-2 text-[11px] uppercase tracking-wider text-dim">
                Resolution review · {review.data.total} candidates needing attention
              </p>
              <div className="divide-y divide-border">
                {review.data.items.map((c) => (
                  <div key={c.match_id} className="flex items-center gap-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-foreground">{c.candidate_value}</p>
                      <p className="text-[11px] text-dim">
                        {c.candidate_type} · {c.decision === "auto_match" ? "auto-matched" : "manual review"} · score {formatPercent(c.score, 0)}
                      </p>
                    </div>
                    <EntityTypeBadge value={c.candidate_type as EntityType} />
                    {canReview ? (
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Accept match"
                          aria-label="Accept match"
                          disabled={acceptMatch.isPending || rejectMatch.isPending}
                          onClick={() => void submitAccept(c.match_id)}
                        >
                          <Check className="size-4 text-success" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Reject match"
                          aria-label="Reject match"
                          disabled={acceptMatch.isPending || rejectMatch.isPending}
                          onClick={() => void submitReject(c.match_id)}
                        >
                          <X className="size-4 text-critical" />
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Dialog open={mergeOpen} onOpenChange={setMergeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Merge entities</DialogTitle>
            <DialogDescription>Fold one duplicate entity into a surviving primary. Their relationships are combined and the graph re-synced.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label>Primary entity (survives)</Label>
              <Select value={mergePrimary} onValueChange={setMergePrimary}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Choose primary…" /></SelectTrigger>
                <SelectContent>
                  {mergeOptions.map((e) => (
                    <SelectItem key={e.id} value={e.id}>{e.display_value} · {e.entity_type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Duplicate entity (merged away)</Label>
              <Select value={mergeDuplicate} onValueChange={setMergeDuplicate}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Choose duplicate…" /></SelectTrigger>
                <SelectContent>
                  {mergeOptions.filter((e) => e.id !== mergePrimary).map((e) => (
                    <SelectItem key={e.id} value={e.id}>{e.display_value} · {e.entity_type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setMergeOpen(false)}>Cancel</Button>
            <Button variant="danger" disabled={mergeEntities.isPending} onClick={() => void submitMerge()}>
              {mergeEntities.isPending ? "Merging…" : "Merge entities"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}