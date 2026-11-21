"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  FileText,
  Loader2,
  ShieldAlert,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { type PdfTarget, PdfViewer } from "@/components/case/pdf-viewer";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api, type Doc } from "@/lib/api";
import { DOCUMENT_KINDS, formatBytes, formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const UPLOAD_KINDS = {
  auto: "Detect automatically",
  annual_report: "Annual report",
  bank_statement: "Bank statement",
  other: "Other",
};

function StatusCell({ doc }: { doc: Doc }) {
  if (doc.status === "failed")
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1.5 text-destructive">
            <XCircle className="size-4" /> Failed
          </span>
        </TooltipTrigger>
        <TooltipContent>{doc.error}</TooltipContent>
      </Tooltip>
    );
  if (doc.status === "indexed")
    return (
      <span className="inline-flex items-center gap-1.5 text-success">
        <CheckCircle2 className="size-4" /> Indexed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />{" "}
      {doc.status === "parsing" ? "Parsing" : "Uploaded"}
    </span>
  );
}

export function DocumentsTab({ caseId }: { caseId: string }) {
  const { data, error, reload } = useApi<Doc[]>(`/cases/${caseId}/documents`);
  const [kind, setKind] = useState("auto");
  const [uploading, setUploading] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [viewer, setViewer] = useState<PdfTarget | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const busy = data?.some(
    (d) => d.status === "uploaded" || d.status === "parsing",
  );
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void reload(), 2000);
    return () => clearInterval(timer);
  }, [busy, reload]);

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files);
    setUploading((n) => n + list.length);
    await Promise.all(
      list.map(async (file) => {
        const form = new FormData();
        form.append("file", file);
        if (kind !== "auto") form.append("kind", kind);
        try {
          await api(`/cases/${caseId}/documents`, {
            method: "POST",
            body: form,
          });
        } catch (e) {
          toast.error(`${file.name}: ${(e as Error).message}`);
        } finally {
          setUploading((n) => n - 1);
        }
      }),
    );
    void reload();
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void uploadFiles(event.dataTransfer.files);
  }

  async function remove(doc: Doc) {
    await api(`/documents/${doc.id}`, { method: "DELETE" });
    toast.success(`${doc.filename} deleted`);
    void reload();
  }

  async function allow(doc: Doc) {
    await api(`/documents/${doc.id}/allow`, { method: "POST" });
    toast.success(`${doc.filename} is now allowed in AI context`);
    void reload();
  }

  return (
    <div className="space-y-6">
      <section
        aria-label="Upload documents"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex items-center justify-between gap-6 rounded-xl border-2 border-dashed px-6 py-6 transition-colors",
          dragging ? "border-primary bg-accent" : "bg-card",
        )}
      >
        <div className="flex items-center gap-4">
          <span className="flex size-11 items-center justify-center rounded-full bg-accent text-accent-foreground">
            {uploading ? (
              <Loader2 className="size-5 animate-spin" />
            ) : (
              <UploadCloud className="size-5" />
            )}
          </span>
          <div>
            <p className="font-medium">
              Drop annual reports and bank statements here
            </p>
            <p className="text-sm text-muted-foreground">
              PDF (digital, not scanned), CAMT.053 XML or CSV · max 20 MB per
              file
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(UPLOAD_KINDS).map(([v, l]) => (
                <SelectItem key={v} value={v}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={() => input.current?.click()}>Choose files</Button>
          <input
            ref={input}
            type="file"
            multiple
            accept=".pdf,.xml,.csv"
            className="hidden"
            onChange={(e) => e.target.files && void uploadFiles(e.target.files)}
          />
        </div>
      </section>

      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <TableSkeleton rows={3} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload the last two annual reports and twelve months of bank statements to start the analysis."
        >
          <Button onClick={() => input.current?.click()}>
            Upload documents
          </Button>
        </EmptyState>
      ) : (
        <div className="rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Document</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Year</TableHead>
                <TableHead className="text-right">Pages</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((doc) => {
                const isPdf = doc.mime === "application/pdf";
                const Icon = isPdf ? FileText : FileSpreadsheet;
                const flagged = doc.injection_flag && !doc.injection_allowed;
                return (
                  <TableRow key={doc.id}>
                    <TableCell className="pl-4">
                      <div className="flex items-center gap-2">
                        <Icon className="size-4 shrink-0 text-muted-foreground" />
                        {isPdf ? (
                          <button
                            type="button"
                            className="font-medium hover:underline"
                            onClick={() =>
                              setViewer({ id: doc.id, filename: doc.filename })
                            }
                          >
                            {doc.filename}
                          </button>
                        ) : (
                          <a
                            className="font-medium hover:underline"
                            href={`/api/documents/${doc.id}/file`}
                          >
                            {doc.filename}
                          </a>
                        )}
                        {flagged && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="destructive" className="gap-1">
                                <ShieldAlert /> Possible prompt injection
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent className="max-w-xs">
                              This document contains text that looks like
                              instructions to an AI. It is excluded from AI
                              context until you allow it.
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{DOCUMENT_KINDS[doc.kind]}</TableCell>
                    <TableCell className="tabular-nums">
                      {doc.year ?? "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {doc.page_count ?? "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatBytes(doc.size_bytes)}
                    </TableCell>
                    <TableCell>
                      <StatusCell doc={doc} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(doc.created_at)}
                    </TableCell>
                    <TableCell className="pr-4 text-right">
                      <div className="flex justify-end gap-1">
                        {flagged && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void allow(doc)}
                          >
                            <AlertTriangle /> Allow
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete ${doc.filename}`}
                          onClick={() => void remove(doc)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <PdfViewer target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}
