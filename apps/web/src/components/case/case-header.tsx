"use client";

import { MoreHorizontal, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, type Case } from "@/lib/api";
import { LEGAL_FORMS, moneyCompact, PURPOSES } from "@/lib/format";

export function CaseHeader({ c }: { c: Case }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);

  async function erase() {
    await api(`/cases/${c.id}`, { method: "DELETE" });
    toast.success("Case and all its data were deleted");
    router.replace("/");
  }

  return (
    <div className="flex items-start justify-between gap-6">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {c.company.name}
          </h1>
          <Badge variant="outline">{LEGAL_FORMS[c.company.legal_form]}</Badge>
          <StatusBadge status={c.status} />
        </div>
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">
            {moneyCompact(c.loan_amount)}
          </span>{" "}
          {PURPOSES[c.loan_purpose].toLowerCase()} · {c.loan_term_months} months
          · Advisor {c.advisor?.name ?? "unassigned"}
        </p>
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" aria-label="Case actions">
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            variant="destructive"
            onClick={() => setConfirm(true)}
          >
            <Trash2 /> Delete case and data
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this case?</DialogTitle>
            <DialogDescription>
              This permanently removes the case, its files, extracted figures,
              transactions, memos and chats (right to erasure). Audit log
              entries keep only their metadata. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void erase()}>
              Delete permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
