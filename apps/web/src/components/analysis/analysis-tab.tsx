"use client";

import { BarChart3, Loader2, Play, RefreshCw } from "lucide-react";
import { useState } from "react";
import { CashflowChart } from "@/components/analysis/cashflow-chart";
import { FiguresTable } from "@/components/analysis/figures-table";
import { RatioCards } from "@/components/analysis/ratio-cards";
import { RedFlagList } from "@/components/analysis/red-flags";
import { useAnalysis } from "@/components/analysis/use-analysis";
import { type PdfTarget, PdfViewer } from "@/components/case/pdf-viewer";
import { EmptyState, ErrorState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Doc } from "@/lib/api";
import {
  CATEGORY_LABELS,
  formatDate,
  formatPercent,
  moneyCompact,
  moneyFull,
} from "@/lib/format";
import { useApi } from "@/lib/use-api";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export function AnalysisTab({ caseId }: { caseId: string }) {
  const { data, error, reload, run, setData } = useAnalysis(caseId);
  const docs = useApi<Doc[]>(`/cases/${caseId}/documents`);
  const [viewer, setViewer] = useState<PdfTarget | null>(null);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data)
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );

  const openSource = (documentId: string, page: number) => {
    const doc = docs.data?.find((d) => d.id === documentId);
    setViewer({
      id: documentId,
      filename: doc?.filename ?? "Source document",
      page,
    });
  };
  const hasResults = data.computed_at !== null;
  const cf = data.cashflow;
  const a = data.ratios?.assumptions;

  return (
    <div className="space-y-6" data-analysis-ready={!data.running}>
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          {data.running
            ? "Extracting figures and computing ratios…"
            : hasResults
              ? `Computed ${formatDate(data.computed_at)}. All numbers are calculated in code.`
              : "Not analysed yet."}
        </p>
        <Button
          onClick={() => void run()}
          disabled={data.running}
          variant={hasResults ? "outline" : "default"}
        >
          {data.running ? (
            <Loader2 className="animate-spin" />
          ) : hasResults ? (
            <RefreshCw />
          ) : (
            <Play />
          )}
          {hasResults ? "Run again" : "Run analysis"}
        </Button>
      </div>

      {data.ratios?.errors?.length ? (
        <Alert variant="destructive">
          <AlertTitle>Some reports could not be extracted</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {data.ratios.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      {!hasResults && !data.running ? (
        <EmptyState
          icon={BarChart3}
          title="No analysis yet"
          description="Upload annual reports and bank statements, then run the analysis to extract figures and compute ratios."
        >
          <Button onClick={() => void run()}>
            <Play /> Run analysis
          </Button>
        </EmptyState>
      ) : !hasResults ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <>
          {data.ratios && data.ratios.items.length > 0 && (
            <section className="space-y-3">
              <h2 className="font-semibold">Ratios {data.ratios.year}</h2>
              <RatioCards ratios={data.ratios.items} />
              {a && (
                <p className="text-xs text-muted-foreground">
                  DSCR assumes the requested {moneyFull(a.loan_amount)} over{" "}
                  {a.term_months} months at {formatPercent(a.interest_rate, 1)}{" "}
                  interest (annual debt service{" "}
                  {moneyFull(a.new_annual_debt_service)}
                  ), plus existing debt service of{" "}
                  {moneyFull(a.existing_annual_debt_service)}
                  {a.existing_debt_service_from_statements
                    ? " from loan repayments in the bank statements."
                    : " (no bank statements yet)."}
                </p>
              )}
            </section>
          )}

          {data.financials.length > 0 && (
            <FiguresTable
              caseId={caseId}
              financials={data.financials}
              onOpenSource={openSource}
              onSaved={setData}
            />
          )}

          {cf && (
            <div className="grid gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Cash flow</CardTitle>
                  <CardDescription>
                    {formatDate(cf.period_start)} – {formatDate(cf.period_end)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid grid-cols-4 gap-4">
                    <Metric
                      label="Avg. monthly inflow"
                      value={moneyCompact(cf.avg_monthly_inflow)}
                    />
                    <Metric
                      label="Months with negative net"
                      value={String(cf.months_negative_net)}
                    />
                    <Metric
                      label="Days below zero"
                      value={
                        cf.negative_balance_days === null
                          ? "—"
                          : String(cf.negative_balance_days)
                      }
                    />
                    <Metric
                      label="Top customer share"
                      value={formatPercent(cf.top_customer_share)}
                    />
                  </div>
                  <CashflowChart months={cf.months} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Red flags</CardTitle>
                  <CardDescription>
                    Thresholds are set in code, not by the AI.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <RedFlagList flags={data.red_flags} />
                </CardContent>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Transaction categories</CardTitle>
                  <CardDescription>
                    Last 12 months, categorised with keyword rules.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <CategoryBreakdown categories={cf.categories} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Tax payments per quarter</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm">
                    {cf.tax_per_quarter.map((q) => (
                      <li key={q.quarter} className="flex justify-between">
                        <span className="text-muted-foreground">
                          {q.quarter.replace("-", " ")}
                        </span>
                        <span
                          className={
                            q.amount === 0
                              ? "font-medium text-destructive"
                              : "tabular-nums"
                          }
                        >
                          {q.amount === 0 ? "No payment" : moneyFull(q.amount)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}
      <PdfViewer target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}

function CategoryBreakdown({
  categories,
}: {
  categories: { category: string; in: number; out: number }[];
}) {
  const max = Math.max(...categories.map((c) => Math.max(c.in, c.out)), 1);
  const rows = [...categories].sort((a, b) => b.in + b.out - (a.in + a.out));
  return (
    <ul className="space-y-3">
      {rows.map((c) => {
        const amount = c.in || c.out;
        const incoming = c.in >= c.out;
        return (
          <li
            key={c.category}
            className="grid grid-cols-[9rem_1fr_7rem] items-center gap-3 text-sm"
          >
            <span className="text-muted-foreground">
              {CATEGORY_LABELS[c.category] ?? c.category}
            </span>
            <div className="h-2 rounded-full bg-muted">
              <div
                className={
                  incoming
                    ? "h-2 rounded-full bg-chart-2"
                    : "h-2 rounded-full bg-chart-3"
                }
                style={{ width: `${(amount / max) * 100}%` }}
              />
            </div>
            <span className="text-right tabular-nums">
              {incoming ? "+" : "−"}
              {moneyFull(amount)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
