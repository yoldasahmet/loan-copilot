"use client";

import { FileUp, Landmark, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type Lender } from "@/lib/api";
import {
  formatPercent,
  LEGAL_FORMS,
  moneyCompact,
  PRODUCT_TYPES,
  SECTORS,
} from "@/lib/format";
import { useApi } from "@/lib/use-api";

const NUMBER_FIELDS = [
  ["min_amount", "Minimum amount (€)"],
  ["max_amount", "Maximum amount (€)"],
  ["min_revenue", "Minimum revenue (€)"],
  ["min_years_trading", "Minimum years trading"],
  ["typical_rate_min", "Typical rate from (e.g. 0.055)"],
  ["typical_rate_max", "Typical rate to (e.g. 0.085)"],
] as const;

function Checklist({
  name,
  options,
  selected,
}: {
  name: string;
  options: Record<string, string>;
  selected: string[];
}) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {Object.entries(options).map(([value, label]) => (
        <label key={value} className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            name={name}
            value={value}
            defaultChecked={selected.includes(value)}
          />
          {label}
        </label>
      ))}
    </div>
  );
}

export function LendersTab() {
  const { data, error, reload } = useApi<Lender[]>("/admin/lenders");
  const [editing, setEditing] = useState<Lender | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const upload = useRef<HTMLInputElement>(null);
  const [uploadFor, setUploadFor] = useState<Lender | null>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      name: f.get("name"),
      product_type: f.get("product_type"),
      excluded_sector_groups: f.getAll("excluded_sector_groups"),
      allowed_legal_forms: f.getAll("allowed_legal_forms"),
      active: f.get("active") === "on",
    };
    for (const [key] of NUMBER_FIELDS) body[key] = Number(f.get(key));
    setBusy(true);
    try {
      if (editing === "new")
        await api("/admin/lenders", {
          method: "POST",
          body: JSON.stringify(body),
        });
      else if (editing)
        await api(`/admin/lenders/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      toast.success(`${body.name} saved`);
      setEditing(null);
      void reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(lender: Lender) {
    if (
      !window.confirm(
        `Delete ${lender.name}? Its historical decisions are deleted too.`,
      )
    )
      return;
    await api(`/admin/lenders/${lender.id}`, { method: "DELETE" });
    toast.success(`${lender.name} deleted`);
    void reload();
  }

  async function uploadCriteria(files: FileList | null) {
    if (!files?.[0] || !uploadFor) return;
    const form = new FormData();
    form.append("file", files[0]);
    try {
      await api(`/admin/lenders/${uploadFor.id}/documents`, {
        method: "POST",
        body: form,
      });
      toast.success(`Criteria uploaded for ${uploadFor.name}`);
      void reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const current = editing && editing !== "new" ? editing : null;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Structured criteria drive the hard checks; criteria PDFs feed the fit
          summaries.
        </p>
        <Button onClick={() => setEditing("new")}>
          <Plus /> Add lender
        </Button>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <TableSkeleton rows={4} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={Landmark}
          title="No lenders yet"
          description="Add the lenders you work with before importing history."
        >
          <Button onClick={() => setEditing("new")}>
            <Plus /> Add lender
          </Button>
        </EmptyState>
      ) : (
        <div className="rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Lender</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Min. revenue</TableHead>
                <TableHead>Years</TableHead>
                <TableHead>Rate</TableHead>
                <TableHead>Criteria</TableHead>
                <TableHead className="pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="pl-4">
                    <div className="font-medium">{l.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {PRODUCT_TYPES[l.product_type] ?? l.product_type}
                      {!l.active && " · inactive"}
                    </div>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {moneyCompact(l.min_amount)} – {moneyCompact(l.max_amount)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {moneyCompact(l.min_revenue)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {l.min_years_trading}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatPercent(Number(l.typical_rate_min), 1)} –{" "}
                    {formatPercent(Number(l.typical_rate_max), 1)}
                  </TableCell>
                  <TableCell>
                    {l.documents.length ? (
                      <Badge variant="secondary">
                        {l.documents.length} PDF
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        none
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="pr-4 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Upload criteria for ${l.name}`}
                      onClick={() => {
                        setUploadFor(l);
                        upload.current?.click();
                      }}
                    >
                      <FileUp />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Edit ${l.name}`}
                      onClick={() => setEditing(l)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${l.name}`}
                      onClick={() => void remove(l)}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <input
        ref={upload}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => void uploadCriteria(e.target.files)}
      />

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      >
        <DialogContent className="sm:max-w-2xl">
          <form onSubmit={save} className="space-y-4">
            <DialogHeader>
              <DialogTitle>
                {current ? `Edit ${current.name}` : "Add lender"}
              </DialogTitle>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-4">
              <Label className="flex flex-col items-stretch gap-2">
                Name
                <Input name="name" required defaultValue={current?.name} />
              </Label>
              <Label className="flex flex-col items-stretch gap-2">
                Product type
                <Input
                  name="product_type"
                  required
                  defaultValue={current?.product_type ?? "term_loan"}
                />
              </Label>
              {NUMBER_FIELDS.map(([key, label]) => (
                <Label key={key} className="flex flex-col items-stretch gap-2">
                  {label}
                  <Input
                    name={key}
                    type="number"
                    step="any"
                    required
                    defaultValue={current ? String(current[key]) : undefined}
                  />
                </Label>
              ))}
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Excluded sectors</p>
              <Checklist
                name="excluded_sector_groups"
                options={SECTORS}
                selected={current?.excluded_sector_groups ?? []}
              />
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Allowed legal forms</p>
              <Checklist
                name="allowed_legal_forms"
                options={LEGAL_FORMS}
                selected={
                  current?.allowed_legal_forms ?? ["bv", "eenmanszaak", "vof"]
                }
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="active"
                defaultChecked={current?.active ?? true}
              />{" "}
              Active
            </label>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditing(null)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={busy}>
                {busy && <Loader2 className="animate-spin" />}
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
