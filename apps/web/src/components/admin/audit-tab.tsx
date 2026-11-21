"use client";

import { ScrollText } from "lucide-react";
import { useState } from "react";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AuditDetail, AuditRow } from "@/lib/api";
import { useApi } from "@/lib/use-api";

const KINDS = [
  "extraction",
  "query_rewrite",
  "chat",
  "lender_reasons",
  "memo",
  "eval_judge",
];

function when(value: string): string {
  return new Date(value).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AuditTab() {
  const [kind, setKind] = useState("all");
  const { data, error, reload } = useApi<AuditRow[]>(
    `/admin/audit${kind === "all" ? "" : `?kind=${kind}`}`,
  );
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useApi<AuditDetail>(
    selected ? `/admin/audit/${selected}` : null,
  );
  const totals = data?.reduce(
    (acc, r) => ({
      tokens: acc.tokens + r.input_tokens + r.output_tokens,
      cost: acc.cost + r.cost_usd,
    }),
    {
      tokens: 0,
      cost: 0,
    },
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          Every AI call with model, prompt version, tokens, latency and cost.
          Prompts are never stored.
          {totals &&
            ` ${data?.length} calls · ${totals.tokens.toLocaleString("en-GB")} tokens · $${totals.cost.toFixed(4)}`}
        </p>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-44" aria-label="Filter by kind">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All kinds</SelectItem>
            {KINDS.map((k) => (
              <SelectItem key={k} value={k}>
                {k.replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <TableSkeleton />
      ) : data.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No AI calls yet"
          description="Calls appear here as soon as documents are analysed or questions are asked."
        />
      ) : (
        <div className="rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Time</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Case</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Prompt</TableHead>
                <TableHead className="text-right">Tokens in / out</TableHead>
                <TableHead className="text-right">Latency</TableHead>
                <TableHead className="pr-4 text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(r.id)}
                >
                  <TableCell className="pl-4 whitespace-nowrap text-muted-foreground">
                    {when(r.created_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {r.kind.replace("_", " ")}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-48 truncate">
                    {r.case_label ?? "—"}
                  </TableCell>
                  <TableCell className="max-w-48 truncate font-mono text-xs">
                    {r.model}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.prompt_version}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {r.input_tokens.toLocaleString("en-GB")} /{" "}
                    {r.output_tokens.toLocaleString("en-GB")}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {(r.latency_ms / 1000).toFixed(1)} s
                  </TableCell>
                  <TableCell className="pr-4 text-right tabular-nums">
                    ${r.cost_usd.toFixed(4)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Sheet
        open={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        <SheetContent className="flex flex-col gap-0 data-[side=right]:w-[min(620px,92vw)] data-[side=right]:sm:max-w-none">
          <SheetHeader className="border-b">
            <SheetTitle>
              {detail.data
                ? `${detail.data.kind.replace("_", " ")} · ${detail.data.prompt_version}`
                : "AI call"}
            </SheetTitle>
            <SheetDescription>
              {detail.data &&
                `${detail.data.model} · ${detail.data.case_label ?? "no case"} · ${when(detail.data.created_at)}`}
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-sm">
            {detail.data && (
              <>
                <section className="space-y-2">
                  <h3 className="font-medium">
                    Sources used ({detail.data.source_count})
                  </h3>
                  {detail.data.sources.length === 0 ? (
                    <p className="text-muted-foreground">
                      Memo sources are stored with the memo version.
                    </p>
                  ) : (
                    detail.data.sources.map((s) => (
                      <div key={s.chunk_id} className="rounded-lg border p-3">
                        <p className="mb-1 text-xs text-muted-foreground">
                          {s.section ?? "Passage"}{" "}
                          {s.page_from && `· page ${s.page_from}`}
                        </p>
                        <p className="line-clamp-4 whitespace-pre-wrap">
                          {s.text}
                        </p>
                      </div>
                    ))
                  )}
                </section>
                <section className="space-y-2">
                  <h3 className="font-medium">Output</h3>
                  <pre className="rounded-lg bg-muted p-3 font-sans whitespace-pre-wrap">
                    {detail.data.output_text ??
                      "Removed when the case was deleted."}
                  </pre>
                </section>
              </>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
