"use client";

import { AlertTriangle, Check, FileSearch, Pencil, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { type AnalysisData, api, type FinancialYear } from "@/lib/api";
import { FIGURE_LABELS, formatDate, moneyFull } from "@/lib/format";

type Props = {
  caseId: string;
  financials: FinancialYear[];
  onOpenSource: (documentId: string, page: number) => void;
  onSaved: (data: AnalysisData) => void;
};

function FigureCell({
  fy,
  field,
  caseId,
  onOpenSource,
  onSaved,
}: { fy: FinancialYear; field: string } & Omit<Props, "financials">) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const value = fy.values[field];
  const source = fy.sources[field];
  const warnings = fy.warnings.filter((w) => w.field === field);
  const edited = fy.edited_fields.includes(field);

  async function save() {
    const parsed =
      draft.trim() === "" ? null : Number(draft.replace(/[€,\s]/g, ""));
    if (parsed !== null && Number.isNaN(parsed)) {
      toast.error("Enter a number in euros");
      return;
    }
    try {
      onSaved(
        await api<AnalysisData>(`/cases/${caseId}/financials/${fy.year}`, {
          method: "PATCH",
          body: JSON.stringify({ values: { [field]: parsed } }),
        }),
      );
      setEditing(false);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (editing)
    return (
      <div className="flex items-center justify-end gap-1">
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void save();
            if (e.key === "Escape") setEditing(false);
          }}
          className="h-7 w-32 text-right tabular-nums"
        />
        <Button
          size="icon"
          variant="ghost"
          className="size-7"
          onClick={() => void save()}
          aria-label="Save"
        >
          <Check />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="size-7"
          onClick={() => setEditing(false)}
          aria-label="Cancel"
        >
          <X />
        </Button>
      </div>
    );

  return (
    <div className="group flex items-center justify-end gap-1.5">
      {warnings.length > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <AlertTriangle
              className="size-3.5 text-amber-600 dark:text-warning"
              aria-label="Validation warning"
            />
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            {warnings.map((w) => w.message).join(" ")}
          </TooltipContent>
        </Tooltip>
      )}
      {edited && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline" className="h-4 px-1 text-[10px]">
              edited
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            Edited by {fy.edited_by ?? "an advisor"}
            {fy.edited_at && ` on ${formatDate(fy.edited_at)}`}
          </TooltipContent>
        </Tooltip>
      )}
      {source && !edited ? (
        <button
          type="button"
          onClick={() => onOpenSource(source.document_id, source.page)}
          className="tabular-nums underline decoration-dotted decoration-muted-foreground/60 underline-offset-4 hover:decoration-foreground"
          title={`Source: page ${source.page}`}
        >
          {moneyFull(value)}
        </button>
      ) : (
        <span className="tabular-nums">{moneyFull(value)}</span>
      )}
      <Button
        size="icon"
        variant="ghost"
        className="size-6 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
        aria-label={`Edit ${FIGURE_LABELS[field]} ${fy.year}`}
        onClick={() => {
          setDraft(value === null ? "" : String(value));
          setEditing(true);
        }}
      >
        <Pencil className="size-3" />
      </Button>
    </div>
  );
}

export function FiguresTable({
  caseId,
  financials,
  onOpenSource,
  onSaved,
}: Props) {
  const units = new Set(financials.map((f) => f.unit).filter(Boolean));
  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="font-medium">Extracted figures</p>
          <p className="text-xs text-muted-foreground">
            Click a value to open its source page. Hover to edit.
            {units.has("EUR_thousands") &&
              " Reported in € thousands, converted to euros."}
          </p>
        </div>
        <FileSearch className="size-4 text-muted-foreground" />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Figure</TableHead>
            {financials.map((f) => (
              <TableHead key={f.year} className="pr-4 text-right">
                {f.year}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {Object.entries(FIGURE_LABELS).map(([field, label]) => (
            <TableRow key={field}>
              <TableCell className="pl-4 text-muted-foreground">
                {label}
              </TableCell>
              {financials.map((fy) => (
                <TableCell key={fy.year} className="pr-4">
                  <FigureCell
                    fy={fy}
                    field={field}
                    caseId={caseId}
                    onOpenSource={onOpenSource}
                    onSaved={onSaved}
                  />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
