"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { CashflowMonth } from "@/lib/api";
import { moneyCompact, moneyFull, monthLabel } from "@/lib/format";

const config = {
  inflow: { label: "Inflow", color: "var(--chart-2)" },
  outflow: { label: "Outflow", color: "var(--chart-3)" },
  end_balance: { label: "End-of-month balance", color: "var(--chart-1)" },
} satisfies ChartConfig;

export function CashflowChart({ months }: { months: CashflowMonth[] }) {
  const data = months.map((m) => ({ ...m, label: monthLabel(m.month) }));
  const hasBalance = months.some((m) => m.end_balance !== null);
  return (
    <ChartContainer config={config} className="aspect-auto h-72 w-full">
      <ComposedChart data={data} margin={{ left: 8, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={64}
          tickFormatter={(v: number) => moneyCompact(v)}
        />
        <ReferenceLine y={0} stroke="var(--border)" />
        <ChartTooltip
          content={
            <ChartTooltipContent
              formatter={(value, name) => (
                <div className="flex w-full justify-between gap-4">
                  <span className="text-muted-foreground">
                    {config[name as keyof typeof config]?.label}
                  </span>
                  <span className="font-medium tabular-nums">
                    {moneyFull(value as number)}
                  </span>
                </div>
              )}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar
          isAnimationActive={false}
          dataKey="inflow"
          fill="var(--color-inflow)"
          radius={[3, 3, 0, 0]}
          maxBarSize={22}
        />
        <Bar
          isAnimationActive={false}
          dataKey="outflow"
          fill="var(--color-outflow)"
          radius={[3, 3, 0, 0]}
          maxBarSize={22}
        />
        {hasBalance && (
          <Line
            isAnimationActive={false}
            dataKey="end_balance"
            type="monotone"
            stroke="var(--color-end_balance)"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        )}
      </ComposedChart>
    </ChartContainer>
  );
}
