"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  MessageSquareWarning,
  ShieldCheck,
} from "lucide-react";
import { Children, isValidElement, type ReactNode, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { SourcePanel, withCitations } from "@/components/citations";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api, type Memo, type MemoSource, type SourceRef } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const STATUS = {
  draft: {
    label: "Draft",
    className: "bg-secondary text-secondary-foreground",
  },
  approved: { label: "Approved", className: "bg-success/15 text-success" },
  changes_requested: {
    label: "Changes requested",
    className: "bg-warning/20 text-amber-700 dark:text-warning",
  },
};

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Citation chips plus a highlight on every number the verifier could not match. */
function enrich(
  node: ReactNode,
  sources: SourceRef[],
  unverified: string[],
  onCite: (s: SourceRef) => void,
): ReactNode {
  return Children.map(node, (child) => {
    if (typeof child !== "string") return isValidElement(child) ? child : child;
    if (unverified.length === 0) return withCitations(child, sources, onCite);
    const pattern = new RegExp(
      `(${unverified.map(escapeRegex).join("|")})`,
      "g",
    );
    return child.split(pattern).map((part, i) =>
      unverified.includes(part) ? (
        <Tooltip
          // biome-ignore lint/suspicious/noArrayIndexKey: parts of one immutable string
          key={i}
        >
          <TooltipTrigger asChild>
            <mark className="rounded bg-destructive/15 px-0.5 text-destructive underline decoration-dotted">
              {part}
            </mark>
          </TooltipTrigger>
          <TooltipContent>
            Not found in the sources. Check before approving.
          </TooltipContent>
        </Tooltip>
      ) : (
        withCitations(part, sources, onCite)
      ),
    );
  });
}

export function MemoTab({
  caseId,
  onReviewed,
}: {
  caseId: string;
  onReviewed?: () => void;
}) {
  const [version, setVersion] = useState<number | null>(null);
  const path = `/cases/${caseId}/memo${version ? `?version=${version}` : ""}`;
  const { data: memo, error, loading, reload } = useApi<Memo | null>(path);
  const [source, setSource] = useState<SourceRef | null>(null);
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function review(action: "approve" | "request-changes") {
    setBusy(true);
    try {
      const body =
        action === "request-changes" ? JSON.stringify({ note }) : undefined;
      await api(`/cases/${caseId}/memo/${action}`, { method: "POST", body });
      toast.success(
        action === "approve"
          ? "Memo approved. The case is ready."
          : "Changes requested. A new version is being drafted.",
      );
      setAsking(false);
      setNote("");
      setVersion(null);
      void reload();
      onReviewed?.();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !memo)
    return (
      <div className="space-y-4">
        <Skeleton className="h-14" />
        <Skeleton className="h-96" />
      </div>
    );
  if (!memo)
    return (
      <EmptyState
        icon={FileText}
        title="No memo yet"
        description="Use “Prepare application” above to analyse the case, find precedents and lenders, and draft a cited memo."
      />
    );

  const v = memo.verification;
  const unverified = v.unverified ?? [];
  const isLatest =
    memo.version === memo.versions[memo.versions.length - 1]?.version;
  const firstDraft = v.attempts?.[0];
  const sources = memo.sources.map((s: MemoSource) => ({
    ...s,
    filename: s.filename ?? s.title,
  }));
  const status = STATUS[memo.status];
  const enrichAll = (children: ReactNode) =>
    enrich(children, sources, unverified, setSource);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Select
            value={String(memo.version)}
            onValueChange={(value) => setVersion(Number(value))}
          >
            <SelectTrigger className="w-56" aria-label="Memo version">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {memo.versions.map((x) => (
                <SelectItem key={x.version} value={String(x.version)}>
                  Version {x.version} · {formatDate(x.created_at)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Badge className={status.className}>{status.label}</Badge>
          {memo.approved_by && (
            <span className="text-sm text-muted-foreground">
              by {memo.approved_by} on {formatDate(memo.approved_at)}
            </span>
          )}
        </div>
        {isLatest && memo.status === "draft" && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setAsking(true)}
              disabled={busy}
            >
              <MessageSquareWarning /> Request changes
            </Button>
            <Button onClick={() => void review("approve")} disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}{" "}
              Approve
            </Button>
          </div>
        )}
      </div>

      <div
        className={cn(
          "flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border px-4 py-3 text-sm",
          unverified.length
            ? "border-destructive/30 bg-destructive/5"
            : "border-success/30 bg-success/5",
        )}
      >
        <span className="flex items-center gap-2 font-medium">
          {unverified.length ? (
            <AlertTriangle className="size-4 text-destructive" />
          ) : (
            <ShieldCheck className="size-4 text-success" />
          )}
          {v.verified ?? 0} of {v.total ?? 0} numbers verified against the
          sources
        </span>
        {unverified.length > 0 && (
          <span className="text-destructive">
            Unverified: {unverified.join(", ")}
          </span>
        )}
        {firstDraft && (v.attempts?.length ?? 0) > 1 && (
          <span className="text-muted-foreground">
            First draft had {firstDraft.unverified.length} unverified, redrafted{" "}
            {(v.attempts?.length ?? 1) - 1}×
          </span>
        )}
        {v.missing_sections && v.missing_sections.length > 0 && (
          <span className="text-destructive">
            Missing sections: {v.missing_sections.join(", ")}
          </span>
        )}
        <span className="ml-auto text-muted-foreground">
          {memo.sources.length} sources · no recommendation, the advisor decides
        </span>
      </div>

      {memo.review_note && (
        <p className="rounded-lg bg-muted px-4 py-3 text-sm">
          <span className="font-medium">Requested changes:</span>{" "}
          {memo.review_note}
        </p>
      )}

      <Card>
        <CardContent className="memo prose-sm max-w-none px-8 py-6 text-sm leading-relaxed">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h2: ({ children }) => (
                <h2 className="mt-6 mb-2 text-base font-semibold first:mt-0">
                  {children}
                </h2>
              ),
              p: ({ children }) => (
                <p className="mb-3">{enrichAll(children)}</p>
              ),
              li: ({ children }) => (
                <li className="mb-1">{enrichAll(children)}</li>
              ),
              ul: ({ children }) => (
                <ul className="mb-3 list-disc pl-5">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="mb-3 list-decimal pl-5">{children}</ol>
              ),
              strong: ({ children }) => (
                <strong className="font-semibold">{enrichAll(children)}</strong>
              ),
              td: ({ children }) => (
                <td className="border px-2 py-1">{enrichAll(children)}</td>
              ),
              th: ({ children }) => (
                <th className="border bg-muted px-2 py-1 text-left">
                  {children}
                </th>
              ),
            }}
          >
            {memo.content_md}
          </ReactMarkdown>
        </CardContent>
      </Card>

      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request changes</DialogTitle>
            <DialogDescription>
              A new version is drafted with your note. The current version is
              kept.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            placeholder="What should change?"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setAsking(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => void review("request-changes")}
              disabled={busy || note.trim().length < 3}
            >
              {busy && <Loader2 className="animate-spin" />}
              Request changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <SourcePanel source={source} onClose={() => setSource(null)} />
    </div>
  );
}
