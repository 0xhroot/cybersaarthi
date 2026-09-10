import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useParams } from "react-router-dom";
import { Upload, FileSearch, Workflow, Database, Trash2, RefreshCw, RotateCcw } from "lucide-react";
import {
  useEvidence,
  useEvidenceDetail,
  useIngestEvidence,
  useIngestJobs,
  useProvenance,
  useUploadEvidence,
  useDeleteEvidence,
  useRetryGraphSync,
  useCollections,
  useRestoreEvidence,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import {
  Drawer,
  DrawerCloseIcon,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import { formatBytes, formatDateTime, formatRelative, shortId } from "@/lib/utils";

const DATA_SOURCES = [
  { value: "CSV_Journals", label: "CSV Journals" },
  { value: "QuickPage", label: "QuickPage Chat" },
  { value: "TransportLogs", label: "Transport Logs" },
  { value: "FinancialSUM", label: "Financial SUM" },
  { value: "WebCamera", label: "Web Camera Tracker" },
  { value: "ManualSupport", label: "Manual Support" },
  { value: "PRELOADED", label: "Preloaded" },
];

function statusMeta(status: string): { label: string; tone: "success" | "info" | "critical" | "high" } {
  if (status === "parsed") return { label: "Parsed", tone: "success" };
  if (status === "failed") return { label: "Failed", tone: "critical" };
  if (status === "processing") return { label: "Processing", tone: "high" };
  return { label: "Stored", tone: "info" };
}

export default function EvidencePage() {
  const { caseId = "" } = useParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<string>("CSV_Journals");
  const [collectionId, setCollectionId] = useState<string>("none");
  const [picked, setPicked] = useState<File | null>(null);
  const [lastDeleted, setLastDeleted] = useState<{ id: string; filename: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const canUpload = useCan("evidence.upload");
  const canIngest = useCan("ingestion.run");
  const canDelete = useCan("evidence.delete");
  const canRestore = useCan("evidence.restore");

  const evidence = useEvidence(caseId, { limit: 50 });
  const jobs = useIngestJobs(caseId);
  const collections = useCollections(caseId);
  const detail = useEvidenceDetail(caseId, selectedId);
  const provenance = useProvenance(caseId, selectedId);
  const upload = useUploadEvidence(caseId);
  const ingest = useIngestEvidence(caseId);
  const remove = useDeleteEvidence(caseId);
  const restore = useRestoreEvidence(caseId);
  const retrySync = useRetryGraphSync(caseId);

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setPicked(file);
    e.target.value = "";
  };

  const submitUpload = async () => {
    if (!picked) return;
    try {
      await upload.mutateAsync({
        file: picked,
        dataSource,
        collectionId: collectionId === "none" ? undefined : collectionId,
      });
      toast({
        title: "Evidence stored",
        description: `${picked.name} uploaded and checksummed${collectionId !== "none" ? " into a sealed collection" : ""}.`,
      });
      setUploadOpen(false);
      setPicked(null);
      setCollectionId("none");
    } catch (err) {
      toast({ title: "Upload failed", description: (err as Error).message });
    }
  };

  const triggerIngest = async (evidenceFileId: string, filename: string) => {
    try {
      await ingest.mutateAsync(evidenceFileId);
      toast({ title: "Ingestion queued", description: `Processing ${filename}…` });
    } catch (err) {
      toast({ title: "Ingestion failed", description: (err as Error).message });
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await remove.mutateAsync(deleteTarget);
      const record = evidence.data?.items?.find((e) => e.id === deleteTarget);
      setLastDeleted({ id: deleteTarget, filename: record?.original_filename ?? "record" });
      toast({ title: "Evidence deleted", description: "The record was moved to the recycle bin." });
      setDeleteTarget(null);
      if (selectedId === deleteTarget) setSelectedId(null);
    } catch (err) {
      toast({ title: "Delete failed", description: (err as Error).message });
    }
  };

  const restoreDeleted = async () => {
    if (!lastDeleted) return;
    try {
      await restore.mutateAsync(lastDeleted.id);
      setLastDeleted(null);
      toast({ title: "Evidence restored", description: `${lastDeleted.filename} returned to the case evidence list.` });
    } catch (err) {
      toast({ title: "Restore failed", description: (err as Error).message });
    }
  };

  const triggerRetry = async (jobId: string) => {
    try {
      const result = await retrySync.mutateAsync(jobId);
      toast({
        title: "Graph sync retried",
        description: `nodes ${result.nodes_synced} · edges ${result.edges_synced}`,
      });
    } catch (err) {
      toast({ title: "Retry failed", description: (err as Error).message });
    }
  };

  const failedSyncJobs = (jobs.data?.items ?? []).filter((j) => j.graph_sync_status === "failed");

  const selectedDetail = detail.data;

  return (
    <PageContainer className="max-w-none">
      <PageHeader
        eyebrow="Source material"
        title="Evidence"
        description="Uploaded source records, their checksums, and ingestion status. Every extracted fact can be traced to a stored file."
        actions={
          canUpload ? (
            <Button onClick={() => setUploadOpen(true)}>
              <Upload className="size-4" /> Upload record
            </Button>
          ) : undefined
        }
      />

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Card><CardContent className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg bg-info/12 text-info"><Database className="size-4" /></span>
          <div>
            <p className="text-lg font-semibold tabular text-foreground">{evidence.data?.total ?? "—"}</p>
            <p className="text-[11px] uppercase tracking-wider text-dim">Stored records</p>
          </div>
        </CardContent></Card>
        <Card><CardContent className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg bg-success/12 text-success"><Workflow className="size-4" /></span>
          <div>
            <p className="text-lg font-semibold tabular text-foreground">
              {(jobs.data?.items ?? []).filter((j) => j.status === "completed").length}
            </p>
            <p className="text-[11px] uppercase tracking-wider text-dim">Ingested files</p>
          </div>
        </CardContent></Card>
        <Card><CardContent className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg bg-accent/12 text-accent-strong"><FileSearch className="size-4" /></span>
          <div>
            <p className="text-lg font-semibold tabular text-foreground">{provenance.data?.entity_count ?? "—"}</p>
            <p className="text-[11px] uppercase tracking-wider text-dim">Entities from selected file</p>
          </div>
        </CardContent></Card>
      </div>

      {lastDeleted && canRestore ? (
        <div className="mt-4">
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              <p className="min-w-0 flex-1 truncate text-xs text-foreground">
                <RotateCcw className="mr-1.5 inline size-3.5 text-info" />
                <span className="font-medium">{lastDeleted.filename}</span> is in the recycle bin — restore to bring it back with its checksum intact.
              </p>
              <Button size="sm" variant="secondary" disabled={restore.isPending} onClick={() => void restoreDeleted()}>
                <RotateCcw className="size-3.5" /> Restore
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {failedSyncJobs.length > 0 && canIngest ? (
        <div className="mt-4">
          <Card>
            <CardContent className="space-y-2">
              <p className="text-[11px] uppercase tracking-wider text-dim">Graph sync needs attention</p>
              {failedSyncJobs.map((job) => (
                <div key={job.id} className="flex items-center justify-between gap-3">
                  <p className="min-w-0 flex-1 truncate text-xs text-foreground">
                    Job {job.id.slice(0, 8)} — {job.graph_error ?? "graph sync failed"}
                  </p>
                  <Button size="sm" disabled={retrySync.isPending} onClick={() => void triggerRetry(job.id)}>
                    <RefreshCw className="size-3.5" /> Retry sync
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      ) : null}

      <div className="mt-4">
        {evidence.isLoading ? (
          <Card><CardContent className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
          </CardContent></Card>
        ) : evidence.isError ? (
          <Card><ErrorState error={evidence.error} onRetry={() => void evidence.refetch()} /></Card>
        ) : (evidence.data?.items ?? []).length === 0 ? (
          <Card><EmptyState
            title="No evidence yet"
            description="Upload a CSV, JSON or text extract to start building the case record."
            action={canUpload ? { label: "Upload record", onClick: () => setUploadOpen(true) } : undefined}
          /></Card>
        ) : (
          <Card>
            <Table>
              <THead>
                <TR>
                  <TH>Filename</TH>
                  <TH className="hidden md:table-cell">Format</TH>
                  <TH className="hidden sm:table-cell">Size</TH>
                  <TH className="hidden sm:table-cell">Records</TH>
                  <TH>Status</TH>
                  <TH className="hidden lg:table-cell">Uploaded</TH>
                  <TH className="w-28" />
                </TR>
              </THead>
              <TBody>
                {(evidence.data?.items ?? []).map((item) => {
                  const meta = statusMeta(item.status);
                  return (
                    <TR key={item.id} className="cursor-pointer" onClick={() => setSelectedId(item.id)}>
                      <TD className="max-w-[260px]">
                        <button type="button" className="block max-w-full truncate text-left font-medium text-foreground hover:text-accent">
                          {item.original_filename}
                        </button>
                      </TD>
                      <TD className="hidden font-mono text-xs text-muted md:table-cell">{item.format ?? "—"}</TD>
                      <TD className="hidden tabular text-xs text-muted sm:table-cell">{formatBytes(item.file_size)}</TD>
                      <TD className="hidden tabular text-xs text-muted sm:table-cell">{item.record_count ?? "—"}</TD>
                      <TD><Badge tone={meta.tone}>{meta.label}</Badge></TD>
                      <TD className="hidden text-xs text-dim lg:table-cell" title={formatDateTime(item.created_at)}>
                        {formatRelative(item.created_at)}
                      </TD>
                      <TD className="text-right">
                        {canIngest && item.status === "stored" ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={ingest.isPending}
                            onClick={(e) => {
                              e.stopPropagation();
                              void triggerIngest(item.id, item.original_filename);
                            }}
                          >
                            Ingest
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setSelectedId(item.id); }}>
                            Inspect
                          </Button>
                        )}
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </Card>
        )}
      </div>

      <Drawer open={selectedId !== null} onOpenChange={(open) => { if (!open) setSelectedId(null); }}>
        <DrawerContent>
          <DrawerHeader>
            <DrawerTitle className="text-sm font-medium">Evidence record</DrawerTitle>
            <DrawerCloseIcon />
          </DrawerHeader>
          <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {detail.isLoading ? (
              <div className="space-y-2"><Skeleton className="h-5 w-3/4" /><Skeleton className="h-24" /></div>
            ) : detail.isError ? (
              <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
            ) : selectedDetail ? (
              <>
                <div>
                  <p className="truncate text-sm font-medium text-foreground">{selectedDetail.original_filename}</p>
                  <p className="mt-1 text-xs text-dim">
                    {selectedDetail.data_source ?? "data source unrecorded"} · {formatDateTime(selectedDetail.created_at)}
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-surface-2 p-3 text-xs">
                  <p className="text-dim">SHA-256</p>
                  <p className="truncate font-mono text-foreground/80">{selectedDetail.sha256.slice(0, 20)}…</p>
                  <p className="text-dim">Stored key</p>
                  <p className="truncate font-mono text-foreground/80">{selectedDetail.stored_key}</p>
                  <p className="text-dim">Format</p>
                  <p className="font-mono text-foreground/80">{selectedDetail.format ?? "—"}</p>
                  <p className="text-dim">Encoding</p>
                  <p className="font-mono text-foreground/80">{selectedDetail.encoding ?? "—"}</p>
                  <p className="text-dim">File size</p>
                  <p className="tabular text-foreground/80">{formatBytes(selectedDetail.file_size)}</p>
                  <p className="text-dim">Records</p>
                  <p className="tabular text-foreground/80">{selectedDetail.record_count ?? "—"}</p>
                </div>

                <div>
                  <p className="mb-2 text-[11px] uppercase tracking-wider text-dim">Provenance summary</p>
                  {provenance.isLoading ? (
                    <Skeleton className="h-20" />
                  ) : provenance.isError ? (
                    <ErrorState error={provenance.error} onRetry={() => void provenance.refetch()} />
                  ) : provenance.data ? (
                    <div className="grid grid-cols-3 gap-2 text-center">
                      {[
                        { label: "Entities", value: provenance.data.entity_count },
                        { label: "Relationships", value: provenance.data.relationship_count },
                        { label: "Findings", value: provenance.data.finding_count },
                      ].map((cell) => (
                        <div key={cell.label} className="rounded-lg border border-border bg-surface-2 py-2">
                          <p className="tabular text-base font-semibold text-foreground">{cell.value}</p>
                          <p className="text-[10px] uppercase tracking-wider text-dim">{cell.label}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>

                {selectedDetail.status === "stored" && canIngest ? (
                  <Button className="w-full" disabled={ingest.isPending} onClick={() => void triggerIngest(selectedDetail.id, selectedDetail.original_filename)}>
                    <Workflow className="size-4" /> Ingest record
                  </Button>
                ) : null}
                {canDelete ? (
                  <Button
                    variant="danger"
                    className="w-full"
                    disabled={remove.isPending}
                    onClick={() => setDeleteTarget(selectedDetail.id)}
                  >
                    <Trash2 className="size-4" /> {remove.isPending ? "Deleting…" : "Delete record"}
                  </Button>
                ) : null}
                <p className="text-[11px] leading-relaxed text-dim">
                  Evidence id {shortId(selectedDetail.id)} · status <code className="font-mono">{selectedDetail.status}</code>
                </p>
              </>
            ) : null}
          </div>
        </DrawerContent>
      </Drawer>

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload evidence</DialogTitle>
            <DialogDescription>CSV, JSON or plain text extracts become the source of record for this case.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label>Data source</Label>
              <Select value={dataSource} onValueChange={setDataSource}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Select source…" /></SelectTrigger>
                <SelectContent>
                  {DATA_SOURCES.map((ds) => <SelectItem key={ds.value} value={ds.value}>{ds.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Collection <span className="text-dim">(optional)</span></Label>
              <Select value={collectionId} onValueChange={setCollectionId}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No collection</SelectItem>
                  {(collections.data?.items ?? []).map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name} — {c.status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-dim">
                Placing the record in a sealed collection locks it against edits and ties it to the collection manifest.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>File</Label>
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="w-full rounded-lg border border-dashed border-border-strong bg-surface-2 px-4 py-6 text-center text-xs text-muted transition-colors hover:border-accent/40 hover:bg-surface-3"
              >
                {picked ? (
                  <span className="font-medium text-foreground">{picked.name} · {formatBytes(picked.size)}</span>
                ) : (
                  <>Click to choose a .csv, .json or .txt file</>
                )}
              </button>
              <input ref={fileInput} type="file" accept=".csv,.json,.jsonl,.txt" className="hidden" onChange={onPick} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>Cancel</Button>
            <Button disabled={!picked || upload.isPending} onClick={() => void submitUpload()}>
              {upload.isPending ? "Storing…" : "Upload"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteTarget !== null} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete evidence?</DialogTitle>
            <DialogDescription>
              This permanently removes the stored record from the case. Prior findings and
              relationships that reference it keep their provenance.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => void confirmDelete()}>
              {remove.isPending ? "Deleting…" : "Delete record"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}