"use client";

import { Check, CircleHelp, Landmark, X } from "lucide-react";
import { useState } from "react";
import { SourcePanel, withCitations } from "@/components/citations";
import { EmptyState, ErrorState } from "@/components/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { LenderMatches, SourceRef } from "@/lib/api";
import { formatPercent, PRODUCT_TYPES } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

export function LendersTab({ caseId }: { caseId: string }) {
  const { data, error, reload } = useApi<LenderMatches>(
    `/cases/${caseId}/lenders`,
  );
  const [source, setSource] = useState<SourceRef | null>(null);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data)
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-80" />
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-44" />
        ))}
      </div>
    );
  if (data.lenders.length === 0)
    return (
      <EmptyState
        icon={Landmark}
        title="No active lenders"
        description="An admin can add lenders in Admin → Lenders."
      />
    );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Lenders failing a hard check are listed last. The others are ordered by
        how often they approved the {data.similar_count} most similar past
        cases. No score: the advisor decides.
      </p>
      {data.errors.length > 0 && (
        <Alert>
          <AlertDescription>
            Fit summaries are unavailable: {data.errors.join(" ")}
          </AlertDescription>
        </Alert>
      )}
      {data.lenders.map((l, index) => {
        const p = l.precedents;
        return (
          <Card
            key={l.lender_id}
            className={cn(!l.passes_hard_checks && "opacity-75")}
          >
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div className="space-y-1">
                <CardTitle className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    {index + 1}.
                  </span>{" "}
                  {l.name}
                  <Badge variant="outline" className="font-normal">
                    {PRODUCT_TYPES[l.product_type] ?? l.product_type}
                  </Badge>
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                  Typical rate {formatPercent(l.typical_rate_min, 1)} –{" "}
                  {formatPercent(l.typical_rate_max, 1)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold tabular-nums">
                  {p.decided > 0 ? `${p.approved} of ${p.decided}` : "—"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {p.decided > 0
                    ? "similar cases approved"
                    : "no similar decisions"}
                  {p.median_granted_ratio !== null &&
                    ` · median ${formatPercent(p.median_granted_ratio)} granted`}
                </p>
              </div>
            </CardHeader>
            <CardContent className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
              <ul className="space-y-1.5 text-sm">
                {l.checks.map((c) => (
                  <li key={c.check} className="flex items-center gap-2">
                    {c.passed === true ? (
                      <Check
                        className="size-4 text-success"
                        aria-label="passed"
                      />
                    ) : c.passed === false ? (
                      <X
                        className="size-4 text-destructive"
                        aria-label="failed"
                      />
                    ) : (
                      <CircleHelp
                        className="size-4 text-muted-foreground"
                        aria-label="unknown"
                      />
                    )}
                    <span className="w-32 text-muted-foreground">
                      {c.check}
                    </span>
                    <span className="font-medium">{c.value}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      ({c.requirement})
                    </span>
                  </li>
                ))}
              </ul>
              <div className="rounded-lg bg-muted/60 p-3 text-sm leading-relaxed">
                {l.summary ? (
                  withCitations(l.summary, data.sources, setSource)
                ) : (
                  <span className="text-muted-foreground">No fit summary.</span>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
      <SourcePanel source={source} onClose={() => setSource(null)} />
    </div>
  );
}
