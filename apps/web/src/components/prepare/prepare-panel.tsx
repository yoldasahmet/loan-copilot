"use client";

import {
  BarChart3,
  CheckCircle2,
  FileSearch,
  FileText,
  Hourglass,
  Landmark,
  Loader2,
  type LucideIcon,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  UserCheck,
  XCircle,
} from "lucide-react";
import { useEffect } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, type PrepareRun } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  check_documents: FileSearch,
  analyse: BarChart3,
  find_similar: ScanSearch,
  match_lenders: Landmark,
  draft_memo: FileText,
  verify_numbers: ShieldCheck,
  human_review: UserCheck,
};

/** "Prepare application" button and live progress through the 7 agent steps (polls every 2 s). */
export function PreparePanel({
  caseId,
  onChange,
}: {
  caseId: string;
  onChange?: () => void;
}) {
  const {
    data: run,
    reload,
    setData,
  } = useApi<PrepareRun | null>(`/cases/${caseId}/prepare`);
  const active = run?.status === "running";

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void reload(), 2000);
    return () => clearInterval(timer);
  }, [active, reload]);

  useEffect(() => {
    if (run && run.status !== "running") onChange?.();
  }, [run?.status, run, onChange]);

  async function start() {
    try {
      setData(
        await api<PrepareRun>(`/cases/${caseId}/prepare`, { method: "POST" }),
      );
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <Card className="gap-0 py-4">
      <CardContent className="space-y-4 px-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 font-medium">
              <Sparkles className="size-4 text-primary" /> Prepare application
            </p>
            <p className="text-sm text-muted-foreground">
              {run?.status === "waiting_review"
                ? "The memo is ready for your review in the Memo tab."
                : run?.status === "done"
                  ? "Completed. The memo was reviewed."
                  : run?.status === "failed"
                    ? `Stopped: ${run.error ?? "unknown error"}`
                    : active
                      ? "Working through the steps…"
                      : "Analyse documents, find precedents and lenders, and draft a cited memo."}
            </p>
          </div>
          <Button
            onClick={() => void start()}
            disabled={active}
            variant={run ? "outline" : "default"}
          >
            {active ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {run ? "Prepare again" : "Prepare application"}
          </Button>
        </div>
        {run && (
          <ol className="grid grid-cols-7 gap-2">
            {run.steps.map((step) => {
              const Icon = ICONS[step.name] ?? FileText;
              return (
                <li
                  key={step.name}
                  title={step.note ?? undefined}
                  className={cn(
                    "flex flex-col items-center gap-1.5 rounded-lg border px-2 py-2.5 text-center",
                    step.status === "done" && "border-success/30 bg-success/5",
                    step.status === "running" && "border-primary/40 bg-accent",
                    step.status === "waiting" &&
                      "border-warning/50 bg-warning/10",
                    step.status === "failed" &&
                      "border-destructive/40 bg-destructive/5",
                  )}
                >
                  <span className="relative">
                    <Icon className="size-5 text-muted-foreground" />
                    {step.status === "done" && (
                      <CheckCircle2 className="absolute -right-2 -bottom-1.5 size-3.5 rounded-full bg-card text-success" />
                    )}
                    {step.status === "running" && (
                      <Loader2 className="absolute -right-2 -bottom-1.5 size-3.5 animate-spin rounded-full bg-card text-primary" />
                    )}
                    {step.status === "waiting" && (
                      <Hourglass className="absolute -right-2 -bottom-1.5 size-3.5 rounded-full bg-card text-amber-600" />
                    )}
                    {step.status === "failed" && (
                      <XCircle className="absolute -right-2 -bottom-1.5 size-3.5 rounded-full bg-card text-destructive" />
                    )}
                  </span>
                  <span className="text-xs leading-tight font-medium">
                    {step.label}
                  </span>
                  {step.note && (
                    <span className="line-clamp-2 text-[11px] leading-tight text-muted-foreground">
                      {step.note}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
