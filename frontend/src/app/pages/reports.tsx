import { useState } from "react";
import { useParams } from "react-router-dom";
import { FileText, Download, RefreshCw } from "lucide-react";
import { api } from "@/api";
import { useReports, useGenerateReport } from "@/hooks/queries";
import { PageContainer } from "@/components/layout/page";
import { InvestigationHeader } from "@/components/layout/investigation-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label, Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import { formatBytes, formatRelative } from "@/lib/utils";

const REPORT_TYPES = [
  { value: "case_summary", label: "Case summary" },
  { value: "intelligence", label: "Intelligence" },
  { value: "evidence_manifest", label: "Evidence manifest" },
  { value: "timeline", label: "Timeline" },
  { value: "network_analysis", label: "Network analysis" },
];

const REPORT_FORMATS = [
  { value: "json", label: "JSON" },
  { value: "csv", label: "CSV" },
  { value: "pdf", label: "PDF" },
];

function statusMeta(status: string): { label: string; tone: "success" | "info" | "critical" | "high" } {
  if (status === "ready") return { label: "Ready", tone: "success" };
  if (status === "failed") return { label: "Failed", tone: "critical" };
  return { label: "Generating", tone: "info" };
}

const TYPE_LABELS: Record<string, string> = {
  case_summary: "Case summary",
  intelligence: "Intelligence",
  evidence_manifest: "Evidence manifest",
  timeline: "Timeline",
  network_analysis: "Network analysis",
};

function typeLabel(reportType: string) {
  return TYPE_LABELS[reportType] ?? reportType.replace(/_/g, " ");
}

export default function ReportsPage() {
  const { caseId = "" } = useParams();
  const reports = useReports(caseId);
  const generate = useGenerateReport(caseId);
  const [open, setOpen] = useState(false);
  const [reportType, setReportType] = useState("case_summary");
  const [format, setFormat] = useState("json");
  const [title, setTitle] = useState("");

  const triggerGenerate = async (input?: { report_type: string; format: string; title?: string }) => {
    const payload = input ?? { report_type: reportType, format, title: title || undefined };
    try {
      const created = await generate.mutateAsync(payload);
      if (created.status === "ready") {
        toast({ title: "Report ready", description: `The ${typeLabel(created.report_type)} report was generated and is ready to download.` });
      } else if (created.status === "failed") {
        toast({ title: "Report failed", description: created.failure_reason ?? "Generation failed — retry from the reports list." });
      } else {
        toast({ title: "Report queued", description: `${typeLabel(created.report_type)} will be ready shortly.` });
      }
      setOpen(false);
      setTitle("");
    } catch (err) {
      toast({ title: "Could not generate report", description: (err as Error).message });
    }
  };

  const downloadReport = async (reportId: string, fallbackName: string) => {
    try {
      const { blob, filename } = await api.reports.download(caseId, reportId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename || fallbackName;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast({ title: "Download failed", description: (err as Error).message });
    }
  };

  return (
    <PageContainer>
      <InvestigationHeader
        eyebrow="Exportable records"
        title="Reports"
        description="Generate and download case reports — summaries, intelligence, evidence manifests, timelines and network analysis in JSON, CSV or PDF."
        actions={
          <Button onClick={() => setOpen(true)}>
            <FileText className="size-4" /> Generate report
          </Button>
        }
      />

      <div className="mt-4">
        {reports.isLoading ? (
          <Card><CardContent className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
          </CardContent></Card>
        ) : reports.isError ? (
          <Card><ErrorState error={reports.error} onRetry={() => void reports.refetch()} /></Card>
        ) : (reports.data?.items ?? []).length === 0 ? (
          <Card><EmptyState title="No reports yet" description="Generate a case summary, evidence manifest, timeline or network analysis export." /></Card>
        ) : (
          <Card>
            <Table>
              <THead>
                <TR>
                  <TH>Title</TH>
                  <TH className="hidden sm:table-cell">Type</TH>
                  <TH className="hidden md:table-cell">Format</TH>
                  <TH>Status</TH>
                  <TH className="hidden md:table-cell">Size</TH>
                  <TH className="hidden lg:table-cell">Created</TH>
                  <TH className="w-28" />
                </TR>
              </THead>
              <TBody>
                {(reports.data?.items ?? []).map((report) => {
                  const meta = statusMeta(report.status);
                  return (
                    <TR key={report.id}>
                      <TD className="max-w-[260px] truncate font-medium text-foreground">{report.title}</TD>
                      <TD className="hidden sm:table-cell">
                        <span className="font-mono text-xs text-muted">{report.report_type}</span>
                      </TD>
                      <TD className="hidden font-mono text-xs text-muted md:table-cell">{report.format}</TD>
                      <TD><Badge tone={meta.tone}>{meta.label}</Badge></TD>
                      <TD className="hidden tabular text-xs text-muted md:table-cell">
                        {report.byte_size != null ? formatBytes(report.byte_size) : "—"}
                      </TD>
                      <TD className="hidden text-xs text-dim lg:table-cell" title={report.created_at}>
                        {formatRelative(report.created_at)}
                      </TD>
                      <TD className="text-right">
                        {report.status === "ready" ? (
                          <Button size="sm" variant="ghost" onClick={() => void downloadReport(report.id, `${report.report_type}-report.${report.format}`)}>
                            <Download className="size-3.5" /> Download
                          </Button>
                        ) : report.status === "failed" ? (
                          <div className="flex flex-col items-end gap-1">
                            {report.failure_reason ? (
                              <span className="max-w-[220px] truncate text-[10px] text-critical" title={report.failure_reason}>
                                {report.failure_reason}
                              </span>
                            ) : null}
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={generate.isPending}
                              onClick={() =>
                                void triggerGenerate({
                                  report_type: report.report_type,
                                  format: report.format,
                                  title: report.title,
                                })
                              }
                            >
                              <RefreshCw className="size-3.5" /> Retry
                            </Button>
                          </div>
                        ) : (
                          <Button size="sm" variant="ghost" disabled>
                            <RefreshCw className="size-3.5 animate-spin" />
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

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate report</DialogTitle>
            <DialogDescription>Reports are generated from the current case state and stored for download.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label>Report type</Label>
              <Select value={reportType} onValueChange={setReportType}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {REPORT_TYPES.map((rt) => <SelectItem key={rt.value} value={rt.value}>{rt.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Format</Label>
              <Select value={format} onValueChange={setFormat}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {REPORT_FORMATS.map((rf) => <SelectItem key={rf.value} value={rf.value}>{rf.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Title (optional)</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`${reportType.replace("_", " ")} — Case`} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={generate.isPending} onClick={() => void triggerGenerate()}>
              {generate.isPending ? "Generating…" : "Generate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}