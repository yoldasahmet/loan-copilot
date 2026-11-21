"use client";

import { CheckCircle2, CircleSlash, History, XCircle } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { PrecedentDecision, SimilarCase } from "@/lib/api";
import {
  formatDate,
  formatPercent,
  LEGAL_FORMS,
  moneyCompact,
  moneyFull,
  PURPOSES,
  SECTORS,
} from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const DECISION_STYLE = {
  approved: {
    icon: CheckCircle2,
    className: "text-success",
    label: "Approved",
  },
  declined: { icon: XCircle, className: "text-destructive", label: "Declined" },
  withdrawn: {
    icon: CircleSlash,
    className: "text-muted-foreground",
    label: "Withdrawn",
  },
};

function DecisionRow({ d }: { d: PrecedentDecision }) {
  const style = DECISION_STYLE[d.decision];
  return (
    <li className="flex items-start gap-3 py-2.5 text-sm">
      <style.icon className={cn("mt-0.5 size-4 shrink-0", style.className)} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="font-medium">{d.lender ?? "Unknown lender"}</span>
          <span className="text-xs text-muted-foreground">
            {formatDate(d.decided_on)}
          </span>
        </div>
        {d.decision === "approved" ? (
          <p className="text-muted-foreground">
            {moneyFull(d.amount_granted)}
            {d.interest_rate !== null &&
              ` at ${formatPercent(d.interest_rate, 1)}`}
            {d.term_months && ` · ${d.term_months} months`}
          </p>
        ) : (
          <p className="text-muted-foreground">
            {d.decline_reason ?? style.label}
          </p>
        )}
      </div>
    </li>
  );
}

export function SimilarTab({ caseId }: { caseId: string }) {
  const { data, error, reload } = useApi<SimilarCase[]>(
    `/cases/${caseId}/similar`,
  );
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data)
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-56" />
        ))}
      </div>
    );
  if (data.length === 0)
    return (
      <EmptyState
        icon={History}
        title="No similar cases yet"
        description="Similar cases come from imported history. An admin can import past applications in Admin → History import."
      />
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        The {data.length} most similar past applications decided before this
        one, matched on profile only. Outcomes are shown, never used for
        matching.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        {data.map((s) => (
          <Card key={s.case_id} className="gap-3">
            <CardHeader className="gap-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-semibold">{s.ref}</span>
                <span className="text-xs text-muted-foreground">
                  Applied {formatDate(s.applied_on)}
                </span>
              </div>
              <p className="text-sm">
                {s.sector_group ? SECTORS[s.sector_group] : "Unknown sector"} ·{" "}
                {LEGAL_FORMS[s.legal_form]} · revenue {moneyCompact(s.revenue)}
                {s.solvency !== null &&
                  ` · solvency ${formatPercent(s.solvency)}`}
              </p>
              <p className="text-sm text-muted-foreground">
                {moneyCompact(s.loan_amount)}{" "}
                {PURPOSES[s.loan_purpose]?.toLowerCase()} · {s.term_months}{" "}
                months
              </p>
              <div className="flex flex-wrap gap-1.5">
                {s.reasons.map((r) => (
                  <Badge key={r} variant="secondary" className="font-normal">
                    {r}
                  </Badge>
                ))}
              </div>
            </CardHeader>
            <CardContent>
              <ul className="divide-y border-t">
                {s.decisions.map((d) => (
                  <DecisionRow key={`${d.lender}-${d.decided_on}`} d={d} />
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
